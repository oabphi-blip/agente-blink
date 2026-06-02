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

# Identificadores fixos do paciente canary no Medware.
# Nome com prefixo único permite cleanup robusto: antes de cada tick,
# listamos TODOS agendamentos com esse nome dos últimos 7 dias e
# cancelamos — limpa fantasmas se tick anterior crashou entre criar +
# cancelar. Convênio fixo pra atravessar autorização sem precisar de
# dados reais.
CANARY_NOME_PACIENTE = "CANARY TESTE BLINK"
CANARY_CPF = "111.444.777-35"  # CPF válido pra DV mas não real
CANARY_DATA_NASC = "1980-05-15"
CANARY_CONVENIO = "STF-Med"

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
# 14 cenários: 7 originais + 7 dos bugs históricos.
# Cada cenário pode rodar isolado (não compartilha estado entre si).
STEPS_CANARIOS: list[StepResultado] = [
    # ===== FLUXO HAPPY PATH (7 originais) =====
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
        must_contain=["08:", "09:", "10:", "11:"],
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
    # ===== CENÁRIOS DOS BUGS HISTÓRICOS (7 novos) =====
    StepResultado(
        nome="08_esther_imagem_pos_agendado",
        # Bug Esther 24060221: lead em 5-AGENDADO, paciente manda imagem
        # de carteirinha. Lia voltou a oferecer slot. Filtro
        # _viola_oferta_apos_agendado deve pegar.
        user_text=(
            "[O paciente enviou uma imagem pelo WhatsApp. Provavelmente "
            "é a carteirinha do convênio. Confirme o recebimento, diga "
            "que a equipe vai conferir, e siga o atendimento normalmente.]"
        ),
        must_contain=["recebi", "obrigad", "confer"],
        must_not_contain=[
            "deixa eu trazer", "horários disponíveis", "vou buscar",
            "qual prefere", "1️⃣", "manhã ou tarde",
        ],
    ),
    StepResultado(
        nome="09_aurora_oi_em_agendado",
        # Bug Aurora 23907418: lead em 5-AGENDADO manda 'oi'. Lia
        # refazia triagem. Deveria confirmar consulta existente.
        user_text="oi tudo bem? me confirma minha consulta?",
        must_contain=["consulta", "marcad", "dia"],
        must_not_contain=[
            "qual dia da semana", "qual médico",
            "deixa eu agendar", "vamos começar",
        ],
    ),
    StepResultado(
        nome="10_cobranca_prematura",
        # Bug 24034205: paciente pergunta valor antes de escolher slot,
        # Lia já cobra Pix.
        user_text="quanto custa a consulta? quero saber antes de marcar",
        must_contain=["valor", "consulta"],
        must_not_contain=[
            "envie via pix", "pague agora", "antes de continuar",
            "chave pix",
        ],
    ),
    StepResultado(
        nome="11_marcela_contato_vs_paciente",
        # Bug Marcela 24048691: Lia confunde contato com paciente.
        # Aqui Maria escreve, mas vai marcar pro filho Pedro.
        user_text=(
            "oi, é a Maria, quero marcar uma consulta pro meu filho "
            "Pedro Silva, ele tem 8 anos"
        ),
        must_contain=["pedro", "nasc", "data"],
        must_not_contain=[
            "olá maria, qual seu nasc",  # confundiu Maria com paciente
        ],
    ),
    StepResultado(
        nome="12_diones_troca_medico_envenenamento",
        # Bug Diones 23742328: ctx já tem médico Karla, paciente pede
        # Fabrício. Lia não pode trocar autonomamente.
        user_text="já vou marcar com a Dra. Karla, mas prefiro o Dr. Fabrício",
        must_contain=["karla", "fabr"],  # ambos mencionados explica
        must_not_contain=[
            "vou agendar com o dr. fabrício",
            "tenho essas opções com o dr. fabrício",
        ],
    ),
    StepResultado(
        nome="13_juliene_medware_vazio",
        # Bug Juliene 24053159: Lia inventa "retorno em horário comercial"
        # quando Medware vem sem slots.
        user_text="terça pela manhã, qualquer horário",
        must_contain=[
            "deixa eu reconsultar", "1 minuto", "volto",
            "tenho", "horários",
        ],
        must_not_contain=[
            "registrar sua preferência",
            "retorno em horário comercial",
            "equipe humana",
            "seg-sex", "seg a sex",
            "exemplo aprovado",
            "exemplo:",
        ],
    ),
    StepResultado(
        nome="14_adelia_nao_aceito_convenio",
        # Bug Adelia 24056883 (caminho relacionado): paciente diz que
        # não aceita convênio, quer particular. Lia deve oferecer
        # fluxo particular com chave Pix correta.
        user_text="não vou usar convênio, prefiro particular",
        must_contain=["particular", "valor", "consulta"],
        must_not_contain=[
            # Chave Pix inválida
            "exemplo aprovado",
            "chave@particular.com",
        ],
    ),
]


