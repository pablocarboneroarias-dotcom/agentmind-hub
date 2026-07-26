# RCA Agent (S3) — Decisiones de diseño acordadas

Documento vivo de las decisiones cerradas durante el diseño del RCA Agent.
Precede al spec formal (`spec-rca-agent.md`), que se escribirá cuando estén
cerradas también las condiciones de parada y el formato de salida.

---

## Naturaleza del agente (heredado de S1)

- **Tipo:** Agente (no workflow) — autónomo, patrón ReAct.
- **Perfil de modelo:** `smart` (razonamiento causal real, no clasificación
  mecánica).
- **Gobernanza:** **read-only siempre.** RCA nunca escribe en Salesforce ni
  en ningún sistema. Busca *por qué* pasó (causa), no *cómo* arreglarlo (eso
  es Solution, S4).

## Reutiliza la base de `react_agent.py` (Fase 1)

El bucle ReAct de producción ya existe y tiene los dos ejes de seguridad
necesarios, que se mantienen:
- **Tope de iteraciones** (`max_iterations`, configurable vía `AgentLimits`).
- **Presupuesto de tokens** (`token_budget`, comprobado antes de cada
  llamada — importa porque cada iteración reenvía todo el historial).
- **Camino feliz:** el modelo deja de emitir tool calls → `final_answer`.

Estos tres caminos de parada son la base. RCA añade lógica de estado propia
encima (ver `rca_status` abajo), porque en un grafo lo que pasa *después* de
que RCA pare depende de *por qué* paró — algo que en Fase 1 no importaba.

## Caja de herramientas — 4 tools, todas búsqueda semántica read-only

```
RCA Agent (ReAct, perfil smart)
├── Tool 1: query_incident_history   (RAG — histórico de incidencias resueltas)
├── Tool 2: search_technical_docs     (RAG — docs técnicas + triggers/flows indexados)
├── Tool 3: search_runbooks           (RAG — guías de diagnóstico paso a paso)
└── Tool 4: search_codebase           (RAG — artefactos de código sintéticos)
```

### Escalado entre tools: lo decide el bucle ReAct, no un if/else

El orden de consulta NO se programa como flujo rígido. El agente empieza por
el RAG de conocimiento (histórico, docs, runbooks) y, si no reúne evidencia
suficiente para una hipótesis de causa raíz, **el propio razonamiento ReAct
decide** escalar a `search_codebase`. Ese es justo el valor de que sea un
agente y no un workflow: la autonomía sobre el camino.

**Principio de negocio detrás (validado por Pablo):** un RCA real, si no
encuentra el error en la KB, se va al código — igual que haría un humano.
No tiene sentido atarle las manos al agente al RAG de conocimiento.

### Tool 4 (`search_codebase`) — alcance en S3 vs. producción

- **En S3 (aprendizaje):** corpus **sintético** de "artefactos de código",
  indexado como el resto del RAG. Tres tipos de documento:
  1. **Fichas de feature** (`.md`): qué objetos, clases, validaciones y
     triggers involucra cada funcionalidad, y cuándo se disparan.
  2. **Ficha de arquitectura:** estructura de carpetas simulada, dónde viven
     las clases, modelo de datos, dónde buscar cada cosa.
  3. **Snippets de código anotados:** cuerpo sintético de triggers/clases
     críticos con comentarios de qué hacen.
- **Búsqueda semántica libre**, no por nombre de archivo exacto — el agente
  describe el síntoma ("validación de fecha en cierre de oportunidad"), no
  necesita saber el nombre del `.cls` de antemano.
- **En producción (evolución documentada, NO en S3):** esto sería un
  **repo map / documentation-augmented retrieval** en vivo sobre el
  repositorio real, y/o un **knowledge graph** de relaciones entre objetos
  Salesforce (el "Mapa de objetos" de `dominio-salesforce.md` ya es la
  semilla textual de ese grafo). Se deja como mejora futura consciente, no
  como deuda oculta.

**Razón de no montar repo real / BD de grafos en S3:** sería
sobre-ingeniería para el objetivo de la semana (dominar el bucle ReAct con
escalado de tools) y añadiría superficie de riesgo (credenciales, ramas,
desincronización repo-índice) que distrae del núcleo didáctico. Con las 4
tools como búsqueda semántica sobre corpus distintos, el aprendizaje se
concentra en *cómo el agente decide a qué corpus preguntar y cuándo escalar*.

## Estado de salida — `rca_status` (4 valores, CERRADO)

