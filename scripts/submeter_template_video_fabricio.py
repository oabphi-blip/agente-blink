#!/usr/bin/env python3
"""
Submeter template Meta WhatsApp Cloud com HEADER VIDEO pro Dr. Fabrício.

Roda LOCAL no Mac do Fábio (não no sandbox — sandbox bloqueia YouTube/Drive).

Fluxo:
  1. Comprime vídeo de entrada (~/Downloads/fabricio_video.mp4 ou
     parâmetro --input) pra <16MB H.264 baseline.
  2. Resumable Upload pra Meta Graph API → pega header_handle.
  3. POST /message_templates com HEADER=VIDEO + BODY + BUTTONS.
  4. Retorna template ID + status.

Requer no .env (lia_engineer/.env.local):
  WHATSAPP_CLOUD_TOKEN=<token system user permanente>
  WHATSAPP_CLOUD_APP_ID=<APP ID Meta App, ex 1234567890>
  WHATSAPP_CLOUD_BUSINESS_ACCOUNT_ID=1990931811727552  (WABA_ID)

Se WABA_ID faltar usa default 1990931811727552 (Blink).
Se APP_ID faltar abre instruções pra Fábio achar e adicionar.
"""

import os
import sys
import argparse
import subprocess
import json
from pathlib import Path
import urllib.request
import urllib.error


REPO_DIR = Path(__file__).resolve().parents[1]
ENV_FILES = [
    REPO_DIR / "lia_engineer" / ".env.local",
    REPO_DIR / ".env.local",
    REPO_DIR / ".env",
]

DEFAULT_WABA_ID = "1990931811727552"
META_GRAPH_VERSION = "v22.0"


def load_env():
    for f in ENV_FILES:
        if not f.exists():
            continue
        for line in f.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            v = v.strip().strip('"').strip("'")
            if k.strip() and k.strip() not in os.environ:
                os.environ[k.strip()] = v


load_env()


def comprimir(input_path: Path, output_path: Path, alvo_mb: int = 14) -> Path:
    """Comprime vídeo pra ~alvo_mb. Retorna path do MP4 final."""
    if not input_path.exists():
        raise FileNotFoundError(f"Vídeo não encontrado: {input_path}")

    tamanho_orig = input_path.stat().st_size / (1024 * 1024)
    print(f"▶ Comprimindo {input_path.name} ({tamanho_orig:.1f} MB → alvo {alvo_mb} MB)")

    # Estratégia padrão: baseline H.264, 720p max, 60s max, ~1.2 Mbps vídeo + 96 kbps áudio
    cmd_padrao = [
        "ffmpeg", "-y", "-i", str(input_path),
        "-c:v", "libx264", "-preset", "medium",
        "-profile:v", "baseline", "-level", "3.1",
        "-vf", "scale='min(720,iw)':-2",
        "-b:v", "1200k", "-maxrate", "1500k", "-bufsize", "2000k",
        "-c:a", "aac", "-b:a", "96k",
        "-movflags", "+faststart",
        "-t", "60",
        str(output_path),
    ]
    r = subprocess.run(cmd_padrao, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"❌ ffmpeg falhou:\n{r.stderr[-500:]}")
        raise SystemExit(2)

    tamanho_mb = output_path.stat().st_size / (1024 * 1024)
    print(f"  Saída: {tamanho_mb:.1f} MB")

    if tamanho_mb > 16:
        print("  ⚠️  Acima de 16MB. Recomprimindo mais agressivo (540p, 800k)...")
        cmd_agressivo = [
            "ffmpeg", "-y", "-i", str(input_path),
            "-c:v", "libx264", "-preset", "slow",
            "-profile:v", "baseline", "-level", "3.1",
            "-vf", "scale='min(540,iw)':-2",
            "-b:v", "800k", "-maxrate", "1000k", "-bufsize", "1500k",
            "-c:a", "aac", "-b:a", "64k",
            "-movflags", "+faststart",
            "-t", "60",
            str(output_path),
        ]
        r = subprocess.run(cmd_agressivo, capture_output=True, text=True)
        if r.returncode != 0:
            print(f"❌ ffmpeg falhou:\n{r.stderr[-500:]}")
            raise SystemExit(2)
        tamanho_mb = output_path.stat().st_size / (1024 * 1024)
        print(f"  Saída final: {tamanho_mb:.1f} MB")

    return output_path


