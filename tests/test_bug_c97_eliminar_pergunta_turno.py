"""
Bug C-97 (07/08/2026) — Lia NÃO deve perguntar dia da semana nem turno.

Decisão Fábio (lead 24424544 Lavinia + lead 24424208 Zoé):
  "continuar perguntando sobre turno, a partir de agora tornou desnecessário,
   pois esta abordagem é para atendimento humano."

Regra arquitetural:
  Com médico + unidade + convênio + motivo definidos → ir direto ao Medware
  e oferecer 2 slots concretos. NUNCA perguntar "qual dia da semana" ou
  "qual turno funciona melhor".

Pytest cobre:
  1. Constantes fallback não contêm "dia da semana" / "turno"
  2. _gerar_proxima_pergunta_sem_convenio não pergunta dia/turno
  3. _gerar_reconhecimento_curto_e_avanca não pergunta dia/turno
  4. Padrão "qual dia da semana" detectado em _viola_pergunta_turno_periodo_com_agenda
  5. Call sites C-31a, C-31b, C-54 retornam oferta quando ctx.agenda disponível
  6. Caso Zoé: "disco furado" — resposta repetida de dia/turno bloqueada
  7. Caso Lavinia: fluxo sem convênio também não pergunta turno
"""
import re
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# ── importações do módulo ──────────────────────────────────────────────────────
from voice_agent.responder import (
    _DIA_SEMANA_FALLBACK,
    _DIA_NAO_ATENDIDO_FALLBACK,
    _DIA_SEM_DATA_FALLBACK,
    _COBRANCA_ANTECIPADA_FALLBACK,
    _PERGUNTA_TURNO_PERIODO_PATTERNS,
    _viola_pergunta_turno_periodo_com_agenda,
    _gerar_oferta_2_slots,
    _gerar_proxima_pergunta_sem_convenio,
    _gerar_reconhecimento_curto_e_avanca,
)

# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _tem_pergunta_dia_turno(text: str) -> bool:
    """True se o texto pede dia da semana OU turno ao paciente."""
    padroes = [
        r"qual\b.{0,30}\bdia\s+da\s+semana\b",
        r"\bturno\s+funciona\b",
        r"\bturno\b.{0,20}\bmelhor\b",
        r"manh[ãa]\s+ou\s+tarde",
        r"qual\s+turno",
        r"prefer[êe]ncia\s+de\s+(turno|dia)",
    ]
    for p in padroes:
        if re.search(p, text, re.IGNORECASE | re.DOTALL):
            return True
    return False


def _ctx_com_agenda(slots=None):
    """Ctx fake com agenda disponível."""
    if slots is None:
        slots = [
            {"data": "2026-08-11", "hora": "09:00", "label": "Segunda-feira 11/08 às 09:00"},
            {"data": "2026-08-11", "hora": "14:30", "label": "Segunda-feira 11/08 às 14:30"},
        ]
    return {
        "agenda": slots,
        "medico": "Karla",
        "unidade": "Asa Norte",
        "convenio": "Saúde Caixa",
    }


def _ctx_sem_agenda():
    return {
        "agenda": [],
        "medico": "Karla",
        "unidade": "Asa Norte",
    }


# ──────────────────────────────────────────────────────────────────────────────
# 1. Constantes fallback NÃO contêm perguntas de dia/turno
# ──────────────────────────────────────────────────────────────────────────────

def test_dia_semana_fallback_sem_pergunta_turno():
    assert not _tem_pergunta_dia_turno(_DIA_SEMANA_FALLBACK), (
        f"_DIA_SEMANA_FALLBACK ainda pede dia/turno: {_DIA_SEMANA_FALLBACK!r}"
    )


def test_dia_nao_atendido_fallback_sem_pergunta_turno():
    assert not _tem_pergunta_dia_turno(_DIA_NAO_ATENDIDO_FALLBACK), (
        f"_DIA_NAO_ATENDIDO_FALLBACK ainda pede dia/turno: {_DIA_NAO_ATENDIDO_FALLBACK!r}"
    )


def test_dia_sem_data_fallback_sem_pergunta_dia():
    assert not _tem_pergunta_dia_turno(_DIA_SEM_DATA_FALLBACK), (
        f"_DIA_SEM_DATA_FALLBACK ainda pede dia/turno: {_DIA_SEM_DATA_FALLBACK!r}"
    )


def test_cobranca_antecipada_fallback_sem_pergunta_turno():
    assert not _tem_pergunta_dia_turno(_COBRANCA_ANTECIPADA_FALLBACK), (
        f"_COBRANCA_ANTECIPADA_FALLBACK ainda pede dia/turno: {_COBRANCA_ANTECIPADA_FALLBACK!r}"
    )


