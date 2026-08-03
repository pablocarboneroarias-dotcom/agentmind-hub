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

### S3 — LangGraph II: subgrafos + RAG → RCA Agent  *(cerrado 2026-07-29)*
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
- **S3 (construcción, 2026-07-27/29) — CERRADO:** corpus RAG + RCA Agent
  completos, probados contra `langgraph dev` real (no solo dobles de test) y
  con el coste dimensionado sobre datos reales, no estimados.
  - **Corpus pgvector** (`docs/specs/rag-corpus-spec-s3.md`): 4 tablas —
    `incident_history` (150), `technical_docs` (25), `runbooks` (40 chunks
    de 8 runbooks), `codebase_artifacts` (27, incluida columna `file_path`
    añadida tras uso real). Embeddings con `embeddinggemma` (Ollama), no
    `nomic-embed-text` (decisión: multilingüe, el corpus es 100% español).
    Postgres en el contenedor Docker compartido `agentops-postgres`
    (`pgvector/pgvector:pg16`), DB propia `agentmind`.
  - **`codebase-toy-repo/`**: repo git independiente (gitignoreado aquí) con
    10 fichas de feature + 5 ficheros de código reales, uno por arquetipo
    de `dominio-salesforce.md` que es código de verdad (los declarativos —
    sharing rules, dedup rules, price rules, dashboard, workflow rule — solo
    tienen ficha, sin `.cls`/`.js` fantasma).
  - **RCA Agent** (`docs/specs/spec-rca-agent.md` + `rca-agent-prompt.md`,
    consolidando `rca-decisiones-s3.md`): `rca_node` es un agente ReAct real
    sobre `react_agent.py` de Fase 1, con 5 tools read-only (4 RAG +
    `read_codebase_repo`). `rca_status` cerrado como `Literal` de verdad
    (`state.RcaStatus`, 5 valores incl. `model_error`), verificado en
    runtime (`rca_agent._finalize`). Dos gates antes de aceptar `completed`
    autodeclarado por el modelo: ≥2 tool calls y confianza ≥80 (si no,
    degrada a `insufficient_evidence`). `graph.py`: `_rca_placeholder_node`
    sustituido por el nodo real, sin tocar `intake`/`priority`.
  - **Tres bugs reales encontrados y corregidos ejecutando contra el modelo
    de verdad** (no en tests con dobles), en orden:
    1. El agente adivinaba rutas de Salesforce DX genéricas al intentar
       `read_codebase_repo` porque `search_codebase` no exponía la ruta
       real → se añadió `codebase_artifacts.file_path`, expuesto como
       `ruta_repo` en el resultado.
    2. Tras encontrar evidencia directa suficiente (un comentario de bug
       explícito en el código), el agente seguía "verificando" con más
       llamadas a la misma tool hasta agotar `token_budget` → se añadió
       `max_calls_per_tool` a `ReActAgent` (tope duro de 2 por tool,
       verificado por código, no por criterio del modelo) + instrucción
       explícita en el prompt sobre cuándo la evidencia directa ya basta.
    3. Confirmado el fix anterior (nunca más de 2 llamadas reales por
       tool), un ticket que necesitaba varias tools distintas seguía
       cortándose en `token_budget` — el corte se comprueba en
       `react_agent.py` ANTES de cada llamada al modelo y es acumulativo
       entre turnos, así que el `token_budget` genérico (60k) podía
       agotarse antes de que el modelo llegara a su paso de "cuándo
       concluir", sin que el prompt del punto 2 tuviera ocasión de
       aplicarse. **Medido con llamadas reales al modelo (no estimado):**
       una investigación con bug directo en código cuesta ~29.6k tokens
       totales (28,506 prompt + 1,059 completion), una sin match exacto
       que fuerza patrón multi-fuente ~42.6k tokens — con precio real de
       Sonnet ($3/$15 por MTok, `claude-sonnet-4-5`), eso es **~$0.10–0.15
       por RCA completado**, frente a ~$0.21 tirados en uno que agota el
       budget sin concluir nada. Fix: `token_budget` elevado SOLO para
       prioridad P1 (`RCA_LIMITS_P1` = 12 iteraciones / 150k tokens);
       P2/P3/P4 se quedan en `DEFAULT_LIMITS` (8 iter / 60k) porque el
       coste medido cabe de sobra ahí y correrán muchas incidencias al
       día. `rca_node` resuelve el límite por `state["priority"]` cuando
       no se le pasa `limits` explícito (los tests siguen pudiendo forzar
       cualquier valor); `graph.py` no necesitó cambios. Probado
       end-to-end en Studio con un ticket P1 real (frase crítica de
       impacto + `business_process=CONTRACTING`) — `priority_reasoning`
       en el estado resultante confirma que entró por la rama P1.
  - **Ajuste de prompt (`rca-agent-prompt.md`):** distingue explícitamente
    el caso "patrón parecido pero no exacto" (mismo componente, mismo tipo
    de fallo, síntoma literal distinto) — en ese caso el agente sigue
    devolviendo `insufficient_evidence`, pero debe nombrar el patrón y su
    propia confianza en `rca_partial_findings` en vez de "no encontré
    nada".
  - **Infra:** `fastapi` añadido al grupo `dev` (dependencia transitiva no
    declarada de `langgraph-api`, sin él `langgraph dev` revienta).
  - **31 tests** (`test_react_agent.py`, `test_codebase_repo.py`,
    `test_rca_agent.py` — incluye el test que prueba que P1 y el resto
    reciben `AgentLimits` distintos sin pasar `limits` a mano —, más los
    de S2), todos en verde.
  - **"Tócalo una vez" de S3:** cubierto en la práctica — consultas RAG
    manuales (`scripts/verify_rag_loop.py`), varias ejecuciones reales
    contra Postgres/Ollama/Claude vía `langgraph dev`/Studio, y la
    medición real de tokens/coste de esta sesión (punto 3 de arriba).
  - **Diferido, NO bloqueante para haber cerrado S3:** correr el test set
    completo (`data/incidents/test/`, 30 tickets) y los edge cases
    (`data/incidents/edge_cases/`, 20) contra el pipeline real para una
    evaluación cuantitativa formal (% completed vs insufficient_evidence,
    distribución real de tokens por caso). Decisión explícita: no hace
    falta para arrancar S4 — es una tarea de evaluación que se puede
    retomar cuando convenga, no una dependencia de Solution Agent.

