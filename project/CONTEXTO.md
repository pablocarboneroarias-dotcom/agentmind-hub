# AgentMind Hub — Contexto del Proyecto

Sube este fichero como conocimiento del Proyecto de Claude.ai. Es la fuente de
verdad: plan, entorno, decisiones y progreso. Mantenlo vivo.

## Objetivo del path
Dominio profesional en construcción y orquestación de agentes de IA mediante un
caso de uso real: sistema multi-agente de gestión de incidencias (análisis,
priorización, RCA, propuesta de solución y comunicación al equipo técnico).
Doble propósito: dominio técnico propio + aplicabilidad directa en Ellevio AMS.

## Caso de uso (ITIL 4)
Pipeline, cada etapa un agente, orquestados con patrón supervisor y routing
condicional:
- **Intake Agent** — clasifica (categoría, sistema, severidad), structured output. [S2]
- **Priority Agent** — impacto × urgencia + SLA; reglas + LLM en casos ambiguos. [S2]
- **RCA Agent** — Root Cause Analysis sobre histórico; RAG + tool use. [S3]
- **Solution Agent** — propone solución; subagente tipo Corrective Developer (Agent SDK). [S4]
- **Comms Agent** — redacta y envía email al EQUIPO TÉCNICO; human-in-the-loop obligatorio. [S6]

## Stack
- **LangGraph**: orquestación por grafos de estado (framework principal).
- **Claude Agent SDK**: diseño interno de agentes complejos (sobre todo Solution Agent).
- **MCP**: integración con sistemas reales (Gmail; opcionalmente Salesforce).
- **LangSmith**: trazabilidad y evaluación.
- Descartados como foco: CrewAI, AutoGen, n8n (solo cultura general).

## Entorno de trabajo (Mac Mini)
- Ollama + LiteLLM + Qwen3 8B local; API de Claude y OpenAI.
- LiteLLM con perfiles con nombre: fast, fast-light, experiment, smart (Claude
  Sonnet), local, local-fast, local-embed.
- El código llama a perfiles, nunca a modelos concretos.
- **PostgreSQL disponible.** Usos previstos: checkpointing/persistencia de
  LangGraph (estado durable, threads, human-in-the-loop de S6), y opcionalmente
  store del RAG del RCA Agent (pgvector) y del dataset de incidencias.

# Plan de 8 semanas — AgentMind Hub (modo arquitecto)

## Qué cambia respecto al plan original

- **Mismo esqueleto:** el pipeline ITIL 4 (Intake → Priority → RCA → Solution → Comms)
  sigue siendo la columna vertebral. No se toca la arquitectura del caso de uso.
- **Distinto modo:** de *autor* a *director*. No tecleas los agentes desde un fichero
  en blanco; escribes el spec, lo revisas, y diriges a Claude Code para que los monte.
- **Distinta profundidad:** el listón pasa de *"sé implementarlo"* a *"sé explicarlo,
  decidir la arquitectura y detectar cuándo está mal"*. Un **"tócalo una vez"** por
  concepto clave (como hicimos con el bucle ReAct) para tener criterio de verdad.
- **Distinto entregable:** ya no es *"programé este sistema"*, sino *"diseñé esto,
  entiendo cada pieza, defiendo cada decisión y ensamblé un prototipo funcional con IA"*.

## Elementos transversales (aplican a TODAS las semanas)

- **SDD como sistema operativo.** Cada semana de construcción sigue el mismo bucle:
  1) lees/decides el patrón → 2) escribes el **spec** del agente (qué debe hacer,
  entradas/salidas, criterios de éxito) → 3) lo revisamos → 4) diriges a Claude Code
  para implementarlo → 5) revisas y evalúas. El spec, no el código, es la fuente de verdad.
- **Capa de juicio (tu lente Deloitte).** En cada agente, decisión explícita y
  documentada de: *workflow vs. agente*, *patrón elegido*, *routing de modelo*
  (coste/latencia), y *nota de gobernanza/compliance* (qué se audita, qué se aprueba).
- **Ya decidido, no re-litigar:** dataset sintético primero · LangSmith desde el día 1 ·
  grafo incremental · frontera LangGraph (orquestación) / Agent SDK (diseño interno) ·
  routing de modelo por agente vía perfiles LiteLLM.

## Lectura previa (antes de arrancar, ~2-3h)

El criterio de arquitecto se apoya en dos textos de Anthropic. Léelos una vez y vuelve
a ellos cada semana:

- **"Building Effective Agents"** (guía de ingeniería): el catálogo de patrones
  (prompt chaining, routing, orchestrator-workers, evaluator-optimizer) y el criterio
  clave *workflow vs. agente*. Regla rectora: empieza simple, añade complejidad solo
  cuando lo justifique.
- **"Building Effective AI Agents: Architecture Patterns and Implementation Frameworks"**
  (PDF, 2026): la versión para tu rol — casar problema con patrón, seguridad/compliance,
  infraestructura y economía de routing de modelo.

---

## Las 8 semanas

