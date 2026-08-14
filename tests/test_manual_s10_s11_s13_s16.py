"""
Pytest — Manual v1.0 S10/S11/S13/S16 (14/08/2026)
===================================================
Cobre os 4 novos bypasses determinísticos adicionados ao
tentar_bypass_deterministico() em blindagens_deterministicas.py.

S10 — FAQ duração da consulta (deve_responder_faq_duracao)
S11 — FAQ dilatação da pupila (deve_responder_faq_dilatacao)
S13 — FAQ encaminhamento médico (deve_responder_faq_encaminhamento)
S16 — FAQ mídias e áudios geral (deve_responder_faq_midia)
"""
from __future__ import annotations

import os
import importlib
import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ctx(medico: str = "", convenio: str = "") -> dict:
    return {"known": {"medico": medico, "convenio": convenio}}


def _reload():
    """Recarrega o módulo para pegar env vars setadas no test."""
    import voice_agent.blindagens_deterministicas as m
    importlib.reload(m)
    return m


# ---------------------------------------------------------------------------
# S10 — FAQ DURAÇÃO
# ---------------------------------------------------------------------------

class TestS10Duracao:

    def test_quanto_tempo_dura_karla(self):
        from voice_agent.blindagens_deterministicas import deve_responder_faq_duracao
        ctx = _ctx(medico="Dra. Karla Delalíbera")
        r = deve_responder_faq_duracao(ctx, "Quanto tempo dura a consulta?")
        assert r is not None
        assert "30 minuto" in r
        assert "Karla" in r

    def test_quanto_tempo_dura_fabricio(self):
        from voice_agent.blindagens_deterministicas import deve_responder_faq_duracao
        ctx = _ctx(medico="Dr. Fabrício Freitas")
        r = deve_responder_faq_duracao(ctx, "demora muito a consulta?")
        assert r is not None
        assert "40 minuto" in r
        assert "Fabrício" in r or "Fabricio" in r

    def test_sem_medico_retorna_media(self):
        from voice_agent.blindagens_deterministicas import deve_responder_faq_duracao
        r = deve_responder_faq_duracao({}, "Quanto tempo leva a consulta?")
        assert r is not None
        assert "30 a 40 minuto" in r

    def test_variante_quantas_horas(self):
        from voice_agent.blindagens_deterministicas import deve_responder_faq_duracao
        r = deve_responder_faq_duracao({}, "Quantas horas dura?")
        assert r is not None

    def test_variante_tempo_consulta(self):
        from voice_agent.blindagens_deterministicas import deve_responder_faq_duracao
        r = deve_responder_faq_duracao({}, "Qual é o tempo de consulta?")
        assert r is not None

    def test_nao_dispara_sem_palavras_chave(self):
        from voice_agent.blindagens_deterministicas import deve_responder_faq_duracao
        r = deve_responder_faq_duracao({}, "Quero agendar uma consulta")
        assert r is None

    def test_nao_dispara_user_text_vazio(self):
        from voice_agent.blindagens_deterministicas import deve_responder_faq_duracao
        assert deve_responder_faq_duracao({}, "") is None
        assert deve_responder_faq_duracao({}, None) is None

    def test_ctx_none_nao_quebra(self):
        from voice_agent.blindagens_deterministicas import deve_responder_faq_duracao
        r = deve_responder_faq_duracao(None, "Quanto tempo demora?")
        assert r is not None  # sem ctx → resposta geral

    def test_toggle_off_retorna_none(self, monkeypatch):
        monkeypatch.setenv("BLINDAGEM_FAQ_DURACAO_ATIVADO", "0")
        m = _reload()
        r = m.deve_responder_faq_duracao({}, "Quanto tempo dura?")
        assert r is None

    def test_wiring_retorna_tuple_correto(self):
        from voice_agent.blindagens_deterministicas import tentar_bypass_deterministico
        ctx = _ctx(medico="karla")
        result = tentar_bypass_deterministico(ctx, "Quanto tempo demora a consulta?")
        assert result is not None
        name, text = result
        assert name == "faq_duracao_s10"
        assert "30" in text


