"""
Bug C-53 (11/07/2026) — Beatriz 16843614.

Lead em 5-AGENDADO com 1.DIA CONSULTA=07/08/2025 (passado). Lia recebeu
ja_agendado=True (corretamente, pois status é 5-AGENDADO) e ofereceu 2
horários NOVOS violando as regras de dia:

  1️⃣ Sexta-feira (07/08) às 10:00 — Karla Águas Claras → impossível (só ter/qui)
  2️⃣ Segunda-feira (17/08) às 10:00 — Karla Águas Claras → impossível (só ter/qui)

Causa: filtro `_viola_oferta_em_dia_nao_atendido` estava pulado quando
`ja_agendado=True` porque supunha que qualquer menção a data era
CONFIRMAÇÃO/REFERÊNCIA. Errado: quando texto tem padrão de OFERTA nova
(emoji 1️⃣ 2️⃣, "tenho N horários", "posso oferecer"), filtro DEVE rodar
mesmo com ja_agendado.

Fix duplo:
1. `_texto_parece_oferta_nova(text)` detecta padrão de OFERTA.
2. Loop de filtros C-31 roda se `not ja_agendado OR texto_parece_oferta`.

Também confirma que a tabela agora é carregada do JSON externo
`voice_agent/calendar_atendimento.json` (fonte única de verdade).
"""

from __future__ import annotations

from voice_agent.responder import (
    _carregar_calendario_atendimento,
    _texto_parece_oferta_nova,
    _viola_oferta_em_dia_nao_atendido,
)


# ---------- _texto_parece_oferta_nova ----------

def test_texto_beatriz_bug_original_e_oferta():
    """Texto exato que a Lia mandou pra Beatriz (11/07/2026)."""
    texto = (
        "Tenho 2 horários abertos com a Dra. Karla Delalibera, Águas Claras: "
        "1️⃣ Sexta-feira (07/08) às 10:00 "
        "2️⃣ Segunda-feira (17/08) às 10:00 "
        "Algum desses cabe pra você? Se preferir outro dia/horário, me diz que ajusto."
    )
    assert _texto_parece_oferta_nova(texto) is True


def test_confirmacao_nao_e_oferta():
    texto = (
        "Sua consulta com a Dra. Karla Delalíbera está confirmada para "
        "terça-feira, 12/08/2026 às 10:00 na unidade Águas Claras."
    )
    assert _texto_parece_oferta_nova(texto) is False


def test_referencia_historica_nao_e_oferta():
    texto = (
        "Vi aqui que a Beatriz teve consulta em 07/08/2025 com a Dra. Karla. "
        "Precisa remarcar ou está tudo certo?"
    )
    assert _texto_parece_oferta_nova(texto) is False


def test_resumo_pos_agendamento_nao_e_oferta():
    texto = (
        "Resumo do Atendimento:\n"
        "Paciente: Beatriz\n"
        "Médico: Dra. Karla Delalibera\n"
        "Data: 12/08/2026 às 10:00\n"
        "Unidade: Águas Claras"
    )
    assert _texto_parece_oferta_nova(texto) is False


def test_emoji_1_sozinho_ja_e_sinal_de_oferta():
    texto = "1️⃣ quarta-feira, 13/08 às 09:00 fica bom?"
    assert _texto_parece_oferta_nova(texto) is True


def test_posso_oferecer_e_oferta():
    texto = "Posso oferecer sexta-feira (15/08) às 14:00 pra você?"
    assert _texto_parece_oferta_nova(texto) is True


# ---------- _viola_oferta_em_dia_nao_atendido pega o caso Beatriz ----------

def test_karla_aguas_claras_sexta_bloqueado():
    """07/08/2026 = sexta-feira. Karla Águas Claras só atende ter/qui."""
    texto = "1️⃣ Sexta-feira (07/08/2026) às 10:00"
    ctx = {
        "known": {"medico": "Karla Delalibera", "unidade": "Águas Claras"},
    }
    resultado = _viola_oferta_em_dia_nao_atendido(texto, ctx)
    assert resultado is not None
    medico, data, dia = resultado
    assert medico == "karla"
    assert "07/08/2026" in data
    assert "sexta" in dia.lower()


