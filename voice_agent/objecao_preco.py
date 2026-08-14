"""
Bug C-107 (11/08/2026) — Quebra de objeção de preço.
Bug C-137 (14/08/2026) — "desconto" não estava no regex (lead 24328426 Alice Tavares).

Quando o paciente diz "está caro" / "encontrei mais barato" / "não tenho esse valor"
/ "queria um desconto", Python entrega script contextualizado que:

  1. Reconhece a objeção (sem dispensar)
  2. Ancora no VALOR da especialidade (diferencial Blink vs clínica genérica)
  3. Apresenta até 3 alternativas: parcelamento 2x, fila de encaixe, escalada humano
  4. Usa urgência clínica real quando presente no ctx (sintoma, tempo)

NUNCA:
  - Dismissar: "nosso preço é justo", "é o valor de mercado"
  - Oferecer desconto além do parcelamento sem aprovação humana
  - Fechar a conversa sem oferecer alternativa
  - Pressionar com urgência inventada

Caso C-107: lead 24436018 Gael, bebê 8 meses, conjuntivite 3 semanas.
Caso C-137: lead 24328426 Alice Tavares — "desconto" → agente respondeu 4x com stall
  "Anotado. Vou verificar os próximos horários disponíveis..." porque "desconto"
  não casava com nenhum padrão em _RE_OBJECAO.

Toggle: OBJECAO_PRECO_ATIVADO (default ON)
Fail-open: qualquer exceção → None (LLM continua normalmente)
"""

from __future__ import annotations

import logging
import os
import re
from typing import Optional

log = logging.getLogger(__name__)

_ATIVADO = os.environ.get("OBJECAO_PRECO_ATIVADO", "1").strip() not in (
    "0", "false", "no", "off"
)

# ─────────────────────────────────────────────────────────────────────────────
# Detecção de objeção de preço
# ─────────────────────────────────────────────────────────────────────────────

_RE_OBJECAO = re.compile(
    r"\b(?:"
    r"car(?:o|a)(?:\s+demais)?"
    r"|car[ií]ss?im[oa]"
    r"|muito\s+(?:caro|cara)"
    r"|(?:est[aá]|t[aá]|ficou|foi|[eé])\s+(?:caro|cara)"
    r"|sai(?:u)?\s+mais\s+barato"
    r"|mais\s+(?:barato|em\s+conta|acess[ií]vel|baratinho)"
    r"|encontrei\s+(?:por|mais\s+barato|por\s+menos|mais\s+em\s+conta)"
    r"|consegui\s+(?:mais\s+barato|por\s+menos|mais\s+em\s+conta|mais\s+acess[ií]vel)"
    r"|achei\s+(?:mais\s+barato|por\s+menos|caro)"
    r"|tem\s+(?:mais\s+barato|por\s+menos)"
    r"|n[aã]o\s+(?:tenho|tem)\s+(?:esse|este|tanto|esse\s+valor|esse\s+dinheiro|tant[oa]s?)"
    r"|(?:sem|fora\s+do)\s+or[çc]amento"
    r"|(?:valor|pre[çc]o)\s+(?:est[aá]\s+)?(?:alto|elevado|absurdo|salgado|pesado)"
    r"|n[aã]o\s+(?:consigo|d[aá])\s+(?:para\s+)?pagar"
    r"|sem\s+condi[çc][õo]es"
    r"|outr[ao]\s+(?:cl[ií]nica|lugar|local|m[eé]dic[oa])\s+(?:[eé]|custa|cobra|achei|encontrei|por)"
    r"|por\s+menos\s+(?:de\s+)?(?:R\$\s*)?\d{2,3}"
    # C-137: pedidos de desconto (lead 24328426 Alice Tavares)
    r"|descontos?"
    r"|promo[çc][aã]o"          # "promoção" (ç) e "promocao" (c)
    r"|pre[çc]o\s+(?:mais\s+)?especial"  # "preço especial" (ç) e "preco especial" (c)
    r"|valor\s+especial"
    r"|tem?\s+algum\s+desconto"
    r"|(?:consegue|d[aá])\s+(?:um\s+)?desconto"
    r")",
    re.IGNORECASE | re.UNICODE,
)

