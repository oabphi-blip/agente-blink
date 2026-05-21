"""Motor de reativação de leads frios.

Percorre o funil ATENDE buscando leads parados nas etapas frias
(0-ETAPA ENTRADA, 1.LEADS FRIO, 2-AGENDAR, 3.REAGENDAR, 5.1-NO-SHOW) e
dispara uma mensagem de retomada — UMA de cada vez, em ritmo controlado.

SEGURANÇA — disparo desligado por padrão. São duas travas:
  - reactivation_enabled=False  → o motor nem roda.
  - reactivation_dry_run=True   → o motor roda, escolhe o lead e monta a
    mensagem, mas NÃO envia nada: apenas registra o que enviaria.
  Uma mensagem real só sai para o paciente com reactivation_enabled=True
  E reactivation_dry_run=False ao mesmo tempo.

RITMO (tudo configurável em settings):
  - só horário comercial (seg–sex, faixa de horas BRT)
  - teto diário de disparos
  - intervalo mínimo entre disparos

COLABORAÇÃO HUMANA: cada lead é ativado UMA única vez (dedup persistente
em Redis). Quando o paciente responde, a Lia conduz a triagem normal; se
um atendente humano assume o chat, o próprio Kommo desliga a IA ali.

CADÊNCIA: o ciclo é acionado pelo endpoint POST /reactivation/tick — um
agendamento externo (cron do Easypanel ou tarefa agendada) chama esse
endpoint a cada N minutos. Cada chamada processa no máximo 1 lead.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

import httpx

log = logging.getLogger(__name__)
_TZ = ZoneInfo("America/Sao_Paulo")

_SEM_CONVENIO = {
    "", "não se aplica", "nao se aplica", "particular",
    "sem convênio", "sem convenio",
}


def _convo_key_from_phone(phone: str) -> str:
    """Mesma normalização do webhook: só dígitos, sem o 9 extra de celular BR.

    Garante que a mensagem de reativação caia no MESMO histórico que a
    resposta do paciente vai usar quando ele responder pelo WhatsApp.
    """
    digits = "".join(c for c in (phone or "") if c.isdigit())
    if digits.startswith("55") and len(digits) == 13 and digits[4] == "9":
        digits = digits[:4] + digits[5:]
    return digits or (phone or "")


def _first_name(full: str) -> str:
    if not full or not full.strip():
        return ""
    return full.strip().split()[0].capitalize()


# Etapas frias do funil ATENDE — usadas para escolher a ABORDAGEM da mensagem
_ST_NO_SHOW = 106184983    # 5.1-NO-SHOW (ATIVAR)
_ST_REAGENDAR = 106184631  # 3.REAGENDAR
_ST_AGENDAR = 102560495    # 2-AGENDAR


def build_message(
    name: str, convenio: Optional[str], status_id: Optional[int] = None,
) -> str:
    """Mensagem de retomada com ABORDAGEM ESCOLHIDA CONFORME O CONTEXTO do lead.

    A abordagem varia pela etapa do funil (quem não compareceu recebe um tom
    de remarcação acolhedora; quem parou perto de fechar recebe um empurrão
    direto; lead frio recebe uma retomada leve) e é modulada pelo convênio.
    O objetivo é impulsionar a conversão em agendamento.

    Tom da Lia: cordial, sem palavras proibidas, termina com pergunta fechada.
    """
    nome = _first_name(name)
    saud = f"Olá, {nome}!" if nome else "Olá!"
    conv = (convenio or "").strip()
    tem_convenio = bool(conv) and conv.lower() not in _SEM_CONVENIO

    # Abordagem conforme a etapa do funil
    if status_id == _ST_NO_SHOW:
        intro = (
            "Notei que não conseguimos concluir a sua consulta no dia "
            "marcado — acontece, e eu quero ajudar a resolver."
        )
        cta = "Posso remarcar para um horário melhor para você?"
    elif status_id == _ST_REAGENDAR:
        intro = "Estou retomando o seu contato para reagendar a sua consulta."
        cta = "Me diga um dia e turno de preferência que eu já organizo."
    elif status_id == _ST_AGENDAR:
        intro = "Faltou pouco para concluir o seu agendamento na Blink."
        cta = "Posso reservar um horário para você? É só me dizer o melhor dia."
    else:  # 0-ETAPA ENTRADA, 1.LEADS FRIO e demais
        intro = "Estou retomando o nosso contato para cuidar da sua consulta."
        cta = "Posso verificar uma data para você?"

    disponibilidade = (
        f"Atendemos pelo {conv} e temos horários próximos."
        if tem_convenio else "Temos horários próximos."
    )
    return f"{saud} Aqui é a Lia, da Blink Oftalmologia. {intro} {disponibilidade} {cta}"


@dataclass
class ReactivationReport:
    ran: bool
    action: str          # 'sent' | 'dry_run' | 'skipped'
    reason: str = ""
    lead_id: Optional[int] = None
    lead_name: Optional[str] = None
    message: Optional[str] = None
    daily_count: int = 0

    def as_dict(self) -> dict:
        return {
            "ran": self.ran,
            "action": self.action,
            "reason": self.reason,
            "lead_id": self.lead_id,
            "lead_name": self.lead_name,
            "message": self.message,
            "daily_count": self.daily_count,
        }


class ReactivationEngine:
    """Motor de reativação. Um `tick()` processa no máximo um lead."""

    def __init__(self, settings, kommo, evolution, store):
        self.s = settings
        self.kommo = kommo
        self.evolution = evolution
        self.store = store
        self._redis = getattr(store, "_redis", None)
        # Fallback em memória (não sobrevive a restart — Redis é o correto)
        self._mem_done: set[int] = set()
        self._mem_count: dict[str, int] = {}
        self._mem_last: float = 0.0

    # ------------------------------------------------- estado (Redis/memória)

    def _today(self) -> str:
        return datetime.now(_TZ).strftime("%Y-%m-%d")

    def _is_done(self, lead_id: int) -> bool:
        if self._redis is not None:
            try:
                return bool(self._redis.exists(f"blink:react:done:{lead_id}"))
            except Exception:  # noqa: BLE001
                pass
        return lead_id in self._mem_done

    def _mark_done(self, lead_id: int) -> None:
        if self._redis is not None:
            try:
                self._redis.set(f"blink:react:done:{lead_id}", "1", ex=90 * 86400)
                return
            except Exception:  # noqa: BLE001
                pass
        self._mem_done.add(lead_id)

    def _daily_count(self) -> int:
        day = self._today()
        if self._redis is not None:
            try:
                v = self._redis.get(f"blink:react:count:{day}")
                return int(v) if v else 0
            except Exception:  # noqa: BLE001
                pass
        return self._mem_count.get(day, 0)

    def _incr_daily(self) -> None:
        day = self._today()
        if self._redis is not None:
            try:
                k = f"blink:react:count:{day}"
                self._redis.incr(k)
                self._redis.expire(k, 2 * 86400)
                return
            except Exception:  # noqa: BLE001
                pass
        self._mem_count[day] = self._mem_count.get(day, 0) + 1

    def _last_send(self) -> float:
        if self._redis is not None:
            try:
                v = self._redis.get("blink:react:last")
                return float(v) if v else 0.0
            except Exception:  # noqa: BLE001
                pass
        return self._mem_last

    def _set_last_send(self, ts: float) -> None:
        if self._redis is not None:
            try:
                self._redis.set("blink:react:last", str(ts))
                return
            except Exception:  # noqa: BLE001
                pass
        self._mem_last = ts

    # ------------------------------------------------- Slack (log opcional)

    def _slack(self, text: str) -> None:
        url = getattr(self.s, "slack_webhook_url", "") or ""
        if not url:
            return
        try:
            with httpx.Client(timeout=8.0) as c:
                c.post(url, json={"text": text})
        except Exception as e:  # noqa: BLE001
            log.debug("slack log ignorado: %s", e)

    # ------------------------------------------------- API pública

    def status(self) -> dict:
        s = self.s
        return {
            "enabled": s.reactivation_enabled,
            "dry_run": s.reactivation_dry_run,
            "daily_cap": s.reactivation_daily_cap,
            "daily_count": self._daily_count(),
            "min_interval_min": s.reactivation_min_interval_min,
            "business_hours": (
                f"{s.reactivation_hour_start}h-{s.reactivation_hour_end}h seg-sex BRT"
            ),
            "pipeline_id": s.reactivation_pipeline_id,
            "cold_status_ids": list(s.reactivation_cold_status_ids),
            "slack_log": bool(getattr(s, "slack_webhook_url", "")),
            "kommo_ready": self.kommo is not None,
        }

    def tick(self) -> ReactivationReport:
        """Executa um ciclo: valida travas e processa no máximo 1 lead."""
        s = self.s

        if not s.reactivation_enabled:
            return ReactivationReport(
                False, "skipped", "motor desligado (reactivation_enabled=false)"
            )
        if self.kommo is None:
            return ReactivationReport(False, "skipped", "Kommo não configurado")

        now = datetime.now(_TZ)
        if now.weekday() > 4:
            return ReactivationReport(False, "skipped", "fim de semana — fora do horário")
        if not (s.reactivation_hour_start <= now.hour < s.reactivation_hour_end):
            return ReactivationReport(False, "skipped", "fora do horário comercial")

        count = self._daily_count()
        if count >= s.reactivation_daily_cap:
            return ReactivationReport(
                False, "skipped",
                f"teto diário atingido ({count}/{s.reactivation_daily_cap})",
                daily_count=count,
            )

        elapsed = time.time() - self._last_send()
        if elapsed < s.reactivation_min_interval_min * 60:
            falta = int(s.reactivation_min_interval_min * 60 - elapsed)
            return ReactivationReport(
                False, "skipped",
                f"intervalo mínimo não cumprido (faltam {falta}s)",
                daily_count=count,
            )

        # Busca os leads frios e escolhe o próximo ainda não ativado
        try:
            leads = self.kommo.list_leads_by_status(
                s.reactivation_pipeline_id,
                list(s.reactivation_cold_status_ids),
                limit=200,
            )
        except Exception as e:  # noqa: BLE001
            return ReactivationReport(
                False, "skipped", f"falha ao listar leads frios: {e}",
                daily_count=count,
            )

        target = next((ld for ld in leads if not self._is_done(int(ld["id"]))), None)
        if target is None:
            return ReactivationReport(
                False, "skipped", "nenhum lead frio pendente na fila",
                daily_count=count,
            )

        lead_id = int(target["id"])

        # Contexto do lead: nome + convênio
        name, convenio = "", None
        try:
            ctx = self.kommo.get_caller_context_by_lead(lead_id)
            name = ctx.get("name") or ""
            convenio = (ctx.get("known") or {}).get("convenio")
        except Exception as e:  # noqa: BLE001
            log.warning("react: contexto do lead %s falhou: %s", lead_id, e)

        # Telefone do contato principal
        phone = None
        try:
            phone = self.kommo.get_lead_main_phone(lead_id)
        except Exception as e:  # noqa: BLE001
            log.warning("react: telefone do lead %s falhou: %s", lead_id, e)

        if not phone:
            # Sem telefone não há como ativar — marca done para não travar a fila
            self._mark_done(lead_id)
            return ReactivationReport(
                True, "skipped", "lead sem telefone — pulado",
                lead_id=lead_id, lead_name=name, daily_count=count,
            )

        message = build_message(name, convenio, target.get("status_id"))

        # ---- DRY-RUN: monta tudo mas NÃO envia
        if s.reactivation_dry_run:
            self._mark_done(lead_id)
            self._incr_daily()
            self._set_last_send(time.time())
            log.info(
                "[REATIVACAO dry-run] lead %s (%s) — ENVIARIA: %s",
                lead_id, name or "s/ nome", message,
            )
            self._slack(
                f"[dry-run] Reativação simulada — lead {lead_id} "
                f"({name or 's/ nome'}). Mensagem pronta, nada foi enviado."
            )
            return ReactivationReport(
                True, "dry_run", "modo dry-run — mensagem não enviada",
                lead_id=lead_id, lead_name=name, message=message,
                daily_count=count + 1,
            )

        # ---- LIVE: envia de verdade
        try:
            self.evolution.send_text(number=phone, text=message)
        except Exception as e:  # noqa: BLE001
            return ReactivationReport(
                True, "skipped", f"falha no envio: {e}",
                lead_id=lead_id, lead_name=name, daily_count=count,
            )

        # Registra no histórico para a Lia continuar com contexto na resposta
        try:
            self.store.append(_convo_key_from_phone(phone), "assistant", message)
        except Exception as e:  # noqa: BLE001
            log.debug("react: append histórico ignorado: %s", e)

        # Move o lead para a etapa-alvo (ex.: 2-AGENDAR)
        try:
            self.kommo.update_lead_status(
                lead_id, s.reactivation_target_status_id, s.reactivation_pipeline_id
            )
        except Exception as e:  # noqa: BLE001
            log.warning("react: mover etapa do lead %s falhou: %s", lead_id, e)

        self._mark_done(lead_id)
        self._incr_daily()
        self._set_last_send(time.time())
        log.info("[REATIVACAO] lead %s (%s) ativado", lead_id, name or "s/ nome")
        self._slack(
            f"Reativação enviada — lead {lead_id} ({name or 's/ nome'}). "
            f"{self._daily_count()}/{s.reactivation_daily_cap} hoje."
        )
        return ReactivationReport(
            True, "sent", "mensagem de reativação enviada",
            lead_id=lead_id, lead_name=name, message=message,
            daily_count=count + 1,
        )
