"""Detector e executor de agendamento Medware após resposta da Lia.

Funciona em thread separada (chamado pelo pipeline). Usa Claude Haiku como
extrator estruturado da última resposta da Lia. Se detectar que ela
confirmou um agendamento específico (data + hora), chama
medware.criar_agendamento e move o lead Kommo para 4-AGENDADO.

Gap 2 do roadmap "100% gravação Medware sem humano".
Documentado em docs/06_pipeline_agente.md.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from typing import Any, Optional

log = logging.getLogger(__name__)

# Status_id no Kommo (pipeline ATENDE) — após codAgendamento, move pra cá.
ST_AGENDADO = 101507507  # 4-AGENDADO

# Cliente Anthropic (Haiku) cacheado no módulo — criado na 1ª chamada.
_anthropic_client = None


def _get_anthropic_client(api_key: str):
    """Devolve um cliente anthropic.Anthropic singleton (lazy init)."""
    global _anthropic_client
    if _anthropic_client is None:
        import anthropic
        _anthropic_client = anthropic.Anthropic(api_key=api_key)
    return _anthropic_client

EXTRATOR_PROMPT = """Você é um extrator estruturado. Analise APENAS a última mensagem da Lia (agente de WhatsApp) abaixo e determine se ela CONFIRMOU um agendamento de consulta com data E hora específicas.

ÚLTIMA MENSAGEM DA LIA:
{answer}

CONTEXTO (do lead Kommo — pode estar vazio se a conversa acabou de começar):
- Médico: {medico}
- Unidade: {unidade}

REGRA: se o contexto está vazio mas a Lia mencionou o médico/unidade NA MENSAGEM, EXTRAIA da mensagem. Médicos válidos: "Dra. Karla Delalibera" (ou "Dra. Karla Delalíbera"), "Dr. Fabricio Freitas" (ou "Dr. Fabrício Freitas"). Unidades válidas: "Asa Norte", "Águas Claras".

Retorne APENAS um JSON válido (sem markdown, sem explicação).

Se a Lia CONFIRMOU um agendamento específico (mencionou data E hora exatas, p.ex. "confirmado para segunda 20/07 às 09:00"), retorne:
{{"agendamento_confirmado": true, "data_iso": "YYYY-MM-DD", "hora": "HH:MM", "medico": "Dra. Karla Delalibera", "unidade": "Águas Claras"}}

Os campos `medico` e `unidade` são OBRIGATÓRIOS no retorno positivo. Se você não consegue determinar nenhum dos dois, retorne agendamento_confirmado=false.

Se a Lia NÃO confirmou (ainda está perguntando preferência, só ofereceu opções sem escolha, transferiu pra humano, ou disse "equipe vai confirmar"), retorne:
{{"agendamento_confirmado": false}}

