"""
Tests del Intake Agent (S2) — criterio de éxito #8 del spec: al menos 3
incidencias sintéticas (APEX claro, INTEG claro, ticket vago).

No llamamos a ningún modelo real: inyectamos un `complete_fn` doble (mismo
patrón que `tests/test_react_agent.py`). Esto también prueba, sin mocks de
librería, que `intake_node` acepta la inyección de dependencia que usan el
demo E2E y el StateGraph.
"""

from __future__ import annotations

import json

from agentmind import domain
from agentmind.models import Completion
from agentmind.agents.intake_agent import (
    _SYSTEM_PROMPT,
    _parse_json_content,
    intake_node,
    route_after_intake,
)


def _fake_complete(payload: dict, *, raise_for_profiles: tuple[str, ...] = (), trailing_text: str = ""):
    """Doble de `models.complete`: devuelve `payload` como JSON, o lanza si
    el perfil llamado está en `raise_for_profiles` (para simular fallback).

    `trailing_text`: simula un modelo que añade texto explicativo después
    del JSON (típico en modelos locales vía Ollama)."""

    def _complete(profile: str, messages: list[dict], tools=None, **kwargs) -> Completion:
        if profile in raise_for_profiles:
            raise RuntimeError(f"perfil '{profile}' no disponible (simulado)")
        return Completion(
            content=json.dumps(payload) + trailing_text,
            tool_calls=[],
            finish_reason="stop",
            prompt_tokens=20,
            completion_tokens=10,
        )

    return _complete


def _base_ticket(**overrides) -> dict:
    ticket = {
        "incident_id": "INC-TEST-0001",
        "title": "",
        "description": "",
        "created_at": "2026-07-20T09:00:00Z",
        "channel": "email",
        "environment": "production",
        "reporter_email": "cliente@empresa.com",
        "account_name": "Empresa Cliente SA",
        "contact_name": "Ana Pérez",
        "affected_users": 5,
        "error_messages": [],
    }
    ticket.update(overrides)
    return ticket


# --- Caso 1: APEX claro ------------------------------------------------------

def test_apex_claro_clasifica_ok():
    ticket = _base_ticket(
        title="Apex trigger OpportunityTrigger falla al cerrar Closed Won",
        description=(
            "Cuando el comercial cambia la etapa de una oportunidad a Closed Won, "
            "el sistema devuelve FIELD_CUSTOM_VALIDATION_EXCEPTION y no guarda."
        ),
        affected_users=45,
        error_messages=["FIELD_CUSTOM_VALIDATION_EXCEPTION: Revenue date invalid"],
    )
    fake = _fake_complete(
        {
            "category": "APEX",
            "system": "SALES_CLOUD",
            "business_process": "SALES_FLOW",
            "affected_objects": ["Opportunity"],
            "confidence": 0.93,
            "needs_clarification": False,
        }
    )

    result = intake_node(ticket, complete_fn=fake)

    assert result["category"] == "APEX"
    assert result["system"] == "SALES_CLOUD"
    assert result["business_process"] == "SALES_FLOW"
    assert result["needs_clarification"] is False
    assert result["intake_status"] == "ok"
    assert result["confidence"] == 0.93
    assert result["business_process_confidence"] == 0.93
    assert route_after_intake({**ticket, **result}) == "priority"


# --- Caso 2: INTEG claro ------------------------------------------------------

def test_integ_claro_clasifica_ok():
    ticket = _base_ticket(
        title="Integración con SAP cae con error 429",
        description=(
            "El middleware que sincroniza pedidos con SAP empieza a devolver "
            "'429 Too Many Requests' desde esta madrugada. Los pedidos no sincronizan."
        ),
        affected_users=30,
        error_messages=["429 Too Many Requests: rate limit exceeded"],
    )
    fake = _fake_complete(
        {
            "category": "INTEG",
            "system": "INTEGRATION",
            "business_process": "SAP_INTEGRATION",
            "affected_objects": [],
            "confidence": 0.9,
            "needs_clarification": False,
        }
    )

    result = intake_node(ticket, complete_fn=fake)

    assert result["category"] == "INTEG"
    assert result["business_process"] == "SAP_INTEGRATION"
    assert result["intake_status"] == "ok"
    assert route_after_intake({**ticket, **result}) == "priority"


# --- Caso 3: ticket vago -> needs_clarification ------------------------------

def test_ticket_vago_pide_clarificacion():
    ticket = _base_ticket(
        title="Algo no funciona en Salesforce",
        description="No sé, algo va mal, revisadlo por favor.",
        affected_users=1,
    )
    fake = _fake_complete(
        {
            "category": "APEX",
            "system": "PLATFORM",
            "business_process": "",
            "affected_objects": [],
            "confidence": 0.3,
            "needs_clarification": True,
        }
    )

    result = intake_node(ticket, complete_fn=fake)

    assert result["needs_clarification"] is True
    assert result["intake_status"] == "needs_clarification"
    assert result["confidence"] < 0.6
    assert route_after_intake({**ticket, **result}) == "clarification"


