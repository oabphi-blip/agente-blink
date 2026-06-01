"""Pytest do módulo audios_fabricio: catálogo, marcador, guardas, URLs.

Cobre 7 áudios + proibições + janela 24h + limite por conversa + paciente
prefere texto. Garante que a Lia NÃO consegue:
 - inventar audio_id fora do catálogo
 - enviar 2 marcadores na mesma mensagem
 - disparar audio_3 (reservado pro motor follow-up)
"""
from __future__ import annotations

import sys
import time
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402

from voice_agent.audios_fabricio import (  # noqa: E402
    AudioFabricio,
    GuardaResultado,
    audios_habilitados,
    detectar_marcador,
    incrementar_contador,
    info_audio,
    limpar_marcador,
    listar_catalogo,
    pode_enviar_audio,
    url_audio,
)


# ----------------------------------------------------------------------
# Catálogo
# ----------------------------------------------------------------------

class TestCatalogo:

    def test_7_audios_no_catalogo(self):
        assert len(listar_catalogo()) == 7

    def test_ids_esperados(self):
        ids = {a.id for a in listar_catalogo()}
        esperados = {
            "audio_1_dr_fabricio_freitas",
            "audio_2_preciso_cuidar_disso_agora",
            "audio_3_retomada_parou_de_responder",
            "audio_4_convite_para_agendar",
            "audio_5_interesse_nas_lentes",
            "audio_6_medo_da_cirurgia",
            "audio_7_o_que_e_avaliacao",
        }
        assert ids == esperados

    def test_info_existente_retorna_dataclass(self):
        a = info_audio("audio_1_dr_fabricio_freitas")
        assert a is not None
        assert a.etapa == "E3"

    def test_info_invalido_retorna_none(self):
        assert info_audio("audio_99_inventado") is None


# ----------------------------------------------------------------------
# Detector do marcador
# ----------------------------------------------------------------------

class TestDetectarMarcador:

    def test_marcador_valido_e_detectado(self):
        texto = "Entendo seu receio. [AUDIO:audio_6_medo_da_cirurgia]"
        assert detectar_marcador(texto) == "audio_6_medo_da_cirurgia"

    def test_marcador_case_insensitive(self):
        texto = "x [AUDIO:Audio_1_Dr_Fabricio_Freitas]"
        assert detectar_marcador(texto) == "audio_1_dr_fabricio_freitas"

    def test_marcador_com_espacos_aceita(self):
        texto = "x [AUDIO: audio_5_interesse_nas_lentes ]"
        assert detectar_marcador(texto) == "audio_5_interesse_nas_lentes"

    def test_sem_marcador_retorna_none(self):
        assert detectar_marcador("nenhum marcador aqui") is None
        assert detectar_marcador("") is None

    def test_marcador_inventado_eh_rejeitado(self):
        texto = "x [AUDIO:audio_99_inventado]"
        assert detectar_marcador(texto) is None

    def test_2_marcadores_na_mesma_msg_rejeita_KB_60(self):
        """KB §60: NUNCA 2 áudios na mesma msg → função rejeita ambos."""
        texto = "[AUDIO:audio_1_dr_fabricio_freitas] e [AUDIO:audio_6_medo_da_cirurgia]"
        assert detectar_marcador(texto) is None

    def test_audio_3_reservado_motor_rejeita(self):
        """Audio 3 só pode ser disparado pelo motor follow-up."""
        texto = "[AUDIO:audio_3_retomada_parou_de_responder]"
        assert detectar_marcador(texto) is None


class TestLimparMarcador:

    def test_remove_marcador_unico(self):
        texto = "Entendo. [AUDIO:audio_6_medo_da_cirurgia]"
        out = limpar_marcador(texto)
        assert "[AUDIO" not in out
        assert "Entendo" in out

    def test_remove_multiplos(self):
        texto = "x [AUDIO:a] y [AUDIO:b] z"
        assert "[AUDIO" not in limpar_marcador(texto)

    def test_texto_sem_marcador_intocado(self):
        assert limpar_marcador("texto normal") == "texto normal"


