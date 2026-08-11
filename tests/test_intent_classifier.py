"""
tests/test_intent_classifier.py
Bug C-81 — Classificador de intenção pré-LLM
Pytest para voice_agent/intent_classifier.py

Cobertura:
  - Urgência crítica (trauma, perda de visão)
  - Urgência prioritária (Isabella case: olhos inchados + remelando)
  - Rotina (agendamento simples)
  - Pré-extração: unidade, n_patients, day_pref, turno, médico
  - Injeção em caller_context
  - Mensagens canônicas de urgência
  - Edge cases (texto vazio, acentos, mayúsculas)
"""

import pytest
from voice_agent.intent_classifier import (
    classify_intent,
    gerar_msg_urgencia,
    injetar_pre_slots,
    IntentResult,
    PreSlots,
)


# ===========================================================================
# CLASSE 1: Urgência Crítica
# ===========================================================================

class TestUrgenciaCritica:
    def test_perda_de_visao(self):
        r = classify_intent("meu filho teve perda de visão no olho direito")
        assert r.urgency_level == "critical"
        assert r.escalate_human is True
        assert r.skip_convenio is True

    def test_nao_enxerga(self):
        r = classify_intent("ele não enxerga mais, aconteceu de repente")
        assert r.urgency_level == "critical"

    def test_trauma_ocular(self):
        r = classify_intent("sofreu trauma ocular jogando bola")
        assert r.urgency_level == "critical"

    def test_bateu_no_olho(self):
        r = classify_intent("bateu no olho com o lápis")
        assert r.urgency_level == "critical"

    def test_cortou_o_olho(self):
        r = classify_intent("cortou o olho com um vidro")
        assert r.urgency_level == "critical"

    def test_corpo_estranho(self):
        r = classify_intent("entrou corpo estranho no olho, estou com muita dor")
        assert r.urgency_level == "critical"

    def test_descolamento(self):
        r = classify_intent("o médico disse que pode ser descolamento de retina")
        assert r.urgency_level == "critical"

    def test_ficou_cega(self):
        r = classify_intent("minha mãe ficou cega de repente")
        assert r.urgency_level == "critical"

    def test_intent_urgencia_em_critical(self):
        r = classify_intent("bateu o olho na parede")
        assert r.intent == "urgencia"

    def test_msg_critical_gerada(self):
        r = classify_intent("perdeu a visão")
        msg = gerar_msg_urgencia(r, "Ana")
        assert "emergência" in msg
        assert "SAMU" in msg or "pronto-socorro" in msg

    def test_msg_critical_sem_nome(self):
        r = classify_intent("perdeu a visão")
        msg = gerar_msg_urgencia(r)
        assert "emergência" in msg


# ===========================================================================
# CLASSE 2: Urgência Prioritária (caso Isabella)
# ===========================================================================

class TestUrgenciaPrioritaria:
    def test_isabella_case_olhos_inchados_remelando(self):
        """Caso real: lead 22335902 Isabella — bug C-81 origem."""
        r = classify_intent(
            "boa tarde, o olho do meu filho está inchado e remelando desde ontem"
        )
        assert r.urgency_level == "priority"
        assert r.skip_convenio is True
        assert r.escalate_human is False

    def test_olho_vermelho(self):
        r = classify_intent("olho vermelho há 2 dias")
        assert r.urgency_level == "priority"

    def test_remela(self):
        r = classify_intent("está com muita remela")
        assert r.urgency_level == "priority"

    def test_remelando(self):
        r = classify_intent("olho remelando desde ontem")
        assert r.urgency_level == "priority"

    def test_conjuntivite(self):
        r = classify_intent("acho que é conjuntivite")
        assert r.urgency_level == "priority"

    def test_dor_no_olho(self):
        r = classify_intent("estou com dor no olho")
        assert r.urgency_level == "priority"

    def test_ardor(self):
        r = classify_intent("sentindo ardor e coceira intensa no olho")
        assert r.urgency_level == "priority"

    def test_visao_embaçada(self):
        r = classify_intent("visão embaçada de repente")
        assert r.urgency_level == "priority"

    def test_urgente_explícito(self):
        r = classify_intent("preciso de atendimento urgente")
        assert r.urgency_level == "priority"

    def test_preciso_hoje(self):
        r = classify_intent("preciso de uma consulta hoje se possível")
        assert r.urgency_level == "priority"

    def test_o_mais_rapido(self):
        r = classify_intent("quero marcar o mais rápido possível")
        assert r.urgency_level == "priority"

    def test_msg_priority_gerada(self):
        r = classify_intent("olho inchado remelando")
        msg = gerar_msg_urgencia(r, "Maria")
        assert "encaixe" in msg or "atenção" in msg

    def test_intent_urgencia_em_priority(self):
        r = classify_intent("olho vermelho e com secreção")
        assert r.intent == "urgencia"

    def test_fotofobia(self):
        r = classify_intent("está com fotofobia, sensibilidade à luz")
        assert r.urgency_level == "priority"

    def test_pus_no_olho(self):
        r = classify_intent("tem pus no olho")
        assert r.urgency_level == "priority"


