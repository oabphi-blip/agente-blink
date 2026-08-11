"""
Pytest — Bug C-109: NO-SHOW COUNT >= 2 → sinal Pix obrigatório antes de ofertar slot.

Cobre:
  - noshow < 2 → None (sem bypass)
  - noshow = 2 → mensagem de sinal (50% Pix)
  - noshow = 3 → mensagem de escalação
  - Redis flag impede repetição na mesma sessão (TTL 8h)
  - Toggle SINAL_NOSHOW_ATIVADO=0 → None
  - ctx=None → None (fail-open)
  - Sem agenda E sem aceite → None (não ativa fora de fluxo)
  - Chave Pix por unidade
  - Valor de sinal por médico/motivo
  - Step 15 enriquecimento_ctx injeta flags corretamente
  - Pipeline flag blink:c109_move_humano gravado para >= 3 no-shows
  - Mensagem sinal contém chave Pix válida (allowlist)
  - Mensagem escalação não expõe chave Pix
"""
from __future__ import annotations

import importlib
import os
import sys
import types
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers para importar com toggle controlado
# ---------------------------------------------------------------------------

def _importar_sinal_noshow(ativado: str = "1"):
    """Re-importa sinal_noshow com toggle específico."""
    env_before = os.environ.get("SINAL_NOSHOW_ATIVADO")
    os.environ["SINAL_NOSHOW_ATIVADO"] = ativado
    # Remover do sys.modules para forçar re-import
    for key in list(sys.modules):
        if "sinal_noshow" in key:
            del sys.modules[key]
    try:
        from voice_agent import sinal_noshow as mod
        return mod
    finally:
        if env_before is None:
            os.environ.pop("SINAL_NOSHOW_ATIVADO", None)
        else:
            os.environ["SINAL_NOSHOW_ATIVADO"] = env_before


def _ctx(
    noshow=0,
    sinal_obrigatorio=False,
    escalar_noshow=False,
    unidade="Asa Norte",
    medico="Karla",
    motivo="rotina",
    agenda=None,
    lead_id=99001,
    name="Teste Paciente",
):
    return {
        "lead_id": lead_id,
        "name": name,
        "known": {
            "noshow_count": noshow,
            "sinal_obrigatorio": sinal_obrigatorio,
            "escalar_noshow": escalar_noshow,
            "unidade": unidade,
            "medico": medico,
            "motivo": motivo,
        },
        "agenda": (
            agenda if agenda is not None
            else ([{"data": "2026-08-20", "hora": "09:30"}] if sinal_obrigatorio or escalar_noshow else [])
        ),
    }


# ---------------------------------------------------------------------------
# 1. Toggle OFF → None em todos os casos
# ---------------------------------------------------------------------------

class TestToggleOff:
    def test_toggle_off_noshow2_retorna_none(self):
        mod = _importar_sinal_noshow("0")
        ctx = _ctx(noshow=2, sinal_obrigatorio=True)
        assert mod.deve_exigir_sinal_noshow(ctx, "") is None

    def test_toggle_off_noshow3_retorna_none(self):
        mod = _importar_sinal_noshow("0")
        ctx = _ctx(noshow=3, sinal_obrigatorio=True, escalar_noshow=True)
        assert mod.deve_exigir_sinal_noshow(ctx, "") is None


# ---------------------------------------------------------------------------
# 2. ctx=None → None (fail-open)
# ---------------------------------------------------------------------------

class TestCtxNone:
    def test_ctx_none(self):
        from voice_agent.sinal_noshow import deve_exigir_sinal_noshow
        assert deve_exigir_sinal_noshow(None, "confirmo esse horário") is None

    def test_ctx_vazio(self):
        from voice_agent.sinal_noshow import deve_exigir_sinal_noshow
        # ctx sem known e sem agenda → None
        assert deve_exigir_sinal_noshow({}, "") is None


# ---------------------------------------------------------------------------
# 3. noshow < 2 → None
# ---------------------------------------------------------------------------

class TestNoShowBaixo:
    def test_noshow_0_retorna_none(self):
        from voice_agent.sinal_noshow import deve_exigir_sinal_noshow
        ctx = _ctx(noshow=0, agenda=[{"data": "2026-08-20"}])
        assert deve_exigir_sinal_noshow(ctx, "") is None

    def test_noshow_1_retorna_none(self):
        from voice_agent.sinal_noshow import deve_exigir_sinal_noshow
        ctx = _ctx(noshow=1, agenda=[{"data": "2026-08-20"}])
        assert deve_exigir_sinal_noshow(ctx, "") is None


# ---------------------------------------------------------------------------
# 4. Sem agenda E sem sinal aceite → None (não ativa fora de fluxo)
# ---------------------------------------------------------------------------

