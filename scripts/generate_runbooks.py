"""
Generador de runbooks sintéticos de diagnóstico (S3 — corpus RAG).

8 runbooks, uno por cada tipo de diagnóstico que ya nombra
`docs/specs/rag-corpus-spec-s3.md`: bulk trigger, Flow roto, integración,
permisos, duplicados, rendimiento, CPQ, notificaciones. ~5 pasos cada uno,
generados SIN trocear todavía — el solape de ~1 frase entre pasos consecutivos
es una transformación mecánica que hace `ingest_rag_corpus.py`, no el LLM
(así se puede ajustar el algoritmo de solape sin volver a gastar una llamada).

Salida: un JSON por runbook en `data/runbooks/RB-XXX.json`.
"""

from __future__ import annotations

import json
from pathlib import Path

from _corpus_common import generate_json

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "data" / "runbooks"

# (runbook_id, título, categoría asociada) — 1:1 con los 8 tipos del spec.
RUNBOOK_SPECS: list[tuple[str, str, str]] = [
    ("RB-001", "Cómo diagnosticar un trigger que falla en bulk", "APEX"),
    ("RB-002", "Cómo depurar un Flow que no dispara o falla", "FLOW"),
    ("RB-003", "Cómo trazar un fallo de integración por límites de API", "INTEG"),
    ("RB-004", "Cómo identificar el origen de un problema de permisos", "PERM"),
    ("RB-005", "Cómo investigar duplicados masivos de registros", "DATA"),
    ("RB-006", "Cómo diagnosticar problemas de rendimiento y límites de gobernador", "PERF"),
    ("RB-007", "Cómo diagnosticar errores de precios/CPQ", "CPQ"),
    ("RB-008", "Cómo diagnosticar notificaciones o emails que no se envían", "EMAIL"),
]


def _prompt(runbook_id: str, title: str, category: str) -> str:
    return f"""Genera un runbook de diagnóstico técnico para un equipo de soporte de
Salesforce CRM (sector energético europeo). Runbook: "{title}"
(runbook_id="{runbook_id}", category="{category}").

Debe tener EXACTAMENTE 5 pasos secuenciales, concretos y accionables (qué
mirar, qué herramienta/log/consulta usar, qué resultado indica qué causa),
en el orden lógico de una investigación real (de síntoma a causa raíz).

Devuelve SOLO un objeto JSON con EXACTAMENTE estas claves:
{{
  "runbook_id": "{runbook_id}",
  "runbook_title": "{title}",
  "category": "{category}",
  "steps": [
    {{"step_number": 1, "step_text": "..."}},
    {{"step_number": 2, "step_text": "..."}},
    {{"step_number": 3, "step_text": "..."}},
    {{"step_number": 4, "step_text": "..."}},
    {{"step_number": 5, "step_text": "..."}}
  ]
}}

Sin explicación ni fences adicionales."""


def generate_all() -> list[dict]:
    runbooks = []
    for runbook_id, title, category in RUNBOOK_SPECS:
        rb = generate_json(_prompt(runbook_id, title, category))
        runbooks.append(rb)
        print(f"{runbook_id}: {len(rb.get('steps', []))} pasos generados")
    return runbooks


def save_all(runbooks: list[dict]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for rb in runbooks:
        path = OUTPUT_DIR / f"{rb['runbook_id']}.json"
        path.write_text(json.dumps(rb, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Guardados {len(runbooks)} runbooks en {OUTPUT_DIR}")


if __name__ == "__main__":
    save_all(generate_all())
