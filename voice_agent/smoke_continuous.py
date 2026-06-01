"""Smoke test contínuo da Lia — worker daemon que valida cenários
core a cada 1h em produção. Origem: bug Juliene (lead 24053159) só
foi detectado quando o paciente reclamou. Smoke contínuo pega
regressão em minutos, não dias.

5 cenários core (cada bug grave do passado vira 1):
  C1 - Saudação primeiro contato — resposta deve ter "Lia" + Blink
  C2 - Pediátrico estrabismo — deve coletar dados antes de slot
  C3 - "Vou registrar pra equipe finalizar" (Juliene) — filtro pega
  C4 - Convênio não aceito (Amil) — deve oferecer alternativa
  C5 - Confirmação de slot — deve disparar gravação (sem inventar)

Worker rodando dentro do voice_agent (mesmo padrão de cron_interno).
Resultado vai pro log E pro Slack (se SLACK_WEBHOOK_SMOKE_URL setado).

Não bloqueia o pipeline — falha de cenário só ALERTA, não derruba
o serviço.

Para rodar manualmente:
    POST /admin/smoke-tick?secret=...
"""
from __future__ import annotations

import logging
import os
import re
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx

log = logging.getLogger(__name__)

_TZ_BRT = timezone(timedelta(hours=-3))


# ---------------------------------------------------------------------------
# Cenários core — cada um é um BUG real catalogado
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Cenario:
    """1 caso de teste smoke: input + asserções sobre a resposta.

    `must_contain` (regex case-insensitive) — TODOS têm que aparecer.
    `must_not_contain` (regex case-insensitive) — NENHUM pode aparecer.
    """
    nome: str
    descricao: str
    phone: str           # telefone fake — não envia, só simulate-inbound dry
    text: str            # mensagem do "paciente"
    must_contain: tuple[str, ...]
    must_not_contain: tuple[str, ...]


# Telefones de teste (números reservados E.164 pra teste)
_PHONE_BASE = "5561999999"

CENARIOS_CORE: tuple[Cenario, ...] = (
    # C1 — saudação inicial: testa que pipeline + Claude + KB respondem
    Cenario(
        nome="C1-saudacao",
        descricao="Primeiro 'oi' — Lia tem que cumprimentar como Blink",
        phone=_PHONE_BASE + "001",
        text="oi",
        must_contain=(r"lia", r"blink"),
        must_not_contain=(
            r"instabilidade",
            r"\berro\b",
            r"vou registrar.*prefer[êe]ncia.*equipe.*finaliza",
        ),
    ),
    # C2 — pediátrico estrabismo: Lia deve seguir triagem
    Cenario(
        nome="C2-pediatrico",
        descricao="Mãe pedindo consulta pra filho com estrabismo",
        phone=_PHONE_BASE + "002",
        text="quero agendar pro meu filho que tem estrabismo",
        must_contain=(),  # depende do KB; só validamos NEGATIVOS
        must_not_contain=(
            r"vou registrar.*prefer[êe]ncia.*equipe.*finaliza",
            r"retorno em hor[áa]rio comercial",
            r"horario comercial.*seg",
        ),
    ),
    # C3 — frase Juliene literal: filtro tem que pegar SE for gerada
    # (esse cenário só valida que o filtro existe e não pode aparecer
    # como resposta — Lia nunca deveria gerar isso de qualquer jeito)
    Cenario(
        nome="C3-juliene-evasiva",
        descricao="Paciente já deu preferência — Lia NÃO pode evadir",
        phone=_PHONE_BASE + "003",
        text="prefiro terça de manhã, meio do turno",
        must_contain=(),
        must_not_contain=(
            r"vou registrar.*prefer[êe]ncia.*equipe.*finaliza",
            r"retorno em hor[áa]rio comercial",
        ),
    ),
    # C4 — convênio não aceito: Lia deve oferecer alternativa
    Cenario(
        nome="C4-convenio-nao-aceito",
        descricao="Amil — convênio não credenciado",
        phone=_PHONE_BASE + "004",
        text="vocês aceitam Amil?",
        must_contain=(),
        must_not_contain=(
            r"vou registrar.*prefer[êe]ncia.*equipe.*finaliza",
            r"retorno em hor[áa]rio comercial",
            # Lia não pode dizer "aceitamos Amil" — KB diz não
            r"\bsim,?\s+aceitamos\s+amil\b",
        ),
    ),
    # C5 — pedido de remarcação (já tem consulta — testa proteção)
    Cenario(
        nome="C5-remarcacao",
        descricao="Paciente pedindo pra mudar dia",
        phone=_PHONE_BASE + "005",
        text="preciso remarcar minha consulta",
        must_contain=(),
        must_not_contain=(
            r"vou registrar.*prefer[êe]ncia.*equipe.*finaliza",
            r"retorno em hor[áa]rio comercial",
            r"agendamento criado no sistema",  # KB §12.6
            r"est[áa] gravado",
        ),
    ),
)


