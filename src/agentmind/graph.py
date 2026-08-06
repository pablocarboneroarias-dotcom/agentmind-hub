"""
StateGraph de AgentMind Hub — grafo incremental (S2: Intake + Priority; S3: RCA; S4: Solution).

"Grafo incremental" (decisión ya tomada, ver CONTEXTO.md): se monta pronto y
se le añaden nodos según se construye cada agente. `clarification` y
`human_review` (human-in-the-loop, S6) siguen siendo ramas placeholder que
solo dejan una miga de trace y terminan; `rca` y `solution` ya son agentes
reales (S3, S4).

    intake --(route_after_intake)--> clarification | priority
    priority --(route_after_priority)--> human_review | rca
    rca --> solution --> END (Comms Agent, S6, aún no existe)
"""

from __future__ import annotations

from functools import partial
from typing import Callable

from langgraph.graph import END, StateGraph

from .agents.intake_agent import intake_node, route_after_intake
from .agents.priority_agent import priority_node, route_after_priority
from .agents.rca_agent import rca_node
from .agents.solution_agent import solution_node
from .models import Completion, complete
from .state import IncidentState

CompleteFn = Callable[..., Completion]


def _clarification_node(state: IncidentState) -> dict:
    """Placeholder: en S6 esto dispara el gate HITL de solicitud de info.
    Por ahora solo deja constancia en el trace y termina el grafo."""
    return {"trace": ["grafo: enrutado a clarification (pendiente de HITL en S6)"]}


def _human_review_node(state: IncidentState) -> dict:
    """Placeholder: en S6 esto encola el caso para un humano. Por ahora solo
    deja constancia en el trace y termina el grafo."""
    return {"trace": ["grafo: enrutado a revisión humana (pendiente de HITL en S6)"]}


def build_graph(*, complete_fn: CompleteFn = complete):
    """Construye y compila el StateGraph. `complete_fn` se inyecta en los
    nodos que llaman al LLM (por defecto `models.complete`; los tests y el
    demo E2E pasan un doble determinista)."""
    graph = StateGraph(IncidentState)

    graph.add_node("intake", partial(intake_node, complete_fn=complete_fn))
    graph.add_node("priority", partial(priority_node, complete_fn=complete_fn))
    graph.add_node("clarification", _clarification_node)
    graph.add_node("human_review", _human_review_node)
    graph.add_node("rca", partial(rca_node, complete_fn=complete_fn))
    graph.add_node("solution", partial(solution_node, complete_fn=complete_fn))

    graph.set_entry_point("intake")
    graph.add_conditional_edges(
        "intake",
        route_after_intake,
        {"clarification": "clarification", "priority": "priority"},
    )
    graph.add_conditional_edges(
        "priority",
        route_after_priority,
        {"human_review": "human_review", "rca": "rca"},
    )

    graph.add_edge("clarification", END)
    graph.add_edge("human_review", END)
    graph.add_edge("rca", "solution")
    graph.add_edge("solution", END)

    return graph.compile()


# Instancia a nivel de módulo: LangGraph Studio (`langgraph dev`) necesita
# apuntar a un grafo ya compilado en `langgraph.json`, no a la función
# builder. Usa el `complete_fn` real (`models.complete` -> tus perfiles
# LiteLLM), así que Intake/Priority llamarán al modelo de verdad.
graph = build_graph()
