"""Tracing estruturado por turno + replay 1-click.

Origem: discussão Fábio 01/06/2026 noite. Hoje quando bate um bug em
prod, o ritual é: abrir Kommo → ver notas → abrir Easypanel → procurar
logs → comparar → adivinhar o ctx. 20 min por bug, no mínimo.

Este módulo grava cada turno como JSON estruturado em Redis (TTL 30
dias). Endpoint `/admin/replay/{lead_id}` devolve todos os turnos do
lead, em ordem cronológica, com tudo que importa pra reproduzir
diagnóstico em 1 curl.

O que cada trace contém:
    {
      "ts_iso": "2026-06-02T00:30:00-03:00",
      "ts_epoch": 1780359000,
      "lead_id": 24060221,
      "phone": "5561992589767",
      "conversation_key": "...",
      "channel": "81331005",
      "user_text": "oi quero agendar",
      "ctx_resumo": {
        "ja_agendado": true,
        "agenda_disponivel": false,
        "etapa": "5-AGENDADO",
        "dia_consulta_iso": "2026-06-09T18:30:00-03:00"
      },
      "tools_chamadas": [{"name": "oferecer_slot", "ok": true}],
      "juiz_veredict": {
        "risco": 85,
        "motivos": ["oferta apos agendado"],
        "recomendado": "substituir"
      },
      "memoria_bugs_match": {
        "bug_id": "esther_oferta_pos_agendado_imagem",
        "similaridade": 0.92
      },
      "output_final": "Anotei aqui! ...",
      "filtros_disparados": ["_viola_oferta_apos_agendado", "juiz_haiku"],
      "elapsed_ms": 3417
    }

Liga via env `TRACING_ENABLED=1` (default off — opt-in).

Custo de espaço: cada trace ~2KB. 200 turnos/dia × 30 dias = 12 MB
em Redis. Irrelevante.
"""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Optional

log = logging.getLogger(__name__)


# TTL padrão: 30 dias em segundos
TTL_DEFAULT = 30 * 24 * 3600


def _agora_iso() -> str:
    """ISO-8601 com offset BRT (-03:00)."""
    try:
        from datetime import timedelta
        brt = timezone(timedelta(hours=-3))
        return datetime.now(brt).isoformat(timespec="seconds")
    except Exception:  # noqa: BLE001
        return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _resumir_ctx(ctx: Optional[dict]) -> dict:
    """Compacta o ctx pra um dict pequeno pro trace."""
    if not isinstance(ctx, dict):
        return {}
    known = ctx.get("known") or {}
    out = {
        "ja_agendado": bool(ctx.get("ja_agendado")),
        "agenda_disponivel": bool(ctx.get("agenda")),
        "etapa": ctx.get("etapa") or "",
        "status_id": ctx.get("status_id"),
    }
    for k in ("nome_paciente", "medico", "unidade", "convenio",
              "dia_consulta_iso"):
        v = known.get(k)
        if v:
            out[k] = v
    return out


@dataclass
class TraceTurno:
    """Snapshot completo de 1 turno de conversa."""
    ts_iso: str = ""
    ts_epoch: int = 0
    lead_id: Optional[int] = None
    phone: str = ""
    conversation_key: str = ""
    channel: str = ""
    user_text: str = ""
    ctx_resumo: dict = field(default_factory=dict)
    tools_chamadas: list[dict] = field(default_factory=list)
    juiz_veredict: dict = field(default_factory=dict)
    memoria_bugs_match: dict = field(default_factory=dict)
    output_final: str = ""
    filtros_disparados: list[str] = field(default_factory=list)
    elapsed_ms: int = 0
    erro: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "TraceTurno":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


# Prefixo de chave Redis. Lista por lead (Redis list).
def _redis_key(lead_id: int | str) -> str:
    return f"blink:trace:{lead_id}"


# -----------------------------------------------------------------------
# Persistência
# -----------------------------------------------------------------------

def gravar_trace(
    redis_client: Any,
    trace: TraceTurno,
    ttl: int = TTL_DEFAULT,
    max_turns_por_lead: int = 200,
) -> bool:
    """Persiste um trace no Redis.

    Estrutura: lista FIFO por lead — `blink:trace:{lead_id}` com TTL.
    Limita a `max_turns_por_lead` (corta os mais antigos).
    Devolve True se persistiu, False em erro.
    """
    if not redis_client or trace.lead_id is None:
        return False
    try:
        payload = json.dumps(trace.to_dict(), ensure_ascii=False)
        key = _redis_key(trace.lead_id)
        # Push à direita (mais novo no final)
        redis_client.rpush(key, payload)
        # Limita tamanho: mantém só os últimos N
        redis_client.ltrim(key, -max_turns_por_lead, -1)
        # Renova TTL a cada gravação
        redis_client.expire(key, ttl)
        return True
    except Exception as e:  # noqa: BLE001
        log.warning("[TRACING] erro ao gravar trace lead=%s: %s",
                    trace.lead_id, e)
        return False