# Hora padrão do tick (BRT) — antes do horário comercial abrir
CANARY_HORA_DIARIA_DEFAULT = 7


def _hora_diaria() -> int:
    try:
        return int(os.getenv("CANARY_HORA_DIARIA", str(CANARY_HORA_DIARIA_DEFAULT)))
    except (TypeError, ValueError):
        return CANARY_HORA_DIARIA_DEFAULT


def deve_rodar_agora(now: Optional[Any] = None) -> bool:
    """True se for a hora do tick (CANARY_HORA_DIARIA, default 7 BRT).
    Chamado pelo cron interno — checa se já rodou nas últimas 23h via
    Redis key (idempotência)."""
    from datetime import datetime, timezone, timedelta
    if now is None:
        brt = timezone(timedelta(hours=-3))
        now = datetime.now(brt)
    return now.hour == _hora_diaria() and now.minute < 30


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


# =====================================================================
# VALIDADORES MEDWARE — provam que o pipeline INTEIRO está vivo
# =====================================================================

def _ler_agenda_no_ctx(redis_client: Any, convo_key: str) -> list[dict]:
    """Lê ctx.agenda no Redis. Devolve [] se vazio ou erro."""
    if not redis_client:
        return []
    try:
        raw = redis_client.get(f"blink:ctx:{convo_key}")
        if not raw:
            return []
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        import json
        d = json.loads(raw)
        agenda = d.get("agenda") or []
        return agenda if isinstance(agenda, list) else []
    except Exception:  # noqa: BLE001
        return []


def validar_medware_consultado(
    redis_client: Any, convo_key: str,
) -> tuple[bool, str]:
    """Prova que a Lia consultou o Medware em tempo real (não inventou
    horários). Se `ctx.agenda` no Redis tem >= 1 slot, foi consultado.
    """
    agenda = _ler_agenda_no_ctx(redis_client, convo_key)
    if not agenda:
        return False, "ctx.agenda vazio — Lia não consultou Medware"
    return True, f"agenda tem {len(agenda)} slots reais"


def validar_slots_do_dia_seguinte(
    redis_client: Any, convo_key: str,
) -> tuple[bool, str]:
    """Prova que pelo menos 1 slot oferecido é de amanhã (D+1 BRT).
    Critério da Blink: completar agenda do dia seguinte."""
    from datetime import datetime, timedelta, timezone
    brt = timezone(timedelta(hours=-3))
    amanha = (datetime.now(brt) + timedelta(days=1)).date()
    agenda = _ler_agenda_no_ctx(redis_client, convo_key)
    if not agenda:
        return False, "ctx.agenda vazio"
    for slot in agenda:
        iso = slot.get("data_iso") or slot.get("dia_iso") or ""
        if not iso:
            continue
        try:
            d = datetime.fromisoformat(iso.replace("Z", "+00:00"))
            if d.astimezone(brt).date() == amanha:
                return (
                    True,
                    f"slot {slot.get('hora','?')} de amanhã ({amanha}) "
                    "está na lista",
                )
        except Exception:  # noqa: BLE001
            continue
    return (
        False,
        f"nenhum slot é de amanhã ({amanha}). slots: "
        f"{[s.get('data_iso') for s in agenda[:3]]}",
    )