def http_request(method: str, url: str, headers: dict | None = None,
                 data: bytes | str | None = None, timeout: int = 120) -> tuple[int, dict | str]:
    headers = headers or {}
    if isinstance(data, str):
        data = data.encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read().decode("utf-8")
            try:
                return r.status, json.loads(body)
            except json.JSONDecodeError:
                return r.status, body
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        try:
            return e.code, json.loads(body)
        except json.JSONDecodeError:
            return e.code, body


def upload_resumable(video_path: Path, app_id: str, token: str) -> str:
    """Resumable Upload Meta → retorna `h` (header_handle)."""
    file_length = video_path.stat().st_size
    print(f"\n▶ Iniciando upload Resumable ({file_length / (1024 * 1024):.1f} MB)")

    # Etapa 1 — iniciar sessão
    url_start = (
        f"https://graph.facebook.com/{META_GRAPH_VERSION}/{app_id}/uploads"
        f"?file_length={file_length}&file_type=video/mp4&access_token={token}"
    )
    status, resp = http_request("POST", url_start)
    if status >= 400:
        print(f"❌ Falha ao iniciar upload: HTTP {status} → {resp}")
        raise SystemExit(2)
    session_id = resp.get("id")
    if not session_id:
        print(f"❌ Resposta sem session_id: {resp}")
        raise SystemExit(2)
    print(f"  Session: {session_id}")

    # Etapa 2 — enviar binário
    print("  Enviando bytes...")
    with video_path.open("rb") as f:
        data = f.read()
    url_upload = f"https://graph.facebook.com/{META_GRAPH_VERSION}/{session_id}"
    status, resp = http_request(
        "POST", url_upload,
        headers={
            "Authorization": f"OAuth {token}",
            "file_offset": "0",
        },
        data=data,
        timeout=300,
    )
    if status >= 400:
        print(f"❌ Upload binário falhou: HTTP {status} → {resp}")
        raise SystemExit(2)
    h_handle = resp.get("h")
    if not h_handle:
        print(f"❌ Sem 'h' na resposta: {resp}")
        raise SystemExit(2)
    print(f"  ✓ Handle: {h_handle[:40]}...")
    return h_handle


