"""
Generador de dataset SINTÉTICO de incidencias — Salesforce CRM (S3).

Genera 200 incidencias en total, coherentes con `project/dominio-salesforce.md`
("Dataset sintético — Blueprint"): 150 históricas (resueltas, corpus del RAG)
+ 30 de test + 20 edge case (ambiguas, para forzar el gate HITL de Priority).

La distribución de severidad y categoría, y la asignación categoría->arquetipo,
se calculan aquí en Python de antemano (no se deja a suerte del LLM); el LLM
solo rellena contenido realista para un lote ya especificado.

Salida: un JSON por incidencia bajo
`data/incidents/{historic,test,edge_cases}/INC-XXXX.json`.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

from _corpus_common import ARCHETYPES, ARCHETYPES_BY_ID, generate_json

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "data" / "incidents"

# Recuento exacto de incidencias históricas por categoría (suma = 150), y su
# arquetipo único asociado (project/dominio-salesforce.md: 10 arquetipos = 10
# categorías, 1:1). APEX 25%, FLOW 20%, INTEG 20%, PERM 10%, DATA 10%,
# PERF 5%, resto 10% repartido entre CPQ/REPORT/EMAIL/UI.
HISTORIC_COUNTS_BY_CATEGORY: dict[str, int] = {
    "APEX": 38, "FLOW": 30, "INTEG": 30, "PERM": 15, "DATA": 15,
    "PERF": 8, "CPQ": 4, "REPORT": 4, "EMAIL": 4, "UI": 2,
}
assert sum(HISTORIC_COUNTS_BY_CATEGORY.values()) == 150

# Severidad: P1 10% (15), P2 25% (37), P3 40% (60), P4 25% (38).
HISTORIC_SEVERITY_COUNTS: dict[str, int] = {"P1": 15, "P2": 37, "P3": 60, "P4": 38}
assert sum(HISTORIC_SEVERITY_COUNTS.values()) == 150

CATEGORY_TO_ARCHETYPE = {a.category: a for a in ARCHETYPES}

BATCH_SIZE = 10
RNG_SEED = 42


def _historic_plan() -> list[dict]:
    """150 tuplas (archetype_id, category, system, severity), orden aleatorio fijo."""
    archetype_slots: list[int] = []
    for category, count in HISTORIC_COUNTS_BY_CATEGORY.items():
        archetype_slots.extend([CATEGORY_TO_ARCHETYPE[category].id] * count)

    severity_slots: list[str] = []
    for sev, count in HISTORIC_SEVERITY_COUNTS.items():
        severity_slots.extend([sev] * count)

    rng = random.Random(RNG_SEED)
    rng.shuffle(archetype_slots)
    rng.shuffle(severity_slots)

    return [
        {"archetype_id": a_id, "severity": sev}
        for a_id, sev in zip(archetype_slots, severity_slots)
    ]


def _small_set_plan(per_archetype: int) -> list[dict]:
    """N incidencias por arquetipo (test=3, edge=2), sin severidad fija (las asigna el LLM)."""
    return [{"archetype_id": a.id} for a in ARCHETYPES for _ in range(per_archetype)]


def _batch_prompt(kind: str, batch: list[dict], id_prefix: str, start_index: int) -> str:
    rows = []
    for i, slot in enumerate(batch):
        archetype = ARCHETYPES_BY_ID[slot["archetype_id"]]
        incident_id = f"{id_prefix}-{start_index + i:04d}"
        severity_hint = f', severity="{slot["severity"]}"' if "severity" in slot else ""
        rows.append(
            f'- incident_id="{incident_id}", arquetipo="{archetype.name}" '
            f'(categoria={archetype.category}, sistema={archetype.system}, '
            f'componente={archetype.component}){severity_hint}'
        )
    rows_text = "\n".join(rows)

    if kind == "historic":
        fill_instructions = (
            "Esta es una incidencia YA RESUELTA (histórico). Rellena TODOS los campos "
            "con valores realistas y coherentes: severity (la indicada arriba), "
            "confidence (0.75-0.99), root_cause y resolution_notes concretos y técnicos "
            "(coherentes con el arquetipo/componente), solution_proposed, resolved_at "
            "(posterior a created_at), resolution_time_hours (coherente con la severity: "
            "P1 unas horas, P4 puede ser días), comms_sent=true, comms_approved_by "
            "(email de un manager ficticio). priority_score y priority_rationale pueden "
            "quedar en null (los calcula Priority Agent en tiempo real, no en el histórico)."
        )
    else:
        fill_instructions = (
            "Esta es una incidencia NUEVA, tal como la reportaría un usuario real "
            "(aún sin diagnosticar). Deja en null: severity, confidence, priority_score, "
            "priority_rationale, root_cause, solution_proposed, resolution_notes, "
            "resolved_at, resolution_time_hours; comms_sent=false, comms_approved_by=null."
        )
        if kind == "edge":
            fill_instructions += (
                " Además, redacta la description de forma DELIBERADAMENTE AMBIGUA: "
                "que no quede claro el impacto real (p.ej. sin especificar cuántos "
                "usuarios afectados en el texto, o mezclando síntomas de más de un "
                "arquetipo), para forzar que Priority necesite el LLM/gate humano."
            )

    return f"""Genera un array JSON con {len(batch)} incidencias de Salesforce CRM
