"""
"Tócalo una vez" — checkpoint pedagógico de S3 (project/CONTEXTO.md):
"una consulta RAG mínima a mano (embed -> retrieve -> mira qué devuelve)
para ver por qué el retrieval manda sobre el prompt."

Una consulta por tabla, grounded en el corpus, más una consulta SIN ningún
grounding (facturación/IVA con SAP — no existe ningún arquetipo de eso) para
ver en vivo que el retrieval devuelve distancias mediocres cuando el corpus
no tiene nada que decir: ninguna ingeniería de prompt en el futuro RCA Agent
arregla eso, solo indexar más corpus.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import psycopg

from agentmind import config
from agentmind.rag import query_incident_history, search_technical_docs, search_runbooks, search_codebase

TABLES = ["incident_history", "technical_docs", "runbooks", "codebase_artifacts"]


def row_counts() -> None:
    conn = psycopg.connect(
        host=config.PG_HOST, port=config.PG_PORT, dbname=config.PG_RAG_DB,
        user=config.PG_USER, password=config.PG_PASSWORD,
    )
    with conn, conn.cursor() as cur:
        print("--- Conteo de filas ---")
        for table in TABLES:
            cur.execute(f"SELECT count(*) FROM {table};")
            print(f"{table}: {cur.fetchone()[0]}")
    conn.close()


def grounded_queries() -> None:
    print("\n--- Consulta 1/5: incident_history (grounded, arquetipo Opportunity trigger) ---")
    print(query_incident_history("trigger de Opportunity falla al cerrar con fecha de cierre en el pasado", k=3))

    print("\n--- Consulta 2/5: technical_docs (grounded) ---")
    print(search_technical_docs("validación de fecha en OpportunityTrigger", k=3))

    print("\n--- Consulta 3/5: runbooks (grounded, debe devolver el runbook COMPLETO) ---")
    print(search_runbooks("cómo diagnosticar un trigger que falla en bulk", k=1))

    print("\n--- Consulta 4/5: codebase_artifacts (grounded) ---")
    print(search_codebase("error 500 en Lightning component de gestión de contratos", k=3))

    print("\n--- Consulta 5/5: incident_history SIN grounding en el corpus (caso negativo) ---")
    print(query_incident_history("fallo de facturación en SAP por IVA incorrecto en factura electrónica", k=3))


if __name__ == "__main__":
    row_counts()
    grounded_queries()
