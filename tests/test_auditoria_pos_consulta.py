"""Pytest blindando a auditoria pós-consulta (seções 24 e 25).

Cenários cobertos agora (função pura comparar_agrupamento):
  1. coincide perfeito → coincide=True
  2. realizado tem item a mais → exames_a_mais detectado
  3. planejado tem item a menos → exames_a_menos detectado
  4. ambos com diferenças simultâneas → ambos detectados
  5. planejado vazio → fonte_vazia=True
  6. realizado vazio → fonte_vazia=True
  7. ambos vazios → fonte_vazia=True

Cenários a cobrir quando processar_lead_realizado for implementado
(task #82): orquestração, Slack, Kommo, dupla assinatura, timeout.
"""
from __future__ import annotations

import pytest

from datetime import datetime, timedelta, timezone

from voice_agent.auditoria import (
    AuditoriaStatus,
    KOMMO_AUDITORIA_FIELDS,
    KOMMO_AUDITORIA_STATUS_ENUMS,
    PacienteAuditoria,
    ResultadoAuditoria,
    ResultadoComparacao,
    comparar_agrupamento,
    confirmar_assinatura,
    detectar_timeouts,
    enviar_slack_auditoria,
    kommo_field_id,
    kommo_status_enum_id,
    montar_mensagem_coincide,
    montar_mensagem_slack,
    processar_lead_realizado,
    _slug_unidade,
)


class TestCompararAgrupamento:

    def test_coincide_perfeito(self):
        r = comparar_agrupamento([1, 2, 3], [3, 2, 1])
        assert r.coincide is True
        assert r.exames_a_mais == []
        assert r.exames_a_menos == []
        assert r.fonte_vazia is False

    def test_realizado_a_mais(self):
        r = comparar_agrupamento(
            planejado=[1, 2, 3],
            realizado=[1, 2, 3, 7],
        )
        assert r.coincide is False
        assert r.exames_a_mais == [7]
        assert r.exames_a_menos == []

    def test_realizado_a_menos(self):
        r = comparar_agrupamento(
            planejado=[1, 2, 3, 9],
            realizado=[1, 2],
        )
        assert r.coincide is False
        assert r.exames_a_mais == []
        assert r.exames_a_menos == [3, 9]

    def test_a_mais_e_a_menos_simultaneo(self):
        r = comparar_agrupamento(
            planejado=[1, 2, 3],
            realizado=[1, 2, 8, 9],
        )
        assert r.coincide is False
        assert r.exames_a_mais == [8, 9]
        assert r.exames_a_menos == [3]

    def test_planejado_vazio_e_fonte_vazia(self):
        r = comparar_agrupamento(planejado=[], realizado=[1, 2])
        assert r.coincide is False
        assert r.fonte_vazia is True
        assert r.razao_fonte_vazia is not None
        assert "planejado vazio" in r.razao_fonte_vazia

    def test_realizado_vazio_e_fonte_vazia(self):
        r = comparar_agrupamento(planejado=[1, 2], realizado=None)
        assert r.coincide is False
        assert r.fonte_vazia is True
        assert "realizado vazio" in r.razao_fonte_vazia

    def test_ambos_vazios_e_fonte_vazia(self):
        r = comparar_agrupamento(planejado=None, realizado=None)
        assert r.fonte_vazia is True
        assert "ambos vazios" in r.razao_fonte_vazia

    def test_duplicatas_no_realizado_nao_geram_falso_a_mais(self):
        # Medware pode retornar mesmo procedimento 2x — só conta uma.
        r = comparar_agrupamento(
            planejado=[1, 2, 3],
            realizado=[1, 1, 2, 3],
        )
        assert r.coincide is True