# ---------------------------------------------------------------------------
# S11 — FAQ DILATAÇÃO
# ---------------------------------------------------------------------------

class TestS11Dilatacao:

    def test_vai_dilatar(self):
        from voice_agent.blindagens_deterministicas import deve_responder_faq_dilatacao
        r = deve_responder_faq_dilatacao({}, "Vai dilatar o olho?")
        assert r is not None
        assert "dilata" in r.lower()
        assert "médico" in r or "medico" in r.lower() or "indica" in r.lower()

    def test_posso_dirigir_depois(self):
        from voice_agent.blindagens_deterministicas import deve_responder_faq_dilatacao
        r = deve_responder_faq_dilatacao({}, "Posso dirigir depois da consulta?")
        assert r is not None
        assert "acompanhante" in r or "turva" in r or "colírio" in r.lower()

    def test_fundo_de_olho(self):
        from voice_agent.blindagens_deterministicas import deve_responder_faq_dilatacao
        r = deve_responder_faq_dilatacao({}, "Vai fazer fundo de olho?")
        assert r is not None

    def test_colirio_de_dilatacao(self):
        from voice_agent.blindagens_deterministicas import deve_responder_faq_dilatacao
        r = deve_responder_faq_dilatacao({}, "Precisa de colírio de dilatação?")
        assert r is not None

    def test_mapa_retina(self):
        from voice_agent.blindagens_deterministicas import deve_responder_faq_dilatacao
        r = deve_responder_faq_dilatacao({}, "Vai fazer mapa de retina?")
        assert r is not None

    def test_nao_dispara_sem_keywords(self):
        from voice_agent.blindagens_deterministicas import deve_responder_faq_dilatacao
        r = deve_responder_faq_dilatacao({}, "Qual o valor da consulta?")
        assert r is None

    def test_nao_dispara_vazio(self):
        from voice_agent.blindagens_deterministicas import deve_responder_faq_dilatacao
        assert deve_responder_faq_dilatacao({}, "") is None

    def test_toggle_off(self, monkeypatch):
        monkeypatch.setenv("BLINDAGEM_FAQ_DILATACAO_ATIVADO", "0")
        m = _reload()
        assert m.deve_responder_faq_dilatacao({}, "Vai dilatar?") is None

    def test_nao_obrigatoria_em_todos_casos(self):
        from voice_agent.blindagens_deterministicas import deve_responder_faq_dilatacao
        r = deve_responder_faq_dilatacao({}, "Vai usar colírio?")
        assert r is not None
        # Mensagem deve deixar claro que não é obrigatório em todos os casos
        assert "não" in r.lower() or "recomendamos" in r.lower()

    def test_wiring_retorna_tuple_correto(self):
        from voice_agent.blindagens_deterministicas import tentar_bypass_deterministico
        result = tentar_bypass_deterministico({}, "Vai dilatar o olho na consulta?")
        assert result is not None
        name, text = result
        assert name == "faq_dilatacao_s11"


# ---------------------------------------------------------------------------
# S13 — FAQ ENCAMINHAMENTO
# ---------------------------------------------------------------------------

