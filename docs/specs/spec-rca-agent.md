# Spec — RCA Agent

**Semana:** S3
**Tipo:** Agente (ReAct, autónomo)
**Patrón:** Bucle Razonar + Actuar sobre `react_agent.py` (Fase 1), con 5 tools de solo-lectura
**Perfil de modelo:** `smart` (razonamiento causal real, no clasificación mecánica)

---

## Qué hace

Busca la causa raíz (`root_cause`) de una incidencia ya clasificada por
Intake y priorizada por Priority, consultando el corpus RAG (histórico de
incidencias, documentación técnica, runbooks, artefactos de código
sintéticos) y, si hace falta, el código real del repo de juguete. **Nunca
escribe en Salesforce ni en ningún sistema — read-only siempre.**

## Por qué es agente, no workflow

A diferencia de Intake/Priority (camino siempre igual), el orden en que RCA
consulta sus fuentes NO se programa como flujo rígido: el propio bucle ReAct
decide, en cada iteración, si tiene evidencia suficiente para concluir o si
necesita otra tool — y cuál. El principio de negocio (validado con Pablo en
`rca-decisiones-s3.md`): un RCA real, si no encuentra el error en la base de
conocimiento, se va al código, igual que haría un humano. Atarle el camino a
un `if/else` rompería justo esa autonomía.

## Reutiliza `react_agent.py` (Fase 1)

El bucle ReAct de producción ya existe y aporta sus tres caminos de parada
sin tocarlos:
- **Tope de iteraciones** (`max_iterations`, vía `AgentLimits`).
- **Presupuesto de tokens** (`token_budget`, comprobado antes de cada llamada).
- **Camino feliz:** el modelo deja de pedir tools → `final_answer`.

RCA añade lógica de estado propia ENCIMA de estos tres caminos (ver
`rca_status` más abajo), porque lo que pasa después de que RCA pare depende
de *por qué* paró — algo que en Fase 1 no importaba.

**Cambio necesario en `react_agent.py`:** `ReActAgent` no aceptaba
`complete_fn` inyectable (llamaba a `complete` importado directamente), así
que sus tests solo podían monkeypatchear el módulo. Se añade un parámetro
`complete_fn` opcional (por defecto `None`, cae al `complete` del módulo si
no se pasa) — **no rompe los tests existentes de `test_react_agent.py`** (el
monkeypatch de `ra.complete` sigue funcionando exactamente igual) y permite
inyectar un doble determinista en `rca_node`, igual que ya hacen
`intake_node`/`priority_node`.

**Segundo cambio, tras un caso real en producción:** el modelo, tras leer
el fichero correcto y encontrar un comentario de bug explícito (evidencia
directa suficiente), siguió "verificando" con más llamadas a la misma tool
buscando confirmar algo que ninguna tool de este corpus podía darle (schema
de un objeto custom), hasta agotar el presupuesto de tokens. Se añade
`max_calls_per_tool` a `ReActAgent` (opcional, `None` por defecto — sin
tope, comportamiento de Fase 1 intacto): un tope DURO por nombre de tool,
verificado por código, no por criterio del modelo. `rca_node` lo fija en
`MAX_CALLS_PER_TOOL = 2` (1 llamada + como mucho 1 de refuerzo); superarlo
no ejecuta la tool de verdad, devuelve un aviso como observación. Se
complementa (no sustituye) con una instrucción explícita en
`rca-agent-prompt.md`: un comentario de bug en el código real ya es
evidencia `single_source` suficiente, y no existe ninguna tool de inspección
de schema/metadata más allá de lo ya consultado — el tope de código es la
red de seguridad, el prompt es lo que evita llegar a necesitarla.

---

## Caja de herramientas — 5 tools, todas read-only

```
RCA Agent (ReAct, perfil smart)
├── Tool 1: query_incident_history   (RAG — histórico de incidencias resueltas)
├── Tool 2: search_technical_docs     (RAG — docs técnicas + triggers/flows indexados)
├── Tool 3: search_runbooks           (RAG — guías de diagnóstico paso a paso)
├── Tool 4: search_codebase           (RAG — artefactos de código sintéticos)
└── Tool 5: read_codebase_repo        (lectura EXACTA del repo de juguete, no semántica)
```

