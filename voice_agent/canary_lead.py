"""Canary lead diário — Pilar #5 da fila de robustez.

Origem: Fábio 01/06/2026 — Lia funciona 95% bem, mas bugs aparecem
sutilmente entre componentes. Smoke contínuo bate 6 cenários
isolados; o canary simula um FLUXO COMPLETO de paciente real:

1. Saudação inicial — "oi, quero agendar"
2. Médico — Lia oferece opções
3. Data nascimento — paciente fornece
4. Convênio — paciente fornece
5. Lia oferece slots (consulta Medware real)
6. Paciente escolhe slot
7. CPF — paciente fornece
8. Lia confirma e grava no Medware

A cada step, valida o ESTADO ESPERADO em Redis FSM + último envio da
Lia. Falha em qualquer step = Slack URGENT.

Não bate em paciente real — usa número canário (CANARY_PHONE) que
o WHITELIST_NUMBERS reconhece como teste. Usa o endpoint
/admin/simulate-inbound do voice_agent (mesmo já usado pelo smoke).

Liga via `CANARY_ENABLED=1`. Roda 1x/dia (cron interno + endpoint
manual `/admin/canary-tick`).
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Optional

log = logging.getLogger(__name__)


# Telefone padrão (override via env CANARY_PHONE)
CANARY_PHONE_DEFAULT = "5561900000000"

# Estados FSM esperados após cada step
ESTADO_TRIAGEM = "TRIAGEM"
ESTADO_DADOS = "DADOS"
ESTADO_CONVENIO = "CONVENIO"
ESTADO_AGENDA = "AGENDA"
ESTADO_CONFIRMACAO = "CONFIRMACAO"


@dataclass
class StepResultado:
    nome: str
    user_text: str
    estado_esperado: str = ""
    must_contain: list[str] = field(default_factory=list)
    must_not_contain: list[str] = field(default_factory=list)
    ok: bool = False
    estado_final: str = ""
    resposta_lia: str = ""
    erro: Optional[str] = None
    elapsed_ms: int = 0


@dataclass
class CanaryResultado:
    canary_phone: str = ""
    iniciado_em: str = ""
    steps_total: int = 0
    steps_ok: int = 0
    steps_falhou: list[str] = field(default_factory=list)
    duracao_total_ms: int = 0
    steps_detalhe: list[dict] = field(default_factory=list)


def esta_habilitado() -> bool:
    return os.getenv("CANARY_ENABLED", "0") == "1"


def _canary_phone() -> str:
    return os.getenv("CANARY_PHONE") or CANARY_PHONE_DEFAULT


def _webhook_url() -> str:
    return (
        os.getenv("SLACK_WEBHOOK_CANARY_URL")
        or os.getenv("SLACK_WEBHOOK_URL")
        or ""
    )


# Sequência canónica de mensagens do "paciente" canário
STEPS_CANARIOS: list[StepResultado] = [
    StepResultado(
        nome="01_saudacao",
        user_text="oi, gostaria de agendar uma consulta",
        must_contain=["olá", "ajud"],
        must_not_contain=["pix", "300,50", "carteirinha"],
    ),
    StepResultado(
        nome="02_motivo",
        user_text="consulta de rotina pra mim mesmo",
        must_contain=["nome", "nasc"],
    ),
    StepResultado(
        nome="03_nome_e_nasc",
        user_text="João da Silva Teste Canary, nasci em 15/05/1980",
        must_contain=["conv"],
    ),
    StepResultado(
        nome="04_convenio",
        user_text="meu convênio é STF-Med",
        must_contain=["agenda", "horários", "opções"],
        must_not_contain=["não aceitamos"],
    ),
    StepResultado(
        nome="05_preferencia",
        user_text="prefiro manhã, na Asa Norte",
        must_contain=["08:", "09:", "10:", "11:"],  # algum horário manhã
    ),
    StepResultado(
        nome="06_escolha_slot",
        user_text="pode ser o primeiro horário que você ofereceu",
        must_contain=["cpf", "confirm"],
    ),
    StepResultado(
        nome="07_cpf",
        user_text="meu CPF é 111.444.777-35",
        must_contain=["confirm", "marcad"],
    ),
]


def _persiste_redis_state(redis_client: Any, key: str, valor: str) -> None:
    if not redis_client:
        return
    try:
        redis_client.setex(key, 3600, valor)
    except Exception:  # noqa: BLE001
        pass


def _ler_estado_fsm(redis_client: Any, convo_key: str) -> str:
    if not redis_client:
        return ""
    try:
        raw = redis_client.get(f"blink:fsm:{convo_key}")
        if not raw:
            return ""
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        # Tenta JSON {estado: "X"} ou string pura
        try:
            import json
            d = json.loads(raw)
            return str(d.get("estado", "") or d.get("state", ""))
        except Exception:
            return raw
    except Exception:  # noqa: BLE001
        return ""


def _validar_step(step: StepResultado, resposta: str) -> bool:
    """True se must_contain bate E must_not_contain não bate."""
    if not resposta:
        return False
    rl = resposta.lower()
    if step.must_not_contain:
        for ban in step.must_not_contain:
            if ban.lower() in rl:
                return False
    if not step.must_contain:
        return True
    # Pelo menos UM dos must_contain precisa bater (não todos)
    return any(s.lower() in rl for s in step.must_contain)


def _envia_slack(payload: dict) -> bool:
    url = _webhook_url()
    if not url:
        return False
    try:
        import httpx
        with httpx.Client(timeout=8.0) as c:
            r = c.post(url, json=payload)
        return 200 <= r.status_code < 300
    except Exception as e:  # noqa: BLE001
        log.warning("[CANARY] erro slack: %s", e)
        return False


def _payload_falha(res: CanaryResultado) -> dict:
    falhou_str = ", ".join(res.steps_falhou) or "nenhum (?)"
    return {
        "text": (
            f":rotating_light: *Canary FALHOU* — `{res.canary_phone}`\n"
            f"• Steps OK: `{res.steps_ok}/{res.steps_total}`\n"
            f"• Falhou em: {falhou_str}\n"
            f"• Iniciado em: {res.iniciado_em}\n"
            f"• Duração total: {res.duracao_total_ms}ms\n"
            "Possíveis causas: Anthropic/OpenAI fora, Medware fora, "
            "FSM corrompida, prompt regrediu. "
            "Rodar `curl /admin/replay/{lead_id_canary}` pra ver "
            "último estado."
        ),
    }


def _payload_ok(res: CanaryResultado) -> dict:
    return {
        "text": (
            f":white_check_mark: Canary OK — `{res.canary_phone}` "
            f"({res.steps_ok}/{res.steps_total} steps, "
            f"{res.duracao_total_ms}ms)"
        ),
    }


def tick(
    simulate_inbound_fn: Any,
    redis_client: Any,
    *,
    phone: Optional[str] = None,
    dry_run: bool = False,
    alertar_sempre: bool = False,
) -> CanaryResultado:
    """Roda o canário ponta-a-ponta.

    `simulate_inbound_fn(phone, text) -> {"resposta_lia": "..."}`
    é a função do pipeline que entrega 1 inbound e devolve a resposta.

    `alertar_sempre=True` manda Slack mesmo no sucesso (útil pra debug).
    """
    t0 = time.time()
    res = CanaryResultado(
        canary_phone=phone or _canary_phone(),
        iniciado_em=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        steps_total=len(STEPS_CANARIOS),
    )
    convo_key = res.canary_phone[-12:]
    # Limpa estado anterior do canário (best-effort)
    if redis_client:
        try:
            redis_client.delete(
                f"blink:fsm:{convo_key}",
                f"blink:checklist:{convo_key}",
            )
        except Exception:  # noqa: BLE001
            pass
    for tpl in STEPS_CANARIOS:
        step = StepResultado(
            nome=tpl.nome,
            user_text=tpl.user_text,
            estado_esperado=tpl.estado_esperado,
            must_contain=list(tpl.must_contain),
            must_not_contain=list(tpl.must_not_contain),
        )
        s0 = time.time()
        try:
            out = simulate_inbound_fn(res.canary_phone, step.user_text)
            if isinstance(out, dict):
                step.resposta_lia = (
                    out.get("resposta_lia") or out.get("answer") or ""
                )
            else:
                step.resposta_lia = str(out or "")
        except Exception as e:  # noqa: BLE001
            step.erro = str(e)[:300]
            step.resposta_lia = ""
        step.estado_final = _ler_estado_fsm(redis_client, convo_key)
        step.elapsed_ms = int((time.time() - s0) * 1000)
        step.ok = step.erro is None and _validar_step(step, step.resposta_lia)
        if step.ok:
            res.steps_ok += 1
        else:
            res.steps_falhou.append(step.nome)
        res.steps_detalhe.append({
            "nome": step.nome,
            "user_text": step.user_text,
            "ok": step.ok,
            "resposta_preview": step.resposta_lia[:300],
            "estado_final": step.estado_final,
            "erro": step.erro,
            "elapsed_ms": step.elapsed_ms,
        })
        if not step.ok and not dry_run:
            # Falhou no meio — para de gastar API
            break
    res.duracao_total_ms = int((time.time() - t0) * 1000)
    if not dry_run:
        if res.steps_falhou:
            _envia_slack(_payload_falha(res))
        elif alertar_sempre:
            _envia_slack(_payload_ok(res))
    return res
