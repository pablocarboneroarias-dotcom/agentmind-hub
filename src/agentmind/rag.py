"""
Búsqueda semántica sobre el corpus RAG (S3) — 4 colecciones en pgvector.

Estas 4 funciones son las que el futuro RCA Agent (ReAct, S3) usará como
tools de solo-lectura (`query_incident_history`, `search_technical_docs`,
`search_runbooks`, `search_codebase`, ver `docs/specs/rca-decisiones-s3.md`).
Se registran en `tools.py` con la misma firma `(...) -> str` que ya usa el
resto de herramientas: nunca lanzan excepción hacia arriba, un fallo de DB se
devuelve como texto legible.

Distancia coseno (`<=>`) porque los índices hnsw se crearon con
`vector_cosine_ops` (ver `scripts/sql/schema.sql`). Menor distancia = más
parecido.
"""

from __future__ import annotations

import psycopg
from pgvector import Vector
from pgvector.psycopg import register_vector

from . import config
from .models import embed_query
from .observability import traced

_SNIPPET_LEN = 600  # cuánto texto de embedding_text/chunk_text mostrar en la observación


def _connect() -> psycopg.Connection:
    conn = psycopg.connect(
        host=config.PG_HOST,
        port=config.PG_PORT,
        dbname=config.PG_RAG_DB,
        user=config.PG_USER,
        password=config.PG_PASSWORD,
        autocommit=True,
    )
    register_vector(conn)
    return conn


def _truncate(text: str | None, length: int = _SNIPPET_LEN) -> str:
    text = text or ""
    return text if len(text) <= length else text[:length] + "…"


@traced("rag.query_incident_history", run_type="retriever")
def query_incident_history(query: str, k: int = 5) -> str:
    """Busca incidencias históricas resueltas parecidas a `query` (RAG semántico)."""
    try:
        qvec = Vector(embed_query(query))
        with _connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT incident_id, created_at, category, system, severity,
                       affected_users, affected_objects, resolution_time_hours,
                       embedding_text, (embedding <=> %(qvec)s) AS distance
                FROM incident_history
                ORDER BY distance
                LIMIT %(k)s;
                """,
                {"qvec": qvec, "k": k},
            )
            rows = cur.fetchall()
    except Exception as exc:  # noqa: BLE001
        return f"Error consultando incident_history: {exc}"

    if not rows:
        return f'No se encontraron incidencias similares en el histórico para: "{query}"'

    lines = [f'{len(rows)} incidencia(s) similares encontradas para: "{query}"\n']
    for i, r in enumerate(rows, 1):
        incident_id, created_at, category, system, severity, affected_users, affected_objects, resolution_time_hours, embedding_text, distance = r
        lines.append(
            f"{i}. [{incident_id}] distancia={distance:.3f} | categoria={category} "
            f"sistema={system} severidad={severity} usuarios_afectados={affected_users} "
            f"objetos={affected_objects} tiempo_resolucion={resolution_time_hours}h "
            f"creado={created_at}\n   {_truncate(embedding_text)}"
        )
    return "\n".join(lines)


@traced("rag.search_technical_docs", run_type="retriever")
def search_technical_docs(query: str, k: int = 5) -> str:
    """Busca documentación técnica del org (triggers, flows, integraciones...) relevante a `query`."""
    try:
        qvec = Vector(embed_query(query))
        with _connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT doc_id, document_type, component_name, related_objects,
                       related_business_process, embedding_text,
                       (embedding <=> %(qvec)s) AS distance
                FROM technical_docs
                ORDER BY distance
                LIMIT %(k)s;
                """,
                {"qvec": qvec, "k": k},
            )
            rows = cur.fetchall()
    except Exception as exc:  # noqa: BLE001
        return f"Error consultando technical_docs: {exc}"

    if not rows:
        return f'No se encontró documentación técnica relevante para: "{query}"'

    lines = [f'{len(rows)} documento(s) técnico(s) encontrados para: "{query}"\n']
    for i, r in enumerate(rows, 1):
        doc_id, document_type, component_name, related_objects, related_business_process, embedding_text, distance = r
        lines.append(
            f"{i}. [{doc_id}] distancia={distance:.3f} | tipo={document_type} "
            f"componente={component_name} objetos={related_objects} "
            f"proceso_negocio={related_business_process}\n   {_truncate(embedding_text)}"
        )
    return "\n".join(lines)


