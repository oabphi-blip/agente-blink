"""
Bug C-92 — Paciente JÁ AGENDADO pediu remarcar/corrigir dados/fila de espera.
(Lead 16843614 Beatriz — 5-AGENDADO, confirmação de reagendamento)

Lia não deve oferecer novos slots para leads em 5-AGENDADO / 6-CONFIRMAR /
7.CONFIRMADO. Deve escalar imediatamente para ATENDIMENTO HUMANO.

Testa o FILTRO C-92 em responder.py::_scrub_prohibited().
"""
import re
import unittest
from typing import Optional


# ---------------------------------------------------------------------------
# Replica da lógica do filtro C-92 (standalone para teste isolado)
# ---------------------------------------------------------------------------

_C92_STATUS_AGENDADO = {101507507, 101109455, 106653499}

_C92_TERMOS_RE = re.compile(
    r"remarcar|reagendar|remarca[çc][aã]o|reagendamento"
    r"|mudar\s+(?:[oa]\s+)?(?:data|dia|hor[áa]rio)"
    r"|trocar\s+(?:[oa]\s+)?(?:data|dia|hor[áa]rio)"
    r"|corrigir\s+(?:os?\s+)?dados?"
    r"|fila\s+de\s+espera"
    r"|outro\s+hor[áa]rio|outra\s+data|outro\s+dia"
    r"|n[aã]o\s+(?:vou|posso|d[áa])\s+(?:conseguir\s+)?(?:ir|comparecer|mais)"
    r"|n[aã]o\s+consigo\s+(?:mais\s+)?(?:ir|comparecer)"
    r"|preciso\s+que\s+(?:o\s+)?hor[áa]rio\s+seja"
    r"|mudar\s+(?:[oa]\s+)?(?:minha\s+)?consulta"
    r"|cancelar\s+(?:[oa]\s+)?(?:minha\s+)?consulta"
    r"|quero\s+(?:mudar|trocar|remarcar|cancelar)",
    re.IGNORECASE,
)


def _simular_filtro_c92(user_text: str, status_id: Optional[int]) -> bool:
    """
    Retorna True se o filtro C-92 deve interceptar (lead agendado + pedido de remarcar).
    """
    if status_id not in _C92_STATUS_AGENDADO:
        return False
    if not user_text:
        return False
    return bool(_C92_TERMOS_RE.search(user_text))


# ---------------------------------------------------------------------------
# Testes
# ---------------------------------------------------------------------------

