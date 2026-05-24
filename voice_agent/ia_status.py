"""Carimbo do campo "ATIVADO IA?" (id 1260635) nos leads do Kommo.

O campo indica, de relance, se a IA está conduzindo o lead (ATIVADO) ou se
um humano assumiu / a IA foi desligada (DESATIVADO). Assim a equipe pode
FILTRAR a lista de leads por esse status, sem abrir conversa por conversa.

Como o estado é deduzido:
  1. Lead em etapa humana (7-CIRURGIAS, 8-LENTES, 9-FORNECEDORES) → DESATIVADO.
  2. Senão, lê as notas do lead:
       - service_message 'Agentes de IA foram desativados' mais recente que
         a última atividade da Lia → DESATIVADO.
       - atividade da Lia mais recente → ATIVADO.
  3. Sem nenhum sinal nas notas → ATIVADO (a IA está habilitada e
     disponível para responder, apenas ainda não atuou no lead).

DOIS MODOS:
  - sweep periódico: varre só os leads com atividade recente (leve, roda a
    cada X min como tarefa agendada) — pega o desligamento forçado pelo
    Kommo, que o agente não consegue carimbar sozinho.
  - backfill: varre a base inteira uma única vez.

SEGURANÇA: dry_run=True decide tudo e monta o relatório sem gravar nada.
A gravação real só acontece com dry_run=False.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional

log = logging.getLogger(__name__)

# Etapas do funil ATENDE em que a IA fica DESLIGADA (atendimento humano /
# contato fornecedor). Espelha kommo.ST_AGENT_OFF.
ST_AGENT_OFF = frozenset({
    106157139,  # 7-CIRURGIAS ANDAMENTO
    106484343,  # 8-LENTES ANDAMENTO
    106484347,  # 9-FORNECEDORES
})


@dataclass
class IaStatusReport:
    ran: bool
    dry_run: bool
    mode: str = "sweep"
    leads_total: int = 0
    ativado: int = 0
    desativado: int = 0
    skipped: int = 0
    errors: int = 0
    detail: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "ran": self.ran,
            "dry_run": self.dry_run,
            "mode": self.mode,
            "leads_total": self.leads_total,
            "ativado": self.ativado,
            "desativado": self.desativado,
            "skipped": self.skipped,
            "errors": self.errors,
            "detail": self.detail[:200],
        }


@dataclass
class IaStatusEngine:
    """Varre leads do Kommo e carimba o campo 'ATIVADO IA?'."""

    kommo: Any                       # KommoClient
    enabled: bool = False
    dry_run: bool = True
    last_report: Optional[IaStatusReport] = None
    running: bool = False

    def status(self) -> dict:
        return {
            "enabled": self.enabled,
            "dry_run_default": self.dry_run,
            "running": self.running,
            "last_report": (
                self.last_report.as_dict() if self.last_report else None
            ),
        }

    # ------------------------------------------------------ decisão por lead

    def _decide(self, lead: dict) -> Optional[str]:
        """Retorna 'ATIVADO' / 'DESATIVADO' para o lead, ou None se falhar."""
        lead_id = lead.get("id")
        status_id = lead.get("status_id")
        # Etapa humana → IA desligada, sem precisar ler notas.
        if status_id in ST_AGENT_OFF:
            return "DESATIVADO"
        try:
            sig = self.kommo.ia_status_from_notes(lead_id)
        except Exception as e:  # noqa: BLE001
            log.warning("IA status: notas do lead %s falharam: %s", lead_id, e)
            return None
        # Sem sinal nas notas → IA habilitada e disponível.
        return sig or "ATIVADO"

    # ----------------------------------------------------------------- run

    def run(
        self,
        dry_run: Optional[bool] = None,
        mode: str = "sweep",
        max_pages: int = 4,
        page_size: int = 250,
    ) -> IaStatusReport:
        """Varre os leads e carimba o campo.

        mode='sweep'   → só as primeiras `max_pages` páginas (mais recentes).
        mode='backfill'→ base inteira (teto de 60 páginas de segurança).
        """
        dr = self.dry_run if dry_run is None else bool(dry_run)
        rep = IaStatusReport(ran=False, dry_run=dr, mode=mode)
        if not self.enabled:
            log.info("IA status: motor desligado (enabled=False).")
            return rep
        if self.kommo is None:
            log.warning("IA status: Kommo não configurado.")
            return rep

        rep.ran = True
        self.running = True
        teto = 60 if mode == "backfill" else max(1, int(max_pages))

        page = 1
        while page <= teto:
            try:
                batch = self.kommo.list_leads_recent(
                    limit=page_size, page=page,
                )
            except Exception as e:  # noqa: BLE001
                log.warning("IA status: página %d falhou: %s", page, e)
                break
            if not batch:
                break
            for ld in batch:
                lead_id = ld.get("id")
                rep.leads_total += 1
                try:
                    novo = self._decide(ld)
                    if novo is None:
                        rep.skipped += 1
                        continue
                    item = {"lead_id": lead_id, "status": novo}
                    if not dr:
                        ok = self.kommo.update_lead_fields(
                            lead_id, {"ativado_ia": novo},
                        )
                        item["aplicado"] = bool(ok)
                        if not ok:
                            rep.errors += 1
                    else:
                        item["aplicado"] = False
                    rep.detail.append(item)
                    if novo == "ATIVADO":
                        rep.ativado += 1
                    else:
                        rep.desativado += 1
                except Exception as e:  # noqa: BLE001
                    log.warning("IA status: lead %s falhou: %s", lead_id, e)
                    rep.errors += 1
                # Gentileza com a API do Kommo no backfill.
                if mode == "backfill":
                    time.sleep(0.15)
            page += 1

        log.info(
            "IA status concluído (mode=%s, dry_run=%s): %d ATIVADO, "
            "%d DESATIVADO, %d pulados, %d erros",
            mode, dr, rep.ativado, rep.desativado, rep.skipped, rep.errors,
        )
        self.last_report = rep
        self.running = False
        return rep
