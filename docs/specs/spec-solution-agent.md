# Spec — Solution Agent

**Semana:** S4
**Tipo:** Router (código) + 2 workers de naturaleza distinta
**Patrón:** Routing determinista + worker condicional — afinado desde
orquestador-worker "puro" tras la discusión de arquitectura de S4: el camino
es predecible (evidencia citada → verifica; si no, investiga código), no hay
paralelismo ni decisión dinámica de qué lanzar. El router es código, no un
agente — ver "Por qué no es un agente el router" más abajo.
**Perfiles de modelo:** Worker A (verificación) → `fast` (tarea de extracción
acotada, no razonamiento causal); Worker B (código) → `smart` (mismo criterio
que RCA: exploración + juicio real). **Abierto a revisión** — sin medición
real de calidad todavía; si `fast` da resultados pobres en la verificación,
se sube a `smart` sin tocar la arquitectura.

---

## Qué hace

Recibe el `IncidentState` con RCA ya cerrado (`root_cause` +
`rca_incident_source_ids`/`rca_technical_doc_ids`/`rca_runbook_ids`/
`rca_codebase_chunk_ids` verificados por código, no autodeclarados — ver
ajuste de S3 en `CONTEXTO.md`) y propone una solución (`proposed_solution`,
`action_plan`). **Nunca escribe en Salesforce ni en el repo de código —
propone, no implementa.**

## Por qué no es un agente el router

A diferencia de RCA (donde el orden de consulta de fuentes no se puede
programar porque no se sabe de antemano qué hace falta), aquí el camino ES
predecible: si el RCA ya citó una fuente estructurada, hay que verificarla;
si no citó ninguna, hay que investigar código. No hay ambigüedad que
justifique que un LLM decida el routing — decidirlo con código es más
barato, más rápido, y más auditable (se puede probar con un test unitario
sin invocar ningún modelo). El juicio real (extraer/adaptar la solución,
investigar el código) vive dentro de cada worker, no en el router.

## Router — lógica exacta

```
¿rca_runbook_ids o rca_technical_doc_ids no vacíos?
  SÍ → Worker A (verificación documental)
  NO → Worker B (investigación de código)
```

Deliberadamente NO se usa `rca_incident_source_ids` (histórico de
incidencias) como disparador de Worker A: un incidente pasado parecido no
trae necesariamente una solución reutilizable (puede que se resolviera sin
dejar procedimiento documentado), a diferencia de un runbook o doc técnico,
que por definición SÍ documentan procedimiento. Si en la evaluación de S4 se
ve que esto deja casos sin cubrir, se revisa — no se abre ahora sin
evidencia.

---

## Worker A — verificación documental

**No es un agente ReAct.** Es una única llamada al modelo con el
`root_cause` del RCA y el contenido COMPLETO del runbook/doc citado como
contexto — no hace falta que explore nada, ya sabe exactamente qué mirar. Si
el doc citado no basta para confirmar aplicabilidad, opcionalmente hace
**como mucho 1** tool call de verificación al código (`read_codebase_repo`,
si `rca_codebase_chunk_ids` trae una ruta útil) — nunca una investigación
abierta.

**Requiere una tool nueva que hoy no existe:** las 4 funciones de RAG
(`rag.py`) solo hacen búsqueda semántica (`search_runbooks`,
`search_technical_docs`, ...), no lectura directa por ID. Repetir la
búsqueda para releer el doc citado es redundante (ya se sabe el ID exacto,
buscar de nuevo puede incluso devolver un top-k distinto) y gasta una
llamada a embeddings sin necesidad. **Se necesita:**
- `get_runbook_by_id(runbook_id) -> str` — mismo patrón de reconstrucción
  por pasos que ya usa `search_runbooks` internamente (query relacional por
  `runbook_id` ordenada por `step_number`), pero sin el paso de embedding.
- `get_technical_doc_by_id(doc_id) -> str` — lookup directo en
  `technical_docs` por `doc_id`.

Ambas en `rag.py`, mismo estilo que las 4 existentes (nunca lanzan
excepción, devuelven texto legible en caso de error).

**Salida del worker:** el modelo responde en JSON con `solution_status`
(`"completed"` o `"cited_source_mismatch"`), `proposed_solution`,
`action_plan` (lista de pasos), y `solution_confidence` (0-100, mismo
criterio que `rca_confidence`).

---

## Worker B — investigación de código

**Es un agente ReAct real**, montado sobre `react_agent.py`, hermano
arquitectónico del RCA Agent — mismo criterio de "por qué es agente": el
camino de exploración no se puede programar de antemano. Herramientas
read-only: `search_codebase`, `read_codebase_repo`, y
`query_incident_history` (para ver si algún incidente pasado, aunque no
citado como fuente estructurada por el RCA, sugiere una solución aplicable
al mismo componente).

