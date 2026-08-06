"""
Solution Agent — nodo LangGraph (S4).

Sigue `docs/specs/spec-solution-agent.md`: router determinista (código, no
LLM) + 2 workers de naturaleza distinta.
  - Worker A (verificación documental): NO es un agente ReAct — 1 llamada al
    modelo (perfil `fast`) sobre el runbook/doc EXACTO que el RCA ya citó,
    con como mucho 1 tool call de verificación al código.
  - Worker B (investigación de código): SÍ es un agente ReAct real, hermano
    del RCA Agent, montado sobre `react_agent.py` — solo se activa cuando el
    RCA no citó ninguna fuente documental.

El router decide por código cuál usar (`_route`), sin invocar ningún modelo
— auditable con un test unitario puro, sin dobles de `complete_fn`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, Literal

from .. import rag
from ..config import AgentLimits, DEFAULT_LIMITS
from ..models import Completion, complete
from ..observability import traced
from ..state import SOLUTION_STATUSES, IncidentState
from ..tools import TOOL_SCHEMAS, run_tool
from .rca_agent import MAX_CALLS_PER_TOOL  # mismo tope y mismo motivo — ver rca_agent.py
from .react_agent import ReActAgent

CompleteFn = Callable[..., Completion]

_PROFILE_A = "fast"   # Worker A: extracción/adaptación acotada, no razonamiento causal
_PROFILE_B = "smart"  # Worker B: exploración + juicio real, mismo criterio que RCA

_PROMPT_DIR = Path(__file__).resolve().parents[3] / "docs" / "specs"
_WORKER_A_SYSTEM_PROMPT = (_PROMPT_DIR / "solution-worker-a-prompt.md").read_text(encoding="utf-8")
_WORKER_B_SYSTEM_PROMPT = (_PROMPT_DIR / "solution-worker-b-prompt.md").read_text(encoding="utf-8")

_WORKER_A_TOOL_NAMES = {"read_codebase_repo"}
WORKER_A_TOOL_SCHEMAS = [s for s in TOOL_SCHEMAS if s["function"]["name"] in _WORKER_A_TOOL_NAMES]

_WORKER_B_TOOL_NAMES = {"search_codebase", "read_codebase_repo", "query_incident_history"}
WORKER_B_TOOL_SCHEMAS = [s for s in TOOL_SCHEMAS if s["function"]["name"] in _WORKER_B_TOOL_NAMES]

# Presupuesto elevado para Worker B en P1+P2 (spec, sección "Worker B"): a
# diferencia de RCA (que corre en el 100% de las incidencias y por eso
# limita el presupuesto elevado a solo P1), Worker B ya es un subconjunto
# acotado del tráfico — solo se activa cuando no hay evidencia documental
# citada. VALORES SIN MEDIR TODAVÍA: se reutilizan los mismos números que
# RCA_LIMITS_P1 como punto de partida razonable, no como resultado de una
# medición real — la spec lo marca explícitamente como "hipótesis a validar
# con medición real", igual que se hizo con RCA_LIMITS_P1 en S3.
SOLUTION_LIMITS_ELEVATED = AgentLimits(max_iterations=12, token_budget=150_000)


# --- Router (spec, "Router — lógica exacta") --------------------------------

def _route(state: IncidentState) -> Literal["worker_a", "worker_b"]:
    """Función de código pura, sin invocar ningún modelo — testeable con un
    test unitario normal, sin dobles de `complete_fn`.

    Deliberadamente NO usa `rca_incident_source_ids` como disparador (spec):
    un incidente histórico parecido no garantiza un procedimiento
    reutilizable, a diferencia de un runbook o doc técnico.
    """
    if state.get("rca_runbook_ids") or state.get("rca_technical_doc_ids"):
        return "worker_a"
    return "worker_b"


# --- Helpers duplicados de rca_agent.py (mismo patrón ya establecido en el
# proyecto: pequeños helpers de parseo se duplican en vez de compartirse) ---

def _extract_first_json_object(text: str) -> str:
    start = text.find("{")
    if start == -1:
        raise ValueError("no se encontró ningún objeto JSON en la respuesta del modelo")

    depth = 0
    in_string = False
    escape_next = False
    for i in range(start, len(text)):
        char = text[i]
        if in_string:
            if escape_next:
                escape_next = False
            elif char == "\\":
                escape_next = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]

    raise ValueError("objeto JSON sin cerrar en la respuesta del modelo")


def _parse_json_content(content: str | None) -> dict:
    if not content:
        raise ValueError("respuesta vacía del modelo")
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[len("json"):]
    json_str = _extract_first_json_object(text.strip())
    return json.loads(json_str)


def _assistant_turn(resp: Completion) -> dict:
    """Reconstruye el mensaje 'assistant' con tool_calls para el historial
    (duplicado de `react_agent._assistant_turn`: Worker A no usa
    `ReActAgent`, monta su propio mini-turno de 1 tool call a mano)."""
    return {
        "role": "assistant",
        "content": resp.content or "",
        "tool_calls": [
            {
                "id": c["id"],
                "type": "function",
                "function": {"name": c["name"], "arguments": c["arguments"]},
            }
            for c in resp.tool_calls
        ],
    }


def _build_evidence(messages: list[dict]) -> list[str]:
    evidence = []
    for m in messages:
        if m.get("role") == "tool":
            name = m.get("name", "?")
            content = (m.get("content") or "").strip().replace("\n", " ")[:300]
            evidence.append(f"[{name}] {content}")
    return evidence


def _count_tool_calls(messages: list[dict]) -> int:
    return sum(1 for m in messages if m.get("role") == "tool")


def _finalize(delta: dict) -> dict:
    """Mismo principio que `rca_agent._finalize`: cierra de verdad el
    `Literal` de `state.SolutionStatus` en runtime."""
    status = delta["solution_status"]
    if status not in SOLUTION_STATUSES:
        raise AssertionError(
            f"solution_status inválido: {status!r} no está en SOLUTION_STATUSES "
            f"({sorted(SOLUTION_STATUSES)}) — bug en solution_agent.py, no en la "
            "respuesta del modelo."
        )
    return delta


# --- Worker A: verificación documental --------------------------------------

def _resolve_cited_source(state: IncidentState) -> tuple[str, str, str]:
    """Elige QUÉ fuente citada verificar. Decisión de implementación (no
    especificada al detalle en la spec): si el RCA citó tanto runbooks como
    docs técnicos, se prioriza el primer runbook (es un procedimiento de
    remediación por definición; un doc técnico solo describe comportamiento).
    Si el RCA cita varias fuentes del mismo tipo, se usa la primera — no se
    concatenan todas. Si en la práctica el RCA cita múltiples fuentes a
    menudo, esto es candidato a revisar."""
    runbook_ids = state.get("rca_runbook_ids") or []
    doc_ids = state.get("rca_technical_doc_ids") or []
    if runbook_ids:
        source_id = runbook_ids[0]
        return "runbook", source_id, rag.get_runbook_by_id(source_id)
    if doc_ids:
        source_id = doc_ids[0]
        return "technical_doc", source_id, rag.get_technical_doc_by_id(source_id)
    # No debería llegar aquí nunca: `_route` ya comprobó que al menos una de
    # las dos listas no está vacía antes de despachar a Worker A.
    raise AssertionError(
        "_worker_a invocado sin fuente citada en el estado — bug en _route/solution_node."
    )


def _build_worker_a_query(state: IncidentState, source_kind: str, source_id: str, content: str) -> str:
    payload = {
        "incident_id": state.get("incident_id", ""),
        "root_cause": state.get("root_cause", ""),
        "rca_partial_findings": state.get("rca_partial_findings", ""),
        "category": state.get("category", ""),
        "system": state.get("system", ""),
        "business_process": state.get("business_process", ""),
    }
    kind_label = "runbook" if source_kind == "runbook" else "documento técnico"
    return (
        "Causa raíz confirmada por el RCA:\n"
        + json.dumps(payload, ensure_ascii=False)
        + f"\n\nFuente citada por el RCA ({kind_label}, id={source_id}):\n{content}"
    )


def _worker_a(state: IncidentState, complete_fn: CompleteFn) -> dict:
    source_kind, source_id, content = _resolve_cited_source(state)
    messages = [
        {"role": "system", "content": _WORKER_A_SYSTEM_PROMPT},
        {"role": "user", "content": _build_worker_a_query(state, source_kind, source_id, content)},
    ]
    evidence = [f"[{source_kind}] {source_id}"]

    resp = complete_fn(_PROFILE_A, messages, tools=WORKER_A_TOOL_SCHEMAS)
    if resp.tool_calls:
        # Spec: como mucho 1 tool call de verificación. Si el modelo pidiera
        # varias en la misma respuesta, solo se ejecuta la primera.
        call = resp.tool_calls[0]
        observation = run_tool(call["name"], call["arguments"])
        evidence.append(f"[{call['name']}] {observation.strip()[:300]}")
        messages.append(_assistant_turn(resp))
        messages.append({
            "role": "tool",
            "tool_call_id": call["id"],
            "name": call["name"],
            "content": observation,
        })
        # Segunda llamada SIN tools: fuerza la respuesta final — ya se
        # agotó la única tool call que permite el spec para Worker A.
        resp = complete_fn(_PROFILE_A, messages, tools=None)

    try:
        data = _parse_json_content(resp.content)
        model_status = str(data.get("solution_status", "")).strip()
        proposed_solution = str(data.get("proposed_solution", "") or "")
        action_plan = list(data.get("action_plan") or [])
        confidence = float(data.get("solution_confidence", 0) or 0)
    except Exception as exc:  # noqa: BLE001 - respuesta final no parseable
        return {
            "proposed_solution": "",
            "action_plan": [],
            "solution_status": "cited_source_mismatch",
            "solution_confidence": 0.0,
            "solution_source": "cited_document",
            "solution_evidence": evidence,
            "needs_human_review": True,
            "trace": [
                f"solution (worker A): respuesta final no parseable ({exc}) "
                "-> cited_source_mismatch"
            ],
        }

    solution_status = "completed" if model_status == "completed" else "cited_source_mismatch"
    if solution_status != "completed":
        proposed_solution = proposed_solution or "El documento citado no aplica a esta causa raíz."
        action_plan = []
        confidence = 0.0

    return {
        "proposed_solution": proposed_solution,
        "action_plan": action_plan,
        "solution_status": solution_status,
        "solution_confidence": confidence,
        "solution_source": "cited_document",
        "solution_evidence": evidence,
        "needs_human_review": solution_status != "completed",
        "trace": [f"solution (worker A): {solution_status} sobre {source_kind} {source_id}"],
    }


# --- Worker B: investigación de código (agente ReAct real) ------------------

def _build_worker_b_query(state: IncidentState) -> str:
    payload = {
        "incident_id": state.get("incident_id", ""),
        "title": state.get("title", ""),
        "description": state.get("description", ""),
        "root_cause": state.get("root_cause", ""),
        "rca_partial_findings": state.get("rca_partial_findings", ""),
        "category": state.get("category", ""),
        "system": state.get("system", ""),
        "business_process": state.get("business_process", ""),
        "affected_objects": state.get("affected_objects") or [],
    }
    return "Propón una solución para la causa raíz de esta incidencia:\n" + json.dumps(
        payload, ensure_ascii=False
    )


def _worker_b(state: IncidentState, complete_fn: CompleteFn, limits: AgentLimits) -> dict:
    agent = ReActAgent(
        profile=_PROFILE_B,
        tools_schemas=WORKER_B_TOOL_SCHEMAS,
        system_prompt=_WORKER_B_SYSTEM_PROMPT,
        limits=limits,
        complete_fn=complete_fn,
        max_calls_per_tool=MAX_CALLS_PER_TOOL,
    )
    result = agent.run(_build_worker_b_query(state))

    evidence = _build_evidence(result.messages)
    tool_call_count = _count_tool_calls(result.messages)

    if result.stop_reason in ("max_iterations", "token_budget"):
        return {
            "proposed_solution": "",
            "action_plan": [],
            "solution_status": result.stop_reason,
            "solution_confidence": 0.0,
            "solution_source": "code_investigation",
            "solution_evidence": evidence,
            "needs_human_review": True,
            "trace": [
                f"solution (worker B): {result.stop_reason} tras {result.iterations} "
                f"iteraciones ({tool_call_count} tool calls)"
            ],
        }

    try:
        data = _parse_json_content(result.answer)
        model_status = str(data.get("solution_status", "")).strip()
        proposed_solution = str(data.get("proposed_solution", "") or "")
        action_plan = list(data.get("action_plan") or [])
        confidence = float(data.get("solution_confidence", 0) or 0)
    except Exception as exc:  # noqa: BLE001 - respuesta final no parseable
        return {
            "proposed_solution": "",
            "action_plan": [],
            "solution_status": "insufficient_evidence",
            "solution_confidence": 0.0,
            "solution_source": "code_investigation",
            "solution_evidence": evidence,
            "needs_human_review": True,
            "trace": [
                f"solution (worker B): respuesta final no parseable ({exc}) "
                "-> insufficient_evidence"
            ],
        }

    solution_status = "completed" if model_status == "completed" else "insufficient_evidence"
    if solution_status != "completed":
        proposed_solution, action_plan, confidence = "", [], 0.0

    return {
        "proposed_solution": proposed_solution,
        "action_plan": action_plan,
        "solution_status": solution_status,
        "solution_confidence": confidence,
        "solution_source": "code_investigation",
        "solution_evidence": evidence,
        "needs_human_review": solution_status != "completed",
        "trace": [
            f"solution (worker B): {solution_status} tras {result.iterations} "
            f"iteraciones ({tool_call_count} tool calls)"
        ],
    }


# --- Nodo LangGraph -----------------------------------------------------------

@traced("solution_node")
def solution_node(
    state: IncidentState,
    *,
    complete_fn: CompleteFn = complete,
    limits: AgentLimits | None = None,
) -> dict:
    """Nodo LangGraph de Solution. Recibe el `IncidentState` con RCA ya
    cerrado (`rca_status == "completed"`), enruta por código a Worker A o
    Worker B (`_route`), y devuelve el delta con la solución propuesta o el
    motivo de no haberla encontrado (`solution_status`, ver spec).

    `limits` solo aplica a Worker B (agente ReAct); Worker A no usa
    `AgentLimits` (como mucho 2 llamadas al modelo, ver `_worker_a`). Si no
    se pasa explícito, se resuelve por `state["priority"]`:
    `SOLUTION_LIMITS_ELEVATED` para P1/P2, `DEFAULT_LIMITS` para el resto —
    ver la nota junto a `SOLUTION_LIMITS_ELEVATED` arriba.
    """
    route = _route(state)
    worker_label = "cited_document" if route == "worker_a" else "code_investigation"

    if limits is None:
        limits = SOLUTION_LIMITS_ELEVATED if state.get("priority") in ("P1", "P2") else DEFAULT_LIMITS

    try:
        if route == "worker_a":
            delta = _worker_a(state, complete_fn)
        else:
            delta = _worker_b(state, complete_fn, limits)
    except Exception as exc:  # noqa: BLE001 - nunca revienta el grafo
        return _finalize({
            "proposed_solution": "",
            "action_plan": [],
            "solution_status": "model_error",
            "solution_confidence": 0.0,
            "solution_source": worker_label,
            "solution_evidence": [],
            "needs_human_review": True,
            "trace": [f"solution: fallo total del modelo ({exc}) -> model_error"],
        })

    return _finalize(delta)
