"""
Utilidades compartidas por los scripts de generación del corpus sintético (S3).

Los 10 arquetipos de incidencia son los de `project/dominio-salesforce.md`
("10 arquetipos de incidencia"). Se centralizan aquí porque `generate_incidents.py`,
`generate_technical_docs.py` y `generate_codebase_artifacts.py` necesitan la
MISMA asignación arquetipo -> (categoría, sistema, componente, proceso de
negocio) para que el corpus sea coherente entre tablas (p.ej. que el
technical_doc de "OpportunityTrigger" y el snippet de código del mismo
arquetipo compartan `related_business_process`).
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from agentmind.models import complete


@dataclass(frozen=True)
class Archetype:
    id: int
    name: str
    category: str
    system: str
    business_process: str
    component: str  # nombre del trigger/flow/integración/etc. protagonista


ARCHETYPES: list[Archetype] = [
    Archetype(1, "Trigger en Opportunity roto tras deploy", "APEX", "SALES_CLOUD", "SALES_FLOW", "OpportunityTrigger"),
    Archetype(2, "Flow de onboarding de Case que no dispara", "FLOW", "SERVICE_CLOUD", "CUSTOMER_SERVICE", "Case_Onboarding_Flow"),
    Archetype(3, "Integración con SAP que falla por límites de API (429)", "INTEG", "INTEGRATION", "SAP_INTEGRATION", "SAP_Middleware_Connector"),
    Archetype(4, "Usuarios de EMEA sin acceso a cuentas de cliente (sharing rule)", "PERM", "SALES_CLOUD", "CUSTOMER_SERVICE", "Account_Sharing_Rule_EMEA"),
    Archetype(5, "Duplicados masivos en Account tras migración de datos", "DATA", "PLATFORM", "DATA_INTEGRITY", "Account_Dedup_Rule"),
    Archetype(6, "Batch job de CPQ timeout por query sin índice", "PERF", "CPQ", "CPQ", "CPQ_Pricing_Batch_Job"),
    Archetype(7, "Precio de bundle CPQ incorrecto para descuentos > 30%", "CPQ", "CPQ", "CPQ", "CPQ_Bundle_Pricing_Rule"),
    Archetype(8, "Dashboard de pipeline de ventas con datos del mes pasado", "REPORT", "ANALYTICS", "REPORTING", "Sales_Pipeline_Dashboard"),
    Archetype(9, "Email de bienvenida no se envía al crear Lead desde web", "EMAIL", "MARKETING", "SALES_FLOW", "Lead_Welcome_Workflow_Rule"),
    Archetype(10, "Lightning component de gestión de contratos da error 500", "UI", "SALES_CLOUD", "CONTRACT_RENEWAL", "ContractManagementLWC"),
]

ARCHETYPES_BY_ID: dict[int, Archetype] = {a.id: a for a in ARCHETYPES}


def generate_json(prompt: str, profile: str = "smart", timeout: int = 180):
    """Llama a complete() pidiendo JSON y parsea la respuesta.

    Convención ya usada por el stub original de generate_incidents.py: pedir
    "SOLO un array/objeto JSON" y quitar un posible fence ```json ... ```.
    `timeout` sube de los 60s por defecto de AgentLimits: generar un lote de
    varias incidencias con texto rico (root_cause, resolution_notes...) tarda
    más que un turno normal de agente y el default se quedaba corto (visto en
    la práctica: timeout a los 60s con lotes de 15 incidencias).
    """
    resp = complete(profile, [{"role": "user", "content": prompt}], timeout=timeout)
    text = (resp.content or "").strip()
    text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    return json.loads(text)
