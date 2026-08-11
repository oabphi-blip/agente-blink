#!/usr/bin/env python3
"""Script standalone pra rodar learning loop nos leads recentes.

Uso:
    python3 scripts/rodar_learning_loop.py                    # dry-run
    python3 scripts/rodar_learning_loop.py --apply            # aplica de verdade
    python3 scripts/rodar_learning_loop.py --lead-id 24290902 # 1 lead só

Pode ser agendado em cron do Easypanel (ex: 4h/4h) OU rodado manualmente
quando você quiser processar handoffs recentes.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Adiciona voice_agent ao path
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--lead-id", type=int, default=None,
        help="Processar 1 lead específico (ID Kommo)",
    )
    parser.add_argument(
        "--limit", type=int, default=50,
        help="Se sem --lead-id, quantos leads recentes varrer (default 50)",
    )
    parser.add_argument(
        "--apply", action="store_true",
        help="Realmente escreve no CLAUDE.md (senão só simula)",
    )
    args = parser.parse_args()

    if not args.apply:
        # Toggle off pra não modificar arquivo real
        os.environ["LEARNING_LOOP_ATIVADO"] = "0"
        print("DRY-RUN — nada será escrito no CLAUDE.md")
        print("Use --apply pra escrever de verdade")
        print()

    from voice_agent import learning_loop
    from voice_agent.kommo import KommoClient

    # Reset toggle se --apply
    if args.apply:
        os.environ["LEARNING_LOOP_ATIVADO"] = "1"

    token = os.environ.get("KOMMO_TOKEN")
    if not token:
        print("ERROR: KOMMO_TOKEN não setado. Export a env primeiro.")
        return 1

    kommo = KommoClient(token=token)

    if args.lead_id:
        # 1 lead
        print(f"Processando lead {args.lead_id}...")
        r = learning_loop.processar_lead(args.lead_id, kommo)
        print(f"Resultado: {r}")
        return 0 if r.get("erro") is None else 1

    # Varre leads recentes — usa notas recentes como sinal
    # (implementação futura: batch. Por hora, exemplo com 1 lead)
    print(f"Modo batch ainda não implementado (limit={args.limit}).")
    print("Use --lead-id NNN pra processar 1 lead específico.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
