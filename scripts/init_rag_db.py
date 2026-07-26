"""
Crea la DB `agentmind` (si no existe) y el esquema del corpus RAG (S3).

Uso:
    uv run python scripts/init_rag_db.py            # crea DB + tablas si faltan
    uv run python scripts/init_rag_db.py --reset     # DROP + recrea las 4 tablas

No usa `psql` (no está instalado en este Mac) — todo vía `psycopg`. El DDL
vive tal cual en `scripts/sql/schema.sql` (copia literal del spec); este
script solo se encarga de `CREATE DATABASE`/`CREATE EXTENSION` (que no pueden
ir en el mismo archivo que el resto: `CREATE DATABASE` exige autocommit y no
puede correr dentro de una transacción) y de partir el .sql en sentencias
individuales, porque psycopg3 (protocolo extendido) ejecuta una sentencia por
`execute()`, a diferencia de `psql -f` que acepta el archivo entero de golpe.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from agentmind import config  # noqa: E402

SCHEMA_PATH = Path(__file__).resolve().parent / "sql" / "schema.sql"
TABLES = ["incident_history", "technical_docs", "runbooks", "codebase_artifacts"]


def _admin_conn() -> psycopg.Connection:
    return psycopg.connect(
        host=config.PG_HOST,
        port=config.PG_PORT,
        dbname=config.PG_ADMIN_DB,
        user=config.PG_USER,
        password=config.PG_PASSWORD,
        autocommit=True,
    )


def _rag_conn() -> psycopg.Connection:
    return psycopg.connect(
        host=config.PG_HOST,
        port=config.PG_PORT,
        dbname=config.PG_RAG_DB,
        user=config.PG_USER,
        password=config.PG_PASSWORD,
        autocommit=True,
    )


def ensure_database() -> None:
    with _admin_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (config.PG_RAG_DB,))
        if cur.fetchone() is None:
            cur.execute(f"CREATE DATABASE {config.PG_RAG_DB} OWNER {config.PG_USER};")
            print(f"DB '{config.PG_RAG_DB}' creada.")
        else:
            print(f"DB '{config.PG_RAG_DB}' ya existe.")


def ensure_extension() -> None:
    with _rag_conn() as conn, conn.cursor() as cur:
        cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
    print("Extensión 'vector' lista.")


def reset_tables() -> None:
    with _rag_conn() as conn, conn.cursor() as cur:
        cur.execute(f"DROP TABLE IF EXISTS {', '.join(TABLES)} CASCADE;")
    print("Tablas existentes eliminadas (--reset).")


def create_tables() -> None:
    # Quita las líneas que son COMENTARIO COMPLETO (empiezan por "--") antes de
    # partir por ";" — si no, un bloque que arranca con un comentario de línea
    # completa se descarta entero (comentario Y sentencia), porque el check
    # se hacía sobre el string completo, no línea a línea.
    lines = [line for line in SCHEMA_PATH.read_text().splitlines() if not line.strip().startswith("--")]
    sql = "\n".join(lines)
    statements = [s.strip() for s in sql.split(";") if s.strip()]
    with _rag_conn() as conn, conn.cursor() as cur:
        for stmt in statements:
            cur.execute(stmt)
    print(f"{len(statements)} sentencias DDL ejecutadas desde {SCHEMA_PATH.name}.")


def summarize() -> None:
    with _rag_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' ORDER BY table_name;"
        )
        found = [row[0] for row in cur.fetchall()]
    print("Tablas en 'agentmind':", found)
    missing = set(TABLES) - set(found)
    if missing:
        print(f"AVISO: faltan tablas esperadas: {sorted(missing)}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true", help="DROP + recrear las 4 tablas")
    args = parser.parse_args()

    ensure_database()
    ensure_extension()
    if args.reset:
        reset_tables()
    create_tables()
    summarize()


if __name__ == "__main__":
    main()
