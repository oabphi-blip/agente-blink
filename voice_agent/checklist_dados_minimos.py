"""Checklist dos dados mínimos para gravar agendamento no Medware.

Origem (31/05/2026): lead 24053159 Juliene. Lia ofereceu slot sem ter
nome completo do Daniel nem CPF — agendamento físico no Medware ficou
impossível. Bug do "vou registrar pra equipe finalizar" foi sintoma
disso: sem dados, Lia improvisa porque ela "sente" que não dá pra
fechar mesmo.

Defesa preventiva: ANTES de oferecer slot, validar checklist. Se
faltar dado, injetar bloco PRÉ-AGENDA no prompt forçando coleta do
campo específico que falta.

Dados mínimos pra `salvar_agendamento` no Medware:
  1. nome_completo_paciente (≥ 3 tokens fortes) — SEMPRE
  2. data_nascimento (formato date) — SEMPRE
  3. convenio_definido ("Não se aplica" OU operadora mapeada) — SEMPRE
  4. cpf_paciente OU cpf_responsavel — APENAS se convenio == "Particular"
     (i.e. "Não se aplica" no Kommo). Para convênio aceito o CPF NÃO é
     mais exigido — paciente é identificado pela carteirinha do plano.

Mudança 02/06/2026 (Fábio): "para não burocratizar vamos retirar a
necessidade de exigência de cpf para paciente com convênios aceitos.
Vamos deixar somente para pacientes sem convênio." — bug Eva Massimo
Agrelis lead 22527166: Lia pediu CPF mesmo com Plan Assiste MPF.

`telefone` está implícito (já temos do canal WhatsApp).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Validações de campo individuais
# ---------------------------------------------------------------------------

_CONECTORES = frozenset({
    "de", "da", "do", "dos", "das", "e",
})


def _tokens_fortes(nome: str) -> int:
    """Conta tokens de ≥3 letras que não sejam conectores. Mesma regra
    de `nomes.avaliar_nome_paciente` — coerente com gravação Kommo."""
    if not nome:
        return 0
    bruto = re.sub(r"[^a-zà-úA-ZÀ-Ú\s]", " ", str(nome))
    tokens = [t.lower() for t in bruto.split() if t.strip()]
    fortes = [t for t in tokens if len(t) >= 3 and t not in _CONECTORES]
    return len(fortes)


def nome_completo_ok(nome: Optional[str]) -> bool:
    """≥3 tokens fortes — ex: 'João da Silva Souza' OK, 'Daniel' não."""
    return _tokens_fortes(nome or "") >= 3


def data_nascimento_ok(data_nasc: Optional[object]) -> bool:
    """Aceita int (timestamp Kommo), date, datetime, ou string ISO/BR."""
    if data_nasc is None or data_nasc == "":
        return False
    if isinstance(data_nasc, (int, float)):
        return data_nasc > 0
    if hasattr(data_nasc, "year"):  # date / datetime
        return True
    if isinstance(data_nasc, str):
        # ISO YYYY-MM-DD ou BR DD/MM/YYYY ou DD/MM/YY
        return bool(re.match(r"^\d{4}-\d{1,2}-\d{1,2}$", data_nasc)
                    or re.match(r"^\d{1,2}/\d{1,2}/\d{2,4}$", data_nasc))
    return False


def cpf_ok(cpf: Optional[str]) -> bool:
    """11 dígitos numéricos (formato pode vir mascarado)."""
    if not cpf:
        return False
    digitos = re.sub(r"\D", "", str(cpf))
    if len(digitos) != 11:
        return False
    # Rejeitar 11 dígitos iguais (00000000000, 11111111111, ...)
    return len(set(digitos)) > 1


def convenio_definido_ok(convenio: Optional[str]) -> bool:
    """Convênio precisa estar definido — particular OU operadora aceita."""
    if not convenio:
        return False
    c = str(convenio).strip().lower()
    if c in ("", "selecionar", "selecione", "(vazio)", "—", "-"):
        return False
    return True


# ---------------------------------------------------------------------------
# Checklist agregado
# ---------------------------------------------------------------------------

_CONVENIOS_PARTICULAR = frozenset({
    "particular",
    "nao se aplica",
    "não se aplica",
    "sem convenio",
    "sem convênio",
})


def _eh_particular(convenio: Optional[str]) -> bool:
    """True quando o paciente NÃO tem plano de saúde (Particular).

    A clínica precisa do CPF do paciente nesse caso pra emitir nota
    fiscal direto. Quando há plano, a operadora identifica o paciente
    pela carteirinha — CPF deixa de ser pré-requisito de agendamento.
    """
    if not convenio:
        return False  # convênio indefinido NÃO conta como particular
    return str(convenio).strip().lower() in _CONVENIOS_PARTICULAR


@dataclass(frozen=True)
class ChecklistResultado:
    """Resultado da verificação dos dados mínimos.

    Regra (revisão 02/06/2026):
      - CPF é obrigatório APENAS quando `convenio == Particular`
        ("Não se aplica" no Kommo).
      - Pra qualquer convênio aceito (Plan Assiste, TJDFT, STM, …)
        o CPF não bloqueia oferta de slot. `cpf_exigido = False`
        e `cpf_ok` é informativo (não entra em
        `pronto_para_oferecer_slot`).

    `pronto_para_oferecer_slot` = True quando nome + data_nasc +
    convênio definidos, MAIS o CPF SE for particular.

    `campos_pendentes` = lista de strings legíveis usadas no prompt
    pra Lia coletar EXATAMENTE o que falta.
    """
    nome_completo_ok: bool
    data_nascimento_ok: bool
    cpf_ok: bool
    convenio_definido_ok: bool
    cpf_exigido: bool = True  # default True pra retrocompat; verificar_dados_minimos seta corretamente
    campos_pendentes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def pronto_para_oferecer_slot(self) -> bool:
        if not (self.nome_completo_ok and self.data_nascimento_ok and self.convenio_definido_ok):
            return False
        if self.cpf_exigido and not self.cpf_ok:
            return False
        return True

    @property
    def total_pendentes(self) -> int:
        return len(self.campos_pendentes)


def verificar_dados_minimos(known: Optional[dict]) -> ChecklistResultado:
    """Verifica os 4 dados mínimos no `known` (camada do caller_context).

    Mapeamento dos campos esperados em `known` (alinhado com kommo.py):
    - nome_paciente: str (campo 1.NOME PACIENTE)
    - data_nasc_iso / data_nascimento_iso: str ISO ou int timestamp
    - cpf_paciente / cpf_responsavel: str (11 dígitos)
    - convenio: str (nome da operadora ou 'Não se aplica')

    Tolera nomes alternativos de chave — se o campo migrar, fica robusto.
    """
    k = known or {}

    nome_full = (
        k.get("nome_paciente")
        or k.get("nome_completo_paciente")
        or k.get("nome")
    )
    nome_ok = nome_completo_ok(nome_full)

    data_nasc = (
        k.get("data_nasc_iso")
        or k.get("data_nascimento_iso")
        or k.get("data_nascimento")
        or k.get("data_nasc")
    )
    data_ok = data_nascimento_ok(data_nasc)

    cpf = (
        k.get("cpf_paciente")
        or k.get("cpf_responsavel")
        or k.get("cpf")
    )
    c_ok = cpf_ok(cpf)

    conv = k.get("convenio")
    conv_ok = convenio_definido_ok(conv)

    # CPF só é exigido quando paciente é Particular.
    # Convênio definido E NÃO-particular => CPF dispensável (Fábio 02/06/2026).
    cpf_exigido = bool(conv_ok and _eh_particular(conv))

    # Monta lista de pendentes em ordem de coleta natural
    pendentes = []
    if not nome_ok:
        pendentes.append("nome completo do paciente")
    if not data_ok:
        pendentes.append("data de nascimento")
    if not conv_ok:
        pendentes.append("convênio (particular ou nome da operadora)")
    if cpf_exigido and not c_ok:
        pendentes.append("CPF do paciente (ou do responsável, se for menor)")

    return ChecklistResultado(
        nome_completo_ok=nome_ok,
        data_nascimento_ok=data_ok,
        cpf_ok=c_ok,
        convenio_definido_ok=conv_ok,
        cpf_exigido=cpf_exigido,
        campos_pendentes=tuple(pendentes),
    )


# ---------------------------------------------------------------------------
# Bloco PRÉ-AGENDA pro system prompt (injetado quando há pendentes)
# ---------------------------------------------------------------------------

def render_bloco_pre_agenda(resultado: ChecklistResultado) -> str:
    """Bloco injetado no system prompt quando há dados pendentes.

    Instrui Lia a coletar os campos faltantes ANTES de oferecer slot,
    sem reperguntar dados já presentes. Combate o anti-pattern
    "oferecer slot sem ter como gravar Medware".
    """
    if resultado.pronto_para_oferecer_slot:
        return ""

    bullets = "\n".join(
        f"  • {campo}" for campo in resultado.campos_pendentes
    )
    return (
        "\n\n----------------------------------------------------------------"
        "\nDADOS PENDENTES — COLETAR ANTES DE OFERECER SLOT"
        "\n----------------------------------------------------------------"
        "\n🚨 É PROIBIDO oferecer dia/hora de consulta enquanto faltar:"
        f"\n{bullets}"
        "\n"
        "\nMotivo: o agendamento no Medware exige esses dados. Oferecer"
        "\nslot sem eles é PROMESSA VAZIA — não tem como gravar."
        "\n"
        "\n✅ CAMINHO CORRETO:"
        "\n  1) Reconheça o avanço do paciente"
        "\n  2) Peça APENAS os campos pendentes acima (não repergunte os"
        "\n     que JÁ ESTÃO preenchidos no ONBOARDING)"
        "\n  3) Quando todos chegarem, AÍ SIM ofereça os slots"
        "\n"
        "\n📋 Exemplo de coleta enxuta:"
        "\n  'Antes de garantir o horário, me passa só [lista campos"
        "\n   pendentes]. Com isso eu já fecho tudo no sistema.'"
        "\n----------------------------------------------------------------"
    )