class TestMensagemSlack:

    def test_inclui_seccao_a_mais_quando_houver(self):
        r = ResultadoComparacao(
            coincide=False, exames_a_mais=[7], exames_a_menos=[],
        )
        msg = montar_mensagem_slack(
            lead_id=12345,
            paciente_idx=1,
            paciente_nome="Maria Silva",
            medico_nome="Dra. Karla Delalíbera",
            unidade="Asa Norte",
            convenio="Saúde Caixa",
            agrupador_planejado="AGRUPADOR_1_ADULTO_ROTINA — 9 exames",
            resultado=r,
            nomes_procedimentos={7: "RETINOGRAFIA"},
            kommo_url="https://univeja.kommo.com/leads/detail/12345",
        )
        assert "Lead: 12345" in msg
        assert "Paciente 1: Maria Silva" in msg
        assert "Secretaria Asa Norte" in msg
        assert "Dra. Karla Delalíbera" in msg
        assert "7 — RETINOGRAFIA" in msg
        assert "a MENOS" not in msg
        assert "https://univeja.kommo.com/leads/detail/12345" in msg

    def test_inclui_seccao_a_menos_quando_houver(self):
        r = ResultadoComparacao(
            coincide=False, exames_a_mais=[], exames_a_menos=[5],
        )
        msg = montar_mensagem_slack(
            lead_id=99,
            paciente_idx=2,
            paciente_nome="João Costa",
            medico_nome="Dr. Fabrício Freitas",
            unidade="Águas Claras",
            convenio="Sem convênio",
            agrupador_planejado="AGRUPADOR_2_ADULTO_EMERGENCIA",
            resultado=r,
            nomes_procedimentos={5: "BIOMETRIA"},
        )
        assert "Secretaria Águas Claras" in msg
        assert "a MENOS" in msg
        assert "5 — BIOMETRIA" in msg
        assert "a MAIS" not in msg


class TestSlugUnidade:

    def test_asa_norte(self):
        assert _slug_unidade("Asa Norte") == "asa-norte"

    def test_aguas_claras_com_acento(self):
        assert _slug_unidade("Águas Claras") == "aguas-claras"

    def test_vazio_devolve_vazio(self):
        assert _slug_unidade("") == ""
        assert _slug_unidade(None) == ""


class TestEstadoStatus:
    """Garante que enum não regrediu sem aviso."""

    def test_status_estao_disponiveis(self):
        assert AuditoriaStatus.AGUARDANDO_SECRETARIA.value == "aguardando_secretaria"
        assert AuditoriaStatus.AGUARDANDO_MEDICO.value == "aguardando_medico"
        assert AuditoriaStatus.FECHADA.value == "fechada"
        assert AuditoriaStatus.DIVERGENCIA.value == "divergencia"
        assert AuditoriaStatus.FONTE_VAZIA.value == "fonte_vazia"


class TestKommoFieldIds:
    """Garante que o mapeamento Kommo→Python casa com o que foi criado em
    31/05/2026 via Chrome MCP. Se algum ID mudar (ex.: campo deletado e
    recriado), pytest avisa."""

    def test_tem_6_pacientes_cadastrados(self):
        assert set(KOMMO_AUDITORIA_FIELDS.keys()) == {1, 2, 3, 4, 5, 6}
        assert set(KOMMO_AUDITORIA_STATUS_ENUMS.keys()) == {1, 2, 3, 4, 5, 6}

    def test_cada_paciente_tem_4_field_ids(self):
        for idx in range(1, 7):
            bucket = KOMMO_AUDITORIA_FIELDS[idx]
            assert set(bucket.keys()) == {"alterado", "status", "sec", "med"}
            for fid in bucket.values():
                assert isinstance(fid, int) and fid > 0

    def test_cada_status_tem_5_enums(self):
        for idx in range(1, 7):
            enums = KOMMO_AUDITORIA_STATUS_ENUMS[idx]
            assert set(enums.keys()) == {
                "aguardando_secretaria", "aguardando_medico",
                "fechada", "divergencia", "fonte_vazia",
            }

    def test_helper_field_id(self):
        assert kommo_field_id(3, "status") == 1260773
        assert kommo_field_id(1, "alterado") == 1260763
        assert kommo_field_id(6, "med") == 1260809

    def test_helper_field_id_paciente_invalido(self):
        assert kommo_field_id(7, "status") is None
        assert kommo_field_id(0, "status") is None

    def test_helper_field_id_papel_invalido(self):
        assert kommo_field_id(1, "inexistente") is None

    def test_helper_status_enum_aceita_string(self):
        assert kommo_status_enum_id(1, "fechada") == 926957
        assert kommo_status_enum_id(4, "divergencia") == 926989

    def test_helper_status_enum_aceita_enum(self):
        assert kommo_status_enum_id(2, AuditoriaStatus.FECHADA) == 926967
        assert kommo_status_enum_id(5, AuditoriaStatus.DIVERGENCIA) == 926999

    def test_helper_status_enum_invalido(self):
        assert kommo_status_enum_id(99, "fechada") is None
        assert kommo_status_enum_id(1, "inexistente") is None

    def test_field_ids_unicos_globalmente(self):
        # Nenhum field_id se repete entre pacientes/papéis.
        todos = []
        for bucket in KOMMO_AUDITORIA_FIELDS.values():
            todos.extend(bucket.values())
        assert len(todos) == len(set(todos)), "field_ids duplicados detectados"

    def test_enum_ids_unicos_globalmente(self):
        todos = []
        for bucket in KOMMO_AUDITORIA_STATUS_ENUMS.values():
            todos.extend(bucket.values())
        assert len(todos) == len(set(todos)), "enum_ids duplicados detectados"


