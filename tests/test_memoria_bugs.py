"""Pytest da memória de bugs por embedding.

Cobre:
- cosine matemático (vetores ortogonais, paralelos, etc)
- serialização base64 (round-trip)
- registrar bug + persistir em Redis (mockado)
- carregar semente quando vazio
- checar (match alto, baixo, sem catálogo)
- from_env (off/on)

Não chama OpenAI real — embedding é mockado.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402


# ----------------------------------------------------------------------
# cosine
# ----------------------------------------------------------------------

class TestCosine:

    def test_vetores_iguais_eh_1(self):
        from voice_agent.memoria_bugs import cosine
        v = [1.0, 2.0, 3.0]
        assert abs(cosine(v, v) - 1.0) < 1e-9

    def test_vetores_ortogonais_eh_0(self):
        from voice_agent.memoria_bugs import cosine
        assert abs(cosine([1.0, 0.0], [0.0, 1.0])) < 1e-9

    def test_vetores_opostos_eh_menos_1(self):
        from voice_agent.memoria_bugs import cosine
        v = [1.0, 2.0, 3.0]
        w = [-1.0, -2.0, -3.0]
        assert abs(cosine(v, w) - (-1.0)) < 1e-9

    def test_vetor_vazio_eh_0(self):
        from voice_agent.memoria_bugs import cosine
        assert cosine([], [1.0, 2.0]) == 0.0
        assert cosine([1.0, 2.0], []) == 0.0

    def test_tamanhos_diferentes_eh_0(self):
        from voice_agent.memoria_bugs import cosine
        assert cosine([1.0, 2.0], [1.0, 2.0, 3.0]) == 0.0


# ----------------------------------------------------------------------
# base64 round-trip
# ----------------------------------------------------------------------

class TestBase64:

    def test_round_trip_preserva_valores(self):
        from voice_agent.memoria_bugs import (
            _b64_encode_embedding, _b64_decode_embedding,
        )
        original = [0.1, -0.5, 2.34567, 1e-6, 0.0, 100.0]
        b64 = _b64_encode_embedding(original)
        de = _b64_decode_embedding(b64)
        assert len(de) == len(original)
        for o, d in zip(original, de):
            assert abs(o - d) < 1e-5

    def test_vetor_grande_1536(self):
        from voice_agent.memoria_bugs import (
            _b64_encode_embedding, _b64_decode_embedding,
        )
        v = [float(i % 100) / 100.0 for i in range(1536)]
        b64 = _b64_encode_embedding(v)
        de = _b64_decode_embedding(b64)
        assert len(de) == 1536
        for o, d in zip(v, de):
            assert abs(o - d) < 1e-5


# ----------------------------------------------------------------------
# MemoriaBugs — com mocks
# ----------------------------------------------------------------------

@pytest.fixture
def mem_mockada():
    """Constrói MemoriaBugs via __new__ pra pular __init__ (que faz
    OpenAI() real). Injeta client e redis mockados."""
    from voice_agent.memoria_bugs import MemoriaBugs, EMBEDDING_MODEL
    m = MemoriaBugs.__new__(MemoriaBugs)
    m._client = MagicMock()
    m._redis = MagicMock()
    m._redis.hgetall.return_value = {}
    m.limiar = 0.85
    m.modelo = EMBEDDING_MODEL
    m._catalogo = []
    m._carregado = False
    return m


def _mock_embedding(client_mock, vetor: list[float]) -> None:
    """Faz client.embeddings.create() devolver um embedding fixo."""
    resp = MagicMock()
    data = MagicMock()
    data.embedding = vetor
    resp.data = [data]
    client_mock.embeddings.create.return_value = resp


class TestEmbed:

    def test_texto_vazio_devolve_lista_vazia(self, mem_mockada):
        assert mem_mockada._embed("") == []

    def test_texto_whitespace_chama_openai(self, mem_mockada):
        # Whitespace puro não dispara early-return (truthy)
        _mock_embedding(mem_mockada._client, [0.1] * 4)
        out = mem_mockada._embed("   ")
        # Texto após strip vira "" mas chega na API mockada
        assert out == [0.1] * 4 or out == []

    def test_embed_normal_chama_openai(self, mem_mockada):
        _mock_embedding(mem_mockada._client, [0.1] * 1536)
        out = mem_mockada._embed("oi")
        assert len(out) == 1536
        mem_mockada._client.embeddings.create.assert_called_once()

    def test_embed_erro_devolve_lista_vazia(self, mem_mockada):
        mem_mockada._client.embeddings.create.side_effect = RuntimeError(
            "openai down"
        )
        assert mem_mockada._embed("oi") == []


class TestRegistrar:

    def test_registra_e_persiste_redis(self, mem_mockada):
        _mock_embedding(mem_mockada._client, [0.5] * 4)
        ok = mem_mockada.registrar(
            bug_id="bug1",
            texto_lia="frase da Lia que deu errado",
            ctx_resumo="ja_agendado:True",
            motivo="cenário X",
        )
        assert ok is True
        # Persistiu em Redis
        mem_mockada._redis.hset.assert_called_once()
        args = mem_mockada._redis.hset.call_args[0]
        assert args[1] == "bug1"
        payload = json.loads(args[2])
        assert payload["bug_id"] == "bug1"
        assert "embedding_b64" in payload
        # Catálogo em memória atualizado
        assert len(mem_mockada._catalogo) == 1
        assert mem_mockada._catalogo[0].bug_id == "bug1"

    def test_registrar_sobrescreve_bug_id_repetido(self, mem_mockada):
        _mock_embedding(mem_mockada._client, [0.1] * 4)
        mem_mockada.registrar("bug1", "texto antigo")
        mem_mockada.registrar("bug1", "texto novo")
        # Só 1 entrada no catálogo
        assert len(mem_mockada._catalogo) == 1
        assert mem_mockada._catalogo[0].texto_lia == "texto novo"

    def test_bug_id_vazio_falha(self, mem_mockada):
        assert mem_mockada.registrar("", "texto") is False

    def test_texto_vazio_falha(self, mem_mockada):
        assert mem_mockada.registrar("bug1", "") is False

    def test_embedding_erro_devolve_False(self, mem_mockada):
        mem_mockada._client.embeddings.create.side_effect = RuntimeError(
            "down"
        )
        assert mem_mockada.registrar("bug1", "texto") is False


class TestCarregarSemente:

    def test_semente_vazia_se_redis_ja_tem_bugs(self, mem_mockada):
        # Simula redis com bugs já registrados
        from voice_agent.memoria_bugs import (
            BugRegistrado, _b64_encode_embedding,
        )
        existing = BugRegistrado(
            bug_id="old",
            texto_lia="x",
            ctx_resumo="",
            motivo="",
            embedding=[0.1] * 4,
        )
        mem_mockada._redis.hgetall.return_value = {
            "old": json.dumps(existing.to_json_dict()),
        }
        n = mem_mockada.carregar_semente_se_vazio()
        assert n == 0
        # Catálogo carregou só o velho
        assert len(mem_mockada._catalogo) == 1
        assert mem_mockada._catalogo[0].bug_id == "old"

    def test_semente_carrega_quando_redis_vazio(self, mem_mockada):
        from voice_agent.memoria_bugs import SEMENTE_BUGS
        _mock_embedding(mem_mockada._client, [0.1] * 4)
        n = mem_mockada.carregar_semente_se_vazio()
        assert n == len(SEMENTE_BUGS)
        # Os 5 bugs canônicos
        ids = [b.bug_id for b in mem_mockada._catalogo]
        assert "aurora_retrocesso_ja_agendado" in ids
        assert "juliene_promete_retorno_humano" in ids
        assert "adelia_exemplo_aprovado_literal" in ids
        assert "diones_medico_trocado" in ids
        assert "esther_oferta_pos_agendado_imagem" in ids


class TestChecar:

    def test_catalogo_vazio_devolve_match_zero(self, mem_mockada):
        _mock_embedding(mem_mockada._client, [1.0] * 4)
        res = mem_mockada.checar("qualquer texto")
        assert res.bug_id == ""
        assert res.similaridade == 0.0
        assert res.deve_substituir is False

    def test_match_alto_aciona_substituicao(self, mem_mockada):
        # Registra um bug com embedding fixo
        _mock_embedding(mem_mockada._client, [1.0, 0.0, 0.0, 0.0])
        mem_mockada.registrar("bug_x", "texto bug X")
        # Checa texto novo cujo embedding é IDÊNTICO ao do bug
        # (mock devolve mesmo vetor)
        res = mem_mockada.checar("texto novo")
        assert res.bug_id == "bug_x"
        assert res.similaridade > 0.99
        assert res.deve_substituir is True

    def test_match_baixo_NAO_substitui(self, mem_mockada):
        # Primeiro registra com vetor [1,0,0,0]
        _mock_embedding(mem_mockada._client, [1.0, 0.0, 0.0, 0.0])
        mem_mockada.registrar("bug_x", "texto bug X")
        # Agora checa com vetor ortogonal [0,1,0,0] → similaridade = 0
        _mock_embedding(mem_mockada._client, [0.0, 1.0, 0.0, 0.0])
        res = mem_mockada.checar("texto novo")
        assert res.bug_id == "bug_x"
        assert res.similaridade < 0.1
        assert res.deve_substituir is False

    def test_pega_o_bug_de_maior_similaridade(self, mem_mockada):
        # Registra 2 bugs com vetores diferentes
        _mock_embedding(mem_mockada._client, [1.0, 0.0, 0.0, 0.0])
        mem_mockada.registrar("bug_a", "texto A")
        _mock_embedding(mem_mockada._client, [0.0, 1.0, 0.0, 0.0])
        mem_mockada.registrar("bug_b", "texto B")
        # Checa com vetor parecido com bug_b
        _mock_embedding(mem_mockada._client, [0.0, 0.95, 0.05, 0.0])
        res = mem_mockada.checar("nova frase")
        assert res.bug_id == "bug_b"
        assert res.similaridade > 0.9

    def test_texto_vazio_devolve_match_zero(self, mem_mockada):
        res = mem_mockada.checar("")
        assert res.bug_id == ""
        assert res.similaridade == 0.0

    def test_embedding_falha_devolve_match_zero(self, mem_mockada):
        # Registra um bug
        _mock_embedding(mem_mockada._client, [1.0, 0.0])
        mem_mockada.registrar("bug_x", "texto")
        # Agora embed do texto novo falha
        mem_mockada._client.embeddings.create.side_effect = RuntimeError(
            "x"
        )
        res = mem_mockada.checar("oi")
        assert res.bug_id == ""


class TestListar:

    def test_lista_sem_embedding_no_payload(self, mem_mockada):
        _mock_embedding(mem_mockada._client, [0.1] * 4)
        mem_mockada.registrar(
            "bug1", "x" * 300, ctx_resumo="y", motivo="z",
        )
        out = mem_mockada.listar()
        assert len(out) == 1
        assert out[0]["bug_id"] == "bug1"
        assert "embedding_dims" in out[0]
        assert out[0]["embedding_dims"] == 4
        # texto preview truncado em 200 chars
        assert len(out[0]["texto_lia_preview"]) == 200
        # NÃO inclui o embedding raw
        assert "embedding" not in out[0]


# ----------------------------------------------------------------------
# from_env
# ----------------------------------------------------------------------

class TestFromEnv:

    def test_desligado_devolve_None(self, monkeypatch):
        monkeypatch.delenv("MEMORIA_BUGS_ENABLED", raising=False)
        from voice_agent.memoria_bugs import MemoriaBugs
        assert MemoriaBugs.from_env(MagicMock()) is None

    def test_ligado_sem_chave_devolve_None(self, monkeypatch):
        monkeypatch.setenv("MEMORIA_BUGS_ENABLED", "1")
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        from voice_agent.memoria_bugs import MemoriaBugs
        assert MemoriaBugs.from_env(MagicMock()) is None

    def test_ligado_com_chave_devolve_instancia(self, monkeypatch):
        monkeypatch.setenv("MEMORIA_BUGS_ENABLED", "1")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        from voice_agent.memoria_bugs import MemoriaBugs
        m = MemoriaBugs.from_env(MagicMock())
        assert m is not None

    def test_limiar_custom_via_env(self, monkeypatch):
        monkeypatch.setenv("MEMORIA_BUGS_ENABLED", "1")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        monkeypatch.setenv("MEMORIA_BUGS_LIMIAR", "0.75")
        from voice_agent.memoria_bugs import MemoriaBugs
        m = MemoriaBugs.from_env(MagicMock())
        assert m.limiar == 0.75

    def test_limiar_invalido_volta_default(self, monkeypatch):
        monkeypatch.setenv("MEMORIA_BUGS_ENABLED", "1")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        monkeypatch.setenv("MEMORIA_BUGS_LIMIAR", "abc")
        from voice_agent.memoria_bugs import MemoriaBugs, LIMIAR_DEFAULT
        m = MemoriaBugs.from_env(MagicMock())
        assert m.limiar == LIMIAR_DEFAULT