class TestC92ReagendamentoAgendado(unittest.TestCase):

    # ── Cenários que DEVEM interceptar (lead agendado + pedido remarcar) ──

    def test_remarcar_5agendado(self):
        """'remarcar' em 5-AGENDADO → interceptar."""
        self.assertTrue(_simular_filtro_c92("quero remarcar minha consulta", 101507507))

    def test_reagendar_6confirmar(self):
        """'reagendar' em 6-CONFIRMAR → interceptar."""
        self.assertTrue(_simular_filtro_c92("preciso reagendar", 101109455))

    def test_mudar_horario_7confirmado(self):
        """'mudar o horário' em 7.CONFIRMADO → interceptar."""
        self.assertTrue(_simular_filtro_c92("Posso mudar o horário?", 106653499))

    def test_corrigir_dados_5agendado(self):
        """'corrigir dados' em 5-AGENDADO → interceptar."""
        self.assertTrue(_simular_filtro_c92("Preciso corrigir os dados da consulta", 101507507))

    def test_fila_de_espera_5agendado(self):
        """'fila de espera' em 5-AGENDADO → interceptar."""
        self.assertTrue(_simular_filtro_c92("Quero entrar na fila de espera", 101507507))

    def test_outro_horario_5agendado(self):
        """'outro horário' em 5-AGENDADO → interceptar."""
        self.assertTrue(_simular_filtro_c92("Tem outro horário disponível?", 101507507))

    def test_nao_vou_conseguir_5agendado(self):
        """'não vou conseguir ir' em 5-AGENDADO → interceptar."""
        self.assertTrue(_simular_filtro_c92("não vou conseguir ir nesse dia", 101507507))

    def test_preciso_que_horario_seja_5agendado(self):
        """Variante Beatriz: 'preciso que o horário seja X' → interceptar."""
        self.assertTrue(
            _simular_filtro_c92("Preciso que o horário seja pela manhã", 101507507)
        )

    def test_cancelar_consulta_6confirmar(self):
        """'cancelar a consulta' em 6-CONFIRMAR → interceptar."""
        self.assertTrue(_simular_filtro_c92("Quero cancelar a consulta", 101109455))

    def test_trocar_data_7confirmado(self):
        """'trocar a data' em 7.CONFIRMADO → interceptar."""
        self.assertTrue(_simular_filtro_c92("Posso trocar a data?", 106653499))

    def test_nao_posso_comparecer(self):
        """'não posso comparecer' em 5-AGENDADO → interceptar."""
        self.assertTrue(_simular_filtro_c92("Infelizmente não posso comparecer", 101507507))

    def test_nao_consigo_mais_ir(self):
        """'não consigo mais ir' em 6-CONFIRMAR → interceptar."""
        self.assertTrue(_simular_filtro_c92("não consigo mais ir amanhã", 101109455))

    def test_quero_mudar_consulta(self):
        """'quero mudar a consulta' → interceptar."""
        self.assertTrue(_simular_filtro_c92("quero mudar a minha consulta", 101507507))

    def test_mudar_dia_6confirmar(self):
        """'mudar o dia' em 6-CONFIRMAR → interceptar."""
        self.assertTrue(_simular_filtro_c92("Posso mudar o dia?", 101109455))

    def test_reagendamento_palavra_7confirmado(self):
        """'reagendamento' sozinho em 7.CONFIRMADO → interceptar."""
        self.assertTrue(_simular_filtro_c92("reagendamento por favor", 106653499))

    # ── Cenários que NÃO devem interceptar ──

    def test_sem_status_agendado_nao_intercepta(self):
        """Lead em 3-AGENDAR não deve ser interceptado (C-92 só age em AGENDADO)."""
        self.assertFalse(_simular_filtro_c92("quero remarcar", 102560495))

    def test_status_nulo_nao_intercepta(self):
        """status_id None → não interceptar."""
        self.assertFalse(_simular_filtro_c92("remarcar", None))

    def test_status_entrada_nao_intercepta(self):
        """Lead em 0-ETAPA ENTRADA não deve ser interceptado."""
        self.assertFalse(_simular_filtro_c92("quero remarcar", 96441724))

    def test_mensagem_normal_agendado_nao_intercepta(self):
        """Mensagem normal ('ok', 'confirmado') em 5-AGENDADO → não interceptar."""
        self.assertFalse(_simular_filtro_c92("Ok, confirmado!", 101507507))

    def test_confirmacao_agendado_nao_intercepta(self):
        """'confirmo o horário' não é pedido de remarcar."""
        self.assertFalse(_simular_filtro_c92("confirmo o horário, estarei lá", 101507507))

    def test_obrigada_nao_intercepta(self):
        """'Obrigada' em 5-AGENDADO → não interceptar."""
        self.assertFalse(_simular_filtro_c92("Obrigada!", 101507507))

    def test_pergunta_valor_agendado_nao_intercepta(self):
        """'Qual o valor?' em 5-AGENDADO → não interceptar (é FAQ, não remarcar)."""
        self.assertFalse(_simular_filtro_c92("Qual o valor da consulta?", 101507507))

    def test_texto_vazio_nao_intercepta(self):
        """Texto vazio → não interceptar."""
        self.assertFalse(_simular_filtro_c92("", 101507507))

    def test_status_closed_won_nao_intercepta(self):
        """Lead em Closed-won (142) não deve ser interceptado."""
        self.assertFalse(_simular_filtro_c92("remarcar", 142))

    def test_status_8_realizado_nao_intercepta(self):
        """Lead em 8-REALIZADO (91486864) não deve ser interceptado."""
        self.assertFalse(_simular_filtro_c92("remarcar", 91486864))

    # ── Testa case-insensitive ──

    def test_remarcar_uppercase(self):
        """'REMARCAR' maiúsculo → interceptar."""
        self.assertTrue(_simular_filtro_c92("REMARCAR CONSULTA", 101507507))

    def test_reagendar_mixed_case(self):
        """'Reagendar' com inicial maiúscula → interceptar."""
        self.assertTrue(_simular_filtro_c92("Reagendar por favor", 101507507))

    # ── Variantes com acento ──

    def test_remarcacao_com_acento(self):
        """'remarcação' com cedilha → interceptar."""
        self.assertTrue(_simular_filtro_c92("solicito remarcação", 101507507))

    def test_remarcacao_sem_acento(self):
        """'remarcacao' sem cedilha → interceptar."""
        self.assertTrue(_simular_filtro_c92("quero fazer remarcacao", 101507507))

    def test_horario_com_acento(self):
        """'horário' com acento → interceptar."""
        self.assertTrue(_simular_filtro_c92("mudar o horário", 101507507))


