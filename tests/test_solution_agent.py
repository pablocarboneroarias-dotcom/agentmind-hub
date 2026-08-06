"""
Tests del Solution Agent (S4) — spec-solution-agent.md, "Entregable esperado".

Mismo mecanismo que `test_rca_agent.py`: `run_tool`/`complete_fn` se
monkeypatchean, sin tocar Postgres/Ollama. Dos monkeypatches distintos según
qué componente ejecuta la tool:
  - Worker A llama a `run_tool` directamente desde `solution_agent.py` (no
    usa `ReActAgent`) -> se monkeypatchea `sa.run_tool`.
  - Worker B SÍ usa `ReActAgent` (como el RCA) -> se monkeypatchea
    `ra.run_tool` (react_agent.py), igual que hace `test_rca_agent.py`.
  - `_resolve_cited_source` (Worker A) llama a `rag.get_runbook_by_id` /
    `rag.get_technical_doc_by_id` -> se monkeypatchean en el módulo `rag`
    (mismo objeto que `sa.rag`, al ser `from .. import rag`).
"""

from __future__ import annotations

import json

import agentmind.agents.react_agent as ra
import agentmind.agents.solution_agent as sa
import agentmind.rag as rag
from agentmind.config import DEFAULT_LIMITS, AgentLimits
from agentmind.models import Completion


def _tool_call_completion(name: str, arguments: dict, *, call_id: str = "1") -> Completion:
    return Completion(
        content=None,
        tool_calls=[{"id": call_id, "name": name, "arguments": json.dumps(arguments)}],
        finish_reason="tool_calls",
        prompt_tokens=20,
        completion_tokens=10,
    )


def _final_answer_completion(payload: dict) -> Completion:
    return Completion(
        content=json.dumps(payload, ensure_ascii=False),
        tool_calls=[],
        finish_reason="stop",
        prompt_tokens=20,
        completion_tokens=15,
    )


def _base_state(**overrides) -> dict:
    state = {
        "incident_id": "INC-2024-0017",
        "title": "Trigger de Opportunity falla al cerrar Closed Won",
        "description": "El sistema devuelve FIELD_CUSTOM_VALIDATION_EXCEPTION al cerrar la oportunidad.",
        "category": "APEX",
        "system": "SALES_CLOUD",
        "business_process": "SALES_FLOW",
        "affected_objects": ["Opportunity"],
        "priority": "P2",
        "root_cause": "El trigger usa Date.today() en vez de opp.CloseDate.",
        "rca_partial_findings": "Histórico + código confirman la causa.",
        "rca_runbook_ids": [],
        "rca_technical_doc_ids": [],
        "rca_incident_source_ids": [],
        "rca_codebase_chunk_ids": [],
    }
    state.update(overrides)
    return state


def _print_full_state(label: str, state: dict, delta: dict) -> None:
    full_state = {**state, **delta}
    print(f"\n{'=' * 70}\n{label} — IncidentState completo tras solution_node\n{'=' * 70}")
    print(json.dumps(full_state, ensure_ascii=False, indent=2))


def _fake_run_tool_ok(name: str, arguments: str) -> str:
    return f"[fake observation for {name}] arguments={arguments}"


# --- Router: función de código pura, sin invocar ningún modelo -----------------

def test_route_worker_a_si_hay_runbook_citado():
    state = _base_state(rca_runbook_ids=["RB-014"])
    assert sa._route(state) == "worker_a"


def test_route_worker_a_si_hay_doc_tecnico_citado():
    state = _base_state(rca_technical_doc_ids=["TD-233"])
    assert sa._route(state) == "worker_a"


def test_route_worker_b_si_no_hay_fuente_citada():
    state = _base_state()
    assert sa._route(state) == "worker_b"


def test_route_ignora_incident_source_ids_como_disparador():
    """Deliberado (spec): un histórico parecido NO dispara Worker A."""
    state = _base_state(rca_incident_source_ids=["INC-2024-0980"])
    assert sa._route(state) == "worker_b"


# --- Worker A: completed --------------------------------------------------------

