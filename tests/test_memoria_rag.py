"""Pytest do RAG de memória ativa (nível 1 do plano de aprendizagem).

Cobre:
 - chunkagem de arquivos longos
 - extração de título
 - indexação a partir de pasta sintética (sem depender da base real)
 - recuperação por similaridade com baseline
 - filtro por tipo (licao vs kb)
 - mensagem vazia → lista vazia
 - cutoff de similaridade mínima
 - formatação para prompt (sem citar paciente)
 - smoke test contra base real (skip se sklearn ausente)
"""
from __future__ import annotations

from pathlib import Path

import pytest

from voice_agent import memoria_rag as rag


# ---------------------------------------------------------------------------
# Pasta sintética compartilhada
# ---------------------------------------------------------------------------

@pytest.fixture
def fake_corpus(tmp_path):
    licoes = tmp_path / "licoes"
    kb = tmp_path / "kb"
    licoes.mkdir()
    kb.mkdir()
    (licoes / "marcela-nome-incompleto.md").write_text(
        "# Bug Marcela — nome incompleto\n\n"
        "Lia aceitou Marcela como nome completo. Deveria pedir sobrenome.\n"
        "Trava: avaliar_nome_paciente em voice_agent/nomes.py.\n",
        encoding="utf-8",
    )
    (licoes / "cobranca-antes-slot.md").write_text(
        "# Cobrei sinal sem oferecer slot\n\n"
        "Lia cobrou R$ 305,50 sinal antes de oferecer horário concreto.\n"
        "Trava: _viola_cobranca_antes_slot no responder.py.\n",
        encoding="utf-8",
    )
    (kb / "convenios.md").write_text(
        "# Convênios aceitos\n\n"
        "Inas GDF NÃO é aceito. Saúde Caixa é aceito. Bradesco recusado.\n",
        encoding="utf-8",
    )
    (kb / "valores.md").write_text(
        "# Valores por médico\n\n"
        "Dra. Karla pediatria R$ 611. Dr. Fabrício catarata R$ 297.\n",
        encoding="utf-8",
    )
    return [(licoes, "licao"), (kb, "kb")]


@pytest.fixture
def indice(fake_corpus):
    return rag.construir_indice(pastas_extras=fake_corpus)


# ---------------------------------------------------------------------------
# Indexação
# ---------------------------------------------------------------------------

class TestIndexacao:

    def test_carrega_4_arquivos(self, indice):
        # 2 lições + 2 KB.
        assert indice.total() == 4
        tipos = sorted(t.fonte_tipo for t in indice.trechos)
        assert tipos == ["kb", "kb", "licao", "licao"]

    def test_titulos_extraidos(self, indice):
        titulos = [t.titulo for t in indice.trechos]
        assert "Bug Marcela — nome incompleto" in titulos
        assert "Convênios aceitos" in titulos

    def test_indice_vazio_para_pastas_inexistentes(self, tmp_path):
        idx = rag.construir_indice(
            pastas_extras=[(tmp_path / "nada", "licao")],
        )
        assert idx.total() == 0


class TestChunkagem:

    def test_arquivo_curto_um_chunk(self):
        chunks = rag._chunkar("texto curto", max_chars=1500)
        assert chunks == ["texto curto"]

    def test_arquivo_longo_quebra_em_paragrafos(self):
        p1 = "A" * 800
        p2 = "B" * 800
        p3 = "C" * 800
        texto = f"{p1}\n\n{p2}\n\n{p3}"
        chunks = rag._chunkar(texto, max_chars=1500)
        assert len(chunks) >= 2
        # Soma das partes preserva todo conteúdo (sem perda)
        recombinado = "".join(chunks)
        assert "A" * 800 in recombinado

    def test_paragrafo_gigante_corta_no_limite(self):
        gigante = "X" * 5000
        chunks = rag._chunkar(gigante, max_chars=1500)
        assert all(len(c) <= 1500 for c in chunks)
        assert sum(len(c) for c in chunks) == 5000


# ---------------------------------------------------------------------------
# Recuperação
# ---------------------------------------------------------------------------

class TestRecuperacao:

    def test_recupera_licao_marcela_quando_query_menciona_nome(self, indice):
        res = rag.recuperar_licoes_relevantes(
            "paciente respondeu Marcela como nome incompleto",
            indice=indice, k=2, similaridade_minima=0.01,
        )
        assert res, "deveria recuperar algo"
        topo = res[0]
        assert "Marcela" in topo.titulo or "marcela" in topo.fonte.lower()

    def test_recupera_kb_para_convenio(self, indice):
        # Query enxuta — "Inas GDF" é termo único do KB convênios.
        res = rag.recuperar_licoes_relevantes(
            "Inas GDF",
            indice=indice, k=2, similaridade_minima=0.01,
        )
        assert res
        # Verifica título OU conteúdo — TF-IDF pode rankear por qualquer.
        assert any(
            "conveni" in r.titulo.lower() or "inas" in r.conteudo.lower()
            for r in res
        )

    def test_recupera_valores_quando_pergunta_e_valor(self, indice):
        res = rag.recuperar_licoes_relevantes(
            "qual valor consulta Dra Karla",
            indice=indice, k=2, similaridade_minima=0.01,
        )
        assert res
        assert any("valor" in r.titulo.lower() for r in res)

    def test_mensagem_vazia_devolve_vazio(self, indice):
        assert rag.recuperar_licoes_relevantes("", indice=indice) == []
        assert rag.recuperar_licoes_relevantes("   ", indice=indice) == []

    def test_filtra_por_tipo_licao(self, indice):
        res = rag.recuperar_licoes_relevantes(
            "Marcela nome incompleto",
            indice=indice, k=5, similaridade_minima=0.01,
            filtrar_tipo="licao",
        )
        assert res
        assert all(r.fonte_tipo == "licao" for r in res)

    def test_filtra_por_tipo_kb(self, indice):
        res = rag.recuperar_licoes_relevantes(
            "Inas GDF",
            indice=indice, k=5, similaridade_minima=0.01,
            filtrar_tipo="kb",
        )
        assert res
        assert all(r.fonte_tipo == "kb" for r in res)

    def test_corte_por_similaridade_minima(self, indice):
        # Query completamente fora do escopo — deve ficar abaixo do mínimo
        res = rag.recuperar_licoes_relevantes(
            "pizza margherita italiana tomate",
            indice=indice, k=5, similaridade_minima=0.30,
        )
        assert res == []

    def test_k_limita_resultados(self, indice):
        res = rag.recuperar_licoes_relevantes(
            "consulta paciente",
            indice=indice, k=1, similaridade_minima=0.0,
        )
        assert len(res) <= 1


