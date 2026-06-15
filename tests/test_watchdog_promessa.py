"""Pytest watchdog_promessa — fecha brecha 'Lia prometeu e não voltou'.

Origem: bugs Carolina 24145994, Cecília 21500693, Fernanda 24145890,
Lílian 24146092, Maitê 24128026, Carmen 24142996.

Cobre detecção pura + extração de campos + tick com mocks.
"""

import time
from unittest.mock import MagicMock

import pytest

from voice_agent.watchdog_promessa import (
    texto_contem_promessa,
    texto_contem_resposta_real,
    eh_promessa_nao_cumprida,
    avaliar_lead,
    tratar_lead,
    tick,
    FIELD_ULTIMA_MSG_OUTBOUND,
    FIELD_ULTIMA_MENS_LIA,
    STATUS_ATENDIMENTO_HUMANO,
    STATUS_CONVERSAVEIS_LIA,
)


# ============================================================
# Detector de texto — promessa
# ============================================================

class TestTextoContemPromessa:
    def test_deixa_eu_consultar(self):
        assert texto_contem_promessa("Deixa eu consultar a agenda real aqui pra você")

    def test_deixa_eu_reconsultar(self):
        assert texto_contem_promessa("Deixa eu reconsultar a agenda")

    def test_um_minutinho(self):
        assert texto_contem_promessa("Um minutinho que volto com as opções")

    def test_um_minuto(self):
        assert texto_contem_promessa("Aguarda um minuto que já te respondo")

    def test_ja_volto(self):
        assert texto_contem_promessa("Já volto com os horários")

    def test_vou_buscar(self):
        assert texto_contem_promessa("Vou buscar os slots disponíveis")

    def test_ainda_estou_buscando(self):
        assert texto_contem_promessa("Ainda estou buscando os horários")

    def test_caso_real_fernanda_24145890(self):
        """Texto literal do bug Fernanda 13/06/2026 08:48 BRT."""
        text = (
            "Combinado! Deixa eu consultar os horários disponíveis para "
            "quarta-feira de manhã (meio ou fim) na Asa Norte com a Dra. "
            "Karla. Um minutinho que volto com as opções concretas pra você."
        )
        assert texto_contem_promessa(text)

    def test_caso_real_kamila_24064723(self):
        """Texto do bug Kamila 02/06."""
        text = (
            "Kamila, ainda estou buscando os horários disponíveis para "
            "quarta-feira de manhã com a Dra. Karla na Asa Norte. Aguarda "
            "só mais um pouquinho que já te passo as opções concretas, ok?"
        )
        assert texto_contem_promessa(text)

    def test_caso_real_alice_21256807(self):
        """Texto Alice 00:11 BRT — vou consultar sem voltar."""
        text = "Vou consultar a agenda e já te retorno!"
        assert texto_contem_promessa(text)

    def test_acknowledgement_normal_nao_dispara(self):
        # Resposta legítima curta sem promessa
        assert not texto_contem_promessa("Perfeito, obrigada!")

    def test_pergunta_normal_nao_dispara(self):
        assert not texto_contem_promessa(
            "Qual sua preferência de turno: manhã ou tarde?"
        )

    def test_texto_vazio(self):
        assert not texto_contem_promessa("")
        assert not texto_contem_promessa(None)


# ============================================================
# Detector de resposta real — cancela promessa
# ============================================================

class TestTextoContemRespostaReal:
    def test_dois_slots_canonicos(self):
        text = (
            "1️⃣ Cecília às 10:30 + Helena às 11:00\n"
            "2️⃣ Cecília às 11:00 + Helena às 11:30"
        )
        assert texto_contem_resposta_real(text)

    def test_tenho_n_horarios(self):
        assert texto_contem_resposta_real("Tenho 2 horários disponíveis pra você")

    def test_horario_hh_mm(self):
        assert texto_contem_resposta_real("Que tal 09:30 na terça?")

    def test_horario_hxxh(self):
        assert texto_contem_resposta_real("Tenho 10h30 disponível")

    def test_agendamento_confirmado(self):
        assert texto_contem_resposta_real("Agendamento confirmado!")

    def test_sem_slot_nao_dispara(self):
        assert not texto_contem_resposta_real(
            "Vou consultar a agenda e volto"
        )


# ============================================================
# Lógica temporal — janela de silêncio
# ============================================================

