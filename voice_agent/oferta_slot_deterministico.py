"""oferta_slot_deterministico.py — C-105 (11/08/2026)

Python seleciona os slots a ofertar; LLM só humaniza o texto em volta.

Antes (até C-104): _agenda_block injetava a agenda INTEIRA no prompt e
o LLM DECIDIA quais horários mostrar. Resultado: LLM às vezes inventava
datas, escolhia slots já ofertados, ou ignorava a preferência de turno.

Depois (C-105): Python pré-seleciona os 3 melhores slots ANTES de chamar
o LLM. O prompt recebe apenas esses 3, com instrução 'USE EXATAMENTE ESTES'.
O LLM não toma mais a decisão de qual horário mostrar — só formata o texto.

Exporta:
  selecionar_slots(agenda, turno_pref, ja_ofertados, lead_id) → list[dict]
  formatar_slots_para_prompt(slots, medico, unidade) → str
  formatar_oferta_humana(slots, medico, unidade, nome_paciente) → str
"""
from __future__ import annotations

import logging
import os
from typing import Optional

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Toggle (default ON — set OFERTA_SLOT_DETERMINISTICO=0 para rollback)
# ---------------------------------------------------------------------------
_ATIVADO = os.environ.get("OFERTA_SLOT_DETERMINISTICO", "1").strip() not in (
    "0", "false", "no", "off"
)


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------

def _hora_int(slot: dict) -> int:
    """Hora como inteiro (0-23) para comparação de turno."""
    try:
        return int(str(slot.get("hora") or "00:00")[:2])
    except (ValueError, TypeError):
        return 0


def _is_manha(slot: dict) -> bool:
    return _hora_int(slot) < 12


def _slot_id(slot: dict) -> str:
    """Chave canônica de um slot para dedup."""
    return f"{slot.get('data_iso', '')}_{slot.get('hora', '')}"


# ---------------------------------------------------------------------------
# Função principal exportada
# ---------------------------------------------------------------------------

def selecionar_slots(
    agenda: list,
    turno_pref: Optional[str] = None,
    ja_ofertados: Optional[set] = None,
    lead_id: Optional[int] = None,
) -> list[dict]:
    """Seleciona até 3 slots ótimos da agenda para oferta determinística.

    Estratégia (em ordem):
      1. Filtra slots já ofertados ao mesmo lead (E6-B: não repetir slot).
      2. Com turno_pref="manhã" → até 3 slots de manhã mais próximos.
         Com turno_pref="tarde" → até 3 slots de tarde.
         Sem preferência → 1 manhã (mais próximo) + 1 tarde + 1 alternativo.
      3. Se não há 3 no turno preferido → completa com o outro turno.
      4. Retorna lista vazia se agenda vazia (fail-open: LLM segue normal).

    Parâmetros:
      agenda       — lista de slots do Medware (já ordenada cronologicamente)
      turno_pref   — "manhã" | "tarde" | None (sem preferência)
      ja_ofertados — set de slot_id já ofertados ao mesmo lead (E6-B)
      lead_id      — apenas para log estruturado

    Fail-open: qualquer exceção interna → retorna [].
    """
    if not _ATIVADO:
        return []

    try:
        return _selecionar_interno(agenda, turno_pref, ja_ofertados or set())
    except Exception as exc:
        log.warning("[C-105] selecionar_slots falhou lead=%s: %s", lead_id, exc)
        return []


def _selecionar_interno(
    agenda: list,
    turno_pref: Optional[str],
    ja_ofertados: set,
) -> list[dict]:
    if not agenda:
        return []

    # Remove slots já ofertados (E6-B)
    candidatos = [s for s in agenda if _slot_id(s) not in ja_ofertados]
    if not candidatos:
        # Todos já ofertados: usa agenda completa (melhor que retornar vazio)
        candidatos = list(agenda)

    manha = [s for s in candidatos if _is_manha(s)]
    tarde = [s for s in candidatos if not _is_manha(s)]

    if turno_pref:
        t = turno_pref.lower()
        if "manh" in t:
            pool_prim, pool_sec = manha, tarde
        else:
            pool_prim, pool_sec = tarde, manha
        resultado = list(pool_prim[:3])
        if len(resultado) < 3:
            resultado += pool_sec[: 3 - len(resultado)]
        return resultado[:3]

    # Sem preferência: 1 manhã + 1 tarde + 1 alternativo
    resultado: list = []
    if manha:
        resultado.append(manha[0])
    if tarde:
        resultado.append(tarde[0])
    # 3º slot: próximo não repetido
    for s in candidatos:
        if len(resultado) >= 3:
            break
        if s not in resultado:
            resultado.append(s)
    return resultado[:3]


