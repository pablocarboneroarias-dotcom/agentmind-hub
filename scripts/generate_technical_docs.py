"""
Generador de documentación técnica sintética del org (S3 — corpus RAG).

25 documentos: 10 ligados a los componentes de los 10 arquetipos de
`project/dominio-salesforce.md` (uno por componente crítico) + 15 de "ruido"
(componentes reales del org, no relacionados con ningún bug conocido, para
que el retrieval no sea trivial).

Los campos se generan DISCRETOS (what_it_does / when_it_triggers /
validations), no como un único bloque de texto, para que la concatenación de
`embedding_text` en `ingest_rag_corpus.py` sea determinista y siga
exactamente la receta del spec: "component_name + qué hace + cuándo se
dispara + validaciones que aplica + related_objects + related_business_process".

Salida: un JSON por documento en `data/technical_docs/DOC-XXX.json`.
"""

from __future__ import annotations

import json
from pathlib import Path

from _corpus_common import ARCHETYPES, generate_json

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "data" / "technical_docs"

# document_type por arquetipo (el enum del spec es orientativo, no un CHECK
# real en Postgres — para arquetipos que no son código puro se usa el bucket
# más cercano de los 4 nombrados: 'trigger' | 'flow' | 'integration' | 'permission_rule').
DOC_TYPE_BY_ARCHETYPE_ID: dict[int, str] = {
    1: "trigger", 2: "flow", 3: "integration", 4: "permission_rule",
    5: "permission_rule", 6: "trigger", 7: "flow", 8: "flow",
    9: "flow", 10: "trigger",
}

NOISE_COUNT = 15
BATCH_SIZE = 13


def _archetype_prompt() -> str:
    rows = []
    for a in ARCHETYPES:
        rows.append(
            f'- doc_id="DOC-{a.id:03d}", document_type="{DOC_TYPE_BY_ARCHETYPE_ID[a.id]}", '
            f'component_name="{a.component}", related_business_process="{a.business_process}", '
            f'contexto="{a.name}" (categoria={a.category}, sistema={a.system})'
        )
    rows_text = "\n".join(rows)
    return f"""Genera un array JSON con {len(ARCHETYPES)} documentos de documentación
técnica interna de un org Salesforce CRM (sector energético europeo), uno por
cada fila (respeta doc_id/document_type/component_name/related_business_process
EXACTAMENTE):

{rows_text}

Cada documento describe el componente TAL COMO ES ANTES del bug (documentación
técnica normal del org, no la incidencia en sí). Cada objeto con EXACTAMENTE
estas claves:
{{
  "doc_id": str, "document_type": str, "component_name": str,
  "related_objects": [str, ...] (objetos Salesforce reales),
  "related_business_process": str,
  "what_it_does": str (1-2 frases, qué hace el componente),
  "when_it_triggers": str (1 frase, cuándo se dispara/ejecuta),
  "validations": str (1-2 frases, qué validaciones o reglas de negocio aplica)
}}

Devuelve SOLO el array JSON, sin explicación ni fences."""


def _noise_prompt(start_id: int, n: int) -> str:
    return f"""Genera un array JSON con {n} documentos de documentación técnica
interna de un org Salesforce CRM (sector energético europeo, mismo dominio que
`project/dominio-salesforce.md`), describiendo componentes REALES del org que
funcionan correctamente y NO están relacionados con ningún bug conocido
(ruido para un sistema de búsqueda semántica: deben ser plausibles pero no
coincidir con: OpportunityTrigger, Case_Onboarding_Flow, SAP_Middleware_Connector,
Account_Sharing_Rule_EMEA, Account_Dedup_Rule, CPQ_Pricing_Batch_Job,
CPQ_Bundle_Pricing_Rule, Sales_Pipeline_Dashboard, Lead_Welcome_Workflow_Rule,
ContractManagementLWC).

Usa doc_id correlativos DOC-{start_id:03d} a DOC-{start_id + n - 1:03d}.
document_type debe ser uno de: "trigger", "flow", "integration", "permission_rule".
related_business_process debe ser uno de estos 14 códigos EXACTOS: CONTRACTING,
OWNERSHIP_CHANGE, CONTRACT_RENEWAL, SAP_INTEGRATION, CUSTOMER_SERVICE, COMPLAINTS,
BILLING, COLLECTIONS, METER_READING, REPORTING, GENERAL_INQUIRY, SALES_FLOW, CPQ,
DATA_INTEGRITY.

Cada objeto con EXACTAMENTE estas claves:
{{
  "doc_id": str, "document_type": str, "component_name": str,
  "related_objects": [str, ...], "related_business_process": str,
  "what_it_does": str, "when_it_triggers": str, "validations": str
}}

Devuelve SOLO el array JSON, sin explicación ni fences."""


def generate_all() -> list[dict]:
    docs = generate_json(_archetype_prompt())
    print(f"Arquetipos: {len(docs)} docs generados")

    remaining = NOISE_COUNT
    next_id = len(ARCHETYPES) + 1
    while remaining > 0:
        batch_n = min(BATCH_SIZE, remaining)
        docs.extend(generate_json(_noise_prompt(next_id, batch_n)))
        print(f"Ruido: +{batch_n} docs (total {len(docs)})")
        next_id += batch_n
        remaining -= batch_n
    return docs


def save_all(docs: list[dict]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for doc in docs:
        path = OUTPUT_DIR / f"{doc['doc_id']}.json"
        path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Guardados {len(docs)} documentos técnicos en {OUTPUT_DIR}")


if __name__ == "__main__":
    save_all(generate_all())