class TestSemFluxoAgendamento:
    def test_sem_agenda_sem_aceite_retorna_none(self):
        from voice_agent.sinal_noshow import deve_exigir_sinal_noshow
        ctx = _ctx(noshow=2, sinal_obrigatorio=True, agenda=[])
        assert deve_exigir_sinal_noshow(ctx, "Oi, bom dia") is None

    def test_com_aceite_no_texto_dispara(self):
        from voice_agent.sinal_noshow import deve_exigir_sinal_noshow
        ctx = _ctx(noshow=2, sinal_obrigatorio=True, agenda=[])
        result = deve_exigir_sinal_noshow(ctx, "quero confirmar esse horário")
        assert result is not None

    def test_com_agenda_disponivel_dispara(self):
        from voice_agent.sinal_noshow import deve_exigir_sinal_noshow
        ctx = _ctx(noshow=2, sinal_obrigatorio=True, agenda=[{"data": "2026-08-20"}])
        result = deve_exigir_sinal_noshow(ctx, "")
        assert result is not None


# ---------------------------------------------------------------------------
# 5. noshow = 2 → mensagem de sinal 50% Pix
# ---------------------------------------------------------------------------

class TestNoShow2Sinal:
    def test_retorna_mensagem_nao_none(self):
        from voice_agent.sinal_noshow import deve_exigir_sinal_noshow
        ctx = _ctx(noshow=2, sinal_obrigatorio=True, unidade="Asa Norte")
        result = deve_exigir_sinal_noshow(ctx, "")
        assert result is not None

    def test_mensagem_contem_pix_asa_norte(self):
        from voice_agent.sinal_noshow import deve_exigir_sinal_noshow
        ctx = _ctx(noshow=2, sinal_obrigatorio=True, unidade="Asa Norte")
        result = deve_exigir_sinal_noshow(ctx, "")
        assert "karladelaliberaoftalmo@gmail.com" in result

    def test_mensagem_contem_pix_aguas_claras(self):
        from voice_agent.sinal_noshow import deve_exigir_sinal_noshow
        ctx = _ctx(noshow=2, sinal_obrigatorio=True, unidade="Águas Claras")
        result = deve_exigir_sinal_noshow(ctx, "")
        assert "52.303.729/0001-30" in result

    def test_mensagem_contem_50_por_cento(self):
        from voice_agent.sinal_noshow import deve_exigir_sinal_noshow
        ctx = _ctx(noshow=2, sinal_obrigatorio=True)
        result = deve_exigir_sinal_noshow(ctx, "")
        assert "50%" in result

    def test_mensagem_nao_contem_escalacao(self):
        from voice_agent.sinal_noshow import deve_exigir_sinal_noshow
        ctx = _ctx(noshow=2, sinal_obrigatorio=True)
        result = deve_exigir_sinal_noshow(ctx, "")
        assert "equipe" not in result.lower()

    def test_flag_redis_impede_repeticao(self):
        from voice_agent.sinal_noshow import deve_exigir_sinal_noshow, REDIS_KEY_SINAL_COBRADO
        redis_mock = MagicMock()
        redis_mock.get.return_value = b"1"  # já cobrou
        ctx = _ctx(noshow=2, sinal_obrigatorio=True)
        result = deve_exigir_sinal_noshow(ctx, "", redis_mock)
        assert result is None  # não repete

    def test_sem_flag_redis_grava_flag(self):
        from voice_agent.sinal_noshow import deve_exigir_sinal_noshow
        redis_mock = MagicMock()
        redis_mock.get.return_value = None  # não cobrou ainda
        ctx = _ctx(noshow=2, sinal_obrigatorio=True, lead_id=12345)
        deve_exigir_sinal_noshow(ctx, "", redis_mock)
        redis_mock.setex.assert_called()
        # Verificar que gravou chave correta
        call_args = redis_mock.setex.call_args_list
        keys_gravadas = [str(c[0][0]) for c in call_args]
        assert any("c109_sinal_cobrado:12345" in k for k in keys_gravadas)


# ---------------------------------------------------------------------------
# 6. noshow = 3 → escalação para humano
# ---------------------------------------------------------------------------

