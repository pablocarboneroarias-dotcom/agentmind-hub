"""
Demo end-to-end del StateGraph de S2: Intake -> Priority sobre un ticket
sintético de Salesforce, mostrando el IncidentState completo a la salida.

Uso: python scripts/run_pipeline_demo.py

Por qué un `complete_fn` doble y no el modelo real: este demo debe poder
correr sin depender de que tu proxy LiteLLM / Ollama estén arriba en este
momento. El doble simula exactamente lo que devolvería el perfil `local` en
Intake y el perfil `fast` en los gates de Priority — mismo contrato
(Completion con `.content` en JSON), cero diferencia de código en los nodos.
Para probarlo contra el modelo real basta con no pasar `complete_fn` a
`build_graph()` (usará `models.complete` con tus perfiles de verdad).
"""

from __future__ import annotations

import json

from agentmind.graph import build_graph
from agentmind.models import Completion

# --- Ticket sintético: arquetipo 1 de dominio-salesforce.md (trigger roto) ---
TICKET = {
    "incident_id": "INC-2026-0731",
    "title": "Apex trigger OpportunityTrigger falla al cerrar Closed Won",
    "description": (
        "Cuando el comercial cambia la etapa de una oportunidad a 'Closed Won', "
        "el sistema devuelve 'FIELD_CUSTOM_VALIDATION_EXCEPTION' y no guarda el "
        "cambio. Afecta a todo el equipo de ventas de EMEA."
    ),
    "created_at": "2026-07-22T09:23:00Z",
    "channel": "email",
    "environment": "production",
    "reporter_email": "john.smith@cliente.com",
    "account_name": "Cliente EMEA SA",
    "contact_name": "John Smith",
    "affected_users": 120,
    "error_messages": [
        "FIELD_CUSTOM_VALIDATION_EXCEPTION: Revenue recognition date cannot be in the past"
    ],
}

# Respuesta que el LLM devolvería en Intake para este ticket (perfil 'local').
_INTAKE_RESPONSE = {
    "category": "APEX",
    "system": "SALES_CLOUD",
    "business_process": "SALES_FLOW",
    "affected_objects": ["Opportunity"],
    "confidence": 0.94,
    "needs_clarification": False,
}


def _fake_complete(profile: str, messages: list[dict], tools=None, **kwargs) -> Completion:
    """Doble determinista de `models.complete`.

    Solo hace falta responder a Intake: con 120 usuarios afectados y sin
    business_process de baja confianza, Priority resuelve impacto y urgencia
    por reglas deterministas y NO debería llamar a ningún gate LLM. Si algún
    gate se llamase igualmente (p.ej. tras editar el ticket de arriba), este
    doble lanza para que el fallo sea explícito en vez de silencioso.
    """
    system_prompt = messages[0]["content"]
    if "IMPACTO" in system_prompt or "URGENCIA" in system_prompt:
        raise AssertionError(
            "Priority no debería escalar a LLM con este ticket; revisa el "
            "ticket sintético o la lógica de reglas si esto salta."
        )
    return Completion(
        content=json.dumps(_INTAKE_RESPONSE),
        tool_calls=[],
        finish_reason="stop",
        prompt_tokens=40,
        completion_tokens=20,
    )


def main() -> None:
    app = build_graph(complete_fn=_fake_complete)
    final_state = app.invoke(TICKET)

    print("=" * 70)
    print("AgentMind Hub — demo E2E S2 (Intake -> Priority)")
    print("=" * 70)
    print(f"\nTicket de entrada: {TICKET['incident_id']} — {TICKET['title']}\n")

    print("-" * 70)
    print("IncidentState completo a la salida del grafo:")
    print("-" * 70)
    for key, value in final_state.items():
        print(f"  {key:28s} = {value!r}")

    print("\n" + "-" * 70)
    print("Traza (breadcrumbs concatenados por el reducer operator.add):")
    print("-" * 70)
    for line in final_state.get("trace", []):
        print(f"  - {line}")


if __name__ == "__main__":
    main()