# ===========================================================================
# CLASSE 3: Rotina
# ===========================================================================

class TestRotina:
    def test_agendamento_simples(self):
        r = classify_intent("quero marcar uma consulta com a Dra. Karla")
        assert r.urgency_level == "routine"
        assert r.skip_convenio is False
        assert r.escalate_human is False

    def test_retorno_consulta(self):
        r = classify_intent("gostaria de agendar retorno")
        assert r.urgency_level == "routine"

    def test_primeira_mensagem_boa_tarde(self):
        r = classify_intent("Boa tarde!")
        assert r.urgency_level == "routine"
        assert r.intent == "agendamento"

    def test_oi_tudo_bem(self):
        r = classify_intent("Oi, tudo bem?")
        assert r.urgency_level == "routine"

    def test_msg_routine_sem_urgencia(self):
        r = classify_intent("quero agendar")
        msg = gerar_msg_urgencia(r)
        assert msg == ""  # rotina não gera msg de urgência


# ===========================================================================
# CLASSE 4: Intenções (FAQ, Cancelamento)
# ===========================================================================

class TestIntents:
    def test_faq_valor(self):
        r = classify_intent("quanto custa a consulta?")
        assert r.intent == "faq_valor"
        assert r.urgency_level == "routine"

    def test_faq_valor_preco(self):
        r = classify_intent("qual o preço da avaliação?")
        assert r.intent == "faq_valor"

    def test_faq_local(self):
        r = classify_intent("onde fica a clínica?")
        assert r.intent == "faq_local"

    def test_faq_local_endereco(self):
        r = classify_intent("me passa o endereço")
        assert r.intent == "faq_local"

    def test_cancelamento(self):
        r = classify_intent("quero cancelar minha consulta")
        assert r.intent == "cancelamento"

    def test_cancelamento_nao_vai(self):
        r = classify_intent("não vou conseguir ir amanhã")
        assert r.intent == "cancelamento"

    def test_urgencia_sobrepoe_faq_valor(self):
        """Urgência é mais importante que qualquer outra intenção."""
        r = classify_intent("olho vermelho e inchado, quanto custa?")
        assert r.intent == "urgencia"
        assert r.urgency_level == "priority"


# ===========================================================================
# CLASSE 5: Pré-extração de unidade
# ===========================================================================

class TestExtrairUnidade:
    def test_asa_norte(self):
        r = classify_intent("gostaria de atender na Asa Norte")
        assert r.pre_slots.unidade == "Asa Norte"

    def test_aguas_claras(self):
        r = classify_intent("tenho preferência por Águas Claras")
        assert r.pre_slots.unidade == "Águas Claras"

    def test_aguas_claras_sem_acento(self):
        r = classify_intent("pode ser em aguas claras?")
        assert r.pre_slots.unidade == "Águas Claras"

    def test_sem_unidade(self):
        r = classify_intent("quero marcar uma consulta")
        assert r.pre_slots.unidade is None

    def test_unidade_nao_sobrescreve_ctx(self):
        ctx = {"known": {"unidade": "Águas Claras"}}
        r = classify_intent("prefiro Asa Norte", caller_context=ctx)
        # Com ctx já preenchido, não deve sobrescrever
        assert r.pre_slots.unidade is None  # foi limpo por detectar ctx conflitante


# ===========================================================================
# CLASSE 6: Pré-extração de n_patients
# ===========================================================================

class TestExtrairNPacientes:
    def test_2_filhos(self):
        r = classify_intent("tenho 2 filhos para consultar")
        assert r.pre_slots.n_patients == 2

    def test_dois_filhos(self):
        r = classify_intent("são dois filhos")
        assert r.pre_slots.n_patients == 2

    def test_eu_e_minha_filha(self):
        r = classify_intent("eu e minha filha precisamos de consulta")
        assert r.pre_slots.n_patients == 2

    def test_nos_dois(self):
        r = classify_intent("nós dois queremos marcar")
        assert r.pre_slots.n_patients == 2

    def test_sem_numero(self):
        r = classify_intent("quero marcar para minha filha")
        # Sem número explícito, n_patients não deve ser extraído
        assert r.pre_slots.n_patients is None or r.pre_slots.n_patients == 1


