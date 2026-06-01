#!/usr/bin/env python3
"""Gera 24 áudios MP3 da Dra. Karla via OpenAI TTS.

Como rodar:
    cd ~/Documents/Claude/Projects/AGENTE\\ IA\\ BLINK/outputs/audios_karla
    export OPENAI_API_KEY=sk-...   # ou já tem no shell
    python3 gerar_audios.py

Resultado: 24 arquivos mp3 nesta pasta (audio_01_*.mp3 .. audio_24_*.mp3).
Custo estimado: ~US$ 0,25 total (tts-1-hd, 8.261 chars).

Modelo: tts-1-hd (qualidade alta)
Voz: nova (feminina jovem profissional — recomendada pra Dra. Karla)
Formato: MP3
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

try:
    from openai import OpenAI
except ImportError:
    print(
        "ERRO: biblioteca 'openai' não instalada.\n"
        "Instale com:  pip3 install --user openai",
        file=sys.stderr,
    )
    sys.exit(2)


VOZ = os.environ.get("TTS_VOZ", "shimmer")  # shimmer / nova / alloy / fable / echo / onyx
MODELO = os.environ.get("TTS_MODELO", "tts-1-hd")  # tts-1-hd ou tts-1
AMOSTRA = os.environ.get("AMOSTRA", "").strip() == "1"  # só roteiro 22 em 2 vozes


def main() -> int:
    aqui = Path(__file__).resolve().parent
    roteiros_path = aqui / "roteiros.json"
    if not roteiros_path.exists():
        print(f"ERRO: {roteiros_path} não encontrado", file=sys.stderr)
        return 1

    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not key.startswith("sk-"):
        print(
            "ERRO: OPENAI_API_KEY não setada.\n"
            "Rode no terminal antes:\n"
            "  export OPENAI_API_KEY=sk-...\n"
            "ou cole a chave que tem no Easypanel.",
            file=sys.stderr,
        )
        return 1

    client = OpenAI(api_key=key)
    roteiros = json.loads(roteiros_path.read_text(encoding="utf-8"))

    # Modo AMOSTRA: gera só roteiro 22 (acolhimento geral) em 2 vozes
    # pra você comparar antes do batch completo.
    if AMOSTRA:
        roteiro_22 = next((r for r in roteiros if r["n"] == 22), None)
        if not roteiro_22:
            print("ERRO: roteiro 22 não encontrado", file=sys.stderr)
            return 1
        vozes_amostra = ["shimmer", "alloy"]
        print(f"Modo AMOSTRA — roteiro 22 em {len(vozes_amostra)} vozes\n")
        for voz in vozes_amostra:
            nome_arquivo = f"AMOSTRA_voz_{voz}.mp3"
            out = aqui / nome_arquivo
            print(f"[{voz}]  →  {nome_arquivo}")
            try:
                resp = client.audio.speech.create(
                    model=MODELO,
                    voice=voz,
                    input=roteiro_22["texto"],
                    response_format="mp3",
                )
                resp.stream_to_file(str(out))
                print(f"        OK  {out.stat().st_size // 1024} KB")
            except Exception as exc:  # noqa: BLE001
                print(f"        FALHOU: {exc}", file=sys.stderr)
                return 1
        print(f"\nAmostras em: {aqui}")
        print("Escute as 2 e me diga qual voz vai ficar.")
        print("Depois, pra gerar os 24:")
        print("  TTS_VOZ=shimmer python3 gerar_audios.py   # ou alloy")
        return 0

    total = len(roteiros)
    print(f"Gerando {total} áudios — voz={VOZ} modelo={MODELO}\n")

    sucessos = 0
    falhas = []
    for r in roteiros:
        n = r["n"]
        slug = r.get("slug") or f"audio_{n:02d}"
        nome_arquivo = f"audio_{n:02d}_{slug.lstrip('0123456789_')}.mp3"
        out = aqui / nome_arquivo
        print(f"[{n:02d}/{total}] {r['titulo'][:60]}  →  {nome_arquivo}")
        if out.exists():
            print(f"           já existe — pulando")
            sucessos += 1
            continue
        try:
            resp = client.audio.speech.create(
                model=MODELO,
                voice=VOZ,
                input=r["texto"],
                response_format="mp3",
            )
            resp.stream_to_file(str(out))
            tam = out.stat().st_size
            print(f"           OK  {tam // 1024} KB")
            sucessos += 1
            time.sleep(0.4)  # pequena pausa pra evitar rate limit
        except Exception as exc:  # noqa: BLE001
            print(f"           FALHOU: {exc}", file=sys.stderr)
            falhas.append((n, str(exc)[:200]))

    print()
    print(f"Concluído: {sucessos}/{total} áudios gerados.")
    if falhas:
        print("Falhas:")
        for n, msg in falhas:
            print(f"  {n}: {msg}")
        return 1
    print(f"\nArquivos em: {aqui}")
    print(
        "\nPróximo passo:\n"
        "  1. Subir os MP3 pro storage do voice_agent:\n"
        "     scp audio_*.mp3 root@blink-agent:/app/voice_agent/static/audios/\n"
        "  2. URL base já existe: https://blink-agent.6prkfn.easypanel.host/static/audios\n"
        "  3. Plugar gatilho na renovacao_dispatcher pra anexar áudio\n"
        "     quando palavra-chave bater (catarata, valor, estrabismo, etc.)"
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nInterrompido (Ctrl+C).")
        sys.exit(130)