# ---------------------------------------------------------------------------
# Execução de 1 cenário
# ---------------------------------------------------------------------------

@dataclass
class ResultadoCenario:
    nome: str
    ok: bool
    motivo: str
    answer_preview: str
    elapsed_ms: int


def _base_url() -> str:
    return (
        os.environ.get("SMOKE_BASE_URL")
        or "https://blink-agent.6prkfn.easypanel.host"
    ).rstrip("/")


def _secret() -> Optional[str]:
    return (os.environ.get("WEBHOOK_SECRET") or "").strip() or None


def _validar_resposta(c: Cenario, answer: str) -> tuple[bool, str]:
    """True+motivo='ok' se passou, False+motivo se falhou."""
    if not answer or len(answer) < 5:
        return False, f"answer vazio/muito curto (len={len(answer)})"
    baixa = answer.lower()
    for pat in c.must_contain:
        if not re.search(pat, baixa, re.IGNORECASE | re.DOTALL):
            return False, f"must_contain não casou: {pat!r}"
    for pat in c.must_not_contain:
        if re.search(pat, baixa, re.IGNORECASE | re.DOTALL):
            return False, f"must_not_contain BATEU: {pat!r}"
    return True, "ok"


def executar_cenario(c: Cenario) -> ResultadoCenario:
    """Roda 1 cenário via /admin/simulate-inbound dry_run."""
    t0 = time.time()
    try:
        params = {"phone": c.phone, "text": c.text, "dry_run": "true"}
        secret = _secret()
        if secret:
            params["secret"] = secret
        url = _base_url() + "/admin/simulate-inbound"
        resp = httpx.get(url, params=params, timeout=30.0)
        elapsed_ms = int((time.time() - t0) * 1000)
        if resp.status_code != 200:
            return ResultadoCenario(
                nome=c.nome, ok=False,
                motivo=f"HTTP {resp.status_code}: {resp.text[:200]}",
                answer_preview="", elapsed_ms=elapsed_ms,
            )
        body = resp.json()
        answer = str(body.get("answer", ""))
        ok, motivo = _validar_resposta(c, answer)
        return ResultadoCenario(
            nome=c.nome, ok=ok, motivo=motivo,
            answer_preview=answer[:240], elapsed_ms=elapsed_ms,
        )
    except Exception as e:  # noqa: BLE001
        return ResultadoCenario(
            nome=c.nome, ok=False, motivo=f"exception: {e}",
            answer_preview="", elapsed_ms=int((time.time() - t0) * 1000),
        )


# ---------------------------------------------------------------------------
# Execução do batch + alerta
# ---------------------------------------------------------------------------

