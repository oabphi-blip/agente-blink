"""Webhook Slack → endpoint de assinatura de auditoria.

Origem: task #82 (sessão 31/05/2026). Os endpoints
`/admin/auditoria-confirma` já existem e gravam status+assinatura no
Kommo. Falta a ponte entre `reaction_added :white_check_mark:` no
canal #auditoria-autorização e essa chamada.

FLUXO
1. Slack envia POST → `/admin/slack-event` (Events API subscription).
2. Filtramos só evento `reaction_added` no canal de auditoria, com
   reaction `white_check_mark`.
3. Buscamos a mensagem original (via Slack `conversations.history`) e
   extraímos `lead_id` + `paciente_idx` do texto (regex no formato
   produzido por `auditoria.montar_mensagem_slack`).
4. Mapeamos `user_id` Slack → (papel, autor) via env
   `SLACK_AUDIT_MAPPING_JSON`. Quem não está no mapeamento é ignorado.
5. Chamamos `confirmar_assinatura()` e gravamos no Kommo.

CONFIG (env vars)
  SLACK_AUDIT_MAPPING_JSON='{"U01ABC...": "sec:asa-norte:Maria Santos",
                             "U02DEF...": "med:karla:Dra Karla"}'
  SLACK_AUDITORIA_REACTION (default "white_check_mark")
  SLACK_VERIFICATION_TOKEN (opcional — valida assinatura HMAC do Slack)

NOTA: a verificação de assinatura HMAC SHA-256 do Slack pode ser
adicionada depois — por enquanto usamos `SLACK_VERIFICATION_TOKEN`
no body (legacy Verification Token). Funciona pra dev/sandbox.
"""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from typing import Callable, Optional

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Regex pra extrair lead_id + paciente_idx do texto da mensagem original
# ---------------------------------------------------------------------------

# Casa "Lead: 24053159 · Paciente 1: Daniel Silva"
# E também "Lead 24053159 paciente 1" (tolerante a formatos)
_LEAD_PACIENTE_REGEX = re.compile(
    r"lead[\s:]+(\d+).{0,80}paciente[\s:]*(\d+)",
    re.IGNORECASE | re.DOTALL,
)


def extrair_lead_paciente(texto: str) -> Optional[tuple[int, int]]:
    """Devolve (lead_id, paciente_idx) ou None se não casar."""
    if not texto:
        return None
    m = _LEAD_PACIENTE_REGEX.search(texto)
    if not m:
        return None
    try:
        return int(m.group(1)), int(m.group(2))
    except (ValueError, IndexError):
        return None


# ---------------------------------------------------------------------------
# Mapeamento user_id Slack → (papel, slug, nome)
# Format: "sec:asa-norte:Maria" ou "med:karla:Dra Karla Delalíbera"
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Assinante:
    """Quem assinou + qual papel ele cumpre."""
    papel: str             # 'sec' | 'med'
    slug: str              # 'asa-norte'|'aguas-claras' (sec) ou nome médico (med)
    nome: str              # nome humano pra gravar na assinatura

    @property
    def papel_completo(self) -> str:
        """Devolve papel no formato esperado por confirmar_assinatura."""
        if self.papel == "sec":
            return f"secretaria_{self.slug.replace('-', '_')}"
        return f"medico_{self.slug}"


def carregar_mapping_env(env_var: str = "SLACK_AUDIT_MAPPING_JSON") -> dict[str, Assinante]:
    """Lê o mapping do env e converte em {user_id: Assinante}.

    Format do JSON:
      {"U01ABC...": "sec:asa-norte:Maria Santos",
       "U02DEF...": "med:karla:Dra Karla Delalíbera"}

    Erros silenciosos — mapping vazio se JSON inválido.
    """
    raw = os.environ.get(env_var) or ""
    if not raw:
        return {}
    try:
        bruto = json.loads(raw)
    except json.JSONDecodeError as e:
        log.warning("[SLACK MAPPING] JSON inválido em %s: %s", env_var, e)
        return {}
    if not isinstance(bruto, dict):
        return {}
    out: dict[str, Assinante] = {}
    for user_id, valor in bruto.items():
        if not isinstance(valor, str):
            continue
        partes = valor.split(":", 2)
        if len(partes) != 3:
            log.warning(
                "[SLACK MAPPING] valor mal formado pra %s: %r", user_id, valor,
            )
            continue
        papel, slug, nome = partes
        if papel not in ("sec", "med"):
            log.warning(
                "[SLACK MAPPING] papel inválido pra %s: %r", user_id, papel,
            )
            continue
        out[str(user_id)] = Assinante(
            papel=papel, slug=slug.strip(), nome=nome.strip(),
        )
    return out


