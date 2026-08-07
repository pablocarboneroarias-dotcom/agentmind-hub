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

## S4 — Solution Agent implementado (2026-08-06) — ver cierre 2026-08-07 abajo

Implementación completa vía Claude Code MCP, siguiendo `spec-solution-agent.md`
al pie de la letra. **46/46 tests en verde** (33 anteriores + 13 nuevos).

- **`state.py`:** `SolutionStatus` (`Literal` de 6 valores) + `SOLUTION_STATUSES`
  (mismo patrón que `RcaStatus`) + 4 campos nuevos: `solution_status`,
  `solution_confidence`, `solution_source`, `solution_evidence`.
  `proposed_solution`/`action_plan` ya existían desde S1.
- **`rag.py`:** `get_runbook_by_id()` y `get_technical_doc_by_id()` — lookup
  directo por ID, sin búsqueda semántica ni truncado (a diferencia de las 4
  funciones de S3), para que Worker A relea el documento EXACTO citado por
  el RCA sin repetir retrieval.
- **`solution_agent.py`** (nuevo):
  - `_route(state)`: función de código pura (sin invocar modelo) — Worker A
    si `rca_runbook_ids`/`rca_technical_doc_ids` no vacíos, Worker B si no.
    Deliberadamente ignora `rca_incident_source_ids` como disparador.
  - **Worker A** (`_worker_a`): NO es agente ReAct — 1 llamada al modelo
    (perfil `fast`) con como mucho 1 tool call de verificación
    (`read_codebase_repo`) adicional. `_resolve_cited_source` decide qué
    fuente verificar si el RCA citó varias: prioriza el primer runbook
    sobre el primer doc técnico (decisión de implementación, no en la
    spec — documentada en el código como candidata a revisar si el RCA
    cita múltiples fuentes a menudo).
  - **Worker B** (`_worker_b`): agente ReAct real sobre `react_agent.py`,
    hermano del RCA, con 3 tools read-only (`search_codebase`,
    `read_codebase_repo`, `query_incident_history`). Presupuesto elevado
    (`SOLUTION_LIMITS_ELEVATED`) en P1+P2 (no solo P1 como RCA) — valores
    NUMÉRICOS SIN MEDIR TODAVÍA, reutilizan los de `RCA_LIMITS_P1` como
    punto de partida; marcado explícito en código como hipótesis pendiente
    de medición real (mismo método que se usó para fijar `RCA_LIMITS_P1`
    en S3).
  - `solution_node`: enruta, despacha al worker, nunca revienta el grafo
    (`model_error` en el `except` general), `_finalize` verifica en runtime
    contra `SOLUTION_STATUSES`.
  - Dos prompts nuevos en `docs/specs/`: `solution-worker-a-prompt.md`
    (verificación) y `solution-worker-b-prompt.md` (investigación de
    código), mismo estilo que `rca-agent-prompt.md`.
- **`graph.py`:** `rca -> solution -> END` (sustituye el `END` directo tras
  `rca`); confirmado con `build_graph()` + inspección de nodos/aristas
  (`rca -> solution`, `solution -> __end__`), sin tocar `intake`/`priority`/`rca`.
- **13 tests nuevos** en `test_solution_agent.py`: router (4, sin invocar
  modelo), Worker A completed/cited_source_mismatch/con 1 tool call de
  verificación (3), Worker B completed/insufficient_evidence/max_iterations
  (3), P1+P2 vs P3+P4 presupuesto (1), model_error en ambos workers (2).
- **Aún NO probado contra `langgraph dev`/modelo real** — a diferencia del
  RCA (S3), que se validó con `langgraph dev` y encontró 3 bugs reales
  antes de cerrar. Esto es una diferencia deliberada de alcance de esta
  sesión (implementación + tests con dobles), no un cierre completo al
  mismo nivel de rigor que S3. **Pendiente antes de dar S4 por
  verdaderamente cerrado** (paralelo al "tócalo una vez"/validación real
  que sí se hizo en S3):
  1. Correr contra `langgraph dev`/Studio con al menos un ticket real por
     cada camino (Worker A completed, Worker A mismatch, Worker B
     completed/insufficient) para confirmar que el modelo real respeta el
     formato JSON pedido en los prompts.
  2. Medir tokens/coste reales de Worker B para confirmar o ajustar
     `SOLUTION_LIMITS_ELEVATED` (hoy son un placeholder, no una medición).
  3. Confirmar si el perfil `fast` da resultados de calidad suficiente en
     Worker A, o si hace falta subir a `smart` (spec ya lo dejó abierto).

### Próximo paso concreto (actualizado)

Antes de dar S4 por cerrado del todo: validar contra `langgraph dev` con
casos reales (los 3 puntos de arriba). Si el resultado obliga a ajustar algo
del spec/código, se hace y se cierra S4 con el mismo rigor que S3. Si todo
se comporta como se espera, se cierra formalmente y se pasa a S5
(orquestación: supervisor + routing condicional + retorno).

---

## S4 — CERRADO (2026-08-07) — validación real contra `langgraph dev`/modelo real

Sesión dedicada íntegramente a "tócalo una vez": los 3 puntos que quedaron
pendientes el 2026-08-06 (arriba) se han cubierto con **7 ejecuciones reales**
del pipeline (modelo real vía `models.complete`, Postgres/pgvector reales,
sin dobles de test), la mayoría vía `langgraph dev`/Studio y las últimas dos
invocando `build_graph().invoke()`/`solution_node()` directamente desde
script cuando Studio exigió login de LangSmith que no correspondía dar por
el agente. Mismo rigor que se aplicó a RCA en S3, que también encontró bugs
reales en esta fase.

