"""Pytest do dispatcher de renovação — janela 24h + template 1039 + dedup.

Mocks injetáveis pra testar sem subir wa_cloud / redis / HTTP.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from unittest import mock

import pytest

from voice_agent.renovacao_dispatcher import (
    REDIS_KEY_FMT,
    SnapshotLead,
    dispatch_renovacao,
)


# ---------------------------------------------------------------------------
# Doubles
# ---------------------------------------------------------------------------

class FakeWA:
    def __init__(self, fail_on=None):
        self.text_calls = []
        self.template_calls = []
        self.fail_on = fail_on

    def send_text(self, *, to, text):
        if self.fail_on == "text":
            raise RuntimeError("simulado: send_text falhou")
        self.text_calls.append({"to": to, "text": text})
        return {"ok": True}

    def send_template(self, *, to, name, body_params=None, language="pt_BR"):
        if self.fail_on == "template":
            raise RuntimeError("simulado: send_template falhou")
        self.template_calls.append({
            "to": to, "name": name, "body_params": body_params,
        })
        return {"ok": True}


class FakeRedis:
    def __init__(self, ja_existente=False):
        self._store = {}
        if ja_existente:
            self._store["preexistente"] = True

    def get(self, key):
        return self._store.get(key)

    def set(self, key, value, ex=None):
        self._store[key] = value


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_AGORA = datetime(2026, 5, 31, 12, 0, tzinfo=timezone.utc).timestamp()


def _ts_horas_atras(h):
    return _AGORA - h * 3600


def _snap_em_conversa(**over):
    base = dict(
        lead_id=24048691,
        telefone_e164="(61) 99999-0000",
        nome_contato="Marcela",
        status_id=102560495,  # 2-AGENDAR
        ultima_msg_paciente_ts=_ts_horas_atras(23),
        paciente_ja_respondeu_na_vida=True,
    )
    base.update(over)
    return SnapshotLead(**base)


# ---------------------------------------------------------------------------
# Cenários de estratégia → ação
# ---------------------------------------------------------------------------

class TestFreeFormDispatch:

    def test_janela_aberta_envia_texto_livre(self):
        wa = FakeWA(); r = FakeRedis()
        res = dispatch_renovacao(_snap_em_conversa(), wa_client=wa,
                                  redis_client=r, agora=_AGORA)
        assert res.enviado is True
        assert res.estrategia == "free_form"
        assert len(wa.text_calls) == 1
        assert wa.text_calls[0]["to"] == "5561999990000"
        assert "Marcela" in wa.text_calls[0]["text"]
        assert "oi" in wa.text_calls[0]["text"].lower()
        # Redis recebeu dedup
        assert r.get("blink:janela:ultima_renovacao:24048691") is not None

    def test_dry_run_nao_envia(self):
        wa = FakeWA(); r = FakeRedis()
        res = dispatch_renovacao(_snap_em_conversa(), wa_client=wa,
                                  redis_client=r, agora=_AGORA, dry_run=True)
        assert res.enviado is False
        assert res.skipped is True
        assert res.razao_skip == "dry_run"
        # Preview foi montado
        assert "Marcela" in res.payload_preview["text"]
        # NÃO chamou WA
        assert wa.text_calls == []

    def test_falha_wa_nao_quebra(self):
        wa = FakeWA(fail_on="text"); r = FakeRedis()
        res = dispatch_renovacao(_snap_em_conversa(), wa_client=wa,
                                  redis_client=r, agora=_AGORA)
        assert res.enviado is False
        assert "send_text falhou" in res.erro


# ---------------------------------------------------------------------------
# Template 1039 — janela morta + lead frio
# ---------------------------------------------------------------------------

class TestTemplateDispatch:

    def test_janela_morta_dispara_template_1039(self):
        wa = FakeWA(); r = FakeRedis()
        snap = _snap_em_conversa(
            ultima_msg_paciente_ts=_ts_horas_atras(30),
        )
        res = dispatch_renovacao(snap, wa_client=wa, redis_client=r, agora=_AGORA)
        assert res.enviado is True
        assert res.estrategia == "template_1039"
        assert len(wa.template_calls) == 1
        chamada = wa.template_calls[0]
        assert chamada["to"] == "5561999990000"
        assert chamada["name"] == "1039_ativar_grau_de_urgencia"
        assert chamada["body_params"] == ["Marcela"]

    def test_lead_frio_puro_dispara_template_1039(self):
        wa = FakeWA(); r = FakeRedis()
        snap = _snap_em_conversa(
            status_id=101508307,  # 1.LEADS FRIO
            ultima_msg_paciente_ts=None,
            paciente_ja_respondeu_na_vida=False,
        )
        res = dispatch_renovacao(snap, wa_client=wa, redis_client=r, agora=_AGORA)
        assert res.enviado is True
        assert res.estrategia == "template_1039"
        assert len(wa.template_calls) == 1

    def test_template_dry_run_so_devolve_payload(self):
        wa = FakeWA(); r = FakeRedis()
        snap = _snap_em_conversa(ultima_msg_paciente_ts=_ts_horas_atras(30))
        res = dispatch_renovacao(snap, wa_client=wa, redis_client=r,
                                  agora=_AGORA, dry_run=True)
        assert res.skipped is True
        assert res.razao_skip == "dry_run"
        assert res.template_name == "1039_ativar_grau_de_urgencia"
        assert res.payload_preview["template"]["name"] == "1039_ativar_grau_de_urgencia"

    def test_falha_template_nao_quebra(self):
        wa = FakeWA(fail_on="template"); r = FakeRedis()
        snap = _snap_em_conversa(ultima_msg_paciente_ts=_ts_horas_atras(30))
        res = dispatch_renovacao(snap, wa_client=wa, redis_client=r, agora=_AGORA)
        assert res.enviado is False
        assert "send_template falhou" in res.erro


# ---------------------------------------------------------------------------
# Não disparar
# ---------------------------------------------------------------------------

class TestNaoDisparar:

    def test_lead_agendado_nao_dispara(self):
        wa = FakeWA(); r = FakeRedis()
        snap = _snap_em_conversa(
            status_id=101507507,  # 4-AGENDADO
        )
        res = dispatch_renovacao(snap, wa_client=wa, redis_client=r, agora=_AGORA)
        assert res.skipped is True
        assert res.enviado is False
        assert res.razao_skip == "status_pos_agendado"
        assert wa.text_calls == []
        assert wa.template_calls == []

    def test_delta_2h_ainda_cedo_nao_dispara(self):
        wa = FakeWA(); r = FakeRedis()
        snap = _snap_em_conversa(ultima_msg_paciente_ts=_ts_horas_atras(2))
        res = dispatch_renovacao(snap, wa_client=wa, redis_client=r, agora=_AGORA)
        assert res.skipped is True

    def test_telefone_invalido_skip(self):
        wa = FakeWA(); r = FakeRedis()
        snap = _snap_em_conversa(telefone_e164="abc")
        res = dispatch_renovacao(snap, wa_client=wa, redis_client=r, agora=_AGORA)
        assert res.skipped is True
        assert res.razao_skip == "telefone_invalido"


# ---------------------------------------------------------------------------
# Dedup Redis
# ---------------------------------------------------------------------------

class TestDedup:

    def test_segunda_chamada_nao_dispara(self):
        wa = FakeWA(); r = FakeRedis()
        snap = _snap_em_conversa()
        res1 = dispatch_renovacao(snap, wa_client=wa, redis_client=r, agora=_AGORA)
        assert res1.enviado is True
        res2 = dispatch_renovacao(snap, wa_client=wa, redis_client=r, agora=_AGORA)
        assert res2.enviado is False
        assert res2.skipped is True
        assert res2.razao_skip == "ja_disparado_nesta_janela"
        assert res2.dedup_ja_existia is True

    def test_forcar_redispatch_ignora_dedup(self):
        wa = FakeWA(); r = FakeRedis()
        snap = _snap_em_conversa()
        dispatch_renovacao(snap, wa_client=wa, redis_client=r, agora=_AGORA)
        # Segundo disparo com forcar=True
        res = dispatch_renovacao(snap, wa_client=wa, redis_client=r,
                                  agora=_AGORA, forcar_redispatch=True)
        assert res.enviado is True

    def test_sem_redis_nao_quebra(self):
        wa = FakeWA()
        snap = _snap_em_conversa()
        res = dispatch_renovacao(snap, wa_client=wa, redis_client=None,
                                  agora=_AGORA)
        # Funciona sem Redis (apenas perde dedup persistente).
        assert res.enviado is True
        assert res.dedup_chave == "blink:janela:ultima_renovacao:24048691"

    def test_redis_falha_get_nao_quebra(self):
        class RBroken:
            def get(self, k): raise RuntimeError("redis down")
            def set(self, k, v, ex=None): raise RuntimeError("redis down")
        wa = FakeWA(); r = RBroken()
        snap = _snap_em_conversa()
        # Não deve levantar
        res = dispatch_renovacao(snap, wa_client=wa, redis_client=r,
                                  agora=_AGORA)
        # Dedup falhou silenciosamente; envio continua
        assert res.enviado is True


# ---------------------------------------------------------------------------
# Visibilidade Kommo — nota gravada por disparo
# ---------------------------------------------------------------------------

class FakeKommo:
    def __init__(self, fail=False):
        self.notes = []
        self.fail = fail

    def add_note(self, lead_id, text):
        if self.fail:
            raise RuntimeError("kommo timeout")
        self.notes.append({"lead_id": lead_id, "text": text})


class TestNotaKommo:

    def test_free_form_grava_nota_no_kommo(self):
        wa = FakeWA(); r = FakeRedis(); k = FakeKommo()
        snap = _snap_em_conversa()
        res = dispatch_renovacao(snap, wa_client=wa, redis_client=r,
                                  kommo_note_writer=k, agora=_AGORA)
        assert res.enviado is True
        assert res.kommo_nota["ok"] is True
        assert len(k.notes) == 1
        nota = k.notes[0]
        assert nota["lead_id"] == 24048691
        # Estrutura da nota
        assert "Motor de Renovação 24h" in nota["text"]
        assert "WhatsApp 8133" in nota["text"]
        assert "texto livre" in nota["text"]
        assert "Marcela" in nota["text"]
        assert "5561999990000" in nota["text"]
        # E o texto enviado entra na nota
        assert "Blink Oftalmologia" in nota["text"]

    def test_template_grava_nota_com_descricao_template(self):
        wa = FakeWA(); r = FakeRedis(); k = FakeKommo()
        snap = _snap_em_conversa(ultima_msg_paciente_ts=_ts_horas_atras(30))
        res = dispatch_renovacao(snap, wa_client=wa, redis_client=r,
                                  kommo_note_writer=k, agora=_AGORA)
        assert res.enviado is True
        assert len(k.notes) == 1
        texto = k.notes[0]["text"]
        assert "template 1039" in texto
        assert "1039_ativar_grau_de_urgencia" in texto
        assert "{1}" in texto and "Marcela" in texto
        assert "Botões" in texto

    def test_dry_run_NAO_grava_mas_devolve_nota_preview(self):
        wa = FakeWA(); r = FakeRedis(); k = FakeKommo()
        snap = _snap_em_conversa()
        res = dispatch_renovacao(snap, wa_client=wa, redis_client=r,
                                  kommo_note_writer=k, agora=_AGORA,
                                  dry_run=True)
        assert res.skipped is True
        assert k.notes == []
        # Mas a nota_preview foi montada
        assert res.nota_preview is not None
        assert "texto livre" in res.nota_preview
        assert "Marcela" in res.nota_preview

    def test_kommo_falha_NAO_desfaz_envio(self):
        wa = FakeWA(); r = FakeRedis(); k = FakeKommo(fail=True)
        snap = _snap_em_conversa()
        res = dispatch_renovacao(snap, wa_client=wa, redis_client=r,
                                  kommo_note_writer=k, agora=_AGORA)
        # WhatsApp já foi enviado mesmo com Kommo quebrado
        assert res.enviado is True
        assert len(wa.text_calls) == 1
        # Mas o status da nota é registrado como falha
        assert res.kommo_nota["ok"] is False
        assert "kommo timeout" in res.kommo_nota["reason"]

    def test_sem_kommo_writer_envia_normalmente(self):
        wa = FakeWA(); r = FakeRedis()
        snap = _snap_em_conversa()
        res = dispatch_renovacao(snap, wa_client=wa, redis_client=r,
                                  kommo_note_writer=None, agora=_AGORA)
        assert res.enviado is True
        # Kommo nota não foi tentada
        assert res.kommo_nota is None or res.kommo_nota.get("skipped") is True

    def test_writer_funcao_simples_funciona(self):
        chamadas = []
        def fake_writer(lead_id, nota):
            chamadas.append((lead_id, nota))
        wa = FakeWA(); r = FakeRedis()
        snap = _snap_em_conversa()
        res = dispatch_renovacao(snap, wa_client=wa, redis_client=r,
                                  kommo_note_writer=fake_writer, agora=_AGORA)
        assert res.enviado is True
        assert len(chamadas) == 1
        assert chamadas[0][0] == 24048691
        assert "Marcela" in chamadas[0][1]

    def test_nota_tem_data_hora_brt(self):
        wa = FakeWA(); r = FakeRedis(); k = FakeKommo()
        snap = _snap_em_conversa()
        dispatch_renovacao(snap, wa_client=wa, redis_client=r,
                           kommo_note_writer=k, agora=_AGORA)
        nota = k.notes[0]["text"]
        # Formato DD/MM/AAAA HH:MM BRT
        import re
        assert re.search(r"\d{2}/\d{2}/\d{4} \d{2}:\d{2} BRT", nota), nota
