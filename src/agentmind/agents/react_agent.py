"""
ReAct Agent — versión production-grade (entregable de la Semana 1).

Como no tenías a mano el react_agent.py de la Fase 1, esto es una
implementación limpia desde cero que se convierte en tu PATRÓN DE REFERENCIA.
La idea de la Semana 1 es entender el bucle ReAct a pelo ANTES de que LangGraph
te lo abstraiga en la Semana 2. Por eso el bucle está escrito a mano y visible.

¿Qué es ReAct? Un bucle de Razonar + Actuar:
    1. El modelo razona sobre la petición.
    2. Si necesita datos, pide una herramienta (Acción).
    3. Ejecutamos la herramienta y le devolvemos el resultado (Observación).
    4. Repite hasta que tenga respuesta final o toque un límite.

Lo que lo hace "production-grade" (los límites explícitos del plan):
    - tope de iteraciones (evita bucles infinitos de tool calls),
    - presupuesto de tokens (evita costes desbocados),
    - reintentos con backoff ante errores transitorios (en models.py),
    - herramientas que nunca revientan el bucle (devuelven el error como texto),
    - razón de parada explícita y trazable.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..config import AgentLimits, DEFAULT_LIMITS
from ..models import Usage, complete
from ..observability import traced
from ..tools import TOOL_SCHEMAS, run_tool


DEFAULT_SYSTEM_PROMPT = (
    "Eres un agente de resolución de incidencias técnicas. Razona paso a paso. "
    "Usa las herramientas disponibles cuando necesites datos que no tienes. "
    "Cuando tengas la respuesta, respóndela directamente sin pedir más herramientas."
)


@dataclass
class AgentResult:
    """Resultado completo de una ejecución, pensado para depurar y evaluar."""

    answer: str | None
    stop_reason: str            # "final_answer" | "max_iterations" | "token_budget"
    iterations: int
    usage: Usage
    messages: list[dict] = field(default_factory=list)  # transcript completo


class ReActAgent:
    """Un agente ReAct con límites duros y trazabilidad."""

    def __init__(
        self,
        *,
        profile: str = "smart",
        tools_schemas: list[dict] | None = None,
        system_prompt: str = DEFAULT_SYSTEM_PROMPT,
        limits: AgentLimits = DEFAULT_LIMITS,
    ) -> None:
        self.profile = profile
        self.tools_schemas = tools_schemas if tools_schemas is not None else TOOL_SCHEMAS
        self.system_prompt = system_prompt
        self.limits = limits

    @traced("react_agent.run")
    def run(self, query: str) -> AgentResult:
        """Ejecuta el bucle ReAct sobre una petición y devuelve un AgentResult."""
        messages: list[dict] = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": query},
        ]
        usage = Usage()

        for iteration in range(1, self.limits.max_iterations + 1):
            # --- 1) Comprobar presupuesto de tokens ANTES de gastar más ---
            if usage.total >= self.limits.token_budget:
                return AgentResult(
                    answer=None,
                    stop_reason="token_budget",
                    iterations=iteration - 1,
                    usage=usage,
                    messages=messages,
                )

            # --- 2) Llamar al modelo (con reintentos gestionados en models.py) ---
            resp = complete(
                self.profile,
                messages,
                tools=self.tools_schemas,
            )
            usage.add(resp.prompt_tokens, resp.completion_tokens)

            # --- 3) ¿Pide herramientas o da respuesta final? ---
            if not resp.tool_calls:
                # No hay acción -> es la respuesta final
                return AgentResult(
                    answer=resp.content or "",
                    stop_reason="final_answer",
                    iterations=iteration,
                    usage=usage,
                    messages=messages,
                )

            # Registramos el turno del asistente (con sus tool_calls) en el historial.
            messages.append(_assistant_turn(resp))

            # --- 4) Ejecutar cada herramienta y adjuntar la observación ---
            for call in resp.tool_calls:
                observation = run_tool(call["name"], call["arguments"])
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call["id"],
                        "name": call["name"],
                        "content": observation,
                    }
                )
            # ...y vuelta al principio del bucle.

        # Si salimos del for, es que agotamos las iteraciones sin respuesta final.
        return AgentResult(
            answer=None,
            stop_reason="max_iterations",
            iterations=self.limits.max_iterations,
            usage=usage,
            messages=messages,
        )


def _assistant_turn(resp) -> dict:
    """Reconstruye el mensaje 'assistant' con tool_calls para el historial."""
    return {
        "role": "assistant",
        "content": resp.content or "",
        "tool_calls": [
            {
                "id": c["id"],
                "type": "function",
                "function": {"name": c["name"], "arguments": c["arguments"]},
            }
            for c in resp.tool_calls
        ],
    }


if __name__ == "__main__":
    # Ejecución manual rápida: python -m agentmind.agents.react_agent
    agent = ReActAgent(profile="fast")
    result = agent.run("¿Cuánto es 3 * (4 + 2) y hay incidencias de login parecidas?")
    print("Respuesta:", result.answer)
    print("Parada:", result.stop_reason, "| iteraciones:", result.iterations)
    print("Tokens:", result.usage.total)
