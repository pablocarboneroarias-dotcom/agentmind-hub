"""
Tests del Priority Agent (S2) — criterio de éxito #8 del spec: 4 incidencias
sintéticas (P1 claro por reglas, gate de impacto, gate de urgencia,
needs_human_review con ambos gates fallando).
"""

from __future__ import annotations

import json

from agentmind.models import Completion
from agentmind.agents.priority_agent import (
    _extract_first_json_object,
    _parse_json_content,
    priority_node,
    route_after_priority,
)


def _fake_gate_complete(
    *,
    impact_response: dict | None = None,
    urgency_response: dict | None = None,
    trailing_text: str = "",
):
    """Doble de `models.complete` para los gates de Priority.

    Distingue impacto vs urgencia por el contenido del system prompt (cada
    gate tiene un prompt distinto, ver priority_agent.py). Si se llama a un
    gate sin respuesta configurada, falla el test explícitamente: así los
    tests de "sin gate" verifican de verdad que las reglas bastaron solas.

    `trailing_text`: simula un modelo (típicamente uno local vía Ollama) que
    añade texto explicativo después del JSON, para reproducir el caso real
    de `JSONDecodeError: Extra data`.
    """

    def _complete(profile: str, messages: list[dict], tools=None, **kwargs) -> Completion:
        system_prompt = messages[0]["content"]
        if "IMPACTO" in system_prompt:
            assert impact_response is not None, "no debería escalar el gate de impacto"
            payload = impact_response
        else:
            assert urgency_response is not None, "no debería escalar el gate de urgencia"
            payload = urgency_response
        return Completion(
            content=json.dumps(payload) + trailing_text,
            tool_calls=[],
            finish_reason="stop",
            prompt_tokens=15,
            completion_tokens=8,
        )

    return _complete


def _base_state(**overrides) -> dict:
    state = {
        "incident_id": "INC-TEST-0100",
        "title": "",
        "description": "",
        "affected_users": 5,
        "business_process": "",
        "business_process_confidence": 0.0,
    }
    state.update(overrides)
    return state


# --- Caso 1: P1 claro por reglas, sin gate a LLM -----------------------------

def test_p1_claro_por_reglas_sin_gate_llm():
    state = _base_state(
        title="Corte total de atención telefónica",
        description="Todo el CTI caído, ningún agente puede atender llamadas.",
        affected_users=200,
        business_process="CUSTOMER_SERVICE",
        business_process_confidence=0.95,
    )
    fake = _fake_gate_complete()  # cualquier llamada revienta el test a propósito

    result = priority_node(state, complete_fn=fake)

    assert result["impact_level"] == "alto"
    assert result["urgency_level"] == "alta"
    assert result["priority"] == "P1"
    assert result["needs_human_review"] is False
    assert result["sla_response"] == "15min"
    assert result["sla_resolution"] == "2h"
    assert route_after_priority({**state, **result}) == "rca"


# --- Caso 2: dispara el gate de impacto (score bajo) -------------------------

def test_dispara_gate_de_impacto():
    state = _base_state(
        title="Facturas con retraso",
        description="Algunos clientes reportan que sus facturas tardan más de lo normal.",
        affected_users=50,  # banda ambigua 10-100 -> score 0.6 < 0.7
        business_process="BILLING",
        business_process_confidence=0.9,  # urgencia se resuelve por lookup, sin gate
    )
    fake = _fake_gate_complete(impact_response={"impact_level": "medio", "confidence": 0.75})

    result = priority_node(state, complete_fn=fake)

    assert result["impact_level"] == "medio"
    assert result["impact_confidence"] == 0.75
    assert result["urgency_level"] == "alta"  # BILLING -> alta (ver domain.py)
    assert result["priority"] == "P2"
    assert result["needs_human_review"] is False
    assert "gate LLM" in result["priority_reasoning"]


# --- Caso 3: dispara el gate de urgencia (business_process vacío) -----------

