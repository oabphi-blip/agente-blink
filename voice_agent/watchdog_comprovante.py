"""
Bug C-122 (11/08/2026) — Watchdog comprovante Pix pós-C-114 reserva.
=====================================================================
Quando paciente escolhe "reserva garantida" (C-114), pipeline grava:
  blink:c114_aguardando_comprovante:{lead_id}  TTL 7d

Quando paciente envia comprovante, C-116 detecta e grava:
  blink:c116_comprovante_detectado:{lead_id}   TTL 2h

Problema: paciente esquece de enviar o comprovante. Slot fica em
limbo — reserva existe mas sem confirmação financeira.

Este watchdog varre o Redis a cada N min (default 60), detecta leads
com c114 ativo há >2h sem c116, e envia lembrete WhatsApp.

Dedup: blink:c122_lembrete_enviado:{lead_id} (TTL 7d) impede repetição.

Liga via WATCHDOG_COMPROVANTE_ENABLED=1 (default OFF).
Fail-open: qualquer erro em lead individual → skip, próximo lead.

Endpoint: POST /admin/watchdog-comprovante-tick?secret=...&dry_run=1
Toggle: WATCHDOG_COMPROVANTE_ENABLED (default OFF para rollout gradual).
Rollback: WATCHDOG_COMPROVANTE_ENABLED=0 → Implantar.
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Optional

log = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Redis keys (mirrors C-114 / C-116)
# ─────────────────────────────────────────────────────────────────────────────
_KEY_AGUARDANDO = "blink:c114_aguardando_comprovante:{lead_id}"
_KEY_DETECTADO  = "blink:c116_comprovante_detectado:{lead_id}"
_KEY_LEMBRETE   = "blink:c122_lembrete_enviado:{lead_id}"

_TTL_AGUARDANDO_SEG = 7 * 24 * 3600   # 7 dias — mesmo TTL do C-114
_TTL_LEMBRETE_SEG   = 7 * 24 * 3600   # 7 dias — não lembrar de novo
_LIMIAR_LEMBRETE_SEG = 2 * 3600        # 2h sem comprovante → lembrar


# ─────────────────────────────────────────────────────────────────────────────
# Toggle
# ─────────────────────────────────────────────────────────────────────────────
def esta_habilitado() -> bool:
    return os.environ.get("WATCHDOG_COMPROVANTE_ENABLED", "0").strip().lower() in (
        "1", "true", "yes", "on",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Mensagem de lembrete
# ─────────────────────────────────────────────────────────────────────────────
_MSG_LEMBRETE_COM_NOME = (
    "{primeiro}, tudo bem? 😊\n\n"
    "Vi que você escolheu garantir sua vaga — ótima decisão! "
    "Ainda estamos aguardando o comprovante do Pix para confirmar o horário.\n\n"
    "É só enviar a foto ou screenshot do comprovante aqui no WhatsApp "
    "que confirmo imediatamente! 📲"
)

_MSG_LEMBRETE_SEM_NOME = (
    "Olá! 😊\n\n"
    "Vi que você escolheu garantir sua vaga — ótima decisão! "
    "Ainda estamos aguardando o comprovante do Pix para confirmar o horário.\n\n"
    "É só enviar a foto ou screenshot do comprovante aqui no WhatsApp "
    "que confirmo imediatamente! 📲"
)


def _montar_msg_lembrete(nome: str = "") -> str:
    primeiro = (nome or "").strip().split()[0].strip() if nome else ""
    if primeiro and not any(c.isdigit() for c in primeiro) and len(primeiro) >= 2:
        return _MSG_LEMBRETE_COM_NOME.format(primeiro=primeiro.capitalize())
    return _MSG_LEMBRETE_SEM_NOME


# ─────────────────────────────────────────────────────────────────────────────
# Varredura Redis
# ─────────────────────────────────────────────────────────────────────────────
def _varrer_leads_pendentes(redis_client) -> list[dict]:
    """
    Retorna lista de {lead_id, elapsed_seg} para leads com comprovante
    aguardando há >2h sem c116 detectado e sem lembrete já enviado.
    """
    pendentes = []
    try:
        cursor = 0
        while True:
            cursor, keys = redis_client.scan(
                cursor, match="blink:c114_aguardando_comprovante:*", count=100
            )
            for key in keys:
                key_str = key.decode() if isinstance(key, bytes) else str(key)
                try:
                    lead_id = int(key_str.rsplit(":", 1)[-1])
                except (ValueError, IndexError):
                    continue

                # Comprovante já chegou → skip (não é candidato)
                if redis_client.exists(_KEY_DETECTADO.format(lead_id=lead_id)):
                    continue

                # Calcular tempo decorrido via TTL residual
                ttl = redis_client.ttl(key_str)
                if ttl < 0:
                    continue  # sem TTL ou expirada
                elapsed = _TTL_AGUARDANDO_SEG - ttl
                if elapsed >= _LIMIAR_LEMBRETE_SEG:
                    pendentes.append({"lead_id": lead_id, "elapsed_seg": int(elapsed)})

            if cursor == 0:
                break
    except Exception as e:  # noqa: BLE001
        log.warning("[C-122 WATCHDOG] varrer_leads_pendentes falhou: %s", e)

    return pendentes


# ─────────────────────────────────────────────────────────────────────────────
# Resultado
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class ResultadoWatchdogComprovante:
    varridos: int = 0
    candidatos: int = 0
    enviados: int = 0
    ja_dedup: int = 0
    erros: int = 0
    detalhes: list = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "varridos": self.varridos,
            "candidatos": self.candidatos,
            "enviados": self.enviados,
            "ja_dedup": self.ja_dedup,
            "erros": self.erros,
            "detalhes": self.detalhes,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Tick principal
# ─────────────────────────────────────────────────────────────────────────────
def tick(
    kommo_client,
    wa_cloud_client,
    redis_client,
    dry_run: bool = True,
    max_leads: int = 20,
    limiar_seg: int = _LIMIAR_LEMBRETE_SEG,
) -> ResultadoWatchdogComprovante:
    """
    Executa uma varredura: detecta leads com comprovante pendente >2h
    e envia lembrete WhatsApp (exceto em dry_run).

    Parâmetros:
        kommo_client  — KommoClient para buscar telefone/nome + add_note
        wa_cloud_client — WhatsAppCloudClient para send_text
        redis_client  — Redis para ler flags + gravar dedup
        dry_run       — se True, NÃO envia nem grava (apenas loga)
        max_leads     — cap de envios por tick
        limiar_seg    — tempo mínimo aguardando sem comprovante (default 2h)
    """
    res = ResultadoWatchdogComprovante()

    if redis_client is None:
        log.warning("[C-122 WATCHDOG] redis_client None — abortando tick")
        return res

    # 1. Varrer Redis
    global _LIMIAR_LEMBRETE_SEG  # noqa: PLW0603
    _original_limiar = _LIMIAR_LEMBRETE_SEG
    _LIMIAR_LEMBRETE_SEG = limiar_seg
    try:
        pendentes = _varrer_leads_pendentes(redis_client)
    finally:
        _LIMIAR_LEMBRETE_SEG = _original_limiar

    res.varridos = len(pendentes)
    res.candidatos = len(pendentes)

    if not pendentes:
        return res

    # 2. Processar candidatos (cap max_leads)
    for item in pendentes[:max_leads]:
        lead_id = item["lead_id"]
        elapsed_h = round(item["elapsed_seg"] / 3600, 1)
        detalhe: dict[str, Any] = {
            "lead_id": lead_id,
            "elapsed_h": elapsed_h,
            "acao": None,
        }

        try:
            # 2a. Dedup (checagem final — outro processo pode ter enviado entre scan e agora)
            lembrete_key = _KEY_LEMBRETE.format(lead_id=lead_id)
            if redis_client.exists(lembrete_key):
                res.ja_dedup += 1
                detalhe["acao"] = "dedup"
                res.detalhes.append(detalhe)
                continue

            # 2b. Buscar telefone + nome do Kommo
            contato = None
            telefone = None
            nome = ""
            if kommo_client is not None:
                try:
                    contato = kommo_client.get_lead_main_contact(lead_id)
                    if contato:
                        telefone = contato.get("telefone")
                        nome = contato.get("nome") or ""
                except Exception as _ek:  # noqa: BLE001
                    log.warning("[C-122 WATCHDOG] kommo lead %s erro: %s", lead_id, _ek)

            if not telefone:
                log.warning(
                    "[C-122 WATCHDOG] lead %s sem telefone — skip", lead_id
                )
                detalhe["acao"] = "sem_telefone"
                res.detalhes.append(detalhe)
                continue

            # Normalizar para E.164
            digits = "".join(ch for ch in telefone if ch.isdigit())
            if not digits.startswith("55") and len(digits) <= 11:
                digits = "55" + digits
            to = digits

            # 2c. Montar mensagem
            msg = _montar_msg_lembrete(nome)

            if dry_run:
                log.info(
                    "[C-122 WATCHDOG dry_run] lead=%s tel=%s elapsed=%.1fh msg=%s",
                    lead_id, to, elapsed_h, msg[:60],
                )
                detalhe["acao"] = "dry_run"
                detalhe["telefone"] = to
                detalhe["nome"] = nome
                res.enviados += 1
                res.detalhes.append(detalhe)
                continue

            # 2d. Enviar WhatsApp
            wamid = None
            if wa_cloud_client is not None:
                try:
                    resp_wa = wa_cloud_client.send_text(to=to, text=msg)
                    wamid = (resp_wa.get("messages") or [{}])[0].get("id")
                    log.info(
                        "[C-122 WATCHDOG] lead=%s tel=%s wamid=%s elapsed=%.1fh",
                        lead_id, to, wamid, elapsed_h,
                    )
                except Exception as _ew:  # noqa: BLE001
                    log.warning(
                        "[C-122 WATCHDOG] wa_cloud lead %s erro: %s", lead_id, _ew
                    )
                    res.erros += 1
                    detalhe["acao"] = "wa_erro"
                    detalhe["erro"] = str(_ew)
                    res.detalhes.append(detalhe)
                    continue
            else:
                log.warning("[C-122 WATCHDOG] wa_cloud_client None — skip lead %s", lead_id)
                detalhe["acao"] = "sem_wa_client"
                res.detalhes.append(detalhe)
                continue

            # 2e. Gravar flag de dedup
            try:
                redis_client.setex(lembrete_key, _TTL_LEMBRETE_SEG, "1")
            except Exception as _er:  # noqa: BLE001
                log.warning("[C-122 WATCHDOG] setex lembrete lead %s erro: %s", lead_id, _er)

            # 2f. Nota Kommo
            if kommo_client is not None:
                ts_str = time.strftime("%d/%m %H:%M", time.localtime())
                nota = (
                    f"📲 [LIA C-122 {ts_str}] Lembrete comprovante Pix enviado\n"
                    f"Aguardando há {elapsed_h}h. wamid={wamid or 'N/A'}"
                )
                try:
                    kommo_client.add_note(lead_id=lead_id, text=nota)
                except Exception as _en:  # noqa: BLE001
                    log.warning(
                        "[C-122 WATCHDOG] add_note lead %s erro: %s", lead_id, _en
                    )

            res.enviados += 1
            detalhe["acao"] = "enviado"
            detalhe["telefone"] = to
            detalhe["nome"] = nome
            detalhe["wamid"] = wamid
            res.detalhes.append(detalhe)

        except Exception as e:  # noqa: BLE001
            log.warning("[C-122 WATCHDOG] lead %s erro inesperado: %s", lead_id, e)
            res.erros += 1
            detalhe["acao"] = "erro_inesperado"
            detalhe["erro"] = str(e)
            res.detalhes.append(detalhe)

    return res
