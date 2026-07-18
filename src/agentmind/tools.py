"""
Herramientas de ejemplo para que el ReAct agent sea ejecutable de verdad.

Cada herramienta se describe con el schema estilo OpenAI (el que entienden
Claude, OpenAI y Qwen a través de litellm) y se registra en TOOL_REGISTRY.
El agente solo conoce el registro: añadir una herramienta no toca el agente.

Cuando construyamos el pipeline real, aquí vivirán tools como
`search_incident_history` (RAG) o `send_email` (con human-in-the-loop).
"""

from __future__ import annotations

import json
from typing import Callable


# --- Implementaciones ---------------------------------------------------------
def calculator(expression: str) -> str:
    """Evalúa una expresión aritmética simple. Solo para demostrar tool use."""
    allowed = set("0123456789+-*/(). ")
    if not set(expression) <= allowed:
        return "Error: la expresión contiene caracteres no permitidos."
    try:
        # eval acotado: sin builtins, solo aritmética
        return str(eval(expression, {"__builtins__": {}}, {}))
    except Exception as exc:  # noqa: BLE001 - devolvemos el error como observación
        return f"Error al evaluar: {exc}"


def search_incidents(query: str) -> str:
    """Mock de búsqueda en histórico de incidencias (placeholder del futuro RCA/RAG)."""
    fake_db = {
        "login": "INC-1042: caída de SSO por certificado caducado. Resuelto renovando cert.",
        "sync": "INC-0988: fallo de sincronización Salesforce-SAP por rate limit de API.",
        "timeout": "INC-1101: timeouts en batch nocturno por bloqueo de registros.",
    }
    hits = [v for k, v in fake_db.items() if k in query.lower()]
    return "\n".join(hits) if hits else "Sin incidencias similares en el histórico."


# --- Registro y schemas -------------------------------------------------------
TOOL_REGISTRY: dict[str, Callable[..., str]] = {
    "calculator": calculator,
    "search_incidents": search_incidents,
}

TOOL_SCHEMAS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "calculator",
            "description": "Evalúa una expresión aritmética (suma, resta, producto, división).",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "Expresión, p.ej. '3 * (4 + 2)'",
                    }
                },
                "required": ["expression"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_incidents",
            "description": "Busca incidencias pasadas parecidas en el histórico.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Términos de búsqueda (síntoma, sistema...).",
                    }
                },
                "required": ["query"],
            },
        },
    },
]


def run_tool(name: str, arguments: str) -> str:
    """Ejecuta una herramienta por nombre con argumentos en JSON (string).

    Diseñada para NO lanzar excepciones hacia arriba: cualquier problema se
    devuelve como texto para que el agente pueda leerlo y corregir el rumbo.
    Esto es parte del "manejo de errores" de la Semana 1.
    """
    fn = TOOL_REGISTRY.get(name)
    if fn is None:
        return f"Error: la herramienta '{name}' no existe. Disponibles: {list(TOOL_REGISTRY)}"
    try:
        kwargs = json.loads(arguments) if arguments else {}
    except json.JSONDecodeError:
        return f"Error: argumentos no son JSON válido: {arguments!r}"
    try:
        return fn(**kwargs)
    except TypeError as exc:
        return f"Error: argumentos incorrectos para '{name}': {exc}"
    except Exception as exc:  # noqa: BLE001
        return f"Error durante la ejecución de '{name}': {exc}"
