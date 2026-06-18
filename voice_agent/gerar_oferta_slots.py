"""Camada 2 — Geração de oferta de 2 slots Medware pra um lead.

Substitui o fluxo manual onde o Claude Cowork era chamado a cada
atendimento. Lê o lead Kommo, extrai médico/unidade/preferência,
bate Medware com janela curta (7 dias = sem timeout), filtra
pelo turno/período, retorna 2 slots ordenados + mensagem pronta
no formato canônico 1️⃣/2️⃣.

Funciona 24h porque vive no agent do Easypanel.

Origem: Bug C-38b ainda apareceu pós-deploy. Fix arquitetural
(LangChain/dev fractional) depende de 1-2 semanas. Esta camada
destrava operação híbrida (endpoint + equipe humana cola) AGORA.

Quem chama:
    from voice_agent.gerar_oferta_slots import gerar_oferta_para_lead
    resultado = gerar_oferta_para_lead(
        lead_id=24113652,
        kommo_client=kommo,
        medware_client=medware,
        postar_nota=True,
    )
    # → {"ok": True, "paciente": "...", "slots": [...],
    #    "mensagem_pronta": "..."}
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

log = logging.getLogger(__name__)

_TZ = ZoneInfo("America/Sao_Paulo")

# Mapeamento dia da semana português → weekday() Python (0=segunda, 6=domingo)
_DIAS_SEMANA_PT = {
    "segunda": 0, "segunda-feira": 0,
    "terca": 1, "terça": 1, "terca-feira": 1, "terça-feira": 1,
    "quarta": 2, "quarta-feira": 2,
    "quinta": 3, "quinta-feira": 3,
    "sexta": 4, "sexta-feira": 4,
    "sabado": 5, "sábado": 5,
    "domingo": 6,
}

_DIAS_SEMANA_NOME = {
    0: "segunda-feira", 1: "terça-feira", 2: "quarta-feira",
    3: "quinta-feira", 4: "sexta-feira", 5: "sábado", 6: "domingo",
}


def _primeiro_nome(nome_completo: str | None) -> str:
    """Retorna apenas o primeiro nome capitalizado."""
    if not nome_completo:
        return ""
    return str(nome_completo).strip().split()[0].title()


def _extrair_cf(lead: dict, nome_campo: str) -> str | None:
    """Extrai valor de custom_field por nome (case-insensitive)."""
    cfs = lead.get("custom_fields_values") or lead.get("custom_fields") or []
    nome_alvo = (nome_campo or "").strip().upper()
    for cf in cfs:
        if not isinstance(cf, dict):
            continue
        nome_cf = (cf.get("field_name") or cf.get("name") or "").strip().upper()
        if nome_cf == nome_alvo:
            vals = cf.get("values") or []
            if vals and isinstance(vals[0], dict):
                v = vals[0].get("value")
                if v not in (None, "", "Selecione", "Não se aplica"):
                    return str(v)
    return None


def parsear_preferencia(texto: str | None) -> dict:
    """Parsea o campo DIA/TURNO/PERIODO ⚠️ do Kommo.

    Exemplos:
        "Segunda-feira — manhã — início (8h-9h)"
        "Quarta tarde fim"
        "Amanhã (preferência não especificada)"
        "Próxima semana"

    Retorna:
        {
          "dia_semana": 0-6 ou None,
          "turno": "manha" | "tarde" | None,
          "periodo": "inicio" | "meio" | "fim" | None,
          "texto_descritivo": "segunda-feira manhã início",
        }
    """
    out = {"dia_semana": None, "turno": None, "periodo": None,
           "texto_descritivo": ""}
    if not texto:
        return out
    t = texto.lower().strip()

    # Dia da semana
    for nome, idx in _DIAS_SEMANA_PT.items():
        if nome in t:
            out["dia_semana"] = idx
            break

    # Turno
    if "manh" in t or "manha" in t:
        out["turno"] = "manha"
    elif "tarde" in t:
        out["turno"] = "tarde"
    elif "noite" in t or "fim de tarde" in t:
        out["turno"] = "tarde"  # noite cai pra tarde (não atende noite)

    # Período
    if "início" in t or "inicio" in t or "começo" in t or "comeco" in t:
        out["periodo"] = "inicio"
    elif "fim" in t or "final" in t or "ultimo" in t or "último" in t:
        out["periodo"] = "fim"
    elif "meio" in t or "metade" in t:
        out["periodo"] = "meio"

    # Texto descritivo pra mensagem
    descritivo = []
    if out["dia_semana"] is not None:
        descritivo.append(_DIAS_SEMANA_NOME[out["dia_semana"]])
    if out["turno"]:
        descritivo.append(out["turno"].replace("manha", "manhã"))
    if out["periodo"]:
        descritivo.append(out["periodo"].replace("inicio", "início"))
    out["texto_descritivo"] = " ".join(descritivo)

    return out


def filtrar_slots_por_preferencia(slots: list[dict], pref: dict) -> list[dict]:
    """Aplica preferência sobre slots brutos do Medware.

    Cada slot tem `data_iso` (YYYY-MM-DD), `hora` (HH:MM ou HH:MM:SS) ou
    o formato original `data` (com 'T00:00:00') + `horario`.

    Retorna lista filtrada (pode ser vazia).
    """
    if not slots:
        return []

    out = []
    for s in slots:
        # Suporta dois formatos: 'data_iso' / 'hora' (transformado em
        # horarios_para_agente) ou 'data' / 'horario' (raw Medware).
        data_str = s.get("data_iso") or s.get("data") or ""
        hora_str = s.get("hora") or s.get("horario") or ""
        try:
            # Formato data_iso é '2026-06-22'; data raw é '2026-06-22T00:00:00'
            data_only = data_str[:10]
            d = datetime.strptime(data_only, "%Y-%m-%d")
        except (ValueError, TypeError):
            continue
        weekday = d.weekday()
        try:
            hora_int = int(hora_str[:2])
        except (ValueError, TypeError):
            continue

        # Filtro dia da semana
        if pref.get("dia_semana") is not None and weekday != pref["dia_semana"]:
            continue
        # Filtro turno
        if pref.get("turno") == "manha" and hora_int >= 12:
            continue
        if pref.get("turno") == "tarde" and hora_int < 12:
            continue

        out.append({**s, "_weekday": weekday, "_hora_int": hora_int})

    # Ordenar por período se especificado
    periodo = pref.get("periodo")
    if periodo and pref.get("turno"):
        if pref["turno"] == "manha":
            # manhã: início = 7-9h, meio = 9-11h, fim = 11-12h
            if periodo == "inicio":
                out.sort(key=lambda x: abs(x["_hora_int"] - 8))
            elif periodo == "meio":
                out.sort(key=lambda x: abs(x["_hora_int"] - 10))
            elif periodo == "fim":
                out.sort(key=lambda x: abs(x["_hora_int"] - 11))
        elif pref["turno"] == "tarde":
            # tarde: início = 13-14h, meio = 14-16h, fim = 16-18h
            if periodo == "inicio":
                out.sort(key=lambda x: abs(x["_hora_int"] - 13))
            elif periodo == "meio":
                out.sort(key=lambda x: abs(x["_hora_int"] - 15))
            elif periodo == "fim":
                out.sort(key=lambda x: abs(x["_hora_int"] - 17))

    return out


def selecionar_2_slots(slots_filtrados: list[dict],
                       slots_sem_preferencia: list[dict] | None = None) -> list[dict]:
    """Seleciona 2 slots da lista filtrada.

    Estratégia:
      - Se tem 2+ slots filtrados → pega os 2 primeiros (já ordenados por preferência)
      - Se tem 1 → pega esse + o mais próximo da preferência da lista sem filtro
      - Se 0 → pega 2 da lista sem filtro (relaxa preferência)
    """
    if len(slots_filtrados) >= 2:
        return slots_filtrados[:2]
    if len(slots_filtrados) == 1:
        outros = [s for s in (slots_sem_preferencia or [])
                  if s != slots_filtrados[0]]
        return [slots_filtrados[0]] + outros[:1]
    return (slots_sem_preferencia or [])[:2]


def formatar_slot(slot: dict) -> dict:
    """Normaliza slot pra formato de saída.

    {data: '22/06', dia_semana: 'segunda-feira', hora: '11:00', codAgenda: 4}
    """
    data_str = slot.get("data_iso") or slot.get("data") or ""
    hora_str = slot.get("hora") or slot.get("horario") or ""
    try:
        data_only = data_str[:10]
        d = datetime.strptime(data_only, "%Y-%m-%d")
        data_br = d.strftime("%d/%m")
        dia_nome = _DIAS_SEMANA_NOME[d.weekday()]
    except (ValueError, TypeError):
        data_br = ""
        dia_nome = ""
    hora_clean = hora_str[:5] if hora_str else ""

    return {
        "data": data_br,
        "dia_semana": dia_nome,
        "hora": hora_clean,
        "codAgenda": slot.get("cod_agenda") or slot.get("codAgenda") or 4,
        "codMedico": slot.get("cod_medico") or slot.get("codMedico"),
        "codUnidade": slot.get("cod_unidade") or slot.get("codUnidade"),
    }


def montar_mensagem(paciente_primeiro_nome: str, medico_apresentacao: str,
                    unidade: str, descritivo_pref: str,
                    slot1: dict, slot2: dict) -> str:
    """Monta mensagem canônica 1️⃣/2️⃣ pronta pra colar no WhatsApp.

    Formato:
        {Nome}! Os horários disponíveis com a Dra. {medico} na {unidade}{pref}:

        1️⃣ {dia1}, {data1} às {hora1}
        2️⃣ {dia2}, {data2} às {hora2}

        Qual prefere?
    """
    pref_sufix = f", {descritivo_pref}" if descritivo_pref else ""
    saudacao = paciente_primeiro_nome if paciente_primeiro_nome else "Olá"
    return (
        f"{saudacao}! Os horários disponíveis com a {medico_apresentacao} "
        f"na {unidade}{pref_sufix}:\n\n"
        f"1️⃣ {slot1['dia_semana']}, {slot1['data']} às {slot1['hora']}\n"
        f"2️⃣ {slot2['dia_semana']}, {slot2['data']} às {slot2['hora']}\n\n"
        f"Qual prefere?"
    )


def _apresentacao_medico(medico_raw: str | None) -> str:
    """Normaliza nome do médico pra apresentação canônica."""
    if not medico_raw:
        return "Dra. Karla Delalíbera"
    m = medico_raw.lower()
    if "karla" in m:
        return "Dra. Karla Delalíbera"
    if "fabr" in m or "fabricio" in m:
        return "Dr. Fabrício Freitas"
    return medico_raw


def gerar_oferta_para_lead(
    lead_id: int,
    kommo_client,
    medware_client,
    postar_nota: bool = False,
    janela_dias: int = 7,
    override_medico: str | None = None,
    override_unidade: str | None = None,
) -> dict:
    """Gera oferta de 2 slots pra um lead Kommo.

    Args:
        lead_id: ID do lead no Kommo
        kommo_client: instância KommoClient (precisa de get_lead, add_note)
        medware_client: instância MedwareClient (precisa horarios_para_agente)
        postar_nota: se True, grava a oferta como nota no próprio lead
        janela_dias: dias à frente pra buscar slots (default 7, máx 14)
        override_medico: força médico específico (ignora ctx do lead)
        override_unidade: força unidade específica (ignora ctx do lead)

    Returns:
        {
          "ok": bool,
          "lead_id": int,
          "paciente": str,
          "medico": str,
          "unidade": str,
          "preferencia": dict (parseada),
          "slots": [{data, dia_semana, hora, codAgenda, ...}, ...],
          "mensagem_pronta": str (formato 1️⃣/2️⃣),
          "nota_kommo_id": int | None,
          "warning": str | None,
        }

    Erros possíveis (retorna ok=False):
        - lead_nao_encontrado
        - medware_indisponivel
        - sem_slots (Medware retornou vazio mesmo com janela curta)
    """
    janela_dias = max(1, min(janela_dias, 14))  # cap defensivo

    # 1. Lê lead Kommo
    lead = kommo_client.get_lead(lead_id)
    if not lead:
        return {"ok": False, "lead_id": lead_id,
                "error": "lead_nao_encontrado"}

    nome_paciente = _extrair_cf(lead, "1.NOME PACIENTE") or ""
    if not nome_paciente:
        # fallback pro nome do lead
        nome_paciente = lead.get("name") or ""
    primeiro_nome = _primeiro_nome(nome_paciente)

    medico_raw = override_medico or _extrair_cf(lead, "MEDICOS") or "Dra. Karla Delalibera"
    unidade_raw = override_unidade or _extrair_cf(lead, "UNIDADE") or "Asa Norte"

    pref_texto = _extrair_cf(lead, "DIA/TURNO/PERIODO ⚠️") or ""
    pref = parsear_preferencia(pref_texto)

    # 2. Bate Medware (janela curta = sem timeout)
    hoje = datetime.now(_TZ)
    data_inicio = (hoje + timedelta(days=1)).date()
    data_fim = (hoje + timedelta(days=janela_dias)).date()
    try:
        slots_raw = medware_client.horarios_para_agente(
            medico_raw, unidade_raw,
            data_inicio=data_inicio, data_fim=data_fim,
        )
    except Exception as e:  # noqa: BLE001
        log.warning("[gerar-oferta-slots] Medware exception lead=%s: %s",
                    lead_id, e)
        return {"ok": False, "lead_id": lead_id,
                "error": "medware_indisponivel", "detail": str(e)}

    if not slots_raw:
        return {"ok": False, "lead_id": lead_id, "error": "sem_slots",
                "janela_dias": janela_dias,
                "medico": medico_raw, "unidade": unidade_raw}

    # 3. Filtra por preferência (com fallback)
    slots_filtrados = filtrar_slots_por_preferencia(slots_raw, pref)
    slots_2 = selecionar_2_slots(slots_filtrados, slots_raw)

    if len(slots_2) < 2:
        return {"ok": False, "lead_id": lead_id,
                "error": "slots_insuficientes",
                "encontrados": len(slots_2),
                "total_medware": len(slots_raw)}

    # 4. Formata saída
    slot1_fmt = formatar_slot(slots_2[0])
    slot2_fmt = formatar_slot(slots_2[1])

    apresentacao_med = _apresentacao_medico(medico_raw)
    mensagem = montar_mensagem(
        primeiro_nome, apresentacao_med, unidade_raw,
        pref.get("texto_descritivo") or "",
        slot1_fmt, slot2_fmt,
    )

    # 5. Posta nota opcional
    nota_id = None
    if postar_nota:
        try:
            nota_texto = (
                f"[OFERTA GERADA - endpoint /admin/gerar-oferta-slots]\n\n"
                f"Mensagem pronta pra colar no WhatsApp:\n\n"
                f"{mensagem}"
            )
            res = kommo_client.add_note(lead_id, nota_texto)
            # add_note retorna bool ou dict — tenta extrair id
            if isinstance(res, dict):
                nota_id = res.get("note_id") or res.get("id")
            elif res:
                nota_id = -1  # success boolean
        except Exception as e:  # noqa: BLE001
            log.warning("[gerar-oferta-slots] add_note falhou lead=%s: %s",
                        lead_id, e)

    log.info(
        "[gerar-oferta-slots] OK lead=%s medico=%s unidade=%s "
        "pref=%s slots=%s,%s nota=%s",
        lead_id, medico_raw, unidade_raw,
        pref.get("texto_descritivo") or "<nenhuma>",
        f"{slot1_fmt['data']} {slot1_fmt['hora']}",
        f"{slot2_fmt['data']} {slot2_fmt['hora']}",
        nota_id,
    )

    return {
        "ok": True,
        "lead_id": lead_id,
        "paciente": nome_paciente,
        "medico": apresentacao_med,
        "unidade": unidade_raw,
        "preferencia": {
            "texto_original": pref_texto,
            "dia_semana": pref.get("dia_semana"),
            "turno": pref.get("turno"),
            "periodo": pref.get("periodo"),
            "descritivo": pref.get("texto_descritivo"),
        },
        "slots": [slot1_fmt, slot2_fmt],
        "mensagem_pronta": mensagem,
        "nota_kommo_id": nota_id,
        "janela_dias": janela_dias,
        "total_slots_medware": len(slots_raw),
        "slots_apos_filtro_pref": len(slots_filtrados),
    }
