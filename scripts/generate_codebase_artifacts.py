"""
Generador de artefactos de código sintéticos (S3 — corpus RAG, tool `search_codebase`).

10 fichas de feature (una por arquetipo, sin trocear) + 1 ficha de arquitectura
(troceada mecánicamente en `ingest_rag_corpus.py`, no aquí — se genera como
markdown con exactamente 6 `## Sección`) + 10 snippets de código (uno por
arquetipo, sin trocear: son de una sola responsabilidad por diseño).

Cada snippet lleva un campo `summary` en lenguaje natural además del código:
el código Apex/LWC crudo embebe mal contra una consulta en lenguaje natural
del agente ("error de validación de fecha al cerrar oportunidad"), así que
`embedding_text = summary + code_text`, no el código a solas.

Salida: JSON bajo
`data/codebase_artifacts/{feature_cards,architecture,code_snippets}/*.json`.
"""

from __future__ import annotations

import json
from pathlib import Path

from _corpus_common import ARCHETYPES, generate_json

BASE_DIR = Path(__file__).resolve().parent.parent / "data" / "codebase_artifacts"


def _feature_cards_prompt() -> str:
    rows = "\n".join(
        f'- artifact_id="FEAT-{a.id:03d}", title="{a.component}", '
        f'related_business_process="{a.business_process}", '
        f'contexto="{a.name}" (categoria={a.category}, sistema={a.system})'
        for a in ARCHETYPES
    )
    return f"""Genera un array JSON con {len(ARCHETYPES)} "fichas de feature" (feature
cards) de un org Salesforce CRM (sector energético europeo), una por fila
(respeta artifact_id/title/related_business_process EXACTAMENTE):

{rows}

Cada ficha describe la FUNCIONALIDAD (no el bug): qué objetos, clases,
validaciones y triggers involucra, y cuándo se disparan. Documento corto, un
solo tema (NO se trocea).

Cada objeto con EXACTAMENTE estas claves:
{{
  "artifact_id": str, "artifact_type": "feature_card", "title": str,
  "related_objects": [str, ...], "related_business_process": str,
  "content_text": str (4-6 frases: objetos/clases involucrados, validaciones, cuándo se dispara)
}}

Devuelve SOLO el array JSON, sin explicación ni fences."""


def _architecture_prompt() -> str:
    return """Genera la ficha de arquitectura simulada de un org Salesforce CRM
(sector energético europeo, mismo dominio que project/dominio-salesforce.md).

Debe ser un documento markdown con EXACTAMENTE 6 secciones "## <Nombre>":
1. Estructura de carpetas (organización de clases Apex, Flows, LWC en el org/repo)
2. Modelo de datos (objetos estándar y custom principales y sus relaciones)
3. Convenciones de nombrado (triggers, clases, flows, campos custom)
4. Ubicación de módulos (dónde vive cada capa: triggers, handlers, servicios, integraciones)
5. Patrones de triggers y flows (framework de triggers usado, patrón de Flows)
6. Capa de integración (cómo se conectan sistemas externos: SAP, middleware, APIs)

Cada sección 3-6 frases, concreta y técnica (nombres de carpetas/clases plausibles).

Devuelve SOLO un objeto JSON con estas claves:
{
  "artifact_id": "ARCH-001",
  "artifact_type": "architecture",
  "title": "Arquitectura del org Salesforce CRM",
  "markdown_content": str (el markdown completo con las 6 secciones "## ...")
}

Sin explicación ni fences adicionales."""


def _code_snippets_prompt() -> str:
    rows = "\n".join(
        f'- artifact_id="SNIP-{a.id:03d}", title="{a.component}", '
        f'related_business_process="{a.business_process}", '
        f'contexto="{a.name}" (categoria={a.category}, sistema={a.system})'
        for a in ARCHETYPES
    )
    return f"""Genera un array JSON con {len(ARCHETYPES)} snippets de código Apex/LWC
sintéticos de un org Salesforce CRM (sector energético europeo), uno por fila
(respeta artifact_id/title/related_business_process EXACTAMENTE):

{rows}

Cada snippet es el cuerpo (parcial, 15-30 líneas) de la clase/trigger/componente
protagonista del arquetipo, con comentarios de qué hace, y debe CONTENER
IMPLÍCITAMENTE el bug de ese arquetipo (para que un RCA que lea el código
pueda encontrar la causa raíz) — pero sin nombrarlo explícitamente como "bug".
Una sola responsabilidad por snippet (NO se trocea).

Cada objeto con EXACTAMENTE estas claves:
{{
  "artifact_id": str, "artifact_type": "code_snippet", "title": str,
  "related_objects": [str, ...], "related_business_process": str,
  "summary": str (1-2 frases en lenguaje natural: qué hace este código y qué síntoma produce),
  "code_text": str (el código, con \\n como separador de línea)
}}

Devuelve SOLO el array JSON, sin explicación ni fences."""


def generate_all() -> dict[str, list[dict] | dict]:
    feature_cards = generate_json(_feature_cards_prompt())
    print(f"Feature cards: {len(feature_cards)}")
    architecture = generate_json(_architecture_prompt())
    print("Architecture doc: generado")
    code_snippets = generate_json(_code_snippets_prompt())
    print(f"Code snippets: {len(code_snippets)}")
    return {"feature_cards": feature_cards, "architecture": architecture, "code_snippets": code_snippets}


def save_all(artifacts: dict) -> None:
    fc_dir = BASE_DIR / "feature_cards"
    arch_dir = BASE_DIR / "architecture"
    snip_dir = BASE_DIR / "code_snippets"
    for d in (fc_dir, arch_dir, snip_dir):
        d.mkdir(parents=True, exist_ok=True)

    for fc in artifacts["feature_cards"]:
        (fc_dir / f"{fc['artifact_id']}.json").write_text(
            json.dumps(fc, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    arch = artifacts["architecture"]
    (arch_dir / f"{arch['artifact_id']}.json").write_text(
        json.dumps(arch, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    for snip in artifacts["code_snippets"]:
        (snip_dir / f"{snip['artifact_id']}.json").write_text(
            json.dumps(snip, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    print(
        f"Guardados {len(artifacts['feature_cards'])} feature cards, "
        f"1 architecture doc, {len(artifacts['code_snippets'])} code snippets en {BASE_DIR}"
    )


if __name__ == "__main__":
    save_all(generate_all())
