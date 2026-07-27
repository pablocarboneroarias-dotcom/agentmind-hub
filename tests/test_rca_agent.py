"""
Tests del RCA Agent (S3) — spec-rca-agent.md, "Entregable esperado": 4
incidencias sintéticas, una por cada valor de `rca_status`.

No tocan Postgres/Ollama: `run_tool` se monkeypatchea (mismo mecanismo que
ya usa `test_react_agent.py` para `complete`) así que las tool calls que
pide el modelo falso se resuelven con observaciones de mentira, rápido y
determinista — igual que exige la convención de tests del proyecto.
"""

from __future__ import annotations

import json

import agentmind.agents.react_agent as ra
from agentmind.agents.rca_agent import rca_node
from agentmind.config import AgentLimits
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
        "error_messages": ["FIELD_CUSTOM_VALIDATION_EXCEPTION: Revenue recognition date cannot be in the past"],
        "category": "APEX",
        "system": "SALES_CLOUD",
        "business_process": "SALES_FLOW",
        "affected_objects": ["Opportunity"],
        "priority": "P2",
        "impact_level": "alto",
        "urgency_level": "media",
    }
    state.update(overrides)
    return state


def _print_full_state(label: str, state: dict, delta: dict) -> None:
    full_state = {**state, **delta}
    print(f"\n{'=' * 70}\n{label} — IncidentState completo tras rca_node\n{'=' * 70}")
    print(json.dumps(full_state, ensure_ascii=False, indent=2))


def _fake_run_tool_ok(name: str, arguments: str) -> str:
    """Doble de `run_tool`: observación de mentira, sin tocar Postgres/Ollama."""
    return f"[fake observation for {name}] arguments={arguments}"


# --- Caso 1: completed --------------------------------------------------------

def test_rca_completed(monkeypatch):
    monkeypatch.setattr(ra, "run_tool", _fake_run_tool_ok)

    calls = [
        _tool_call_completion("query_incident_history", {"query": "OpportunityTrigger fecha cierre"}, call_id="1"),
        _tool_call_completion("read_codebase_repo", {"path": "src/triggers/OpportunityTrigger.cls"}, call_id="2"),
        _final_answer_completion({
            "rca_status": "completed",
            "root_cause": "El trigger usa Date.today() en vez de opp.CloseDate para validar Revenue_Recognition_Date__c.",
            "rca_confidence": 92,
            "rca_corroboration": "multi_source",
            "rca_partial_findings": "Histórico + lectura del código confirman la misma causa.",
            "similar_incidents": ["INC-2024-0017"],
        }),
    ]
    it = iter(calls)

    def fake_complete(profile, messages, tools=None, **kwargs):
        return next(it)

    state = _base_state()
    delta = rca_node(state, complete_fn=fake_complete)
    _print_full_state("Caso 1: completed", state, delta)

    assert delta["rca_status"] == "completed"
    assert "Date.today()" in delta["root_cause"]
    assert delta["rca_confidence"] == 92
    assert delta["rca_corroboration"] == "multi_source"
    assert delta["similar_incidents"] == ["INC-2024-0017"]
    assert delta["needs_human_review"] is False
    assert delta["rca_iterations_used"] == 3
    assert len(delta["rca_evidence"]) == 2


# --- Caso 2: max_iterations ----------------------------------------------------

def test_rca_max_iterations(monkeypatch):
    monkeypatch.setattr(ra, "run_tool", _fake_run_tool_ok)

    def fake_complete(profile, messages, tools=None, **kwargs):
        # Siempre pide otra tool -> nunca da respuesta final.
        return _tool_call_completion("query_incident_history", {"query": "algo"}, call_id="x")

    state = _base_state()
    delta = rca_node(state, complete_fn=fake_complete, limits=AgentLimits(max_iterations=3, token_budget=100_000))
    _print_full_state("Caso 2: max_iterations", state, delta)

    assert delta["rca_status"] == "max_iterations"
    assert delta["root_cause"] == ""
    assert delta["rca_confidence"] == 0.0
    assert delta["needs_human_review"] is True
    assert delta["rca_iterations_used"] == 3
    assert len(delta["rca_evidence"]) == 3