JSON:"""


def _parse_extractor_response(raw: str) -> Optional[dict]:
    """Limpa markdown ao redor do JSON e devolve dict ou None."""
    if not raw:
        return None
    raw = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.IGNORECASE)
    raw = re.sub(r"\s*```$", "", raw)
    try:
        return json.loads(raw)
    except Exception:  # noqa: BLE001
        return None


def detectar_agendamento_confirmado(
    answer: str,
    caller_context: dict,
    anthropic_client: Any,
    haiku_model: str,
) -> Optional[dict]:
    """Analisa a resposta da Lia. Se confirmou agendamento, devolve dict
    com {data_iso, hora, medico, unidade, cod_agenda}. Caso contrário, None.
    """
    if not answer or not answer.strip():
        return None
    known = (caller_context or {}).get("known") or {}
    medico_ctx = (known.get("medico") or "").strip()
    unidade_ctx = (known.get("unidade") or "").strip()
    # ANTES: abortava aqui se medico_ctx estivesse vazio. Mas isso bloqueava
    # gravação Medware sempre que paciente novo definia médico DURANTE a
    # conversa (sync Kommo é assíncrono → caller_context não tem o médico).
    # Origem: lead 24038029 (29/05/2026) Lia confirmou agendamento, Medware
    # nunca foi chamado, atendente humano teve que gravar manualmente.
    # Solução: deixar o Haiku extrair médico/unidade do próprio texto da Lia.

    prompt = EXTRATOR_PROMPT.format(
        answer=answer.strip()[:2000],
        medico=medico_ctx or "(não definido — extraia da mensagem da Lia)",
        unidade=unidade_ctx or "(não definida — extraia da mensagem da Lia)",
    )
    try:
        resp = anthropic_client.messages.create(
            model=haiku_model,
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = ""
        if resp and getattr(resp, "content", None):
            for block in resp.content:
                if getattr(block, "type", "") == "text":
                    raw = block.text or ""
                    break
        data = _parse_extractor_response(raw)
        if not data or not data.get("agendamento_confirmado"):
            return None
        data_iso = data.get("data_iso")
        hora = data.get("hora")
        if not data_iso or not hora:
            return None
        try:
            datetime.strptime(data_iso, "%Y-%m-%d")
            datetime.strptime(hora, "%H:%M")
        except ValueError:
            log.warning("detector agendamento: data/hora inválidas %s %s", data_iso, hora)
            return None
        # Tenta casar cod_agenda do slot apresentado anteriormente.
        cod_agenda = 0
        for slot in (caller_context.get("agenda") or []):
            if slot.get("data_iso") == data_iso and slot.get("hora") == hora:
                cod_agenda = int(slot.get("cod_agenda") or 0)
                break
        # Resolução de médico/unidade: ctx > Haiku-extraído > erro
        medico_final = medico_ctx or (data.get("medico") or "").strip()
        unidade_final = unidade_ctx or (data.get("unidade") or "").strip()
        if not medico_final:
            log.warning(
                "detector agendamento: confirmado mas sem médico (ctx vazio E "
                "Haiku não extraiu). answer=%r", answer[:200],
            )
            return None
        log.info(
            "detector agendamento: confirmado %s %s (medico=%s, unidade=%s, "
            "cod_agenda=%s, fonte_medico=%s)",
            data_iso, hora, medico_final, unidade_final, cod_agenda,
            "ctx" if medico_ctx else "haiku-extracao",
        )
        return {
            "data_iso": data_iso,
            "hora": hora,
            "medico": medico_final,
            "unidade": unidade_final,
            "cod_agenda": cod_agenda,
        }
    except Exception as e:  # noqa: BLE001
        log.warning("detector agendamento erro: %s", e)
        return None


def executar_agendamento(
    decision: dict,
    caller_context: dict,
    medware: Any,
    kommo: Any,
) -> dict:
    """Chama medware.criar_agendamento e atualiza Kommo em sucesso.

    Retorna dict: {ok, cod_agendamento?, lead_id?, motivo?}
    """
    from .medware import MEDICO_CODES, UNIDADE_CODES, _code_lookup

    known = (caller_context or {}).get("known") or {}
    cod_medico = _code_lookup(MEDICO_CODES, decision.get("medico"))
    cod_unidade = _code_lookup(UNIDADE_CODES, decision.get("unidade"))
    if not cod_medico:
        return {"ok": False, "motivo": "medico_nao_mapeado",
                "medico": decision.get("medico")}

    data_hora = f"{decision['data_iso']}T{decision['hora']}"
    convenio = (known.get("convenio") or "").strip()
    nome = (known.get("nome_paciente") or caller_context.get("name") or "").strip()
    cpf = (known.get("cpf") or "").strip()
    data_nasc = (known.get("data_nascimento") or "").strip()
    celular = (known.get("telefone") or "").strip()

    result = medware.criar_agendamento(
        cod_medico=cod_medico,
        cod_unidade=cod_unidade,
        cod_agenda=int(decision.get("cod_agenda") or 0),
        data_hora=data_hora,
        nome=nome,
        cpf=cpf,
        data_nascimento=data_nasc,
        celular=celular,
        convenio=convenio if convenio else None,
    )
    if not result.get("ok"):
        log.warning("medware criar_agendamento falhou: %s", result)
        _lid = (caller_context or {}).get("lead_id")
        if _lid and kommo:
            try:
                kommo.update_lead_status(int(_lid), 106563343)
                _nota = "GRAVACAO MEDWARE FALHOU. motivo=" + str(result.get('motivo')) + " detalhe=" + str(result.get('detalhe'))[:200] + " data=" + str(decision.get('data_iso')) + " hora=" + str(decision.get('hora')) + " medico=" + str(decision.get('medico')) + " unidade=" + str(decision.get('unidade')) + ". ACAO HUMANA: confirmar manualmente no Medware."
                kommo.add_note(int(_lid), _nota)
                log.info("Gap 5: lead %s -> 0-HUMANO + nota", _lid)
            except Exception as _e:
                log.warning("Gap 5 fallback erro: %s", _e)
        return {"ok": False, "motivo": result.get("motivo"),
                "detalhe": result.get("detalhe")}

    cod_ag = result.get("cod_agendamento")
    lead_id = (caller_context or {}).get("lead_id")
    log.info("agendamento criado: codAgendamento=%s lead=%s", cod_ag, lead_id)

    # Move lead Kommo para 4-AGENDADO (Gap 3).
    if lead_id and cod_ag:
        try:
            kommo.update_lead_status(int(lead_id), ST_AGENDADO)
            log.info("kommo lead %s -> 4-AGENDADO", lead_id)
        except Exception as e:  # noqa: BLE001
            log.warning("kommo move 4-AGENDADO falhou (%s): %s", lead_id, e)

        # Carimba codAgendamento no campo do Kommo (Gap 4) — best effort.
        # Só funciona se o campo "cod_agendamento" estiver mapeado em update_lead_fields.
        try:
            kommo.update_lead_fields(int(lead_id), {"cod_agendamento": cod_ag})
        except Exception as e:  # noqa: BLE001
            log.warning("kommo cod_agendamento falhou (%s): %s", lead_id, e)

    return {"ok": True, "cod_agendamento": cod_ag, "lead_id": lead_id}


def detectar_e_executar_safely(
    answer: str,
    caller_context: dict,
    medware: Any,
    kommo: Any,
    anthropic_api_key: str,
    haiku_model: str,
) -> Optional[dict]:
    """Entry-point chamado pelo pipeline (em thread).

    Detecta agendamento confirmado e, se houver, executa.
    Captura qualquer exceção — nunca propaga.
    """
    try:
        client = _get_anthropic_client(anthropic_api_key)
        decision = detectar_agendamento_confirmado(
            answer, caller_context, client, haiku_model,
        )
        if not decision:
            return None
        if not medware or not kommo:
            log.warning("agendamento detectado mas medware/kommo indisponíveis")
            return None
        return executar_agendamento(decision, caller_context, medware, kommo)
    except Exception as e:  # noqa: BLE001
        log.exception("detectar_e_executar_safely falhou: %s", e)
        return None
