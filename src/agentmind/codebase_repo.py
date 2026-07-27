"""
Tool 5 del RCA Agent (S3): lectura EXACTA (no semántica) de un fichero real,
sobre `codebase-toy-repo/` — ver `docs/specs/rca-decisiones-s3.md`.

Complementa a `search_codebase` (RAG semántico sobre `codebase_artifacts`):
cuando el agente ya sabe (por el RAG) qué fichero quiere mirar, esta tool se
lo lee tal cual, sin resumir ni reinterpretar — el caso de uso típico es
verificar si algo que dice un doc/ficha indexado ("implementa retry logic")
es cierto en el código real.

Gobernanza no negociable (read-only estricto):
  - nunca escribe/mueve/borra nada — solo `read_text`,
  - la ruta resuelta debe quedar estrictamente dentro de codebase-toy-repo/
    (se rechaza cualquier ../ o ruta absoluta que se salga), verificado con
    `Path.relative_to`, no con comparación de strings,
  - fichero inexistente -> mensaje de texto, nunca una excepción sin manejar,
  - límite de tamaño de lectura (evita que un fichero enorme reviente el
    presupuesto de tokens del agente).
"""

from __future__ import annotations

from pathlib import Path

from .observability import traced

REPO_ROOT = (Path(__file__).resolve().parents[2] / "codebase-toy-repo").resolve()
MAX_READ_BYTES = 50_000


@traced("codebase_repo.read_codebase_repo", run_type="tool")
def read_codebase_repo(path: str) -> str:
    """Lee el contenido de un fichero dentro de codebase-toy-repo/.

    `path`: ruta relativa a la raíz de codebase-toy-repo/
    (ej. "src/triggers/OpportunityTrigger.cls").
    """
    requested = Path(path)
    if requested.is_absolute():
        return f"Error: no se permiten rutas absolutas: {path!r}"

    target = (REPO_ROOT / requested).resolve()
    try:
        target.relative_to(REPO_ROOT)
    except ValueError:
        return f"Error: ruta fuera de codebase-toy-repo/: {path!r}"

    if not target.exists():
        return f"Error: el fichero '{path}' no existe en codebase-toy-repo/."
    if not target.is_file():
        return f"Error: '{path}' no es un fichero (¿es un directorio?)."

    size = target.stat().st_size
    if size > MAX_READ_BYTES:
        return (
            f"Error: '{path}' pesa {size} bytes, supera el límite de lectura "
            f"de {MAX_READ_BYTES} bytes. Pide un fichero más pequeño o una "
            "sección concreta."
        )

    return target.read_text(encoding="utf-8", errors="replace")
