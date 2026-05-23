"""Disparo de unificação — avisa a base que o atendimento é no 8133.

Envia o template aprovado de unificação (atendimento_unificado_oficial)
para os contatos do Kommo, dos MAIS RECENTES para os mais antigos
(hoje, ontem, e assim sucessivamente), em lotes com teto diário.

SEGURANÇA — duas travas, igual à reativação:
  - broadcast_enabled=False → o motor nem roda.
  - broadcast_dry_run=True  → monta tudo mas NÃO envia (apenas registra).
  Envio real só com broadcast_enabled=True E broadcast_dry_run=False.

Cada contato recebe o aviso UMA única vez (dedup persistente em Redis).
Os namespaces de dedup e contagem são SEPARADOS por modo (dry/live):
um teste em dry-run não "consome" os contatos da fila real.

CADÊNCIA: acionado por POST /broadcast/tick — um cron externo chama a
cada N minutos. Cada chamada processa até broadcast_batch_size contatos,
respeitando o teto diário.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from zoneinfo import ZoneInfo

log = logging.getLogger(__name__)
_TZ = ZoneInfo("America/Sao_Paulo")


def _first_name(full: str) -> str:
    if not full or not full.strip():
        return "paciente"
    return full.strip().split()[0].capitalize()


@dataclass
class BroadcastReport:
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


class BroadcastEngine:
    """Motor do disparo de unificação. Um tick() processa um lote."""

    # Teto de páginas varridas por tick (40 x 250 = 10.000 leads).
    MAX_PAGES = 40

    def __init__(self, settings, kommo, wa_cloud, store):
        self.s = settings
        self.kommo = kommo
        self.wa_cloud = wa_cloud
        self.store = store
        self._redis = getattr(store, "_redis", None)
        self._mem_done: set[str] = set()
        self._mem_count: dict[str, int] = {}

    # --------------------------------------------- estado (Redis/memória)

    def _today(self) -> str:
        return datetime.now(_TZ).strftime("%Y-%m-%d")

    def _mode(self) -> str:
        # 'dry' e 'live' usam namespaces SEPARADOS: um teste em dry-run
        # não consome os contatos da fila real.
        return "dry" if self.s.broadcast_dry_run else "live"

    def _done_key(self, lead_id: int) -> str:
        return f"blink:bcast:done:{self._mode()}:{lead_id}"

    def _is_done(self, lead_id: int) -> bool:
        if self._redis is not None:
            try:
                return bool(self._redis.exists(self._done_key(lead_id)))
            except Exception:  # noqa: BLE001
                pass
        return f"{self._mode()}:{lead_id}" in self._mem_done

    def _mark_done(self, lead_id: int) -> None:
        if self._redis is not None:
            try:
                self._redis.set(self._done_key(lead_id), "1", ex=180 * 86400)
                return
            except Exception:  # noqa: BLE001
                pass
        self._mem_done.add(f"{self._mode()}:{lead_id}")

    def _daily_count(self) -> int:
        day = self._today()
        if self._redis is not None:
            try:
                v = self._redis.get(f"blink:bcast:count:{self._mode()}:{day}")
                return int(v) if v else 0
            except Exception:  # noqa: BLE001
                pass
        return self._mem_count.get(f"{self._mode()}:{day}", 0)

    def _incr_daily(self, n: int = 1) -> None:
        day = self._today()
        if self._redis is not None:
            try:
                k = f"blink:bcast:count:{self._mode()}:{day}"
                self._redis.incrby(k, n)
                self._redis.expire(k, 2 * 86400)
                return
            except Exception:  # noqa: BLE001
                pass
        key = f"{self._mode()}:{day}"
        self._mem_count[key] = self._mem_count.get(key, 0) + n

    # --------------------------------------------- API pública

    def status(self) -> dict:
        s = self.s
        return {
            "enabled": s.broadcast_enabled,
            "dry_run": s.broadcast_dry_run,
            "mode": self._mode(),
            "template": s.broadcast_template_name,
            "daily_cap": s.broadcast_daily_cap,
            "daily_count": self._daily_count(),
            "batch_size": s.broadcast_batch_size,
            "business_hours": (
                f"{s.broadcast_hour_start}h-{s.broadcast_hour_end}h BRT"
            ),
            "wa_cloud_ready": self.wa_cloud is not None,
            "kommo_ready": self.kommo is not None,
        }

    def _next_targets(self, want: int) -> list[dict]:
        """Varre os leads do Kommo, do mais recente ao mais antigo, e
        devolve até `want` leads ainda não avisados."""
        out: list[dict] = []
        page = 1
        while page <= self.MAX_PAGES and len(out) < want:
            leads = self.kommo.list_leads_recent(limit=250, page=page)
            if not leads:
                break
            for ld in leads:
                if not self._is_done(int(ld["id"])):
                    out.append(ld)
                    if len(out) >= want:
                        break
            page += 1
        return out

    def tick(self, force: bool = False) -> BroadcastReport:
        """Processa um lote do disparo de unificação.

        force=True ignora a trava de horário comercial (uso em teste).
        As travas que protegem o paciente (broadcast_enabled e
        broadcast_dry_run) continuam valendo.
        """
        s = self.s

        if not s.broadcast_enabled:
            return BroadcastReport(
                False, "skipped", "motor desligado (broadcast_enabled=false)"
            )
        if self.kommo is None:
            return BroadcastReport(False, "skipped", "Kommo não configurado")
        if self.wa_cloud is None:
            return BroadcastReport(
                False, "skipped", "WhatsApp Cloud não configurado"
            )
        if not s.broadcast_template_name:
            return BroadcastReport(
                False, "skipped", "broadcast_template_name vazio"
            )

        now = datetime.now(_TZ)
        if not force:
            if not (s.broadcast_hour_start <= now.hour < s.broadcast_hour_end):
                return BroadcastReport(
                    False, "skipped", "fora do horário comercial"
                )

        count = self._daily_count()
        if count >= s.broadcast_daily_cap:
            return BroadcastReport(
                False, "skipped",
                f"teto diário atingido ({count}/{s.broadcast_daily_cap})",
                daily_count=count,
            )

        want = min(s.broadcast_batch_size, s.broadcast_daily_cap - count)
        try:
            targets = self._next_targets(want)
        except Exception as e:  # noqa: BLE001
            return BroadcastReport(
                False, "skipped", f"falha ao listar leads: {e}",
                daily_count=count,
            )
        if not targets:
            return BroadcastReport(
                True, "skipped", "nenhum contato pendente — base concluída",
                daily_count=count,
            )

        sent = 0
        details: list = []
        for ld in targets:
            lead_id = int(ld["id"])
            name = ld.get("name") or ""

            phone = None
            try:
                phone = self.kommo.get_lead_main_phone(lead_id)
            except Exception as e:  # noqa: BLE001
                log.warning("bcast: telefone do lead %s falhou: %s", lead_id, e)

            if not phone:
                # Sem telefone não há como avisar — marca done p/ não travar.
                self._mark_done(lead_id)
                details.append({"lead_id": lead_id, "result": "sem telefone"})
                continue

            # ---- DRY-RUN: registra mas NÃO envia
            if s.broadcast_dry_run:
                self._mark_done(lead_id)
                self._incr_daily()
                sent += 1
                details.append(
                    {"lead_id": lead_id, "name": name, "result": "dry_run"}
                )
                continue

            # ---- LIVE: envia o template pelo 8133
            try:
                self.wa_cloud.send_template(
                    to=phone,
                    name=s.broadcast_template_name,
                    language=s.broadcast_template_lang,
                    body_params=[_first_name(name)],
                )
            except Exception as e:  # noqa: BLE001
                details.append(
                    {"lead_id": lead_id, "result": f"falha: {str(e)[:160]}"}
                )
                continue

            self._mark_done(lead_id)
            self._incr_daily()
            sent += 1
            details.append(
                {"lead_id": lead_id, "name": name, "result": "enviado"}
            )

        action = "dry_run" if s.broadcast_dry_run else "sent"
        log.info(
            "[BROADCAST] tick (%s): %d contato(s) processado(s)", action, sent
        )
        return BroadcastReport(
            True, action, f"{sent} contato(s) processado(s)",
            sent=sent, daily_count=self._daily_count(), details=details,
        )
