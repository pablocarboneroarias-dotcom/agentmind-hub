-- Copia literal del DDL de docs/specs/rag-corpus-spec-s3.md (fuente de verdad).
-- La extensión "vector" se crea aparte en init_rag_db.py (necesita ejecutarse
-- una sola vez, de forma idempotente, antes que estas tablas).

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
    embedding VECTOR(768)
);

CREATE INDEX ON codebase_artifacts USING hnsw (embedding vector_cosine_ops);
