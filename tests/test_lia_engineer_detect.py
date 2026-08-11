"""Pytest do detector de bugs do Lia Engineer.

Valida com casos REAIS observados (lead 24125064 Tatiana, lead 24117314
Maria Agostini, lead 24053159 Juliene). Cada caso real vira teste.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from lia_engineer.detect_bugs import (
    BugReport,
    detectar_bugs_em_lead,
    detectar_padroes_em_texto,
    detectar_padroes_sliding_window,
)


_REF_TATIANA = datetime(2026, 6, 9, 20, 27, tzinfo=timezone.utc)


# ────────────────────────────────────────────────────────────────────────
# Cenário Tatiana lead 24125064 (09/06/2026)
# ────────────────────────────────────────────────────────────────────────

class TestTatiana:
    def test_detecta_vou_consultar_e_nao_volta(self):
        """Nota #14 (20:26:36): 'Deixa eu reconsultar a agenda da Dra. Karla'"""
        bugs = detectar_padroes_em_texto(
            "Perfeito! Deixa eu reconsultar a agenda da Dra. Karla para "
            "Asa Norte e já volto com os horários — me dá só um momento.",
            lead_id=24125064,
            timestamp=_REF_TATIANA,
        )
        assert any(b.padrao_id == "vou_consultar_e_nao_volta" for b in bugs)

    def test_detecta_data_dia_inconsistente_quarta_11_06(self):
        """Nota #15: 'quarta-feira, 11/06' mas 11/06/2026 é QUINTA."""
        bugs = detectar_padroes_em_texto(
            "Tatiana, para a Laura com a Dra. Karla na Asa Norte à tarde, "
            "tenho estes horários:\n\n1️⃣ quarta-feira, 11/06 às 14:00\n"
            "2️⃣ sexta-feira, 13/06 às 15:30",
            lead_id=24125064,
            timestamp=_REF_TATIANA,
            ja_dia_da_semana_hoje=_REF_TATIANA,
        )
        assert any(b.padrao_id == "data_dia_semana_inconsistente" for b in bugs), (
            "Bug 11/06 quarta deveria ser detectado (na verdade quarta=10/06)"
        )

    def test_aceita_data_correta_quarta_10_06(self):
        """Versão corrigida: quarta-feira, 10/06/2026 BATE (weekday=2=quarta)"""
        bugs = detectar_padroes_em_texto(
            "Os horários disponíveis são quarta-feira, 10/06 às 14:00 e "
            "sexta-feira, 12/06 às 15:30. Qual prefere?",
            lead_id=24125064,
            timestamp=_REF_TATIANA,
            ja_dia_da_semana_hoje=_REF_TATIANA,
        )
        # Não deve ter bug data_dia_inconsistente
        assert not any(b.padrao_id == "data_dia_semana_inconsistente" for b in bugs)

    def test_detecta_4_perguntas_em_msg(self):
        """Nota #4: 4 dados pedidos numa msg só (bug C-14)"""
        bugs = detectar_padroes_em_texto(
            "Entendi! A consulta é para sua filha de 8 anos com a Dra. Karla. "
            "Para eu registrar certo no sistema, preciso de:\n• Nome completo "
            "da sua filha? • Data de nascimento dela? • O motivo da consulta? "
            "• Tem alguma dúvida específica?",
            lead_id=24125064,
            timestamp=_REF_TATIANA,
        )
        assert any(b.padrao_id == "multiplas_perguntas_em_uma_msg" for b in bugs)

    def test_detecta_race_condition_sliding_window(self):
        """Notas 4 e 5: Lia mandou mesma pergunta com 7s de diferença"""
        n1 = {
            "at": datetime(2026, 6, 9, 20, 21, 18, tzinfo=timezone.utc),
            "txt": "Para eu agendar, preciso de nome completo e nascimento",
            "author": "LIA",
        }
        n2 = {
            "at": datetime(2026, 6, 9, 20, 21, 25, tzinfo=timezone.utc),
            "txt": "Preciso que você me passe nome completo e nascimento da filha",
            "author": "LIA",
        }
        bugs = detectar_padroes_sliding_window([n1, n2], lead_id=24125064)
        race_bugs = [b for b in bugs if b.padrao_id == "mensagem_duplicada_lia_em_janela_curta"]
        assert len(race_bugs) >= 1
        assert race_bugs[0].severidade == "P0"

    def test_detecta_contradicao_urgencia_rotina_em_30s(self):
        """Notas 10, 11, 12: muda classificação 3x em <30s"""
        notas = [
            {"at": datetime(2026, 6, 9, 20, 25, 1, tzinfo=timezone.utc),
             "txt": "Perfeito! Registrado como urgência.", "author": "LIA"},
            {"at": datetime(2026, 6, 9, 20, 25, 8, tzinfo=timezone.utc),
             "txt": "Vou registrar como rotina com sintoma.", "author": "LIA"},
        ]
        bugs = detectar_padroes_sliding_window(notas, lead_id=24125064)
        contra = [b for b in bugs if b.padrao_id == "contradicao_classificacao_motivo"]
        assert len(contra) >= 1, (
            "Contradição urgência↔rotina em <60s deveria ser detectada"
        )


# ────────────────────────────────────────────────────────────────────────
# Cenário Maria Agostini lead 24117314 (08/06/2026) — Bug C-16 INAS
# ────────────────────────────────────────────────────────────────────────

