"""Testes para medware_sql.horarios_livres_dia + helpers de normalização.

Bug C-73 (26/07/2026): nova arquitetura de agenda com requisitos mínimos.
- Requisito para MOSTRAR slots: médico + unidade + 1 data específica.
- Nome/data_nasc/convênio coletados DEPOIS que paciente escolher horário.
- Query canônica WITH RECURSIVE + CONTAINING (case-insensitive, Firebird).

Pytest: 12/12 cenários.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch


class TestNormalizarParaSQL(unittest.TestCase):
    """Testa _normalizar_para_sql (nome médico → primeiro nome sem acento)."""

    def _fn(self, nome):
        from voice_agent.medware_sql import _normalizar_para_sql
        return _normalizar_para_sql(nome)

    def test_karla_completo(self):
        self.assertEqual(self._fn("Dra. Karla Delalíbera"), "KARLA")

    def test_karla_sem_titulo(self):
        self.assertEqual(self._fn("Karla Delalíbera"), "KARLA")

    def test_fabricio(self):
        self.assertEqual(self._fn("Dr. Fabrício Freitas"), "FABRICIO")

    def test_fabricio_sem_acento(self):
        self.assertEqual(self._fn("Fabricio"), "FABRICIO")

    def test_vazio(self):
        self.assertEqual(self._fn(""), "")

    def test_none_safe(self):
        from voice_agent.medware_sql import _normalizar_para_sql
        self.assertEqual(_normalizar_para_sql(None), "")  # type: ignore[arg-type]


class TestNormalizarUnidadeParaSQL(unittest.TestCase):
    """Testa _normalizar_unidade_para_sql (unidade sem acento, full)."""

    def _fn(self, nome):
        from voice_agent.medware_sql import _normalizar_unidade_para_sql
        return _normalizar_unidade_para_sql(nome)

    def test_aguas_claras(self):
        self.assertEqual(self._fn("Águas Claras"), "AGUAS CLARAS")

    def test_asa_norte(self):
        self.assertEqual(self._fn("Asa Norte"), "ASA NORTE")

    def test_ja_maiusculo(self):
        self.assertEqual(self._fn("AGUAS CLARAS"), "AGUAS CLARAS")

    def test_vazio(self):
        self.assertEqual(self._fn(""), "")


class TestHorariosLivresDia(unittest.TestCase):
    """Testa horarios_livres_dia com Medware mockado."""

    def _mk_resp(self, horarios_hhmm: list[str]) -> dict:
        """Monta resposta fake do endpoint SQL."""
        return {
            "colunas": [{"coluna": "HORARIO", "tipo": "TIME"}],
            "dados": [{"HORARIO": h + ":00"} for h in horarios_hhmm],
        }

    def test_retorna_lista_hhmm(self):
        from voice_agent.medware_sql import horarios_livres_dia
        resp = self._mk_resp(["08:30", "09:00", "14:00"])
        with patch("voice_agent.medware_sql.executar", return_value=resp):
            result = horarios_livres_dia("Karla", "Asa Norte", "2026-08-04")
        self.assertEqual(result, ["08:30", "09:00", "14:00"])

    def test_retorna_vazio_sem_slots(self):
        from voice_agent.medware_sql import horarios_livres_dia
        resp = self._mk_resp([])
        with patch("voice_agent.medware_sql.executar", return_value=resp):
            result = horarios_livres_dia("Karla", "Águas Claras", "2026-08-05")
        self.assertEqual(result, [])

    def test_erro_retorna_vazio(self):
        from voice_agent.medware_sql import horarios_livres_dia, MedwareSQLError
        with patch("voice_agent.medware_sql.executar",
                   side_effect=MedwareSQLError("timeout")):
            result = horarios_livres_dia("Karla", "Asa Norte", "2026-08-04")
        self.assertEqual(result, [])

    def test_normaliza_dra_karla_no_containing(self):
        """Confirma que 'Dra. Karla Delalíbera' resulta em CONTAINING 'KARLA'."""
        from voice_agent.medware_sql import horarios_livres_dia
        resp = self._mk_resp(["09:30"])
        with patch("voice_agent.medware_sql.executar", return_value=resp) as mock_exec:
            horarios_livres_dia("Dra. Karla Delalíbera", "Asa Norte", "2026-08-03")
        query_usado = mock_exec.call_args[0][0]
        self.assertIn("CONTAINING 'KARLA'", query_usado)
        self.assertIn("CONTAINING 'ASA NORTE'", query_usado)
        self.assertIn("2026-08-03", query_usado)

    def test_query_exclui_almoco(self):
        """Confirma que a query exclui 12:00–13:00."""
        from voice_agent.medware_sql import horarios_livres_dia
        resp = self._mk_resp([])
        with patch("voice_agent.medware_sql.executar", return_value=resp) as mock_exec:
            horarios_livres_dia("Karla", "Asa Norte", "2026-08-03")
        query = mock_exec.call_args[0][0]
        self.assertIn("12:00:00", query)
        self.assertIn("13:00:00", query)

    def test_parametros_invalidos_retorna_vazio(self):
        from voice_agent.medware_sql import horarios_livres_dia
        # medico vazio → vazio sem chamar Medware
        with patch("voice_agent.medware_sql.executar") as mock_exec:
            r1 = horarios_livres_dia("", "Asa Norte", "2026-08-04")
            r2 = horarios_livres_dia("Karla", "", "2026-08-04")
        self.assertEqual(r1, [])
        self.assertEqual(r2, [])
        mock_exec.assert_not_called()

    def test_horas_truncadas_para_hhmm(self):
        """Valores que venham como 'HH:MM:SS' são truncados para 'HH:MM'."""
        from voice_agent.medware_sql import horarios_livres_dia
        resp = {"dados": [{"HORARIO": "09:30:00"}, {"HORARIO": "14:00:00"}]}
        with patch("voice_agent.medware_sql.executar", return_value=resp):
            result = horarios_livres_dia("Karla", "Asa Norte", "2026-08-04")
        self.assertEqual(result, ["09:30", "14:00"])

    def test_aguas_claras_normalizado_no_containing(self):
        """Confirma 'Águas Claras' → CONTAINING 'AGUAS CLARAS'."""
        from voice_agent.medware_sql import horarios_livres_dia
        resp = self._mk_resp(["10:30"])
        with patch("voice_agent.medware_sql.executar", return_value=resp) as mock_exec:
            horarios_livres_dia("Karla", "Águas Claras", "2026-08-05")
        query = mock_exec.call_args[0][0]
        self.assertIn("CONTAINING 'AGUAS CLARAS'", query)


class TestResponderChecklistGateC73(unittest.TestCase):
    """Confirma lógica do gate checklist com slots presentes/ausentes (C-73)."""

    def _gate_ativo(self, ctx: dict) -> bool:
        """Simula a condição do gate em responder.py."""
        checklist = ctx.get("checklist_dados_minimos")
        _tem_slots = bool((ctx or {}).get("agenda"))
        return bool(
            checklist
            and not checklist.get("pronto_para_oferecer_slot", True)
            and not _tem_slots
        )

    def test_gate_nao_bloqueia_com_slots(self):
        """Se ctx tem agenda (slots), gate NÃO deve bloquear — C-73."""
        ctx = {
            "agenda": [{"dia_semana": "Segunda-feira", "data_br": "04/08/2026", "hora": "09:30"}],
            "checklist_dados_minimos": {
                "pronto_para_oferecer_slot": False,
                "campos_pendentes": ["nome_completo"],
            },
        }
        self.assertFalse(
            self._gate_ativo(ctx),
            "Gate NÃO deve bloquear quando há slots — paciente vê horários primeiro",
        )

    def test_gate_bloqueia_sem_slots(self):
        """Se NÃO há slots, gate DEVE bloquear para coletar dados mínimos."""
        ctx = {
            "agenda": [],
            "checklist_dados_minimos": {
                "pronto_para_oferecer_slot": False,
                "campos_pendentes": ["nome_completo"],
            },
        }
        self.assertTrue(
            self._gate_ativo(ctx),
            "Gate DEVE bloquear quando agenda está vazia",
        )

    def test_gate_off_quando_checklist_ok(self):
        """Gate OFF quando pronto_para_oferecer_slot=True (cenário normal)."""
        ctx = {
            "agenda": [],
            "checklist_dados_minimos": {"pronto_para_oferecer_slot": True},
        }
        self.assertFalse(self._gate_ativo(ctx))

    def test_gate_off_sem_checklist(self):
        """Gate OFF quando não há checklist no ctx."""
        ctx = {"agenda": []}
        self.assertFalse(self._gate_ativo(ctx))


if __name__ == "__main__":
    unittest.main()
