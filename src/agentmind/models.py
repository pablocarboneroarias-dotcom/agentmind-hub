"""
Interfaz única con los modelos.

Todo el proyecto llama a `complete(...)`. Nadie llama a litellm/anthropic/openai
directamente. Ventajas:
  - cambias de proveedor en un sitio (config.py),
  - los reintentos y el conteo de tokens viven aquí, no repartidos por cada agente,
  - los agentes quedan limpios y centrados en su lógica.

Usa litellm por debajo porque habla con Claude, OpenAI, Ollama (Qwen local) y
tu proxy LiteLLM con la misma firma estilo OpenAI.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import litellm

from . import config


@dataclass
class Usage:
    """Contador acumulado de tokens de una ejecución completa del agente."""

    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def total(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    def add(self, prompt: int, completion: int) -> None:
        self.prompt_tokens += prompt
        self.completion_tokens += completion


@dataclass
class Completion:
    """Respuesta normalizada de una llamada al modelo."""

    content: str | None
    tool_calls: list[dict] = field(default_factory=list)
    finish_reason: str | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    raw: Any = None


# Errores que merece la pena reintentar (transitorios de red/proveedor)
_RETRYABLE = (
    litellm.exceptions.RateLimitError,
    litellm.exceptions.APIConnectionError,
    litellm.exceptions.InternalServerError,
    litellm.exceptions.Timeout,
)


def complete(
    profile: str,
    messages: list[dict],
    tools: list[dict] | None = None,
    *,
    temperature: float | None = None,
    timeout: int | None = None,
    max_retries: int | None = None,
) -> Completion:
    """Una llamada al modelo, con reintentos y backoff exponencial.

    `profile` es un perfil con nombre ('fast', 'smart', 'local'); config.py lo
    traduce al modelo concreto (tu LiteLLM o proveedor directo).
    """
    limits = config.DEFAULT_LIMITS
    temperature = limits.temperature if temperature is None else temperature
    timeout = limits.request_timeout_s if timeout is None else timeout
    max_retries = limits.max_retries if max_retries is None else max_retries

    model, extra = config.resolve_model(profile)

    kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "timeout": timeout,
        **extra,
    }
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"

    last_err: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            resp = litellm.completion(**kwargs)
            choice = resp.choices[0]
            msg = choice.message
            usage = getattr(resp, "usage", None)
            return Completion(
                content=msg.get("content"),
                tool_calls=_normalize_tool_calls(msg),
                finish_reason=choice.get("finish_reason"),
                prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
                completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
                raw=resp,
            )
        except _RETRYABLE as err:
            last_err = err
            if attempt == max_retries:
                break
            backoff = 2 ** attempt  # 1s, 2s, 4s...
            time.sleep(backoff)
        # Errores NO transitorios (auth, bad request) se propagan de inmediato:
        # no tiene sentido reintentar una clave mal puesta.

    raise RuntimeError(
        f"Fallo al llamar al modelo '{profile}' tras {max_retries} reintentos"
    ) from last_err


def _normalize_tool_calls(message: Any) -> list[dict]:
    """Convierte los tool_calls del proveedor a una lista de dicts homogénea."""
    raw_calls = message.get("tool_calls") or []
    normalized: list[dict] = []
    for call in raw_calls:
        fn = call["function"]
        normalized.append(
            {
                "id": call.get("id", ""),
                "name": fn["name"],
                "arguments": fn.get("arguments", "{}"),  # string JSON crudo
            }
        )
    return normalized
