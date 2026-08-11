"""
Testes para Bug C-116 — Comprovante Pix detection.

Cobre:
1. Detecção de texto sintético de imagem (Evolution + WA Cloud, positivos e negativos)
2. Gate Redis: flag c114_aguardando_comprovante ausente → None (imagem = carteirinha normal)
3. Gate Redis: flag presente → retorna confirmação + grava c116_comprovante_detectado
4. Resposta de confirmação (nome, unidade)
5. Toggle OFF → None
6. Fail-open: sem Redis → None (não quebra pipeline)
7. Fail-open: lead_id ausente no ctx → None
8. Posição do bypass no código (após C-115, antes de faq_endereco)
9. Chaves Pix da allowlist não vazam em mensagem de confirmação
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures e helpers
# ─────────────────────────────────────────────────────────────────────────────

def _ctx(lead_id=12345, unidade="Asa Norte", nome="Maria"):
    return {
        "lead_id": lead_id,
        "known": {
            "nome_paciente": nome,
            "unidade": unidade,
        },
    }


def _redis_com_flag(lead_id=12345):
    """Mock Redis com blink:c114_aguardando_comprovante:{lead_id} ativo."""
    r = MagicMock()
    r.get.side_effect = lambda key: b"1" if f"aguardando_comprovante:{lead_id}" in key else None
    r.setex.return_value = True
    r.delete.return_value = 1
    return r


def _redis_sem_flag():
    """Mock Redis sem nenhum flag ativo."""
    r = MagicMock()
    r.get.return_value = None
    return r


# Textos sintéticos de imagem reais dos dois caminhos do webhook
_IMG_EVOLUTION = "[O paciente acabou de enviar uma imagem/foto pelo WhatsApp — não é possível visualizá-la aqui]"
_IMG_WACLOUD = "[O paciente enviou uma imagem pelo WhatsApp]"
_IMG_DOC_EVOLUTION = "[O paciente acabou de enviar um documento/arquivo pelo WhatsApp]"
_IMG_DOC_WACLOUD = "[O paciente enviou um documento/arquivo pelo WhatsApp]"

_MSG_NORMAL = "quero agendar uma consulta"
_MSG_TEXTO = "boa tarde, o horário está confirmado?"


# ─────────────────────────────────────────────────────────────────────────────
# 1. Detecção de texto sintético de imagem
# ─────────────────────────────────────────────────────────────────────────────

class TestDeteccaoImagemSintetica:

    def _fn(self, texto):
        from voice_agent.comprovante_pix import _texto_e_imagem_sintetica
        return _texto_e_imagem_sintetica(texto)

    @pytest.mark.parametrize("texto", [
        _IMG_EVOLUTION,
        _IMG_WACLOUD,
        _IMG_DOC_EVOLUTION,
        _IMG_DOC_WACLOUD,
        "[O paciente enviou uma foto pelo WhatsApp]",
        "[O paciente acabou de enviar um arquivo pelo WhatsApp]",
        "[O paciente enviou um sticker pelo WhatsApp]",
    ])
    def test_detecta_texto_sintetico(self, texto):
        assert self._fn(texto) is True, f"Não detectou: {texto!r}"

    @pytest.mark.parametrize("texto", [
        "olá, boa tarde",
        "quero agendar",
        "qual o horário?",
        "",
        "comprovante pix",          # texto escrito pelo paciente, não sintético
        "enviei a foto",            # paciente DIZENDO que enviou, não o texto sintético
    ])
    def test_nao_detecta_texto_normal(self, texto):
        assert self._fn(texto) is False, f"Falso positivo: {texto!r}"


# ─────────────────────────────────────────────────────────────────────────────
# 2. Função principal — gates
# ─────────────────────────────────────────────────────────────────────────────

class TestDeveConfirmarComprovante:

    def _fn(self, ctx, user_text, redis=None):
        """Chama deve_confirmar_comprovante_pix com Redis mockado via patch."""
        import voice_agent.comprovante_pix as mod

        if redis is None:
            redis = _redis_sem_flag()

        with patch.object(mod, "_ATIVADO", True):
            with patch("voice_agent.comprovante_pix.get_redis", return_value=redis, create=True):
                # Também precisa mockar o import interno
                import unittest.mock as _mock
                with _mock.patch.dict("sys.modules", {"voice_agent.redis_client": _mock.MagicMock(get_redis=lambda: redis)}):
                    # Reimport para pegar o mock — método mais direto: patch o get_redis interno
                    from voice_agent.comprovante_pix import deve_confirmar_comprovante_pix
                    # Força o módulo a usar nosso redis via patch no import interno
                    with _mock.patch("voice_agent.comprovante_pix.get_redis", return_value=redis, create=True):
                        # Reexecutar com import internal mockado
                        pass
                # Approach mais simples: patch diretamente o get_redis no módulo
                with _mock.patch(
                    "voice_agent.comprovante_pix.get_redis",
                    return_value=redis,
                    create=True,
                ):
                    from voice_agent.comprovante_pix import deve_confirmar_comprovante_pix as fn
                    return fn(ctx, user_text)

    def _fn_direct(self, ctx, user_text, redis=None):
        """Approach mais simples com patch no módulo."""
        import voice_agent.comprovante_pix as mod
        import unittest.mock as _mock

        if redis is None:
            redis = _redis_sem_flag()

        orig_ativado = mod._ATIVADO
        mod._ATIVADO = True

        try:
            # Sobrescrever get_redis dentro do módulo
            orig_fn = None
            try:
                import voice_agent.redis_client as _rc
                orig_fn = _rc.get_redis
                _rc.get_redis = lambda: redis
            except ImportError:
                pass

            from voice_agent.comprovante_pix import deve_confirmar_comprovante_pix
            result = deve_confirmar_comprovante_pix(ctx, user_text)
            return result
        finally:
            mod._ATIVADO = orig_ativado
            if orig_fn is not None:
                try:
                    import voice_agent.redis_client as _rc
                    _rc.get_redis = orig_fn
                except ImportError:
                    pass

    def test_imagem_sem_flag_retorna_none(self):
        """Imagem enviada mas sem flag de reserva → carteirinha normal → None."""
        ctx = _ctx()
        result = self._fn_direct(ctx, _IMG_WACLOUD, redis=_redis_sem_flag())
        assert result is None

    def test_texto_normal_com_flag_retorna_none(self):
        """Flag ativo mas mensagem não é imagem → None."""
        ctx = _ctx()
        result = self._fn_direct(ctx, _MSG_NORMAL, redis=_redis_com_flag())
        assert result is None

    def test_imagem_com_flag_retorna_confirmacao(self):
        """Imagem + flag ativo → retorna texto de confirmação."""
        ctx = _ctx()
        result = self._fn_direct(ctx, _IMG_WACLOUD, redis=_redis_com_flag())
        assert result is not None
        assert "comprovante" in result.lower() or "recebido" in result.lower()

    def test_imagem_evolution_com_flag_retorna_confirmacao(self):
        """Caminho Evolution também detectado."""
        ctx = _ctx()
        result = self._fn_direct(ctx, _IMG_EVOLUTION, redis=_redis_com_flag())
        assert result is not None

    def test_imagem_documento_com_flag_retorna_confirmacao(self):
        """Documento também é aceito como possível comprovante."""
        ctx = _ctx()
        result = self._fn_direct(ctx, _IMG_DOC_WACLOUD, redis=_redis_com_flag())
        assert result is not None

    def test_sem_lead_id_retorna_none(self):
        """Sem lead_id no ctx → não consegue checar Redis → None."""
        ctx = {"known": {"nome_paciente": "Teste"}}  # sem lead_id
        result = self._fn_direct(ctx, _IMG_WACLOUD, redis=_redis_com_flag())
        assert result is None

    def test_ctx_none_retorna_none(self):
        from voice_agent.comprovante_pix import deve_confirmar_comprovante_pix
        result = deve_confirmar_comprovante_pix(None, _IMG_WACLOUD)
        assert result is None

    def test_user_text_vazio_retorna_none(self):
        from voice_agent.comprovante_pix import deve_confirmar_comprovante_pix
        ctx = _ctx()
        result = deve_confirmar_comprovante_pix(ctx, "")
        assert result is None

    def test_flag_c116_detectado_gravado(self):
        """Quando comprovante detectado, grava flag c116_comprovante_detectado."""
        ctx = _ctx()
        redis = _redis_com_flag()
        self._fn_direct(ctx, _IMG_WACLOUD, redis=redis)
        # Verifica que setex foi chamado com a key c116_comprovante_detectado
        calls = [str(c) for c in redis.setex.call_args_list]
        assert any("c116_comprovante_detectado" in c for c in calls), (
            f"setex não chamado com c116_comprovante_detectado. Calls: {calls}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# 3. Conteúdo da resposta de confirmação
# ─────────────────────────────────────────────────────────────────────────────

class TestRespostaConfirmacao:

    def _confirmar(self, ctx, texto_img=_IMG_WACLOUD):
        """Helper direto que bypassa Redis — testa _montar_resposta_confirmacao."""
        from voice_agent.comprovante_pix import _montar_resposta_confirmacao
        return _montar_resposta_confirmacao(ctx)

    def test_resposta_tem_emoji_confirmacao(self):
        r = self._confirmar(_ctx())
        assert "✅" in r

    def test_resposta_menciona_nome(self):
        r = self._confirmar(_ctx(nome="Juliana"))
        assert "Juliana" in r

    def test_resposta_sem_nome_nao_quebra(self):
        ctx = {"lead_id": 999, "known": {"unidade": "Asa Norte"}}
        r = self._confirmar(ctx)
        assert "✅" in r
        assert "comprovante" in r.lower() or "recebido" in r.lower()

    def test_resposta_menciona_unidade_asa_norte(self):
        r = self._confirmar(_ctx(unidade="Asa Norte"))
        assert "Asa Norte" in r

    def test_resposta_menciona_unidade_aguas_claras(self):
        r = self._confirmar(_ctx(unidade="Águas Claras"))
        assert "Águas Claras" in r

    def test_resposta_sem_unidade_nao_quebra(self):
        ctx = {"lead_id": 999, "known": {}}
        r = self._confirmar(ctx)
        assert "✅" in r

    def test_resposta_menciona_equipe_ou_confirmacao(self):
        """Deve mencionar que a equipe vai confirmar."""
        r = self._confirmar(_ctx())
        assert "equipe" in r.lower() or "confirmar" in r.lower() or "garantido" in r.lower()

    def test_chave_pix_nao_vaza_na_confirmacao(self):
        """Confirmação não deve re-exibir a chave Pix (isso é papel da mensagem C-114)."""
        r = self._confirmar(_ctx(unidade="Asa Norte"))
        assert "karladelaliberaoftalmo@gmail.com" not in r
        assert "52.303.729" not in r


# ─────────────────────────────────────────────────────────────────────────────
# 4. Toggle
# ─────────────────────────────────────────────────────────────────────────────

class TestToggle:

    def test_toggle_off_retorna_none(self):
        import voice_agent.comprovante_pix as mod
        orig = mod._ATIVADO
        mod._ATIVADO = False
        try:
            from voice_agent.comprovante_pix import deve_confirmar_comprovante_pix
            result = deve_confirmar_comprovante_pix(_ctx(), _IMG_WACLOUD)
            assert result is None
        finally:
            mod._ATIVADO = orig

    def test_toggle_on_permite_execucao(self):
        """Toggle ON não quebra — verifica que a lógica roda (mesmo sem Redis)."""
        import voice_agent.comprovante_pix as mod
        orig = mod._ATIVADO
        mod._ATIVADO = True
        try:
            from voice_agent.comprovante_pix import deve_confirmar_comprovante_pix
            # Sem Redis → None (fail-open), mas não levanta exceção
            result = deve_confirmar_comprovante_pix(_ctx(), _IMG_WACLOUD)
            assert result is None or isinstance(result, str)
        finally:
            mod._ATIVADO = orig


# ─────────────────────────────────────────────────────────────────────────────
# 5. Fail-open
# ─────────────────────────────────────────────────────────────────────────────

class TestFailOpen:

    def test_excecao_interna_retorna_none(self):
        """Qualquer exceção não deve vazar para o caller."""
        from voice_agent.comprovante_pix import deve_confirmar_comprovante_pix
        # ctx com tipo errado vai tentar .get() e eventualmente falhar
        result = deve_confirmar_comprovante_pix("nao_e_dict", _IMG_WACLOUD)
        assert result is None

    def test_redis_none_retorna_none(self):
        """Quando get_redis() retorna None (testes/sem REDIS_URL) → None sem crash."""
        import voice_agent.comprovante_pix as mod
        import unittest.mock as _mock
        orig = mod._ATIVADO
        mod._ATIVADO = True
        try:
            with _mock.patch("voice_agent.comprovante_pix.get_redis", return_value=None, create=True):
                from voice_agent.comprovante_pix import deve_confirmar_comprovante_pix
                result = deve_confirmar_comprovante_pix(_ctx(), _IMG_WACLOUD)
                # Sem Redis → None (fail-open)
                assert result is None
        finally:
            mod._ATIVADO = orig


# ─────────────────────────────────────────────────────────────────────────────
# 6. Posição do bypass no código
# ─────────────────────────────────────────────────────────────────────────────

class TestPosicaoBypass:

    def test_c116_apos_c115_e_antes_faq_endereco(self):
        """C-116 vem após C-115 e antes de faq_endereco no código fonte."""
        import inspect
        import voice_agent.blindagens_deterministicas as mod
        src = inspect.getsource(mod)
        idx_c115 = src.find('return ("faq_consulta_marcada"')
        idx_c116 = src.find('return ("comprovante_pix_c116"')
        idx_endereco = src.find('return ("faq_endereco"')
        assert idx_c115 != -1, "return faq_consulta_marcada não encontrado"
        assert idx_c116 != -1, "return comprovante_pix_c116 não encontrado"
        assert idx_endereco != -1, "return faq_endereco não encontrado"
        assert idx_c115 < idx_c116 < idx_endereco, (
            f"Posição incorreta: c115@{idx_c115} c116@{idx_c116} endereco@{idx_endereco}"
        )

    def test_c114_reserva_grava_flag_comprovante(self):
        """Pipeline C-114 reserva branch inclui setex aguardando_comprovante."""
        import inspect
        import voice_agent.pipeline as mod
        src = inspect.getsource(mod)
        # Deve ter a chave c114_aguardando_comprovante sendo gravada com setex
        assert "aguardando_comprovante" in src, "flag aguardando_comprovante não encontrado em pipeline.py"
        assert "c116_comprovante_detectado" in src, "C-116 block não encontrado em pipeline.py"

    def test_c116_pipeline_block_apos_c114_bloco(self):
        """C-116 pipeline block vem após o bloco C-114 no código fonte."""
        import inspect
        import voice_agent.pipeline as mod
        src = inspect.getsource(mod)
        idx_c114 = src.find("3a-qua) Bug C-114")
        idx_c116 = src.find("3a-cin) Bug C-116")
        assert idx_c114 != -1, "Bloco C-114 não encontrado em pipeline.py"
        assert idx_c116 != -1, "Bloco C-116 não encontrado em pipeline.py"
        assert idx_c114 < idx_c116, (
            f"C-116 deveria vir APÓS C-114 em pipeline.py. c114@{idx_c114} c116@{idx_c116}"
        )
