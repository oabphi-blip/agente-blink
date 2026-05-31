"""Validação de nome civil completo do paciente.

Origem: bug do lead 24048691 (30/05/2026). A Lia perguntou "qual é o seu
nome completo?", paciente respondeu "Marcela", Lia gravou direto em
`1.NOME PACIENTE` sem aplicar a regra 5.2-B.

Esta regra está documentada no `_MASTER_INSTRUCTION.md` seção 5.2.4. Esta
implementação é o gatilho de código que a Lia chama ANTES de gravar
`1.NOME PACIENTE` (em kommo.py:update_lead_fields) — se devolver
NomeStatus.INCOMPLETO ou NomeStatus.SO_PRIMEIRO_NOME, o pipeline NÃO grava
e pede o nome completo novamente.

Regra resumida (5.2-B + 5.2.4):
- Tokens ≤ 2 letras → iniciais (ex.: "Renata C B E M Coelho").
- Conectivos minúsculos não contam: de, da, do, das, dos, e.
- Nome completo = pelo menos 3 tokens "fortes" (≥ 3 letras, sem ser conectivo).
- 2 tokens fortes → SO_SOBRENOME_FALTANDO (pedir mais uma vez).
- 1 token forte → SO_PRIMEIRO_NOME (caso "Marcela").
- Vazio → VAZIO.
"""
from __future__ import annotations

from enum import Enum

CONECTIVOS = {"de", "da", "do", "das", "dos", "e"}


class NomeStatus(str, Enum):
    COMPLETO = "completo"
    INCOMPLETO_COM_INICIAIS = "incompleto_com_iniciais"
    SO_SOBRENOME_FALTANDO = "so_sobrenome_faltando"
    SO_PRIMEIRO_NOME = "so_primeiro_nome"
    VAZIO = "vazio"


def _tokens(nome: str) -> list[str]:
    if not nome:
        return []
    # Remove pontuação simples comum em nomes
    limpo = nome.replace(".", " ").replace(",", " ")
    return [t for t in limpo.split() if t.strip()]


def _eh_conectivo(token: str) -> bool:
    return token.lower() in CONECTIVOS


def _eh_inicial(token: str) -> bool:
    """Token com ≤ 2 letras (sem contar pontos) é considerado inicial."""
    letras = "".join(c for c in token if c.isalpha())
    return 0 < len(letras) <= 2


def _tokens_fortes(tokens: list[str]) -> list[str]:
    """Tokens com ≥ 3 letras alfabéticas, excluindo conectivos."""
    fortes = []
    for t in tokens:
        if _eh_conectivo(t):
            continue
        letras = "".join(c for c in t if c.isalpha())
        if len(letras) >= 3:
            fortes.append(t)
    return fortes


def avaliar_nome_paciente(nome: str | None) -> NomeStatus:
    """Classifica o nome recebido do paciente.

    Status COMPLETO ⇒ Lia pode gravar.
    Qualquer outro ⇒ Lia pergunta novamente com a frase apropriada.
    """
    if not nome or not nome.strip():
        return NomeStatus.VAZIO

    toks = _tokens(nome)
    if not toks:
        return NomeStatus.VAZIO

    # Detecta iniciais — pelo menos um token não-conectivo com ≤ 2 letras.
    iniciais = [t for t in toks if not _eh_conectivo(t) and _eh_inicial(t)]
    if iniciais:
        return NomeStatus.INCOMPLETO_COM_INICIAIS

    fortes = _tokens_fortes(toks)
    if len(fortes) >= 3:
        return NomeStatus.COMPLETO
    if len(fortes) == 2:
        return NomeStatus.SO_SOBRENOME_FALTANDO
    if len(fortes) == 1:
        return NomeStatus.SO_PRIMEIRO_NOME
    return NomeStatus.VAZIO


def mensagem_pedido_complemento(status: NomeStatus, primeiro_nome: str = "") -> str:
    """Frase que a Lia envia quando o nome está incompleto.

    Tom segue a regra 5.2.4 do prompt. Não inventa, só preenche o template.
    """
    saudacao = f"Obrigada, {primeiro_nome}!" if primeiro_nome else "Obrigada!"
    if status == NomeStatus.SO_PRIMEIRO_NOME:
        return (
            f"{saudacao} Pra eu registrar no sistema, preciso do nome civil "
            f"completo da paciente — nome, nome do meio (se houver) e "
            f"sobrenomes. Pode me confirmar?"
        )
    if status == NomeStatus.SO_SOBRENOME_FALTANDO:
        return (
            f"{saudacao} Pra ficar completo no cadastro, me confirma o "
            f"sobrenome restante da paciente?"
        )
    if status == NomeStatus.INCOMPLETO_COM_INICIAIS:
        return (
            f"{saudacao} Pro cadastro ficar correto, preciso de cada nome "
            f"do meio escrito por inteiro (sem iniciais). Pode me passar?"
        )
    return (
        "Pra eu seguir com o agendamento, preciso do nome civil completo "
        "da paciente — pode me passar?"
    )
