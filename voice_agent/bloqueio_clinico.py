"""
Bug C-57 (14/07/2026, lead 10934653 Melissa Vargas Nakatani).

Melissa tem 3+ no-shows/desmarcações em cima da hora. Dra. Karla escreveu
em 15/08/2025 (nota 27722655):

    "DRA KARLA: NÃO AGENDAR MAIS ESSA PACIENTE, JÁ DESMARCOU ALGUMAS
    VEZES EM CIMA DA HORA E NA ULTIMA VEZ NÃO COMPARECEU E NÃO AVISOU"

Stephany reforçou em 15/06/2026 (nota 28986672):

    "Caso a paciente não compareça no dia agendado, não agendar mais com
    a Dra. Karla a pedido da mesma."

**Mesmo assim** a Lia continuou respondendo/agendando essa paciente em
27/05/2026, 07/06/2026, 15/06/2026 e 14/07/2026.

Causa raiz arquitetural: pipeline não lia notas humanas antigas buscando
sinal explícito de bloqueio clínico da médica. Só olhava campo
`ATIVADO IA?` e etapa do funil, nenhum dos dois refletia a instrução
histórica da médica.

Fix: este módulo. Função `detectar_bloqueio_clinico(notas)` faz regex
nas notas humanas (created_by != 0) buscando padrões inequívocos de
proibição médica. Se encontra → agente é desativado permanentemente pra
esse lead.

Chamado por `voice_agent/kommo.py::agent_paused_for_lead` como regra 3,
depois da regra 1 (etapa humana) e regra 2 (humano-escreveu-recente).
"""

from __future__ import annotations

import re
from typing import Iterable, Optional


# Padrões que indicam ordem médica de NÃO agendar mais essa paciente.
# Case-insensitive. Precisam ser inequívocos — nada de "não confirmou"
# ou "não veio hoje", tem que ser proibição de agendamento futuro.
_PADROES_BLOQUEIO = [
    # Ordens diretas da médica ou equipe
    re.compile(r"n[aã]o\s+agendar\s+mais\s+(?:essa|esse|est[ea])?\s*paciente", re.IGNORECASE),
    re.compile(r"n[aã]o\s+agendar\s+mais\s+com\s+(?:a\s+)?dra?\.?\s*karla", re.IGNORECASE),
    re.compile(r"n[aã]o\s+agendar\s+mais\s+com\s+(?:o\s+)?dr\.?\s*fabr[ií]cio", re.IGNORECASE),
    re.compile(r"n[aã]o\s+agendar\s+mais\s+essa", re.IGNORECASE),
    re.compile(r"proibido\s+(?:re)?agendar", re.IGNORECASE),
    re.compile(r"paciente\s+bloquead[ao]", re.IGNORECASE),
    re.compile(r"bloquear\s+(?:agendamento|paciente)", re.IGNORECASE),
    # Frase canônica da Dra. Karla
    re.compile(r"dra\s+karla:?\s+n[aã]o\s+agendar\s+mais", re.IGNORECASE),
    # Variantes mais brandas mas com sinal claro
    re.compile(r"a\s+pedido\s+da\s+(?:pr[oó]pria\s+)?m[eé]dica\s*[,.]?\s*n[aã]o\s+agendar", re.IGNORECASE),
]


def _texto_da_nota(nota: dict) -> str:
    """Extrai o texto de uma nota Kommo (tolerante a formato)."""
    if not isinstance(nota, dict):
        return ""
    return str(nota.get("text") or nota.get("params", {}).get("text") or "")


def _eh_nota_humana(nota: dict) -> bool:
    """Nota humana = created_by != 0 (0 = robô/serviço Kommo)."""
    if not isinstance(nota, dict):
        return False
    return int(nota.get("created_by") or 0) > 0


def detectar_bloqueio_clinico(
    notas: Optional[Iterable[dict]],
) -> Optional[str]:
    """Varre notas HUMANAS do lead procurando ordem de bloqueio clínico.

    Retorna o trecho da nota que casou (pra log/auditoria) ou None.

    Regras:
    - Só considera nota humana (created_by != 0). Ignora nota de bot/Lia
      pra evitar falso positivo (se Lia disser "vou anotar não agendar
      mais" numa mensagem antiga, isso NÃO é ordem médica).
    - Não tem decay temporal. Uma vez que médica pediu pra não agendar,
      vale pra sempre até médica remover explicitamente. Se paciente
      quiser voltar, equipe humana desbloqueia manualmente.
    - Case-insensitive.
    - Retorna 1ª ocorrência (não precisa varrer todas).
    """
    if not notas:
        return None
    for nota in notas:
        if not _eh_nota_humana(nota):
            continue
        texto = _texto_da_nota(nota)
        if not texto:
            continue
        for padrao in _PADROES_BLOQUEIO:
            match = padrao.search(texto)
            if match:
                # Retorna trecho de contexto (30 chars antes + match + 30 depois)
                inicio = max(0, match.start() - 30)
                fim = min(len(texto), match.end() + 30)
                return texto[inicio:fim].strip()
    return None


def paciente_bloqueado(notas: Optional[Iterable[dict]]) -> bool:
    """Wrapper booleano. True se detectar_bloqueio_clinico encontrou algo."""
    return detectar_bloqueio_clinico(notas) is not None