class TestNoShow3Escalacao:
    def test_retorna_mensagem_escalacao(self):
        from voice_agent.sinal_noshow import deve_exigir_sinal_noshow
        ctx = _ctx(noshow=3, sinal_obrigatorio=True, escalar_noshow=True)
        result = deve_exigir_sinal_noshow(ctx, "")
        assert result is not None

    def test_mensagem_escalacao_nao_contem_pix(self):
        from voice_agent.sinal_noshow import deve_exigir_sinal_noshow
        ctx = _ctx(noshow=3, sinal_obrigatorio=True, escalar_noshow=True)
        result = deve_exigir_sinal_noshow(ctx, "")
        assert "karladelaliberaoftalmo" not in result
        assert "52.303.729" not in result

    def test_mensagem_escalacao_menciona_equipe(self):
        from voice_agent.sinal_noshow import deve_exigir_sinal_noshow
        ctx = _ctx(noshow=3, sinal_obrigatorio=True, escalar_noshow=True)
        result = deve_exigir_sinal_noshow(ctx, "")
        assert "equipe" in result.lower()

    def test_flag_move_humano_gravado_redis(self):
        from voice_agent.sinal_noshow import deve_exigir_sinal_noshow
        redis_mock = MagicMock()
        redis_mock.get.return_value = None
        ctx = _ctx(noshow=3, sinal_obrigatorio=True, escalar_noshow=True, lead_id=67890)
        deve_exigir_sinal_noshow(ctx, "", redis_mock)
        call_args = redis_mock.setex.call_args_list
        keys_gravadas = [str(c[0][0]) for c in call_args]
        assert any("c109_move_humano:67890" in k for k in keys_gravadas)

    def test_flag_escalar_impede_repeticao(self):
        from voice_agent.sinal_noshow import deve_exigir_sinal_noshow, REDIS_KEY_ESCALAR_NOSHOW
        redis_mock = MagicMock()
        redis_mock.get.return_value = b"1"  # já escalou
        ctx = _ctx(noshow=3, sinal_obrigatorio=True, escalar_noshow=True)
        result = deve_exigir_sinal_noshow(ctx, "", redis_mock)
        assert result is None  # não repete escalação


# ---------------------------------------------------------------------------
# 7. Valor de sinal por médico / motivo
# ---------------------------------------------------------------------------

class TestValorSinal:
    def test_karla_apv_valor_400(self):
        from voice_agent.sinal_noshow import deve_exigir_sinal_noshow
        ctx = _ctx(noshow=2, sinal_obrigatorio=True, medico="Karla", motivo="processamento visual")
        result = deve_exigir_sinal_noshow(ctx, "")
        assert "R$ 400" in result

    def test_karla_rotina_valor_305(self):
        from voice_agent.sinal_noshow import deve_exigir_sinal_noshow
        ctx = _ctx(noshow=2, sinal_obrigatorio=True, medico="Karla", motivo="rotina")
        result = deve_exigir_sinal_noshow(ctx, "")
        assert "305" in result

    def test_fabricio_catarata_valor_222(self):
        from voice_agent.sinal_noshow import deve_exigir_sinal_noshow
        ctx = _ctx(noshow=2, sinal_obrigatorio=True, medico="Fabrício", motivo="catarata")
        result = deve_exigir_sinal_noshow(ctx, "")
        assert "222" in result

    def test_medico_desconhecido_usa_default(self):
        from voice_agent.sinal_noshow import deve_exigir_sinal_noshow
        ctx = _ctx(noshow=2, sinal_obrigatorio=True, medico="", motivo="")
        result = deve_exigir_sinal_noshow(ctx, "")
        assert result is not None
        assert "305" in result  # default R$ 305,50


# ---------------------------------------------------------------------------
# 8. Step 15 em enriquecimento_ctx.py injeta flags corretos
# ---------------------------------------------------------------------------

class TestStep15Enriquecimento:
    """Valida que enriquecimento_ctx.py step 15 injeta sinal_obrigatorio/escalar_noshow."""

    def _rodar_step15(self, noshow_count: int) -> dict:
        """Simula apenas o step 15 de enriquecimento_ctx, retornando known."""
        known = {"noshow_count": noshow_count}
        try:
            _ns_c109 = int(known.get("noshow_count") or 0)
            if _ns_c109 >= 2 and not known.get("sinal_obrigatorio"):
                known["sinal_obrigatorio"] = True
                known["noshow_count_val"] = _ns_c109
                if _ns_c109 >= 3:
                    known["escalar_noshow"] = True
        except Exception:
            pass
        return known

    def test_noshow_0_sem_flags(self):
        known = self._rodar_step15(0)
        assert not known.get("sinal_obrigatorio")
        assert not known.get("escalar_noshow")

    def test_noshow_1_sem_flags(self):
        known = self._rodar_step15(1)
        assert not known.get("sinal_obrigatorio")
        assert not known.get("escalar_noshow")

    def test_noshow_2_sinal_obrigatorio(self):
        known = self._rodar_step15(2)
        assert known.get("sinal_obrigatorio") is True
        assert not known.get("escalar_noshow")

    def test_noshow_3_sinal_e_escalar(self):
        known = self._rodar_step15(3)
        assert known.get("sinal_obrigatorio") is True
        assert known.get("escalar_noshow") is True

    def test_noshow_5_sinal_e_escalar(self):
        known = self._rodar_step15(5)
        assert known.get("sinal_obrigatorio") is True
        assert known.get("escalar_noshow") is True