# ---------------------------------------------------------------------------
# Sender Slack (com mock)
# ---------------------------------------------------------------------------

class _FakeResp:
    def __init__(self, status_code=200, body=None):
        self.status_code = status_code
        self._body = body or {"ok": True, "ts": "1780000000.000100", "channel": "C0B83BK5SMN"}

    def json(self):
        return self._body


class TestSlackSender:

    def test_sem_token_retorna_skipped(self):
        r = enviar_slack_auditoria("oi", bot_token="")
        assert r["skipped"] is True
        assert r["ok"] is False
        assert "vazio" in r["reason"]

    def test_envia_quando_tem_token_e_mock(self):
        calls = []
        def fake_post(url, headers, json_body):
            calls.append({"url": url, "headers": headers, "body": json_body})
            return _FakeResp(200)
        r = enviar_slack_auditoria(
            "mensagem", bot_token="xoxb-test", channel_id="C123", http_post=fake_post,
        )
        assert r["ok"] is True
        assert r["ts"] == "1780000000.000100"
        assert r["skipped"] is False
        assert len(calls) == 1
        assert calls[0]["url"] == "https://slack.com/api/chat.postMessage"
        assert "Bearer xoxb-test" in calls[0]["headers"]["Authorization"]
        assert calls[0]["body"]["channel"] == "C123"
        assert calls[0]["body"]["text"] == "mensagem"

    def test_slack_erro_devolvido(self):
        def fake_post(url, headers, json_body):
            return _FakeResp(200, {"ok": False, "error": "channel_not_found"})
        r = enviar_slack_auditoria(
            "x", bot_token="xoxb-test", http_post=fake_post,
        )
        assert r["ok"] is False
        assert r["reason"] == "channel_not_found"

    def test_excecao_capturada(self):
        def fake_post(*a, **k):
            raise RuntimeError("network down")
        r = enviar_slack_auditoria(
            "x", bot_token="xoxb-test", http_post=fake_post,
        )
        assert r["ok"] is False
        assert "network down" in r["reason"]


# ---------------------------------------------------------------------------
# Orquestrador
# ---------------------------------------------------------------------------

def _paciente_fake(idx, planejado, realizado, nome="Maria Silva"):
    return PacienteAuditoria(
        idx=idx, nome=nome, medico_nome="Dra. Karla Delalíbera",
        unidade="Asa Norte", convenio="Saúde Caixa",
        agrupador_planejado="AGRUPADOR_1_ADULTO_ROTINA",
        planejado_codigos=planejado, realizado_codigos=realizado,
        nomes_procedimentos={5: "BIOMETRIA", 7: "RETINOGRAFIA"},
    )


