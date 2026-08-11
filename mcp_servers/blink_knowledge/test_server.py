"""Pytest blink-knowledge — Sprint 2."""
from __future__ import annotations
import os
import tempfile
from pathlib import Path
import pytest


@pytest.fixture
def kb_temp(monkeypatch):
    """Cria KB fake com 3 artigos."""
    tmp = tempfile.mkdtemp()
    p = Path(tmp)
    (p / "01_medicos.md").write_text(
        "# Médicos\n\nDra. Karla atende oftalmologia.", encoding="utf-8"
    )
    (p / "18_convenios_nao_aceitos.md").write_text(
        "# Convênios não aceitos\n\nInas GDF não atendemos.", encoding="utf-8"
    )
    (p / "22_agenda_dra_karla.md").write_text(
        "# Agenda Dra. Karla\n\nSegunda e quarta na Asa Norte.", encoding="utf-8"
    )
    monkeypatch.setenv("BLINK_KB_PATH", tmp)
    # Recarrega o módulo para pegar a env nova
    import importlib
    from blink_knowledge import server as srv
    importlib.reload(srv)
    yield srv


def test_listar_artigos_kb_retorna_3(kb_temp):
    out = kb_temp.listar_artigos_kb()
    assert len(out) == 3
    slugs = {a["slug"] for a in out}
    assert "medicos" in slugs
    assert "convenios_nao_aceitos" in slugs
    assert "agenda_dra_karla" in slugs


def test_listar_artigos_inclui_uri(kb_temp):
    out = kb_temp.listar_artigos_kb()
    for a in out:
        assert a["uri"].startswith("blink://kb/")


def test_buscar_inas_acha_artigo_convenios(kb_temp):
    out = kb_temp.buscar_no_kb("Inas")
    assert len(out) >= 1
    assert any("convenios_nao_aceitos" in m["slug"] for m in out)


def test_buscar_termo_inexistente_retorna_vazio(kb_temp):
    out = kb_temp.buscar_no_kb("xyz123nonexistente")
    assert out == []


def test_buscar_termo_curto_rejeita(kb_temp):
    with pytest.raises(ValueError):
        kb_temp.buscar_no_kb("a")


def test_ler_artigo_kb_retorna_conteudo(kb_temp):
    txt = kb_temp.ler_artigo_kb("medicos")
    assert "Karla" in txt
    assert "oftalmologia" in txt


def test_ler_artigo_inexistente_levanta(kb_temp):
    with pytest.raises(ValueError):
        kb_temp.ler_artigo_kb("inexistente")


def test_kb_index_lista_todos(kb_temp):
    txt = kb_temp.kb_index()
    assert "medicos" in txt
    assert "convenios_nao_aceitos" in txt
    assert "Total de artigos: 3" in txt
