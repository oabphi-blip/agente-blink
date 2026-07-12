"""Pytest do vector store dos bugs (Camada 2 memória ativa)."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from voice_agent.memoria_vector import (
    buscar_bug_similar,
    contar_bugs_indexados,
    extrair_chunks_bugs,
    indexar_claude_md,
    invalidar_cache,
)


CLAUDE_MD_MOCK = """# CLAUDE.md — teste

Preâmbulo qualquer.

### 0. (11/07/2026) Bug C-99 — Lia inventou "reconferir com calendário" (Mariana X 000001)

Corpo do bug C-99. Descreve o padrão "reconferir com calendário"
que a Lia gerou quando Medware retornou timeout. Fix: adicionar
frase banida em oferta_deterministica.

### 0. (12/07/2026) Bug C-100 — Convênio Afego não mapeado (Mariana Lopes 000002)

Corpo do bug C-100. Kommo grava "Afego" (1 F) mas Medware espera
"AFFEGO" (2 F). Sem alias, gravação falha.

## Outra seção

Não é bug — não deve ser indexado.
"""


@pytest.fixture
def db_temp():
    """DB SQLite temporário isolado por teste."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.unlink(path)
    yield path
    invalidar_cache()
    if os.path.exists(path):
        os.unlink(path)


@pytest.fixture
def claude_md_temp():
    """Arquivo CLAUDE.md mock temporário."""
    fd, path = tempfile.mkstemp(suffix=".md")
    os.close(fd)
    Path(path).write_text(CLAUDE_MD_MOCK, encoding="utf-8")
    yield path
    if os.path.exists(path):
        os.unlink(path)


class TestExtrairChunks:
    def test_extrai_2_bugs_do_mock(self):
        chunks = extrair_chunks_bugs(CLAUDE_MD_MOCK)
        assert len(chunks) == 2
        ids = [c["bug_id"] for c in chunks]
        assert "C-99" in ids
        assert "C-100" in ids

    def test_ignora_secoes_nao_bug(self):
        chunks = extrair_chunks_bugs(CLAUDE_MD_MOCK)
        for c in chunks:
            assert "Outra seção" not in c["corpo"] or c["bug_id"].startswith("C-")

    def test_texto_vazio_retorna_lista_vazia(self):
        assert extrair_chunks_bugs("") == []

    def test_captura_titulo(self):
        chunks = extrair_chunks_bugs(CLAUDE_MD_MOCK)
        c99 = next(c for c in chunks if c["bug_id"] == "C-99")
        assert "reconferir" in c99["titulo"].lower()


class TestIndexacao:
    def test_indexa_bugs_do_mock(self, claude_md_temp, db_temp):
        r = indexar_claude_md(caminho_md=claude_md_temp, db_path=db_temp)
        assert r["inseridos"] == 2
        assert r["total_bugs"] == 2

    def test_reindexacao_incremental(self, claude_md_temp, db_temp):
        # Primeiro run: 2 inseridos
        r1 = indexar_claude_md(caminho_md=claude_md_temp, db_path=db_temp)
        assert r1["inseridos"] == 2

        # Segundo run: 0 novos (sem mudança)
        r2 = indexar_claude_md(caminho_md=claude_md_temp, db_path=db_temp)
        assert r2["inseridos"] == 0
        assert r2["sem_mudanca"] == 2

    def test_contagem(self, claude_md_temp, db_temp):
        indexar_claude_md(caminho_md=claude_md_temp, db_path=db_temp)
        assert contar_bugs_indexados(db_path=db_temp) == 2

    def test_arquivo_inexistente_nao_estoura(self, db_temp):
        r = indexar_claude_md(caminho_md="/nao/existe.md", db_path=db_temp)
        assert "erro" in r


class TestBusca:
    def test_busca_por_convenio_afego(self, claude_md_temp, db_temp):
        indexar_claude_md(caminho_md=claude_md_temp, db_path=db_temp)
        invalidar_cache()
        res = buscar_bug_similar(
            "convênio Afego não mapeado no Medware",
            db_path=db_temp,
            top_k=3,
            threshold=0.01,
        )
        assert len(res) > 0
        # Top-1 deve ser C-100
        assert res[0]["bug_id"] == "C-100"

    def test_busca_por_reconferir(self, claude_md_temp, db_temp):
        indexar_claude_md(caminho_md=claude_md_temp, db_path=db_temp)
        invalidar_cache()
        res = buscar_bug_similar(
            "Lia disse reconferir com calendário",
            db_path=db_temp,
            top_k=3,
            threshold=0.01,
        )
        assert len(res) > 0
        assert res[0]["bug_id"] == "C-99"

    def test_query_vazia_retorna_lista_vazia(self, claude_md_temp, db_temp):
        indexar_claude_md(caminho_md=claude_md_temp, db_path=db_temp)
        assert buscar_bug_similar("", db_path=db_temp) == []
        assert buscar_bug_similar("   ", db_path=db_temp) == []

    def test_top_k_limita_resultados(self, claude_md_temp, db_temp):
        indexar_claude_md(caminho_md=claude_md_temp, db_path=db_temp)
        invalidar_cache()
        res = buscar_bug_similar(
            "bug", db_path=db_temp, top_k=1, threshold=0.0,
        )
        assert len(res) <= 1

    def test_threshold_filtra_matches_fracos(self, claude_md_temp, db_temp):
        indexar_claude_md(caminho_md=claude_md_temp, db_path=db_temp)
        invalidar_cache()
        # Threshold 0.99 = quase certeza que nada bate
        res = buscar_bug_similar(
            "assunto totalmente não relacionado xyz",
            db_path=db_temp, threshold=0.99,
        )
        assert res == []

    def test_toggle_off(self, monkeypatch, claude_md_temp, db_temp):
        indexar_claude_md(caminho_md=claude_md_temp, db_path=db_temp)
        monkeypatch.setenv("MEMORIA_VECTOR_ATIVADO", "0")
        assert buscar_bug_similar("Afego", db_path=db_temp) == []


class TestIntegracaoClaudeMdReal:
    """Roda contra o CLAUDE.md real do projeto — smoke E2E."""

    def test_indexa_claude_md_real(self, db_temp):
        r = indexar_claude_md(caminho_md="CLAUDE.md", db_path=db_temp)
        assert r.get("total_bugs", 0) >= 5, (
            f"CLAUDE.md deveria ter >=5 bugs indexados. Retornou {r}"
        )

    def test_busca_c_43_afego_no_claude_md_real(self, db_temp):
        indexar_claude_md(caminho_md="CLAUDE.md", db_path=db_temp)
        invalidar_cache()
        res = buscar_bug_similar(
            "convênio Afego não mapeado",
            db_path=db_temp,
            top_k=3,
        )
        assert len(res) > 0
        ids = [r["bug_id"] for r in res]
        assert "C-43" in ids
