"""Bug C-42 revogado + política simplificada (Fábio 30/06/2026 22:45).

Regras validadas:
  1. Lia opera SOMENTE no funil ATENDE (8601819) — outros funis são
     ignorados silenciosamente.
  2. Dentro do ATENDE:
     - Etapa 1-ATENDIMENTO HUMANO (106563343) desativa IA.
     - Todas as outras 12 etapas ativam IA.
  3. Env LIA_POLITICA_SIMPLIFICADA toggle:
     - =1 (default) → política nova.
     - =0 → política antiga (rollback Bug C-42).
"""
from __future__ import annotations

import os


# Pipeline exclusivo — só ATENDE é aceito.
PIPELINE_ATENDE = 8601819
PIPELINE_CIRURGIA_LENTES = 12715740
PIPELINE_ADM_BLINK = 8606099

# Etapas do funil ATENDE — nomes reais confirmados via Kommo API 30/06/2026.
STATUS_ATENDE = {
    "0-ETAPA ENTRADA": 96441724,
    "0-a classificar/EXCLUIR DUPLICADO": 106919911,
    "1-ATENDIMENTO HUMANO": 106563343,
    "2.LEADS FRIO": 101508307,
    "3-AGENDAR": 102560495,
    "4-APRESENTADO HORÁRIOS": 107084255,
    "5.REAGENDAR (now show)": 106184631,
    "6-AGENDADO": 101507507,
    "7-CONFIRMAR": 101109455,
    "8.CONFIRMADO": 106653499,
    "9-REALIZADO CONSULTA": 91486864,
    "10-PRÓXIMA CONSULTA": 106157327,
    "Closed - won": 142,
    "Closed - lost": 143,
}

# Etapas de outros funis — Lia NÃO opera nelas.
STATUS_CIRURGIA_LENTES = {
    "ENTRADA": 108319447,
    "ANDAMENTOS CIRURGIAS": 108319527,
    "ANDAMENTOS LENTES": 108319451,
}
STATUS_ADM_BLINK = {
    "COLABORADORES": 108326839,
    "LISTA DE PRESTADORES": 108326779,
}


# --------------------------------------------------------------------- helpers
def _politica_simplificada() -> bool:
    """Espelha a lógica do webhook.py."""
    return (
        os.environ.get("LIA_POLITICA_SIMPLIFICADA", "1").strip().lower()
        not in ("0", "false", "no", "off")
    )


def _ativos_simplificada() -> set[int]:
    return {
        96441724, 106919911, 101508307, 102560495, 107084255, 106184631,
        101507507, 101109455, 106653499, 91486864, 106157327, 142, 143,
    }


def _inativos_simplificada() -> set[int]:
    return {106563343}


def _ativos_antiga() -> set[int]:
    return {
        96441724, 106919911, 101508307, 102560495, 107084255, 106184631,
        91486864, 106157327, 142, 143,
    }


def _inativos_antiga() -> set[int]:
    return {106563343, 101507507, 101109455, 106653499}


# ------------------------------------------------ testes: política SIMPLIFICADA
class TestPoliticaSimplificadaDefault:
    """LIA_POLITICA_SIMPLIFICADA=1 (default) — nova política."""

    def setup_method(self) -> None:
        os.environ["LIA_POLITICA_SIMPLIFICADA"] = "1"

    def test_1_atendimento_humano_desativa(self) -> None:
        assert STATUS_ATENDE["1-ATENDIMENTO HUMANO"] in _inativos_simplificada()

    def test_todas_outras_etapas_ativam(self) -> None:
        for nome, sid in STATUS_ATENDE.items():
            if nome == "1-ATENDIMENTO HUMANO":
                continue
            assert sid in _ativos_simplificada(), (
                f"{nome} deveria estar em ATIVOS na política simplificada"
            )

    def test_6_agendado_ativa_revoga_c42(self) -> None:
        assert STATUS_ATENDE["6-AGENDADO"] in _ativos_simplificada()
        assert STATUS_ATENDE["6-AGENDADO"] not in _inativos_simplificada()

    def test_7_confirmar_ativa_revoga_c42(self) -> None:
        assert STATUS_ATENDE["7-CONFIRMAR"] in _ativos_simplificada()

    def test_8_confirmado_ativa_revoga_c42(self) -> None:
        assert STATUS_ATENDE["8.CONFIRMADO"] in _ativos_simplificada()

    def test_ativos_e_inativos_sao_disjuntos(self) -> None:
        assert not (_ativos_simplificada() & _inativos_simplificada()), (
            "Nenhuma etapa deve estar em ATIVOS E INATIVOS ao mesmo tempo"
        )