Tools 1-4 viven en `rag.py`, ya indexadas en pgvector (S3, corpus RAG). Tool
5 vive en `codebase_repo.py`, ya implementada (read-only estricto,
anti-path-traversal, límite de 50KB). Ninguna de las 5 escribe nada.

El orden de consulta lo decide el bucle ReAct, no un `if/else` — ver "Por
qué es agente" arriba.

---

## Inputs (de `IncidentState`, ya rellenados por Intake + Priority)

| Campo | Origen | Uso en RCA |
|---|---|---|
| `title`, `description`, `error_messages` | Ticket original | Texto base de la investigación |
| `category`, `system`, `business_process` | Intake | Contexto para elegir qué RAG consultar primero |
| `affected_objects` | Intake | Pistas de objetos Salesforce involucrados |
| `severity` (vía `priority`), `impact_level`, `urgency_level` | Priority | Contexto de gravedad, no cambia el criterio de investigación |

**Importante:** RCA no re-clasifica ni repriotiza. Si Intake/Priority
marcaron `needs_human_review`/`needs_clarification`, ese caso no debería
llegar a RCA (lo enruta `route_after_priority` a `human_review`) — RCA
asume que category/system/business_process ya son de fiar.

---

## Condición de parada — "evidencia suficiente" (CERRADO en `rca-decisiones-s3.md`)

**Por qué no "2 fuentes que corroboren" como requisito duro:** rompe el
caso legítimo de una incidencia nueva sin precedente en el histórico, donde
solo el código explica la causa — exigir 2 fuentes fuerza
`insufficient_evidence` sobre una causa raíz correctamente encontrada.

Diseño final (estructura + juicio del modelo):

1. **Requisito estructural duro** (lo verifica `rca_node`, no el modelo):
   antes de aceptar `rca_status: "completed"`, el nodo cuenta cuántas tool
   calls distintas aparecen en el transcript. **Si son menos de 2, el nodo
   fuerza `rca_status: "insufficient_evidence"`** aunque el modelo haya
   declarado `completed` — no basta con "no haberse saltado nada por
   pereza" en la intención del modelo, tiene que ser verificable en el
   registro de llamadas. *(Nota: `rca-decisiones-s3.md` deja el conteo
   exacto sin cerrar — "verificable objetivamente contando tool calls
   registradas" — el umbral de 2 es una decisión de implementación de este
   spec, ajustable si Pablo prefiere otro número.)*
2. **Metadato de solidez** (no bloqueante, informativo): `rca_corroboration:
   "multi_source" | "single_source"` — lo decide el modelo, coherente con
   cuántas fuentes distintas corroboran la MISMA causa (no cuántas consultó).
3. **Confianza del modelo** (juicio, tras pasar el paso 1): escala **0-100**
   (no 0-1 — nota de reconciliación: el campo `rca_confidence` ya existía en
   `state.py` desde S1 con comentario "0-1"; se actualiza a 0-100 para
   cuadrar con el umbral que cierra `rca-decisiones-s3.md`). Umbral de corte:
   **80**. Por debajo, aunque el modelo declare `completed`, el nodo lo
   degrada a `insufficient_evidence` (mismo razonamiento que el requisito
   estructural: una autodeclaración de confianza no verificada no basta).

**Caso intermedio, añadido tras un caso real en producción (no cambia el
enum, refina qué va en `rca_partial_findings`):** una incidencia nueva cuyo
síntoma exacto no coincide con ningún histórico ni con el código real es
esperable, no un fallo de búsqueda — el corpus sintético tiene un único bug
canónico por arquetipo en `codebase-toy-repo/` pero variaciones
independientes en `incident_history`/`test`/`edge_cases`, así que el detalle
literal (método, línea) a menudo no va a coincidir en ningún sitio. Cuando
el agente encuentra el MISMO componente con un problema de la MISMA
naturaleza técnica (no solo la misma categoría/objeto) pero no el síntoma
exacto, sigue siendo `insufficient_evidence` (no hay causa confirmada) —
pero `rca_partial_findings` debe nombrar el patrón, su procedencia, y la
confianza del propio modelo en que ese patrón sea relevante, en vez de un
genérico "no encontré nada". Ver `rca-agent-prompt.md`, sección "Cuándo
concluir", con el ejemplo exacto de redacción esperada. El parecido tiene
que ser real (mismo componente + mismo mecanismo de fallo) — una conexión
superficial no cuenta y el prompt lo dice así de explícito.