class TestOrquestrador:

    def test_coincide_status_fechada_slack_chamado(self):
        slacks = []
        def fake_slack(msg):
            slacks.append(msg)
            return {"ok": True, "skipped": False, "ts": "1", "channel": "C0B83BK5SMN", "reason": None}
        ress = processar_lead_realizado(
            lead_id=99,
            pacientes=[_paciente_fake(1, [1, 2, 3], [1, 2, 3])],
            slack_sender=fake_slack,
        )
        assert len(ress) == 1
        assert ress[0].status == AuditoriaStatus.FECHADA
        assert ress[0].comparacao.coincide is True
        assert len(slacks) == 1
        assert "sem discrepância" in slacks[0]

    def test_discrepancia_status_aguardando_secretaria(self):
        ress = processar_lead_realizado(
            lead_id=100,
            pacientes=[_paciente_fake(1, [1, 2, 3], [1, 2, 3, 7])],
            slack_sender=lambda m: {"ok": True, "skipped": False, "ts": "2", "channel": "x", "reason": None},
        )
        assert ress[0].status == AuditoriaStatus.AGUARDANDO_SECRETARIA
        assert ress[0].comparacao.exames_a_mais == [7]

    def test_fonte_vazia_status_fonte_vazia(self):
        ress = processar_lead_realizado(
            lead_id=101,
            pacientes=[_paciente_fake(1, [], [1])],
            slack_sender=lambda m: {"ok": True, "skipped": False, "ts": "3", "channel": "x", "reason": None},
        )
        assert ress[0].status == AuditoriaStatus.FONTE_VAZIA

    def test_kommo_writer_recebe_status_correto(self):
        kommo_calls = []
        def fake_kommo(lead_id, p_idx, enum_id, alterado):
            kommo_calls.append({"lead": lead_id, "p": p_idx, "enum": enum_id, "alt": alterado})
            return {"ok": True}
        processar_lead_realizado(
            lead_id=200,
            pacientes=[_paciente_fake(2, [1, 2], [1, 2, 9])],
            slack_sender=lambda m: {"ok": True, "skipped": False, "ts": "4", "channel": "x", "reason": None},
            kommo_writer=fake_kommo,
        )
        assert len(kommo_calls) == 1
        # paciente 2 + AGUARDANDO_SECRETARIA → enum 926963.
        assert kommo_calls[0]["enum"] == 926963
        assert kommo_calls[0]["alt"] is True

    def test_kommo_writer_excecao_nao_quebra(self):
        def kommo_quebrado(lead_id, p_idx, enum_id, alterado):
            raise RuntimeError("kommo down")
        ress = processar_lead_realizado(
            lead_id=300,
            pacientes=[_paciente_fake(1, [1], [1])],
            slack_sender=lambda m: {"ok": True, "skipped": False, "ts": "5", "channel": "x", "reason": None},
            kommo_writer=kommo_quebrado,
        )
        assert ress[0].kommo["ok"] is False
        assert "kommo down" in ress[0].kommo["error"]


# ---------------------------------------------------------------------------
# Confirmar assinatura — dupla checagem
# ---------------------------------------------------------------------------