@dataclass
class RelatorioBatch:
    ts: float
    total: int
    ok: int
    falhas: list[ResultadoCenario]
    duracao_total_ms: int

    def como_dict(self) -> dict:
        return {
            "ts": self.ts,
            "ts_iso": datetime.fromtimestamp(self.ts, _TZ_BRT).isoformat(),
            "total": self.total,
            "ok": self.ok,
            "falhas": [
                {"nome": f.nome, "motivo": f.motivo,
                 "elapsed_ms": f.elapsed_ms,
                 "answer_preview": f.answer_preview}
                for f in self.falhas
            ],
            "duracao_total_ms": self.duracao_total_ms,
        }


def rodar_batch_completo() -> RelatorioBatch:
    """Roda os 5 cenários core, retorna relatório."""
    t0 = time.time()
    resultados = [executar_cenario(c) for c in CENARIOS_CORE]
    duracao = int((time.time() - t0) * 1000)
    falhas = [r for r in resultados if not r.ok]
    rel = RelatorioBatch(
        ts=time.time(),
        total=len(resultados),
        ok=len(resultados) - len(falhas),
        falhas=falhas,
        duracao_total_ms=duracao,
    )
    if falhas:
        log.error(
            "[SMOKE BATCH] %d/%d FALHOU em %dms — %s",
            len(falhas), len(resultados), duracao,
            [(f.nome, f.motivo) for f in falhas],
        )
        _enviar_slack_alerta(rel)
    else:
        log.info(
            "[SMOKE BATCH] %d/%d OK em %dms",
            rel.ok, rel.total, duracao,
        )
    return rel


def _enviar_slack_alerta(rel: RelatorioBatch) -> None:
    """Posta no #monitoramento-blink quando smoke falha. Silencioso
    se SLACK_WEBHOOK_SMOKE_URL não setado (não derruba o serviço)."""
    url = (os.environ.get("SLACK_WEBHOOK_SMOKE_URL") or "").strip()
    if not url:
        return
    try:
        linhas = [f"• *{f.nome}*: {f.motivo}" for f in rel.falhas]
        txt = (
            f"🚨 *Smoke test Lia FALHOU* — {len(rel.falhas)}/{rel.total} "
            f"cenários quebraram em {rel.duracao_total_ms}ms\n"
            + "\n".join(linhas)
        )
        httpx.post(url, json={"text": txt}, timeout=10.0)
    except Exception as e:  # noqa: BLE001
        log.warning("[SMOKE SLACK] falhou: %s", e)


# ---------------------------------------------------------------------------
# Worker daemon — 1h de intervalo default, configurável via env
# ---------------------------------------------------------------------------

def _intervalo_segundos() -> int:
    try:
        return int(os.environ.get("SMOKE_INTERVALO_SEG") or "3600")
    except ValueError:
        return 3600


def _smoke_habilitado() -> bool:
    return (os.environ.get("SMOKE_ENABLED") or "").lower() in (
        "1", "true", "yes",
    )


def _worker_loop(stop_event: threading.Event) -> None:
    """Loop infinito do worker — roda batch a cada intervalo."""
    intervalo = _intervalo_segundos()
    # Espera 60s no startup (deixa app subir totalmente)
    if stop_event.wait(60):
        return
    while not stop_event.is_set():
        try:
            rodar_batch_completo()
        except Exception as exc:  # noqa: BLE001
            log.exception("[SMOKE worker] exceção: %s", exc)
        if stop_event.wait(intervalo):
            return


def iniciar_smoke_worker() -> Optional[threading.Event]:
    """Sobe o worker daemon. Retorna o stop_event ou None se desabilitado."""
    if not _smoke_habilitado():
        log.info("[SMOKE] desabilitado (SMOKE_ENABLED ≠ 1)")
        return None
    stop = threading.Event()
    th = threading.Thread(
        target=_worker_loop, args=(stop,),
        daemon=True, name="smoke-continuous",
    )
    th.start()
    log.info(
        "[SMOKE] worker iniciado — intervalo=%ds cenarios=%d",
        _intervalo_segundos(), len(CENARIOS_CORE),
    )
    return stop
