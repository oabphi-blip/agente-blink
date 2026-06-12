"""
voice_agent/ativacao_inteligente.py — saudação personalizada com PROVA DE ESCUTA.

Origem: Fábio 12/06/2026 — quando paciente volta com lead já criado e campos
preenchidos (nome paciente, médico, convênio, notas anteriores), a Lia DEVE
demonstrar que sabe quem é + recapitular onde parou + perguntar como avançar.
NÃO tratar como lead novo.

Princípios:
  - PROVA DE ESCUTA: citar pelo menos UM dado concreto do histórico ("vi que
    sua última conversa foi sobre {médico}", "lembrei que o convênio é {X}").
  - NÃO INVENTAR: só usar dados PRESENTES no lead. Sem dado → cair pra
    saudação genérica.
  - ECONÔMICO: máx 2 frases. Não despeja todo o histórico. Pergunta UMA coisa.
  - ANTI-CONSTRANGIMENTO: se há gap longo (>6 meses sem conversa), reconhecer
    sem dramatizar.

Quem chama:
    from voice_agent.ativacao_inteligente import gerar_saudacao_personalizada
    saudacao = gerar_saudacao_personalizada(lead_ctx)
"""

from __future__ import annotations
from typing import Any
from datetime import datetime, timezone


def _extrair_campo(lead: dict, field_name: str) -> str | None:
    """Extrai value do custom_field por nome (case-insensitive)."""
    cfs = lead.get("custom_fields") or lead.get("custom_fields_values") or []
    if not cfs:
        return None
    nome_alvo = (field_name or "").strip().upper()
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


def _primeiro_nome(nome_completo: str | None) -> str:
    if not nome_completo:
        return ""
    return str(nome_completo).strip().split()[0].title()


def _dias_atras(ts_epoch: int | float | None) -> int | None:
    if not ts_epoch:
        return None
    try:
        ts = int(float(ts_epoch))
        agora = datetime.now(timezone.utc).timestamp()
        return max(0, int((agora - ts) / 86400))
    except Exception:  # noqa: BLE001
        return None


