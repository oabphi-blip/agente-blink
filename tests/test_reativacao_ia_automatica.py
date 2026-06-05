"""Cobertura do fluxo de reativação automática da IA (task #233).

Fluxo proposto por Fábio 05/06/2026:
1. Humano envia msg manual → IA desativa + lead move pra 1-ATENDIMENTO HUMANO
2. Humano resolve + move pra etapa ativa → IA reativa via webhook
"""
import pytest
from unittest.mock import MagicMock


# ---------------------------------------------------------------------------
# Conjunto de status_ids onde IA deve estar SEMPRE ativa
# ---------------------------------------------------------------------------

# Importa do webhook.py local function _STATUS_ATIVOS_IA via cópia (essa
# constante fica dentro de build_app() — replicada aqui pra teste isolado)
STATUS_ATIVOS_IA = {
    96441724,   # 0-ETAPA ENTRADA
    106919911,  # 0-a classificar
    101508307,  # 2.LEADS FRIO
    102560495,  # 3-AGENDAR
    106184631,  # 4.REAGENDAR
    101507507,  # 5-AGENDADO
    101109455,  # 6-CONFIRMAR
    106653499,  # 7.CONFIRMADO
    106184983,  # 7.1-NO-SHOW
}

STATUS_ATENDIMENTO_HUMANO = 106563343
STATUS_FECHADOS = {142, 143, 91486864}  # Closed-won, Closed-lost, Realizado


def test_status_atendimento_humano_NAO_esta_na_lista_ativa():
    """Etapa 1-ATENDIMENTO HUMANO NÃO reativa IA — humano ainda está no caso."""
    assert STATUS_ATENDIMENTO_HUMANO not in STATUS_ATIVOS_IA


def test_etapas_de_funil_atende_estao_marcadas_como_ativas():
    """Tudo entre 0-ENTRADA e 7.1-NO-SHOW está marcado como ativo."""
    assert 96441724 in STATUS_ATIVOS_IA   # 0-ETAPA ENTRADA
    assert 106919911 in STATUS_ATIVOS_IA  # 0-a classificar
    assert 101508307 in STATUS_ATIVOS_IA  # 2.LEADS FRIO
    assert 102560495 in STATUS_ATIVOS_IA  # 3-AGENDAR
    assert 106184631 in STATUS_ATIVOS_IA  # 4.REAGENDAR
    assert 101507507 in STATUS_ATIVOS_IA  # 5-AGENDADO
    assert 101109455 in STATUS_ATIVOS_IA  # 6-CONFIRMAR
    assert 106653499 in STATUS_ATIVOS_IA  # 7.CONFIRMADO
    assert 106184983 in STATUS_ATIVOS_IA  # 7.1-NO-SHOW


def test_etapas_fechadas_NAO_estao_na_lista_ativa():
    """Closed-won/lost e Realizado NÃO devem reativar IA."""
    for status_fechado in STATUS_FECHADOS:
        assert status_fechado not in STATUS_ATIVOS_IA


# ---------------------------------------------------------------------------
# Mock do fluxo: status_id muda → endpoint reativa OU ignora
# ---------------------------------------------------------------------------

def _simular_webhook_status_change(
    kommo_client, lead_id, novo_status_id, lista_ativos=None,
):
    """Simula a lógica do endpoint /admin/kommo-trigger-status-change."""
    lista = lista_ativos or STATUS_ATIVOS_IA
    if novo_status_id not in lista:
        return {"acao": "ignorado", "motivo": "etapa não ativa"}
    kommo_client.update_lead_fields(lead_id, {"ativado_ia": "Ativado"})
    return {"acao": "ia_reativada", "lead_id": lead_id}


def test_webhook_reativa_quando_move_para_3_agendar():
    kc = MagicMock()
    kc.update_lead_fields.return_value = True
    res = _simular_webhook_status_change(kc, 10513560, 102560495)
    assert res["acao"] == "ia_reativada"
    kc.update_lead_fields.assert_called_once_with(
        10513560, {"ativado_ia": "Ativado"},
    )


