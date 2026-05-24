"""Carimbo do campo "ATIVADO IA?" (id 1260635) nos leads do Kommo.

O campo indica, de relance, se a IA está conduzindo o lead (ATIVADO) ou se
um humano assumiu / a IA foi desligada (DESATIVADO). Assim a equipe pode
FILTRAR a lista de leads por esse status, sem abrir conversa por conversa.

DOIS MODOS:
  - backfill: varre a base inteira UMA vez. Decisão rápida só pela etapa
    do funil (etapa humana → DESATIVADO; resto → ATIVADO) e gravação em
    LOTE (PATCH de até 250 leads por requisição). Roda em segundos/minutos.
    É o baseline; o sweep refina depois quem foi entregue a humano.
  - sweep: varre só os leads recentes. Lê as NOTAS de cada lead para
    detectar o desligamento da IA ('Agentes de IA foram desativados') e
    corrige o campo. Mais preciso, porém mais lento — por isso só recentes.

SEGURANÇA: dry_run=True decide tudo e monta o relatório sem gravar nada.
A gravação real só acontece com dry_run=False.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from .kommo import FIELD_ATIVADO_IA

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
    gravados: int = 0
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
            "gravados": self.gravados,
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

    def _decide_by_stage(self, lead: dict) -> str:
        """Decisão RÁPIDA só pela etapa — usada no backfill."""
        if lead.get("status_id") in ST_AGENT_OFF:
            return "DESATIVADO"
        return "ATIVADO"

    def _decide_by_notes(self, lead: dict) -> Optional[str]:
        """Decisão PRECISA lendo as notas — usada no sweep."""
        if lead.get("status_id") in ST_AGENT_OFF:
            return "DESATIVADO"
        try:
            sig = self.kommo.ia_status_from_notes(lead.get("id"))
        except Exception as e:  # noqa: BLE001
            log.warning("IA status: notas do lead %s falharam: %s",
                        lead.get("id"), e)
            return None
        return sig or "ATIVADO"

    # ----------------------------------------------------------------- run

    def run(
        self,
        dry_run: Optional[bool] = None,
        mode: str = "sweep",
        max_pages: int = 4,
        page_size: int = 250,
    ) -> IaStatusReport:
        """Varre os leads e carimba o campo 'ATIVADO IA?'.

        mode='backfill'→ base inteira, decisão por etapa, gravação em lote.
        mode='sweep'   → só `max_pages` páginas recentes, decisão por notas.
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
        try:
            teto = 60 if mode == "backfill" else max(1, int(max_pages))
            pares: list[tuple[int, str]] = []

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
                    rep.leads_total += 1
                    lead_id = ld.get("id")
                    try:
                        if mode == "backfill":
                            novo = self._decide_by_stage(ld)
                        else:
                            novo = self._decide_by_notes(ld)
                        if novo is None:
                            rep.skipped += 1
                            continue
                        pares.append((int(lead_id), novo))
                        if novo == "ATIVADO":
                            rep.ativado += 1
                        else:
                            rep.desativado += 1
                    except Exception as e:  # noqa: BLE001
                        log.warning("IA status: lead %s falhou: %s", lead_id, e)
                        rep.errors += 1
                page += 1

            # Gravação em LOTE (PATCH de até 250 leads por requisição).
            if pares and not dr:
                res = self.kommo.update_leads_field_batch(
                    FIELD_ATIVADO_IA, pares,
                )
                rep.gravados = res.get("ok", 0)
                rep.errors += res.get("fail", 0)

            log.info(
                "IA status concluído (mode=%s, dry_run=%s): %d ATIVADO, "
                "%d DESATIVADO, %d gravados, %d pulados, %d erros",
                mode, dr, rep.ativado, rep.desativado, rep.gravados,
                rep.skipped, rep.errors,
            )
            self.last_report = rep
        finally:
            self.running = False
        return rep
