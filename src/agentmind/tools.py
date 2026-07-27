"""
Herramientas de ejemplo para que el ReAct agent sea ejecutable de verdad.

Cada herramienta se describe con el schema estilo OpenAI (el que entienden
Claude, OpenAI y Qwen a través de litellm) y se registra en TOOL_REGISTRY.
El agente solo conoce el registro: añadir una herramienta no toca el agente.

Las 4 tools reales de RAG (S3) viven en `rag.py` y se registran aquí abajo;
`search_incidents` queda como mock de la Semana 1, superado por
`query_incident_history` — no se retira porque `react_agent.py` aún puede
usarlo como demo sin depender de Postgres.
"""

from __future__ import annotations

import json
from typing import Callable

from . import rag
from .codebase_repo import read_codebase_repo


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
    "query_incident_history": rag.query_incident_history,
    "search_technical_docs": rag.search_technical_docs,
    "search_runbooks": rag.search_runbooks,
    "search_codebase": rag.search_codebase,
    "read_codebase_repo": read_codebase_repo,
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
    {
        "type": "function",
        "function": {
            "name": "query_incident_history",
            "description": "Busca en el histórico de incidencias resueltas (RAG semántico) las más parecidas a la consulta.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Síntoma, error o descripción del problema a buscar."},
                    "k": {"type": "integer", "description": "Número de incidencias a devolver (por defecto 5)."},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_technical_docs",
            "description": "Busca documentación técnica del org (triggers, flows, integraciones, reglas de permisos) relevante a la consulta.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Componente o comportamiento a buscar."},
                    "k": {"type": "integer", "description": "Número de documentos a devolver (por defecto 5)."},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_runbooks",
            "description": "Busca runbooks de diagnóstico paso a paso; devuelve el procedimiento completo, no un fragmento suelto.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Tipo de problema a diagnosticar."},
                    "k": {"type": "integer", "description": "Número de runbooks completos a devolver (por defecto 2)."},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_codebase",
            "description": "Busca en artefactos de código sintéticos (fichas de feature, arquitectura, snippets anotados) por síntoma, sin necesitar el nombre exacto del archivo.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Descripción del síntoma o comportamiento a buscar en el código."},
                    "k": {"type": "integer", "description": "Número de fragmentos a devolver (por defecto 5)."},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_codebase_repo",
            "description": "Lee el contenido EXACTO de un fichero real del repo de juguete (codebase-toy-repo/), sin resumir. Úsalo cuando ya sepas qué fichero quieres mirar (p.ej. tras un resultado de search_codebase) y necesites verificar el código tal cual, no un resumen semántico.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Ruta relativa a la raíz de codebase-toy-repo/, p.ej. 'src/triggers/OpportunityTrigger.cls'.",
                    },
                },
                "required": ["path"],
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