def carregar_traces(
    redis_client: Any,
    lead_id: int | str,
    limit: int = 100,
) -> list[TraceTurno]:
    """Carrega traces do lead, do mais antigo pro mais novo."""
    if not redis_client or lead_id is None:
        return []
    try:
        key = _redis_key(lead_id)
        # Pega os últimos `limit`
        raw_list = redis_client.lrange(key, -limit, -1) or []
        traces = []
        for raw in raw_list:
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            try:
                d = json.loads(raw)
                traces.append(TraceTurno.from_dict(d))
            except Exception as e:  # noqa: BLE001
                log.warning("[TRACING] trace inválido: %s", e)
        return traces
    except Exception as e:  # noqa: BLE001
        log.warning("[TRACING] erro ao carregar lead=%s: %s", lead_id, e)
        return []


# -----------------------------------------------------------------------
# Builder fluente (usado pelo pipeline)
# -----------------------------------------------------------------------

class TraceBuilder:
    """Acumula os dados de 1 turno conforme o pipeline avança.

    Uso típico no pipeline:
        tb = TraceBuilder(lead_id=24060221, phone="...", ...)
        tb.set_user_text(text)
        tb.set_ctx(ctx)
        tb.add_tool("oferecer_slot", ok=True)
        tb.set_juiz({"risco": 85, ...})
        tb.add_filtro("_viola_oferta_apos_agendado")
        tb.set_output(resposta_final)
        tb.gravar(redis_client)
    """

    def __init__(
        self,
        lead_id: Optional[int] = None,
        phone: str = "",
        conversation_key: str = "",
        channel: str = "",
    ):
        self._t0 = time.time()
        self._trace = TraceTurno(
            ts_iso=_agora_iso(),
            ts_epoch=int(self._t0),
            lead_id=lead_id,
            phone=phone,
            conversation_key=conversation_key,
            channel=channel,
        )

    @property
    def trace(self) -> TraceTurno:
        return self._trace

    def set_user_text(self, text: str) -> "TraceBuilder":
        if text:
            self._trace.user_text = text[:2000]
        return self

    def set_ctx(self, ctx: Optional[dict]) -> "TraceBuilder":
        self._trace.ctx_resumo = _resumir_ctx(ctx)
        return self

    def add_tool(self, name: str, ok: bool = True, detail: str = "") -> "TraceBuilder":
        self._trace.tools_chamadas.append({
            "name": name, "ok": bool(ok), "detail": (detail or "")[:200],
        })
        return self

    def set_juiz(self, veredict: dict) -> "TraceBuilder":
        if isinstance(veredict, dict):
            self._trace.juiz_veredict = {
                "risco": int(veredict.get("risco", 0)),
                "motivos": list(veredict.get("motivos") or [])[:5],
                "recomendado": str(veredict.get("recomendado", "enviar")),
            }
        return self

    def set_memoria_bugs(self, bug_id: str, similaridade: float) -> "TraceBuilder":
        self._trace.memoria_bugs_match = {
            "bug_id": bug_id, "similaridade": round(float(similaridade), 4),
        }
        return self

    def add_filtro(self, nome: str) -> "TraceBuilder":
        if nome:
            self._trace.filtros_disparados.append(nome)
        return self

    def set_output(self, texto: str) -> "TraceBuilder":
        if texto:
            self._trace.output_final = texto[:3000]
        return self

    def set_erro(self, msg: str) -> "TraceBuilder":
        if msg:
            self._trace.erro = msg[:500]
        return self

    def finalizar(self) -> TraceTurno:
        self._trace.elapsed_ms = int((time.time() - self._t0) * 1000)
        return self._trace

    def gravar(self, redis_client: Any) -> bool:
        return gravar_trace(redis_client, self.finalizar())


# -----------------------------------------------------------------------
# Helper de habilitação
# -----------------------------------------------------------------------

def esta_habilitado() -> bool:
    """Default ON desde Bug C-32 (16/06/2026).

    Sem tracing, /admin/replay/{lead_id} retorna vazio e fica impossível
    investigar bugs em prod. Default ON garante observabilidade básica.
    Pra desligar: TRACING_ENABLED=0 explicitamente.
    """
    val = (os.getenv("TRACING_ENABLED") or "1").lower().strip()
    return val not in ("0", "false", "no", "off", "")
