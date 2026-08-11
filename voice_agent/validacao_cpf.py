"""
Bug C-110 (11/08/2026) — Validação de CPF por dígitos verificadores.

Causa raiz: LLM aceitava qualquer sequência de 11 dígitos como CPF válido.
Pacientes digitavam "111.111.111-11" (sequência inválida), "12345678900"
(matematicamente errado), ou até texto sem CPF — e pipeline prosseguia
tentando gravar no Medware com CPF inválido → falha silenciosa.

Resultado: agendamento Medware falhava, Lia entrava em loop pedindo CPF
de novo, ou pior: gravava CPF incorreto no prontuário do paciente.

Decisão arquitetural (P0):
  - Python extrai CPF do user_text (regex) e valida matematicamente
    (algoritmo dígitos verificadores) ANTES de aceitar o campo
  - CPF inválido → Python retorna mensagem pedindo correção, com exemplo
  - CPF válido → injeta em ctx.known["cpf_validado"] para Medware
  - CPF de sequências homogêneas (000.000.000-00, etc.) → inválido
  - Fail-open: qualquer exceção → None (pipeline continua, LLM decide)

Toggle: VALIDACAO_CPF_ATIVADO (default ON)
"""

from __future__ import annotations

import logging
import os
import re
from typing import Optional

log = logging.getLogger(__name__)

_ATIVADO = os.environ.get("VALIDACAO_CPF_ATIVADO", "1").strip() not in (
    "0", "false", "no", "off"
)

# Regex para extrair CPF do texto — aceita com ou sem pontuação
_RE_CPF_RAW = re.compile(
    r"\b(\d{3})[.\s-]?(\d{3})[.\s-]?(\d{3})[.\s-]?(\d{2})\b"
)

# Sequências homogêneas inválidas (000.000.000-00, 111.111.111-11, etc.)
_SEQUENCIAS_INVALIDAS = {str(d) * 11 for d in range(10)}

# Mensagem de erro padronizada
_MSG_CPF_INVALIDO = (
    "Hmm, esse CPF não parece correto. 😊\n\n"
    "Pode me confirmar os 11 dígitos? "
    "Pode enviar com ou sem pontuação, por exemplo: `123.456.789-09`."
)


def _calcular_digitos_verificadores(cpf9: str) -> tuple[int, int]:
    """Calcula os dois dígitos verificadores para os primeiros 9 dígitos do CPF."""
    # Primeiro dígito
    soma1 = sum(int(cpf9[i]) * (10 - i) for i in range(9))
    resto1 = soma1 % 11
    d1 = 0 if resto1 < 2 else 11 - resto1

    # Segundo dígito
    cpf10 = cpf9 + str(d1)
    soma2 = sum(int(cpf10[i]) * (11 - i) for i in range(10))
    resto2 = soma2 % 11
    d2 = 0 if resto2 < 2 else 11 - resto2

    return d1, d2


def cpf_matematicamente_valido(cpf_digitos: str) -> bool:
    """Retorna True se os 11 dígitos formam um CPF matematicamente válido.

    Rejeita:
    - sequências homogêneas (11111111111, etc.)
    - CPFs com dígitos verificadores errados
    """
    if len(cpf_digitos) != 11 or not cpf_digitos.isdigit():
        return False
    if cpf_digitos in _SEQUENCIAS_INVALIDAS:
        return False

    d1_esperado, d2_esperado = _calcular_digitos_verificadores(cpf_digitos[:9])
    return int(cpf_digitos[9]) == d1_esperado and int(cpf_digitos[10]) == d2_esperado


def extrair_cpf_do_texto(texto: str) -> Optional[str]:
    """Extrai e normaliza CPF do texto do usuário (apenas dígitos).

    Retorna string de 11 dígitos ou None se não encontrar.
    """
    if not texto:
        return None
    m = _RE_CPF_RAW.search(texto)
    if not m:
        return None
    return "".join(m.groups())


def formatar_cpf(cpf11: str) -> str:
    """Formata CPF no padrão XXX.XXX.XXX-XX."""
    return f"{cpf11[:3]}.{cpf11[3:6]}.{cpf11[6:9]}-{cpf11[9:11]}"


def deve_validar_cpf(
    ctx: Optional[dict],
    user_text: str = "",
) -> Optional[str]:
    """Valida CPF no user_text. Retorna mensagem de erro se inválido, None se válido ou ausente.

    Lógica:
    - Só age quando há um padrão de CPF no user_text
    - Se CPF encontrado E matematicamente inválido → retorna mensagem de correção
    - Se CPF encontrado E válido → retorna None (pipeline continua normal;
      enriquecimento_ctx injeta o CPF em known)
    - Se nenhum CPF no texto → retorna None (não interfere)

    Fail-open: qualquer exceção → None.
    """
    if not _ATIVADO:
        return None
    if ctx is None:
        return None

    try:
        cpf_digitos = extrair_cpf_do_texto(user_text)
        if cpf_digitos is None:
            return None  # sem CPF no texto — não interfere

        if cpf_matematicamente_valido(cpf_digitos):
            # CPF válido — enriquecimento_ctx vai injetar em known
            log.info("[C-110] CPF válido detectado: %s***", cpf_digitos[:3])
            return None

        # CPF inválido — retorna mensagem de correção
        log.info(
            "[C-110] CPF inválido rejeitado: %s lead=%s",
            formatar_cpf(cpf_digitos),
            ctx.get("lead_id"),
        )
        return _MSG_CPF_INVALIDO

    except Exception as exc:
        log.warning("[C-110] deve_validar_cpf falhou: %s", exc)
        return None  # fail-open