## rca_status — 5 valores (CERRADO, `Literal` real en `state.RcaStatus`)

Cerrado de verdad, no solo documentado: `state.py` define
`RcaStatus = Literal["completed", "max_iterations", "token_budget",
"insufficient_evidence", "model_error"]` y `RCA_STATUSES` (el mismo conjunto,
derivado con `typing.get_args`, no duplicado a mano). `rca_agent.py` afirma
en runtime, en cada punto de retorno (`_finalize()`), que el valor final
pertenece a ese conjunto — un typo o un 6º valor no documentado revienta con
`AssertionError` explícito en vez de colarse en silencio.

| `rca_status` | Quién lo decide | Significado | Implica |
|---|---|---|---|
| `completed` | Modelo (tras pasar los gates 1 y 3 de arriba) | Causa raíz con evidencia suficiente | Sigue a Solution (S4, aún no existe) |
| `max_iterations` | `react_agent.py` (harness) | Se agotaron las iteraciones sin conclusión | Falta presupuesto — subir límite o cambiar perfil |
| `token_budget` | `react_agent.py` (harness) | Se agotó el presupuesto de tokens sin conclusión | Ídem — problema de recursos, no de datos |
| `insufficient_evidence` | Modelo, o `rca_node` si degrada por los gates 1/3 | Tuvo recursos pero no halló evidencia (o no la verificó) | Problema de **datos**: falta contenido indexado |
| `model_error` *(añadido, ver nota abajo)* | `rca_node` (captura de excepción) | Fallo total de `complete_fn` (reintentos agotados) | Problema de **infraestructura**, no de datos ni de recursos del agente |

En los cuatro casos que no son `completed` (incluido `model_error`, ver nota
abajo), `needs_human_review = true`.

**Resumen de cierre forzado en `max_iterations`/`token_budget` (añadido tras
validación real de S4, ver checkpoint de `CONTEXTO.md`):** `react_agent.py`
corta en seco estos dos caminos — `answer=None`, sin darle al modelo ninguna
oportunidad de cerrar su razonamiento. Sin corrección, `rca_partial_findings`
quedaba en lo último que el modelo hubiera dicho en su turno anterior
(`_last_assistant_text`): un fragmento de pensamiento a medias, a veces
vacío, según en qué punto del bucle se cortara — nada garantizaba que fuera
útil para quien hace la revisión humana. `rca_node` ahora hace **una llamada
extra, acotada y sin tools** (`_forced_wrapup`) pidiendo un resumen en texto
plano de la evidencia real encontrada y, si la hay, una hipótesis explícita
marcada como SIN CONFIRMAR. No cambia el contrato: `rca_status` sigue siendo
`max_iterations`/`token_budget`, `root_cause` sigue vacío, no se acepta como
conclusión — solo mejora la calidad de un campo que ya existía.

**`model_error` — 5º valor, decisión tomada al implementar (no viene de
`rca-decisiones-s3.md`, que cierra solo 4):** para cuando `complete_fn` agota
sus reintentos por un fallo total del modelo/proveedor — no hubo
investigación real, es un fallo de infraestructura, distinto de
`insufficient_evidence` (que implica que SÍ se investigó y aun así no hubo
evidencia). Se evaluó la alternativa de reconducirlo a `insufficient_evidence`
sin 5º valor, pero se descartó: mandaría una señal engañosa a quien consuma
`rca_status` después (ej. un reintento automático que interprete
`insufficient_evidence` como "falta corpus" cuando el problema real fue que
la API del modelo estaba caída). `rca_node` nunca deja que esto reviente el
grafo: lo captura y devuelve este estado degradado. No es uno de los 4 tests
que pide el "Entregable esperado" más abajo — es manejo defensivo, no un
camino que el criterio de suficiencia decida.

---

## Outputs (escritos en `IncidentState`)