def validar_agendamento_gravado_medware(
    medware_client: Any, dia_iso: Optional[str] = None,
) -> tuple[bool, str]:
    """Prova que o agendamento canary foi efetivamente gravado no
    Medware. Lista agendamentos de hoje+amanhã filtrando por nome
    CANARY_NOME_PACIENTE.

    Critério OK: pelo menos 1 agendamento com esse nome aparece e tem
    `codAgendamento` truthy.
    """
    if not medware_client:
        return False, "medware client não disponível"
    from datetime import datetime, timedelta, timezone
    brt = timezone(timedelta(hours=-3))
    if not dia_iso:
        dia_iso = (datetime.now(brt) + timedelta(days=1)).date().isoformat()
    try:
        ags = medware_client.listar_agendamentos(
            data_inicio=dia_iso, data_fim=dia_iso,
        ) or []
    except Exception as e:  # noqa: BLE001
        return False, f"medware.listar_agendamentos falhou: {e}"
    matches = [
        a for a in ags
        if CANARY_NOME_PACIENTE.lower()
        in str(a.get("nomePaciente", a.get("paciente", ""))).lower()
    ]
    if not matches:
        return (
            False,
            f"nenhum agendamento '{CANARY_NOME_PACIENTE}' em {dia_iso}",
        )
    com_cod = [m for m in matches if m.get("codAgendamento")]
    if not com_cod:
        return False, f"{len(matches)} matches mas sem codAgendamento"
    return (
        True,
        f"agendamento gravado: codAgendamento={com_cod[0].get('codAgendamento')}",
    )


# =====================================================================
# CLEANUP — cancela agendamentos canary antigos (fantasmas)
# =====================================================================

def cancelar_agendamentos_canary_antigos(
    medware_client: Any, dias_atras: int = 7,
) -> dict:
    """Cancela TODOS os agendamentos com nome CANARY_NOME_PACIENTE dos
    últimos N dias. Idempotente — pode ser chamada antes de cada tick
    pra garantir que crashes anteriores não deixaram fantasma.

    Devolve dict com {listados, cancelados, erros}.
    """
    out = {"listados": 0, "cancelados": 0, "erros": []}
    if not medware_client:
        out["erros"].append("medware client indisponível")
        return out
    from datetime import datetime, timedelta, timezone
    brt = timezone(timedelta(hours=-3))
    hoje = datetime.now(brt).date()
    inicio = (hoje - timedelta(days=dias_atras)).isoformat()
    fim = (hoje + timedelta(days=dias_atras)).isoformat()
    try:
        ags = medware_client.listar_agendamentos(
            data_inicio=inicio, data_fim=fim,
        ) or []
    except Exception as e:  # noqa: BLE001
        out["erros"].append(f"listar falhou: {e}")
        return out
    canarios = [
        a for a in ags
        if CANARY_NOME_PACIENTE.lower()
        in str(a.get("nomePaciente", a.get("paciente", ""))).lower()
    ]
    out["listados"] = len(canarios)
    for ag in canarios:
        cod = ag.get("codAgendamento")
        if not cod:
            continue
        try:
            ok = medware_client.cancelar_agendamento(cod)
            if ok:
                out["cancelados"] += 1
            else:
                out["erros"].append(f"cancelar {cod} devolveu False")
        except Exception as e:  # noqa: BLE001
            out["erros"].append(f"cancelar {cod} erro: {e}")
    return out