def test_worker_a_completed(monkeypatch):
    monkeypatch.setattr(rag, "get_runbook_by_id", lambda rid: f'Runbook: "Fix trigger" ({rid})\nPaso 1/1: usa opp.CloseDate.')

    def fake_complete(profile, messages, tools=None, **kwargs):
        assert profile == "fast"
        return _final_answer_completion({
            "solution_status": "completed",
            "proposed_solution": "Cambiar Date.today() por opp.CloseDate en el trigger.",
            "action_plan": ["Editar OpportunityTrigger.cls", "Desplegar a sandbox", "Ejecutar tests"],
            "solution_confidence": 90,
        })

    state = _base_state(rca_runbook_ids=["RB-014"])
    delta = sa.solution_node(state, complete_fn=fake_complete)
    _print_full_state("Worker A: completed", state, delta)

    assert delta["solution_status"] == "completed"
    assert "opp.CloseDate" in delta["proposed_solution"]
    assert len(delta["action_plan"]) == 3
    assert delta["solution_confidence"] == 90
    assert delta["solution_source"] == "cited_document"
    assert delta["needs_human_review"] is False
    assert delta["solution_evidence"] == ["[runbook] RB-014"]


# --- Worker A: cited_source_mismatch --------------------------------------------

def test_worker_a_cited_source_mismatch(monkeypatch):
    monkeypatch.setattr(
        rag, "get_technical_doc_by_id",
        lambda did: f"[{did}] tipo=trigger componente=OtroComponente\nDescribe un comportamiento no relacionado.",
    )

    def fake_complete(profile, messages, tools=None, **kwargs):
        return _final_answer_completion({
            "solution_status": "cited_source_mismatch",
            "proposed_solution": "El doc citado describe OtroComponente, no el trigger con el bug real.",
            "action_plan": [],
            "solution_confidence": 0,
        })

    state = _base_state(rca_technical_doc_ids=["TD-233"])
    delta = sa.solution_node(state, complete_fn=fake_complete)
    _print_full_state("Worker A: cited_source_mismatch", state, delta)

    assert delta["solution_status"] == "cited_source_mismatch"
    assert delta["action_plan"] == []
    assert delta["solution_confidence"] == 0.0
    assert delta["needs_human_review"] is True
    assert delta["solution_source"] == "cited_document"


# --- Worker A: como mucho 1 tool call de verificación ---------------------------

def test_worker_a_con_una_tool_call_de_verificacion(monkeypatch):
    monkeypatch.setattr(rag, "get_runbook_by_id", lambda rid: f"Runbook: \"X\" ({rid})\nPaso 1/1: revisa el campo custom.")
    monkeypatch.setattr(sa, "run_tool", _fake_run_tool_ok)

    def fake_complete(profile, messages, tools=None, **kwargs):
        if tools:  # primera llamada: puede pedir la tool de verificación
            return _tool_call_completion("read_codebase_repo", {"path": "src/triggers/OpportunityTrigger.cls"})
        # segunda llamada: sin tools, forzada a dar la respuesta final
        return _final_answer_completion({
            "solution_status": "completed",
            "proposed_solution": "Confirmado en código: falta la validación del campo custom.",
            "action_plan": ["Añadir validación"],
            "solution_confidence": 85,
        })

    state = _base_state(rca_runbook_ids=["RB-014"])
    delta = sa.solution_node(state, complete_fn=fake_complete)
    _print_full_state("Worker A: con 1 tool call de verificación", state, delta)

    assert delta["solution_status"] == "completed"
    assert delta["solution_confidence"] == 85
    # 1 entrada del doc citado + 1 de la tool call de verificación
    assert len(delta["solution_evidence"]) == 2
    assert delta["solution_evidence"][0] == "[runbook] RB-014"
    assert "read_codebase_repo" in delta["solution_evidence"][1]


# --- Worker B: completed --------------------------------------------------------

def test_worker_b_completed(monkeypatch):
    monkeypatch.setattr(ra, "run_tool", _fake_run_tool_ok)

    calls = [
        _tool_call_completion("search_codebase", {"query": "OpportunityTrigger fecha cierre"}, call_id="1"),
        _tool_call_completion("read_codebase_repo", {"path": "src/triggers/OpportunityTrigger.cls"}, call_id="2"),
        _final_answer_completion({
            "solution_status": "completed",
            "proposed_solution": "Sustituir Date.today() por opp.CloseDate en la validación.",
            "action_plan": ["Editar el trigger", "Desplegar", "Probar"],
            "solution_confidence": 88,
        }),
    ]
    it = iter(calls)

    def fake_complete(profile, messages, tools=None, **kwargs):
        assert profile == "smart"
        return next(it)

    state = _base_state()  # sin citas -> Worker B
    delta = sa.solution_node(state, complete_fn=fake_complete)
    _print_full_state("Worker B: completed", state, delta)

    assert delta["solution_status"] == "completed"
    assert "opp.CloseDate" in delta["proposed_solution"]
    assert delta["solution_confidence"] == 88
    assert delta["solution_source"] == "code_investigation"
    assert delta["needs_human_review"] is False
    assert len(delta["solution_evidence"]) == 2


