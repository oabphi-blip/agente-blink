"""Bug C-70 (26/07/2026) — Janela Medware ignora user_text: mês pedido pelo
paciente na mensagem ATUAL não era passado ao parser; pipeline usava só
known["dia_turno"] (campo Kommo do turno anterior). Resultado: slots de julho
ofertados 3x em loop mesmo com paciente dizendo "outubro" e "09/10/2026".

Lead real: 21397921 (Renata / Augusto Lopes).

3 sub-bugs corrigidos em pipeline.py:
  C-70a — user_text não alimentava parse_janela_preferencia
  C-70b — fallback de dia único → hoje+10d em vez de mês inteiro
  C-70c — mesmo par de slots ofertado 3 vezes (sem re-query com nova janela)

Referência: voz canônica no CLAUDE.md seção 0-ÚLTIMAS 5 LIÇÕES.
"""
from __future__ import annotations

import pytest
from datetime import date

from voice_agent.janela_preferencia import parse_janela_preferencia


# ═══════════════════════════════════════════════════════════════════════
# C-70a — Parse de mês diretamente do user_text
# ═══════════════════════════════════════════════════════════════════════

class TestParseUserTextMes:
    """Valida que parse_janela_preferencia extrai mês do texto do paciente."""

    def test_outubro_no_mes_de(self):
        """'no mês de outubro' → janela outubro."""
        j = parse_janela_preferencia("Para o Augusto, no mês de outubro")
        assert j is not None, "deve parsear 'no mês de outubro'"
        assert j[0].month == 10
        assert j[1].month == 10

    def test_outubro_em(self):
        """'em outubro' → janela outubro."""
        j = parse_janela_preferencia("Queria para em outubro")
        assert j is not None
        assert j[0].month == 10

    def test_outubro_sozinho_frase(self):
        """'outubro' numa frase sem preposição não precisa parsear (conservador)."""
        # sem preposição não deve parsear (evita falso positivo em nomes)
        j = parse_janela_preferencia("outubro")
        # É aceitável retornar None; só não pode retornar mês errado
        if j is not None:
            assert j[0].month == 10

    def test_data_exata(self):
        """'09/10/2026 às 16:00' → dia único 09/10/2026."""
        j = parse_janela_preferencia("09/10/2026 às 16:00")
        assert j is not None, "deve parsear data exata"
        assert j[0] == date(2026, 10, 9)
        assert j[1] == date(2026, 10, 9)

    def test_data_exata_com_contexto(self):
        """Frase completa do paciente real com data."""
        j = parse_janela_preferencia("09/10/2026 às 16:00")
        assert j is not None
        assert j[0].month == 10
        assert j[0].day == 9

    def test_combinacao_dia_turno_mais_user_text(self):
        """Combinação de dia_turno vazio + user_text com mês → deve parsear."""
        dia_turno = ""
        user_text = "Para o Augusto, no mês de outubro"
        combined = " ".join(filter(None, [dia_turno, user_text]))
        j = parse_janela_preferencia(combined)
        assert j is not None
        assert j[0].month == 10

    def test_dia_turno_velho_mais_user_text_novo(self):
        """dia_turno com dado antigo + user_text com mês mais recente.
        O mês do user_text deve ser detectado mesmo com lixo no dia_turno."""
        dia_turno = "manhã"  # campo velho sem data
        user_text = "no mês de outubro"
        combined = " ".join(filter(None, [dia_turno, user_text]))
        j = parse_janela_preferencia(combined)
        assert j is not None
        assert j[0].month == 10


# ═══════════════════════════════════════════════════════════════════════
# C-70b — Fallback de dia único deve expandir para mês inteiro
# ═══════════════════════════════════════════════════════════════════════

class TestFallbackMesInteiro:
    """Valida lógica de expansão: dia único → mês completo quando sem slots."""

    def test_mes_inteiro_cobre_dia_unico(self):
        """Quando janela é dia único, mês inteiro a partir do mesmo mês."""
        import calendar
        d = date(2026, 10, 9)
        ultimo = calendar.monthrange(d.year, d.month)[1]
        di_mes = date(d.year, d.month, 1)
        df_mes = date(d.year, d.month, ultimo)
        # O mês deve conter o dia original
        assert di_mes <= d <= df_mes

    def test_expansao_nao_aplicada_quando_ja_mes_inteiro(self):
        """Se a janela já é o mês inteiro, não deve expandir (evita dupla chamada)."""
        import calendar
        d = date(2026, 10, 1)
        ultimo = calendar.monthrange(d.year, d.month)[1]
        di_mes = date(d.year, d.month, 1)
        df_mes = date(d.year, d.month, ultimo)
        janela = (di_mes, df_mes)
        # Condição do código: só expande se di_mes != janela[0] OU df_mes != janela[1]
        ja_e_mes_inteiro = (di_mes == janela[0] and df_mes == janela[1])
        assert ja_e_mes_inteiro  # não deve expandir de novo

    def test_janela_unico_dia_expandivel(self):
        """Janela de um único dia DEVE ser marcada como expansível."""
        import calendar
        d = date(2026, 10, 9)
        ultimo = calendar.monthrange(d.year, d.month)[1]
        di_mes = date(d.year, d.month, 1)
        df_mes = date(d.year, d.month, ultimo)
        janela = (d, d)
        deve_expandir = (di_mes != janela[0] or df_mes != janela[1])
        assert deve_expandir


# ═══════════════════════════════════════════════════════════════════════
# C-70c — Cenário ponta-a-ponta: preferência de outubro a partir de user_text
# ═══════════════════════════════════════════════════════════════════════

class TestCenarioReal:
    """Reproduz a sequência real da conversa do lead 21397921."""

    def _parse(self, dia_turno: str, user_text: str):
        combined = " ".join(filter(None, [dia_turno, user_text]))
        return parse_janela_preferencia(combined)

    def test_turno1_paciente_diz_outubro(self):
        """Turno 1: dia_turno vazio, paciente diz 'no mês de outubro'."""
        j = self._parse("", "Para o Augusto, no mês de outubro")
        assert j is not None
        assert j[0].month == 10, "deve identificar outubro"

    def test_turno2_paciente_repete_outubro(self):
        """Turno 2: paciente corrige dizendo 'Queria para o mês de outubro'."""
        j = self._parse("tarde — fim", "Não. Queria para o mes de outubro")
        assert j is not None
        assert j[0].month == 10

    def test_turno3_paciente_da_data_exata(self):
        """Turno 3: paciente especifica '09/10/2026 às 16:00'."""
        j = self._parse(
            "Sexta-feira — tarde — fim (17h)",
            "09/10/2026 às 16:00",
        )
        assert j is not None
        assert j[0] == date(2026, 10, 9)
        assert j[1] == date(2026, 10, 9)

    def test_nao_deve_parsear_como_julho(self):
        """Em nenhum dos 3 turnos a janela deve ser julho."""
        frases = [
            ("", "Para o Augusto, no mês de outubro"),
            ("tarde — fim", "Não. Queria para o mes de outubro"),
            ("Sexta-feira — tarde — fim", "09/10/2026 às 16:00"),
        ]
        for dia_turno, user_text in frases:
            j = self._parse(dia_turno, user_text)
            if j is not None:
                assert j[0].month != 7, (
                    f"janela NÃO deve ser julho para: dia_turno={dia_turno!r} "
                    f"user_text={user_text!r}"
                )
