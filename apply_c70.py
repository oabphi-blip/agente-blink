#!/usr/bin/env python3
"""Bug C-70 — bloqueia link de vídeo/música NÃO autorizado (rickroll alucinado).

Aplica o guarda determinístico em voice_agent/responder.py e cria o pytest.
Roda LOCALMENTE (não depende da ponte de nuvem). Idempotente.
"""
import io
import os
import sys

REPO = os.path.dirname(os.path.abspath(__file__))
RESP = os.path.join(REPO, "voice_agent", "responder.py")
TEST = os.path.join(REPO, "tests", "test_bug_c70_link_nao_autorizado.py")

src = io.open(RESP, encoding="utf-8").read()

if "Bug C-70" in src:
    print("C-70 já aplicado em responder.py — pulando patch.")
else:
    # ---- 1) helpers, inseridos antes de def _scrub_prohibited ----
    anchor_h = "def _scrub_prohibited(text: str, ctx: Optional[dict] = None) -> str:"
    if src.count(anchor_h) != 1:
        print("ERRO: âncora de helper não única (%d). Abortando." % src.count(anchor_h))
        sys.exit(1)

    helper = r'''# ─────────────────────────────────────────────────────────────────────────
# Bug C-70 (22/07/2026, lead 24330420 Anny) — LINK NÃO AUTORIZADO
# ─────────────────────────────────────────────────────────────────────────
# A Lia vazou o pitch de "vídeo da Dra. Karla" (exclusivo de leads de
# estrabismo, KB 20) num lead de Oftalmologia Geral E ALUCINOU a URL:
# mandou https://www.youtube.com/watch?v=dQw4w9WgXcQ (rickroll) pra
# paciente. Guarda determinístico: remove qualquer link de vídeo/música
# que NÃO seja o único autorizado (short de estrabismo K8zmQEJazlU) e a
# frase de pitch associada. NÃO toca em link de pagamento/avaliação/Kommo.
# ─────────────────────────────────────────────────────────────────────────
_C70_VIDEO_IDS_AUTORIZADOS = ("K8zmQEJazlU",)
_C70_DOMINIOS_VIDEO_MUSICA = (
    "youtube.com", "youtu.be", "music.", "spotify", "soundcloud",
    "vimeo.com", "tiktok.com",
)
_C70_MARCAS_PITCH_VIDEO = (
    "preparei um vídeo", "preparamos um vídeo", "preparei um video",
    "preparamos um video", "vídeo curtinho", "video curtinho",
    "vale muito a pena assistir", "vale a pena assistir",
)


def _c70_url_video_nao_autorizada(url: str) -> bool:
    low = url.lower()
    if not any(d in low for d in _C70_DOMINIOS_VIDEO_MUSICA):
        return False
    return not any(vid in url for vid in _C70_VIDEO_IDS_AUTORIZADOS)


def _scrub_link_nao_autorizado(text: str) -> str:
    """Remove link de vídeo/música não autorizado + pitch (Bug C-70)."""
    if not text or "http" not in text.lower():
        return text
    tem_nao_aut = any(
        _c70_url_video_nao_autorizada(u)
        for u in re.findall(r"https?://\S+", text)
    )
    if not tem_nao_aut:
        return text
    linhas = []
    for ln in text.split("\n"):
        low = ln.lower()
        tem_link_va = ("http" in low) and any(
            d in low for d in _C70_DOMINIOS_VIDEO_MUSICA
        )
        autorizado = any(vid in ln for vid in _C70_VIDEO_IDS_AUTORIZADOS)
        if tem_link_va and not autorizado:
            continue
        if any(mk in low for mk in _C70_MARCAS_PITCH_VIDEO):
            continue
        linhas.append(ln)
    out = re.sub(r"\n{3,}", "\n\n", "\n".join(linhas)).strip()
    if not out:
        out = "Perfeito! Como posso te ajudar com o seu atendimento?"
    log.error(
        "[FILTRO C-70] Link video/musica NAO autorizado removido. original=%r",
        text[:200],
    )
    return out


'''
    src = src.replace(anchor_h, helper + anchor_h, 1)

    # ---- 2) chamada do filtro, antes do FILTRO C-66 ----
    anchor_f = "    # === FILTRO C-66 SEMPRE-ON (Fábio 21/07/2026, lead 21329281 Letícia) ==="
    if src.count(anchor_f) != 1:
        print("ERRO: âncora de filtro não única (%d). Abortando." % src.count(anchor_f))
        sys.exit(1)

    filtro = (
        "    # === FILTRO C-70 SEMPRE-ON (Fábio 22/07/2026, lead 24330420 Anny) ===\n"
        "    # Remove link de vídeo/música não autorizado (rickroll alucinado) + pitch.\n"
        "    text = _scrub_link_nao_autorizado(text)\n\n"
        + anchor_f
    )
    src = src.replace(anchor_f, filtro, 1)

    io.open(RESP, "w", encoding="utf-8").write(src)
    print("C-70 aplicado em responder.py.")

# ---- 3) cria o pytest (sempre reescreve) ----
teste = r'''"""Bug C-70 — bloqueio de link de vídeo/música não autorizado (rickroll)."""
from voice_agent.responder import _scrub_link_nao_autorizado


def test_remove_rickroll_e_pitch():
    txt = (
        "Olá, Anny! Claro que posso te ajudar!\n\n"
        "Antes de tudo, preparei um vídeo curtinho da Dra. Karla explicando "
        "como funciona o atendimento. Vale muito a pena assistir\n\n"
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ\n\n"
        "Agora me conta: a consulta é pra você mesma ou pra outra pessoa?"
    )
    out = _scrub_link_nao_autorizado(txt)
    assert "youtube.com" not in out.lower()
    assert "dQw4w9WgXcQ" not in out
    assert "vídeo" not in out.lower()
    assert "consulta" in out.lower()


def test_preserva_video_autorizado_estrabismo():
    txt = (
        "Olá! preparamos um vídeo curtinho da Dra. Karla.\n"
        "https://youtube.com/shorts/K8zmQEJazlU"
    )
    out = _scrub_link_nao_autorizado(txt)
    assert "K8zmQEJazlU" in out


def test_nao_toca_em_link_de_pagamento():
    txt = "Segue o link de pagamento: https://asaas.com/c/abc123"
    out = _scrub_link_nao_autorizado(txt)
    assert "asaas.com/c/abc123" in out


def test_texto_sem_link_inalterado():
    txt = "Qual unidade fica melhor — Asa Norte ou Águas Claras?"
    assert _scrub_link_nao_autorizado(txt) == txt
'''
io.open(TEST, "w", encoding="utf-8").write(teste)
print("Teste criado: tests/test_bug_c70_link_nao_autorizado.py")