(sector energético europeo), una por cada fila de esta lista (respeta el
incident_id y el arquetipo/categoría/sistema de cada una EXACTAMENTE):

{rows_text}

{fill_instructions}

Cada objeto debe tener EXACTAMENTE estas claves (usa null donde corresponda,
nunca omitas una clave):
{{
  "incident_id": str, "created_at": "YYYY-MM-DDTHH:MM:SSZ", "title": str,
  "description": str (2-4 frases, en español, con detalle técnico realista),
  "reporter": "nombre.apellido@cliente.com", "category": str, "system": str,
  "severity": str|null, "confidence": float|null, "priority_score": float|null,
  "priority_rationale": str|null, "affected_users": int,
  "affected_objects": [str, ...] (objetos Salesforce reales: Opportunity, Case, ...),
  "error_messages": [str, ...] (vacío [] si no aplica al arquetipo),
  "root_cause": str|null, "solution_proposed": str|null,
  "resolution_notes": str|null, "resolved_at": str|null,
  "resolution_time_hours": float|null, "comms_sent": bool,
  "comms_approved_by": str|null
}}

Devuelve SOLO el array JSON, sin explicación ni fences adicionales."""


def _generate_set(kind: str, plan: list[dict], id_prefix: str) -> list[dict]:
    incidents: list[dict] = []
    for start in range(0, len(plan), BATCH_SIZE):
        batch = plan[start : start + BATCH_SIZE]
        prompt = _batch_prompt(kind, batch, id_prefix, start)
        parsed = generate_json(prompt)
        if len(parsed) != len(batch):
            print(f"AVISO [{kind}]: pedí {len(batch)}, recibí {len(parsed)} (sigo igual)")
        incidents.extend(parsed)
        print(f"[{kind}] lote {start}-{start + len(batch)} generado ({len(parsed)} incidencias)")
    return incidents


def generate_all() -> dict[str, list[dict]]:
    return {
        "historic": _generate_set("historic", _historic_plan(), "INC-2024"),
        "test": _generate_set("test", _small_set_plan(3), "INC-TEST"),
        "edge_cases": _generate_set("edge", _small_set_plan(2), "INC-EDGE"),
    }


def save_all(incidents_by_set: dict[str, list[dict]]) -> None:
    for set_name, incidents in incidents_by_set.items():
        out_dir = OUTPUT_DIR / set_name
        out_dir.mkdir(parents=True, exist_ok=True)
        for inc in incidents:
            path = out_dir / f"{inc['incident_id']}.json"
            path.write_text(json.dumps(inc, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Guardadas {len(incidents)} incidencias en {out_dir}")


if __name__ == "__main__":
    save_all(generate_all())