# --- Fallback local -> fast ---------------------------------------------------

def test_fallback_a_fast_si_local_falla():
    ticket = _base_ticket(title="Trigger de Apex falla", description="Error en Apex.")
    fake = _fake_complete(
        {
            "category": "APEX",
            "system": "PLATFORM",
            "business_process": "SALES_FLOW",
            "affected_objects": [],
            "confidence": 0.8,
            "needs_clarification": False,
        },
        raise_for_profiles=("local",),
    )

    result = intake_node(ticket, complete_fn=fake)

    assert result["intake_status"] == "ok"
    assert "fast" in result["trace"][0]


# --- Fallo total de ambos perfiles: nunca revienta el grafo ------------------

def test_fallo_total_no_revienta_y_marca_rejected():
    ticket = _base_ticket(title="x", description="y")

    def _always_fails(profile, messages, tools=None, **kwargs):
        raise RuntimeError("modelo caído (simulado)")

    result = intake_node(ticket, complete_fn=_always_fails)

    assert result["intake_status"] == "rejected"
    assert result["needs_clarification"] is True
    assert result["confidence"] == 0.0


# --- Regresión: JSON válido + texto adicional detrás (JSONDecodeError real) --

def test_clasifica_ok_si_el_modelo_anade_texto_tras_el_json():
    """Reproduce el mismo fallo que en Priority: un modelo local añade una
    explicación en texto plano después del JSON pedido."""
    ticket = _base_ticket(
        title="Apex trigger falla",
        description="Error en un trigger de Apex al guardar la oportunidad.",
        affected_users=45,
    )
    fake = _fake_complete(
        {
            "category": "APEX",
            "system": "SALES_CLOUD",
            "business_process": "SALES_FLOW",
            "affected_objects": ["Opportunity"],
            "confidence": 0.9,
            "needs_clarification": False,
        },
        trailing_text="\n\nEsta clasificación se basa en el trigger mencionado en la descripción.",
    )

    result = intake_node(ticket, complete_fn=fake)

    assert result["category"] == "APEX"
    assert result["intake_status"] == "ok"


def test_parse_json_content_ignora_texto_extra_tras_el_json():
    content = (
        '{"category": "APEX", "system": "SALES_CLOUD", "business_process": "SALES_FLOW", '
        '"affected_objects": [], "confidence": 0.9, "needs_clarification": false}\n\n'
        "Espero que esta clasificación te sea útil."
    )
    data = _parse_json_content(content)
    assert data["category"] == "APEX"
    assert data["confidence"] == 0.9


# --- Regresión: business_process necesita descripción, no solo el código ----
# (INC-2026-0732: "altas de nuevos puntos de suministro" salió SALES_FLOW en
# vez de CONTRACTING porque el prompt solo listaba códigos desnudos.)

def test_prompt_incluye_descripcion_de_cada_business_process():
    """El prompt debe llevar 'CÓDIGO: descripción', no solo el código — si
    solo ve 'SALES_FLOW' y 'CONTRACTING' el LLM no tiene forma de distinguir
    un alta de suministro de un pipeline comercial genérico."""
    for code, description in domain.BUSINESS_PROCESS_DESCRIPTIONS.items():
        assert code in _SYSTEM_PROMPT
        assert description in _SYSTEM_PROMPT
    # Las dos que se confundieron en producción, explícitamente:
    assert "CONTRACTING: Contratación / Alta de suministro" in _SYSTEM_PROMPT
    assert "SALES_FLOW: Proceso comercial / pipeline de ventas (Sales Cloud)" in _SYSTEM_PROMPT


def test_inc_2026_0732_alta_de_suministro_clasifica_como_contracting():
    """Ticket real que falló en Studio: alta de nuevos puntos de suministro
    bloqueada. Con la descripción completa en el prompt, el LLM debe poder
    distinguirlo de SALES_FLOW."""
    ticket = _base_ticket(
        incident_id="INC-2026-0732",
        title="Problemas con altas de suministro esta mañana",
        description=(
            "Varios comerciales de la zona de Cataluña nos comentan que llevan "
            "desde primera hora sin poder avanzar las altas de nuevos puntos de "
            "suministro que tenían agendadas para hoy. No hay mensaje de error "
            "visible, simplemente el proceso no avanza."
        ),
        created_at="2026-07-22T10:05:00Z",
        channel="email",
        environment="production",
        reporter_email="maria.lopez@ellevio-partner.com",
        account_name="Ellevio Distribución Cataluña",
        contact_name="María López",
    )
    fake = _fake_complete(
        {
            "category": "FLOW",
            "system": "SALES_CLOUD",
            "business_process": "CONTRACTING",
            "affected_objects": ["Opportunity"],
            "confidence": 0.95,
            "needs_clarification": False,
        }
    )

    result = intake_node(ticket, complete_fn=fake)

    assert result["business_process"] == "CONTRACTING"
    assert result["intake_status"] == "ok"
    assert result["confidence"] == 0.95
    assert result["business_process_confidence"] == 0.95