def test_karla_aguas_claras_segunda_bloqueado():
    """17/08/2026 = segunda-feira. Karla Águas Claras só atende ter/qui."""
    texto = "2️⃣ Segunda-feira (17/08/2026) às 10:00"
    ctx = {
        "known": {"medico": "Karla Delalibera", "unidade": "Águas Claras"},
    }
    resultado = _viola_oferta_em_dia_nao_atendido(texto, ctx)
    assert resultado is not None


def test_karla_aguas_claras_terca_OK():
    """11/08/2026 = terça-feira. Karla Águas Claras atende → ok."""
    texto = "1️⃣ Terça-feira (11/08/2026) às 10:00"
    ctx = {
        "known": {"medico": "Karla Delalibera", "unidade": "Águas Claras"},
    }
    resultado = _viola_oferta_em_dia_nao_atendido(texto, ctx)
    assert resultado is None


def test_karla_aguas_claras_quinta_OK():
    """13/08/2026 = quinta-feira. Karla Águas Claras atende → ok."""
    texto = "1️⃣ Quinta-feira (13/08/2026) às 14:00"
    ctx = {
        "known": {"medico": "Karla Delalibera", "unidade": "Águas Claras"},
    }
    resultado = _viola_oferta_em_dia_nao_atendido(texto, ctx)
    assert resultado is None


def test_karla_asa_norte_quinta_bloqueado():
    """13/08/2026 = quinta-feira. Karla Asa Norte só atende seg/qua/sex."""
    texto = "1️⃣ Quinta-feira (13/08/2026) às 14:00"
    ctx = {
        "known": {"medico": "Karla Delalibera", "unidade": "Asa Norte"},
    }
    resultado = _viola_oferta_em_dia_nao_atendido(texto, ctx)
    assert resultado is not None


# ---------- Fonte de verdade agora é JSON externo ----------

def test_json_externo_carrega_com_sucesso():
    cal = _carregar_calendario_atendimento()
    assert cal["fonte"] == "json", (
        "Esperava carregar de voice_agent/calendar_atendimento.json, "
        f"caiu em {cal['fonte']}"
    )


def test_json_tem_karla_aguas_claras_ter_qui():
    cal = _carregar_calendario_atendimento()
    dias = cal["medicos_unidades"].get(("karla", "águas claras"))
    assert dias == {1, 3}, f"Esperava terça+quinta pra Karla AC, achou {dias}"


def test_json_tem_karla_asa_norte_seg_qua_sex():
    cal = _carregar_calendario_atendimento()
    dias = cal["medicos_unidades"].get(("karla", "asa norte"))
    assert dias == {0, 2, 4}, f"Esperava seg/qua/sex pra Karla AN, achou {dias}"


def test_json_tem_cidades_satelite():
    cal = _carregar_calendario_atendimento()
    cidades = cal["cidades_satelite_unidade"]
    assert cidades.get("taguatinga") == "Águas Claras"
    assert cidades.get("sobradinho") == "Asa Norte"
    assert cidades.get("ceilândia") == "Águas Claras"
    assert cidades.get("planaltina") == "Asa Norte"


# ---------- Regressão fim-de-semana (Priscila 06/06/2026) ----------

def test_karla_sabado_bloqueado_em_qualquer_unidade():
    """08/08/2026 = sábado. Karla NÃO atende em nenhuma unidade."""
    texto = "1️⃣ Sábado (08/08/2026) às 09:00"
    for unid in ("Asa Norte", "Águas Claras"):
        ctx = {"known": {"medico": "Karla Delalibera", "unidade": unid}}
        resultado = _viola_oferta_em_dia_nao_atendido(texto, ctx)
        assert resultado is not None, f"Sábado deveria bloquear em {unid}"


def test_karla_domingo_bloqueado_em_qualquer_unidade():
    """09/08/2026 = domingo. Karla NÃO atende."""
    texto = "1️⃣ Domingo (09/08/2026) às 10:00"
    for unid in ("Asa Norte", "Águas Claras"):
        ctx = {"known": {"medico": "Karla Delalibera", "unidade": unid}}
        resultado = _viola_oferta_em_dia_nao_atendido(texto, ctx)
        assert resultado is not None