Cada semana: **Decisión de arquitectura** · **Tócalo una vez** (hands-on mínimo) ·
**Qué diriges** (spec → Claude Code) · **Curso** · **Entregable**.

### S1 — Fundamentos + criterio de patrones  *(casi hecho)*
- **Decisión:** para cada uno de los 5 agentes, ¿workflow o agente? y ¿por qué?
  (dataset sintético ya decidido).
- **Tócalo una vez:** el bucle ReAct — **hecho**. Falta: *entender* (no reescribir)
  el `react_agent.py` que ya tienes, y saber dirigirlo.
- **Qué diriges:** —(semana de criterio, poca construcción).
- **Curso:** lectura de Anthropic (arriba) + empezar el short course de SDD.
- **Entregable:** cimientos ya montados + un **"mapa de patrones"** tuyo: tabla que
  decide, agente por agente, workflow-vs-agente y el patrón que usará.

### S2 — LangGraph I: el grafo y los primeros nodos (Intake + Priority)
- **Decisión:** el esquema de `IncidentState`; Intake como workflow de clasificación
  (structured output, modelo ligero); Priority como reglas + LLM en casos ambiguos.
- **Tócalo una vez:** monta a mano un `StateGraph` mínimo de 2 nodos para ver cómo
  fluye el estado por el grafo (State/Nodes/Edges).
- **Qué diriges:** spec de Intake y de Priority → Claude Code los implementa como nodos.
- **Curso:** DeepLearning.AI *AI Agents in LangGraph* + LangChain Academy
  *Introduction to LangGraph* (gratis, componentes esenciales).
- **Entregable:** grafo con Intake + Priority funcionando, y tú capaz de explicar por
  qué cada uno es workflow o agente.

### S3 — LangGraph II: subgrafos + RAG → RCA Agent
- **Decisión:** diseño del RAG (qué indexas del histórico, chunking, embeddings,
  pgvector sobre Postgres); por qué el RCA **es un agente** (razonamiento multi-paso).
- **Tócalo una vez:** una consulta RAG mínima a mano (embed → retrieve → mira qué
  devuelve) para ver por qué el retrieval manda sobre el prompt.
- **Qué diriges:** spec del RCA (fuentes, tools, criterio de causa raíz) → Claude Code.
- **Curso:** RAG de DeepLearning.AI (de arquitectura a evaluación).
- **Entregable:** RCA Agent haciendo RCA sobre el dataset con RAG + tool use, y tú
  capaz de defender las decisiones de diseño del RAG.

### S4 — Claude Agent SDK + subagentes → Solution Agent
- **Decisión:** patrón **orquestador-worker**; subagentes vs. teams; aislamiento de
  contexto; routing de modelo *dentro* (orquestador fuerte, workers baratos).
- **Tócalo una vez:** un orquestador mínimo que lanza **1 subagente** y recoge su
  resultado — para ver que un subagente es, en el fondo, otro bucle ReAct anidado con
  su propia lista de mensajes aislada.
- **Qué diriges:** spec del Solution Agent (subagente tipo *Corrective Developer*)
  → Claude Code con Agent SDK.
- **Curso:** docs del Claude Agent SDK (subagentes) + un patrón de orquestación.
- **Entregable:** Solution Agent con ≥1 subagente, y tú capaz de justificar
  subagente-vs-team y el routing de modelo interno.

### S5 — Orquestación: supervisor + routing condicional + retorno
- **Decisión:** el patrón de supervisor, las condiciones de routing entre agentes y la
  lógica de retorno (cuándo un agente devuelve al anterior). Como el grafo se montó
  incremental, esto es **afinar**, no integrar de cero.
- **Tócalo una vez:** traza/dibuja el grafo completo con sus aristas condicionales.
- **Qué diriges:** spec de las reglas de routing del supervisor → Claude Code.
- **Curso:** la parte de orquestación multi-agente (IBM *Agentic AI…* o LangGraph
  multi-agent).
- **Entregable:** pipeline end-to-end orquestado.

### S6 — Acción externa: human-in-the-loop + Comms Agent
- **Decisión:** el **gate HITL** antes de enviar el email al equipo técnico —tu terreno
  de gobernanza—. Punto de interrupción (interrupt de LangGraph + checkpointing en
  Postgres), qué se muestra al humano, cómo se aprueba/edita/rechaza.
- **Tócalo una vez:** provoca una interrupción y reanuda desde el checkpoint.
- **Qué diriges:** spec del Comms Agent + del gate HITL → Claude Code.
- **Curso:** DeepLearning.AI *data governance para agentes*.
- **Entregable:** Comms Agent que redacta el email y se detiene en el gate hasta que
  un humano aprueba.

### S7 — MCP: conexión real a Gmail
- **Decisión:** MCP como estándar de integración; qué expone el servidor de Gmail;
  permisos y seguridad (conecta con tu lente de compliance); el gate HITL delante de la
  acción real.
