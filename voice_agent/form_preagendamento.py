"""
Bug C-132 (12/08/2026) — Endpoint /admin/form-preagendamento

Recebe dados do Google Form "Pré-Agendamento Blink Oftalmologia" e:
1. Localiza o lead no Kommo pelo número de WhatsApp
2. Atualiza campos custom: nome, data_nasc, CPF, convênio, unidade, motivo
3. Adiciona nota para a equipe humana
4. Na próxima mensagem do paciente, enriquecimento_ctx já vê os campos
   preenchidos → C-125 não dispara → agente pula coleta e oferece slots

SETUP:
- Formulário: https://docs.google.com/forms/d/1V2q8fcyPUm7CRBAImGzZVmqCP7353PclCjRllx8tMDA/edit
- Rodar SETUP_FORM_BLINK.gs no Apps Script do formulário (configura campos + trigger)
- O trigger chama este endpoint via UrlFetchApp.fetch() em cada envio

Toggle: sempre ativo (sem toggle — é endpoint, não bypass inline).
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Optional

log = logging.getLogger(__name__)

# ─── Mapeamento convênio Google Form → enum Kommo ──────────────────────────────

_CONVENIO_MAP = {
    "sem convênio":             "Não se aplica",
    "pagar particular":         "Não se aplica",
    "anafe":                    "Anafe",
    "bacen":                    "Bacen",
    "care plus":                "Care Plus",
    "casec":                    "Casec (Codevasf)",
    "casembrapa":               "Casembrapa _ Embrapa",
    "conab":                    "Conab",
    "e-vida":                   "E-vida (Luminar)",
    "luminar":                  "E-vida (Luminar)",
    "fascal":                   "Fascal",
    "omint":                    "Omint",
    "pf saúde":                 "PF Saúde",
    "pf saude":                 "PF Saúde",
    "plas":                     "PLAS/JMU (STM)",
    "plan assiste":             "Plan Assiste - MPF (MPU)",
    "mpu":                      "Plan Assiste - MPF (MPU)",
    "prosaúde câmara":          "PróSaúde (Câmara dos Deputados)",
    "câmara dos deputados":     "PróSaúde (Câmara dos Deputados)",
    "pro ser stj":              "Pro ser STJ",
    "proasa":                   "Proasa",
    "saúde caixa":              "Saúde Caixa",
    "saude caixa":              "Saúde Caixa",
    "petrobrás":                "Petrobrás (Saúde Petrobrás)",
    "petrobras":                "Petrobrás (Saúde Petrobrás)",
    "serpro":                   "Serpro",
    "sis senado":               "SIS Senado",
    "stf":                      "STF-Med",
    "tjdft":                    "TJDFT Pró-Saúde",
    "tre":                      "TRE",
    "trf":                      "TRF Pró-Social",
    "trt":                      "TRT",
    "tst":                      "TST Saúde",
}


def _normalizar_convenio(texto: str) -> Optional[str]:
    """Mapeia texto livre do formulário para enum exato do Kommo."""
    if not texto:
        return None
    t = texto.lower().strip()
    for chave, enum in _CONVENIO_MAP.items():
        if chave in t:
            return enum
    if "outro" in t:
        return None  # não mapeia, humano verifica
    return None


def _normalizar_unidade(texto: str) -> Optional[str]:
    """Mapeia texto do formulário para 'Asa Norte' ou 'Águas Claras'."""
    if not texto:
        return None
    t = texto.lower()
    if "asa norte" in t:
        return "Asa Norte"
    if "águas claras" in t or "aguas claras" in t:
        return "Águas Claras"
    return None  # sem preferência


def _normalizar_whatsapp(numero: str) -> str:
    """Remove formatação e garante +55 + DDD + número (13 dígitos)."""
    if not numero:
        return ""
    digitos = re.sub(r"\D", "", numero)
    if digitos.startswith("55"):
        return "+" + digitos
    if len(digitos) == 11:
        return "+55" + digitos
    if len(digitos) == 10:
        return "+55" + digitos
    return "+" + digitos


# ─── Função principal chamada pelo endpoint ────────────────────────────────────

def processar_form_preagendamento(
    payload: dict,
    kommo_client,
    redis_client=None,
) -> dict:
    """
    Processa dados vindos do Google Form e atualiza o lead no Kommo.

    Args:
        payload: dict com campos do formulário (whatsapp, nome_paciente, etc.)
        kommo_client: instância de KommoClient
        redis_client: opcional, para gravar flag de prioridade

    Returns:
        dict com {ok, lead_id, campos_atualizados, erros}
    """
    resultado = {"ok": False, "lead_id": None, "campos_atualizados": [], "erros": []}

    try:
        whatsapp = _normalizar_whatsapp(payload.get("whatsapp", ""))
        if not whatsapp or len(whatsapp) < 12:
            resultado["erros"].append("WhatsApp inválido ou ausente")
            return resultado

        # 1. Localiza o lead pelo telefone
        lead_id = kommo_client.find_lead_id_by_phone(whatsapp)
        if not lead_id:
            log.warning(
                "[C-132] formulário recebido mas lead não encontrado para %s", whatsapp
            )
            resultado["erros"].append(f"Lead não encontrado para {whatsapp}")
            return resultado

        resultado["lead_id"] = lead_id
        log.info("[C-132] formulário → lead %s (%s)", lead_id, whatsapp)

        # 2. Monta campos para atualizar em known (via nota no Kommo)
        nome_contato   = payload.get("nome_contato", "").strip()
        nome_paciente  = payload.get("nome_paciente", "").strip()
        data_nasc      = payload.get("data_nascimento", "").strip()
        cpf            = re.sub(r"\D", "", payload.get("cpf", ""))
        motivo         = payload.get("motivo", "").strip()
        observacoes    = payload.get("observacoes", "").strip()

        convenio_raw   = payload.get("convenio", "")
        unidade_raw    = payload.get("unidade", "")

        convenio_enum  = _normalizar_convenio(convenio_raw)
        unidade_enum   = _normalizar_unidade(unidade_raw)

        # 3. Atualiza campos custom no Kommo (os que temos field_id)
        campos_update = {}

        if convenio_enum:
            campos_update["convenio"] = convenio_enum
            resultado["campos_atualizados"].append("convenio")

        if unidade_enum:
            campos_update["unidade"] = unidade_enum
            resultado["campos_atualizados"].append("unidade")

        if campos_update:
            try:
                kommo_client.update_lead_fields(lead_id, campos_update)
            except Exception as e_upd:
                log.warning("[C-132] update_lead_fields falhou: %s", e_upd)
                resultado["erros"].append(f"update_lead_fields: {e_upd}")

        # 4. Adiciona nota estruturada (lida pelo enriquecimento_ctx)
        ts = datetime.now().strftime("%d/%m %H:%M")
        linhas = [f"📋 [FORM C-132 {ts}] Dados via Google Form:"]

        if nome_contato:
            linhas.append(f"• Contato: {nome_contato}")
        if nome_paciente:
            linhas.append(f"• Paciente: {nome_paciente}")
        if data_nasc:
            linhas.append(f"• Data nasc: {data_nasc}")
        if cpf:
            linhas.append(f"• CPF: {cpf}")
        if convenio_raw:
            linhas.append(f"• Convênio: {convenio_raw}")
        if unidade_raw:
            linhas.append(f"• Unidade pref: {unidade_raw}")
        if motivo:
            linhas.append(f"• Motivo: {motivo}")
        if observacoes:
            linhas.append(f"• Obs: {observacoes}")

        linhas.append("")
        linhas.append("⚡ Prioridade: agente pode ofertar slots diretamente na próxima mensagem.")

        nota_texto = "\n".join(linhas)

        try:
            kommo_client.add_note(lead_id, nota_texto)
            resultado["campos_atualizados"].append("nota_kommo")
        except Exception as e_nota:
            log.warning("[C-132] add_note falhou: %s", e_nota)
            resultado["erros"].append(f"add_note: {e_nota}")

        # 5. Grava flag Redis para próximo turn do agente saber que há dados do form
        if redis_client:
            try:
                key = f"blink:c132_form_dados:{lead_id}"
                import json
                dados_json = json.dumps({
                    "nome_contato": nome_contato,
                    "nome_paciente": nome_paciente,
                    "data_nasc": data_nasc,
                    "cpf": cpf,
                    "convenio": convenio_enum or convenio_raw,
                    "unidade": unidade_enum or unidade_raw,
                    "motivo": motivo,
                })
                redis_client.setex(key, 7 * 24 * 3600, dados_json)  # TTL 7 dias
                resultado["campos_atualizados"].append("redis_flag")
            except Exception as e_redis:
                log.warning("[C-132] redis setex falhou: %s", e_redis)

        resultado["ok"] = True
        log.info(
            "[C-132] lead %s atualizado — campos: %s",
            lead_id, resultado["campos_atualizados"]
        )
        return resultado

    except Exception as exc:
        log.exception("[C-132] processar_form_preagendamento falhou: %s", exc)
        resultado["erros"].append(str(exc))
        return resultado