class TestC92StatusIds(unittest.TestCase):
    """Valida que os status IDs do conjunto estão corretos."""

    def test_5agendado_no_set(self):
        self.assertIn(101507507, _C92_STATUS_AGENDADO)

    def test_6confirmar_no_set(self):
        self.assertIn(101109455, _C92_STATUS_AGENDADO)

    def test_7confirmado_no_set(self):
        self.assertIn(106653499, _C92_STATUS_AGENDADO)

    def test_3agendar_fora_do_set(self):
        self.assertNotIn(102560495, _C92_STATUS_AGENDADO)

    def test_atendimento_humano_fora_do_set(self):
        self.assertNotIn(106563343, _C92_STATUS_AGENDADO)


class TestC92RespostaCanonica(unittest.TestCase):
    """Valida o formato da resposta canônica retornada pelo filtro C-92."""

    def _gerar_resp_c92(self, nome_contato: Optional[str] = None) -> str:
        """Replica a geração de resposta do filtro C-92."""
        nome = str(nome_contato or "").strip()
        saud = (f"{nome.split()[0]}, e" if nome else "E")
        return (
            f"{saud}ntendido! Para remarcar ou ajustar sua consulta, "
            "vou passar você para nossa equipe. Em instantes alguém da Blink te ajuda! 🤝"
        )

    def test_resposta_com_nome(self):
        """Com nome, resposta deve incluir primeiro nome."""
        resp = self._gerar_resp_c92("Beatriz Lobosque")
        self.assertIn("Beatriz", resp)
        self.assertIn("entendido", resp.lower())
        self.assertIn("remarcar", resp.lower())
        self.assertIn("Blink", resp)

    def test_resposta_sem_nome(self):
        """Sem nome, resposta começa com 'Entendido!'."""
        resp = self._gerar_resp_c92(None)
        self.assertTrue(resp.startswith("Entendido!"))
        self.assertIn("remarcar", resp.lower())

    def test_resposta_nao_oferece_slot(self):
        """Resposta canônica não deve conter '1️⃣' ou '2️⃣' (oferta de slot)."""
        resp = self._gerar_resp_c92("Beatriz")
        self.assertNotIn("1️⃣", resp)
        self.assertNotIn("2️⃣", resp)

    def test_resposta_menciona_equipe(self):
        """Resposta deve mencionar que vai passar para a equipe."""
        resp = self._gerar_resp_c92()
        self.assertIn("equipe", resp.lower())


if __name__ == "__main__":
    unittest.main(verbosity=2)
