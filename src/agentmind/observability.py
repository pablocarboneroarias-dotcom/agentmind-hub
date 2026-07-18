"""
Observabilidad con LangSmith, activada desde el día 1.

Exponemos un decorador `traced` que:
  - si tienes LANGSMITH_API_KEY configurada, envuelve la función con el
    `@traceable` real de LangSmith (verás cada paso del agente en la UI),
  - si no, es un no-op transparente (no rompe nada, no añade dependencia dura).

Esto materializa la modificación #2 del plan: ver lo que hace el agente desde
el primer refactor, sin esperar a la Semana 8.
"""

from __future__ import annotations

from functools import wraps
from typing import Any, Callable

from . import config


def traced(name: str | None = None, run_type: str = "chain") -> Callable:
    """Decorador de trazabilidad. Uso: @traced("react_agent.run")."""

    def decorator(func: Callable) -> Callable:
        if not config.LANGSMITH_ENABLED:
            return func  # no-op limpio

        try:
            from langsmith import traceable

            return traceable(name=name or func.__name__, run_type=run_type)(func)
        except ImportError:
            # langsmith no instalado -> seguimos sin trazas
            @wraps(func)
            def _fallback(*args: Any, **kwargs: Any) -> Any:
                return func(*args, **kwargs)

            return _fallback

    return decorator
