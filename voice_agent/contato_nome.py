"""
Validador de nome de contato (responsável que está digitando no WhatsApp).

Origem: Bug C-20 (Fábio 10/06/2026).

No batch ferias julho, leads 12871624 (Wendel) e 20901861 (Fábio Jr.) tinham
nome do contato cadastrado no Kommo como "Inbra" e vazio (caindo no fallback
"Você"). Mensagem foi entregue mas saudação ficou esquisita.

REGRA Fábio:
  Quando o nome do contato é INVÁLIDO, Lia NÃO usa o nome do paciente como
  saudação genérica. Em vez disso, pergunta de forma natural pra descobrir
  COM QUEM está falando — e usa esse nome dali em diante.

Quem é o "CONTATO":
  É a pessoa que está digitando no WhatsApp — geralmente o RESPONSÁVEL pelo
  paciente (mãe, pai, filha do paciente idoso). Diferente do PACIENTE.

Quando o nome é inválido:
  - vazio / None
  - exatamente os fallbacks técnicos ("Você", "Olá", "Oi")
  - rótulos genéricos ("Cliente", "Paciente", "Contato", "Usuário")
  - nomes técnicos do CRM/sistema ("Inbra", "Test", "Teste", "Lia")
  - só números ou só símbolos
  - menor que 2 caracteres
  - nome igual a "555..." (telefone formatado como nome)
"""

from __future__ import annotations

import re
import unicodedata
from typing import Final

# ---------------------------------------------------------------------------
# Tokens proibidos (palavras inteiras)
# ---------------------------------------------------------------------------

_FALLBACKS_TECNICOS = {
    "voce", "oi", "ola", "ei",
    "cliente", "paciente", "contato", "usuario", "usuaria",
    "responsavel", "lead",
    "lia", "blink", "ariany", "stephany", "karla", "fabricio",  # nomes da equipe
    "test", "teste", "demo", "exemplo",
    "inbra",  # observado no Kommo lead 12871624
    "none", "null", "nan",
}

_RE_SO_NUMEROS_OU_SIMBOLOS: Final = re.compile(r"^[\W\d_]+$", flags=re.UNICODE)
_RE_TELEFONE_BR: Final = re.compile(r"^55\d{10,11}$")


def _normalizar(nome: str) -> str:
    nfkd = unicodedata.normalize("NFD", nome.strip().lower())
    return "".join(c for c in nfkd if unicodedata.category(c) != "Mn")


def nome_contato_invalido(nome: str | None) -> bool:
    """Retorna True quando o nome do contato NÃO serve pra saudação natural."""
    if nome is None:
        return True
    n = nome.strip()
    if not n or len(n) < 2:
        return True
    if _RE_SO_NUMEROS_OU_SIMBOLOS.match(n):
        return True
    # Telefone formatado como nome
    nsem = re.sub(r"[\s\-\+\(\)]", "", n)
    if _RE_TELEFONE_BR.match(nsem):
        return True
    # Token único nos fallbacks técnicos (case/acento insensitive)
    tokens = _normalizar(n).split()
    if not tokens:
        return True
    # Primeiro token sozinho proibido E nome inteiro só tem 1 token
    if len(tokens) == 1 and tokens[0] in _FALLBACKS_TECNICOS:
        return True
    # OU nome inteiro normalizado match algum fallback
    nome_norm = _normalizar(n)
    if nome_norm in _FALLBACKS_TECNICOS:
        return True
    return False


# ---------------------------------------------------------------------------
# Pergunta amigável pra coletar o nome
# ---------------------------------------------------------------------------

PERGUNTA_PADRAO_NOME_CONTATO: Final = (
    "Olá! 😊 Pra te chamar pelo nome certo, "
    "com quem estou falando, por favor?"
)

PERGUNTA_PARA_RESPONSAVEL: Final = (
    "Antes de tudo, com quem tenho o prazer de falar? "
    "(Pra eu te chamar pelo nome certo na conversa.) 😊"
)


def pergunta_nome_contato(*, contexto_paciente_menor: bool = False) -> str:
    """Retorna a frase pronta pra Lia perguntar o nome do contato.

    Args:
        contexto_paciente_menor: True quando o paciente é criança/idoso e
            quem está digitando provavelmente é o responsável. Frase varia
            sutilmente pra dar contexto de responsável.
    """
    if contexto_paciente_menor:
        return PERGUNTA_PARA_RESPONSAVEL
    return PERGUNTA_PADRAO_NOME_CONTATO


# ---------------------------------------------------------------------------
# Helper de saudação segura
# ---------------------------------------------------------------------------

def saudacao_segura(nome_contato: str | None, fallback: str = "Olá") -> str:
    """Devolve "Olá, Carolina" se nome OK; "Olá" puro se inválido.

    NUNCA cai em "Olá Você" ou "Olá Inbra" — sempre o fallback limpo.
    """
    if nome_contato_invalido(nome_contato):
        return fallback
    primeiro = nome_contato.strip().split()[0].title()
    return f"{fallback}, {primeiro}"
