"""
RCA Agent — nodo LangGraph (S3).

Sigue `docs/specs/spec-rca-agent.md` al pie de la letra: es un AGENTE ReAct
(no un workflow) montado sobre `react_agent.py` de Fase 1 — el bucle decide
él solo, iteración a iteración, si tiene evidencia suficiente o necesita
escalar de RAG de conocimiento a lectura de código real. No hay un
`if/else` que decida el orden de las 5 tools.

`rca_node` NO confía a ciegas en la autodeclaración `rca_status: "completed"`
del modelo: aplica dos gates de verificación (spec, sección "Condición de
parada") antes de aceptarla — si no los pasa, degrada a
`insufficient_evidence`.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Callable

from ..config import AgentLimits, DEFAULT_LIMITS
from ..models import Completion, complete
from ..observability import traced
from ..state import RCA_STATUSES, IncidentState
from ..tools import TOOL_SCHEMAS
from .react_agent import ReActAgent

CompleteFn = Callable[..., Completion]

_PROFILE = "smart"

_PROMPT_PATH = Path(__file__).resolve().parents[3] / "docs" / "specs" / "rca-agent-prompt.md"
_SYSTEM_PROMPT = _PROMPT_PATH.read_text(encoding="utf-8")

_RCA_TOOL_NAMES = {
    "query_incident_history",
    "search_technical_docs",
    "search_runbooks",
    "search_codebase",
    "read_codebase_repo",
}
RCA_TOOL_SCHEMAS = [s for s in TOOL_SCHEMAS if s["function"]["name"] in _RCA_TOOL_NAMES]

# Gates de verificación (spec-rca-agent.md, "Condición de parada"). El
# umbral exacto de tool calls no lo cierra rca-decisiones-s3.md — es una
# decisión de implementación de este spec, documentada y ajustable.
MIN_TOOL_CALLS_FOR_COMPLETED = 2
CONFIDENCE_THRESHOLD = 80

# Tope duro por tool (ver react_agent.ReActAgent.max_calls_per_tool): 1
# llamada inicial + como mucho 1 de refuerzo. Verificado por código, no por
# criterio del modelo — visto en producción que el modelo, tras encontrar
# evidencia directa suficiente (un comentario de bug explícito en el código
# real), seguía "verificando" con más llamadas a la misma tool en vez de
# concluir, hasta agotar el presupuesto de tokens.
MAX_CALLS_PER_TOOL = 2

# token_budget elevado SOLO para P1. Medido con llamadas reales al modelo
# (no estimado): una investigación con bug directo en código cuesta ~29.6k
# tokens totales, una sin match exacto que fuerza patrón multi-fuente ~42.6k
# — ambas caben de sobra en DEFAULT_LIMITS.token_budget (60k), que por eso
# se mantiene para P2/P3/P4. P1 son las incidencias más críticas: si una
# investigación P1 necesita más margen para llegar a una conclusión real en
# vez de cortarse en insufficient_evidence, ese gasto extra está justificado;
# para el resto de prioridades no lo está (correrán muchas al día).
RCA_LIMITS_P1 = AgentLimits(max_iterations=12, token_budget=150_000)


def _build_query(state: IncidentState) -> str:
    """Contexto del ticket ya clasificado/priorizado, como pregunta inicial
    del ReActAgent (privacidad: sin reporter_email/contact_name, igual que
    hace intake_agent con el LLM)."""
    payload = {
        "incident_id": state.get("incident_id", ""),
        "title": state.get("title", ""),
        "description": state.get("description", ""),
        "error_messages": state.get("error_messages") or [],
        "category": state.get("category", ""),
        "system": state.get("system", ""),
        "business_process": state.get("business_process", ""),
        "affected_objects": state.get("affected_objects") or [],
        "priority": state.get("priority", ""),
        "impact_level": state.get("impact_level", ""),
        "urgency_level": state.get("urgency_level", ""),
    }
    return "Investiga la causa raíz de esta incidencia:\n" + json.dumps(payload, ensure_ascii=False)


def _extract_first_json_object(text: str) -> str:
    """Encuentra el primer objeto `{...}` balanceado dentro de `text`.

    Duplicado deliberado de la misma función en `intake_agent.py` /
    `priority_agent.py` (mismo problema: modelos que devuelven JSON válido
    seguido de texto explicativo) — mismo patrón ya establecido en el
    proyecto, no una abstracción nueva.
    """
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


def _count_tool_calls(messages: list[dict]) -> int:
    """Requisito estructural duro: cuenta observaciones de tool registradas
    en el transcript (una por cada tool call ejecutada)."""
    return sum(1 for m in messages if m.get("role") == "tool")


def _build_evidence(messages: list[dict]) -> list[str]:
    """Traza auditable: qué tool se llamó y qué devolvió (truncado)."""
    evidence = []
    for m in messages:
        if m.get("role") == "tool":
            name = m.get("name", "?")
            content = (m.get("content") or "").strip().replace("\n", " ")[:300]
            evidence.append(f"[{name}] {content}")
    return evidence


# Patrones de extracción de IDs por tool de RAG, sobre el texto CRUDO (sin
# truncar) que devuelve cada una (ver `rag.py`). 3 de las 4 tools comparten
# el mismo formato de línea `"{i}. [{id}] distancia=..."`; `search_runbooks`
# es la excepción porque agrupa por runbook completo, no por línea suelta:
# `Runbook: "{title}" ({runbook_id}, categoria=...)`.
_LINE_BRACKET_ID = re.compile(r"^\d+\.\s*\[([^\]]+)\]", re.MULTILINE)
_RUNBOOK_ID = re.compile(r"\(([^,()]+),\s*categoria=")

_SOURCE_ID_PATTERNS: dict[str, re.Pattern[str]] = {
    "query_incident_history": _LINE_BRACKET_ID,
    "search_technical_docs": _LINE_BRACKET_ID,
    "search_codebase": _LINE_BRACKET_ID,
    "search_runbooks": _RUNBOOK_ID,
}

_SOURCE_STATE_FIELD_BY_TOOL: dict[str, str] = {
    "query_incident_history": "rca_incident_source_ids",
    "search_technical_docs": "rca_technical_doc_ids",
    "search_codebase": "rca_codebase_chunk_ids",
    "search_runbooks": "rca_runbook_ids",
}


def _extract_source_ids(messages: list[dict]) -> dict[str, list[str]]:
    """Extrae por código los IDs de fuentes (runbook_id, doc_id, incident_id,
    chunk_id) citados en las observaciones de las 4 tools de RAG.

    Deliberadamente NO se apoya en `similar_incidents` (autodeclarado por el
    modelo en el JSON final) ni en `rca_evidence` (que trunca a 300 chars y
    podría cortar el ID). Lee `messages` -- el transcript sin truncar -- y
    aplica regex sobre el formato fijo que ya emite `rag.py`. Si una tool
    devuelve "sin resultados" o un error, el texto no matchea el patrón y
    simplemente no aporta IDs, sin necesidad de filtrarlo aparte.

    Es el equivalente, para trazabilidad de fuentes, de lo que los gates de
    `rca_status` hacen para el veredicto: verificar por código en vez de
    confiar en que el modelo lo declare bien.
    """
    found: dict[str, list[str]] = {field: [] for field in _SOURCE_STATE_FIELD_BY_TOOL.values()}
    for m in messages:
        if m.get("role") != "tool":
            continue
        pattern = _SOURCE_ID_PATTERNS.get(m.get("name", ""))
        if pattern is None:
            continue
        field = _SOURCE_STATE_FIELD_BY_TOOL[m["name"]]
        for match in pattern.finditer(m.get("content") or ""):
            source_id = match.group(1).strip()
            if source_id and source_id not in found[field]:
                found[field].append(source_id)
    return found


def _last_assistant_text(messages: list[dict]) -> str:
    for m in reversed(messages):
        if m.get("role") == "assistant" and m.get("content"):
            return m["content"]
    return ""


_WRAPUP_PROMPT = (
    "Se agotó tu presupuesto de investigación (límite de recursos, no de "
    "evidencia). No puedes pedir más herramientas. Con lo que ya "
    "investigaste hasta ahora, responde en texto plano (NO JSON, NO "
    "declares 'rca_status: completed'):\n"
    "1. Qué evidencia real encontraste (fuentes concretas, no generalidades).\n"
    "2. Si tienes una hipótesis de causa raíz o de posible solución, indícala "
    "explícitamente dejando CLARO que es una hipótesis SIN CONFIRMAR — no "
    "actúes como si hubieras terminado la investigación.\n"
    "3. Qué haría falta investigar para confirmarla.\n"
    "Sé conciso (máximo un párrafo corto por punto)."
)


def _forced_wrapup(messages: list[dict], complete_fn: CompleteFn) -> str:
    """Llamada extra, acotada (sin tools) y fuera del bucle ReAct, solo para
    los caminos `max_iterations`/`token_budget`.

    Por qué hace falta: `react_agent.py` corta en seco en esos dos casos
    (`answer=None`, sin darle al modelo ninguna oportunidad de cerrar su
    razonamiento — ver `ReActAgent.run`). Sin esto, `rca_partial_findings`
    quedaba en `_last_assistant_text`: lo último que el modelo dijera en su
    turno anterior, que puede ser un fragmento de pensamiento a medias o
    estar vacío, según en qué punto del bucle se cortara — nada garantizaba
    que fuera un resumen útil para quien hace la revisión humana.

    No se reabre ninguna investigación (no se pasan `tools`, es una única
    llamada) y no se acepta como conclusión: el prompt exige explícitamente
    marcar cualquier hipótesis como SIN CONFIRMAR. `rca_status` sigue siendo
    `max_iterations`/`token_budget`, `root_cause` sigue vacío — esto solo
    mejora la calidad del texto que ya se guardaba, no cambia el contrato."""
    wrapup_messages = messages + [{"role": "user", "content": _WRAPUP_PROMPT}]
    resp = complete_fn(_PROFILE, wrapup_messages, tools=None)
    return (resp.content or "").strip()


def _finalize(delta: dict) -> dict:
    """Cierra de verdad el `Literal` de `state.RcaStatus`: si algún camino de
    código de este fichero llegase a construir un `rca_status` fuera de
    `RCA_STATUSES` (typo, valor nuevo olvidado de registrar...), esto revienta
    aquí con un mensaje claro en vez de colar un 6º valor no documentado en
    silencio."""
    status = delta["rca_status"]
    if status not in RCA_STATUSES:
        raise AssertionError(
            f"rca_status inválido: {status!r} no está en RCA_STATUSES "
            f"({sorted(RCA_STATUSES)}) — bug en rca_agent.py, no en la respuesta del modelo."
        )
    return delta


@traced("rca_node")
def rca_node(
    state: IncidentState,
    *,
    complete_fn: CompleteFn = complete,
    limits: AgentLimits | None = None,
) -> dict:
    """Nodo LangGraph de RCA. Recibe el IncidentState (Intake + Priority ya
    aplicados), devuelve el delta con la causa raíz o el motivo de no
    haberla encontrado (`rca_status`, ver spec).

    `limits` es inyectable (igual que `complete_fn`) para que los tests
    puedan forzar `max_iterations`/`token_budget` exactos sin depender de la
    prioridad del ticket. Si no se pasa explícitamente (el caso real en
    `graph.py`), se elige según `state["priority"]`: `RCA_LIMITS_P1` para
    incidencias P1, `DEFAULT_LIMITS` (8 iteraciones / 60k tokens) para el
    resto — ver la nota junto a `RCA_LIMITS_P1` arriba."""
    if limits is None:
        limits = RCA_LIMITS_P1 if state.get("priority") == "P1" else DEFAULT_LIMITS

    agent = ReActAgent(
        profile=_PROFILE,
        tools_schemas=RCA_TOOL_SCHEMAS,
        system_prompt=_SYSTEM_PROMPT,
        limits=limits,
        complete_fn=complete_fn,
        max_calls_per_tool=MAX_CALLS_PER_TOOL,
    )

    try:
        result = agent.run(_build_query(state))
    except Exception as exc:  # noqa: BLE001 - nunca revienta el grafo
        return _finalize({
            "root_cause": "",
            "rca_confidence": 0.0,
            "rca_status": "model_error",
            "rca_corroboration": "",
            "rca_evidence": [],
            "rca_partial_findings": f"Fallo total del modelo durante la investigación: {exc}",
            "rca_iterations_used": 0,
            "similar_incidents": [],
            "rca_incident_source_ids": [],
            "rca_technical_doc_ids": [],
            "rca_runbook_ids": [],
            "rca_codebase_chunk_ids": [],
            "needs_human_review": True,
            "trace": [f"rca: fallo total del modelo ({exc}) -> model_error"],
        })

    evidence = _build_evidence(result.messages)
    tool_call_count = _count_tool_calls(result.messages)
    source_ids = _extract_source_ids(result.messages)

    # --- Caminos de parada del harness (react_agent.py), no del modelo ---
    if result.stop_reason in ("max_iterations", "token_budget"):
        try:
            wrapup_summary = _forced_wrapup(result.messages, complete_fn)
        except Exception:  # noqa: BLE001 - nunca revienta el grafo por esto
            wrapup_summary = ""
        return _finalize({
            "root_cause": "",
            "rca_confidence": 0.0,
            "rca_status": result.stop_reason,
            "rca_corroboration": "",
            "rca_evidence": evidence,
            "rca_partial_findings": (
                wrapup_summary
                or _last_assistant_text(result.messages)
                or "Sin conclusión: se agotó el límite antes de una respuesta final."
            ),
            "rca_iterations_used": result.iterations,
            "similar_incidents": [],
            **source_ids,
            "needs_human_review": True,
            "trace": [
                f"rca: {result.stop_reason} tras {result.iterations} iteraciones "
                f"({tool_call_count} tool calls)"
            ],
        })

    # --- final_answer: parsear el JSON que pide rca-agent-prompt.md ---
    try:
        data = _parse_json_content(result.answer)
        model_status = str(data.get("rca_status", "")).strip()
        root_cause = str(data.get("root_cause", "") or "")
        confidence = float(data.get("rca_confidence", 0) or 0)
        corroboration = data.get("rca_corroboration") or ""
        partial_findings = str(data.get("rca_partial_findings", "") or "")
        similar_incidents = list(data.get("similar_incidents") or [])
    except Exception as exc:  # noqa: BLE001 - respuesta final no parseable
        return _finalize({
            "root_cause": "",
            "rca_confidence": 0.0,
            "rca_status": "insufficient_evidence",
            "rca_corroboration": "",
            "rca_evidence": evidence,
            "rca_partial_findings": f"Respuesta final no parseable como JSON ({exc}): {result.answer!r}",
            "rca_iterations_used": result.iterations,
            "similar_incidents": [],
            **source_ids,
            "needs_human_review": True,
            "trace": [
                f"rca: respuesta final no parseable -> insufficient_evidence "
                f"({tool_call_count} tool calls)"
            ],
        })

    # --- Gates de verificación (spec, "Condición de parada") ------------
    reasoning_notes: list[str] = []
    rca_status = "completed" if model_status == "completed" else "insufficient_evidence"

    if rca_status == "completed" and tool_call_count < MIN_TOOL_CALLS_FOR_COMPLETED:
        rca_status = "insufficient_evidence"
        reasoning_notes.append(
            f"degradado: solo {tool_call_count} tool call(s) "
            f"(< {MIN_TOOL_CALLS_FOR_COMPLETED} requeridas)"
        )
    if rca_status == "completed" and confidence < CONFIDENCE_THRESHOLD:
        rca_status = "insufficient_evidence"
        reasoning_notes.append(
            f"degradado: confianza {confidence} < umbral {CONFIDENCE_THRESHOLD}"
        )

    if rca_status == "completed":
        final_root_cause, final_confidence = root_cause, confidence
        final_corroboration, final_similar = corroboration, similar_incidents
    else:
        # No se acepta la autodeclaración -> se limpian los campos que solo
        # tienen sentido con una causa raíz confirmada.
        final_root_cause, final_confidence = "", 0.0
        final_corroboration, final_similar = "", []

    trace_msg = f"rca: {rca_status} tras {result.iterations} iteraciones ({tool_call_count} tool calls)"
    if reasoning_notes:
        trace_msg += " | " + " | ".join(reasoning_notes)

    return _finalize({
        "root_cause": final_root_cause,
        "rca_confidence": final_confidence,
        "rca_status": rca_status,
        "rca_corroboration": final_corroboration,
        "rca_evidence": evidence,
        "rca_partial_findings": partial_findings or "(sin resumen del modelo)",
        "rca_iterations_used": result.iterations,
        "similar_incidents": final_similar,
        **source_ids,
        "needs_human_review": rca_status != "completed",
        "trace": [trace_msg],
    })


def route_after_rca(state: IncidentState) -> str:
    """Arista condicional del grafo (spec, "Señal de enrutado" — cerrado en
    S4 al conectar Solution).

    Antes de S4 no existía ningún consumidor de `rca_status` distinto entre
    valores, así que `graph.py` usaba una arista fija `rca -> solution`. Eso
    dejaba pasar tickets con `rca_status != "completed"` (y por tanto
    `root_cause == ""`) directos a Solution: `rca_runbook_ids`/
    `rca_technical_doc_ids` pueden no estar vacíos incluso cuando RCA no
    concluye (se extraen de CUALQUIER resultado de búsqueda visto, no solo
    de lo citado en una conclusión — ver `_extract_source_ids`), así que el
    router de Solution (`solution_agent._route`) se dejaba engañar y
    despachaba a Worker A con una causa raíz vacía, gastando una llamada al
    modelo sin poder producir nada útil. Mismo patrón que
    `priority_agent.route_after_priority`: mira `needs_human_review`, que
    RCA ya pone en `true` en los 4 casos que no son `completed`."""
    if state.get("needs_human_review"):
        return "human_review"
    return "solution"
