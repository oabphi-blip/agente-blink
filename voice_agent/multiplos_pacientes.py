"""
Bug C-113 (11/08/2026) — Múltiplos pacientes: bifurcar para 2 agendamentos.

Causa raiz: quando paciente dizia "para mim e minha filha" ou "2 filhos", a Lia
começava triagem para 1 paciente e no Medware gravava apenas 1 agendamento.
O segundo paciente ficava sem consulta e sem aviso.

Caso real: intent_classifier.py já extraía `n_patients` em primeira mensagem (C-81),
mas nenhum bypass deterministico usava esse campo. LLM recebia o contexto mas
frequentemente ignorava o segundo paciente.

Decisão arquitetural (P0):
  - Python detecta EXPLICITAMENTE múltiplos pacientes (regex + ctx.known.n_patients)
  - Bypass entrega mensagem avisando que precisamos de 2 agendamentos separados
  - Mensagem já inicia coleta do PRIMEIRO paciente (nome + data nasc)
  - Redis flag evita repetição da instrução a cada turno
  - Fail-open: exceção → None (pipeline continua; LLM decide)

Toggle: MULTIPLOS_PACIENTES_ATIVADO (default ON)

Limitação: C-113 detecta e bifurca para coleta sequencial.
O segundo agendamento é feito em turno subsequente (não bifurcação paralela).
Bifurcação paralela (gravar os 2 no Medware no mesmo turno) é C-113b — futuro.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Optional

log = logging.getLogger(__name__)

_ATIVADO = os.environ.get("MULTIPLOS_PACIENTES_ATIVADO", "1").strip() not in (
    "0", "false", "no", "off"
)

# Padrões que indicam MAIS DE 1 paciente na mesma conversa
_RE_MULTIPLOS = re.compile(
    r"""
    (?:
        # "para mim e minha(o)..." / "eu e minha filha" / "para nós"
        (?:para\s+)?(?:mim|eu|nós|nos|a\s+gente)\s+e\s+(?:minha?|meu|a|o)\s+\w+
    |
        # "minha filha e eu"
        (?:minha?|meu)\s+\w+\s+e\s+(?:eu|mim)
    |
        # "2 filhos" / "dois filhos" / "3 crianças"
        (?:2|3|4|dois?|três?|tr[eê]s|quatro?)\s+(?:filhos?|filhas?|crian[çc]as?|meninos?|meninas?|pacientes?)
    |
        # "minha filha e meu filho" / "minhas duas filhas" / "meus dois filhos"
        (?:minhas?|meus?)\s+(?:\w+\s+e\s+(?:minhas?|meus?)|dois?\s+\w+|duas?\s+\w+)
    |
        # "nós dois" / "as duas" / "os dois"
        (?:nós|a\s+gente)\s+(?:dois?|duas?)
    |
        # "para minha filha e para mim"
        (?:para\s+)?minha?\s+\w+\s+e\s+para\s+(?:mim|eu)
    |
        # "consulta para 2 / duas pessoas"
        (?:consulta|consultar|agendar|marcar)\s+(?:para\s+)?(?:2|dois?|duas?)\s+\w+
    |
        # "os dois" / "as duas" (quando precedido de verbo de agendamento)
        (?:agendar|marcar|consultar|quero)\s+(?:para\s+)?(?:os|as)\s+(?:dois?|duas?)
    )
    """,
    re.VERBOSE | re.IGNORECASE,
)

# Padrões que NÃO são múltiplos pacientes (falso positivo)
_RE_NAO_MULTIPLOS = re.compile(
    r"""
    # "segunda-feira" (dia da semana)
    segunda[- ]feira
    |
    # "20 minutos" / "2 horas" (tempo)
    \d+\s*(?:minuto|hora|dia|semana|mês|mes|ano)
    |
    # "cartão de 2 vias" (documento)
    (?:via|vias|cópias)
    """,
    re.VERBOSE | re.IGNORECASE,
)

# Flag Redis para não repetir instrução a cada turno
_FLAG_TTL = 7200  # 2 horas


def detectar_multiplos_pacientes(user_text: str, ctx: Optional[dict] = None) -> int:
    """Retorna número de pacientes detectados (0 = não detectado, 1 = só 1, ≥2 = múltiplos).

    Fontes (em ordem de prioridade):
    1. ctx.known.n_patients (injetado pelo intent_classifier C-81)
    2. regex no user_text
    """
    if ctx is not None:
        known = ctx.get("known") or {}  # read-only here — falsy-fallback OK
        n = known.get("n_patients") or known.get("multiplos_pacientes")
        if n and str(n).isdigit() and int(n) >= 2:
            return int(n)

    if not user_text or _RE_NAO_MULTIPLOS.search(user_text):
        return 0

    if _RE_MULTIPLOS.search(user_text):
        return 2  # padrão conservador: detectamos "múltiplos" sem saber exato

    return 0


def deve_orientar_multiplos_pacientes(
    ctx: Optional[dict],
    user_text: str = "",
    redis_client=None,
) -> Optional[str]:
    """Detecta múltiplos pacientes e entrega orientação de bifurcação.

    Retorna:
    - str: mensagem de orientação (bifurcar para 2 agendamentos)
    - None: não aplicável ou erro

    Fail-open: qualquer exceção → None.
    """
    if not _ATIVADO:
        return None
    if ctx is None:
        return None

    try:
        known = ctx.get("known")
        if known is None:
            known = {}
        lead_id = ctx.get("lead_id")

        # Verificar flag Redis (já orientamos neste turno → não repetir)
        if redis_client and lead_id:
            flag = redis_client.get(f"blink:c113_orientado:{lead_id}")
            if flag:
                return None

        # Detectar múltiplos pacientes
        n = detectar_multiplos_pacientes(user_text, ctx)
        if n < 2:
            return None

        # Se já coletamos o 2° agendamento, não orientar mais
        if known.get("segundo_agendamento_coletado"):
            return None

        # Montar mensagem de orientação
        nome = known.get("nome_paciente") or known.get("nome") or ""
        n_str = f"{n} " if n and n < 10 else ""
        pacientes_str = "os 2 pacientes" if n == 2 else f"os {n_str}pacientes"

        msg = (
            f"Ótimo! Vou agendar para {pacientes_str} — mas precisamos fazer "
            f"um agendamento de cada vez, porque cada paciente tem um cadastro "
            f"separado no sistema. 😊\n\n"
            f"**Vamos começar pelo primeiro paciente:**\n"
            f"Como se chama? E qual a data de nascimento?"
        )

        # Gravar flag Redis pra não repetir
        if redis_client and lead_id:
            try:
                redis_client.setex(f"blink:c113_orientado:{lead_id}", _FLAG_TTL, "1")
            except Exception as _re:
                log.warning("[C-113] Redis flag falhou: %s", _re)

        # Injetar em known para o pipeline saber
        known["multiplos_pacientes"] = n
        known["aguardando_primeiro_paciente"] = True
        log.info("[C-113] %d pacientes detectados lead=%s", n, lead_id)

        return msg

    except Exception as exc:
        log.warning("[C-113] deve_orientar_multiplos_pacientes falhou (fail-open): %s", exc)
        return None
