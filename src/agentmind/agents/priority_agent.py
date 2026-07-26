"""
Priority Agent — nodo LangGraph (S2).

Sigue `docs/specs/spec-priority-agent.md`: reglas deterministas primero,
LLM (perfil `fast`) solo como gate puntual cuando las reglas no alcanzan
confianza suficiente. Es un workflow, no un agente: el camino es siempre
impacto -> urgencia -> matriz -> SLA; el LLM resuelve una sub-tarea semántica
concreta y devuelve el control, no planifica ni elige herramientas.

Heurística de "score de cobertura" (el spec no fija la fórmula exacta, solo
el umbral): cada señal de impacto que matchea aporta una confianza propia
("cuánta evidencia literal hay detrás de este match"); nos quedamos con el
score más alto entre las señales que matchearon, y con el nivel de impacto
que trae esa señal. Así el resultado es determinista y auditable en
`priority_reasoning`, que es lo que pide la nota de gobernanza del spec.
"""

from __future__ import annotations

import json
from typing import Callable

from .. import domain
from ..models import Completion, complete
from ..observability import traced
from ..state import IncidentState

CompleteFn = Callable[..., Completion]

_PROFILE = "fast"  # el spec solo escala a LLM con este perfil, nunca a 'smart'

IMPACT_GATE_THRESHOLD = 0.7          # score_impacto < 0.7 -> gate a LLM
URGENCY_CONFIDENCE_THRESHOLD = 0.8   # business_process_confidence < 0.8 -> gate
LOW_CONFIDENCE_THRESHOLD = 0.5       # confianza del LLM < 0.5 -> needs_human_review

# Señales de impacto por regla, con su propia confianza ("cuánta evidencia
# literal hay detrás"). Ver docstring del módulo.
_PHRASE_MATCH_SCORE = 0.9
_INTEGRATION_DOWN_SCORE = 0.85
_VOLUME_EXTREME_SCORE = 0.8   # afectados > 100 o < 10: umbral inequívoco
_VOLUME_MID_SCORE = 0.6       # afectados 10-100: banda ambigua a propósito


def _score_impact_from_rules(state: IncidentState) -> tuple[str | None, float, str]:
    """Impacto por reglas deterministas. Devuelve (nivel|None, score, motivo)."""
    text = f"{state.get('title', '')} {state.get('description', '')}".lower()
    affected = state.get("affected_users") or 0

    candidates: list[tuple[str, float, str]] = []  # (nivel, score, motivo)

    matched_phrase = next((p for p in domain.IMPACT_CRITICAL_PHRASES if p in text), None)
    if matched_phrase:
        candidates.append(("alto", _PHRASE_MATCH_SCORE, f"frase crítica detectada: '{matched_phrase}'"))

    if state.get("system") == "INTEGRATION" and "down" in text:
        candidates.append(("alto", _INTEGRATION_DOWN_SCORE, "system=INTEGRATION + keyword 'down'"))

    if affected > 100 or "toda una oficina" in text:
        candidates.append(("alto", _VOLUME_EXTREME_SCORE, f"volumen alto de afectados ({affected})"))
    elif affected < 10 and affected > 0:
        candidates.append(("bajo", _VOLUME_EXTREME_SCORE, f"volumen bajo de afectados ({affected})"))
    elif 10 <= affected <= 100:
        candidates.append(("medio", _VOLUME_MID_SCORE, f"volumen medio de afectados ({affected}), banda ambigua"))

    if not candidates:
        return None, 0.0, "sin señales de impacto por reglas (ni frases críticas ni volumen concluyente)"

    level, score, reason = max(candidates, key=lambda c: c[1])
    return level, score, reason


def _urgency_from_table(state: IncidentState) -> tuple[str | None, float, str]:
    """Urgencia por lookup determinista en domain.BUSINESS_PROCESS_URGENCY."""
    bp = (state.get("business_process") or "").strip().upper()
    bp_confidence = state.get("business_process_confidence", 0.0)

    if not bp or bp not in domain.BUSINESS_PROCESS_URGENCY:
        return None, 0.0, f"business_process vacío o fuera de tabla: '{bp or '(vacío)'}'"
    if bp_confidence < URGENCY_CONFIDENCE_THRESHOLD:
        return None, bp_confidence, (
            f"business_process_confidence={bp_confidence:.2f} < {URGENCY_CONFIDENCE_THRESHOLD} "
            "(umbral estricto de urgencia)"
        )

    level = domain.BUSINESS_PROCESS_URGENCY[bp]
    return level, 1.0, f"lookup directo: business_process='{bp}' -> urgencia_base='{level}'"


def _ticket_text(state: IncidentState) -> str:
    return f"Título: {state.get('title', '')}\nDescripción: {state.get('description', '')}"


def _extract_first_json_object(text: str) -> str:
    """Encuentra el primer objeto `{...}` balanceado dentro de `text`.

    Los LLM (sobre todo modelos locales vía Ollama) suelen devolver JSON
    válido seguido de texto explicativo ("Esta clasificación se basa en...").
    `json.loads` sobre la respuesta completa revienta con
    `JSONDecodeError: Extra data` en ese caso. Aquí solo nos quedamos con el
    primer objeto bien cerrado, ignorando lo que venga antes o después,
    contando llaves con cuidado de no confundirnos con `{`/`}` dentro de
    strings del propio JSON.
    """
    start = text.find("{")
    if start == -1:
        raise ValueError("no se encontró ningún objeto JSON en la respuesta del modelo")

    depth = 0
    in_string = False
    escape_next = False
    for i in range(start, len(text)):
        char = text[i]
        if in_string:
            if escape_next:
                escape_next = False
            elif char == "\\":
                escape_next = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]

    raise ValueError("objeto JSON sin cerrar en la respuesta del modelo")