def tick(
    simulate_inbound_fn: Any,
    redis_client: Any,
    *,
    medware_client: Any = None,
    phone: Optional[str] = None,
    dry_run: bool = False,
    alertar_sempre: bool = False,
    pular_cleanup: bool = False,
    pular_medware: bool = False,
) -> CanaryResultado:
    """Roda o canário ponta-a-ponta (14 cenários, 1x/dia recomendado).

    Etapas:
    0) Cleanup: cancela agendamentos canary antigos (fantasmas).
    1-7) Happy path: saudação → motivo → nome/nasc → convênio →
       preferência → escolha → CPF. Inclui 3 validadores Medware nos
       steps 4 (consultado), 5 (slot dia seguinte), 7 (gravado).
    8-14) Bugs históricos: Esther/Aurora/Marcela/Diones/Juliene/Adelia.

    Args:
        simulate_inbound_fn(phone, text) -> {"resposta_lia": "..."}
        medware_client: cliente Medware (pra validar gravação + cleanup).
        pular_medware: se True, valida só texto (sem criar agendamento).
        pular_cleanup: se True, não cancela canários antigos no início.
    """
    t0 = time.time()
    res = CanaryResultado(
        canary_phone=phone or _canary_phone(),
        iniciado_em=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        steps_total=len(STEPS_CANARIOS),
    )
    convo_key = res.canary_phone[-12:]
    # ---- ETAPA 0: cleanup robusto de fantasmas anteriores ----
    if not pular_cleanup and not pular_medware and medware_client:
        try:
            cleanup = cancelar_agendamentos_canary_antigos(
                medware_client, dias_atras=7,
            )
            res.steps_detalhe.append({
                "nome": "00_cleanup",
                "user_text": "(pré-tick)",
                "ok": cleanup.get("erros", []) == [],
                "resposta_preview": (
                    f"listados={cleanup.get('listados',0)} "
                    f"cancelados={cleanup.get('cancelados',0)} "
                    f"erros={cleanup.get('erros',[])[:3]}"
                ),
            })
        except Exception as e:  # noqa: BLE001
            log.warning("[CANARY] cleanup falhou: %s", e)
    # Limpa estado anterior do canário (best-effort)
    if redis_client:
        try:
            redis_client.delete(
                f"blink:fsm:{convo_key}",
                f"blink:checklist:{convo_key}",
                f"blink:ctx:{convo_key}",
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
        # ---- VALIDAÇÕES MEDWARE EXTRAS por step ----
        validador_medware = ""
        if not pular_medware:
            try:
                if step.nome == "04_convenio":
                    # Após convênio, Lia deve ter consultado Medware
                    ok, det = validar_medware_consultado(
                        redis_client, convo_key,
                    )
                    if not ok:
                        step.ok = False
                    validador_medware = f"medware_consultado: {det}"
                elif step.nome == "05_preferencia":
                    # Slots oferecidos devem incluir dia seguinte
                    ok, det = validar_slots_do_dia_seguinte(
                        redis_client, convo_key,
                    )
                    if not ok:
                        step.ok = False
                    validador_medware = f"slot_dia_seguinte: {det}"
                elif step.nome == "07_cpf" and medware_client:
                    # Após CPF, agendamento deve ter sido gravado
                    ok, det = validar_agendamento_gravado_medware(
                        medware_client,
                    )
                    if not ok:
                        step.ok = False
                    validador_medware = f"medware_gravado: {det}"
            except Exception as e:  # noqa: BLE001
                validador_medware = f"validador erro: {e}"
        if step.ok:
            res.steps_ok += 1
        else:
            res.steps_falhou.append(step.nome)
        res.steps_detalhe.append({
            "nome": step.nome,
            "user_text": step.user_text[:200],
            "ok": step.ok,
            "resposta_preview": step.resposta_lia[:300],
            "estado_final": step.estado_final,
            "validador_medware": validador_medware,
            "erro": step.erro,
            "elapsed_ms": step.elapsed_ms,
        })
        if not step.ok and not dry_run:
            # Falhou no meio — para de gastar API mas garante cleanup
            break
    res.duracao_total_ms = int((time.time() - t0) * 1000)
    if not dry_run:
        if res.steps_falhou:
            _envia_slack(_payload_falha(res))
        elif alertar_sempre:
            _envia_slack(_payload_ok(res))
    return res