Se confirma que RCA necesita **su propio campo de estado**, distinto de
`needs_human_review`, que registre *por qué* paró y conserve el trabajo
parcial. Cuatro valores acordados:

| `rca_status` | Significado | Qué implica para el humano/pipeline |
|---|---|---|
| `completed` | Encontró causa raíz con evidencia suficiente | Sigue a Solution (S4) |
| `max_iterations` | Se agotaron las iteraciones sin conclusión | Falta presupuesto — quizá subir límite o cambiar perfil |
| `token_budget` | Se agotó el presupuesto de tokens sin conclusión | Ídem — problema de recursos, no de datos |
| `insufficient_evidence` | Tuvo todos los recursos pero no halló evidencia | Problema de **datos**: falta contenido en el RAG/corpus |

**Por qué distinguir `insufficient_evidence` de los dos límites de recursos
(validado por Pablo):** al humano que revisa la cola le importa —y mucho—
saber si RCA "se quedó sin gasolina" (subir límites) o "tuvo toda la
gasolina y aun así no encontró nada" (falta contenido indexado). Son dos
problemas con solución completamente distinta.

En los tres casos que no son `completed`, además se pone
`needs_human_review = true` (mecanismo transversal ya existente) y se guarda
el análisis parcial hecho hasta el momento (ver campos pendientes abajo).

## Condición de parada — "evidencia suficiente" (CERRADO)

**Problema de diseño detectado y corregido durante la discusión:** la
primera propuesta era exigir "al menos 2 fuentes que corroboren la causa"
como requisito duro antes de poder declarar `completed`. Se descartó porque
rompe un caso real legítimo: una incidencia **nueva sin precedente en el
histórico**, donde solo el código/metadata explica la causa. Exigir 2
fuentes ahí forzaría `insufficient_evidence` sobre una causa raíz
correctamente encontrada — penalizar precisión real por rigidez de proceso.

**Causa del error:** confundir "cuántas fuentes consultó" (esfuerzo) con
"cuántas fuentes corroboran la misma causa" (solidez de la evidencia). No
son lo mismo — se puede consultar todo y solo una fuente tener resultado.

**Diseño final (mezcla estructurado + juicio del modelo, según lo acordado):**

1. **Requisito estructural duro (lo verifica el código, no el modelo):** el
   agente debe haber *intentado* consultar las tools relevantes antes de
   declarar `completed` — no que todas devuelvan resultado, sino que
   ninguna se salte por pereza. Verificable objetivamente contando tool
   calls registradas.
2. **Metadato de solidez (no bloqueante, solo informativo):**
   `rca_corroboration: "multi_source" | "single_source"` — si la causa
   final está respaldada por evidencia coincidente en más de una fuente, o
   solo en una (pero directa y concreta, ej. un stacktrace exacto en
   código).
3. **Confianza del modelo (juicio, tras cumplir el paso 1):** el modelo
   evalúa consistencia entre las fuentes que sí tuvieron resultado y
   asigna su propio nivel de confianza sobre esa evidencia ya verificada
   — no sobre la nada. Umbral de corte: **80** (no 90 — se deja margen
   80-100 para que Solution/S4 pueda tratar distinto una causa "muy
   segura" de una "razonablemente segura", en vez de un corte binario
   ciego).

Con esto, un `completed` con `multi_source` + confianza 85 se distingue
correctamente de un `completed` con `single_source` + confianza 85 — mismo
número, distinta solidez, sin que ninguno de los dos quede bloqueado
injustamente.

---

## Pendiente de cerrar (próximos pasos, antes del spec formal)

1. **Campos exactos de salida en `IncidentState`:** consolidar
   `rca_status`, `rca_corroboration`, `root_cause`, `rca_evidence`,
   `rca_partial_findings`, `rca_iterations_used`, confianza del modelo
   (`rca_confidence`).
2. **Corpus sintético:** generar los artefactos de código (fichas de
   feature + arquitectura + snippets) coherentes con los 10 arquetipos de
   `dominio-salesforce.md`, y las 150 incidencias históricas + runbooks, e
   indexarlos en pgvector (3-4 colecciones separadas).
3. **Prompt del agente:** redactar el system prompt de RCA que explique el
   criterio de suficiencia (paso 1 estructural + paso 3 de juicio) en
   lenguaje natural, coherente con este documento.
4. **Spec formal (`spec-rca-agent.md`):** una vez cerrado lo anterior,
   consolidar todo en el mismo formato usado para Intake y Priority.