| Campo | Tipo | Descripción |
|---|---|---|
| `root_cause` | `str` | Causa raíz (vacío si no es `completed`) |
| `rca_confidence` | `float` (0-100) | Confianza del modelo (0.0 si no es `completed`) |
| `rca_status` | `str` | Uno de los 4 valores de la tabla de arriba |
| `rca_corroboration` | `str` | `"multi_source"` \| `"single_source"` \| `""` (vacío si no es `completed`) |
| `rca_evidence` | `list[str]` | Traza de qué tool se llamó con qué resultado (auditoría) |
| `rca_partial_findings` | `str` | Resumen de la investigación — siempre relleno, incluso en `completed` |
| `rca_iterations_used` | `int` | Iteraciones del bucle ReAct consumidas |
| `similar_incidents` | `list[str]` | IDs de `incident_history` citados como evidencia (vacío si no aplica) |
| `needs_human_review` | `bool` | `true` en los 4 casos que no son `completed` |

---

## Señal de enrutado

RCA **no enruta condicionalmente todavía** (`graph.py`: `rca -> END`
siempre) — el Solution Agent que consumiría `rca_status` de forma distinta
según el valor es S4, aún no existe. Los campos de salida quedan en el
`IncidentState` final para que un humano o el pipeline de S4 los lea; no se
inventa un `route_after_rca` que hoy no tendría a dónde enrutar (grafo
incremental, `CONTEXTO.md`).

---

## Nota de gobernanza

- **Read-only siempre**, sin excepción — las 5 tools son de solo lectura;
  ninguna escribe en Salesforce ni en el repo de código.
- **La confianza y la solidez son verificables, no autodeclaradas.** El nodo
  no confía ciegamente en que el modelo diga `completed`: aplica el
  requisito estructural (≥2 tool calls) y el umbral de confianza (≥80) antes
  de aceptar esa autodeclaración.
- **`rca_evidence` hace auditable el recorrido** — un humano revisando la
  cola puede ver qué tools se llamaron y qué devolvieron, sin re-ejecutar el
  agente.
- **RCA no re-decide category/system/priority** — hereda esas decisiones de
  Intake/Priority tal cual.

---

## Lo que RCA no decide (explícito para evitar scope creep)

| Decisión | Quién la toma |
|---|---|
| Categoría / sistema / proceso de negocio | Intake Agent |
| Impacto / urgencia / prioridad / SLA | Priority Agent |
| Solución concreta / archivos a modificar | Solution Agent (S4) |
| Comunicación al equipo | Comms Agent + gate HITL (S6) |
| Si escalar a `search_codebase`/`read_codebase_repo` o quedarse en el RAG de conocimiento | El propio bucle ReAct, no una regla fija |

---

## Entregable esperado de Claude Code

Un nodo LangGraph (`rca_node`) que:
1. Recibe el `IncidentState` con los campos de Intake + Priority rellenos.
2. Construye el mensaje de usuario inicial del `ReActAgent` con el contexto
   relevante del ticket (título, descripción, errores, clasificación).
3. Instancia `ReActAgent` con `system_prompt` = contenido de
   `docs/specs/rca-agent-prompt.md`, las 5 tool schemas de RCA, perfil
   `smart`, y `complete_fn` inyectado.
4. Mapea `stop_reason` del `ReActAgent` a `rca_status`:
   `max_iterations`/`token_budget` directos; en `final_answer`, parsea el
   JSON final del modelo y aplica los gates de verificación (≥2 tool calls,
   confianza ≥80) antes de aceptar `completed`.
5. Escribe todos los campos de salida en el `IncidentState`, incluyendo
   `rca_evidence` (traza de tools) y `rca_partial_findings` (siempre
   relleno).
6. Nunca revienta el grafo: un fallo total del modelo se captura y se
   traduce en un estado degradado con `needs_human_review: true`.
7. Se conecta en `graph.py` sustituyendo `_rca_placeholder_node` — sin tocar
   `intake`/`priority` ni la forma del grafo.
8. Tests unitarios con al menos 4 incidencias sintéticas (uno por
   `rca_status`), mostrando el `IncidentState` completo de salida en cada
   caso:
   - `completed`: el modelo declara causa raíz tras ≥2 tool calls y
     confianza ≥80.
   - `max_iterations`: el doble de `complete_fn` pide tools indefinidamente.
   - `token_budget`: presupuesto de tokens minúsculo forzado en el test.
   - `insufficient_evidence`: el modelo concluye sin evidencia suficiente
     (o declara `completed` pero con <2 tool calls / confianza <80, para
     probar que el nodo degrada correctamente).
