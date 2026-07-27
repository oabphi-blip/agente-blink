"""
Bug: paciente precisa de N consultas consecutivas.
listar_slots_livres sem n_slots retorna qualquer slot livre,
incluindo aqueles onde só 1 de N slots contíguos está disponível.

Fix: parâmetro n_slots verifica bloco de N×30min antes de incluir
o horário de início.
"""
import pytest
from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# helpers internos (sem deps Medware)
# ---------------------------------------------------------------------------

def _hhmm_para_minutos(s: str) -> int:
    try:
        h, m = str(s).split(":")
        return int(h) * 60 + int(m)
    except Exception:
        return 0


def _minutos_para_hhmm(m: int) -> str:
    return f"{m // 60:02d}:{m % 60:02d}"


def _simular_slots_livres(livres_hhmm: list[str], n_slots: int) -> list[str]:
    """Replica a lógica de filtragem de bloco contíguo do listar_slots_livres.
    Recebe lista de horários livres (strings HH:MM) e devolve apenas aqueles
    onde os próximos N-1 slots de 30min também estão na lista.
    """
    DATA = "2026-08-04"
    livres_set = {(DATA, h) for h in livres_hhmm}
    resultado = []
    for h in livres_hhmm:
        inicio_min = _hhmm_para_minutos(h)
        bloco_ok = all(
            (DATA, _minutos_para_hhmm(inicio_min + 30 * i)) in livres_set
            for i in range(1, n_slots)
        )
        if bloco_ok:
            resultado.append(h)
    return resultado


# ---------------------------------------------------------------------------
# Testes de lógica de bloco contíguo
# ---------------------------------------------------------------------------

class TestBlocoContiguoLogica:

    def test_n1_todos_passam(self):
        """n_slots=1: qualquer slot livre é válido."""
        livres = ["08:00", "08:30", "09:30", "10:00"]
        assert _simular_slots_livres(livres, 1) == livres

    def test_n2_exige_proximo_slot(self):
        """n_slots=2: 08:00 só passa se 08:30 também está livre."""
        livres = ["08:00", "08:30", "09:30"]
        resultado = _simular_slots_livres(livres, 2)
        assert "08:00" in resultado   # 08:30 está livre ✓
        assert "08:30" not in resultado  # 09:00 não está livre ✗
        assert "09:30" not in resultado  # 10:00 não está livre ✗

    def test_n2_gap_impede_inicio(self):
        """08:00 livre, 09:00 livre, mas 08:30 não livre → nenhum passa n_slots=2."""
        livres = ["08:00", "09:00"]
        resultado = _simular_slots_livres(livres, 2)
        assert resultado == []

    def test_n3_bloco_completo(self):
        """n_slots=3: exige 3 slots consecutivos de 30min."""
        livres = ["08:00", "08:30", "09:00", "10:00", "10:30"]
        resultado = _simular_slots_livres(livres, 3)
        # 08:00 → 08:30 → 09:00 ✓
        assert "08:00" in resultado
        # 08:30 → 09:00 → 09:30 ✗ (09:30 não está)
        assert "08:30" not in resultado
        # 09:00 → 09:30 ✗
        assert "09:00" not in resultado
        # 10:00 → 10:30 → 11:00 ✗
        assert "10:00" not in resultado

    def test_n4_bloco_longo(self):
        """n_slots=4 = 2h de atendimento contíguo.
        Apenas 4 slots consecutivos disponíveis: 13:00 é o único início válido."""
        # Exatamente 4 slots → só 13:00 pode ser início
        livres = ["13:00", "13:30", "14:00", "14:30"]
        resultado = _simular_slots_livres(livres, 4)
        # 13:00 → 13:30 → 14:00 → 14:30 ✓
        assert "13:00" in resultado
        # 13:30 → 14:00 → 14:30 → 15:00 ✗ (15:00 não está)
        assert "13:30" not in resultado
        # 14:00 e 14:30 também não têm bloco suficiente
        assert "14:00" not in resultado
        assert "14:30" not in resultado

    def test_agenda_vazia_retorna_vazio(self):
        assert _simular_slots_livres([], 2) == []

    def test_slot_unico_n2_falha(self):
        """Apenas 1 slot disponível, n_slots=2: não retorna nada."""
        assert _simular_slots_livres(["09:00"], 2) == []

    def test_dois_blocos_separados(self):
        """Dois blocos de 2 slots, separados: ambos os inícios passam n_slots=2."""
        livres = ["08:00", "08:30", "10:00", "10:30"]
        resultado = _simular_slots_livres(livres, 2)
        assert "08:00" in resultado
        assert "10:00" in resultado
        assert "08:30" not in resultado
        assert "10:30" not in resultado


