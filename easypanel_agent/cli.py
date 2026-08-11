"""CLI interativo do agente Easypanel.

Uso:
    python -m easypanel_agent.cli           # modo chat
    python -m easypanel_agent.cli "comando" # one-shot

Variáveis de ambiente esperadas (carregadas via .env se presente):
    ANTHROPIC_API_KEY
    EASYPANEL_URL    (ex: http://easypanel:3000 ou http://2.24.110.21:3000)
    EASYPANEL_TOKEN
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt

from .agent import Agent, AgentConfig

console = Console()


def _load_config_json() -> dict:
    """Lê config.json no cwd, se existir, para fallback dos secrets."""
    candidates = [
        Path.cwd() / "config.json",
        Path(__file__).resolve().parent.parent / "config.json",
    ]
    for path in candidates:
        if path.is_file():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                pass
    return {}


def _build_config() -> AgentConfig:
    load_dotenv()
    cfg_json = _load_config_json()
    easypanel_cfg = cfg_json.get("easypanel", {}) if isinstance(cfg_json, dict) else {}

    anthropic_key = os.getenv("ANTHROPIC_API_KEY")
    easypanel_url = os.getenv("EASYPANEL_URL") or easypanel_cfg.get("base_url")
    easypanel_token = os.getenv("EASYPANEL_TOKEN") or easypanel_cfg.get("api_token")
    model = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5")

    missing = []
    if not anthropic_key:
        missing.append("ANTHROPIC_API_KEY")
    if not easypanel_url:
        missing.append("EASYPANEL_URL (ou config.json easypanel.base_url)")
    if not easypanel_token:
        missing.append("EASYPANEL_TOKEN (ou config.json easypanel.api_token)")

    if missing:
        console.print(
            Panel.fit(
                "[red]Faltam variáveis de ambiente:[/]\n  - "
                + "\n  - ".join(missing)
                + "\n\nCrie um arquivo .env baseado no .env.example.",
                title="Erro de configuração",
                border_style="red",
            )
        )
        sys.exit(1)

    return AgentConfig(
        anthropic_api_key=anthropic_key,
        easypanel_url=easypanel_url,
        easypanel_token=easypanel_token,
        model=model,
    )


def _on_event(event_type: str, data) -> None:
    if event_type == "tool_use":
        # Renderiza o input de forma compacta
        try:
            input_preview = json.dumps(data["input"], ensure_ascii=False)
        except (TypeError, ValueError):
            input_preview = str(data["input"])
        if len(input_preview) > 200:
            input_preview = input_preview[:200] + "..."
        console.print(
            f"[dim cyan]→ tool[/] [cyan]{data['name']}[/]([dim]{input_preview}[/])"
        )
    elif event_type == "tool_result":
        result = data["result"]
        preview = result.replace("\n", " ")
        if len(preview) > 120:
            preview = preview[:120] + "..."
        console.print(f"  [dim]↳ {preview}[/]")


def _interactive(agent: Agent) -> None:
    console.print(
        Panel.fit(
            "[bold green]Agente Easypanel[/]\n"
            f"[dim]URL:[/] {agent.config.easypanel_url}\n"
            f"[dim]Modelo:[/] {agent.config.model}\n"
            "[dim]Comandos: /reset, /quit[/]",
            border_style="green",
        )
    )

    while True:
        try:
            user_input = Prompt.ask("[bold blue]você[/]").strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]tchau[/]")
            return

        if not user_input:
            continue
        if user_input.lower() in ("/quit", "/exit", ":q"):
            console.print("[dim]tchau[/]")
            return
        if user_input.lower() == "/reset":
            agent.reset()
            console.print("[dim]histórico limpo[/]")
            continue

        try:
            answer = agent.ask(user_input, on_event=_on_event)
        except Exception as e:  # noqa: BLE001
            console.print(f"[red]erro:[/] {type(e).__name__}: {e}")
            continue

        if answer:
            console.print(
                Panel(answer, title="claude", border_style="magenta", expand=False)
            )


def main(argv: list[str] | None = None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    config = _build_config()
    agent = Agent(config=config)

    if argv:
        # Modo one-shot: tudo que veio depois do nome do programa = prompt
        prompt = " ".join(argv)
        answer = agent.ask(prompt, on_event=_on_event)
        if answer:
            console.print(answer)
    else:
        _interactive(agent)


if __name__ == "__main__":
    main()