def test_dispara_gate_de_urgencia():
    state = _base_state(
        title="No se envían contratos a distribuidora",
        description="No se envían contratos a distribuidora desde ayer, bloqueado.",
        affected_users=15,
        business_process="",  # vacío -> gate obligatorio
        business_process_confidence=0.0,
    )
    fake = _fake_gate_complete(urgency_response={"urgency_level": "media", "confidence": 0.7})

    result = priority_node(state, complete_fn=fake)

    assert result["impact_level"] == "alto"  # frase crítica, score 0.9, sin gate
    assert result["urgency_level"] == "media"
    assert result["urgency_confidence"] == 0.7
    assert result["priority"] == "P2"  # alto x media -> P2
    assert result["needs_human_review"] is False


# --- Caso 4: needs_human_review (ambos gates con baja confianza) -----------

def test_needs_human_review_si_ambos_gates_fallan():
    state = _base_state(
        title="Incidencia poco clara",
        description="Hay un problema pero no está claro el alcance real.",
        affected_users=50,  # banda ambigua -> gate de impacto
        business_process="",  # vacío -> gate de urgencia
        business_process_confidence=0.0,
    )
    fake = _fake_gate_complete(
        impact_response={"impact_level": "medio", "confidence": 0.3},
        urgency_response={"urgency_level": "baja", "confidence": 0.2},
    )

    result = priority_node(state, complete_fn=fake)

    assert result["needs_human_review"] is True
    assert result["priority"] == ""
    assert result["sla_response"] == ""
    assert route_after_priority({**state, **result}) == "human_review"


# --- Regresión: JSON válido + texto adicional detrás (JSONDecodeError real) --

def test_gate_tolera_json_seguido_de_texto_explicativo():
    """Reproduce el fallo real: un modelo (típicamente local vía Ollama)
    devuelve el JSON pedido y luego añade una explicación en texto plano.
    Antes, `_parse_json_content` asumía que la respuesta ENTERA era JSON y
    reventaba con `json.JSONDecodeError: Extra data`."""
    state = _base_state(
        title="Facturas con retraso",
        description="Algunos clientes reportan que sus facturas tardan más de lo normal.",
        affected_users=50,  # banda ambigua -> gate de impacto
        business_process="BILLING",
        business_process_confidence=0.9,  # urgencia por lookup, sin gate
    )
    fake = _fake_gate_complete(
        impact_response={"impact_level": "medio", "confidence": 0.75},
        trailing_text="\n\nEsta clasificación se basa en el volumen de afectados reportado.",
    )

    result = priority_node(state, complete_fn=fake)

    assert result["impact_level"] == "medio"
    assert result["impact_confidence"] == 0.75
    assert result["priority"] == "P2"


def test_parse_json_content_ignora_texto_extra_tras_el_json():
    content = (
        '{"urgency_level": "media", "confidence": 0.7}\n\n'
        "Espero que esta clasificación te sea útil. ¿Necesitas algo más?"
    )
    assert _parse_json_content(content) == {"urgency_level": "media", "confidence": 0.7}


def test_parse_json_content_ignora_texto_antes_del_json():
    content = 'Aquí tienes mi análisis:\n{"impact_level": "alto", "confidence": 0.9}'
    assert _parse_json_content(content) == {"impact_level": "alto", "confidence": 0.9}


def test_extract_first_json_object_respeta_llaves_dentro_de_strings():
    # Las llaves dentro de un string ("texto con { y }") no deben confundir
    # el conteo de profundidad del extractor.
    text = '{"reasoning": "impacto alto (texto con { llave } dentro)"} texto sobrante'
    extracted = _extract_first_json_object(text)
    assert extracted == '{"reasoning": "impacto alto (texto con { llave } dentro)"}'
    assert json.loads(extracted)["reasoning"] == "impacto alto (texto con { llave } dentro)"
