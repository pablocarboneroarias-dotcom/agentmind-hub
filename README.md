# AgentMind Hub — Fase 2

Agent Engineering y orquestación multi-agente, mediante un caso de uso real:
un **sistema de gestión de incidencias alineado con ITIL 4** (Intake → Priority
→ RCA → Solution → Comms), orquestado con patrón supervisor y con un gate
human-in-the-loop obligatorio antes de enviar el email al equipo técnico.

Stack: **LangGraph** (orquestación), **Claude Agent SDK** (diseño interno del
Solution Agent), **MCP** (integración con Gmail), **LangSmith** (trazabilidad y
evaluación). Modelos vía **LiteLLM** (Claude / OpenAI / Qwen local).

## Estructura

```
src/agentmind/
  config.py         # routing de modelos por perfil + límites + LangSmith
  models.py         # complete(): interfaz única con reintentos y conteo de tokens
  observability.py  # tracing LangSmith (no-op si no hay clave)
  state.py          # IncidentState: esquema compartido del pipeline (borrador)
  tools.py          # herramientas de ejemplo + registro
  agents/
    react_agent.py  # ⭐ entregable Semana 1: ReAct production-grade
tests/              # smoke tests (sin llamadas reales al modelo)
scripts/            # generación de dataset sintético (modificación #1)
data/incidents/     # dataset de incidencias (se rellena en Semana 1/3)
project/            # instrucciones y contexto para el Proyecto de Claude.ai
```

## Puesta en marcha (Mac Mini)

```bash
# 1) Entorno con uv (o tu gestor preferido)
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"

# 2) Config
cp .env.example .env      # y rellena lo que uses (proxy LiteLLM o claves)

# 3) Prueba rápida del ReAct agent
python -m agentmind.agents.react_agent

# 4) Tests (no gastan tokens)
pytest
```

## Semana 1 — dónde estamos

Cimientos + patrón ReAct de referencia:
- [x] Scaffolding, config, routing por perfiles
- [x] Tracing LangSmith enchufado desde el día 1
- [x] `react_agent.py` production-grade (límites de iteraciones, presupuesto de
      tokens, reintentos, herramientas que no rompen el bucle)
- [x] Borrador de `IncidentState` (adelantado de la Semana 2)
- [ ] Decidir y generar el dataset sintético (`scripts/generate_incidents.py`)

Siguiente: Semana 2 — Intake Agent + Priority Agent sobre LangGraph, reutilizando
`IncidentState` como estado del grafo.