def submeter_template(waba_id: str, token: str, header_handle: str,
                      nome_template: str) -> dict:
    """Submete template com HEADER VIDEO + BODY + BUTTONS."""
    payload = {
        "name": nome_template,
        "language": "pt_BR",
        "category": "MARKETING",
        "components": [
            {
                "type": "HEADER",
                "format": "VIDEO",
                "example": {"header_handle": [header_handle]},
            },
            {
                "type": "BODY",
                "text": (
                    "Olá, {{1}}! 👋\n\n"
                    "Sou Dr. Fabrício Freitas, especialista em catarata "
                    "e saúde ocular do adulto 50+ na Blink Oftalmologia.\n\n"
                    "Atendo em Asa Norte e Águas Claras (DF) - avaliação "
                    "inicial + acompanhamento cirúrgico personalizado.\n\n"
                    "Quer agendar uma avaliação?"
                ),
                "example": {"body_text": [["paciente"]]},
            },
            {
                "type": "BUTTONS",
                "buttons": [
                    {"type": "QUICK_REPLY", "text": "Quero agendar"},
                    {"type": "QUICK_REPLY", "text": "Mais informações"},
                    {"type": "QUICK_REPLY", "text": "Me ligue depois"},
                ],
            },
        ],
    }
    url = (
        f"https://graph.facebook.com/{META_GRAPH_VERSION}/{waba_id}/message_templates"
        f"?access_token={token}"
    )
    print(f"\n▶ Submetendo template '{nome_template}' ...")
    status, resp = http_request(
        "POST", url,
        headers={"Content-Type": "application/json"},
        data=json.dumps(payload),
    )
    if status >= 400:
        print(f"❌ Submissão falhou: HTTP {status}")
        print(f"   Resposta: {json.dumps(resp, indent=2)[:1500]}")
        raise SystemExit(2)
    return resp


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", type=str,
                    default=str(Path.home() / "Downloads" / "fabricio_video.mp4"))
    ap.add_argument("--nome", type=str,
                    default="video_apresentar_fabricio_freitas_v1")
    ap.add_argument("--app-id", type=str, default=None,
                    help="Meta App ID (sobrescreve env WHATSAPP_CLOUD_APP_ID)")
    ap.add_argument("--waba-id", type=str, default=None)
    ap.add_argument("--skip-upload", action="store_true",
                    help="Só comprime, não submete (gera /tmp/template_payload.json)")
    args = ap.parse_args()

    token = os.environ.get("WHATSAPP_CLOUD_TOKEN", "").strip()
    app_id = args.app_id or os.environ.get("WHATSAPP_CLOUD_APP_ID", "").strip()
    waba_id = args.waba_id or os.environ.get("WHATSAPP_CLOUD_BUSINESS_ACCOUNT_ID", "").strip() or DEFAULT_WABA_ID

    if not token:
        print("❌ WHATSAPP_CLOUD_TOKEN não configurado em lia_engineer/.env.local")
        sys.exit(2)

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"❌ Vídeo de entrada não existe: {input_path}")
        print("")
        print("📥 Baixe o vídeo do Drive PRIMEIRO (escolha qual):")
        print("")
        print("  Apresentação (Primeira Consulta) - 245MB:")
        print("    https://drive.google.com/file/d/1zsJxkm-VHv_VX-O04H0cafLHOEDmXOFL/view")
        print("")
        print("  Educacional Indicação para cirurgia - 43MB (recomendado):")
        print("    https://drive.google.com/file/d/1XxlbRHoEokJKxTJ_kJ5jiHiyynWSPDWG/view")
        print("")
        print("  Catarata cega - 55MB:")
        print("    https://drive.google.com/file/d/1xhlZ4WktCN03Cncc8VOCEkiF0RA3SCDJ/view")
        print("")
        print(f"  Salve em: {input_path}")
        print("")
        print("Tentando abrir o link recomendado no browser...")
        try:
            subprocess.run(
                ["open", "https://drive.google.com/file/d/1XxlbRHoEokJKxTJ_kJ5jiHiyynWSPDWG/view"],
                check=False,
            )
        except Exception:
            pass
        sys.exit(1)

    # Comprime
    saida_mp4 = Path("/tmp/fabricio_template.mp4")
    comprimir(input_path, saida_mp4)

    if args.skip_upload or not app_id:
        if not app_id:
            print("")
            print("⚠️  WHATSAPP_CLOUD_APP_ID não configurado em .env.local.")
            print("")
            print("Pra achar:")
            print("  1. https://developers.facebook.com/apps/")
            print("  2. Clique no app da Blink (whatsapp business)")
            print("  3. Configurações > Básico → 'ID do aplicativo'")
            print("")
            print("Adicione em lia_engineer/.env.local:")
            print("  WHATSAPP_CLOUD_APP_ID=<ID copiado>")
            print("")
            print("Depois rode esse script de novo.")
        print(f"\n✅ Vídeo comprimido em: {saida_mp4}")
        print("   Submeta manualmente via Business Manager OU rode com --app-id <X>")
        sys.exit(0)

    # Upload + submissão
    handle = upload_resumable(saida_mp4, app_id, token)
    resp = submeter_template(waba_id, token, handle, args.nome)

    print("\n✅ TEMPLATE SUBMETIDO!")
    print(json.dumps(resp, indent=2, ensure_ascii=False))
    print("")
    print("Próximos passos:")
    print(f"  1. Aguardar aprovação Meta (24-72h)")
    print(f"  2. Validar via /admin/listar-templates-meta procurando '{args.nome}'")
    print(f"  3. Plugar slug em voice_agent/templates_meta.py")


if __name__ == "__main__":
    main()