## Dónde estamos ahora (2026-07-29)

- **Cerradas:** S1, S2, S3. Pipeline real Intake → Priority → RCA corriendo
  end-to-end contra Postgres/Ollama/Claude vía `langgraph dev`, con RAG,
  tool use, gates de verificación y presupuesto por prioridad. 31 tests en
  verde. Nada pendiente de S1/S2/S3 bloquea seguir.
- **Sin empezar todavía:** S4 (Claude Agent SDK + subagentes → Solution
  Agent), y todo lo de después (S5 supervisor/routing, S6 HITL + Comms,
  S7 MCP/Gmail, S8 evaluación + demo).
- **Próximo paso concreto:** arrancar S4 con el bucle SDD de siempre —
  decisión de arquitectura (orquestador-worker, subagentes vs. teams,
  routing de modelo interno) → spec del Solution Agent (subagente tipo
  Corrective Developer) → revisión → Claude Code implementa.
- **Deuda abierta, no urgente:** evaluación cuantitativa del test
  set/edge cases de S3 (ver arriba) — retomar cuando convenga, no bloquea S4.

## S4 (arrancada 2026-08-03) — checkpoint de fin de sesión

**Estado: capa de arquitectura + spec ESCRITOS, sin implementar todavía.**
Próxima sesión arranca directo en revisión final del spec (o directamente en
Claude Code si no hay más cambios) — no hay que repetir la discusión de
arquitectura.

### Ajuste retroactivo a S3 (RCA Agent), hecho vía Claude Code MCP

Al discutir cómo el Solution Agent reutilizaría la evidencia del RCA, se
detectó un hueco: `similar_incidents` es autodeclarado por el modelo (sin
verificación), y no existía ningún ID estructurado para runbooks/docs
técnicos/artefactos de código citados como evidencia — solo texto libre
truncado a 300 chars en `rca_evidence`. Se implementó la opción "verificado
por código" (mismo principio que los gates de `rca_status`, no fiarse de la
autodeclaración):
- 4 campos nuevos en `IncidentState` (`state.py`): `rca_incident_source_ids`,
  `rca_technical_doc_ids`, `rca_runbook_ids`, `rca_codebase_chunk_ids`.
- `_extract_source_ids()` en `rca_agent.py`: regex sobre el texto CRUDO
  (sin truncar) de las observaciones de las 4 tools de RAG — 3 comparten
  el formato `"{i}. [{id}] distancia=..."`, `search_runbooks` usa
  `(runbook_id, categoria=...)`. Conectado en los 4 caminos de retorno de
  `rca_node` (éxito, max_iterations/token_budget, JSON no parseable,
  fallo total del modelo) para que los campos existan siempre, aunque
  vacíos.