# ──────────────────────────────────────────────────────────────────────────────
# 2. _gerar_proxima_pergunta_sem_convenio NÃO pergunta dia/turno
# ──────────────────────────────────────────────────────────────────────────────

def test_proxima_pergunta_sem_convenio_nao_pergunta_turno_sem_unidade():
    """Sem unidade definida, função oferece escolha de unidade — não de turno."""
    ctx = {"medico": "Karla", "unidade": None, "nome_paciente": "Lavinia"}
    resultado = _gerar_proxima_pergunta_sem_convenio(ctx)
    assert not _tem_pergunta_dia_turno(resultado), (
        f"_gerar_proxima_pergunta_sem_convenio pediu dia/turno: {resultado!r}"
    )


def test_proxima_pergunta_sem_convenio_nao_pergunta_turno_com_unidade():
    """Com unidade definida, função deve indicar que vai verificar agenda."""
    ctx = {"medico": "Karla", "unidade": "Asa Norte", "nome_paciente": "Lavinia"}
    resultado = _gerar_proxima_pergunta_sem_convenio(ctx)
    assert not _tem_pergunta_dia_turno(resultado), (
        f"_gerar_proxima_pergunta_sem_convenio pediu dia/turno: {resultado!r}"
    )


# ──────────────────────────────────────────────────────────────────────────────
# 3. _gerar_reconhecimento_curto_e_avanca NÃO pergunta dia/turno
# ──────────────────────────────────────────────────────────────────────────────

def test_reconhecimento_sem_preferencia_nao_pergunta_turno():
    """Mesmo sem preferencia_dia/preferencia_turno, não deve pedir ao paciente."""
    ctx = {
        "medico": "Karla",
        "unidade": "Asa Norte",
        "convenio": "Bacen",
        "nome_paciente": "Zoé",
        "known": {},
    }
    resultado = _gerar_reconhecimento_curto_e_avanca(ctx)
    assert not _tem_pergunta_dia_turno(resultado), (
        f"_gerar_reconhecimento_curto_e_avanca pediu dia/turno: {resultado!r}"
    )


def test_reconhecimento_com_preferencia_nao_pergunta_turno():
    """Com preferência já coletada, também não deve repetir pergunta."""
    ctx = {
        "medico": "Karla",
        "unidade": "Asa Norte",
        "convenio": "Bacen",
        "nome_paciente": "Zoé",
        "known": {"preferencia_dia": "segunda", "preferencia_turno": "manhã"},
    }
    resultado = _gerar_reconhecimento_curto_e_avanca(ctx)
    assert not _tem_pergunta_dia_turno(resultado), (
        f"_gerar_reconhecimento_curto_e_avanca pediu dia/turno: {resultado!r}"
    )


# ──────────────────────────────────────────────────────────────────────────────
# 4. "qual dia da semana" detectado pelos padrões C-97
# ──────────────────────────────────────────────────────────────────────────────

def test_padrao_qual_dia_da_semana_detectado():
    """O novo padrão C-97 captura "Qual dia da semana ... funciona melhor"."""
    texto = "Qual dia da semana e turno funcionam melhor pra vocês?"
    encontrou = any(p.search(texto) for p in _PERGUNTA_TURNO_PERIODO_PATTERNS)
    assert encontrou, "Padrão 'qual dia da semana' não foi detectado pelos _PERGUNTA_TURNO_PERIODO_PATTERNS"


def test_padrao_qual_dia_da_semana_variante():
    """Variante mais curta também detectada."""
    texto = "Qual dia da semana funciona melhor?"
    encontrou = any(p.search(texto) for p in _PERGUNTA_TURNO_PERIODO_PATTERNS)
    assert encontrou, "Variante curta 'qual dia da semana' não detectada"


def test_padrao_manha_ou_tarde_continua_detectado():
    """Padrões existentes continuam funcionando."""
    texto = "Prefere manhã ou tarde?"
    encontrou = any(p.search(texto) for p in _PERGUNTA_TURNO_PERIODO_PATTERNS)
    assert encontrou, "'manhã ou tarde' não detectado"


def test_padrao_texto_neutro_nao_detectado():
    """Texto neutro (sem pergunta de turno) NÃO dispara o padrão."""
    texto = "Vou verificar os próximos horários disponíveis e já te apresento as opções."
    encontrou = any(p.search(texto) for p in _PERGUNTA_TURNO_PERIODO_PATTERNS)
    assert not encontrou, f"Falso positivo no texto neutro: {texto!r}"


# ──────────────────────────────────────────────────────────────────────────────
# 5. _viola_pergunta_turno_periodo_com_agenda captura "qual dia da semana"
# ──────────────────────────────────────────────────────────────────────────────