# ----------------------------------------------------------------------
# Guardas (janela 24h, limite, preferência)
# ----------------------------------------------------------------------

class TestGuardas:

    def test_paciente_prefere_texto_bloqueia(self):
        r = pode_enviar_audio(
            "5561999999001",
            paciente_prefere_texto=True,
        )
        assert r.pode_enviar is False
        assert "texto" in r.motivo.lower()

    def test_janela_meta_expirada_bloqueia(self):
        # last_inbound há 25h
        ts_velho = time.time() - 25 * 3600
        r = pode_enviar_audio(
            "5561999999001",
            last_inbound_ts=ts_velho,
        )
        assert r.pode_enviar is False
        assert "janela" in r.motivo.lower()

    def test_janela_dentro_22h_ok(self):
        ts_recente = time.time() - 22 * 3600
        r = pode_enviar_audio(
            "5561999999001",
            last_inbound_ts=ts_recente,
        )
        # sem redis, contador=0, dentro do limite
        assert r.pode_enviar is True

    def test_limite_por_conversa_bloqueia(self):
        # Redis fake que devolve 3 (= limite default)
        fake = MagicMock()
        fake.get.return_value = b"3"
        r = pode_enviar_audio(
            "convo_x",
            redis_client=fake,
        )
        assert r.pode_enviar is False
        assert "limite" in r.motivo.lower()
        assert r.contador_atual == 3

    def test_contador_abaixo_do_limite_ok(self):
        fake = MagicMock()
        fake.get.return_value = b"1"
        r = pode_enviar_audio(
            "convo_x",
            redis_client=fake,
        )
        assert r.pode_enviar is True
        assert r.contador_atual == 1

    def test_redis_falha_silenciosa_passa(self):
        """Falha de Redis não bloqueia envio (degradação graciosa)."""
        fake = MagicMock()
        fake.get.side_effect = RuntimeError("redis offline")
        r = pode_enviar_audio("convo_x", redis_client=fake)
        # contador fica 0 → não bloqueia
        assert r.pode_enviar is True

    def test_incrementar_contador_chama_incr_e_expire(self):
        fake = MagicMock()
        fake.incr.return_value = 2
        novo = incrementar_contador("convo_x", redis_client=fake)
        assert novo == 2
        assert fake.incr.called
        assert fake.expire.called


# ----------------------------------------------------------------------
# URL pública
# ----------------------------------------------------------------------

class TestURL:

    def test_url_default(self):
        u = url_audio("audio_1_dr_fabricio_freitas")
        assert u is not None
        assert "audio_1_dr_fabricio_freitas.mp3" in u
        assert "dr_fabricio" in u
        assert u.startswith("https://")

    def test_url_inventado_retorna_none(self):
        assert url_audio("audio_99_inventado") is None

    def test_audio_base_url_env(self, monkeypatch):
        monkeypatch.setenv("AUDIO_BASE_URL", "https://meu.cdn/audios")
        u = url_audio("audio_2_preciso_cuidar_disso_agora")
        assert u == "https://meu.cdn/audios/audio_2_preciso_cuidar_disso_agora.mp3"


# ----------------------------------------------------------------------
# Toggle global
# ----------------------------------------------------------------------

class TestToggle:

    def test_default_on(self, monkeypatch):
        monkeypatch.delenv("AUDIOS_FABRICIO_ENABLED", raising=False)
        assert audios_habilitados() is True

    @pytest.mark.parametrize("val,esperado", [
        ("1", True), ("true", True), ("YES", True),
        ("0", False), ("false", False), ("no", False),
    ])
    def test_valores(self, monkeypatch, val, esperado):
        monkeypatch.setenv("AUDIOS_FABRICIO_ENABLED", val)
        assert audios_habilitados() is esperado