# C-137: detector específico de pedido de desconto (para routing interno)
_RE_DESCONTO_ESPECIFICO = re.compile(
    r"\b(?:descontos?|promo[çc][aã]o|pre[çc]o\s+(?:mais\s+)?especial|valor\s+especial"
    r"|tem?\s+algum\s+desconto|(?:consegue|d[aá])\s+(?:um\s+)?desconto)\b",
    re.IGNORECASE | re.UNICODE,
)

# Palavras que invalidam (contexto positivo — não é objeção)
_RE_NAO_OBJECAO = re.compile(
    r"\b(?:n[aã]o\s+(?:[eé]\s+)?caro|bom\s+pre[çc]o|pre[çc]o\s+(?:bom|justo|ok|[oó]timo)|aceito|topo|tudo\s+bem)\b",
    re.IGNORECASE,
)


def detectar_objecao_preco(user_text: str) -> bool:
    """Retorna True se o texto contém objeção de preço."""
    if not user_text:
        return False
    if _RE_NAO_OBJECAO.search(user_text):
        return False
    return bool(_RE_OBJECAO.search(user_text))


def detectar_desconto_especifico(user_text: str) -> bool:
    """C-137: True se o paciente está pedindo desconto/promoção (não 'está caro').

    Distinção importante: "desconto" é pedido de negociação — resposta diferente
    de "está caro" (price shock). Para desconto, pulamos a âncora de valor e
    vamos direto para as opções de pagamento flexível.
    """
    return bool(_RE_DESCONTO_ESPECIFICO.search(user_text or ""))


# ─────────────────────────────────────────────────────────────────────────────
# Âncoras clínicas — urgência real, nunca fabricada
# ─────────────────────────────────────────────────────────────────────────────

_RE_SEMANAS = re.compile(r"(\d+)\s*semanas?", re.IGNORECASE)
_RE_DIAS = re.compile(r"(\d+)\s*dias?", re.IGNORECASE)

_SINTOMAS_URGENTES = re.compile(
    r"\b(?:conjuntivite|irritação|vermelho|remel[ao]|inchado|dor|ardor|trauma|queda|pancada)\b",
    re.IGNORECASE,
)


def _ancoragem_clinica(ctx: Optional[dict]) -> str:
    """Retorna frase de âncora clínica se o ctx tiver sintoma/tempo relevante.

    Usa apenas dados que o paciente informou — nunca inventa urgência.
    """
    if not ctx:
        return ""
    known = ctx.get("known") or {}
    motivo = (known.get("motivo") or known.get("sintoma") or "").lower()
    notas = " ".join(
        n.get("text", "") for n in (ctx.get("notas") or []) if isinstance(n, dict)
    )
    texto_completo = motivo + " " + notas

    tem_sintoma = bool(_SINTOMAS_URGENTES.search(texto_completo))
    semanas_m = _RE_SEMANAS.search(texto_completo)
    dias_m = _RE_DIAS.search(texto_completo)

    if not tem_sintoma:
        return ""

    tempo = ""
    if semanas_m:
        n = int(semanas_m.group(1))
        if n >= 2:
            tempo = f"há {n} semanas"
    elif dias_m:
        n = int(dias_m.group(1))
        if n >= 10:
            tempo = f"há {n} dias"

    if tempo:
        return f" — e com o sintoma {tempo}, uma avaliação especializada faz diferença no diagnóstico correto"
    return " — e com esse sintoma, uma avaliação especializada é importante para o diagnóstico correto"


# ─────────────────────────────────────────────────────────────────────────────
# Bloco de alternativas de preço
# ─────────────────────────────────────────────────────────────────────────────

def _alternativas(parcela_1: int, parcela_2: int, tem_fila: bool = True) -> str:
    """Monta bloco de alternativas de pagamento."""
    linhas = [
        f"1️⃣ *Parcelamento:* 2x de R$ {parcela_2} no cartão sem juros",
    ]
    if tem_fila:
        linhas.append(
            "2️⃣ *Fila de encaixe:* quando abre uma vaga com prioridade, "
            "entramos em contato — valor diferenciado"
        )
        linhas.append(
            "3️⃣ *Falar com a equipe:* nossa atendente pode verificar "
            "condições especiais para o seu caso"
        )
    else:
        linhas.append(
            "2️⃣ *Falar com a equipe:* nossa atendente pode verificar "
            "condições especiais para o seu caso"
        )
    return "\n".join(linhas)


