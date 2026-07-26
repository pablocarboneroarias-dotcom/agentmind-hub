# exercises/s2_stategraph_minimal.py
#
# "Tócalo una vez" de S2 — StateGraph mínimo con 2 nodos.
# Objetivo: ver cómo el estado fluye y se enriquece entre nodos.
# NO es el código de producción — es el ejercicio de comprensión.

from typing import TypedDict
from langgraph.graph import StateGraph, END


# ── 1. STATE ──────────────────────────────────────────────────────────────────
# Versión simplificada del IncidentState: solo los campos que tocan
# Intake y Priority. El grafo completo tendrá muchos más.

class IncidentState(TypedDict):
    # Campos que llegan con el ticket
    incident_id:         str
    title:               str
    description:         str
    affected_users:      int

    # Intake rellena estos
    category:            str    # APEX / FLOW / INTEG / PERM...
    system:              str    # SALES_CLOUD / CPQ / INTEGRATION...
    business_process:    str    # SALES_FLOW / CPQ / SAP_INTEGRATION...
    confidence:          float  # 0-1: seguridad de la clasificación

    # Priority rellena estos
    severity:            str    # P1 / P2 / P3 / P4
    priority_rationale:  str    # explicación de la prioridad


# ── 2. NODES ──────────────────────────────────────────────────────────────────
# Cada nodo recibe el state completo y devuelve SOLO los campos que modifica.
# LangGraph hace el merge automáticamente.
#
# En producción estos nodos llamarían a LiteLLM con structured output.
# Aquí simulamos la lógica para ver el patrón sin necesitar API keys.

def intake_node(state: IncidentState) -> dict:
    """
    Workflow de clasificación: categoría, sistema y proceso de negocio.
    En producción: llamada a LiteLLM con perfil 'fast' y structured output.
    """
    print(f"\n[INTAKE] Procesando: {state['title']}")

    # Lógica de clasificación simplificada (en producción: LLM)
    description = state["description"].lower()

    if "trigger" in description or "apex" in description:
        category = "APEX"
        confidence = 0.92
    elif "flow" in description:
        category = "FLOW"
        confidence = 0.88
    elif "sap" in description or "integración" in description:
        category = "INTEG"
        confidence = 0.85
    else:
        category = "APEX"
        confidence = 0.45  # bajo → necesita clarificación

    if "opportunity" in description or "oportunidad" in description:
        system = "SALES_CLOUD"
        business_process = "SALES_FLOW"
    elif "cpq" in description or "precio" in description:
        system = "CPQ"
        business_process = "CPQ"
    elif "sap" in description:
        system = "INTEGRATION"
        business_process = "SAP_INTEGRATION"
    else:
        system = "PLATFORM"
        business_process = "PLATFORM"

    print(f"[INTAKE] → category={category}, system={system}, confidence={confidence}")

    # Devuelve SOLO los campos que Intake rellena (delta, no el state completo)
    return {
        "category": category,
        "system": system,
        "business_process": business_process,
        "confidence": confidence,
    }


def priority_node(state: IncidentState) -> dict:
    """
    Workflow de priorización: reglas deterministas primero, LLM en ambiguos.
    En producción: reglas Python + llamada a LiteLLM perfil 'fast' si ambiguo.
    """
    print(f"\n[PRIORITY] Calculando prioridad para: {state['incident_id']}")
    print(f"[PRIORITY] affected_users={state['affected_users']}, system={state['system']}")

    # Reglas deterministas (siempre auditables, coste cero)
    if state["affected_users"] > 100:
        severity = "P1"
        rationale = "Más de 100 usuarios afectados → P1 automático por regla."
    elif state["system"] == "INTEGRATION" and state["affected_users"] > 20:
        severity = "P1"
        rationale = "Integración caída con impacto masivo → P1 por regla."
    elif state["affected_users"] > 30:
        severity = "P2"
        rationale = "Más de 30 usuarios afectados → P2 por regla."
    elif state["category"] == "APEX" and state["business_process"] == "SALES_FLOW":
        severity = "P2"
        rationale = "APEX en Sales Flow → impacto en pipeline de ventas → P2 por regla."
    else:
        # Aquí en producción entraría el LLM para casos ambiguos
        severity = "P3"
        rationale = "Sin regla determinista aplicable → P3 por defecto (LLM en producción)."

    print(f"[PRIORITY] → severity={severity}")
    print(f"[PRIORITY] → rationale={rationale}")

    return {
        "severity": severity,
        "priority_rationale": rationale,
    }


# ── 3. GRAPH ──────────────────────────────────────────────────────────────────
# Aquí es donde ocurre la magia: declaras nodos y aristas,
# y LangGraph gestiona el flujo y el merge del estado.

def build_graph() -> StateGraph:
    graph = StateGraph(IncidentState)

    # Registrar nodos
    graph.add_node("intake", intake_node)
    graph.add_node("priority", priority_node)

    # Definir el flujo: entrada → intake → priority → fin
    graph.set_entry_point("intake")
    graph.add_edge("intake", "priority")
    graph.add_edge("priority", END)

    return graph.compile()


# ── 4. EJECUCIÓN ──────────────────────────────────────────────────────────────

if __name__ == "__main__":

    # Incidencia sintética de Salesforce — arquetipo 1: trigger roto
    incident = {
        "incident_id": "INC-2024-0042",
        "title": "Apex trigger falla al cerrar oportunidad en Closed Won",
        "description": (
            "Cuando el comercial cambia la etapa de una oportunidad a Closed Won, "
            "el sistema devuelve FIELD_CUSTOM_VALIDATION_EXCEPTION y no guarda. "
            "El trigger OpportunityTrigger parece ser el origen. "
            "Afecta a todo el equipo de ventas EMEA."
        ),
        "affected_users": 120,
        # Campos que rellenarán los nodos (vacíos al entrar)
        "category": "",
        "system": "",
        "business_process": "",
        "confidence": 0.0,
        "severity": "",
        "priority_rationale": "",
    }

    print("=" * 60)
    print("AgentMind Hub — StateGraph mínimo S2")
    print("=" * 60)
    print(f"\nIncidencia de entrada: {incident['incident_id']}")
    print(f"Usuarios afectados: {incident['affected_users']}")

    # Compilar y ejecutar el grafo
    app = build_graph()
    result = app.invoke(incident)

    # Estado final — enriquecido por ambos nodos
    print("\n" + "=" * 60)
    print("ESTADO FINAL (IncidentState enriquecido)")
    print("=" * 60)
    print(f"  incident_id:      {result['incident_id']}")
    print(f"  category:         {result['category']}")
    print(f"  system:           {result['system']}")
    print(f"  business_process: {result['business_process']}")
    print(f"  confidence:       {result['confidence']}")
    print(f"  severity:         {result['severity']}")
    print(f"  rationale:        {result['priority_rationale']}")