- **Tócalo una vez:** conecta el pipeline a Gmail vía MCP en un caso de prueba.
- **Qué diriges:** spec de la integración → Claude Code.
- **Curso:** cobertura MCP (cert IBM RAG & Agentic AI, o docs de MCP).
- **Entregable:** pipeline enviando (tras aprobación humana) un email real vía MCP.

### S8 — Evaluación, guardrails y demo
- **Decisión:** testing formal, datasets de evaluación, guardrails; la lente de
  *constitutional SDD* (principios no negociables de seguridad/compliance en el spec).
- **Tócalo una vez:** define **1 métrica** de evaluación y córrela en LangSmith.
- **Qué diriges:** spec de los guardrails y del dataset de eval → Claude Code.
- **Curso:** evaluación de agentes (DeepLearning.AI) + LangSmith Academy.
- **Entregable:** sistema evaluado + demo lista para Ellevio AMS. *(Opcional: cert IBM
  RAG & Agentic AI como credencial para LinkedIn/Deloitte.)*

---

## El bucle de trabajo semanal (SDD, resumido)

1. **Lee/decide** el patrón de la semana (apóyate en la guía de Anthropic).
2. **Escribe el spec** del agente: qué hace, entradas/salidas, criterios de éxito,
   nota de gobernanza.
3. **Revísalo** (conmigo) antes de generar nada.
4. **Dirige a Claude Code** para implementarlo contra el spec.
5. **Revisa y evalúa** el resultado; si algo se desvía, editas el spec y regeneras.

## Mapa de cursos → semanas

| Semana | Curso principal |
|---|---|
| Previo | Anthropic *Building Effective Agents* (guía + PDF de arquitectura) |
| S1 | Short course de **SDD** (Spec-Driven Development with Coding Agents) |
| S2 | DeepLearning.AI *AI Agents in LangGraph* + LangChain Academy *Intro to LangGraph* |
| S3 | RAG de DeepLearning.AI |
| S4 | Docs Claude Agent SDK (subagentes) + patrón de orquestación |
| S5 | Orquestación multi-agente (IBM / LangGraph) |
| S6 | Data governance para agentes (DeepLearning.AI) |
| S7 | MCP (cert IBM RAG & Agentic AI / docs MCP) |
| S8 | Evaluación de agentes (DeepLearning.AI) + LangSmith Academy |

## Nota: actualiza también el framing del proyecto

En las instrucciones del Proyecto y en el `CONTEXTO.md`, ajusta el rol para reflejar el
modo arquitecto: el objetivo es **fluidez de arquitecto/líder** (entender las tripas,
decidir arquitectura, dirigir la construcción con IA), no autoría de código en Python
en solitario. SDD es el método transversal; los subagentes son un patrón que se estudia
y se aplica en S4.


## Decisiones (log)
- 2026-07: dataset "sintético primero"; se generará con Claude en `scripts/generate_incidents.py`.
- 2026-07: tracing LangSmith desde el día 1.
- 2026-07: grafo incremental (no big-bang en S5).
- 2026-07: Agent SDK reservado al Solution Agent; resto como nodos LangGraph.
- 2026-07: routing de modelo por agente vía perfiles LiteLLM.
- 2026-07: PostgreSQL como backend de checkpointing de LangGraph (y candidato a
  store del RAG con pgvector).
- 2026-07: modelo de interacción/aprendizaje = Claude Sonnet (Opus para
  decisiones de arquitectura duras); dev-loop de agentes en `local` (Qwen 8B),
  Haiku para tool-calling/structured output, Sonnet para razonamiento (RCA/Solution).

## Log de progreso
- **S1 (en curso):** hecho el scaffolding, config con routing por perfiles,
  observabilidad LangSmith, `react_agent.py` production-grade con límites de
  iteraciones/tokens + reintentos, borrador de `IncidentState`, smoke tests.
  Pendiente: generar el dataset sintético.
- **S2 (construcción, 2026-07-22):** `IncidentState` afinado en `state.py` para
  cuadrar campo a campo con `spec-intake-agent.md` y `spec-priority-agent.md`
  (antes era un borrador de S1). `intake_node` y `priority_node` implementados
  y con tests unitarios sintéticos (12 tests, ver `tests/test_intake_agent.py`
  y `tests/test_priority_agent.py`). `graph.py` monta el `StateGraph` mínimo
  Intake -> Priority con las aristas condicionales de ambos specs, más nodos
  placeholder (`clarification`, `human_review`, `rca`) para no romper el
  grafo incremental hasta S3/S6. Demo E2E en `scripts/run_pipeline_demo.py`.
  Se completó también el vocabulario `business_process` que faltaba en
  `dominio-salesforce.md` (lo pedía el criterio de éxito #2 de Intake) — ver
  el log de decisiones de ese fichero para el detalle de las 3 reconciliaciones
  entre specs (vocabulario de business_process, redondeo "Media-alta" -> "alta",
  tabla de SLA operativa). Pendiente: correr esto contra el modelo real
  (Ollama/LiteLLM) en vez de los dobles de test, y el "tócalo una vez" de S2.