# ===========================================================================
# CLASSE 7: Pré-extração de dia/turno
# ===========================================================================

class TestExtrairDiaTurno:
    def test_segunda(self):
        r = classify_intent("prefiro segunda-feira de manhã")
        assert r.pre_slots.day_pref == "segunda"
        assert r.pre_slots.turno == "manhã"

    def test_terca(self):
        r = classify_intent("tenho disponibilidade na terça")
        assert r.pre_slots.day_pref == "terça"

    def test_amanha(self):
        r = classify_intent("tem horário para amanhã?")
        assert r.pre_slots.day_pref == "amanhã"

    def test_semana_que_vem(self):
        r = classify_intent("quero agendar para a semana que vem")
        assert r.pre_slots.day_pref == "semana_que_vem"

    def test_turno_tarde(self):
        r = classify_intent("prefiro à tarde se possível")
        assert r.pre_slots.turno == "tarde"

    def test_turno_manha(self):
        r = classify_intent("só posso de manhã")
        assert r.pre_slots.turno == "manhã"

    def test_sem_dia(self):
        r = classify_intent("quero marcar")
        assert r.pre_slots.day_pref is None


# ===========================================================================
# CLASSE 8: Pré-extração de médico
# ===========================================================================

class TestExtrairMedico:
    def test_karla(self):
        r = classify_intent("quero consultar com a Karla")
        assert r.pre_slots.medico == "Karla"

    def test_dra_karla(self):
        r = classify_intent("consulta com Dra. Karla")
        assert r.pre_slots.medico == "Karla"

    def test_fabricio(self):
        r = classify_intent("preciso ver o Dr. Fabrício")
        assert r.pre_slots.medico == "Fabrício"

    def test_sem_medico(self):
        r = classify_intent("quero marcar uma consulta")
        assert r.pre_slots.medico is None


# ===========================================================================
# CLASSE 9: Injeção em caller_context
# ===========================================================================

class TestInjetarPreSlots:
    def test_injeta_unidade(self):
        ctx = {"known": {}}
        r = classify_intent("atender na Asa Norte")
        injetar_pre_slots(ctx, r)
        assert ctx["known"]["unidade"] == "Asa Norte"

    def test_nao_sobrescreve_unidade_existente(self):
        ctx = {"known": {"unidade": "Águas Claras"}}
        r = classify_intent("prefiro Asa Norte")
        injetar_pre_slots(ctx, r)
        # pre_slots.unidade foi limpo pelo classify_intent ao detectar conflito com ctx
        assert ctx["known"]["unidade"] == "Águas Claras"

    def test_injeta_dia_turno(self):
        ctx = {"known": {}}
        r = classify_intent("segunda-feira de tarde")
        injetar_pre_slots(ctx, r)
        assert ctx["known"]["dia_turno"] == "segunda"
        assert ctx["known"]["turno_preferido"] == "tarde"

    def test_injeta_urgency_flag(self):
        ctx = {"known": {}}
        r = classify_intent("olho inchado e vermelho")
        injetar_pre_slots(ctx, r)
        assert ctx["known"].get("urgency_level") == "priority"
        assert ctx["known"].get("skip_convenio") is True

    def test_ctx_none_nao_explode(self):
        r = classify_intent("qualquer coisa")
        result = injetar_pre_slots(None, r)
        assert result is None

    def test_ctx_sem_known(self):
        ctx = {}
        r = classify_intent("segunda de manhã")
        injetar_pre_slots(ctx, r)
        assert "known" in ctx


# ===========================================================================
# CLASSE 10: Edge cases
# ===========================================================================

class TestEdgeCases:
    def test_texto_vazio(self):
        r = classify_intent("")
        assert r.urgency_level == "routine"
        assert r.reasoning == "empty message"

    def test_maiusculas(self):
        r = classify_intent("OLHO INCHADO E REMELANDO")
        assert r.urgency_level == "priority"

    def test_sem_acento_remela(self):
        r = classify_intent("remela no olho")
        assert r.urgency_level == "priority"

    def test_reasoning_presente(self):
        r = classify_intent("olho vermelho")
        assert "[C-81]" in r.reasoning
        assert "priority" in r.reasoning

    def test_caller_context_none(self):
        r = classify_intent("asa norte terça-feira", caller_context=None)
        assert r.pre_slots.unidade == "Asa Norte"
        assert r.pre_slots.day_pref == "terça"