**Solo se activa cuando ya no hay evidencia documental citada** — es decir,
ya es un subconjunto acotado del tráfico total por diseño del router (a
diferencia del RCA, que corre en el 100% de las incidencias). Esto cambia el
cálculo de presupuesto respecto a RCA:

- **P1 y P2:** `SOLUTION_LIMITS_ELEVATED` — presupuesto elevado (valores
  exactos a medir con llamadas reales, mismo método que
  `RCA_LIMITS_P1` en S3 — no se fijan a ciegas).
- **P3 y P4:** `DEFAULT_LIMITS` — si no encuentra solución rápido, cae a
  revisión humana; no hay urgencia que justifique presupuesto extra.

**Hipótesis a validar, no decisión cerrada:** el corte P1+P2 vs. P3+P4 (en
vez de solo P1, como hace RCA) se basa en que el volumen de Worker B ya está
acotado por el propio router — falta medir tokens/coste reales de este
worker en concreto antes de confirmarlo, igual que se hizo con RCA en S3.

Reutiliza `max_calls_per_tool` de `react_agent.py` (mismo problema
potencial que en RCA: seguir "verificando" tras encontrar evidencia
suficiente).

---

## solution_status — 6 valores

Mismo principio que `rca_status`: `Literal` real en `state.py`
(`SolutionStatus`), con `SOLUTION_STATUSES` derivado vía `get_args` y
verificación en runtime antes de cada retorno del nodo — no un 7º valor
colándose sin documentar.

| `solution_status` | Quién lo decide | Significado | Implica |
|---|---|---|---|
| `completed` | Worker A o B (tras sus propios gates) | Solución propuesta con evidencia suficiente | Sigue a Comms (S6) |
| `cited_source_mismatch` | Worker A | El doc/runbook citado por el RCA no aplica a esta causa raíz | **No cae a Worker B** (ver más abajo) — `needs_human_review = true`, y es señal de calidad sobre el propio RCA, no del Solution Agent |
| `max_iterations` | `react_agent.py` (harness, solo Worker B) | Se agotaron las iteraciones sin conclusión | Falta presupuesto en Worker B |
| `token_budget` | `react_agent.py` (harness, solo Worker B) | Se agotó el presupuesto de tokens sin conclusión | Ídem — recursos, no datos |
| `insufficient_evidence` | Worker B | Investigó el código y no encontró solución aplicable | Problema de **cobertura**: la causa raíz no tiene arreglo evidente en el repo consultado |
| `model_error` | `solution_node` (captura de excepción, cualquier worker) | Fallo total del modelo/proveedor | Infraestructura, no datos |

En los 5 casos que no son `completed`, `needs_human_review = true`.

### Por qué `cited_source_mismatch` NO cae a Worker B (decisión ya tomada con Pablo)

Lanzar Worker B tras un mismatch asumiría, sin base real, que el problema
es "no exploré bastante" — pero la premisa de partida (RCA encontró una
fuente aplicable) ya resultó falsa al verificarla. Investigar código bajo
esa premisa rota es tirar presupuesto persiguiendo un caso que la propia
cadena ya marcó como sospechoso, y además sería un cierre en falso: si
Worker B encontrara "algo", no se sabría si es la solución real o una
coincidencia forzada por haber buscado con la premisa equivocada. Se queda
en su propio estado (`cited_source_mismatch`), no en `insufficient_evidence`
genérico, para que sea auditable como lo que es: una discrepancia entre lo
que el RCA creyó citar y lo que el documento dice de verdad — útil para la
deuda de evaluación cuantitativa pendiente de S3 (¿el gate de confianza ≥80
se está quedando corto en algún patrón de falsos positivos de citación?).

---

## Inputs (de `IncidentState`, ya rellenados por RCA)

| Campo | Origen | Uso en Solution |
|---|---|---|
| `root_cause`, `rca_confidence`, `rca_partial_findings` | RCA | Base de la propuesta de solución |
| `rca_runbook_ids`, `rca_technical_doc_ids` | RCA (extraídos por código, S3) | Disparan el router a Worker A si no están vacíos |
| `rca_codebase_chunk_ids` | RCA (extraído por código, S3) | Pista de ruta de fichero para el `read_codebase_repo` opcional de Worker A |
| `category`, `system`, `business_process`, `affected_objects` | Intake | Contexto para Worker B si tiene que explorar código |
| `priority` | Priority | Determina el presupuesto de Worker B (`SOLUTION_LIMITS_ELEVATED` vs. `DEFAULT_LIMITS`) |