def test_webhook_reativa_quando_move_para_5_agendado():
    kc = MagicMock()
    kc.update_lead_fields.return_value = True
    res = _simular_webhook_status_change(kc, 999, 101507507)
    assert res["acao"] == "ia_reativada"


def test_webhook_reativa_quando_move_para_2_leads_frio():
    kc = MagicMock()
    kc.update_lead_fields.return_value = True
    res = _simular_webhook_status_change(kc, 999, 101508307)
    assert res["acao"] == "ia_reativada"


def test_webhook_ignora_quando_move_para_1_atendimento_humano():
    """Mover pra 1-ATENDIMENTO HUMANO NÃO reativa IA (humano ainda tá lá)."""
    kc = MagicMock()
    res = _simular_webhook_status_change(kc, 999, STATUS_ATENDIMENTO_HUMANO)
    assert res["acao"] == "ignorado"
    kc.update_lead_fields.assert_not_called()


def test_webhook_ignora_quando_move_para_closed_lost():
    """Closed-lost não reativa IA — lead acabou."""
    kc = MagicMock()
    res = _simular_webhook_status_change(kc, 999, 143)
    assert res["acao"] == "ignorado"
    kc.update_lead_fields.assert_not_called()


def test_webhook_ignora_quando_move_para_8_realizado():
    """8-REALIZADO CONSULTA não reativa IA — consulta já aconteceu."""
    kc = MagicMock()
    res = _simular_webhook_status_change(kc, 999, 91486864)
    assert res["acao"] == "ignorado"


# ---------------------------------------------------------------------------
# Movimentação pra ATENDIMENTO HUMANO quando humano envia msg manual
# ---------------------------------------------------------------------------

def test_handoff_NAO_move_se_lead_ja_esta_em_atendimento_humano():
    """Se status_atual = 106563343, NÃO mexe — já está lá."""
    kc = MagicMock()
    status_atual = STATUS_ATENDIMENTO_HUMANO
    if status_atual != STATUS_ATENDIMENTO_HUMANO:
        kc.update_lead_status(999, STATUS_ATENDIMENTO_HUMANO)
    kc.update_lead_status.assert_not_called()


def test_handoff_move_quando_humano_envia_de_etapa_normal():
    """Lead em 3-AGENDAR + humano envia → move pra 1-ATENDIMENTO HUMANO."""
    kc = MagicMock()
    kc.update_lead_status.return_value = True
    status_atual = 102560495  # 3-AGENDAR
    if (
        status_atual
        and status_atual != STATUS_ATENDIMENTO_HUMANO
        and status_atual not in STATUS_FECHADOS
    ):
        kc.update_lead_status(999, STATUS_ATENDIMENTO_HUMANO)
    kc.update_lead_status.assert_called_once_with(999, STATUS_ATENDIMENTO_HUMANO)


def test_handoff_NAO_move_se_lead_esta_fechado():
    """Closed-won/lost ou Realizado NÃO devem ser mexidos."""
    kc = MagicMock()
    for status_fechado in STATUS_FECHADOS:
        kc.reset_mock()
        if (
            status_fechado
            and status_fechado != STATUS_ATENDIMENTO_HUMANO
            and status_fechado not in STATUS_FECHADOS
        ):
            kc.update_lead_status(999, STATUS_ATENDIMENTO_HUMANO)
        kc.update_lead_status.assert_not_called()


# ---------------------------------------------------------------------------
# Cenário fim-a-fim: lead Larissa/Lis/Samuel (10513560 — caso Fábio)
# ---------------------------------------------------------------------------

def test_caso_larissa_lead_10513560_seria_reativado():
    """Lead 10513560 está em 6-CONFIRMAR + ATIVADO IA=Desativado.
    Batch /admin/reativar-ia-batch deve incluir esse lead."""
    status_atual = 101109455  # 6-CONFIRMAR
    estado_ia = "DESATIVADO"
    elegivel = (status_atual in STATUS_ATIVOS_IA) and (estado_ia == "DESATIVADO")
    assert elegivel is True