class TestConfirmarAssinatura:

    def test_secretaria_ok_avanca_para_medico(self):
        r = confirmar_assinatura(
            lead_id=1, paciente_idx=1, papel="secretaria_an",
            decisao="ok", autor="Mariana",
            status_atual=AuditoriaStatus.AGUARDANDO_SECRETARIA,
        )
        assert r["novo_status"] == AuditoriaStatus.AGUARDANDO_MEDICO
        assert r["campo_assinatura"] == "sec"
        assert "Mariana" in r["assinatura"]
        assert r["criar_tarefa_humana"] is False

    def test_medico_ok_apos_secretaria_fecha_ciclo(self):
        r = confirmar_assinatura(
            lead_id=1, paciente_idx=1, papel="medico_karla",
            decisao="ok", autor="Karla",
            status_atual=AuditoriaStatus.AGUARDANDO_MEDICO,
        )
        assert r["novo_status"] == AuditoriaStatus.FECHADA
        assert r.get("ciclo_fechado") is True

    def test_medico_tenta_assinar_antes_da_secretaria_rejeitado(self):
        r = confirmar_assinatura(
            lead_id=1, paciente_idx=1, papel="medico_karla",
            decisao="ok", autor="Karla",
            status_atual=AuditoriaStatus.AGUARDANDO_SECRETARIA,
        )
        assert r["novo_status"] == AuditoriaStatus.AGUARDANDO_SECRETARIA
        assert r.get("erro") == "secretaria ainda não confirmou"

    def test_divergente_fecha_em_qualquer_papel(self):
        r1 = confirmar_assinatura(
            lead_id=1, paciente_idx=1, papel="secretaria_ac",
            decisao="divergente", autor="Ana",
            status_atual=AuditoriaStatus.AGUARDANDO_SECRETARIA,
        )
        assert r1["novo_status"] == AuditoriaStatus.DIVERGENCIA
        assert r1["criar_tarefa_humana"] is True
        r2 = confirmar_assinatura(
            lead_id=2, paciente_idx=1, papel="medico_fabricio",
            decisao="divergente", autor="Fabrício",
            status_atual=AuditoriaStatus.AGUARDANDO_MEDICO,
        )
        assert r2["novo_status"] == AuditoriaStatus.DIVERGENCIA

    def test_idempotente_secretaria_duas_vezes(self):
        r1 = confirmar_assinatura(
            lead_id=1, paciente_idx=1, papel="secretaria_an",
            decisao="ok", autor="Mariana",
            status_atual=AuditoriaStatus.AGUARDANDO_MEDICO,
        )
        assert r1["novo_status"] == AuditoriaStatus.AGUARDANDO_MEDICO
        assert r1.get("ja_assinado") is True

    def test_idempotente_medico_apos_fechada(self):
        r = confirmar_assinatura(
            lead_id=1, paciente_idx=1, papel="medico_karla",
            decisao="ok", autor="Karla",
            status_atual=AuditoriaStatus.FECHADA,
        )
        assert r["novo_status"] == AuditoriaStatus.FECHADA
        assert r.get("ja_assinado") is True

    def test_papel_invalido_levanta(self):
        with pytest.raises(ValueError):
            confirmar_assinatura(
                lead_id=1, paciente_idx=1, papel="enfermeira",
                decisao="ok", autor="Ana",
                status_atual=AuditoriaStatus.AGUARDANDO_SECRETARIA,
            )

    def test_decisao_invalida_levanta(self):
        with pytest.raises(ValueError):
            confirmar_assinatura(
                lead_id=1, paciente_idx=1, papel="secretaria_an",
                decisao="talvez", autor="Ana",
                status_atual=AuditoriaStatus.AGUARDANDO_SECRETARIA,
            )

    def test_status_atual_string_aceito(self):
        r = confirmar_assinatura(
            lead_id=1, paciente_idx=1, papel="secretaria_an",
            decisao="ok", autor="Mariana",
            status_atual="aguardando_secretaria",
        )
        assert r["novo_status"] == AuditoriaStatus.AGUARDANDO_MEDICO


# ---------------------------------------------------------------------------
# Timeouts
# ---------------------------------------------------------------------------

class TestDetectarTimeouts:

    def test_pendencia_recente_nao_dispara(self):
        agora = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
        pings = detectar_timeouts(
            [{"lead_id": 1, "paciente_idx": 1,
              "status": AuditoriaStatus.AGUARDANDO_SECRETARIA,
              "criado_em": agora - timedelta(hours=2)}],
            agora=agora, timeout_horas=48,
        )
        assert pings == []

    def test_pendencia_velha_dispara_ping(self):
        agora = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
        pings = detectar_timeouts(
            [{"lead_id": 42, "paciente_idx": 3,
              "status": AuditoriaStatus.AGUARDANDO_SECRETARIA,
              "criado_em": agora - timedelta(hours=49)}],
            agora=agora, timeout_horas=48,
        )
        assert len(pings) == 1
        assert pings[0]["lead_id"] == 42
        assert pings[0]["horas_pendente"] == 49
        assert "lead 42" in pings[0]["mensagem"]

    def test_status_fechada_nao_gera_ping(self):
        agora = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
        pings = detectar_timeouts(
            [{"lead_id": 1, "paciente_idx": 1,
              "status": AuditoriaStatus.FECHADA,
              "criado_em": agora - timedelta(hours=200)}],
            agora=agora, timeout_horas=48,
        )
        assert pings == []

    def test_aceita_status_como_string(self):
        agora = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
        pings = detectar_timeouts(
            [{"lead_id": 7, "paciente_idx": 2,
              "status": "aguardando_medico",
              "criado_em": agora - timedelta(hours=50)}],
            agora=agora, timeout_horas=48,
        )
        assert len(pings) == 1
        assert pings[0]["status"] == "aguardando_medico"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