**Importante:** si `rca_status != "completed"`, el ticket no debería llegar
a Solution — se enruta a revisión humana desde antes (mismo principio que
RCA no recibe tickets sin clasificar de Intake/Priority). No es
responsabilidad de Solution repetir esa validación, pero sí de `graph.py`.

---

## Outputs (escritos en `IncidentState`)

| Campo | Tipo | Descripción |
|---|---|---|
| `proposed_solution` | `str` | Ya existía en `state.py` (S1) — la solución propuesta (vacío si no `completed`) |
| `action_plan` | `list[str]` | Ya existía en `state.py` (S1) — pasos concretos (vacío si no `completed`) |
| `solution_status` | `str` | Uno de los 6 valores de la tabla de arriba *(campo nuevo)* |
| `solution_confidence` | `float` (0-100) | Confianza del worker que resolvió *(campo nuevo)* |
| `solution_source` | `str` | `"cited_document"` \| `"code_investigation"` \| `""` — qué worker resolvió *(campo nuevo, trazabilidad de qué camino tomó el router)* |
| `solution_evidence` | `list[str]` | Traza de tool calls (Worker B) o del doc verificado (Worker A) *(campo nuevo, mismo espíritu que `rca_evidence`)* |
| `needs_human_review` | `bool` | `true` en los 5 casos que no son `completed` (ya existe en `state.py`) |

---

## Nota de gobernanza

- **Propone, no implementa.** Ningún worker escribe en Salesforce ni en el
  repo de código — mismo principio read-only que RCA.
- **`cited_source_mismatch` es una señal de calidad sobre el RCA, no solo un
  fallo de Solution.** Debería alimentar la evaluación cuantitativa
  pendiente de S3 (deuda ya registrada en `CONTEXTO.md`).
- **El router es auditable sin invocar ningún modelo** — es una condición
  sobre campos ya estructurados y verificados por código en S3, no una
  decisión de un LLM.
- **Worker A reutiliza evidencia, no la reinventa** — lee el documento
  citado exacto, no vuelve a hacer retrieval semántico sobre él.

---

## Lo que Solution no decide (explícito para evitar scope creep)

| Decisión | Quién la toma |
|---|---|
| Causa raíz | RCA Agent (S3) |
| Si el ticket llega a Solution o se desvía a revisión humana | `graph.py` / Priority |
| Comunicación al equipo técnico | Comms Agent + gate HITL (S6) |
| Implementación real de la solución propuesta | Ningún agente de este pipeline — el equipo técnico humano |

---

## Entregable esperado de Claude Code

1. `state.py`: `SolutionStatus` (`Literal` de 6 valores) + `SOLUTION_STATUSES`
   (vía `get_args`, mismo patrón que `RcaStatus`) + los 4 campos nuevos de la
   tabla de outputs.
2. `rag.py`: `get_runbook_by_id(runbook_id)` y
   `get_technical_doc_by_id(doc_id)` — lookup directo, sin embedding.
3. `solution_agent.py`:
   - `_route(state) -> Literal["worker_a", "worker_b"]`: función de código
     pura, testeable sin invocar ningún modelo.
   - Worker A: una función que arma el prompt con `root_cause` + contenido
     del doc/runbook citado, llama al modelo (perfil `fast`), parsea el JSON
     de salida, y opcionalmente hace 1 `read_codebase_repo` si hace falta
     verificar contra código.
   - Worker B: `ReActAgent` igual que `rca_node`, con `SOLUTION_LIMITS_ELEVATED`
     para P1/P2 y `DEFAULT_LIMITS` para P3/P4 (resuelto por `state["priority"]`,
     igual que `rca_node` con `RCA_LIMITS_P1`).
   - `solution_node`: orquesta router → worker → mapea resultado a
     `solution_status` + campos de salida, con `_finalize()` verificando en
     runtime contra `SOLUTION_STATUSES` (mismo patrón que RCA).
   - Nunca revienta el grafo: fallo total del modelo → `model_error`.
4. Conectar en `graph.py`: `priority/rca -> solution -> END` (sustituye el
   `END` actual tras `rca`), sin tocar `intake`/`priority`/`rca`.
5. Tests unitarios con dobles deterministas (mismo mecanismo que
   `test_rca_agent.py`, monkeypatch de `run_tool`/`complete_fn`), cubriendo
   al menos:
   - Router: ambas ramas, sin invocar ningún modelo.
   - Worker A: `completed` y `cited_source_mismatch`.
   - Worker B: `completed`, `insufficient_evidence`, `max_iterations`,
     `token_budget`.
   - P1/P2 reciben `SOLUTION_LIMITS_ELEVADO`, P3/P4 reciben `DEFAULT_LIMITS`
     (mismo patrón que el test de S3 para `RCA_LIMITS_P1`).
   - `model_error` en ambos workers.
