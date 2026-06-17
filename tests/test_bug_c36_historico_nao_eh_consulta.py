"""
Pytest Bug C-36 — 1.DIA CONSULTA no passado tratado como consulta futura.

Origem: lead 22071351 Karina (17/06/2026 11:58).
- 1.DIA CONSULTA = 23/09/2025 (9 meses atrás, paciente FALTOU)
- ja_agendado = False (correto)
- ctx.known tinha medico/convenio/unidade/paciente_nome preenchidos
- Lia disse "consulta da Julia estava marcada, comparecer?"
- Atendente humana: "IA se atrapalhando"

Fix em 3 camadas:
1. ativacao_inteligente.py — saudação personalizada distingue passado
2. _MASTER_INSTRUCTION.md seção 0-AB — regra explícita
3. responder.py — filtro pós-geração sempre-ON
"""

import sys
import os
from pathlib import Path

# Stubs leves pra evitar deps pesadas (anthropic, redis, etc)
sys.path.insert(0, str(Path(__file__).parent.parent))
os.environ.setdefault("ANTHROPIC_API_KEY", "stub")


def test_viola_afirmou_consulta_ativa_pega_frase_karina():
    """Frase real da Lia no caso Karina deve ser pega pelo filtro."""
    from voice_agent.responder import _viola_afirmou_consulta_ativa_c36
    msg = (
        "Bom dia, Karina! Vi aqui que a consulta da Julia Akemi "
        "estava marcada com a Dra. Karla Delalíbera pelo TJDFT "
        "Pró-Saúde na unidade Águas Claras. Está tudo certo para "
        "comparecer, ou posso te ajudar com algo?"
    )
    ctx = {"ja_agendado": False, "known": {"medico": "Karla"}}
    assert _viola_afirmou_consulta_ativa_c36(msg, ctx) is True


def test_viola_pega_consulta_esta_marcada():
    from voice_agent.responder import _viola_afirmou_consulta_ativa_c36
    msg = "Olá! Sua consulta está marcada para amanhã."
    assert _viola_afirmou_consulta_ativa_c36(msg, {"ja_agendado": False}) is True


def test_viola_pega_consulta_esta_agendada():
    from voice_agent.responder import _viola_afirmou_consulta_ativa_c36
    msg = "Olá! Sua consulta está agendada com a Dra. Karla."
    assert _viola_afirmou_consulta_ativa_c36(msg, {"ja_agendado": False}) is True


def test_viola_pega_tudo_certo_para_comparecer():
    from voice_agent.responder import _viola_afirmou_consulta_ativa_c36
    msg = "Olá! Tudo certo para comparecer amanhã?"
    assert _viola_afirmou_consulta_ativa_c36(msg, {"ja_agendado": False}) is True


def test_NAO_bloqueia_quando_ja_agendado_true():
    """Quando ja_agendado=True, a Lia PODE falar de consulta ativa."""
    from voice_agent.responder import _viola_afirmou_consulta_ativa_c36
    msg = "Olá! Sua consulta está marcada para amanhã às 14h."
    assert _viola_afirmou_consulta_ativa_c36(msg, {"ja_agendado": True}) is False


def test_NAO_bloqueia_frase_inocente():
    from voice_agent.responder import _viola_afirmou_consulta_ativa_c36
    msg = "Olá! Posso te ajudar com algo hoje?"
    assert _viola_afirmou_consulta_ativa_c36(msg, {"ja_agendado": False}) is False


def test_gera_saudacao_historica_karla_convenio():
    from voice_agent.responder import _gerar_saudacao_historica_c36
    ctx = {
        "name": "Karina",
        "known": {
            "medico": "Dra. Karla Delalibera",
            "convenio": "TJDFT Pró-Saúde",
        },
    }
    out = _gerar_saudacao_historica_c36(ctx)
    assert "Karina" in out
    assert "já passou pelo nosso atendimento" in out
    assert "Dra. Karla" in out
    assert "TJDFT" in out
    assert "Como posso te ajudar hoje?" in out
    # NÃO deve afirmar consulta marcada
    assert "marcada" not in out.lower()
    assert "comparecer" not in out.lower()


