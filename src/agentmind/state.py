"""
Esquema de estado compartido del pipeline de incidencias.

Está aquí ya en la Semana 1 a propósito (modificación #3): el `state schema`
condiciona todo el grafo, así que definirlo pronto evita rehacer nodos luego.
De momento es un borrador: lo iremos afinando al montar cada agente.

Cuando lleguemos a LangGraph (Semana 2) este TypedDict será el `State` del
StateGraph. Por ahora sirve como contrato de datos entre etapas.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional, TypedDict


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class IncidentState(TypedDict, total=False):
    """Estado que fluye por el pipeline Intake -> Priority -> RCA -> Solution -> Comms."""

    # --- Entrada ---
    incident_id: str
    raw_text: str                    # descripción original de la incidencia

    # --- Intake Agent (Semana 2) ---
    category: str                    # p.ej. "Salesforce / Integración"
    affected_system: str
    severity: Severity

    # --- Priority Agent (Semana 2) ---
    impact: int                      # 1-4
    urgency: int                     # 1-4
    priority: str                    # derivada de impacto x urgencia + SLA
    sla_hours: Optional[float]

    # --- RCA Agent (Semana 3) ---
    root_cause: str
    rca_confidence: float            # 0-1; si baja, el supervisor puede reenrutar
    similar_incidents: list[str]     # ids recuperados del histórico (RAG)

    # --- Solution Agent (Semana 4) ---
    proposed_solution: str
    action_plan: list[str]

    # --- Comms Agent (Semana 6) ---
    tech_team_email_draft: str
    human_approved: bool             # gate obligatorio antes de enviar

    # --- Metadatos de ejecución ---
    trace: list[str]                 # migas de pan para depurar el recorrido