def _parse_json_content(content: str | None) -> dict:
    if not content:
        raise ValueError("respuesta vacía del modelo")
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[len("json"):]
    json_str = _extract_first_json_object(text.strip())
    return json.loads(json_str)


def _llm_impact_gate(state: IncidentState, complete_fn: CompleteFn) -> tuple[str, float]:
    """Gate a LLM (perfil fast) para impacto cuando el score de reglas es bajo."""
    system_prompt = (
        "Clasifica el IMPACTO de esta incidencia de Salesforce como "
        "'alto', 'medio' o 'bajo'. Frases de referencia de contenido crítico "
        f"(impacto alto): {list(domain.IMPACT_CRITICAL_PHRASES)}. "
        'Responde SOLO JSON: {"impact_level": "alto|medio|bajo", "confidence": float}'
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": _ticket_text(state)},
    ]
    resp = complete_fn(_PROFILE, messages, response_format={"type": "json_object"})
    data = _parse_json_content(resp.content)
    return str(data["impact_level"]).strip().lower(), float(data["confidence"])


def _llm_urgency_gate(state: IncidentState, complete_fn: CompleteFn) -> tuple[str, float]:
    """Gate a LLM (perfil fast) para urgencia cuando el proceso de negocio no
    permite un lookup directo (vacío, desconocido o de baja confianza)."""
    table_hint = {code: level for code, level in domain.BUSINESS_PROCESS_URGENCY.items()}
    system_prompt = (
        "Infiere el proceso de negocio real de esta incidencia a partir del "
        "texto libre y clasifica su URGENCIA como 'alta', 'media' o 'baja'. "
        f"Tabla de referencia business_process -> urgencia_base: {table_hint}. "
        'Responde SOLO JSON: {"urgency_level": "alta|media|baja", "confidence": float}'
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": _ticket_text(state)},
    ]
    resp = complete_fn(_PROFILE, messages, response_format={"type": "json_object"})
    data = _parse_json_content(resp.content)
    return str(data["urgency_level"]).strip().lower(), float(data["confidence"])


@traced("priority_node")
def priority_node(state: IncidentState, *, complete_fn: CompleteFn = complete) -> dict:
    """Nodo LangGraph de Priority. Recibe el IncidentState (con Intake ya
    aplicado), devuelve el delta: impacto, urgencia, prioridad, SLA."""
    reasoning_parts: list[str] = []
    needs_human_review = False

    # --- Impacto ---
    impact_level, impact_score, impact_reason = _score_impact_from_rules(state)
    if impact_level is None or impact_score < IMPACT_GATE_THRESHOLD:
        reasoning_parts.append(f"impacto: reglas insuficientes ({impact_reason}) -> gate LLM")
        llm_level, llm_confidence = _llm_impact_gate(state, complete_fn)
        if llm_confidence < LOW_CONFIDENCE_THRESHOLD:
            impact_level = None
            impact_confidence = llm_confidence
            needs_human_review = True
            reasoning_parts.append(f"impacto: LLM con baja confianza ({llm_confidence:.2f}) -> revisión humana")
        else:
            impact_level = llm_level
            impact_confidence = llm_confidence
            reasoning_parts.append(f"impacto: LLM decide '{llm_level}' (confidence={llm_confidence:.2f})")
    else:
        impact_confidence = impact_score
        reasoning_parts.append(f"impacto: regla decide '{impact_level}' ({impact_reason}, score={impact_score:.2f})")

    # --- Urgencia ---
    urgency_level, urgency_confidence, urgency_reason = _urgency_from_table(state)
    if urgency_level is None:
        reasoning_parts.append(f"urgencia: lookup insuficiente ({urgency_reason}) -> gate LLM")
        llm_level, llm_confidence = _llm_urgency_gate(state, complete_fn)
        if llm_confidence < LOW_CONFIDENCE_THRESHOLD:
            urgency_level = None
            urgency_confidence = llm_confidence
            needs_human_review = True
            reasoning_parts.append(f"urgencia: LLM con baja confianza ({llm_confidence:.2f}) -> revisión humana")
        else:
            urgency_level = llm_level
            urgency_confidence = llm_confidence
            reasoning_parts.append(f"urgencia: LLM decide '{llm_level}' (confidence={llm_confidence:.2f})")
    else:
        reasoning_parts.append(f"urgencia: {urgency_reason}")

    # --- Matriz + SLA (solo si ambos ejes están resueltos) ---
    if needs_human_review:
        priority = ""
        sla_response = ""
        sla_resolution = ""
        reasoning_parts.append("matriz NO ejecutada: needs_human_review=true")
    else:
        priority = domain.PRIORITY_MATRIX[impact_level][urgency_level]
        sla_response, sla_resolution = domain.SLA_BY_PRIORITY[priority]
        reasoning_parts.append(f"matriz: impacto={impact_level} x urgencia={urgency_level} -> {priority}")

    return {
        "impact_level": impact_level or "",
        "impact_confidence": impact_confidence,
        "urgency_level": urgency_level or "",
        "urgency_confidence": urgency_confidence,
        "priority": priority,
        "sla_response": sla_response,
        "sla_resolution": sla_resolution,
        "needs_human_review": needs_human_review,
        "priority_reasoning": " | ".join(reasoning_parts),
        "trace": [f"priority: {' | '.join(reasoning_parts)}"],
    }


def route_after_priority(state: IncidentState) -> str:
    """Arista condicional del grafo (spec de Priority, 'Señal de enrutado')."""
    if state.get("needs_human_review"):
        return "human_review"
    return "rca"