# ---------------------------------------------------------------------------
# Parser de evento — recebe payload bruto do Slack
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class EventoReaction:
    """Resultado parseado de um reaction_added que merece ação."""
    user_id: str
    channel_id: str
    msg_ts: str
    reaction: str


def parsear_reaction_event(payload: dict) -> Optional[EventoReaction]:
    """Recebe o payload do Slack Events API e retorna o evento se for
    `reaction_added` válido. Senão None.

    O payload do Slack tem estrutura:
      {
        "type": "event_callback",
        "event": {
          "type": "reaction_added",
          "user": "U01ABC...",
          "reaction": "white_check_mark",
          "item": {"type": "message", "channel": "C...", "ts": "..."},
        }
      }
    """
    if not isinstance(payload, dict):
        return None
    if payload.get("type") != "event_callback":
        return None
    evento = payload.get("event") or {}
    if evento.get("type") != "reaction_added":
        return None
    item = evento.get("item") or {}
    if item.get("type") != "message":
        return None
    user = evento.get("user") or ""
    channel = item.get("channel") or ""
    ts = item.get("ts") or ""
    reaction = evento.get("reaction") or ""
    if not (user and channel and ts and reaction):
        return None
    return EventoReaction(
        user_id=user, channel_id=channel, msg_ts=ts, reaction=reaction,
    )


# ---------------------------------------------------------------------------
# Wrapper de processamento — junta parser + mapping + busca mensagem
# ---------------------------------------------------------------------------

@dataclass
class ResultadoProcessamento:
    """Resultado de processar 1 evento. `acao` indica o que fazer:
      - 'assinar' → caller chama confirmar_assinatura com os campos
      - 'ignorar' → não é evento que nos interessa (motivo em `motivo`)
      - 'erro' → algo deu errado (motivo em `motivo`)
    """
    acao: str  # 'assinar' | 'ignorar' | 'erro'
    motivo: str = ""
    lead_id: Optional[int] = None
    paciente_idx: Optional[int] = None
    papel: Optional[str] = None
    autor: Optional[str] = None
    reaction_user_id: Optional[str] = None


def processar_evento_slack(
    payload: dict,
    *,
    mapping: dict[str, Assinante],
    reaction_esperada: str = "white_check_mark",
    canal_esperado: Optional[str] = None,
    buscar_mensagem: Optional[Callable[[str, str], Optional[str]]] = None,
) -> ResultadoProcessamento:
    """Pipeline completo de 1 evento.

    Args:
      payload: dict bruto do Slack
      mapping: {user_id: Assinante}
      reaction_esperada: emoji que dispara assinatura (default check)
      canal_esperado: filtrar só esse canal (ignora outros). None = aceita todos
      buscar_mensagem: callable que recebe (channel_id, msg_ts) e devolve o
        texto da mensagem original. Devolva None se não conseguir buscar.
        Caller passa um wrapper de conversations.history aqui.
    """
    evento = parsear_reaction_event(payload)
    if not evento:
        return ResultadoProcessamento(
            acao="ignorar",
            motivo="payload não é reaction_added válido",
        )
    if evento.reaction != reaction_esperada:
        return ResultadoProcessamento(
            acao="ignorar",
            motivo=f"reaction {evento.reaction!r} ≠ esperada",
            reaction_user_id=evento.user_id,
        )
    if canal_esperado and evento.channel_id != canal_esperado:
        return ResultadoProcessamento(
            acao="ignorar",
            motivo=f"canal {evento.channel_id} fora do esperado",
            reaction_user_id=evento.user_id,
        )
    assinante = mapping.get(evento.user_id)
    if not assinante:
        return ResultadoProcessamento(
            acao="ignorar",
            motivo=f"user {evento.user_id} fora do mapping",
            reaction_user_id=evento.user_id,
        )
    if buscar_mensagem is None:
        return ResultadoProcessamento(
            acao="erro",
            motivo="buscar_mensagem não fornecido",
            reaction_user_id=evento.user_id,
        )
    texto = buscar_mensagem(evento.channel_id, evento.msg_ts)
    if not texto:
        return ResultadoProcessamento(
            acao="erro",
            motivo="mensagem original não encontrada ou vazia",
            reaction_user_id=evento.user_id,
        )
    extracao = extrair_lead_paciente(texto)
    if not extracao:
        return ResultadoProcessamento(
            acao="erro",
            motivo="lead_id/paciente_idx não extraídos do texto",
            reaction_user_id=evento.user_id,
        )
    lead_id, paciente_idx = extracao
    return ResultadoProcessamento(
        acao="assinar",
        motivo="ok",
        lead_id=lead_id,
        paciente_idx=paciente_idx,
        papel=assinante.papel_completo,
        autor=assinante.nome,
        reaction_user_id=evento.user_id,
    )