# C-137: resposta específica para pedido de desconto
# Diferença de "está caro": paciente não está em choque — está negociando.
# Não precisamos âncora de valor — vamos direto para opções de pagamento.

def _montar_resposta_desconto(nome: str, parcela_2: int) -> str:
    """Resposta para paciente que pediu desconto/promoção.

    Tom: amigável, honesto, propositivo. Não dismissar ("não fazemos desconto")
    nem prometer o que não pode ("vou verificar").
    Apresenta o parcelamento como equivalente funcional ao desconto.
    """
    saud = f"{nome}, " if nome else ""
    return (
        f"{saud}desconto direto no valor da consulta não temos — o valor já reflete "
        "a especialização e os exames incluídos. 😊\n\n"
        "Mas tenho duas opções que podem facilitar bastante:\n\n"
        f"1️⃣ *Parcelamento:* 2x de R$ {parcela_2} no cartão sem juros\n"
        "2️⃣ *Fila de encaixe:* quando abre uma vaga, entramos em contato "
        "com condições diferenciadas\n\n"
        "Qual dessas encaixa melhor para você?"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Templates de resposta por contexto
# ─────────────────────────────────────────────────────────────────────────────

def _objecao_karla_pediatrico(nome: str, ancoragem: str, idade: Optional[int]) -> str:
    faixa = "bebês e crianças"
    if idade is not None and idade <= 2:
        faixa = "bebês e recém-nascidos"
    elif idade is not None and idade <= 12:
        faixa = f"crianças até {idade} anos"

    alt = _alternativas(parcela_1=611, parcela_2=335)
    return (
        f"{nome}, entendo completamente.\n\n"
        f"A diferença de valor existe porque a Dra. Karla Delalíbera é especialista "
        f"em oftalmopediatria — ela tem equipamentos e protocolo específicos para {faixa}, "
        f"o que faz toda a diferença na qualidade do diagnóstico{ancoragem}. "
        f"Em clínicas gerais, nem sempre há essa especialização.\n\n"
        "A consulta inclui avaliação completa: acuidade visual, alinhamento dos olhos, "
        "fundo de olho e pressão ocular — tudo em um atendimento.\n\n"
        f"Para facilitar, tenho algumas opções:\n{alt}\n\n"
        "Qual dessas opções consegue encaixar melhor para vocês?"
    )


def _objecao_karla_apv(nome: str, ancoragem: str) -> str:
    alt = _alternativas(parcela_1=800, parcela_2=435, tem_fila=True)
    return (
        f"{nome}, entendo.\n\n"
        "A Avaliação do Processamento Visual com a Dra. Karla Delalíbera "
        "é uma consulta de 2 a 3 horas — bem diferente de uma consulta de rotina. "
        "Ela investiga a relação entre a visão e sintomas como cefaleia, cansaço ao ler "
        "e dificuldade de concentração, com testes que a maioria das clínicas não realiza.\n\n"
        f"Para facilitar:\n{alt}\n\n"
        "Qual opção funciona melhor para você?"
    )


def _objecao_karla_adulto(nome: str, ancoragem: str) -> str:
    alt = _alternativas(parcela_1=611, parcela_2=335)
    return (
        f"{nome}, entendo.\n\n"
        "A consulta com a Dra. Karla Delalíbera inclui avaliação completa — "
        "tonometria, mapeamento de retina, avaliação do alinhamento dos olhos "
        f"e orientação personalizada{ancoragem}. "
        "Tudo em um único atendimento, sem cobrar separado por exame.\n\n"
        f"Para facilitar:\n{alt}\n\n"
        "Qual dessas opções funciona melhor para você?"
    )


def _objecao_fabricio_catarata(nome: str, ancoragem: str) -> str:
    alt = _alternativas(parcela_1=445, parcela_2=235, tem_fila=True)
    return (
        f"{nome}, entendo.\n\n"
        "A avaliação do Dr. Fabrício Freitas inclui biometria ocular — "
        "que em muitos lugares é cobrada separadamente — além do diagnóstico completo "
        f"do grau de opacificação e planejamento cirúrgico quando indicado{ancoragem}. "
        "É uma consulta pensada para dar todas as respostas em um único atendimento.\n\n"
        f"Para facilitar:\n{alt}\n\n"
        "Qual opção encaixa melhor para você?"
    )


def _objecao_fabricio_geral(nome: str, ancoragem: str) -> str:
    alt = _alternativas(parcela_1=611, parcela_2=335)
    return (
        f"{nome}, entendo.\n\n"
        "A consulta com o Dr. Fabrício Freitas inclui avaliação completa da saúde "
        "ocular — tonometria, córnea, retina e orientação preventiva personalizada "
        f"para a sua faixa etária{ancoragem}. "
        "Tudo em um único atendimento.\n\n"
        f"Para facilitar:\n{alt}\n\n"
        "Qual dessas opções funciona melhor para você?"
    )


def _objecao_geral(nome: str, ancoragem: str) -> str:
    """Fallback quando médico não é conhecido."""
    alt = _alternativas(parcela_1=611, parcela_2=335)
    return (
        f"{nome}, entendo completamente.\n\n"
        "Na Blink, a consulta inclui avaliação completa — não cobramos separado "
        f"por cada exame realizado durante o atendimento{ancoragem}.\n\n"
        f"Para facilitar:\n{alt}\n\n"
        "Qual opção encaixa melhor para você?"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Função principal
# ─────────────────────────────────────────────────────────────────────────────

def deve_responder_objecao_preco(
    ctx: Optional[dict],
    user_text: str = "",
) -> Optional[str]:
    """Retorna resposta de quebra de objeção, ou None se não aplicável.

    Ativado quando:
      - Toggle ON
      - user_text contém objeção de preço (detectada por regex)
      - ctx.known.objecao_preco=True (injetado pelo step 13 do enriquecimento_ctx)

    Fail-open: qualquer exceção → None (LLM continua normalmente).
    """
    if not _ATIVADO:
        return None
    if ctx is None:
        return None

    try:
        # Verifica flag do enriquecimento OU detecta no user_text
        known = (ctx or {}).get("known") or {}
        tem_flag = known.get("objecao_preco", False)
        tem_regex = detectar_objecao_preco(user_text)

        if not tem_flag and not tem_regex:
            return None

        nome = _extrair_nome(ctx)

        # C-137: pedido de desconto recebe resposta diferente de "está caro"
        # Para desconto: pulamos âncora de valor, vamos direto para opções flexíveis
        if detectar_desconto_especifico(user_text) and not tem_flag:
            medico_raw_d = (known.get("medico") or "").lower()
            motivo_d = (known.get("motivo") or "").lower()
            # Valor da parcela depende da especialidade
            if "apv" in motivo_d or "processamento" in motivo_d:
                parcela_d = 435
            elif "catarata" in motivo_d or "fabr" in medico_raw_d:
                parcela_d = 235
            else:
                parcela_d = 335
            return _montar_resposta_desconto(nome, parcela_d)

        ancoragem = _ancoragem_clinica(ctx)

        medico_raw = (known.get("medico") or "").lower().strip()
        motivo = (known.get("motivo") or known.get("especialidade") or "").lower()
        idade = known.get("idade")
        pediatrico = known.get("contexto_pediatrico", False)

        karla = "karla" in medico_raw
        fabricio = "fabr" in medico_raw

        if karla:
            if any(k in motivo for k in ("apv", "processamento visual", "sdp", "prisma")):
                return _objecao_karla_apv(nome, ancoragem)
            if pediatrico or (idade is not None and idade < 18):
                return _objecao_karla_pediatrico(nome, ancoragem, idade)
            return _objecao_karla_adulto(nome, ancoragem)

        if fabricio:
            if "catarata" in motivo:
                return _objecao_fabricio_catarata(nome, ancoragem)
            return _objecao_fabricio_geral(nome, ancoragem)

        # Médico não identificado → fallback geral
        return _objecao_geral(nome, ancoragem)

    except Exception as exc:
        log.warning("[C-107] deve_responder_objecao_preco falhou: %s", exc)
        return None  # fail-open


# ─────────────────────────────────────────────────────────────────────────────
# Helper
# ─────────────────────────────────────────────────────────────────────────────

def _extrair_nome(ctx: Optional[dict]) -> str:
    if not ctx:
        return ""
    nome_completo = (ctx.get("name") or ctx.get("contact_name") or "").strip()
    if not nome_completo or nome_completo.lower() in ("você", "cliente", "lead"):
        return ""
    partes = nome_completo.split()
    return partes[0].capitalize() if partes else ""
