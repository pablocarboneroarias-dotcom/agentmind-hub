"""
Esquema de estado compartido del pipeline de incidencias.

`IncidentState` es el `State` del `StateGraph` de LangGraph (S2). Cada nodo
recibe el state completo y devuelve solo el delta de campos que rellena;
LangGraph hace el merge. Las secciones de abajo siguen el orden del pipeline
(Intake -> Priority -> RCA -> Solution -> Comms) y están alineadas campo a
campo con `docs/specs/spec-intake-agent.md`, `docs/specs/spec-priority-agent.md`
y `docs/specs/spec-rca-agent.md`.
"""

from __future__ import annotations

import operator
from enum import Enum
from typing import Annotated, TypedDict


class UrgencyHint(str, Enum):
    """Vocabulario de `urgency_hint` (señal de Intake, no decisión de prioridad)."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class IncidentState(TypedDict, total=False):
    """Estado que fluye por el pipeline Intake -> Priority -> RCA -> Solution -> Comms."""

    # --- Entrada (ticket de Salesforce; Intake y Priority solo lo leen) ---
    incident_id: str
    title: str
    description: str
    created_at: str
    channel: str                      # email / web / phone / chat
    environment: str                  # production / sandbox
    reporter_email: str
    account_name: str
    contact_name: str
    affected_users: int
    error_messages: list[str]

    # --- Intake Agent (Semana 2) ---
    category: str                     # vocabulario: domain.CATEGORIES
    system: str                       # vocabulario: domain.SYSTEMS
    business_process: str             # vocabulario: domain.BUSINESS_PROCESSES
    affected_objects: list[str]       # objetos SF detectados: Opportunity, Case...
    confidence: float                 # 0.0-1.0: seguridad de la clasificación
    needs_clarification: bool
    urgency_hint: str                 # UrgencyHint: señal preliminar, no decisión
    intake_status: str                # "ok" | "needs_clarification" | "rejected"
    # Puente entre specs: el spec de Priority pide la confianza que Intake le
    # puso a su clasificación de business_process, pero el spec de Intake solo
    # define un `confidence` global (no una confianza por campo). Intake
    # escribe aquí una copia de `confidence` — ver nota en intake_agent.py.
    business_process_confidence: float

    # --- Priority Agent (Semana 2) ---
    impact_level: str                 # "alto" | "medio" | "bajo"
    impact_confidence: float
    urgency_level: str                # "alta" | "media" | "baja"
    urgency_confidence: float
    priority: str                     # "P1" | "P2" | "P3" | "P4"
    sla_response: str                 # p.ej. "15min"
    sla_resolution: str               # p.ej. "2h"
    needs_human_review: bool
    priority_reasoning: str           # traza auditable de reglas/gates activados

    # --- RCA Agent (Semana 3) ---
    root_cause: str                   # "" si rca_status != "completed"
    rca_confidence: float             # 0-100 (spec-rca-agent.md); umbral de corte: 80
    rca_status: str                   # "completed" | "max_iterations" | "token_budget"
                                       # | "insufficient_evidence" | "model_error"
    rca_corroboration: str            # "multi_source" | "single_source" | ""
    rca_evidence: list[str]           # traza auditable: qué tool se llamó y qué devolvió
    rca_partial_findings: str         # resumen de la investigación, siempre relleno
    rca_iterations_used: int          # iteraciones del bucle ReAct consumidas
    similar_incidents: list[str]      # ids de incident_history citados como evidencia

    # --- Solution Agent (Semana 4) ---
    proposed_solution: str
    action_plan: list[str]

    # --- Comms Agent (Semana 6) ---
    tech_team_email_draft: str
    human_approved: bool              # gate obligatorio antes de enviar

    # --- Metadatos de ejecución ---
    # Annotated + operator.add: cada nodo devuelve solo SU miga de pan y
    # LangGraph las concatena (reducer), en vez de que el último nodo
    # sobrescriba lo que escribieron los anteriores.
    trace: Annotated[list[str], operator.add]