# ---------------------------------------------------------------------------
# Formatação para injeção no system prompt
# ---------------------------------------------------------------------------

def formatar_slots_para_prompt(
    slots: list[dict],
    medico: str = "",
    unidade: str = "",
) -> str:
    """Formata os 3 slots pré-selecionados como bloco de texto para o prompt.

    Usado por _agenda_block quando ctx.known.slots_selecionados está presente.
    LLM recebe APENAS estes slots com instrução 'USE EXATAMENTE ESTES'.
    """
    if not slots:
        return ""

    linhas = []
    for i, s in enumerate(slots):
        dia = (s.get("dia_semana") or "").capitalize()
        dbr = s.get("data_br") or ""
        hora = s.get("hora") or ""
        prefixo = f"{dia} ({dbr})" if dia and dbr else dbr or dia
        linhas.append(f"  {i+1}. {prefixo} às {hora}")

    med_str = f" com {medico}" if medico else ""
    uni_str = f", {unidade}" if unidade else ""
    header = f"SLOTS PRÉ-SELECIONADOS{med_str}{uni_str}:"

    return (
        "\n\n--- SLOTS PRÉ-SELECIONADOS PELO SISTEMA PYTHON (C-105) ---"
        f"\n{header}"
        + "\n".join(linhas)
        + "\n"
        "\n🚨 REGRA C-105 (INVIOLÁVEL):"
        "\n  USE EXATAMENTE ESTES SLOTS. NÃO escolha outros da agenda."
        "\n  NÃO invente datas, horas ou dias que não estejam listados."
        "\n  Sua tarefa: formatar esses slots em mensagem humanizada e"
        "\n  calorosa no formato 1️⃣/2️⃣/3️⃣ e perguntar qual fica melhor."
        "\n--- FIM SLOTS PRÉ-SELECIONADOS ---"
    )


# ---------------------------------------------------------------------------
# Formatação da oferta humanizada (bypass direto — sem LLM)
# ---------------------------------------------------------------------------

_EMOJIS = ["1️⃣", "2️⃣", "3️⃣"]


def formatar_oferta_humana(
    slots: list[dict],
    medico: str = "a médica",
    unidade: str = "a unidade combinada",
    nome_paciente: str = "",
) -> str:
    """Gera a mensagem de oferta de slot pronta para enviar ao paciente.

    Usada pelos bypasses determinísticos (_gerar_oferta_3_slots e
    deve_ofertar_agora) quando ctx.known.slots_selecionados está disponível.

    Exemplo de saída:
      Tenho esses horários disponíveis com a Dra. Karla Delalíbera, Asa Norte:

      1️⃣ Quarta-feira (13/08) às 09:30
      2️⃣ Quarta-feira (13/08) às 14:00
      3️⃣ Quinta-feira (14/08) às 10:00

      Qual fica melhor pra você?
    """
    if not slots:
        return ""

    saud = f"{nome_paciente}, " if nome_paciente else ""
    linhas = []
    for i, s in enumerate(slots):
        dia = (s.get("dia_semana") or "").capitalize()
        dbr = s.get("data_br") or ""
        hora = s.get("hora") or ""
        emoji = _EMOJIS[i] if i < len(_EMOJIS) else f"{i+1}."
        prefixo = f"{dia} ({dbr})" if dia and dbr else dbr or dia
        linhas.append(f"{emoji} {prefixo} às {hora}")

    return (
        f"{saud}Tenho esses horários disponíveis com a {medico}, {unidade}:\n\n"
        + "\n".join(linhas)
        + "\n\nQual fica melhor pra você?"
    )