### Caminos confirmados con modelo real

| Camino | Confirmado | Incidencia(s) |
|---|---|---|
| RCA `completed` | ✓ | INC-2026-0806-A, INC-2026-0807-E, INC-2026-0807-G |
| RCA sin conclusión (`token_budget`) → revisión humana | ✓ | INC-2026-0806-B, INC-2026-0806-D |
| Worker A → `cited_source_mismatch` (con hallazgo de código remarcado) | ✓ | INC-2026-0806-A, INC-2026-0807-E, INC-2026-0807-F |
| Worker A → `completed` (resolución 100% autónoma, `needs_human_review=false`) | ✓ | INC-2026-0807-G |
| Worker B → `completed` | ✓ | Prueba dirigida (`solution_node` a mano, root_cause real de INC-2026-0807-F, sin fuente citada) |
| Resumen de cierre forzado de RCA (`_forced_wrapup`) | ✓ | INC-2026-0806-B, INC-2026-0806-D |

**No cubierto, aceptado como deuda menor (no bloquea el cierre):** Worker B
en sus caminos `insufficient_evidence`/`max_iterations`/`token_budget`, y
Worker A en su variante `model_error`. Ambos ya están cubiertos por tests
unitarios con dobles (`test_solution_agent.py`); falta la confirmación
contra modelo real, igual que quedaron algunos caminos de RCA sin tocar en
S3 sin que eso bloqueara su cierre.

### Bugs reales encontrados y corregidos en esta sesión

1. **Worker A perdía hallazgos de código en `cited_source_mismatch`**
   (INC-2026-0806-A): su propia tool call de verificación encontró el fix
   real en código, pero el prompt no le exigía remarcarlo — dependía de que
   el modelo lo narrara por iniciativa propia. Corregido en
   `solution-worker-a-prompt.md` (commit `52a3f48`): ahora es instrucción
   explícita, sin tocar `solution_status`/`action_plan`/`needs_human_review`.
2. **`rca_partial_findings` era un fragmento sin curar en `token_budget`/
   `max_iterations`** (INC-2026-0806-B): `react_agent.py` corta en seco sin
   dar oportunidad al modelo de resumir. Corregido con `_forced_wrapup()` en
   `rca_agent.py` (commit `52a3f48`): una llamada extra acotada (sin tools)
   que pide un resumen estructurado con cualquier hipótesis marcada
   explícitamente como SIN CONFIRMAR.
3. **Bug de routing (el más serio):** `graph.py` conectaba `rca -> solution`
   con arista fija, arrastrada de cuando Solution no existía. Un RCA que
   fallaba por `token_budget`/`max_iterations` llegaba igualmente a Solution
   con `root_cause` vacío, porque `rca_runbook_ids`/`rca_technical_doc_ids`
   no se vacían solo por fallar (se extraen de cualquier resultado de
   búsqueda visto, citado o no) — el router de Solution se dejaba engañar y
   gastaba una llamada al modelo (Worker A) sin poder aportar nada.
   Encontrado corriendo INC-2026-0806-B/D reales. Corregido con
   `route_after_rca()` (mismo patrón que `route_after_priority`, mira
   `needs_human_review`) — commit `1b6fee5`.

### Hallazgo de diseño, documentado sin abrir acción (no es deuda, es una observación)

**Worker B es estructuralmente raro de alcanzar por el pipeline orgánico en
este corpus.** 4 de 4 intentos reales con tickets distintos (INC-2026-0806-A,
0807-E, 0807-F, 0807-G) aterrizaron en Worker A, nunca en Worker B. Motivo:
los 5 ficheros reales de `codebase-toy-repo/` tienen cada uno su ficha
técnica correspondiente indexada (`DOC-001/002/003/006/010`), así que
cualquier RCA que confirme una causa leyendo código real casi siempre topa
también con un doc relacionado al buscar — y el router, tal como está
diseñado a propósito (spec: "si RCA ya citó una fuente estructurada, hay que
verificarla"), prefiere Worker A siempre que exista algo citable. No se
investigó si esto es solo una propiedad de este corpus sintético
(documentación completa) o si se repetiría en datos reales con cobertura
documental más desigual — **candidato a revisar con datos de producción
reales, no con más tickets sintéticos.**

### Medición de coste (parcial, primer dato real — no exhaustivo)

Worker B, en su única ejecución real, resolvió en 3 iteraciones/3 tool calls
— muy por debajo de `SOLUTION_LIMITS_ELEVATED` (12 iter/150k tokens). Un solo
dato no basta para confirmar o ajustar el límite (mismo criterio que ya se
aplicó a `RCA_LIMITS_P1` en S3: hace falta más volumen antes de tocar el
número), pero es evidencia de que el orden de magnitud no está disparatado.

### Commits de esta sesión

- `52a3f48` — Worker A (remarcar hallazgo de código) + RCA (`_forced_wrapup`).
- `ac536de` — ignora `.claude/` (config local, no del proyecto).
- `1b6fee5` — `route_after_rca` (el bug de routing más serio de los tres).

### Próximo paso concreto (actualizado)

S4 cerrado. Empezar S5 (orquestación: supervisor + routing condicional +
retorno) en la próxima sesión.
