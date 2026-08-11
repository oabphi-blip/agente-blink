"""Verifica saúde da Lia após deploy: smoke test E2E.

Bate `/admin/smoke-tick` (6 cenários core) em produção. Se passar,
o fix é considerado seguro e o engineer_loop merge automaticamente.
Se falhar, dispara rollback.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

import requests


PROD_URL = os.getenv(
    "LIA_ENGINEER_PROD_URL",
    "https://blink-agent.6prkfn.easypanel.host",
)
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")


@dataclass
class SmokeResult:
    """Resultado do smoke test em produção."""

    passou: bool
    cenarios_total: int = 0
    cenarios_ok: int = 0
    falha_motivo: Optional[str] = None
    tempo_seg: float = 0


def smoke_test_prod(timeout_seg: int = 120) -> SmokeResult:
    """Bate `/admin/smoke-tick` em produção e retorna resultado.

    Critério de aprovação: 6/6 cenários ok. Se 5/6 já é warning (rollback
    de qualquer jeito porque pode ser regressão silenciosa).
    """
    try:
        r = requests.post(
            f"{PROD_URL}/admin/smoke-tick",
            params={"secret": WEBHOOK_SECRET} if WEBHOOK_SECRET else {},
            timeout=timeout_seg,
        )
        if r.status_code != 200:
            return SmokeResult(
                passou=False,
                falha_motivo=f"HTTP {r.status_code}: {r.text[:300]}",
            )
        data = r.json()
        total = data.get("total", 0)
        ok = data.get("ok", 0)
        return SmokeResult(
            passou=(ok == total and total > 0),
            cenarios_total=total,
            cenarios_ok=ok,
            falha_motivo=None if ok == total else f"falhou {total-ok} cenários",
            tempo_seg=r.elapsed.total_seconds(),
        )
    except requests.exceptions.Timeout:
        return SmokeResult(passou=False, falha_motivo=f"timeout {timeout_seg}s")
    except Exception as e:
        return SmokeResult(passou=False, falha_motivo=f"{type(e).__name__}: {e}")


def healthz_externo() -> dict:
    """Bate `/admin/healthz` pra ver se dependências externas estão OK.

    Útil pra distinguir "fix tem bug" vs "Meta token expirou de novo".
    """
    try:
        r = requests.get(
            f"{PROD_URL}/admin/healthz",
            params={"secret": WEBHOOK_SECRET} if WEBHOOK_SECRET else {},
            timeout=10,
        )
        return r.json() if r.status_code == 200 else {"erro": r.text[:300]}
    except Exception as e:
        return {"erro": f"{type(e).__name__}: {e}"}
