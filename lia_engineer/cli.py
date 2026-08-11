"""CLI do Lia Engineer — entrypoint pro cron Easypanel ou shell manual.

Comandos:
    python -m lia_engineer.cli tick              # 1 iteração
    python -m lia_engineer.cli tick --dry-run    # detecta mas não aplica
    python -m lia_engineer.cli daemon            # loop infinito (5min)
    python -m lia_engineer.cli status            # estado atual
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from .engineer_loop import EngineerState, engineer_tick
from .apply_fix import aplicar_fix, rollback, merge_para_main
from .verify import smoke_test_prod
from .notify import (
    notify_slack, notify_fix_aplicado, notify_rollback,
    notify_escalado, notify_pausado,
)


log = logging.getLogger("lia_engineer")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


# ────────────────────────────────────────────────────────────────────────
# Adapters dummy pra dev (em prod, vêm de voice_agent.kommo)
# ────────────────────────────────────────────────────────────────────────

class KommoClientStub:
    """Stub usado APENAS em dev quando voice_agent.kommo falha (sem token).
    Em prod, _carregar_kommo_real() resolve pra KommoClient real que já
    tem list_recent_notes implementado (kommo.py linhas ~1453)."""

    def list_recent_notes(self, since, author_user_id=0, limit=250, note_type="common"):
        log.warning("[KommoClientStub] retornando vazio (sem KOMMO_TOKEN). Substituir.")
        return []

    def search_leads_by_window(self, pipeline_id, ts_from, ts_to):
        return []


def _carregar_kommo_real():
    """Tenta carregar voice_agent.kommo.KommoClient. Se falhar, usa stub."""
    try:
        from voice_agent.kommo import KommoClient
        token = os.getenv("KOMMO_TOKEN", "")
        base = os.getenv("KOMMO_API_BASE", "https://univeja.kommo.com/api/v4")
        return KommoClient(token=token, base_url=base)
    except Exception as e:
        log.warning("[lia_engineer] usando KommoClientStub (real falhou: %s)", e)
        return KommoClientStub()


# ────────────────────────────────────────────────────────────────────────
# Comandos
# ────────────────────────────────────────────────────────────────────────

def cmd_tick(args) -> int:
    """1 iteração completa."""
    state_path = Path(os.getenv("LIA_ENGINEER_STATE_PATH", "/tmp/lia_engineer_state.json"))
    state = _load_state(state_path)

    kommo = _carregar_kommo_real()
    arquivo_codigo = Path(os.getenv(
        "LIA_ENGINEER_REPO_ROOT",
        "/Users/fabiophilipecostamartins/Documents/Claude/Projects/AGENTE IA BLINK",
    )) / "voice_agent" / "responder.py"

    def apply_fix_fn(proposta):
        if args.dry_run:
            log.info("[dry-run] PULANDO apply_fix — proposta: %s", proposta.commit_message)
            return {"push_ok": True, "commit_sha": "dryrun", "branch_name": "dryrun"}
        result = aplicar_fix(proposta)
        return {
            "push_ok": result.push_ok,
            "commit_sha": result.commit_sha,
            "branch_name": result.branch_name,
            "erro": result.erro,
        }

    def smoke_test_fn():
        if args.dry_run:
            return {"passou": True, "cenarios_ok": 6, "cenarios_total": 6}
        result = smoke_test_prod()
        return {
            "passou": result.passou,
            "cenarios_ok": result.cenarios_ok,
            "cenarios_total": result.cenarios_total,
            "falha_motivo": result.falha_motivo,
        }

    def notify_fn(msg):
        log.info("[NOTIFY] %s", msg)
        if not args.dry_run:
            notify_slack(msg, severidade="info" if "✅" in msg else "warning")

    def rollback_fn(sha):
        if args.dry_run:
            log.info("[dry-run] PULANDO rollback %s", sha)
            return True
        return rollback(sha)

    resultado = engineer_tick(
        kommo_client=kommo,
        state=state,
        arquivo_codigo_path=arquivo_codigo,
        apply_fix_fn=apply_fix_fn,
        smoke_test_fn=smoke_test_fn,
        notify_fn=notify_fn,
        rollback_fn=rollback_fn,
    )

    _save_state(state_path, state)
    print(json.dumps(resultado, indent=2, default=str))
    return 0


def cmd_daemon(args) -> int:
    """Loop infinito tick a cada 5min."""
    intervalo = int(os.getenv("LIA_ENGINEER_INTERVAL_SEG", "300"))
    log.info("[daemon] iniciando loop, tick a cada %ds", intervalo)
    while True:
        try:
            cmd_tick(args)
        except Exception as e:
            log.exception("[daemon] tick falhou: %s", e)
            notify_slack(f"❌ Tick falhou: {type(e).__name__}: {e}", "error")
        time.sleep(intervalo)


def cmd_status(args) -> int:
    """Mostra estado atual."""
    state_path = Path(os.getenv("LIA_ENGINEER_STATE_PATH", "/tmp/lia_engineer_state.json"))
    state = _load_state(state_path)
    print(json.dumps({
        "ultimo_tick": state.ultimo_tick.isoformat() if state.ultimo_tick else None,
        "bugs_detectados_24h": state.bugs_detectados_24h,
        "fixes_aplicados_24h": state.fixes_aplicados_24h,
        "fixes_escalados_24h": state.fixes_escalados_24h,
        "rollbacks_24h": state.rollbacks_24h,
        "pausado": state.pausado,
        "motivo_pausa": state.motivo_pausa,
    }, indent=2))
    return 0


# ────────────────────────────────────────────────────────────────────────
# State persistente (arquivo JSON em /tmp ou Redis em prod)
# ────────────────────────────────────────────────────────────────────────

def _load_state(path: Path) -> EngineerState:
    if not path.exists():
        return EngineerState()
    try:
        data = json.loads(path.read_text())
        return EngineerState(
            ultimo_tick=datetime.fromisoformat(data["ultimo_tick"]) if data.get("ultimo_tick") else None,
            bugs_detectados_24h=data.get("bugs_detectados_24h", 0),
            fixes_aplicados_24h=data.get("fixes_aplicados_24h", 0),
            fixes_escalados_24h=data.get("fixes_escalados_24h", 0),
            rollbacks_24h=data.get("rollbacks_24h", 0),
            rollbacks_consecutivos=data.get("rollbacks_consecutivos", 0),
            pausado=data.get("pausado", False),
            motivo_pausa=data.get("motivo_pausa", ""),
            bugs_processados_chaves=set(data.get("bugs_processados_chaves", [])),
        )
    except Exception as e:
        log.warning("[state] falha load (%s), iniciando estado limpo", e)
        return EngineerState()


def _save_state(path: Path, state: EngineerState):
    try:
        path.write_text(json.dumps({
            "ultimo_tick": state.ultimo_tick.isoformat() if state.ultimo_tick else None,
            "bugs_detectados_24h": state.bugs_detectados_24h,
            "fixes_aplicados_24h": state.fixes_aplicados_24h,
            "fixes_escalados_24h": state.fixes_escalados_24h,
            "rollbacks_24h": state.rollbacks_24h,
            "rollbacks_consecutivos": state.rollbacks_consecutivos,
            "pausado": state.pausado,
            "motivo_pausa": state.motivo_pausa,
            "bugs_processados_chaves": list(state.bugs_processados_chaves),
        }, indent=2))
    except Exception as e:
        log.warning("[state] falha save: %s", e)


# ────────────────────────────────────────────────────────────────────────
# Entry point
# ────────────────────────────────────────────────────────────────────────

def main(argv=None):
    parser = argparse.ArgumentParser(prog="lia_engineer")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_tick = sub.add_parser("tick", help="1 iteração")
    p_tick.add_argument("--dry-run", action="store_true",
                        help="Detecta bugs mas NÃO aplica fix nem push")
    p_tick.set_defaults(func=cmd_tick)

    p_daemon = sub.add_parser("daemon", help="Loop infinito 5min")
    p_daemon.add_argument("--dry-run", action="store_true")
    p_daemon.set_defaults(func=cmd_daemon)

    p_status = sub.add_parser("status", help="Estado atual")
    p_status.set_defaults(func=cmd_status)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