class TestS13Encaminhamento:

    def test_preciso_de_encaminhamento_particular(self):
        from voice_agent.blindagens_deterministicas import deve_responder_faq_encaminhamento
        # Sem convênio → não precisa
        ctx = _ctx(convenio="Não se aplica")
        r = deve_responder_faq_encaminhamento(ctx, "Preciso de encaminhamento?")
        assert r is not None
        assert "não" in r.lower()
        assert "encaminhamento" in r.lower() or "pedido" in r.lower()

    def test_preciso_de_encaminhamento_convenio(self):
        from voice_agent.blindagens_deterministicas import deve_responder_faq_encaminhamento
        ctx = _ctx(convenio="Saúde Caixa")
        r = deve_responder_faq_encaminhamento(ctx, "Preciso de encaminhamento?")
        assert r is not None
        assert "convênio" in r.lower() or "plano" in r.lower()

    def test_sem_convenio_definido_responde_genericamente(self):
        from voice_agent.blindagens_deterministicas import deve_responder_faq_encaminhamento
        r = deve_responder_faq_encaminhamento({}, "Precisa de pedido médico?")
        assert r is not None

    def test_variante_pedido_do_clinico(self):
        from voice_agent.blindagens_deterministicas import deve_responder_faq_encaminhamento
        r = deve_responder_faq_encaminhamento({}, "Precisa de pedido do clínico geral?")
        assert r is not None

    def test_variante_precisa_de_guia(self):
        from voice_agent.blindagens_deterministicas import deve_responder_faq_encaminhamento
        r = deve_responder_faq_encaminhamento({}, "Tem que ter guia?")
        assert r is not None

    def test_sem_encaminhamento(self):
        from voice_agent.blindagens_deterministicas import deve_responder_faq_encaminhamento
        r = deve_responder_faq_encaminhamento({}, "Consigo marcar sem encaminhamento?")
        assert r is not None

    def test_nao_dispara_sem_keywords(self):
        from voice_agent.blindagens_deterministicas import deve_responder_faq_encaminhamento
        r = deve_responder_faq_encaminhamento({}, "Qual o horário da consulta?")
        assert r is None

    def test_nao_dispara_vazio(self):
        from voice_agent.blindagens_deterministicas import deve_responder_faq_encaminhamento
        assert deve_responder_faq_encaminhamento({}, "") is None

    def test_toggle_off(self, monkeypatch):
        monkeypatch.setenv("BLINDAGEM_FAQ_ENCAMINHAMENTO_ATIVADO", "0")
        m = _reload()
        assert m.deve_responder_faq_encaminhamento({}, "Preciso de encaminhamento?") is None

    def test_ctx_none_nao_quebra(self):
        from voice_agent.blindagens_deterministicas import deve_responder_faq_encaminhamento
        r = deve_responder_faq_encaminhamento(None, "Preciso de encaminhamento?")
        assert r is not None

    def test_particular_resposta_direta(self):
        from voice_agent.blindagens_deterministicas import deve_responder_faq_encaminhamento
        ctx = _ctx(convenio="Não se aplica")
        r = deve_responder_faq_encaminhamento(ctx, "Preciso levar encaminhamento?")
        # Resposta deve ser positiva e convidar para agendar
        assert "agendar" in r.lower() or "horários" in r.lower() or "verificar" in r.lower()

    def test_wiring_retorna_tuple_correto(self):
        from voice_agent.blindagens_deterministicas import tentar_bypass_deterministico
        result = tentar_bypass_deterministico({}, "Preciso de encaminhamento médico?")
        assert result is not None
        name, text = result
        assert name == "faq_encaminhamento_s13"


# ---------------------------------------------------------------------------
# S16 — FAQ MÍDIAS E ÁUDIOS GERAL
# ---------------------------------------------------------------------------

