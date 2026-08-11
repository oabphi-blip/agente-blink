#!/usr/bin/env python3
"""Hook PreToolUse — intercepta Chrome MCP em URLs do Kommo.

Origem: Bug C-11 (05/06/2026) — 14 mensagens viraram notas internas porque pulei
a validação de canal antes de clicar Enviar via Chrome MCP no Kommo.

Como funciona:
- Claude Code chama esse script ANTES de cada tool call que matche o padrão.
- Script lê tool_name + tool_input do stdin (JSON).
- Se for Chrome MCP em URL kommo.com fazendo click ou type em coordenadas
  típicas da caixa de mensagem (y entre 760-800), verifica se já houve canary
  nessa sessão (arquivo .canary-validated).
- Sem canary validado: stderr com instruções + exit code 2 (bloqueia call).
- Com canary: deixa passar.

Pra resetar canary (forçar nova validação): `rm .claude/hooks/.canary-validated`.

Pra MARCAR canary validado depois que Fábio confirmou: Claude escreve arquivo
.canary-validated com timestamp + lead_id do piloto.
"""
import json
import os
import sys
import time
from pathlib import Path

HOOK_DIR = Path(__file__).parent
CANARY_FILE = HOOK_DIR / ".canary-validated"
CANARY_TTL_SEC = 60 * 60  # 1 hora — depois disso exige novo canary


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        # Sem payload, deixa passar — não bloqueia outras tools
        sys.exit(0)

    tool_name = payload.get("tool_name") or ""
    tool_input = payload.get("tool_input") or {}

    # Só intercepta Chrome MCP
    if not tool_name.startswith("mcp__Claude_in_Chrome__"):
        sys.exit(0)

    # Detecta se é ação que pode causar envio (computer click/type, javascript)
    action_risky = False

    if tool_name == "mcp__Claude_in_Chrome__computer":
        action = tool_input.get("action", "")
        coord = tool_input.get("coordinate") or []
        # Click ou type na faixa Y da caixa de mensagem do Kommo (760-800)
        if action in ("left_click", "type", "key"):
            if len(coord) == 2 and 750 <= coord[1] <= 810:
                action_risky = True
            elif action == "type":
                # Type em qualquer Y mas com tabId em Kommo é suspeito
                action_risky = True
    elif tool_name == "mcp__Claude_in_Chrome__navigate":
        url = tool_input.get("url", "")
        if "kommo.com/leads/detail" in url:
            # Navegação pra lead Kommo — checa canary
            action_risky = True
    elif tool_name == "mcp__Claude_in_Chrome__browser_batch":
        # Batch — sempre verifica
        action_risky = True
    elif tool_name == "mcp__Claude_in_Chrome__javascript_tool":
        text = tool_input.get("text", "")
        if "kommo.com" in text and ("fetch" in text or "POST" in text):
            action_risky = True

    if not action_risky:
        sys.exit(0)

    # Verifica canary
    canary_valid = False
    if CANARY_FILE.exists():
        try:
            data = json.loads(CANARY_FILE.read_text())
            age = time.time() - data.get("ts", 0)
            if age < CANARY_TTL_SEC:
                canary_valid = True
        except Exception:
            pass

    if canary_valid:
        sys.exit(0)

    # Sem canary — bloqueia e dá instrução
    msg = (
        "[HOOK pre-chrome-kommo] Bloqueando Chrome MCP em URL Kommo "
        "porque NÃO há canary validado nessa sessão.\n\n"
        "Bug C-11 (05/06/2026): 14 mensagens viraram notas internas. "
        "REGRA P0: antes de batch ≥ 3 ações via Chrome MCP no Kommo, "
        "fazer 1 piloto isolado, screenshot, AGUARDAR confirmação do Fábio.\n\n"
        "Pra desbloquear nessa sessão:\n"
        "1. Faça 1 lead piloto manual (read_page → confirma 'WhatsApp Business' "
        "no header da caixa, NÃO 'Bate-papo com todos os').\n"
        "2. Envie a mensagem.\n"
        "3. Screenshot mostra bolha verde + canal correto no histórico.\n"
        "4. Pergunte Fábio: 'Piloto OK? Posso seguir com os outros?'\n"
        "5. Após confirmação, escreva o arquivo "
        f"{CANARY_FILE} com: "
        '{"ts": <unix_ts>, "lead_id": <id>, "confirmed_by": "Fabio"}\n'
        "6. Aí o hook libera as próximas Chrome MCP calls em Kommo por 1h.\n\n"
        "Ler também: /Users/fabiophilipecostamartins/Documents/Claude/Projects/"
        "AGENTE IA BLINK/enviar_kommo_chrome_validado.md"
    )
    print(msg, file=sys.stderr)
    sys.exit(2)


if __name__ == "__main__":
    main()