class TestEhPromessaNaoCumprida:
    def test_silencio_abaixo_min_nao_dispara(self):
        # 1 min de silêncio — normal
        assert not eh_promessa_nao_cumprida(
            ultima_msg_outbound="Deixa eu consultar a agenda",
            ts_ultima_msg_lia=int(time.time()) - 60,
        )

    def test_silencio_5min_dispara(self):
        assert eh_promessa_nao_cumprida(
            ultima_msg_outbound="Um minutinho que volto",
            ts_ultima_msg_lia=int(time.time()) - 5 * 60,
        )

    def test_silencio_30min_dispara(self):
        assert eh_promessa_nao_cumprida(
            ultima_msg_outbound="Vou buscar os horários",
            ts_ultima_msg_lia=int(time.time()) - 30 * 60,
        )

    def test_silencio_acima_max_nao_dispara(self):
        # 3h — passou da janela, lead esquecido
        assert not eh_promessa_nao_cumprida(
            ultima_msg_outbound="Vou consultar",
            ts_ultima_msg_lia=int(time.time()) - 3 * 60 * 60,
        )

    def test_promessa_com_resposta_real_nao_dispara(self):
        # Lia disse "vou consultar" MAS já listou os slots — não está pendente
        text = (
            "Vou consultar a agenda. Tenho 2 horários disponíveis: "
            "1️⃣ Terça 10:30 / 2️⃣ Quinta 11:00"
        )
        assert not eh_promessa_nao_cumprida(
            ultima_msg_outbound=text,
            ts_ultima_msg_lia=int(time.time()) - 10 * 60,
        )

    def test_texto_sem_promessa_nao_dispara(self):
        assert not eh_promessa_nao_cumprida(
            ultima_msg_outbound="Qual seu convênio?",
            ts_ultima_msg_lia=int(time.time()) - 10 * 60,
        )

    def test_ts_zero_nao_dispara(self):
        assert not eh_promessa_nao_cumprida(
            ultima_msg_outbound="Vou consultar",
            ts_ultima_msg_lia=0,
        )


# ============================================================
# Avaliar lead — integração com payload Kommo
# ============================================================

def _make_lead(
    lead_id: int = 24145890,
    status_id: int = 102560495,  # 3-AGENDAR
    ultima_msg: str = "Deixa eu consultar a agenda. Um minutinho.",
    minutos_atras: int = 10,
) -> dict:
    ts = int(time.time()) - minutos_atras * 60
    return {
        "id": lead_id,
        "status_id": status_id,
        "custom_fields": [
            {"field_id": FIELD_ULTIMA_MSG_OUTBOUND, "values": [{"value": ultima_msg}]},
            {"field_id": FIELD_ULTIMA_MENS_LIA, "values": [{"value": ts}]},
        ],
    }


class TestAvaliarLead:
    def test_lead_promessa_pendente_em_agendar(self):
        lead = _make_lead()
        r = avaliar_lead(lead)
        assert r["tratar"] is True
        assert r["lead_id"] == 24145890
        assert r["silencio_min"] >= 9.5

    def test_lead_fora_de_status_conversavel(self):
        lead = _make_lead(status_id=101507507)  # 5-AGENDADO
        r = avaliar_lead(lead)
        assert r["tratar"] is False

    def test_lead_em_atendimento_humano_nao_dispara(self):
        # 1-ATENDIMENTO HUMANO — humano já assumiu
        lead = _make_lead(status_id=106563343)
        r = avaliar_lead(lead)
        assert r["tratar"] is False

    def test_lead_sem_ultima_msg_nao_dispara(self):
        lead = _make_lead(ultima_msg="")
        r = avaliar_lead(lead)
        assert r["tratar"] is False

    def test_lead_em_frios_dispara(self):
        # 2.LEADS FRIO também é conversável
        lead = _make_lead(status_id=101508307)
        r = avaliar_lead(lead)
        assert r["tratar"] is True

    def test_silencio_recente_demais_nao_dispara(self):
        lead = _make_lead(minutos_atras=1)
        r = avaliar_lead(lead)
        assert r["tratar"] is False


# ============================================================
# Tratar lead — ação corretiva
# ============================================================