class TestS16MidiaGeral:

    def test_audio_evolution(self):
        from voice_agent.blindagens_deterministicas import deve_responder_faq_midia
        # Padrão Evolution
        r = deve_responder_faq_midia({}, "O paciente enviou um áudio pelo WhatsApp")
        assert r is not None
        assert "áudio" in r.lower() or "audio" in r.lower() or "texto" in r.lower()

    def test_audio_wa_cloud_audio_message(self):
        from voice_agent.blindagens_deterministicas import deve_responder_faq_midia
        r = deve_responder_faq_midia({}, "[audio message]")
        assert r is not None

    def test_audio_voice_message(self):
        from voice_agent.blindagens_deterministicas import deve_responder_faq_midia
        r = deve_responder_faq_midia({}, "[voice message]")
        assert r is not None

    def test_imagem_evolution(self):
        from voice_agent.blindagens_deterministicas import deve_responder_faq_midia
        r = deve_responder_faq_midia({}, "O paciente acabou de enviar uma imagem pelo WhatsApp")
        assert r is not None
        assert "imagem" in r.lower() or "documento" in r.lower() or "receb" in r.lower()

    def test_imagem_wa_cloud_image_message(self):
        from voice_agent.blindagens_deterministicas import deve_responder_faq_midia
        r = deve_responder_faq_midia({}, "[image message]")
        assert r is not None

    def test_imagem_photo_message(self):
        from voice_agent.blindagens_deterministicas import deve_responder_faq_midia
        r = deve_responder_faq_midia({}, "[photo message]")
        assert r is not None

    def test_documento_sintetico(self):
        from voice_agent.blindagens_deterministicas import deve_responder_faq_midia
        r = deve_responder_faq_midia({}, "O paciente enviou um documento pelo WhatsApp")
        assert r is not None

    def test_sticker_message(self):
        from voice_agent.blindagens_deterministicas import deve_responder_faq_midia
        r = deve_responder_faq_midia({}, "[sticker message]")
        assert r is not None

    def test_texto_normal_nao_dispara(self):
        from voice_agent.blindagens_deterministicas import deve_responder_faq_midia
        r = deve_responder_faq_midia({}, "Quero marcar uma consulta")
        assert r is None

    def test_vazio_nao_dispara(self):
        from voice_agent.blindagens_deterministicas import deve_responder_faq_midia
        assert deve_responder_faq_midia({}, "") is None
        assert deve_responder_faq_midia({}, None) is None

    def test_audio_pede_texto(self):
        from voice_agent.blindagens_deterministicas import deve_responder_faq_midia
        r = deve_responder_faq_midia({}, "[audio message]")
        assert r is not None
        # Mensagem de áudio deve pedir que o paciente escreva em texto
        assert "texto" in r.lower() or "escreva" in r.lower() or "escrever" in r.lower() or "mensagem" in r.lower()

    def test_toggle_off(self, monkeypatch):
        monkeypatch.setenv("BLINDAGEM_FAQ_MIDIA_ATIVADO", "0")
        m = _reload()
        assert m.deve_responder_faq_midia({}, "[audio message]") is None

    def test_wiring_audio_retorna_tuple_correto(self):
        from voice_agent.blindagens_deterministicas import tentar_bypass_deterministico
        result = tentar_bypass_deterministico({}, "[audio message]")
        assert result is not None
        name, text = result
        assert name == "faq_midia_s16"

    def test_wiring_imagem_retorna_tuple_correto(self):
        from voice_agent.blindagens_deterministicas import tentar_bypass_deterministico
        result = tentar_bypass_deterministico({}, "[image message]")
        assert result is not None
        name, text = result
        assert name == "faq_midia_s16"


# ---------------------------------------------------------------------------
# Teste de não-regressão: S10/S11/S13/S16 NÃO interferem em fluxos normais
# ---------------------------------------------------------------------------

class TestNaoRegressao:

    def test_agendamento_normal_nao_dispara_s10(self):
        from voice_agent.blindagens_deterministicas import deve_responder_faq_duracao
        # Paciente dando nome — não deve triggerar duracao
        assert deve_responder_faq_duracao({}, "Meu nome é João Silva") is None

    def test_convenio_normal_nao_dispara_s11(self):
        from voice_agent.blindagens_deterministicas import deve_responder_faq_dilatacao
        assert deve_responder_faq_dilatacao({}, "Meu convênio é o Bacen") is None

    def test_valor_nao_dispara_s13(self):
        from voice_agent.blindagens_deterministicas import deve_responder_faq_encaminhamento
        assert deve_responder_faq_encaminhamento({}, "Qual o valor da consulta?") is None

    def test_slot_aceite_nao_dispara_s16(self):
        from voice_agent.blindagens_deterministicas import deve_responder_faq_midia
        assert deve_responder_faq_midia({}, "1") is None
        assert deve_responder_faq_midia({}, "Quero o primeiro horário") is None

    def test_saudacao_nao_dispara_nenhum(self):
        from voice_agent.blindagens_deterministicas import (
            deve_responder_faq_duracao,
            deve_responder_faq_dilatacao,
            deve_responder_faq_encaminhamento,
            deve_responder_faq_midia,
        )
        for fn in [deve_responder_faq_duracao, deve_responder_faq_dilatacao,
                   deve_responder_faq_encaminhamento, deve_responder_faq_midia]:
            assert fn({}, "Olá, boa tarde!") is None