@traced("rag.search_runbooks", run_type="retriever")
def search_runbooks(query: str, k: int = 2) -> str:
    """Busca runbooks de diagnóstico; devuelve el procedimiento COMPLETO, no un chunk suelto.

    Dos pasos, tal como exige el spec: (1) sobre-buscar chunks para localizar
    qué runbooks son relevantes, (2) por cada runbook_id encontrado, una
    segunda query relacional ordenada por step_number para reconstruirlo entero.
    """
    try:
        qvec = Vector(embed_query(query))
        with _connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT runbook_id, runbook_title, category, chunk_id,
                       (embedding <=> %(qvec)s) AS distance
                FROM runbooks
                ORDER BY distance
                LIMIT 15;
                """,
                {"qvec": qvec},
            )
            candidates = cur.fetchall()

            seen: dict[str, tuple] = {}
            for runbook_id, runbook_title, category, _chunk_id, distance in candidates:
                if runbook_id not in seen:
                    seen[runbook_id] = (runbook_title, category, distance)
                if len(seen) >= k:
                    break

            if not seen:
                return f'No se encontraron runbooks relevantes para: "{query}"'

            blocks = [f'{len(seen)} runbook(s) encontrados para: "{query}"\n']
            for runbook_id, (runbook_title, category, distance) in seen.items():
                cur.execute(
                    """
                    SELECT step_number, total_steps, chunk_text
                    FROM runbooks
                    WHERE runbook_id = %(rid)s
                    ORDER BY step_number;
                    """,
                    {"rid": runbook_id},
                )
                steps = cur.fetchall()
                header = (
                    f'Runbook: "{runbook_title}" ({runbook_id}, categoria={category}, '
                    f"distancia={distance:.3f})"
                )
                step_lines = [
                    f"Paso {step_number}/{total_steps}: {chunk_text}"
                    for step_number, total_steps, chunk_text in steps
                ]
                blocks.append(header + "\n" + "\n".join(step_lines))
    except Exception as exc:  # noqa: BLE001
        return f"Error consultando runbooks: {exc}"

    return "\n\n".join(blocks)


@traced("rag.search_codebase", run_type="retriever")
def search_codebase(query: str, k: int = 5) -> str:
    """Busca en artefactos de código sintéticos (fichas de feature, arquitectura, snippets)."""
    try:
        qvec = Vector(embed_query(query))
        with _connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT chunk_id, artifact_type, parent_doc_id, parent_title,
                       chunk_index, total_chunks, related_objects,
                       related_business_process, chunk_text, file_path,
                       (embedding <=> %(qvec)s) AS distance
                FROM codebase_artifacts
                ORDER BY distance
                LIMIT %(k)s;
                """,
                {"qvec": qvec, "k": k},
            )
            rows = cur.fetchall()
    except Exception as exc:  # noqa: BLE001
        return f"Error consultando codebase_artifacts: {exc}"

    if not rows:
        return f'No se encontraron artefactos de código relevantes para: "{query}"'

    lines = [f'{len(rows)} artefacto(s) de código encontrados para: "{query}"\n']
    for i, r in enumerate(rows, 1):
        chunk_id, artifact_type, parent_doc_id, parent_title, chunk_index, total_chunks, related_objects, related_business_process, chunk_text, file_path, distance = r
        pos = f" (parte {chunk_index + 1}/{total_chunks})" if chunk_index is not None else ""
        ruta = (
            f"ruta_repo={file_path} (usa read_codebase_repo con esta ruta EXACTA)"
            if file_path
            else "ruta_repo=(sin fichero real — componente declarativo, no hay .cls/.js que leer)"
        )
        lines.append(
            f"{i}. [{chunk_id}] distancia={distance:.3f} | tipo={artifact_type} "
            f"titulo={parent_title}{pos} objetos={related_objects} "
            f"proceso_negocio={related_business_process} | {ruta}\n   {_truncate(chunk_text)}"
        )
    return "\n".join(lines)


# --- Lookup directo por ID (S4 — Solution Agent, Worker A) ------------------
# Diferencia clave frente a las 4 funciones de arriba: NO hacen búsqueda
# semántica (sin `embed_query`, sin `<=>`). El RCA Agent ya identificó el
# runbook/doc exacto (`rca_runbook_ids`/`rca_technical_doc_ids`, extraídos
# por código en S3) — repetir una búsqueda semántica para releerlo es
# redundante y podría devolver un top-k distinto. Devuelven el contenido
# COMPLETO sin truncar (a diferencia de `_truncate` arriba): Worker A
# necesita el documento entero para verificar si aplica a la causa raíz,
# no un snippet de 600 caracteres.


@traced("rag.get_runbook_by_id", run_type="retriever")
def get_runbook_by_id(runbook_id: str) -> str:
    """Lee el runbook COMPLETO por su ID exacto, sin búsqueda semántica.

    Mismo query relacional (ordenado por step_number) que usa el segundo
    paso de `search_runbooks`, pero filtrando directo por `runbook_id` en
    vez de partir de una lista de candidatos por distancia.
    """
    try:
        with _connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT runbook_title, category, step_number, total_steps, chunk_text
                FROM runbooks
                WHERE runbook_id = %(rid)s
                ORDER BY step_number;
                """,
                {"rid": runbook_id},
            )
            rows = cur.fetchall()
    except Exception as exc:  # noqa: BLE001
        return f"Error consultando runbooks por ID: {exc}"

    if not rows:
        return f"Error: no se encontró ningún runbook con id '{runbook_id}'."

    runbook_title, category, _, _, _ = rows[0]
    header = f'Runbook: "{runbook_title}" ({runbook_id}, categoria={category})'
    step_lines = [
        f"Paso {step_number}/{total_steps}: {chunk_text}"
        for _, _, step_number, total_steps, chunk_text in rows
    ]
    return header + "\n" + "\n".join(step_lines)


@traced("rag.get_technical_doc_by_id", run_type="retriever")
def get_technical_doc_by_id(doc_id: str) -> str:
    """Lee el documento técnico COMPLETO por su ID exacto, sin búsqueda semántica.

    Mismo motivo que `get_runbook_by_id`: releer el doc EXACTO que el RCA ya
    citó (`rca_technical_doc_ids`), no un resultado nuevo de `search_technical_docs`.
    """
    try:
        with _connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT doc_id, document_type, component_name, related_objects,
                       related_business_process, embedding_text
                FROM technical_docs
                WHERE doc_id = %(did)s;
                """,
                {"did": doc_id},
            )
            row = cur.fetchone()
    except Exception as exc:  # noqa: BLE001
        return f"Error consultando technical_docs por ID: {exc}"

    if row is None:
        return f"Error: no se encontró ningún documento técnico con id '{doc_id}'."

    doc_id_, document_type, component_name, related_objects, related_business_process, embedding_text = row
    return (
        f"[{doc_id_}] tipo={document_type} componente={component_name} "
        f"objetos={related_objects} proceso_negocio={related_business_process}\n"
        f"{embedding_text}"
    )