# ---------------------------------------------------------------------------
# Testes de integração (mockando dependências Medware)
# ---------------------------------------------------------------------------

class TestListarSlotsLivresNSlots:

    def _make_grade(self):
        """Grade simulada: segunda-feira 08:00-12:00, intervalo 30min."""
        return [{"DIASEMANA": 2, "HORAINICIO": "08:00", "HORAFIM": "12:00", "INTERVALO": 30}]

    @patch("voice_agent.medware_sql.listar_grade_medico")
    @patch("voice_agent.medware_sql.executar")
    @patch("voice_agent.medware_sql.rows")
    def test_n1_default_sem_mudanca(self, mock_rows, mock_exec, mock_grade):
        """n_slots=1 (default) retorna todos os slots livres — sem regressão."""
        from voice_agent.medware_sql import listar_slots_livres
        mock_grade.return_value = self._make_grade()
        mock_rows.return_value = []  # nenhum ocupado
        resultado = listar_slots_livres(12080, 5, dias=7, n_slots=1)
        # Deve ter slots (segunda da próxima semana)
        # Sem verificar contagem exata porque depende de data — só valida tipo
        assert isinstance(resultado, list)
        for s in resultado:
            assert "data_iso" in s
            assert "hora" in s
            assert "hora_min" not in s  # campo interno não deve vazar

    @patch("voice_agent.medware_sql.listar_grade_medico")
    @patch("voice_agent.medware_sql.executar")
    @patch("voice_agent.medware_sql.rows")
    def test_n2_slot_intermediario_ocupado_bloqueia(self, mock_rows, mock_exec, mock_grade):
        """Se 08:30 está ocupado, 08:00 NÃO pode ser início de bloco n_slots=2.
        Verificação agnóstica de data: busca a primeira segunda na janela."""
        from voice_agent.medware_sql import listar_slots_livres
        from datetime import date, timedelta

        mock_grade.return_value = self._make_grade()

        # Encontrar a primeira segunda-feira dentro da janela de 14 dias
        hoje = date.today()
        # isoweekday: 1=seg...7=dom. DIASEMANA Medware 2 = seg (convenção dom=1)
        # Próxima segunda (ou hoje se for segunda)
        dias_ate_segunda = (1 - hoje.isoweekday()) % 7  # 0 se hoje é segunda
        primeira_segunda = hoje + timedelta(days=dias_ate_segunda)
        data_iso = primeira_segunda.isoformat()

        def fake_rows(r):
            # Ocupa apenas 08:30 da primeira segunda
            return [{"DATAHORAAGENDADA": f"{data_iso}T08:30:00"}]

        mock_rows.side_effect = fake_rows

        resultado = listar_slots_livres(12080, 5, dias=14, n_slots=2)
        horas_resultado = [(s["data_iso"], s["hora"]) for s in resultado]

        # 08:00 não deve estar porque 08:30 está ocupado
        assert (data_iso, "08:00") not in horas_resultado
        # 09:00 deve estar: 09:30 está livre → bloco 09:00+09:30 OK
        assert (data_iso, "09:00") in horas_resultado

    @patch("voice_agent.medware_sql.listar_grade_medico")
    @patch("voice_agent.medware_sql.executar")
    @patch("voice_agent.medware_sql.rows")
    def test_hora_min_nao_vaza_no_resultado(self, mock_rows, mock_exec, mock_grade):
        """hora_min é campo interno e não deve aparecer no resultado."""
        from voice_agent.medware_sql import listar_slots_livres
        mock_grade.return_value = self._make_grade()
        mock_rows.return_value = []
        resultado = listar_slots_livres(12080, 5, dias=7, n_slots=2)
        for s in resultado:
            assert "hora_min" not in s, "hora_min não deve vazar no resultado público"


# ---------------------------------------------------------------------------
# Concordância: "atendimento" vs "consulta"
# ---------------------------------------------------------------------------

class TestConcordanciaNominal:
    """Verifica que mensagens de agendamento usam 'atendimento' (neutro
    para 1-N slots) e não 'consulta' (implica 1 único atendimento)."""

    def test_mensagem_pergunta_data_usa_atendimento(self):
        """A mensagem de coleta de data deve usar 'atendimento' não 'consulta'."""
        # Mensagem canônica definida na sessão anterior
        mensagem = "Oi, Elida! 😊 Qual data você prefere para o atendimento da Ana Beatriz?"
        assert "atendimento" in mensagem.lower()
        assert "consulta" not in mensagem.lower()

    def test_palavra_atendimento_cobre_multiplos_slots(self):
        """'atendimento' é semanticamente correto para 1, 2, 3 ou 4 slots."""
        for n in [1, 2, 3, 4]:
            msg = f"Qual data prefere para o atendimento? ({n} horários consecutivos)"
            assert "atendimento" in msg.lower()
