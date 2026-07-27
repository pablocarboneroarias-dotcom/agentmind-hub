# Corpus RAG — Especificación técnica (S3)

Modelo de embeddings: `embeddinggemma` (Ollama, local) — VECTOR(768).
(Sustituye a `nomic-embed-text`, la sugerencia original: pgvector es agnóstico
al modelo mientras cuadre la dimensión, y embeddinggemma es multilingüe —
el corpus es 100% español — mientras nomic-embed-text v1 está optimizado
para inglés. Decisión tomada al implementar, 2026-07.)

---

## 1. `incident_history`

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE incident_history (
    incident_id TEXT PRIMARY KEY,
    created_at TIMESTAMP,
    category TEXT,
    system TEXT,
    severity TEXT,
    affected_users INTEGER,
    affected_objects TEXT[],
    resolution_time_hours FLOAT,
    embedding_text TEXT,
    embedding VECTOR(768)
);

CREATE INDEX ON incident_history USING hnsw (embedding vector_cosine_ops);
```

**`embedding_text` = concatenación de:** `description + category + system +
error_messages + root_cause + resolution_notes`

**Volumen:** 150 filas (histórico, insertadas) + 30 test + 20 edge cases
(generados como JSON aparte, NO insertados en la tabla — son para probar el
pipeline end-to-end, no para ser encontrados por RAG).

---

## 2. `technical_docs`

```sql
CREATE TABLE technical_docs (
    doc_id TEXT PRIMARY KEY,
    document_type TEXT,            -- 'trigger' | 'flow' | 'integration' | 'permission_rule'
    component_name TEXT,
    related_objects TEXT[],
    related_business_process TEXT, -- uno de los 14 códigos de dominio-salesforce.md
    embedding_text TEXT,
    embedding VECTOR(768)
);

CREATE INDEX ON technical_docs USING hnsw (embedding vector_cosine_ops);
```

**`embedding_text` = concatenación de:** `component_name + qué hace + cuándo
se dispara + validaciones que aplica + related_objects + related_business_process`

**Volumen:** 25 documentos (cubriendo componentes de los 10 arquetipos + ruido
no relacionado con ningún bug conocido).

---

## 3. `runbooks`

```sql
CREATE TABLE runbooks (
    chunk_id TEXT PRIMARY KEY,
    runbook_id TEXT,
    runbook_title TEXT,
    step_number INTEGER,
    total_steps INTEGER,
    category TEXT,
    chunk_text TEXT,
    embedding_text TEXT,           -- normalmente = chunk_text (+ runbook_title si aporta contexto)
    embedding VECTOR(768)
);

CREATE INDEX ON runbooks USING hnsw (embedding vector_cosine_ops);
```

**Patrón:** trocear por paso, con overlap de ~1 frase entre pasos consecutivos
para no perder contexto local. Al recuperar, hacer una segunda query
relacional (`WHERE runbook_id = X ORDER BY step_number`) para devolver el
runbook completo, no el chunk suelto.

**Volumen:** 8 runbooks (~5 pasos cada uno) = ~40 chunks. Uno por tipo de
diagnóstico: bulk trigger, Flow roto, integración, permisos, duplicados,
rendimiento, CPQ, notificaciones.

---

## 4. `codebase_artifacts`

```sql
CREATE TABLE codebase_artifacts (
    chunk_id TEXT PRIMARY KEY,
    artifact_type TEXT,            -- 'feature_card' | 'architecture' | 'code_snippet'
    parent_doc_id TEXT,             -- NULL si no aplica (documento corto, sin trocear)
    parent_title TEXT,
    chunk_index INTEGER,            -- NULL si no trocea
    total_chunks INTEGER,
    related_objects TEXT[],
    related_business_process TEXT,
    chunk_text TEXT,
    embedding_text TEXT,
    embedding VECTOR(768),
    file_path TEXT                  -- añadida tras uso real, ver nota abajo
);

CREATE INDEX ON codebase_artifacts USING hnsw (embedding vector_cosine_ops);
```

**Columna `file_path` (añadida tras el primer uso real del RCA Agent, no en
la versión original de este spec):** ruta relativa dentro de
`codebase-toy-repo/` del fichero real que corresponde a este artefacto
(ej. `"src/batch/CPQ_Pricing_Batch_Job.cls"`), o `NULL` si el artefacto
describe algo declarativo sin fichero real (sharing rules, dedup rules,
price rules, dashboards, workflow rules — ver `codebase-toy-repo/README.md`).
Se añadió al detectar en producción que el RCA Agent encontraba el
componente correcto por `search_codebase` pero no tenía forma de saber su
ruta real, y gastaba tool calls adivinando convenciones genéricas de
Salesforce DX (`force-app/main/default/classes/...`) que no existen en este
repo de juguete — `search_codebase` ahora devuelve `file_path` directamente
cuando existe, así `read_codebase_repo` puede usarlo sin adivinar.

**Criterio de troceado (aplicar por tipo):**
- `feature_card`: NO trocear — documento corto, un solo tema.
- `architecture`: SÍ trocear, por sección lógica (estructura de carpetas,
  modelo de datos, convenciones, ubicación de módulos son temas independientes).
- `code_snippet`: SÍ trocear si el componente mezcla varios métodos/bloques
  lógicos independientes; NO trocear si es una función/validación compacta
  de una sola responsabilidad.

**Volumen:** 10 fichas de feature + 1 ficha de arquitectura (troceada en ~6
secciones) + 10 snippets de código, uno por arquetipo de
`dominio-salesforce.md`.

---

## Regla general de troceado (aplicada arriba, para referencia)

Trocear cuando el documento mezcla varios temas independientes que alguien
podría necesitar buscar por separado (dilución semántica: el vector
"promedio" deja de parecerse a ninguna búsqueda específica). No trocear
cuando el documento ya es una unidad de significado compacta y corta
(correlación directa, sin riesgo de dilución).