class TestTratarLead:
    def test_dry_run_nao_chama_kommo(self):
        kommo = MagicMock()
        veredicto = {
            "lead_id": 24145890,
            "tratar": True,
            "silencio_seg": 600,
            "silencio_min": 10.0,
            "ultima_msg_outbound": "Vou consultar",
            "status_id_atual": 102560495,
        }
        r = tratar_lead(
            lead=_make_lead(),
            veredicto=veredicto,
            kommo_client=kommo,
            dry_run=True,
        )
        assert r["dry_run"] is True
        assert r["acao"] == "would_move_to_human"
        kommo.update_lead_fields.assert_not_called()
        kommo.add_note.assert_not_called()

    def test_dry_run_off_move_e_anota(self):
        kommo = MagicMock()
        kommo.update_lead_fields.return_value = True
        kommo.add_note.return_value = {"id": 99999}
        veredicto = {
            "lead_id": 24145890,
            "tratar": True,
            "silencio_seg": 600,
            "silencio_min": 10.0,
            "ultima_msg_outbound": "Vou consultar a agenda",
            "status_id_atual": 102560495,
        }
        r = tratar_lead(
            lead=_make_lead(),
            veredicto=veredicto,
            kommo_client=kommo,
            dry_run=False,
        )
        assert r["ok"] is True
        assert r["acao"] == "moved_to_human"
        assert r["moveu_status"] is True
        kommo.update_lead_fields.assert_called_once()
        call_kwargs = kommo.update_lead_fields.call_args.kwargs
        assert call_kwargs.get("status_id") == STATUS_ATENDIMENTO_HUMANO
        assert call_kwargs.get("custom_fields", {}).get("ATIVADO IA?") == "Desativado"
        kommo.add_note.assert_called_once()
        nota_text = kommo.add_note.call_args.kwargs.get("text", "")
        assert "WATCHDOG PROMESSA" in nota_text
        assert "AÇÃO HUMANA NECESSÁRIA" in nota_text

    def test_dedup_skip_quando_recente(self):
        kommo = MagicMock()
        redis = MagicMock()
        redis.exists.return_value = True
        veredicto = {
            "lead_id": 24145890,
            "tratar": True,
            "silencio_min": 10.0,
            "ultima_msg_outbound": "Vou consultar",
            "status_id_atual": 102560495,
        }
        r = tratar_lead(
            lead=_make_lead(),
            veredicto=veredicto,
            kommo_client=kommo,
            redis_client=redis,
            dry_run=False,
        )
        assert r.get("ja_dedup") is True
        kommo.update_lead_fields.assert_not_called()


# ============================================================
# Tick — integração de varredura
# ============================================================

class TestTick:
    def test_tick_dry_run_marca_candidatos(self):
        kommo = MagicMock()
        # 1 lead em 3-AGENDAR com promessa pendente
        # 1 lead em 3-AGENDAR sem promessa
        # 1 lead em 5-AGENDADO (não deve nem ser varrido por estar fora)
        kommo.list_leads_by_status.side_effect = lambda **kw: (
            [_make_lead()] if kw["status_id"] == 102560495 else []
        )
        res = tick(kommo_client=kommo, dry_run=True)
        assert res.varridos >= 1
        assert res.candidatos == 1
        # dry_run conta como "tratado" (ok=True) mesmo sem chamar Kommo
        assert res.tratados == 1
        kommo.update_lead_fields.assert_not_called()

    def test_tick_kommo_erro_em_um_status_nao_quebra(self):
        kommo = MagicMock()

        def list_with_error(**kw):
            if kw["status_id"] == 102560495:
                raise RuntimeError("kommo offline")
            return []

        kommo.list_leads_by_status.side_effect = list_with_error
        res = tick(kommo_client=kommo, dry_run=True)
        assert res.erros >= 1
        # Não levantou exceção — continuou


# ============================================================
# Statuses conversáveis — sanity check
# ============================================================

class TestStatusList:
    def test_status_conversaveis_nao_inclui_humano(self):
        # 1-ATENDIMENTO HUMANO (106563343) NÃO deve estar na lista
        assert 106563343 not in STATUS_CONVERSAVEIS_LIA

    def test_status_conversaveis_nao_inclui_fechados(self):
        # 8-REALIZADO, Closed-won, Closed-lost NÃO devem estar
        assert 91486864 not in STATUS_CONVERSAVEIS_LIA
        assert 142 not in STATUS_CONVERSAVEIS_LIA
        assert 143 not in STATUS_CONVERSAVEIS_LIA

    def test_status_conversaveis_inclui_agendar_e_reagendar(self):
        assert 102560495 in STATUS_CONVERSAVEIS_LIA  # 3-AGENDAR
        assert 106184631 in STATUS_CONVERSAVEIS_LIA  # 4.REAGENDAR


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
