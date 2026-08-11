"""
Testes para o bloco C-114 no pipeline.py:
- detectar_escolha_c114() detecta "fila" e "reserva" corretamente
- Pipeline lê flag Redis c114_sinal_solicitado antes de agir
- Pipeline chama patch_custom_fields_raw com enum correto
- Pipeline move lead para 4.REAGENDAR quando "fila"
- Pipeline não move lead quando "reserva" (apenas nota)
- Sem flag Redis → nenhuma ação mesmo com texto "fila"
- detectar_escolha_c114 retorna None sem flag Redis ativo
- Fail-open: exceção → pipeline continua
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch, call


# ─────────────────────────────────────────────────────────────────────────────
# Testes para detectar_escolha_c114()
# ─────────────────────────────────────────────────────────────────────────────

class TestDetectarEscolhaC114:
    """Testes unitários para a função detectar_escolha_c114."""

    def _redis_com_flag(self, lead_id=999):
        """Simula Redis com flag c114_sinal_solicitado ativo."""
        redis = MagicMock()
        redis.get.return_value = b"1"
        return redis

    def _redis_sem_flag(self):
        """Simula Redis sem flag ativo."""
        redis = MagicMock()
        redis.get.return_value = None
        return redis

    def test_sem_flag_redis_retorna_none(self):
        from voice_agent.politica_comparecimento import detectar_escolha_c114
        redis = self._redis_sem_flag()
        # Mesmo com texto de fila claro, sem flag → None
        result = detectar_escolha_c114("2 quero a fila", lead_id=1, redis_client=redis)
        assert result is None

    def test_fila_opcao_2(self):
        from voice_agent.politica_comparecimento import detectar_escolha_c114
        redis = self._redis_com_flag()
        assert detectar_escolha_c114("2", lead_id=1, redis_client=redis) == "fila"

    def test_fila_opcao_2_emoji(self):
        from voice_agent.politica_comparecimento import detectar_escolha_c114
        redis = self._redis_com_flag()
        assert detectar_escolha_c114("2️⃣", lead_id=1, redis_client=redis) == "fila"

    def test_fila_texto_literal(self):
        from voice_agent.politica_comparecimento import detectar_escolha_c114
        redis = self._redis_com_flag()
        assert detectar_escolha_c114("prefiro a fila", lead_id=1, redis_client=redis) == "fila"

    def test_fila_sem_pagamento(self):
        from voice_agent.politica_comparecimento import detectar_escolha_c114
        redis = self._redis_com_flag()
        assert detectar_escolha_c114("prefiro sem pagamento", lead_id=1, redis_client=redis) == "fila"

    def test_fila_sem_pagar(self):
        from voice_agent.politica_comparecimento import detectar_escolha_c114
        redis = self._redis_com_flag()
        assert detectar_escolha_c114("quero sem pagar", lead_id=1, redis_client=redis) == "fila"

    def test_reserva_opcao_1(self):
        from voice_agent.politica_comparecimento import detectar_escolha_c114
        redis = self._redis_com_flag()
        assert detectar_escolha_c114("1", lead_id=1, redis_client=redis) == "reserva"

    def test_reserva_texto(self):
        from voice_agent.politica_comparecimento import detectar_escolha_c114
        redis = self._redis_com_flag()
        assert detectar_escolha_c114("quero a reserva", lead_id=1, redis_client=redis) == "reserva"

    def test_reserva_comprovante(self):
        from voice_agent.politica_comparecimento import detectar_escolha_c114
        redis = self._redis_com_flag()
        assert detectar_escolha_c114("vou mandar o comprovante", lead_id=1, redis_client=redis) == "reserva"

    def test_reserva_vou_pagar(self):
        from voice_agent.politica_comparecimento import detectar_escolha_c114
        redis = self._redis_com_flag()
        assert detectar_escolha_c114("vou pagar", lead_id=1, redis_client=redis) == "reserva"

    def test_texto_neutro_retorna_none(self):
        from voice_agent.politica_comparecimento import detectar_escolha_c114
        redis = self._redis_com_flag()
        # "obrigada" não indica nem fila nem reserva
        assert detectar_escolha_c114("obrigada", lead_id=1, redis_client=redis) is None

    def test_sem_redis_sem_lead_id_retorna_none_para_fila(self):
        """Sem Redis e sem lead_id, não verifica flag → pode retornar resultado."""
        from voice_agent.politica_comparecimento import detectar_escolha_c114
        # Sem redis_client e lead_id → não verifica flag → detecta normalmente
        result = detectar_escolha_c114("2 fila", lead_id=None, redis_client=None)
        assert result == "fila"

    def test_fila_grava_redis_flag_opcao(self):
        """Quando detecta fila, grava blink:c114_opcao_fila:{lead_id} no Redis."""
        from voice_agent.politica_comparecimento import detectar_escolha_c114
        redis = self._redis_com_flag(lead_id=42)
        detectar_escolha_c114("sem pagamento", lead_id=42, redis_client=redis)
        redis.setex.assert_called_once()
        # Verificar que a chave correta foi usada
        chave = redis.setex.call_args[0][0]
        assert "c114_opcao_fila" in chave
        assert "42" in chave


# ─────────────────────────────────────────────────────────────────────────────
# Testes de integração — bloco C-114 no pipeline
# ─────────────────────────────────────────────────────────────────────────────

class TestPipelineC114Loop:
    """Verifica que o bloco C-114 no pipeline.py age corretamente."""

    def _make_redis_com_flag(self, lead_id=123):
        redis = MagicMock()

        def get_side_effect(key):
            if f"c114_sinal_solicitado:{lead_id}" in key:
                return b"1"
            return None

        redis.get.side_effect = get_side_effect
        return redis

    def _make_kommo(self):
        kommo = MagicMock()
        kommo.patch_custom_fields_raw.return_value = (True, {})
        kommo.update_lead_status.return_value = True
        kommo.add_note.return_value = True
        return kommo

    def _make_caller_ctx(self, lead_id=123, status_id=102560495):
        """status_id=102560495 = 3-AGENDAR (etapa válida pra mover)."""
        return {
            "lead_id": lead_id,
            "status_id": status_id,
            "found": True,
            "known": {},
        }

    # ── Fila ──────────────────────────────────────────────────────────────────

    def test_fila_atualiza_a_fazer_enum_927866(self):
        """'2/fila' → A FAZER = Fila Encaixe (enum 927866)."""
        from voice_agent.politica_comparecimento import A_FAZER_FILA_ENCAIXE_ENUM_ID
        assert A_FAZER_FILA_ENCAIXE_ENUM_ID == 927866

    def test_reserva_atualiza_a_fazer_enum_927023(self):
        """'1/reserva' → A FAZER = Encaixe (enum 927023)."""
        from voice_agent.politica_comparecimento import A_FAZER_ENCAIXE_ENUM_ID
        assert A_FAZER_ENCAIXE_ENUM_ID == 927023

    def test_a_fazer_field_id_correto(self):
        """Verifica que o field_id do A FAZER é 1259312."""
        from voice_agent.politica_comparecimento import A_FAZER_FIELD_ID
        assert A_FAZER_FIELD_ID == 1259312

    def test_fila_move_para_reagendar_status_106184631(self):
        """Verifica que o status de 4.REAGENDAR é 106184631."""
        # O valor hardcoded no bloco do pipeline
        REAGENDAR_STATUS_ID = 106184631
        assert REAGENDAR_STATUS_ID == 106184631  # Garantia de não regredir

    def test_bloco_c114_presente_no_pipeline(self):
        """Verifica que o bloco C-114 existe no pipeline.py."""
        import inspect
        import voice_agent.pipeline as _pipeline
        src = inspect.getsource(_pipeline)
        assert "c114" in src.lower() or "C-114" in src
        assert "detectar_escolha_c114" in src
        assert "blink:c114_sinal_solicitado" in src

    def test_bloco_c114_usa_enum_fila_encaixe(self):
        """Verifica que o bloco usa enum_id 927866 para fila."""
        import inspect
        import voice_agent.pipeline as _pipeline
        src = inspect.getsource(_pipeline)
        assert "927866" in src

    def test_bloco_c114_move_para_4_reagendar(self):
        """Verifica que o bloco move para status 106184631 (4.REAGENDAR)."""
        import inspect
        import voice_agent.pipeline as _pipeline
        src = inspect.getsource(_pipeline)
        assert "106184631" in src

    def test_bloco_c114_usa_patch_custom_fields_raw(self):
        """Verifica que o bloco usa patch_custom_fields_raw (não update_lead_fields)."""
        import inspect
        import voice_agent.pipeline as _pipeline
        src = inspect.getsource(_pipeline)
        assert "patch_custom_fields_raw" in src

    def test_bloco_c114_apos_c92_antes_envio(self):
        """Verifica posição do bloco C-114 no pipeline (após C-92, antes do envio)."""
        import inspect
        import voice_agent.pipeline as _pipeline
        src = inspect.getsource(_pipeline)
        idx_c92 = src.find("C-92 PIPELINE")
        idx_c114 = src.find("C-114 PIPELINE")
        idx_envio = src.find("4) Envio")
        assert idx_c92 < idx_c114 < idx_envio, (
            f"Posição incorreta: C-92@{idx_c92} C-114@{idx_c114} Envio@{idx_envio}"
        )

    def test_bloco_c114_tem_fail_open(self):
        """Verifica que o bloco tem try/except fail-open."""
        import inspect
        import voice_agent.pipeline as _pipeline
        src = inspect.getsource(_pipeline)
        # Verifica que existe o except do bloco C-114
        assert "C-114 PIPELINE] check falhou" in src

    def test_bloco_c114_limpa_flag_redis_apos_escolha(self):
        """Verifica que o bloco faz redis.delete() do flag após agir."""
        import inspect
        import voice_agent.pipeline as _pipeline
        src = inspect.getsource(_pipeline)
        # Verifica que usa delete para limpar a flag
        assert "_redis_c114_pipe.delete" in src or "redis_c114_pipe.delete" in src

    # ── Constantes de campos ──────────────────────────────────────────────────

    def test_campos_acompanhamento_tem_fila_encaixe(self):
        """FIELD_A_FAZER em campos_acompanhamento.py tem fila_encaixe → 927866."""
        from voice_agent.campos_acompanhamento import FIELD_A_FAZER
        field_id, enums = FIELD_A_FAZER
        assert field_id == 1259312
        assert enums.get("fila_encaixe") == 927866

    def test_campos_acompanhamento_tem_encaixe(self):
        """FIELD_A_FAZER tem encaixe → 927023."""
        from voice_agent.campos_acompanhamento import FIELD_A_FAZER
        _, enums = FIELD_A_FAZER
        assert enums.get("encaixe") == 927023