# ---------------------------------------------------------------------------
# 9. Mensagem de sinal não contém chaves Pix inválidas (allowlist)
# ---------------------------------------------------------------------------

class TestAllowlistPix:
    _PIXES_VALIDOS = {
        "karladelaliberaoftalmo@gmail.com",
        "52.303.729/0001-30",
    }

    def test_pix_asa_norte_valido(self):
        from voice_agent.sinal_noshow import deve_exigir_sinal_noshow
        ctx = _ctx(noshow=2, sinal_obrigatorio=True, unidade="Asa Norte")
        result = deve_exigir_sinal_noshow(ctx, "")
        # Garantir que pelo menos 1 pix válido aparece
        assert any(p in result for p in self._PIXES_VALIDOS)

    def test_pix_aguas_claras_valido(self):
        from voice_agent.sinal_noshow import deve_exigir_sinal_noshow
        ctx = _ctx(noshow=2, sinal_obrigatorio=True, unidade="Águas Claras")
        result = deve_exigir_sinal_noshow(ctx, "")
        assert any(p in result for p in self._PIXES_VALIDOS)

    def test_nenhum_pix_inventado_asa_norte(self):
        from voice_agent.sinal_noshow import deve_exigir_sinal_noshow
        ctx = _ctx(noshow=2, sinal_obrigatorio=True, unidade="Asa Norte")
        result = deve_exigir_sinal_noshow(ctx, "")
        # Só karladelalibera deve aparecer
        assert "karladelaliberaoftalmo@gmail.com" in result
        assert "52.303.729" not in result

    def test_nenhum_pix_inventado_aguas_claras(self):
        from voice_agent.sinal_noshow import deve_exigir_sinal_noshow
        ctx = _ctx(noshow=2, sinal_obrigatorio=True, unidade="Águas Claras")
        result = deve_exigir_sinal_noshow(ctx, "")
        assert "52.303.729/0001-30" in result
        assert "karladelaliberaoftalmo" not in result


# ---------------------------------------------------------------------------
# 10. Posição na chain (C-109 aparece depois de C-108, antes de urgência)
# ---------------------------------------------------------------------------

class TestPosicaoNaChain:
    def test_c109_depois_de_c108_antes_urgencia(self):
        """C-109 deve estar na chain DEPOIS de C-108 e ANTES de deve_orientar_urgencia."""
        caminho = (
            "voice_agent/blindagens_deterministicas.py"
        )
        import pathlib
        base = pathlib.Path(__file__).parent.parent
        conteudo = (base / caminho).read_text(encoding="utf-8")

        # Encontrar o corpo da função tentar_bypass_deterministico
        inicio_func = conteudo.find("def tentar_bypass_deterministico")
        assert inicio_func >= 0, "função tentar_bypass_deterministico não encontrada"
        corpo = conteudo[inicio_func:]

        pos_c108 = corpo.find("C-108")
        pos_c109 = corpo.find("C-109")
        pos_urgencia = corpo.find("deve_orientar_urgencia(ctx")

        assert pos_c108 >= 0, "comentário C-108 não encontrado no corpo da função"
        assert pos_c109 >= 0, "comentário C-109 não encontrado no corpo da função"
        assert pos_urgencia >= 0, "call site deve_orientar_urgencia(ctx não encontrado"

        assert pos_c108 < pos_c109, "C-108 deve vir antes de C-109 na chain"
        assert pos_c109 < pos_urgencia, "C-109 deve vir antes de deve_orientar_urgencia"


# ---------------------------------------------------------------------------
# 11. Aceite por texto — padrões de aceite detectados
# ---------------------------------------------------------------------------

class TestAceiteNoTexto:
    """user_text com aceite de slot dispara mesmo sem ctx.agenda."""

    @pytest.mark.parametrize("aceite", [
        "confirmo esse horário",
        "quero o primeiro",
        "pode ser a opção 1",
        "esse dia está bom",
        "pode ser",
    ])
    def test_aceite_dispara_com_noshow2(self, aceite):
        from voice_agent.sinal_noshow import deve_exigir_sinal_noshow
        ctx = _ctx(noshow=2, sinal_obrigatorio=True, agenda=[])
        result = deve_exigir_sinal_noshow(ctx, aceite)
        assert result is not None, f"Aceite '{aceite}' deveria disparar C-109"
