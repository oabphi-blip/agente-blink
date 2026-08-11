"""
Bug C-114 (11/08/2026) — Política de comparecimento: sinal 50% pós-conclusão de agendamento.

Analogia "poltrona de avião": depois que o agendamento está confirmado
(conclusão enviada com dados corretos), o paciente PARTICULAR recebe 2 opções:

    1️⃣  Reserva garantida → Pix de 50% do valor da consulta
    2️⃣  Fila de encaixe → sem pagamento, mas sem exclusividade no horário

Tom: leve, incentivo ao comparecimento, não coercitivo.
Momento: logo após o paciente confirmar os dados da conclusão de agendamento.

Trigger (todos devem ser verdadeiros):
    1. user_text confirma dados: "sim", "correto", "confirmo", "tudo certo", etc.
    2. Última mensagem outbound ERA uma conclusão de agendamento
       (ctx.known.ultima_msg_outbound contém data/hora OU ctx.ja_agendado==True)
    3. Convênio = PARTICULAR (Não se aplica / "" / sem convênio)
    4. Redis flag blink:c114_sinal_solicitado:{lead_id} NÃO ativo (TTL 24h)

Valores (50% da tabela oficial):
    Karla + APV/SDP/Processamento Visual → consulta R$ 800,00 → sinal R$ 400,00
    Karla + outros (rotina/oftalmopediatria/estrabismo) → R$ 611,00 → R$ 305,50
    Fabrício + catarata → R$ 445,00 → R$ 222,50
    Fabrício + outros → R$ 611,00 → R$ 305,50

Chaves Pix (allowlist oficial):
    Asa Norte:     karladelaliberaoftalmo@gmail.com
    Águas Claras:  52.303.729/0001-30

Fail-open: exceção → None (pipeline continua, LLM decide).
Toggle: POLITICA_COMPARECIMENTO_ATIVADO (default ON)
Rollback: POLITICA_COMPARECIMENTO_ATIVADO=0 em Easypanel → Implantar.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Optional

log = logging.getLogger(__name__)

_ATIVADO = os.environ.get("POLITICA_COMPARECIMENTO_ATIVADO", "1").strip() not in (
    "0", "false", "no", "off"
)

_FLAG_TTL = 86400  # 24 horas

# ──────────────────────────────────────────────────────────────────────────────
# Enum IDs do campo "A FAZER" (Kommo field_id 1259312) para atualização
# pelo pipeline quando paciente responde à oferta C-114.
# C-114 (11/08/2026): adicionado "Fila Encaixe" enum_id 927866.
# ──────────────────────────────────────────────────────────────────────────────
A_FAZER_FIELD_ID = 1259312
A_FAZER_ENCAIXE_ENUM_ID = 927023       # paciente pagou sinal → reserva garantida
A_FAZER_FILA_ENCAIXE_ENUM_ID = 927866  # paciente escolheu fila sem pagamento

# Redis flag: "blink:c114_opcao_fila:{lead_id}" (TTL 86400)
# Pipeline lê para saber que paciente escolheu Fila Encaixe → seta "A FAZER"
REDIS_KEY_OPCAO_FILA = "blink:c114_opcao_fila:{lead_id}"

# Padrões que indicam que o paciente escolheu opção 2 (fila / sem pagamento)
import re as _re
RE_ESCOLHEU_FILA = _re.compile(
    r"""
    \b
    (?:
        2[️⃣]?\s*\.?
        | opcao\s*2
        | op[çc][aã]o\s*2
        | fila\b
        | encaixe\b
        | sem\s+pagamento
        | sem\s+pagar
        | n[aã]o\s+vou\s+pagar
        | pref[eo]ro?\s+(?:a\s+)?fila
    )
    """,
    _re.VERBOSE | _re.IGNORECASE,
)

# Padrões que indicam que o paciente escolheu opção 1 (reserva / pagar)
RE_ESCOLHEU_RESERVA = _re.compile(
    r"""
    \b
    (?:
        1[️⃣]?\s*\.?
        | opcao\s*1
        | op[çc][aã]o\s*1
        | reserva\b
        | garantid[ao]\b
        | vou\s+pagar
        | vou\s+fazer\s+(?:o\s+)?pix
        | mand[ao]\s+(?:o\s+)?comprovante
        | comprovante\b
    )
    """,
    _re.VERBOSE | _re.IGNORECASE,
)

# ──────────────────────────────────────────────────────────────────────────────
# Chaves Pix por unidade (allowlist — qualquer outra é alucinação)
# ──────────────────────────────────────────────────────────────────────────────
_PIX_POR_UNIDADE: dict[str, str] = {
    "asa norte":    "karladelaliberaoftalmo@gmail.com",
    "águas claras": "52.303.729/0001-30",
    "aguas claras": "52.303.729/0001-30",
    "ac":           "52.303.729/0001-30",  # abreviação comum
    "an":           "karladelaliberaoftalmo@gmail.com",
}

_PIX_FALLBACK = "karladelaliberaoftalmo@gmail.com"  # Asa Norte como padrão seguro

# ──────────────────────────────────────────────────────────────────────────────
# Convênios que indicam PARTICULAR (sem cobertura de plano)
# ──────────────────────────────────────────────────────────────────────────────
_CONVENIOS_PARTICULAR: frozenset[str] = frozenset({
    "",
    "não se aplica",
    "nao se aplica",
    "sem convênio",
    "sem convenio",
    "particular",
    "n/a",
    "na",
    "nenhum",
    "sem plano",
})

# ──────────────────────────────────────────────────────────────────────────────
# Padrões de confirmação de dados ("sim dados corretos", "tudo ok", etc.)
# ──────────────────────────────────────────────────────────────────────────────
_RE_CONFIRMA_DADOS = re.compile(
    r"""
    (?:^|\b)
    (?:
        # Afirmações diretas
        sim\b
        | ok\b
        | certo[sa]?\b
        | correto[sa]?\b
        | confirm[oaei]\b
        | confirmado\b
        | isso\b
        | exato\b
        | perfeito\b
        | ótimo\b
        | otimo\b
        | correto\b
        # "tudo certo/ok/correto"
        | tudo\s+(?:certo|ok|correto|corretos|bom|certa)
        # "está certo / tá certo / ta ok"
        | t[áa]\s+(?:certo|ok|bom|correto)
        | est[áa]\s+(?:certo|ok|bom|correto)
        # "dados corretos" / "dados ok"
        | dados\s+(?:corretos?|ok|certos?)
        # "1. Tudo Correto" (botão Salesbot)
        | [1１]\s*\.?\s*tudo\s+correto
        # emoji de confirmação
        | ✅
        | 👍
    )
    """,
    re.VERBOSE | re.IGNORECASE,
)

# ──────────────────────────────────────────────────────────────────────────────
# Padrões que indicam última outbound era uma conclusão de agendamento
# ──────────────────────────────────────────────────────────────────────────────
_RE_CONCLUSAO_OUTBOUND = re.compile(
    r"""
    (?:
        # Data + hora do slot (DD/MM às HH:MM)
        \d{2}/\d{2}(?:/\d{2,4})?\s+(?:às|as|-)\s*\d{2}[h:]\d{2}
        |
        # Emoji de confirmação + médico/agend
        (?:✅|📅|🏥)\s*(?:agend|confirm|reserv)
        |
        # Template conclusão canônico
        (?:agendamento\s+confirmado|consulta\s+agendada|reserva\s+confirmada)
        |
        # "Os dados estão corretos?" (pergunta de confirmação pré-conclusão)
        dados?\s+est[aã]o\s+correto
        | os\s+dados?\s+abaixo
        | confirme?\s+os\s+dados?
    )
    """,
    re.VERBOSE | re.IGNORECASE,
)


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _e_particular(ctx: dict) -> bool:
    """Retorna True somente se convênio indica explicitamente particular."""
    known = ctx.get("known")
    if known is None:
        return False
    convenio = (known.get("convenio") or "").lower().strip()
    return convenio in _CONVENIOS_PARTICULAR


def _ultima_msg_era_conclusao(ctx: dict) -> bool:
    """Verifica se o último outbound da Lia era conclusão de agendamento.

    Aceita:
    - ctx.known.ultima_msg_outbound com padrão de conclusão
    - ctx.ja_agendado == True (Medware já gravou, logo havia conclusão)
    """
    known = ctx.get("known")
    if known is None:
        return False

    # Verificar última outbound
    ultima = (known.get("ultima_msg_outbound") or "").strip()
    if ultima and _RE_CONCLUSAO_OUTBOUND.search(ultima):
        return True

    # Fallback: lead marcado como ja_agendado
    if ctx.get("ja_agendado") or known.get("ja_agendado"):
        return True

    return False


def _pix_da_unidade(ctx: dict) -> str:
    """Retorna chave Pix correta pela unidade do lead."""
    known = (ctx.get("known") or {})
    unidade = (known.get("unidade") or "").lower().strip()
    for key, pix in _PIX_POR_UNIDADE.items():
        if key in unidade:
            return pix
    return _PIX_FALLBACK


def _calcular_sinal(ctx: dict) -> tuple[str, str, str]:
    """Retorna (valor_sinal_fmt, valor_consulta_fmt, medico_nome).

    Baseado em médico + especialidade/motivo do ctx.known.
    """
    known = (ctx.get("known") or {})
    medico_raw = (known.get("medico") or known.get("medicos") or "").lower()
    especialidade = (
        known.get("especialidade")
        or known.get("motivo")
        or known.get("motivo_consulta")
        or ""
    ).lower()

    _apv = {"apv", "sdp", "processamento", "prisma", "postural", "visual"}
    _catarata = {"catarata", "catarat"}

    if "karla" in medico_raw or "delalíbera" in medico_raw or "delalibera" in medico_raw:
        nome = "Dra. Karla Delalíbera"
        if any(k in especialidade for k in _apv):
            return "R$ 400,00", "R$ 800,00", nome
        return "R$ 305,50", "R$ 611,00", nome

    if "fabrício" in medico_raw or "fabricio" in medico_raw or "freitas" in medico_raw:
        nome = "Dr. Fabrício Freitas"
        if any(k in especialidade for k in _catarata):
            return "R$ 222,50", "R$ 445,00", nome
        return "R$ 305,50", "R$ 611,00", nome

    # Fallback: Karla rotina
    return "R$ 305,50", "R$ 611,00", "Dra. Karla Delalíbera"


# ──────────────────────────────────────────────────────────────────────────────
# Função principal
# ──────────────────────────────────────────────────────────────────────────────

def detectar_escolha_c114(
    user_text: str,
    lead_id: int | None = None,
    redis_client=None,
) -> str | None:
    """Detecta se paciente respondeu à oferta C-114 escolhendo fila ou reserva.

    Deve ser chamada pelo pipeline APÓS C-114 ter sido disparado
    (flag blink:c114_sinal_solicitado:{lead_id} ativo).

    Returns:
        "fila"    — paciente escolheu Fila de Encaixe (opção 2)
        "reserva" — paciente escolheu Reserva Garantida (opção 1)
        None      — não detectado / C-114 não havia sido disparado
    """
    if not user_text:
        return None

    # Verificar se C-114 estava ativo para este lead
    if redis_client and lead_id:
        if not redis_client.get(f"blink:c114_sinal_solicitado:{lead_id}"):
            return None  # C-114 não havia sido disparado → não interpretar

    if RE_ESCOLHEU_FILA.search(user_text):
        # Gravar flag que o paciente escolheu fila (para pipeline setar A FAZER)
        if redis_client and lead_id:
            try:
                redis_client.setex(
                    REDIS_KEY_OPCAO_FILA.format(lead_id=lead_id), _FLAG_TTL, "1"
                )
            except Exception:
                pass
        return "fila"

    if RE_ESCOLHEU_RESERVA.search(user_text):
        return "reserva"

    return None


def deve_solicitar_sinal_particular(
    ctx: Optional[dict],
    user_text: str = "",
    redis_client=None,
) -> Optional[str]:
    """Detecta confirmação de dados pós-agendamento particular → solicita 50% sinal.

    Returns:
        str: mensagem com 2 opções (Pix reserva garantida OU fila encaixe)
        None: não aplicável, convênio ativo, ou erro (fail-open)
    """
    if not _ATIVADO:
        return None
    if ctx is None or not user_text:
        return None

    try:
        known = ctx.get("known")
        if known is None:
            known = {}
        lead_id = ctx.get("lead_id")

        # 1. Redis flag: já solicitamos sinal neste período → não repetir
        if redis_client and lead_id:
            flag = redis_client.get(f"blink:c114_sinal_solicitado:{lead_id}")
            if flag:
                return None

        # 2. Só para pacientes PARTICULAR (sem convênio aceito)
        if not _e_particular(ctx):
            return None

        # 3. user_text deve confirmar dados do agendamento
        if not _RE_CONFIRMA_DADOS.search(user_text):
            return None

        # 4. Última outbound era conclusão de agendamento
        #    (garante que o "sim" é em resposta à conclusão, não a qualquer pergunta)
        if not _ultima_msg_era_conclusao(ctx):
            return None

        # Calcular valores e chave Pix
        valor_sinal, valor_consulta, medico_nome = _calcular_sinal(ctx)
        chave_pix = _pix_da_unidade(ctx)

        # Montar mensagem com tom leve (incentivo, não cobrança agressiva)
        msg = (
            f"Ótimo! 😊\n\n"
            f"Para garantir seu horário com exclusividade, temos duas opções:\n\n"
            f"1️⃣ *Reserva garantida* — Pix de {valor_sinal} agora.\n"
            f"Chave Pix: `{chave_pix}`\n"
            f"Com o comprovante o horário fica assegurado para você. "
            f"Se precisar cancelar, avise com pelo menos 24h de antecedência 🙂\n\n"
            f"2️⃣ *Fila de encaixe* — Mantemos seu interesse sem pagamento, "
            f"mas o horário pode ser ocupado por outro paciente enquanto aguardamos.\n\n"
            f"Qual prefere?"
        )

        # Gravar Redis flag (TTL 24h — não repetir se paciente mandar outro "sim")
        if redis_client and lead_id:
            try:
                redis_client.setex(
                    f"blink:c114_sinal_solicitado:{lead_id}", _FLAG_TTL, "1"
                )
            except Exception as _re:
                log.warning("[C-114] Redis flag falhou: %s", _re)

        log.info(
            "[C-114] Sinal particular solicitado — lead=%s valor=%s pix=%s",
            lead_id, valor_sinal, chave_pix,
        )
        return msg

    except Exception as exc:
        log.warning("[C-114] deve_solicitar_sinal_particular falhou (fail-open): %s", exc)
        return None