# --- Caso 3: token_budget -------------------------------------------------------

def test_rca_token_budget(monkeypatch):
    monkeypatch.setattr(ra, "run_tool", _fake_run_tool_ok)

    def fake_complete(profile, messages, tools=None, **kwargs):
        return _tool_call_completion("search_technical_docs", {"query": "algo"}, call_id="x")

    state = _base_state()
    # Presupuesto minúsculo: debe abortar por tokens, no por iteraciones.
    delta = rca_node(state, complete_fn=fake_complete, limits=AgentLimits(max_iterations=50, token_budget=25))
    _print_full_state("Caso 3: token_budget", state, delta)

    assert delta["rca_status"] == "token_budget"
    assert delta["root_cause"] == ""
    assert delta["needs_human_review"] is True


# --- Caso 4: insufficient_evidence ----------------------------------------------

def test_rca_insufficient_evidence(monkeypatch):
    monkeypatch.setattr(ra, "run_tool", _fake_run_tool_ok)

    calls = [
        _tool_call_completion("query_incident_history", {"query": "fallo de facturación SAP IVA"}, call_id="1"),
        _tool_call_completion("search_technical_docs", {"query": "IVA factura electrónica"}, call_id="2"),
        _tool_call_completion("search_runbooks", {"query": "facturación IVA"}, call_id="3"),
        _final_answer_completion({
            "rca_status": "insufficient_evidence",
            "root_cause": "",
            "rca_confidence": 0,
            "rca_corroboration": None,
            "rca_partial_findings": "Consulté histórico, docs técnicas y runbooks: nada relacionado con IVA/facturación electrónica en el corpus indexado.",
            "similar_incidents": [],
        }),
    ]
    it = iter(calls)

    def fake_complete(profile, messages, tools=None, **kwargs):
        return next(it)

    state = _base_state(
        title="Fallo de facturación en SAP por IVA incorrecto",
        description="Las facturas electrónicas salen con el IVA mal calculado tras la sincronización con SAP.",
        category="INTEG",
        system="INTEGRATION",
        business_process="SAP_INTEGRATION",
    )
    delta = rca_node(state, complete_fn=fake_complete)
    _print_full_state("Caso 4: insufficient_evidence", state, delta)

    assert delta["rca_status"] == "insufficient_evidence"
    assert delta["root_cause"] == ""
    assert delta["rca_confidence"] == 0.0
    assert delta["rca_corroboration"] == ""
    assert delta["needs_human_review"] is True
    assert "IVA" in delta["rca_partial_findings"]
    assert len(delta["rca_evidence"]) == 3


# --- Bonus: gate estructural degrada 'completed' con <2 tool calls -------------

def test_rca_degrada_completed_con_pocas_tool_calls(monkeypatch):
    """No pedido explícitamente por el spec como uno de los 4 casos, pero sí
    como comportamiento del gate ("... o declara completed pero con <2 tool
    calls / confianza <80, para probar que el nodo degrada correctamente")."""
    monkeypatch.setattr(ra, "run_tool", _fake_run_tool_ok)

    calls = [
        _tool_call_completion("query_incident_history", {"query": "algo"}, call_id="1"),
        _final_answer_completion({
            "rca_status": "completed",
            "root_cause": "Una causa poco fundamentada.",
            "rca_confidence": 95,
            "rca_corroboration": "single_source",
            "rca_partial_findings": "Solo consulté una fuente.",
            "similar_incidents": [],
        }),
    ]
    it = iter(calls)

    def fake_complete(profile, messages, tools=None, **kwargs):
        return next(it)

    state = _base_state()
    delta = rca_node(state, complete_fn=fake_complete)
    _print_full_state("Bonus: degradado por <2 tool calls", state, delta)

    assert delta["rca_status"] == "insufficient_evidence"
    assert delta["root_cause"] == ""
    assert "degradado" in delta["trace"][0]
