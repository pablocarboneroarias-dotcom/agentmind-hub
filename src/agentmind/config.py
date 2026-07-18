"""
Configuración central del proyecto.

Todo lo que pueda cambiar entre tu Mac Mini y otro entorno (claves de API,
URL del proxy de LiteLLM, presupuestos de tokens) se lee de variables de
entorno, no se hardcodea. Copia `.env.example` a `.env` y rellénalo.

Idea clave (modificación #5 del plan): el modelo NO se elige dentro de cada
agente. Se elige aquí, con perfiles con nombre, igual que ya haces en tu
LiteLLM. Así cambias "qué modelo usa el RCA" en un sitio, no en diez.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()  # carga .env si existe; en producción usarás env reales


# ---------------------------------------------------------------------------
# Routing de modelos
# ---------------------------------------------------------------------------
# Estos son los nombres de perfil de TU LiteLLM (fast, smart, local, ...).
# El código llama al perfil; tu proxy decide el modelo concreto. Si algún día
# quieres saltarte el proxy, cambia USE_LITELLM_PROXY=false y ajusta el
# diccionario DIRECT_MODELS de abajo.

USE_LITELLM_PROXY: bool = os.getenv("USE_LITELLM_PROXY", "true").lower() == "true"

# URL y clave de tu proxy LiteLLM en el Mac Mini
LITELLM_BASE_URL: str = os.getenv("LITELLM_BASE_URL", "http://localhost:4000")
LITELLM_API_KEY: str = os.getenv("LITELLM_API_KEY", "sk-anything")  # LiteLLM la ignora si no la exiges

# Fallback directo a proveedor (solo si USE_LITELLM_PROXY=false).
# Ajusta las cadenas exactas a las que tengas dadas de alta.
DIRECT_MODELS: dict[str, str] = {
    "fast": "anthropic/claude-haiku-4-5",
    "smart": "anthropic/claude-sonnet-4-5",   # confírmalo con tu config
    "local": "ollama/qwen3:8b",               # tu Qwen local vía Ollama
    "openai": "openai/gpt-4o",
}


def resolve_model(profile: str) -> tuple[str, dict]:
    """Traduce un perfil ('smart') al 'model' + kwargs que espera litellm.completion.

    Devuelve (model_string, extra_kwargs). Centralizar esto aquí es lo que hace
    que el resto del código sea agnóstico del proveedor.
    """
    if USE_LITELLM_PROXY:
        # litellm sabe hablar con un proxy LiteLLM con este prefijo
        return f"litellm_proxy/{profile}", {
            "api_base": LITELLM_BASE_URL,
            "api_key": LITELLM_API_KEY,
        }
    model = DIRECT_MODELS.get(profile)
    if model is None:
        raise ValueError(
            f"Perfil '{profile}' desconocido. Perfiles directos: {list(DIRECT_MODELS)}"
        )
    return model, {}


# ---------------------------------------------------------------------------
# Presupuestos y límites por defecto (modificación: límites explícitos)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class AgentLimits:
    """Límites duros para que un agente nunca se descontrole en bucle o coste."""

    max_iterations: int = 8          # tope de vueltas del bucle ReAct (tool calls)
    token_budget: int = 60_000       # tokens acumulados totales antes de abortar
    request_timeout_s: int = 60      # timeout por llamada al modelo
    max_retries: int = 3             # reintentos ante errores transitorios
    temperature: float = 0.0


DEFAULT_LIMITS = AgentLimits()


# ---------------------------------------------------------------------------
# Observabilidad (LangSmith)
# ---------------------------------------------------------------------------
# Tracing desde el día 1 (modificación #2). Si no pones la clave, todo funciona
# igual pero sin trazas. No bloquea nada.
LANGSMITH_ENABLED: bool = bool(os.getenv("LANGSMITH_API_KEY"))
LANGSMITH_PROJECT: str = os.getenv("LANGSMITH_PROJECT", "agentmind-hub")

if LANGSMITH_ENABLED:
    # LangSmith lee estas variables automáticamente
    os.environ.setdefault("LANGSMITH_TRACING", "true")
    os.environ.setdefault("LANGSMITH_PROJECT", LANGSMITH_PROJECT)
