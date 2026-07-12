"""Pytest dos 4 bypasses determinísticos (Nível 3 do framework anti-invenção).

Cada asserção usa contexto REAL de pacientes que travaram a Lia:
    - Urgência: Clarice (trauma na córnea)
    - Valor: Adriana (PróSaúde perguntou preço)
    - Aceite slot: Theo/Tiago (opção 2)
    - Endereço pós-agenda: Marcela 24232988 (não recebeu endereço)
"""
from __future__ import annotations

import pytest

from voice_agent.blindagens_deterministicas import (
    _identificar_slot_aceito,
    deve_enviar_endereco_pos_agenda,
    deve_gerar_confirmacao_aceite,
    deve_orientar_urgencia,
    deve_responder_valor,
    tentar_bypass_deterministico,
)


# ═══════════════════════════════════════════════════════════════════════
# CTX HELPERS
# ═══════════════════════════════════════════════════════════════════════

def _ctx_com_medico_karla_asa_norte(convenio: str = "Particular") -> dict:
    return {
        "fsm": {"estado": "AGENDA"},
        "known": {
            "nome_paciente": "Clarice Santos Brunelli",
            "medico": "Dra. Karla Delalíbera",
            "unidade": "Asa Norte",
            "convenio": convenio,
        },
    }


def _slots_theo_tiago() -> list[dict]:
    return [
        {"data_iso": "2026-08-07", "hora": "08:30"},
        {"data_iso": "2026-08-07", "hora": "10:00"},
    ]


# ═══════════════════════════════════════════════════════════════════════
# BYPASS 1 — CONFIRMAÇÃO DE ACEITE
# ═══════════════════════════════════════════════════════════════════════

class TestConfirmacaoAceite:
    def test_paciente_disse_opcao_2_pega_segundo_slot(self):
        ctx = _ctx_com_medico_karla_asa_norte()
        ctx["slots_ofertados"] = _slots_theo_tiago()
        texto = deve_gerar_confirmacao_aceite(ctx, "opção 2")
        assert texto is not None
        assert "07/08" in texto
        assert "10:00" in texto or "10h00" in texto or "10 " in texto

    def test_paciente_disse_emoji_1_pega_primeiro_slot(self):
        ctx = _ctx_com_medico_karla_asa_norte()
        ctx["slots_ofertados"] = _slots_theo_tiago()
        texto = deve_gerar_confirmacao_aceite(ctx, "1️⃣")
        assert texto is not None
        assert "07/08" in texto
        # Primeiro slot é 08:30
        assert "08:30" in texto or "8h30" in texto or "08" in texto

    def test_paciente_disse_segunda_1308_1730(self):
        ctx = _ctx_com_medico_karla_asa_norte()
        ctx["slots_ofertados"] = [
            {"data_iso": "2026-07-13", "hora": "17:30"},
            {"data_iso": "2026-07-15", "hora": "13:30"},
        ]
        texto = deve_gerar_confirmacao_aceite(ctx, "prefiro segunda-feira 13/07 às 17h30")
        assert texto is not None
        assert "13/07" in texto

    def test_sem_slots_ofertados_retorna_none(self):
        ctx = _ctx_com_medico_karla_asa_norte()
        # sem ctx["slots_ofertados"]
        texto = deve_gerar_confirmacao_aceite(ctx, "opção 1")
        assert texto is None

    def test_texto_sem_sinal_de_aceite_retorna_none(self):
        ctx = _ctx_com_medico_karla_asa_norte()
        ctx["slots_ofertados"] = _slots_theo_tiago()
        texto = deve_gerar_confirmacao_aceite(ctx, "quando começa a consulta?")
        assert texto is None

    def test_texto_contem_medico_canonico(self):
        ctx = _ctx_com_medico_karla_asa_norte()
        ctx["slots_ofertados"] = _slots_theo_tiago()
        texto = deve_gerar_confirmacao_aceite(ctx, "1️⃣")
        assert "Dra. Karla Delalíbera" in texto

    def test_convenio_aceito_aparece(self):
        ctx = _ctx_com_medico_karla_asa_norte(convenio="Saúde Caixa")
        ctx["slots_ofertados"] = _slots_theo_tiago()
        texto = deve_gerar_confirmacao_aceite(ctx, "1️⃣")
        assert "Saúde Caixa" in texto

    def test_particular_nao_menciona_convenio_falso(self):
        ctx = _ctx_com_medico_karla_asa_norte(convenio="Particular")
        ctx["slots_ofertados"] = _slots_theo_tiago()
        texto = deve_gerar_confirmacao_aceite(ctx, "1️⃣")
        assert "pelo Particular" not in texto

    def test_toggle_off_retorna_none(self, monkeypatch):
        monkeypatch.setenv("BLINDAGEM_ACEITE_ATIVADO", "0")
        ctx = _ctx_com_medico_karla_asa_norte()
        ctx["slots_ofertados"] = _slots_theo_tiago()
        assert deve_gerar_confirmacao_aceite(ctx, "1️⃣") is None


