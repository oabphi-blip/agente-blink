"""CLI para testar a pipeline localmente sem WhatsApp.

Uso:
    # Áudio de arquivo
    python -m voice_agent.cli audio paciente.ogg
    python -m voice_agent.cli audio paciente.ogg --send 5561996830710

    # Texto direto
    python -m voice_agent.cli texto "Quero saber sobre catarata"
    python -m voice_agent.cli texto "Aceitam Unimed?" --send 5561996830710

    # Chat interativo
    python -m voice_agent.cli chat
"""

from __future__ import annotations

import argparse
import mimetypes
import sys
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt

from .evolution import EvolutionClient
from .pipeline import VoicePipeline
from .responder import Responder
from .settings import Settings
from .transcribe import Transcriber

console = Console()


def _build_pipeline(settings: Settings) -> VoicePipeline:
    transcriber = Transcriber(api_key=settings.openai_api_key, model=settings.whisper_model)
    responder = Responder(
        api_key=settings.anthropic_api_key,
        sonnet_model=settings.claude_sonnet_model,
        haiku_model=settings.claude_haiku_model,
        max_response_chars=settings.max_response_chars,
    )
    evolution = EvolutionClient(
        base_url=settings.evolution_base_url,
        api_key=settings.evolution_api_key,
        instance=settings.evolution_default_instance,
    )
    return VoicePipeline(transcriber, responder, evolution, settings)


def _print_result(result, send_to=None):
    if result.transcript:
        console.print(Panel(result.transcript, title="entrada (transcrição/texto)", border_style="cyan"))
    console.print(
        Panel(
            result.answer or "[vazio]",
            title=f"resposta — {result.model_used or '?'} (artigos: {len(result.articles_used)})",
            border_style="magenta",
        )
    )
    if result.articles_used:
        console.print(f"[dim]Artigos consultados: {', '.join(result.articles_used)}[/]")
    if send_to:
        if result.sent:
            console.print(f"[green]✓ enviado para[/] {send_to}")
        elif result.blocked_by_whitelist:
            console.print(f"[yellow]⚠ bloqueado pela whitelist:[/] {send_to}")
        else:
            console.print(f"[red]✗ envio falhou:[/] {result.error}")
    elif result.error:
        console.print(f"[red]erro:[/] {result.error}")


def cmd_audio(args, settings: Settings, pipeline: VoicePipeline) -> None:
    p = Path(args.file)
    if not p.is_file():
        console.print(f"[red]Arquivo não encontrado:[/] {p}")
        sys.exit(2)
    mime = mimetypes.guess_type(p.name)[0] or "audio/ogg"
    console.print(f"[dim]Processando {p.name} ({p.stat().st_size} bytes, {mime})...[/]")
    result = pipeline.process_audio_bytes(
        audio_bytes=p.read_bytes(),
        mime_type=mime,
        conversation_key=args.conversation,
        reply_to_number=args.send,
    )
    _print_result(result, args.send)


def cmd_texto(args, settings: Settings, pipeline: VoicePipeline) -> None:
    result = pipeline.process_text(
        text=args.text,
        conversation_key=args.conversation,
        reply_to_number=args.send,
    )
    _print_result(result, args.send)


def cmd_chat(args, settings: Settings, pipeline: VoicePipeline) -> None:
    conversation = args.conversation
    console.print(
        Panel.fit(
            f"[bold green]Chat com Agente Blink[/]\n"
            f"[dim]Conversa: {conversation}\n"
            f"Modelo principal: {settings.claude_sonnet_model}\n"
            f"Modelo rápido: {settings.claude_haiku_model}\n"
            f"Whitelist: {len(settings.whitelist_numbers)} número(s) "
            f"(strict={settings.whitelist_strict})\n"
            f"Comandos: /reset, /quit[/]",
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
            return
        if user_input.lower() == "/reset":
            pipeline.responder.reset(conversation)
            console.print("[dim]histórico limpo[/]")
            continue
        result = pipeline.process_text(
            text=user_input,
            conversation_key=conversation,
            reply_to_number=None,  # sem enviar — só simula
        )
        _print_result(result)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Agente Blink — CLI")
    parser.add_argument("--conversation", default="cli", help="Chave de conversa (default: cli)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sa = sub.add_parser("audio", help="Processa arquivo de áudio")
    sa.add_argument("file", help="Arquivo de áudio (.ogg/.mp3/.m4a/.wav)")
    sa.add_argument("--send", metavar="NUMBER", help="Envia resposta via WhatsApp")

    st = sub.add_parser("texto", help="Processa mensagem de texto")
    st.add_argument("text", help="Texto da mensagem do paciente")
    st.add_argument("--send", metavar="NUMBER", help="Envia resposta via WhatsApp")

    sc = sub.add_parser("chat", help="Chat interativo (não envia, só simula)")

    args = parser.parse_args(argv)
    settings = Settings.load()
    pipeline = _build_pipeline(settings)

    {
        "audio": cmd_audio,
        "texto": cmd_texto,
        "chat": cmd_chat,
    }[args.cmd](args, settings, pipeline)


if __name__ == "__main__":
    main()