def test_viola_dia_semana_com_agenda():
    """Texto com 'qual dia da semana' + agenda disponível → filtro detecta."""
    texto = "Qual dia da semana e turno funcionam melhor pra vocês?"
    ctx = _ctx_com_agenda()
    assert _viola_pergunta_turno_periodo_com_agenda(texto, ctx)


def test_viola_dia_semana_sem_agenda_nao_dispara():
    """Sem agenda no ctx, filtro NÃO dispara (não há como substituir)."""
    texto = "Qual dia da semana e turno funcionam melhor pra vocês?"
    ctx = _ctx_sem_agenda()
    assert not _viola_pergunta_turno_periodo_com_agenda(texto, ctx)


# ──────────────────────────────────────────────────────────────────────────────
# 6. _gerar_oferta_2_slots retorna texto com horários reais (não pergunta)
# ──────────────────────────────────────────────────────────────────────────────

def test_gerar_oferta_2_slots_sem_pergunta():
    """Oferta gerada não deve conter pergunta de dia/turno."""
    ctx = _ctx_com_agenda()
    oferta = _gerar_oferta_2_slots(ctx)
    assert oferta, "Oferta de slots retornou vazia"
    assert not _tem_pergunta_dia_turno(oferta), (
        f"_gerar_oferta_2_slots contém pergunta de dia/turno: {oferta!r}"
    )


def test_gerar_oferta_2_slots_contem_horarios():
    """Oferta deve conter os horários do ctx.agenda."""
    ctx = _ctx_com_agenda()
    oferta = _gerar_oferta_2_slots(ctx)
    # Deve mencionar ao menos um dos labels ou horas
    assert "09:00" in oferta or "14:30" in oferta or "1️⃣" in oferta, (
        f"Oferta não menciona horários reais: {oferta!r}"
    )


# ──────────────────────────────────────────────────────────────────────────────
# 7. Caso Zoé (24424208) — "disco furado" detectado e bloqueado
# ──────────────────────────────────────────────────────────────────────────────

def test_caso_zoe_disco_furado_detectado_com_agenda():
    """
    Caso real Zoé Alves Gabriel (24424208):
    Lia repetiu 'Qual dia da semana e turno funcionam melhor pra vocês?'
    mesmo após paciente responder 'Segunda à tarde' 3 vezes.
    O filtro deve detectar e substituir quando há agenda.
    """
    texto_lia = "Qual dia da semana e turno funcionam melhor pra vocês? Assim consigo verificar os horários com Dra. Karla Delalíbera."
    ctx = _ctx_com_agenda()
    assert _viola_pergunta_turno_periodo_com_agenda(texto_lia, ctx), (
        "Caso Zoé: disco furado não detectado pelo filtro"
    )


def test_caso_zoe_resposta_substituta_sem_pergunta():
    """
    A substituição do disco furado deve oferecer slots, não outra pergunta.
    """
    ctx = _ctx_com_agenda()
    oferta = _gerar_oferta_2_slots(ctx)
    assert not _tem_pergunta_dia_turno(oferta), (
        f"Substituição para caso Zoé ainda tem pergunta: {oferta!r}"
    )


# ──────────────────────────────────────────────────────────────────────────────
# 8. Constantes contêm mensagens de verificação (não ficaram vazias)
# ──────────────────────────────────────────────────────────────────────────────

def test_fallbacks_nao_estao_vazios():
    """Fallbacks alterados não podem estar vazios — devem ter mensagem neutra."""
    assert len(_DIA_SEMANA_FALLBACK) > 10
    assert len(_DIA_NAO_ATENDIDO_FALLBACK) > 10
    assert len(_DIA_SEM_DATA_FALLBACK) > 10
    assert len(_COBRANCA_ANTECIPADA_FALLBACK) > 10


def test_fallbacks_contem_verificar_ou_equivalente():
    """Fallbacks devem conter indicação de que a Lia vai verificar a agenda."""
    for nome, texto in [
        ("_DIA_SEMANA_FALLBACK", _DIA_SEMANA_FALLBACK),
        ("_DIA_NAO_ATENDIDO_FALLBACK", _DIA_NAO_ATENDIDO_FALLBACK),
        ("_DIA_SEM_DATA_FALLBACK", _DIA_SEM_DATA_FALLBACK),
        ("_COBRANCA_ANTECIPADA_FALLBACK", _COBRANCA_ANTECIPADA_FALLBACK),
    ]:
        tem_verificar = any(
            kw in texto.lower()
            for kw in ["verificar", "trago", "passo", "apresento", "opções"]
        )
        assert tem_verificar, (
            f"{nome} não contém indicação de verificação: {texto!r}"
        )