class TestIdentificarSlot:
    def test_emoji_1(self):
        slots = _slots_theo_tiago()
        assert _identificar_slot_aceito("1️⃣", slots) == slots[0]

    def test_data_literal(self):
        slots = [
            {"data_iso": "2026-07-14", "hora": "17:30"},
            {"data_iso": "2026-07-16", "hora": "11:30"},
        ]
        assert _identificar_slot_aceito("prefiro 16/07 então", slots) == slots[1]

    def test_hora_literal(self):
        slots = [
            {"data_iso": "2026-07-14", "hora": "17:30"},
            {"data_iso": "2026-07-16", "hora": "11:30"},
        ]
        assert _identificar_slot_aceito("11h30 fica bom", slots) == slots[1]


# ═══════════════════════════════════════════════════════════════════════
# BYPASS 2 — ENDEREÇO PÓS-AGENDA
# ═══════════════════════════════════════════════════════════════════════

class TestEnderecoPosAgenda:
    def test_agenda_gravada_gera_texto(self):
        ctx = _ctx_com_medico_karla_asa_norte(convenio="Care Plus")
        ctx["agenda_gravada"] = True
        ctx["endereco_ja_enviado"] = False
        ctx["known"]["dia_hora_confirmado"] = "Terça-feira, 07/08/2026 às 10:00"
        texto = deve_enviar_endereco_pos_agenda(ctx)
        assert texto is not None
        assert "Asa Norte" in texto
        assert "Dra. Karla Delalíbera" in texto
        assert "📍" in texto  # emoji endereço

    def test_agenda_nao_gravada_retorna_none(self):
        ctx = _ctx_com_medico_karla_asa_norte()
        ctx["agenda_gravada"] = False
        assert deve_enviar_endereco_pos_agenda(ctx) is None

    def test_endereco_ja_enviado_retorna_none(self):
        ctx = _ctx_com_medico_karla_asa_norte()
        ctx["agenda_gravada"] = True
        ctx["endereco_ja_enviado"] = True
        assert deve_enviar_endereco_pos_agenda(ctx) is None

    def test_texto_contem_maps_url(self):
        ctx = _ctx_com_medico_karla_asa_norte()
        ctx["agenda_gravada"] = True
        ctx["known"]["dia_hora_confirmado"] = "07/08 10:00"
        texto = deve_enviar_endereco_pos_agenda(ctx)
        assert "google.com/maps" in texto or "Mapa" in texto

    def test_aguas_claras_pega_endereco_certo(self):
        ctx = _ctx_com_medico_karla_asa_norte(convenio="TJDFT")
        ctx["known"]["unidade"] = "Águas Claras"
        ctx["known"]["dia_hora_confirmado"] = "16/07 15:00"
        ctx["agenda_gravada"] = True
        texto = deve_enviar_endereco_pos_agenda(ctx)
        assert "Águas Claras" in texto


# ═══════════════════════════════════════════════════════════════════════
# BYPASS 3 — URGÊNCIA MÉDICA
# ═══════════════════════════════════════════════════════════════════════

class TestUrgencia:
    @pytest.mark.parametrize("frase", [
        "sofri um trauma na córnea",
        "estou com dor forte no olho",
        "não consigo abrir o olho",
        "não estou conseguindo enxergar",
        "olho muito vermelho e doendo",
        "caiu algo no olho",
        "levou uma batida forte no olho",
        "acidente no olho ontem",
        "queimadura no olho com produto",
    ])
    def test_detecta_urgencia(self, frase):
        ctx = _ctx_com_medico_karla_asa_norte()
        texto = deve_orientar_urgencia(ctx, frase)
        assert texto is not None, f"NÃO detectou urgência em: {frase!r}"

    def test_orientacao_menciona_ps(self):
        ctx = _ctx_com_medico_karla_asa_norte()
        texto = deve_orientar_urgencia(ctx, "sofri um trauma na córnea agora")
        assert "pronto-socorro" in texto.lower() or "PS" in texto

    def test_menciona_hospital_brasilia(self):
        ctx = _ctx_com_medico_karla_asa_norte()
        texto = deve_orientar_urgencia(ctx, "trauma na córnea")
        assert "HBDF" in texto or "Hospital de Base" in texto or "HRAN" in texto

    def test_texto_normal_nao_dispara(self):
        ctx = _ctx_com_medico_karla_asa_norte()
        assert deve_orientar_urgencia(ctx, "quero agendar uma consulta") is None
        assert deve_orientar_urgencia(ctx, "tenho olhos sensíveis à luz") is None

    def test_urgencia_sem_ctx_ainda_dispara(self):
        texto = deve_orientar_urgencia(None, "trauma na córnea forte")
        assert texto is not None


# ═══════════════════════════════════════════════════════════════════════
# BYPASS 4 — VALOR CONSULTA
# ═══════════════════════════════════════════════════════════════════════