# ---------------------------------------------------------------------------
# Formatação
# ---------------------------------------------------------------------------

class TestFormatarParaPrompt:

    def test_vazio_devolve_string_vazia(self):
        assert rag.formatar_para_prompt([]) == ""

    def test_inclui_aviso_uso_interno(self):
        t = rag.TrechoRelevante(
            fonte="x.md", titulo="Teste", conteudo="conteúdo qualquer",
            fonte_tipo="licao", similaridade=0.5,
        )
        out = rag.formatar_para_prompt([t])
        assert "uso interno — não citar ao paciente" in out
        assert "Teste" in out
        assert "[LIÇÃO]" in out

    def test_kb_aparece_com_tag_correta(self):
        t = rag.TrechoRelevante(
            fonte="x.md", titulo="Convênios", conteudo="x",
            fonte_tipo="kb", similaridade=0.2,
        )
        out = rag.formatar_para_prompt([t])
        assert "[KB]" in out

    def test_trecho_longo_e_truncado(self):
        # 2000 chars > 800 limite → trunca
        t = rag.TrechoRelevante(
            fonte="x.md", titulo="Longo", conteudo="A" * 2000,
            fonte_tipo="licao", similaridade=0.3,
        )
        out = rag.formatar_para_prompt([t])
        assert "[...]" in out


# ---------------------------------------------------------------------------
# Diagnóstico + cache
# ---------------------------------------------------------------------------

class TestDiagnostico:

    def test_diagnostico_devolve_chaves_esperadas(self):
        # Não usa fake_corpus — testa o caminho real.
        rag.limpar_cache()
        d = rag.diagnostico()
        # Pode ser ok=True ou ok=False; aceitar ambos com chaves estruturadas.
        assert "ok" in d
        if d["ok"]:
            assert "total_trechos" in d
            assert "por_tipo" in d


class TestCache:

    def test_obter_indice_retorna_mesmo_objeto(self):
        rag.limpar_cache()
        a = rag.obter_indice()
        b = rag.obter_indice()
        assert a is b

    def test_forcar_rebuild_cria_novo(self):
        rag.limpar_cache()
        a = rag.obter_indice()
        b = rag.obter_indice(forcar_rebuild=True)
        assert a is not b

    def test_limpar_cache_forca_reconstrucao(self):
        rag.limpar_cache()
        a = rag.obter_indice()
        rag.limpar_cache()
        b = rag.obter_indice()
        assert a is not b


# ---------------------------------------------------------------------------
# Smoke test contra base real
# ---------------------------------------------------------------------------

class TestBaseReal:
    """Sanity-check contra os arquivos do repo. Skip se sklearn ausente."""

    def test_base_real_carrega_mais_que_50_trechos(self):
        if not rag._SKLEARN_OK:
            pytest.skip("sklearn não disponível")
        rag.limpar_cache()
        idx = rag.obter_indice()
        # Hoje (31/05/2026) base tem ~200 trechos. Tolerância larga.
        assert idx.total() > 50, (
            f"esperado > 50, obtido {idx.total()} — base murchou?"
        )

    def test_query_real_marcela_acha_licao(self):
        if not rag._SKLEARN_OK:
            pytest.skip("sklearn não disponível")
        rag.limpar_cache()
        res = rag.recuperar_licoes_relevantes(
            "lia gravou Marcela como nome paciente sem sobrenome",
            k=3,
        )
        assert res, "base real deveria recuperar algo"
        # Deveria aparecer algo relacionado a paciente/nome
        encontrou_relevante = any(
            "paciente" in r.conteudo.lower() or "nome" in r.conteudo.lower()
            for r in res
        )
        assert encontrou_relevante

    def test_query_real_inas_gdf_acha_convenios(self):
        if not rag._SKLEARN_OK:
            pytest.skip("sklearn não disponível")
        rag.limpar_cache()
        res = rag.recuperar_licoes_relevantes(
            "paciente perguntou Inas GDF é aceito?", k=3,
        )
        assert res
        assert any("conveni" in r.titulo.lower() or "conveni" in r.fonte.lower()
                   for r in res)