# --- Worker B: insufficient_evidence --------------------------------------------

def test_worker_b_insufficient_evidence(monkeypatch):
    monkeypatch.setattr(ra, "run_tool", _fake_run_tool_ok)

    calls = [
        _tool_call_completion("search_codebase", {"query": "algo"}, call_id="1"),
        _final_answer_completion({
            "solution_status": "insufficient_evidence",
            "proposed_solution": "",
            "action_plan": [],
            "solution_confidence": 0,
        }),
    ]
    it = iter(calls)

    def fake_complete(profile, messages, tools=None, **kwargs):
        return next(it)

    state = _base_state()
    delta = sa.solution_node(state, complete_fn=fake_complete)
    _print_full_state("Worker B: insufficient_evidence", state, delta)

    assert delta["solution_status"] == "insufficient_evidence"
    assert delta["proposed_solution"] == ""
    assert delta["needs_human_review"] is True


# --- Worker B: max_iterations / token_budget ------------------------------------

def test_worker_b_max_iterations(monkeypatch):
    monkeypatch.setattr(ra, "run_tool", _fake_run_tool_ok)

    def fake_complete(profile, messages, tools=None, **kwargs):
        return _tool_call_completion("search_codebase", {"query": "algo"}, call_id="x")

    state = _base_state()
    delta = sa.solution_node(
        state, complete_fn=fake_complete,
        limits=AgentLimits(max_iterations=3, token_budget=100_000),
    )
    _print_full_state("Worker B: max_iterations", state, delta)

    assert delta["solution_status"] == "max_iterations"
    assert delta["proposed_solution"] == ""
    assert delta["needs_human_review"] is True


# --- P1/P2 reciben presupuesto elevado; P3/P4 el default (sin pasar `limits`) --

def test_p1_p2_reciben_mas_presupuesto_que_p3_p4_sin_pasar_limits(monkeypatch):
    monkeypatch.setattr(ra, "run_tool", _fake_run_tool_ok)

    def fake_complete_always_calls_tool(profile, messages, tools=None, **kwargs):
        return _tool_call_completion("search_codebase", {"query": "algo"}, call_id="x")

    for priority in ("P1", "P2"):
        state = _base_state(priority=priority)
        delta = sa.solution_node(state, complete_fn=fake_complete_always_calls_tool)
        assert delta["solution_status"] == "max_iterations"
        assert f"tras {sa.SOLUTION_LIMITS_ELEVATED.max_iterations} iteraciones" in delta["trace"][0]

    for priority in ("P3", "P4"):
        state = _base_state(priority=priority)
        delta = sa.solution_node(state, complete_fn=fake_complete_always_calls_tool)
        assert delta["solution_status"] == "max_iterations"
        assert f"tras {DEFAULT_LIMITS.max_iterations} iteraciones" in delta["trace"][0]

    assert sa.SOLUTION_LIMITS_ELEVATED.max_iterations != DEFAULT_LIMITS.max_iterations


# --- model_error: nunca revienta el grafo ---------------------------------------

def test_worker_a_model_error(monkeypatch):
    monkeypatch.setattr(rag, "get_runbook_by_id", lambda rid: "contenido")

    def fake_complete_raises(profile, messages, tools=None, **kwargs):
        raise RuntimeError("proveedor caído")

    state = _base_state(rca_runbook_ids=["RB-014"])
    delta = sa.solution_node(state, complete_fn=fake_complete_raises)
    _print_full_state("Worker A: model_error", state, delta)

    assert delta["solution_status"] == "model_error"
    assert delta["solution_source"] == "cited_document"
    assert delta["needs_human_review"] is True


def test_worker_b_model_error(monkeypatch):
    def fake_complete_raises(profile, messages, tools=None, **kwargs):
        raise RuntimeError("proveedor caído")

    state = _base_state()
    delta = sa.solution_node(state, complete_fn=fake_complete_raises)
    _print_full_state("Worker B: model_error", state, delta)

    assert delta["solution_status"] == "model_error"
    assert delta["solution_source"] == "code_investigation"
    assert delta["needs_human_review"] is True