def test_gera_saudacao_historica_sem_convenio():
    from voice_agent.responder import _gerar_saudacao_historica_c36
    ctx = {
        "name": "João",
        "known": {"medico": "Dr. Fabrício Freitas"},
    }
    out = _gerar_saudacao_historica_c36(ctx)
    assert "Dr. Fabrício" in out
    assert "marcada" not in out.lower()


def test_versao_prompt_bumpada():
    """Bumpa de versão obrigatória pra invalidar cache Anthropic SDK."""
    prompt = (
        Path(__file__).parent.parent
        / "voice_agent" / "knowledge_base" / "_MASTER_INSTRUCTION.md"
    ).read_text()
    assert "2026-06-17-c36-historico-nao-eh-consulta-ativa" in prompt


def test_secao_0ab_existe_no_prompt():
    prompt = (
        Path(__file__).parent.parent
        / "voice_agent" / "knowledge_base" / "_MASTER_INSTRUCTION.md"
    ).read_text()
    assert "0-AB. NUNCA TRATAR HISTÓRICO COMO CONSULTA ATIVA" in prompt
    assert "0AB.5. CONTRA-EXEMPLO REAL (lead 22071351 Karina" in prompt


def test_ativacao_inteligente_distingue_data_passada():
    """Quando 1.DIA CONSULTA está no passado, saudação muda pra histórico."""
    import time
    from voice_agent.ativacao_inteligente import gerar_saudacao_personalizada

    lead_passado = {
        "id": 22071351,
        "name": "Karina",
        "updated_at": "2026-06-17T10:00:00Z",
        "custom_fields": [
            {"field_id": 1255757, "field_name": "1.NOME PACIENTE",
             "values": [{"value": "Julia Akemi"}]},
            {"field_id": 1256257, "field_name": "MEDICOS",
             "values": [{"value": "Dra. Karla Delalibera"}]},
            {"field_id": 853206, "field_name": "CONVENIO",
             "values": [{"value": "TJDFT Pró-Saúde"}]},
            {"field_id": 1245125, "field_name": "UNIDADE",
             "values": [{"value": "Águas Claras"}]},
            # 1.DIA CONSULTA = 23/09/2025 (passado de ~9 meses)
            {"field_id": 1255723, "field_name": "1.DIA CONSULTA",
             "values": [{"value": 1758652200}]},
        ],
    }
    out = gerar_saudacao_personalizada(lead_passado)
    assert out["tipo"] == "personalizada"
    saudacao = out["saudacao"]
    # NÃO deve dizer "sua consulta era com" — histórico tem que ser explícito
    assert "já passou pelo nosso atendimento" in saudacao
    # NÃO deve afirmar consulta marcada
    assert "está marcada" not in saudacao.lower()


def test_ativacao_inteligente_data_futura_mantem_saudacao_original():
    """Se 1.DIA CONSULTA está no FUTURO (consulta ativa), saudação original."""
    import time
    from voice_agent.ativacao_inteligente import gerar_saudacao_personalizada

    futuro_ts = int(time.time()) + (7 * 86400)  # +7 dias
    lead_futuro = {
        "id": 99999,
        "name": "Maria",
        "updated_at": "2026-06-17T10:00:00Z",
        "custom_fields": [
            {"field_id": 1255757, "field_name": "1.NOME PACIENTE",
             "values": [{"value": "Pedro"}]},
            {"field_id": 1256257, "field_name": "MEDICOS",
             "values": [{"value": "Dra. Karla"}]},
            {"field_id": 1255723, "field_name": "1.DIA CONSULTA",
             "values": [{"value": futuro_ts}]},
        ],
    }
    out = gerar_saudacao_personalizada(lead_futuro)
    saudacao = out["saudacao"]
    # Mantém estrutura original (que será complementada pelo bloco
    # 🚨 ATENÇÃO MÁXIMA do responder.py quando ja_agendado=True)
    assert "Vamos seguir de onde paramos" in saudacao
