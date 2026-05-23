"""Motor de reconciliação de etapas — cruza a agenda da Medware com o Kommo.

Objetivo: manter a etapa dos leads coerente com quem já consultou em 2026.

Regra de negócio:
  - Lead aberto cujo telefone TEM consulta registrada em 2026 na Medware
    → o paciente já foi atendido/está agendado este ano → mover para
    8-PRÓXIMA CONSULTA (volta no ciclo de retorno: acima de 2 anos = anual,
    até 2 anos = semestral — a cadência fina é tratada pela seção 15 da
    instrução mestra / campo N.PRÓXIMA CONSULTA).
  - Lead aberto cujo telefone NÃO tem consulta em 2026 → ainda precisa
    agendar → mover para 2-AGENDAR.

SEGURANÇA — duas travas, idêntico ao motor de reativação:
  - reconciliation_enabled=False → o motor nem roda.
  - reconciliation_dry_run=True  → roda, decide tudo e monta o relatório,
    mas NÃO altera nenhuma etapa no Kommo.
  Mudança real de etapa só acontece com enabled=True E dry_run=False.

PAREAMENTO: feito pelo telefone do contato do lead (só dígitos, com
normalização do 9º dígito BR) contra o telefone do paciente em cada
agendamento de 2026. É o identificador mais estável disponível.

ACIONAMENTO: endpoint POST /reconciliation/run. Pode rodar sob demanda
ou como tarefa agendada. Processa o funil aberto inteiro numa passada.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional
from zoneinfo import ZoneInfo

log = logging.getLogger(__name__)
_TZ = ZoneInfo("America/Sao_Paulo")

# ------------------------------------------------------------------ funil
PIPELINE_ATENDE = 8601819

# Etapas-alvo da reconciliação
ST_PROXIMA_CONSULTA = 106157327  # 8-PRÓXIMA CONSULTA — já consultou em 2026
ST_AGENDAR = 102560495           # 2-AGENDAR — ainda precisa agendar

# Etapas ABERTAS que entram na reconciliação (origem). Ficam de fora:
# 4-AGENDADO e 5-CONFIRMAR (consulta ativa), 6-REALIZADO, 7-CIRURGIAS,
# 8-PRÓXIMA (já reconciliado) e Closed-won/lost.
OPEN_STAGES = [
    96441724,   # 0-ETAPA ENTRADA
    101508307,  # 1.LEADS FRIO
    102560495,  # 2-AGENDAR
    106184631,  # 3.REAGENDAR
    106184983,  # 5.1-NO-SHOW (ATIVAR)
]


def _digits(value: str) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def _phone_key(phone: str) -> str:
    """Normaliza um telefone BR para servir de chave de pareamento.

    Remove o 9º dígito de celular (55 + DDD + 9 + 8 dígitos → 12) para que
    cadastros com e sem o 9 batam. Usa os últimos 10 dígitos como chave.
    """
    d = _digits(phone)
    if d.startswith("55") and len(d) == 13 and d[4] == "9":
        d = d[:4] + d[5:]
    return d[-10:] if len(d) >= 10 else d


@dataclass
class ReconciliationReport:
    ran: bool
    dry_run: bool
    leads_total: int = 0
    to_proxima: int = 0
    to_agendar: int = 0
    unchanged: int = 0
    errors: int = 0
    detail: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "ran": self.ran,
            "dry_run": self.dry_run,
            "leads_total": self.leads_total,
            "to_proxima_consulta": self.to_proxima,
            "to_agendar": self.to_agendar,
            "unchanged": self.unchanged,
            "errors": self.errors,
            "detail": self.detail[:200],
        }


@dataclass
class ReconciliationEngine:
    """Cruza Medware 2026 × Kommo e ajusta as etapas dos leads abertos."""

    kommo: Any            # KommoClient
    medware: Any          # MedwareClient
    enabled: bool = False
    dry_run: bool = True
    last_report: Optional[ReconciliationReport] = None
    running: bool = False

    def status(self) -> dict:
        """Estado atual + último relatório — consultável por GET."""
        return {
            "enabled": self.enabled,
            "dry_run_default": self.dry_run,
            "running": self.running,
            "last_report": (
                self.last_report.as_dict() if self.last_report else None
            ),
        }

    # ----------------------------------------------- índice Medware 2026

    def _build_medware_index(self) -> set[str]:
        """Conjunto de chaves de telefone com agendamento/consulta em 2026.

        Varre o ANO INTEIRO (jan → dez) — assim pega tanto a consulta já
        realizada quanto o agendamento FUTURO marcado para este ano.
        """
        keys: set[str] = set()
        hoje = datetime.now(_TZ)
        ano = hoje.year
        for mes in range(1, 13):
            ini = f"01/{mes:02d}/{ano}"
            # último dia do mês: usa 31 — a Medware aceita e ignora o excedente
            fim = f"31/{mes:02d}/{ano}"
            try:
                ags = self.medware.listar_agendamentos(ini, fim)
            except Exception as e:  # noqa: BLE001
                log.warning("Reconciliação: Medware mês %d falhou: %s", mes, e)
                continue
            for ag in (ags or []):
                pac = (ag or {}).get("paciente") or {}
                tel = pac.get("telefone") or ""
                k = _phone_key(tel)
                if k:
                    keys.add(k)
        log.info("Reconciliação: %d telefones com consulta em %d", len(keys), ano)
        return keys

    # --------------------------------------------------------------- run

    def run(self, dry_run: Optional[bool] = None) -> ReconciliationReport:
        """Executa a reconciliação. dry_run sobrescreve a config se informado."""
        dr = self.dry_run if dry_run is None else bool(dry_run)
        if not self.enabled:
            log.info("Reconciliação: motor desligado (enabled=False).")
            return ReconciliationReport(ran=False, dry_run=dr)
        if self.kommo is None or self.medware is None:
            log.warning("Reconciliação: Kommo ou Medware não configurado.")
            return ReconciliationReport(ran=False, dry_run=dr)

        rep = ReconciliationReport(ran=True, dry_run=dr)
        self.running = True
        index = self._build_medware_index()

        # Pagina a base inteira de leads abertos (250 por página).
        leads: list = []
        page = 1
        while page <= 40:  # teto de segurança: 40 x 250 = 10.000 leads
            batch = self.kommo.list_leads_by_status(
                PIPELINE_ATENDE, OPEN_STAGES, limit=250, page=page,
            )
            if not batch:
                break
            leads.extend(batch)
            page += 1
        rep.leads_total = len(leads)
        log.info("Reconciliação: %d leads abertos para avaliar", len(leads))

        for ld in leads:
            lead_id = ld.get("id")
            status_atual = ld.get("status_id")
            try:
                phone = self.kommo.get_lead_main_phone(lead_id)
                consultou = bool(phone) and _phone_key(phone) in index

                # Sem agendamento/consulta em 2026 → continua frio. NÃO
                # move: fica onde está, disponível para a reativação.
                if not consultou:
                    rep.unchanged += 1
                    continue

                alvo = ST_PROXIMA_CONSULTA
                if status_atual == alvo:
                    rep.unchanged += 1
                    continue

                item = {
                    "lead_id": lead_id,
                    "de": status_atual,
                    "para": alvo,
                    "consultou_2026": consultou,
                }
                if not dr:
                    ok = self.kommo.update_lead_status(
                        lead_id, alvo, PIPELINE_ATENDE,
                    )
                    item["aplicado"] = ok
                    if not ok:
                        rep.errors += 1
                else:
                    item["aplicado"] = False
                rep.detail.append(item)
                rep.to_proxima += 1
            except Exception as e:  # noqa: BLE001
                log.warning("Reconciliação: lead %s falhou: %s", lead_id, e)
                rep.errors += 1

        log.info(
            "Reconciliação concluída (dry_run=%s): %d→PRÓXIMA, %d→AGENDAR, "
            "%d sem mudança, %d erros",
            dr, rep.to_proxima, rep.to_agendar, rep.unchanged, rep.errors,
        )
        self.last_report = rep
        self.running = False
        return rep