class TestMariaAgostini:
    def test_detecta_atende_inas_gdf(self):
        bugs = detectar_padroes_em_texto(
            "Perfeito!  Atendemos o INAS GDF.\n\nAgora, para eu já solicitar "
            "a autorização do convênio antes do dia da consulta...",
            lead_id=24117314,
            timestamp=datetime(2026, 6, 8, 14, 41, tzinfo=timezone.utc),
        )
        assert any(b.padrao_id == "atende_convenio_nao_aceito" for b in bugs)

    @pytest.mark.parametrize("texto", [
        "Sim, atendemos Bradesco",
        "Cobrimos Cassi",
        "Aceitamos Sul América",
        "Credenciamos Hapvida",
    ])
    def test_detecta_outros_convenios_kb18(self, texto):
        bugs = detectar_padroes_em_texto(
            texto, lead_id=99, timestamp=_REF_TATIANA,
        )
        assert any(b.padrao_id == "atende_convenio_nao_aceito" for b in bugs)

    @pytest.mark.parametrize("texto", [
        "Não atendemos INAS",
        "Infelizmente o Bradesco não cobre",
        "Cassi não está credenciada",
    ])
    def test_nao_dispara_em_negacao(self, texto):
        bugs = detectar_padroes_em_texto(
            texto, lead_id=99, timestamp=_REF_TATIANA,
        )
        assert not any(b.padrao_id == "atende_convenio_nao_aceito" for b in bugs)


# ────────────────────────────────────────────────────────────────────────
# Cenário Juliene lead 24053159 (01/06/2026)
# ────────────────────────────────────────────────────────────────────────

class TestJuliene:
    def test_detecta_horario_comercial_inventado(self):
        bugs = detectar_padroes_em_texto(
            "Vou registrar pra equipe finalizar — você terá retorno em "
            "horário comercial seg-sex 8h-18h",
            lead_id=24053159,
            timestamp=datetime(2026, 6, 1, 18, 0, tzinfo=timezone.utc),
        )
        assert any(b.padrao_id == "horario_comercial_inventado" for b in bugs)
        assert any(b.padrao_id == "promete_retorno_humano_sem_volta" for b in bugs)


# ────────────────────────────────────────────────────────────────────────
# Integração: detectar_bugs_em_lead processa cenário completo
# ────────────────────────────────────────────────────────────────────────

class TestIntegracaoTatianaCompleto:
    def test_processa_lead_24125064_com_todos_padroes(self):
        """Cenário real Tatiana - várias notas Lia em sequência."""
        notas = [
            {"at": datetime(2026, 6, 9, 20, 19, 39, tzinfo=timezone.utc),
             "txt": "Boa tarde, Tatiana! Como posso te ajudar?", "author": "LIA"},
            {"at": datetime(2026, 6, 9, 20, 21, 18, tzinfo=timezone.utc),
             "txt": "Preciso de: Nome? Data? Motivo? Dúvida?", "author": "LIA"},
            {"at": datetime(2026, 6, 9, 20, 21, 25, tzinfo=timezone.utc),
             "txt": "Preciso de nome, data nasc, motivo. Pode me passar?",
             "author": "LIA"},
            {"at": datetime(2026, 6, 9, 20, 26, 36, tzinfo=timezone.utc),
             "txt": "Deixa eu reconsultar a agenda e já volto", "author": "LIA"},
            {"at": datetime(2026, 6, 9, 20, 27, 39, tzinfo=timezone.utc),
             "txt": "Quarta-feira, 11/06 às 14:00 ou sexta, 13/06 às 15:30",
             "author": "LIA"},
        ]
        bugs = detectar_bugs_em_lead(notas, lead_id=24125064)
        padroes_detectados = {b.padrao_id for b in bugs}

        # Padrões que DEVEM ser detectados:
        esperados = {
            "multiplas_perguntas_em_uma_msg",
            "mensagem_duplicada_lia_em_janela_curta",
            "vou_consultar_e_nao_volta",
            "data_dia_semana_inconsistente",
        }
        faltando = esperados - padroes_detectados
        assert not faltando, f"Padrões não detectados: {faltando}"

    def test_lead_sem_bugs_nao_gera_relatorio(self):
        """Cenário ideal: Lia funciona certinho."""
        notas = [
            {"at": datetime(2026, 6, 9, 20, 0, tzinfo=timezone.utc),
             "txt": "Boa tarde, Tatiana! Sou a Lia.", "author": "LIA"},
            {"at": datetime(2026, 6, 9, 20, 1, tzinfo=timezone.utc),
             "txt": "Qual sua preferência: manhã ou tarde?", "author": "LIA"},
        ]
        bugs = detectar_bugs_em_lead(notas, lead_id=99)
        assert len(bugs) == 0


# ────────────────────────────────────────────────────────────────────────
# Dedup
# ────────────────────────────────────────────────────────────────────────

class TestDedup:
    def test_chave_dedup_inclui_hora(self):
        b = BugReport(
            lead_id=24125064,
            timestamp=datetime(2026, 6, 9, 20, 27, tzinfo=timezone.utc),
            padrao_id="vou_consultar_e_nao_volta",
            categoria_raiz="cat1_tool_calling_nao_forcado",
            severidade="P0",
            texto_lia="deixa eu consultar",
        )
        chave = b.chave_dedup()
        assert "24125064" in chave
        assert "20260609" in chave  # ano-mês-dia (formato canônico)
        assert "vou_consultar" in chave