def gerar_saudacao_personalizada(lead: dict) -> dict:
    """Monta saudação Lia com prova de escuta.

    Args:
        lead: dict com `name`, `custom_fields` (com 1.NOME PACIENTE, MEDICOS,
              CONVENIO, UNIDADE), `updated_at` opcional, `notes` opcional.

    Returns:
        {
          "tipo": "personalizada" | "generica" | "lacuna_longa",
          "saudacao": "<texto pronto pra Lia enviar>",
          "campos_usados": ["nome_paciente", "medico", ...],
          "ancora_principal": "<o dado citado mais forte>",
          "pergunta_aberta": "<a pergunta única no fim>"
        }

    Regras:
        - Se NÃO tem nome paciente E NÃO tem médico/convênio → "generica".
        - Se updated_at >180 dias atrás → "lacuna_longa" (reconhece gap).
        - Caso contrário → "personalizada" (cita 1-2 campos do lead).
    """
    nome_paciente_full = _extrair_campo(lead, "1.NOME PACIENTE") or ""
    nome_paciente = _primeiro_nome(nome_paciente_full)
    medico = _extrair_campo(lead, "MEDICOS") or ""
    convenio = _extrair_campo(lead, "CONVENIO") or ""
    unidade = _extrair_campo(lead, "UNIDADE") or ""
    especialidade = _extrair_campo(lead, "ESPECIALID") or ""

    # Caso 1: dado nenhum → genérica
    if not (nome_paciente or medico or convenio):
        return {
            "tipo": "generica",
            "saudacao": (
                "Olá! 👋 Aqui é a Lia da Blink Oftalmologia.\n\n"
                "Pra te chamar pelo nome certo, com quem estou falando? "
                "E como posso te ajudar hoje?"
            ),
            "campos_usados": [],
            "ancora_principal": None,
            "pergunta_aberta": "Com quem estou falando?",
        }

    # Caso 2: lacuna longa? (>180 dias desde último update)
    updated_at_iso = lead.get("updated_at")
    dias = None
    if updated_at_iso:
        try:
            dt = datetime.fromisoformat(
                str(updated_at_iso).replace("Z", "+00:00"),
            )
            dias = (datetime.now(timezone.utc) - dt).days
        except Exception:  # noqa: BLE001
            pass

    if dias and dias > 180:
        meses = dias // 30
        ancora = (
            f"a Dra. {medico.split('Delalibera')[0].strip() or medico}"
            if "Karla" in medico else
            (f"o {medico}" if medico else "nossa equipe")
        )
        return {
            "tipo": "lacuna_longa",
            "saudacao": (
                f"Olá, {nome_paciente or 'tudo bem'}! 👋\n\n"
                f"Aqui é a Lia da Blink. Vi que nossa última conversa "
                f"foi há cerca de {meses} meses — que bom te ver de volta. "
                f"Como posso te ajudar hoje?"
            ),
            "campos_usados": ["nome_paciente", "updated_at"],
            "ancora_principal": f"última conversa há {meses} meses",
            "pergunta_aberta": "Como posso te ajudar hoje?",
        }

    # Caso 3: personalizada com prova de escuta
    # Escolhe a âncora mais forte: nome paciente > médico > convênio
    ancoras_texto = []
    campos = []
    if nome_paciente:
        campos.append("nome_paciente")
    if medico:
        # Limpa nome médico ("Dra. Karla Delalibera" → "Dra. Karla")
        med_curto = medico
        if "Karla" in medico:
            med_curto = "Dra. Karla"
        elif "Fabrício" in medico or "Fabricio" in medico:
            med_curto = "Dr. Fabrício"
        ancoras_texto.append(f"era com a {med_curto}" if "Dra" in med_curto
                              else f"era com o {med_curto}")
        campos.append("medico")
    if convenio and convenio not in ("Não se aplica", "particular"):
        ancoras_texto.append(f"pelo {convenio}")
        campos.append("convenio")
    if unidade:
        ancoras_texto.append(f"na {unidade}")
        campos.append("unidade")

    # Saudação personalizada — máx 2 frases
    if nome_paciente:
        primeira = f"Olá, {nome_paciente}! 👋"
    else:
        primeira = "Olá! 👋"

    if ancoras_texto:
        prova = " ".join(ancoras_texto)
        recapitula = (
            f"Vi aqui que sua consulta {prova}. "
            f"Vamos seguir de onde paramos?"
        )
        ancora_principal = ancoras_texto[0]
    else:
        recapitula = "Em que posso te ajudar hoje?"
        ancora_principal = nome_paciente or None

    saudacao = f"{primeira}\n\nAqui é a Lia da Blink. {recapitula}"

    return {
        "tipo": "personalizada",
        "saudacao": saudacao,
        "campos_usados": campos,
        "ancora_principal": ancora_principal,
        "pergunta_aberta": (
            "Vamos seguir de onde paramos?" if ancoras_texto
            else "Em que posso te ajudar hoje?"
        ),
    }


def gerar_saudacao_de_ctx(ctx: dict | None) -> dict:
    """Versão que aceita o formato `caller_context` do pipeline.

    Converte ctx → formato lead Kommo e delega pra
    gerar_saudacao_personalizada. Usado em responder.py pra que a Lia
    inicie conversa com prova de escuta quando há dados conhecidos.

    Args:
        ctx: dict do pipeline com `name`, `known: {nome_paciente, medico,
             convenio, unidade, especialidade, dia_consulta_iso, ...}`,
             `updated_at` opcional.

    Returns:
        Mesmo dict que gerar_saudacao_personalizada.
    """
    if not ctx or not ctx.get("found"):
        return gerar_saudacao_personalizada({"id": 0, "custom_fields": []})

    known = ctx.get("known") or {}
    # Constrói custom_fields no formato esperado
    cfs = []

    def _add(field_name: str, value):
        if value:
            cfs.append({
                "field_name": field_name,
                "values": [{"value": str(value)}],
            })

    _add("1.NOME PACIENTE", known.get("nome_paciente"))
    _add("MEDICOS", known.get("medico"))
    _add("CONVENIO", known.get("convenio"))
    _add("UNIDADE", known.get("unidade"))
    _add("ESPECIALID", known.get("especialidade"))

    lead_norm = {
        "id": ctx.get("lead_id") or 0,
        "name": ctx.get("name") or "",
        "updated_at": ctx.get("updated_at"),
        "custom_fields": cfs,
    }
    return gerar_saudacao_personalizada(lead_norm)
