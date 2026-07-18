"""
Generador de dataset SINTÉTICO de incidencias (placeholder).

Materializa la modificación #1: decidir el dataset en la Semana 1 para no
bloquear las Semanas 3 y 8. La estrategia es "sintético primero": generamos
incidencias ITIL realistas con Claude y las guardamos en data/incidents/.
Más adelante sustituimos (o ampliamos) con datos reales anonimizados de Ellevio.

Este fichero está deliberadamente incompleto: lo terminaremos juntos cuando
lleguemos a ese paso. Aquí queda esbozado el enfoque y el schema de salida.
"""

from __future__ import annotations

import json
from pathlib import Path

from agentmind.models import complete

OUTPUT_DIR = Path(__file__).resolve().parents[1] / "data" / "incidents"

# Estructura objetivo de cada incidencia (alineada con IncidentState).
INCIDENT_SCHEMA_HINT = {
    "incident_id": "INC-XXXX",
    "raw_text": "descripción tal como la reportaría un usuario",
    "category": "área funcional / técnica",
    "affected_system": "sistema concreto",
    "severity": "low | medium | high | critical",
    "root_cause": "causa raíz real (para poder evaluar al RCA Agent)",
    "resolution": "cómo se resolvió",
}


def build_prompt(n: int) -> str:
    return (
        f"Genera {n} incidencias técnicas realistas de un entorno Salesforce en el "
        "sector energético europeo. Devuelve SOLO un array JSON. Cada objeto con las "
        f"claves: {list(INCIDENT_SCHEMA_HINT)}. Varía severidad y sistemas afectados."
    )


def generate(n: int = 10, profile: str = "smart") -> list[dict]:
    resp = complete(profile, [{"role": "user", "content": build_prompt(n)}])
    text = (resp.content or "").strip().removeprefix("```json").removesuffix("```").strip()
    return json.loads(text)


if __name__ == "__main__":
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    incidents = generate(n=10)
    for inc in incidents:
        path = OUTPUT_DIR / f"{inc['incident_id']}.json"
        path.write_text(json.dumps(inc, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Generadas {len(incidents)} incidencias en {OUTPUT_DIR}")
