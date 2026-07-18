"""
Smoke test del ReAct agent (modificación: testear a medida que construyes).

No llamamos a ningún modelo real: sustituimos `complete` por un doble que
devuelve respuestas prefabricadas. Así el test es rápido, gratis y determinista,
y verifica lo que de verdad importa en la Semana 1: que los LÍMITES funcionan.
"""

from __future__ import annotations

import agentmind.agents.react_agent as ra
from agentmind.config import AgentLimits
from agentmind.models import Completion


def _fake_complete_always_calls_tool(profile, messages, tools=None, **kwargs):
    """Modelo falso que pide siempre una herramienta -> nunca termina solo.

    Sirve para comprobar que el tope de iteraciones corta el bucle.
    """
    return Completion(
        content=None,
        tool_calls=[{"id": "1", "name": "calculator", "arguments": '{"expression": "1+1"}'}],
        finish_reason="tool_calls",
        prompt_tokens=10,
        completion_tokens=5,
    )


def _fake_complete_final_answer(profile, messages, tools=None, **kwargs):
    """Modelo falso que responde directamente, sin herramientas."""
    return Completion(
        content="La respuesta es 42.",
        tool_calls=[],
        finish_reason="stop",
        prompt_tokens=10,
        completion_tokens=5,
    )


def test_stops_at_max_iterations(monkeypatch):
    monkeypatch.setattr(ra, "complete", _fake_complete_always_calls_tool)
    agent = ra.ReActAgent(limits=AgentLimits(max_iterations=3, token_budget=10_000))
    result = agent.run("bucle infinito de prueba")
    assert result.stop_reason == "max_iterations"
    assert result.iterations == 3


def test_returns_final_answer(monkeypatch):
    monkeypatch.setattr(ra, "complete", _fake_complete_final_answer)
    agent = ra.ReActAgent()
    result = agent.run("dame una respuesta")
    assert result.stop_reason == "final_answer"
    assert result.answer == "La respuesta es 42."
    assert result.iterations == 1


def test_stops_on_token_budget(monkeypatch):
    monkeypatch.setattr(ra, "complete", _fake_complete_always_calls_tool)
    # Presupuesto minúsculo: debe abortar por tokens, no por iteraciones.
    agent = ra.ReActAgent(limits=AgentLimits(max_iterations=50, token_budget=20))
    result = agent.run("gasta tokens")
    assert result.stop_reason == "token_budget"