- `similar_incidents` (autodeclarado) se deja intacto por compatibilidad —
  los nuevos campos son su contrapartida verificada, no un reemplazo.
- 2 tests nuevos en `test_rca_agent.py` (extracción con formato real de
  `rag.py`; campos presentes-pero-vacíos en el camino de corte por
  límite). **33/33 tests en verde** (31 + 2).

### Decisiones de arquitectura de S4 (cerradas)

- **Patrón real: routing determinista + worker condicional**, NO
  orquestador-worker "puro" — el camino es predecible (evidencia citada →
  verifica; si no, investiga código), no hay decisión dinámica de qué
  lanzar ni paralelismo. El router es código, no un LLM: auditable con test
  unitario sin invocar ningún modelo.
- **Router:** ¿`rca_runbook_ids` o `rca_technical_doc_ids` no vacíos? →
  Worker A (verificación). Si no → Worker B (código). Deliberadamente NO
  usa `rca_incident_source_ids` como disparador (un histórico similar no
  garantiza procedimiento reutilizable).
- **Worker A (verificación documental):** NO es agente — 1 llamada al
  modelo con `root_cause` + contenido completo del doc/runbook citado,
  opcionalmente +1 tool call de confirmación al código. Perfil `fast`
  (tarea de extracción acotada, no razonamiento causal) — decisión tomada
  con Pablo, abierta a revisión si la calidad no acompaña.
- **Worker B (investigación de código):** SÍ es agente ReAct real, hermano
  del RCA — mismo criterio ("el camino de exploración no se puede programar
  de antemano"). Presupuesto elevado en **P1+P2** (no solo P1 como RCA): el
  volumen de Worker B ya está acotado por el propio router, así que el
  argumento de "correrán muchas al día" que limitaba RCA a solo-P1 no
  aplica igual aquí. Marcado explícitamente como **hipótesis a validar con
  medición real**, no decisión cerrada.
- **`cited_source_mismatch` (caso: doc citado mismatch tras verificar) NO
  cae a Worker B** — decisión explícita con Pablo: lanzar investigación de
  código bajo la premisa "el RCA encontró algo" cuando esa premisa ya
  resultó falsa es tirar presupuesto y es un cierre en falso. Queda en su
  propio estado (no en `insufficient_evidence` genérico) porque es señal de
  calidad sobre el propio RCA, no un fallo de Solution.

### Spec escrita: `docs/specs/spec-solution-agent.md`

Sigue el mismo formato que `spec-rca-agent.md`. Contenido: router +
Worker A + Worker B (arriba), `solution_status` con 6 valores (`completed`,
`cited_source_mismatch`, `max_iterations`, `token_budget`,
`insufficient_evidence`, `model_error`) como `Literal` real (mismo patrón
que `RcaStatus`), tabla de inputs/outputs, nota de gobernanza, y entregable
esperado de Claude Code.

**Gap detectado al escribir la spec, no implementado todavía:** Worker A
necesita releer el documento EXACTO citado por el RCA sin repetir una
búsqueda semántica (que podría devolver un top-k distinto). `rag.py` solo
tiene búsqueda semántica hoy — faltan `get_runbook_by_id(runbook_id)` y
`get_technical_doc_by_id(doc_id)` (lookup directo, sin embedding). Recogido
en el "Entregable esperado" de la spec, punto 2.

**Abierto explícitamente en la spec (no decidido a ciegas):**
1. Perfil de Worker A (`fast` vs `smart`) — sin medición real todavía.
2. Valores exactos de `SOLUTION_LIMITS_ELEVATED` (P1+P2) — a medir con
   llamadas reales, mismo método que `RCA_LIMITS_P1` en S3.

### Próximo paso concreto

Repasar `docs/specs/spec-solution-agent.md` línea a línea con Pablo (quedó a
medio revisar — se validó el perfil de Worker A pero no el resto línea por
línea) y, si no hay más cambios, dirigir a Claude Code para implementar:
`state.py` (`SolutionStatus` + 4 campos nuevos) → `rag.py` (2 funciones de
lookup) → `solution_agent.py` (router + Worker A + Worker B + `solution_node`)
→ conectar en `graph.py` → tests unitarios con dobles deterministas (mismo
mecanismo que `test_rca_agent.py`).