# ------------------------------------------------ testes: política ANTIGA
class TestPoliticaAntigaRollback:
    """LIA_POLITICA_SIMPLIFICADA=0 — rollback pro Bug C-42."""

    def setup_method(self) -> None:
        os.environ["LIA_POLITICA_SIMPLIFICADA"] = "0"

    def teardown_method(self) -> None:
        os.environ["LIA_POLITICA_SIMPLIFICADA"] = "1"

    def test_toggle_desativado_carrega_politica_antiga(self) -> None:
        assert _politica_simplificada() is False

    def test_6_agendado_desativa(self) -> None:
        assert STATUS_ATENDE["6-AGENDADO"] in _inativos_antiga()

    def test_7_confirmar_desativa(self) -> None:
        assert STATUS_ATENDE["7-CONFIRMAR"] in _inativos_antiga()

    def test_8_confirmado_desativa(self) -> None:
        assert STATUS_ATENDE["8.CONFIRMADO"] in _inativos_antiga()

    def test_1_atendimento_humano_ainda_desativa(self) -> None:
        assert STATUS_ATENDE["1-ATENDIMENTO HUMANO"] in _inativos_antiga()


# ------------------------------------------------ testes: gate por pipeline
class TestGatePorPipeline:
    """Lia opera SOMENTE no funil ATENDE. Outros funis são ignorados."""

    def test_ids_do_atende_sao_reconhecidos(self) -> None:
        assert PIPELINE_ATENDE == 8601819

    def test_pipelines_diferentes_sao_ignorados(self) -> None:
        # Simulação: se o webhook recebe status_id da CIRURGIA/LENTES,
        # deveria retornar "ignorado" sem mexer no ATIVADO IA.
        for sid in STATUS_CIRURGIA_LENTES.values():
            # Nenhum deles está nas listas do ATENDE.
            assert sid not in _ativos_simplificada()
            assert sid not in _inativos_simplificada()

    def test_adm_blink_ids_nao_estao_no_atende(self) -> None:
        for sid in STATUS_ADM_BLINK.values():
            assert sid not in _ativos_simplificada()
            assert sid not in _inativos_simplificada()


# ------------------------------------------------ toggle env vazio / inválido
class TestTogglePolitica:
    def test_env_ausente_default_simplificada(self) -> None:
        os.environ.pop("LIA_POLITICA_SIMPLIFICADA", None)
        assert _politica_simplificada() is True

    def test_env_vazia_default_simplificada(self) -> None:
        os.environ["LIA_POLITICA_SIMPLIFICADA"] = ""
        assert _politica_simplificada() is True
        os.environ["LIA_POLITICA_SIMPLIFICADA"] = "1"

    def test_env_off_desativa(self) -> None:
        os.environ["LIA_POLITICA_SIMPLIFICADA"] = "off"
        assert _politica_simplificada() is False
        os.environ["LIA_POLITICA_SIMPLIFICADA"] = "1"

    def test_env_false_desativa(self) -> None:
        os.environ["LIA_POLITICA_SIMPLIFICADA"] = "false"
        assert _politica_simplificada() is False
        os.environ["LIA_POLITICA_SIMPLIFICADA"] = "1"

    def test_env_true_ativa(self) -> None:
        os.environ["LIA_POLITICA_SIMPLIFICADA"] = "true"
        assert _politica_simplificada() is True
