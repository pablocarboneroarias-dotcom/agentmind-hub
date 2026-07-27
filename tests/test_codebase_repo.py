"""
Tests de la tool 5 del RCA Agent (S3): read_codebase_repo.

No necesita mock de modelo ni de DB (a diferencia de rag.py) — es lectura
directa de ficheros sobre codebase-toy-repo/, así que se testea sin dobles.
"""

from __future__ import annotations

from agentmind.codebase_repo import read_codebase_repo


def test_lee_fichero_existente():
    content = read_codebase_repo("src/triggers/OpportunityTrigger.cls")
    assert not content.startswith("Error")
    assert "trigger OpportunityTrigger" in content
    assert "Revenue_Recognition_Date__c" in content


def test_rechaza_path_traversal():
    result = read_codebase_repo("../../../../etc/passwd")
    assert result.startswith("Error")
    assert "fuera de codebase-toy-repo" in result


def test_rechaza_ruta_absoluta():
    result = read_codebase_repo("/etc/passwd")
    assert result.startswith("Error")
    assert "absolutas" in result


def test_fichero_inexistente_da_mensaje_claro():
    result = read_codebase_repo("src/triggers/NoExiste.cls")
    assert result.startswith("Error")
    assert "no existe" in result