class TestValor:
    @pytest.mark.parametrize("frase", [
        "quanto custa a consulta?",
        "qual o valor?",
        "quanto vou pagar?",
        "qual o preço?",
        "quanto eu pago?",
        "quanto sai a consulta?",
    ])
    def test_detecta_pergunta_valor(self, frase):
        ctx = _ctx_com_medico_karla_asa_norte(convenio="Particular")
        texto = deve_responder_valor(ctx, frase)
        assert texto is not None, f"NÃO detectou pergunta em: {frase!r}"

    def test_convenio_aceito_fala_coberto(self):
        ctx = _ctx_com_medico_karla_asa_norte(convenio="Saúde Caixa")
        texto = deve_responder_valor(ctx, "quanto custa?")
        assert texto is not None
        assert "coberta" in texto.lower() or "cobre" in texto.lower()
        assert "Saúde Caixa" in texto or "saúde caixa" in texto.lower()

    def test_particular_karla_valor_correto(self):
        ctx = _ctx_com_medico_karla_asa_norte(convenio="Particular")
        texto = deve_responder_valor(ctx, "qual valor?")
        assert texto is not None
        # Karla particular = R$ 611 (não APV)
        assert "R$ 611" in texto or "611" in texto

    def test_particular_karla_apv(self):
        ctx = _ctx_com_medico_karla_asa_norte(convenio="Particular")
        ctx["known"]["motivo"] = "avaliação processamento visual"
        texto = deve_responder_valor(ctx, "quanto custa?")
        assert texto is not None
        assert "R$ 800" in texto or "800" in texto

    def test_sem_medico_retorna_none(self):
        ctx = {"known": {"nome_paciente": "Test"}}
        assert deve_responder_valor(ctx, "quanto?") is None

    def test_texto_sem_pergunta_nao_dispara(self):
        ctx = _ctx_com_medico_karla_asa_norte()
        assert deve_responder_valor(ctx, "queria agendar amanhã") is None


# ═══════════════════════════════════════════════════════════════════════
# ORQUESTRADOR — prioridade correta
# ═══════════════════════════════════════════════════════════════════════

class TestOrquestrador:
    def test_urgencia_prioridade_absoluta(self):
        ctx = _ctx_com_medico_karla_asa_norte(convenio="Particular")
        ctx["slots_ofertados"] = _slots_theo_tiago()
        # Paciente diz "1" MAS TAMBÉM tem trauma
        resultado = tentar_bypass_deterministico(
            ctx, "1 mas estou com trauma na córnea",
        )
        assert resultado is not None
        nome, texto = resultado
        assert nome == "urgencia"

    def test_valor_antes_aceite(self):
        ctx = _ctx_com_medico_karla_asa_norte(convenio="Particular")
        ctx["slots_ofertados"] = _slots_theo_tiago()
        # Paciente pergunta valor mas texto tem "1"
        resultado = tentar_bypass_deterministico(
            ctx, "quanto custa opção 1?",
        )
        # Valor tem prioridade sobre aceite
        assert resultado is not None
        nome, _ = resultado
        assert nome == "valor"

    def test_aceite_slot_puro(self):
        ctx = _ctx_com_medico_karla_asa_norte(convenio="Care Plus")
        ctx["slots_ofertados"] = _slots_theo_tiago()
        resultado = tentar_bypass_deterministico(ctx, "opção 1")
        assert resultado is not None
        nome, _ = resultado
        assert nome == "aceite_slot"

    def test_endereco_pos_agenda_ultimo(self):
        ctx = _ctx_com_medico_karla_asa_norte()
        ctx["agenda_gravada"] = True
        ctx["known"]["dia_hora_confirmado"] = "07/08 10:00"
        resultado = tentar_bypass_deterministico(ctx, "")
        assert resultado is not None
        nome, _ = resultado
        assert nome == "endereco_pos_agenda"

    def test_nenhum_bypass_retorna_none(self):
        ctx = _ctx_com_medico_karla_asa_norte()
        resultado = tentar_bypass_deterministico(ctx, "qual o horário de funcionamento?")
        assert resultado is None

    def test_excecao_fail_open(self):
        # ctx malformado — não deve estourar
        resultado = tentar_bypass_deterministico({"broken": True}, "opção 1")
        assert resultado is None or isinstance(resultado, tuple)


# ═══════════════════════════════════════════════════════════════════════
# INTEGRAÇÃO — bypass NÃO contém frases banidas
# ═══════════════════════════════════════════════════════════════════════

class TestBypassSemFrasesInventadas:
    """Nenhum bypass pode gerar texto com padrão C-44 (papel inventado)."""

    @pytest.mark.parametrize("input_ctx_and_text", [
        ("1️⃣", True),
        ("opção 2", True),
        ("quanto custa?", False),
        ("trauma na córnea", False),
    ])
    def test_nunca_menciona_especialista_em_x(self, input_ctx_and_text):
        from voice_agent.responder import _viola_papel_inventado

        user_text, precisa_slots = input_ctx_and_text
        ctx = _ctx_com_medico_karla_asa_norte(convenio="Particular")
        if precisa_slots:
            ctx["slots_ofertados"] = _slots_theo_tiago()

        resultado = tentar_bypass_deterministico(ctx, user_text)
        if resultado:
            _, texto = resultado
            assert _viola_papel_inventado(texto) is False, (
                f"Bypass gerou texto com papel inventado: {texto!r}"
            )
