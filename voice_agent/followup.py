"""Motor de follow-up pós-valor.

Quando o agente apresenta o valor da consulta e o paciente fica em
silêncio por alguns minutos, dispara UM template de retomada pelo 8133,
para tirar o paciente da inércia. Uma vez por lead.

Marcação: o pipeline chama set_pending() quando a resposta do agente
apresenta o valor, e clear_pending() sempre que o paciente responde.
O motor (tick) varre os marcadores e dispara quando passam do tempo de
silêncio configurado.

SEGURANÇA — duas travas, igual à reativação/broadcast:
  - followup_enabled=False → o motor nem roda.
  - followup_dry_run=True  → monta tudo, mas NÃO envia.

CADÊNCIA: acionado por POST /followup/tick — um cron externo chama a
cada poucos minutos.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from zoneinfo import ZoneInfo

log = logging.getLogger(__name__)
_TZ = ZoneInfo("America/Sao_Paulo")

_PENDING_PREFIX = "blink:followup:pending:"
_DONE_PREFIX = "blink:followup:done:"

# Fallback em memória — pipeline e motor rodam no MESMO processo, então
# um dict de módulo é compartilhado entre eles quando não há Redis.
_MEM_PENDING: dict[str, float] = {}
_MEM_DONE: set[str] = set()

_SEM_CONVENIO = {
    "", "não se aplica", "nao se aplica", "particular",
    "sem convênio", "sem convenio",
}


def _first_name(full: str) -> str:
    if not full or not full.strip():
        return "paciente"
    return full.strip().split()[0].capitalize()


def answer_has_value(answer: str) -> bool:
    """True quando a resposta do agente apresentou o valor da consulta
    (bloco de formas de pagamento: R$ junto de Pix/Cartão)."""
    if not answer:
        return False
    a = answer.lower()
    return ("r$" in a) and ("pix" in a or "cartão" in a or "cartao" in a)


def set_pending(redis, ckey: str) -> None:
    """Arma o marcador de follow-up (o agente apresentou o valor)."""
    if not ckey:
        return
    now = time.time()
    if redis is not None:
        try:
            redis.set(_PENDING_PREFIX + ckey, str(now), ex=26 * 3600)
            return
        except Exception:  # noqa: BLE001
            pass
    _MEM_PENDING[ckey] = now


def clear_pending(redis, ckey: str) -> None:
    """Remove o marcador — o paciente respondeu, não precisa follow-up."""
    if not ckey:
        return
    if redis is not None:
        try:
            redis.delete(_PENDING_PREFIX + ckey)
            return
        except Exception:  # noqa: BLE001
            pass
    _MEM_PENDING.pop(ckey, None)


@dataclass
class FollowupReport:
    ran: bool
    action: str            # 'sent' | 'dry_run' | 'skipped'
    reason: str = ""
    sent: int = 0
    daily_count: int = 0
    details: list = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "ran": self.ran, "action": self.action, "reason": self.reason,
            "sent": self.sent, "daily_count": self.daily_count,
            "details": self.details,
        }


class FollowupEngine:
    """Motor de follow-up pós-valor. Um tick() processa um lote."""

    def __init__(self, settings, kommo, wa_cloud, store):
        self.s = settings
        self.kommo = kommo
        self.wa_cloud = wa_cloud
        self.store = store
        self._redis = getattr(store, "_redis", None)
        self._mem_count: dict[str, int] = {}

    def _today(self) -> str:
        return datetime.now(_TZ).strftime("%Y-%m-%d")

    def _mode(self) -> str:
        return "dry" if self.s.followup_dry_run else "live"

    def _done_key(self, ckey: str) -> str:
        return f"{_DONE_PREFIX}{self._mode()}:{ckey}"

    def _is_done(self, ckey: str) -> bool:
        if self._redis is not None:
            try:
                return bool(self._redis.exists(self._done_key(ckey)))
            except Exception:  # noqa: BLE001
                pass
        return f"{self._mode()}:{ckey}" in _MEM_DONE

    def _mark_done(self, ckey: str) -> None:
        if self._redis is not None:
            try:
                self._redis.set(self._done_key(ckey), "1", ex=7 * 86400)
                return
            except Exception:  # noqa: BLE001
                pass
        _MEM_DONE.add(f"{self._mode()}:{ckey}")

    def _daily_count(self) -> int:
        day = self._today()
        if self._redis is not None:
            try:
                v = self._redis.get(f"blink:followup:count:{self._mode()}:{day}")
                return int(v) if v else 0
            except Exception:  # noqa: BLE001
                pass
        return self._mem_count.get(f"{self._mode()}:{day}", 0)

    def _incr_daily(self) -> None:
        day = self._today()
        if self._redis is not None:
            try:
                k = f"blink:followup:count:{self._mode()}:{day}"
                self._redis.incr(k)
                self._redis.expire(k, 2 * 86400)
                return
            except Exception:  # noqa: BLE001
                pass
        key = f"{self._mode()}:{day}"
        self._mem_count[key] = self._mem_count.get(key, 0) + 1

    def _pending_items(self) -> list[tuple[str, float]]:
        """Lista (conversation_key, timestamp) dos marcadores pendentes."""
        if self._redis is not None:
            out: list[tuple[str, float]] = []
            try:
                for k in self._redis.scan_iter(match=_PENDING_PREFIX + "*"):
                    key = k.decode() if isinstance(k, bytes) else str(k)
                    ckey = key[len(_PENDING_PREFIX):]
                    v = self._redis.get(k)
                    try:
                        ts = float(v) if v else 0.0
                    except (TypeError, ValueError):
                        ts = 0.0
                    out.append((ckey, ts))
                return out
            except Exception as e:  # noqa: BLE001
                log.warning("followup scan falhou: %s", e)
                return []
        return list(_MEM_PENDING.items())

    def status(self) -> dict:
        s = self.s
        return {
            "enabled": s.followup_enabled,
            "dry_run": s.followup_dry_run,
            "mode": self._mode(),
            "silence_min": s.followup_silence_min,
            "daily_cap": s.followup_daily_cap,
            "daily_count": self._daily_count(),
            "pending": len(self._pending_items()),
            "template_convenio": s.followup_template_convenio or None,
            "template_particular": s.followup_template_particular or None,
            "wa_cloud_ready": self.wa_cloud is not None,
            "kommo_ready": self.kommo is not None,
        }

    def tick(self, force: bool = False) -> FollowupReport:
        s = self.s

        if not s.followup_enabled:
            return FollowupReport(
                False, "skipped", "motor desligado (followup_enabled=false)"
            )
        if self.wa_cloud is None:
            return FollowupReport(
                False, "skipped", "WhatsApp Cloud não configurado"
            )
        if self.kommo is None:
            return FollowupReport(False, "skipped", "Kommo não configurado")

        count = self._daily_count()
        if count >= s.followup_daily_cap:
            return FollowupReport(
                False, "skipped",
                f"teto diário atingido ({count}/{s.followup_daily_cap})",
                daily_count=count,
            )

        now = time.time()
        threshold = s.followup_silence_min * 60
        due = [
            (ck, ts) for ck, ts in self._pending_items()
            if (now - ts) >= threshold
        ]
        if not due:
            return FollowupReport(
                True, "skipped", "nenhum lead no tempo de follow-up",
                daily_count=count,
            )

        sent = 0
        details: list = []
        for ckey, _ts in due:
            if count + sent >= s.followup_daily_cap:
                break
            if self._is_done(ckey):
                clear_pending(self._redis, ckey)
                continue

            # Encontra o lead e decide o template (convênio x particular)
            convenio, name, phone = None, "", ckey
            try:
                lead_id = self.kommo.find_lead_id_by_phone(ckey)
                if lead_id:
                    ctx = self.kommo.get_caller_context_by_lead(lead_id)
                    name = ctx.get("name") or ""
                    convenio = (ctx.get("known") or {}).get("convenio")
                    p = self.kommo.get_lead_main_phone(lead_id)
                    if p:
                        phone = p
            except Exception as e:  # noqa: BLE001
                log.warning("followup: contexto do lead falhou (%s): %s", ckey, e)

            tem_convenio = (
                bool(convenio)
                and str(convenio).strip().lower() not in _SEM_CONVENIO
            )
            template = (
                s.followup_template_convenio if tem_convenio
                else s.followup_template_particular
            )
            # Fallback: se o template do caso não está configurado, usa o outro.
            template = (
                template or s.followup_template_particular
                or s.followup_template_convenio
            )
            if not template:
                details.append({"ckey": ckey, "result": "sem template configurado"})
                continue

            # ---- DRY-RUN: registra mas NÃO envia
            if s.followup_dry_run:
                self._mark_done(ckey)
                clear_pending(self._redis, ckey)
                self._incr_daily()
                sent += 1
                details.append({
                    "ckey": ckey, "template": template,
                    "convenio": tem_convenio, "result": "dry_run",
                })
                continue

            # ---- LIVE: envia o template pelo 8133
            try:
                self.wa_cloud.send_template(
                    to=phone,
                    name=template,
                    language=s.followup_template_lang,
                    body_params=[_first_name(name)],
                )
            except Exception as e:  # noqa: BLE001
                details.append(
                    {"ckey": ckey, "result": f"falha: {str(e)[:140]}"}
                )
                continue
            self._mark_done(ckey)
            clear_pending(self._redis, ckey)
            self._incr_daily()
            sent += 1
            details.append({
                "ckey": ckey, "template": template,
                "convenio": tem_convenio, "result": "enviado",
            })

        action = "dry_run" if s.followup_dry_run else "sent"
        log.info("[FOLLOWUP] tick (%s): %d processado(s)", action, sent)
        return FollowupReport(
            True, action, f"{sent} follow-up(s) processado(s)",
            sent=sent, daily_count=self._daily_count(), details=details,
        )
