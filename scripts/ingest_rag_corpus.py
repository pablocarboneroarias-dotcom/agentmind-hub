"""
Ingesta del corpus sintético generado en las 4 tablas pgvector (S3).

Lee el JSON generado por `generate_incidents.py` / `generate_technical_docs.py`
/ `generate_runbooks.py` / `generate_codebase_artifacts.py`, construye
`embedding_text` con la concatenación EXACTA que dicta cada tabla en
`docs/specs/rag-corpus-spec-s3.md`, embebe en lotes con `embed_documents()`
(embeddinggemma) e inserta en Postgres.

`incident_history` lee SOLO `data/incidents/historic/*.json` — los sets
`test`/`edge_cases` son JSON-only, nunca se insertan (así lo dice el spec).

Uso:
    uv run python scripts/ingest_rag_corpus.py --table all --dry-run
    uv run python scripts/ingest_rag_corpus.py --table all --reset
    uv run python scripts/ingest_rag_corpus.py --table runbooks
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import psycopg
from pgvector import Vector
from pgvector.psycopg import register_vector

from agentmind import config
from agentmind.models import embed_documents

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


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


def _load_dir(path: Path) -> list[dict]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(path.glob("*.json"))]


def _last_sentence(text: str) -> str:
    parts = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s.strip()]
    return parts[-1] if parts else text.strip()


# --- Construcción de filas por tabla (embedding_text incluido) --------------


def _build_incident_rows() -> list[dict]:
    rows = []
    for inc in _load_dir(DATA_DIR / "incidents" / "historic"):
        embedding_text = " ".join(
            str(x)
            for x in [
                inc.get("description", ""),
                inc.get("category", ""),
                inc.get("system", ""),
                " ".join(inc.get("error_messages") or []),
                inc.get("root_cause", "") or "",
                inc.get("resolution_notes", "") or "",
            ]
        )
        rows.append(
            {
                "incident_id": inc["incident_id"],
                "created_at": inc.get("created_at"),
                "category": inc.get("category"),
                "system": inc.get("system"),
                "severity": inc.get("severity"),
                "affected_users": inc.get("affected_users"),
                "affected_objects": inc.get("affected_objects") or [],
                "resolution_time_hours": inc.get("resolution_time_hours"),
                "embedding_text": embedding_text,
            }
        )
    return rows


def _build_technical_doc_rows() -> list[dict]:
    rows = []
    for doc in _load_dir(DATA_DIR / "technical_docs"):
        embedding_text = " ".join(
            str(x)
            for x in [
                doc.get("component_name", ""),
                doc.get("what_it_does", ""),
                doc.get("when_it_triggers", ""),
                doc.get("validations", ""),
                " ".join(doc.get("related_objects") or []),
                doc.get("related_business_process", ""),
            ]
        )
        rows.append(
            {
                "doc_id": doc["doc_id"],
                "document_type": doc.get("document_type"),
                "component_name": doc.get("component_name"),
                "related_objects": doc.get("related_objects") or [],
                "related_business_process": doc.get("related_business_process"),
                "embedding_text": embedding_text,
            }
        )
    return rows


def _build_runbook_rows() -> list[dict]:
    rows = []
    for rb in _load_dir(DATA_DIR / "runbooks"):
        steps = sorted(rb["steps"], key=lambda s: s["step_number"])
        total_steps = len(steps)
        prev_text = None
        for step in steps:
            step_text = step["step_text"]
            chunk_text = step_text if prev_text is None else f"{_last_sentence(prev_text)} {step_text}"
            prev_text = step_text
            embedding_text = f"{rb['runbook_title']} ({rb['category']}): {chunk_text}"
            rows.append(
                {
                    "chunk_id": f"{rb['runbook_id']}-S{step['step_number']:02d}",
                    "runbook_id": rb["runbook_id"],
                    "runbook_title": rb["runbook_title"],
                    "step_number": step["step_number"],
                    "total_steps": total_steps,
                    "category": rb["category"],
                    "chunk_text": chunk_text,
                    "embedding_text": embedding_text,
                }
            )
    return rows


def _build_codebase_rows() -> list[dict]:
    rows = []

    for fc in _load_dir(DATA_DIR / "codebase_artifacts" / "feature_cards"):
        rows.append(
            {
                "chunk_id": fc["artifact_id"],
                "artifact_type": "feature_card",
                "parent_doc_id": None,
                "parent_title": fc.get("title"),
                "chunk_index": None,
                "total_chunks": None,
                "related_objects": fc.get("related_objects") or [],
                "related_business_process": fc.get("related_business_process"),
                "chunk_text": fc.get("content_text"),
                "embedding_text": fc.get("content_text"),
            }
        )

    for arch in _load_dir(DATA_DIR / "codebase_artifacts" / "architecture"):
        sections = [s for s in re.split(r"(?m)^##\s+", arch["markdown_content"]) if s.strip()]
        total = len(sections)
        for idx, section in enumerate(sections):
            chunk_text = "## " + section.strip()
            rows.append(
                {
                    "chunk_id": f"{arch['artifact_id']}-C{idx:02d}",
                    "artifact_type": "architecture",
                    "parent_doc_id": arch["artifact_id"],
                    "parent_title": arch.get("title"),
                    "chunk_index": idx,
                    "total_chunks": total,
                    "related_objects": [],
                    "related_business_process": None,
                    "chunk_text": chunk_text,
                    "embedding_text": chunk_text,
                }
            )

    for snip in _load_dir(DATA_DIR / "codebase_artifacts" / "code_snippets"):
        embedding_text = f"{snip.get('summary', '')}\n\n{snip.get('code_text', '')}"
        rows.append(
            {
                "chunk_id": snip["artifact_id"],
                "artifact_type": "code_snippet",
                "parent_doc_id": None,
                "parent_title": snip.get("title"),
                "chunk_index": None,
                "total_chunks": None,
                "related_objects": snip.get("related_objects") or [],
                "related_business_process": snip.get("related_business_process"),
                "chunk_text": snip.get("code_text"),
                "embedding_text": embedding_text,
            }
        )
    return rows


# --- Embeber + insertar ------------------------------------------------------


def _embed_and_insert(conn: psycopg.Connection, table: str, rows: list[dict], reset: bool) -> None:
    if not rows:
        print(f"[{table}] sin filas que insertar (¿generaste el corpus primero?)")
        return

    if reset:
        with conn.cursor() as cur:
            cur.execute(f"TRUNCATE TABLE {table};")
        print(f"[{table}] TRUNCATE hecho.")

    texts = [r["embedding_text"] for r in rows]
    embeddings = embed_documents(texts)
    for r, emb in zip(rows, embeddings):
        r["embedding"] = Vector(emb)

    columns = list(rows[0])  # todas las claves generadas, incluidas embedding_text y embedding
    placeholders = ", ".join(f"%({c})s" for c in columns)
    col_list = ", ".join(columns)
    pk = columns[0]
    query = (
        f"INSERT INTO {table} ({col_list}) VALUES ({placeholders}) "
        f"ON CONFLICT ({pk}) DO NOTHING;"
    )
    with conn.cursor() as cur:
        cur.executemany(query, rows)
    print(f"[{table}] {len(rows)} filas insertadas (o ya existentes, ON CONFLICT DO NOTHING).")


BUILDERS = {
    "incidents": ("incident_history", _build_incident_rows),
    "technical_docs": ("technical_docs", _build_technical_doc_rows),
    "runbooks": ("runbooks", _build_runbook_rows),
    "codebase": ("codebase_artifacts", _build_codebase_rows),
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--table", choices=["all", *BUILDERS], default="all")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args()

    targets = list(BUILDERS) if args.table == "all" else [args.table]

    conn = None if args.dry_run else _connect()
    try:
        for name in targets:
            table, builder = BUILDERS[name]
            rows = builder()
            if args.dry_run:
                print(f"[{name} -> {table}] {len(rows)} filas listas para insertar. Ejemplo embedding_text:")
                if rows:
                    print("  " + rows[0]["embedding_text"][:300])
                continue
            _embed_and_insert(conn, table, rows, args.reset)
    finally:
        if conn is not None:
            conn.close()


if __name__ == "__main__":
    main()
