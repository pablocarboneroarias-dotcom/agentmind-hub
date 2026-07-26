"""
Vocabulario y tablas del dominio Salesforce CRM.

Espejo en Python de `project/dominio-salesforce.md` (fuente de verdad). Vive
aquí, separado de los nodos, porque el spec de Priority es explícito: "la
tabla de negocio es dato, no código" — así se puede ajustar sin tocar
`intake_agent.py` ni `priority_agent.py`. Si cambias algo aquí, cámbialo
también en el `.md` para que no diverjan.
"""

from __future__ import annotations

# --- Vocabulario cerrado de Intake (criterio de éxito #2 del spec) -----------

CATEGORIES: frozenset[str] = frozenset(
    {"APEX", "FLOW", "INTEG", "PERM", "DATA", "PERF", "CPQ", "REPORT", "EMAIL", "UI"}
)

SYSTEMS: frozenset[str] = frozenset(
    {
        "SALES_CLOUD",
        "SERVICE_CLOUD",
        "CPQ",
        "MARKETING",
        "INTEGRATION",
        "PLATFORM",
        "ANALYTICS",
    }
)

# business_process -> urgencia_base ("alta" | "media" | "baja").
# Las filas marcadas como "Media-alta" en el spec original de Priority se
# redondean a "alta" (ver nota de gobernanza en dominio-salesforce.md).
BUSINESS_PROCESS_URGENCY: dict[str, str] = {
    "CONTRACTING": "alta",
    "OWNERSHIP_CHANGE": "alta",
    "CONTRACT_RENEWAL": "alta",
    "SAP_INTEGRATION": "alta",
    "CUSTOMER_SERVICE": "alta",
    "COMPLAINTS": "alta",
    "BILLING": "alta",
    "COLLECTIONS": "media",
    "METER_READING": "media",
    "REPORTING": "baja",
    "GENERAL_INQUIRY": "baja",
    "SALES_FLOW": "media",
    "CPQ": "alta",
    "DATA_INTEGRITY": "alta",
}

BUSINESS_PROCESSES: frozenset[str] = frozenset(BUSINESS_PROCESS_URGENCY)

# Descripciones legibles de cada business_process (mismo texto que la columna
# "Descripción" de la tabla en dominio-salesforce.md). Intake se las pasa al
# LLM junto al código: el código solo ("SALES_FLOW", "CONTRACTING") no basta
# para distinguir semánticamente procesos parecidos — un ticket de "alta de
# nuevo punto de suministro" es CONTRACTING, no SALES_FLOW, pero un LLM que
# solo ve la lista de códigos no tiene forma de saberlo.
BUSINESS_PROCESS_DESCRIPTIONS: dict[str, str] = {
    "CONTRACTING": "Contratación / Alta de suministro",
    "OWNERSHIP_CHANGE": "Cambio de titularidad",
    "CONTRACT_RENEWAL": "Renovación de contratos",
    "SAP_INTEGRATION": "Integraciones con distribuidora / SAP",
    "CUSTOMER_SERVICE": "CTI / Atención al cliente (telefonía)",
    "COMPLAINTS": "Reclamaciones / Quejas regulatorias",
    "BILLING": "Facturación / Emisión de facturas",
    "COLLECTIONS": "Gestión de cobros / Impagos",
    "METER_READING": "Lecturas / Telemedida",
    "REPORTING": "Reporting interno / Dashboards",
    "GENERAL_INQUIRY": "Consulta general / Información al cliente",
    "SALES_FLOW": "Proceso comercial / pipeline de ventas (Sales Cloud)",
    "CPQ": "Configuración de precios y ofertas (CPQ)",
    "DATA_INTEGRITY": "Inconsistencia / corrupción de datos entre sistemas o pantallas (sync, duplicados, discrepancias)",
}

assert BUSINESS_PROCESS_DESCRIPTIONS.keys() == BUSINESS_PROCESS_URGENCY.keys(), (
    "BUSINESS_PROCESS_DESCRIPTIONS y BUSINESS_PROCESS_URGENCY deben tener las "
    "mismas claves (misma tabla que dominio-salesforce.md)"
)

# Objetos Salesforce conocidos (mapa de objetos de dominio-salesforce.md).
KNOWN_SF_OBJECTS: frozenset[str] = frozenset(
    {
        "Account",
        "Contact",
        "Opportunity",
        "OpportunityLineItem",
        "Quote",
        "Case",
        "CaseComment",
        "Entitlement",
        "Lead",
        "User",
        "Profile",
        "PermissionSet",
        "Role",
    }
)

# --- Diccionario de impacto de Priority ("frases de contenido crítico") -----

IMPACT_CRITICAL_PHRASES: tuple[str, ...] = (
    "no se puede contratar en toda el área",
    "todo el cti caído",
    "no se envían contratos a distribuidora",
)

# --- Matriz Impacto x Urgencia -> Prioridad ---------------------------------

PRIORITY_MATRIX: dict[str, dict[str, str]] = {
    "alto": {"alta": "P1", "media": "P2", "baja": "P3"},
    "medio": {"alta": "P2", "media": "P3", "baja": "P3"},
    "bajo": {"alta": "P3", "media": "P3", "baja": "P4"},
}

# --- SLA por prioridad (tabla operativa de spec-priority-agent.md) ----------

SLA_BY_PRIORITY: dict[str, tuple[str, str]] = {
    # priority -> (sla_response, sla_resolution)
    "P1": ("15min", "2h"),
    "P2": ("30min", "4h"),
    "P3": ("2h", "24h"),
    "P4": ("8h", "48h"),
}
