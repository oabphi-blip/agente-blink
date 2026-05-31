"""Dispatcher de renovação de janela 24h — orquestra elegibilidade + estratégia + envio.

Fluxo:
  1. Recebe snapshot do lead (status_id, telefone, nome_contato, ultima_msg_ts).
  2. Chama elegivel_renovar_janela() — verifica status + interação + tempo.
  3. Chama decidir_estrategia() — decide free_form vs template_1039 vs skip.
  4. Despacha:
     - free_form    → wa_cloud.send_text(to, render_mensagem_renovar_janela(nome))
     - template_1039 → wa_cloud.send_template(to, name, body_params=[nome])
     - nao_disparar → log + skip
  5. Grava dedup Redis (`blink:janela:ultima_renovacao:<lead>`, TTL 24h).
  6. Devolve resultado estruturado (pra log/telemetria).

Princípio: NUNCA dispara duas vezes na mesma janela 24h.

Todos os colaboradores externos (wa_client, redis, agora) são injetáveis
pra facilitar pytest sem subir infra.
"""
from __future__ import annotations

import logging
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone

# Fuso de Brasília (UTC-3, sem DST desde 2019).
_TZ_BRT = timezone(timedelta(hours=-3))

from voice_agent.mensagens_janela import (
    elegivel_renovar_janela,
    render_mensagem_renovar_janela,
)
from voice_agent.templates_meta import (
    TEMPLATE_1039,
    build_template_ativar_urgencia,
    decidir_estrategia,
    normalizar_telefone_e164,
)

log = logging.getLogger(__name__)

# Anti-spam: chave Redis com TTL.
REDIS_KEY_FMT = "blink:janela:ultima_renovacao:{lead_id}"
REDIS_TTL_SEG = 22 * 60 * 60   # 22h — alinhado com LIMIAR_DISPARO


@dataclass
class SnapshotLead:
    """Tudo o que o dispatcher precisa por lead."""
    lead_id: int
    telefone_e164: str
    nome_contato: str
    status_id: int | None
    ultima_msg_paciente_ts: int | float | None
    paciente_ja_respondeu_na_vida: bool


@dataclass
class ResultadoDispatch:
    lead_id: int
    elegibilidade: dict
    estrategia: str
    motivo: str | None
    enviado: bool
    skipped: bool
    razao_skip: str | None = None
    template_name: str | None = None
    payload_preview: dict | None = None
    erro: str | None = None
    dedup_chave: str | None = None
    dedup_ja_existia: bool = False
    kommo_nota: dict | None = None   # {ok, skipped, reason}
    nota_preview: str | None = None  # texto da nota (mesmo em dry_run)

    def to_dict(self) -> dict:
        return asdict(self)


def _ja_disparou_nesta_janela(redis_client, lead_id: int) -> bool:
    if redis_client is None:
        return False
    try:
        return bool(redis_client.get(REDIS_KEY_FMT.format(lead_id=lead_id)))
    except Exception as exc:  # noqa: BLE001
        log.warning("[DISPATCHER] Falha Redis GET dedup: %s", exc)
        return False


def formatar_nota_kommo(
    *,
    estrategia: str,
    nome_contato: str,
    telefone_e164: str,
    texto_ou_template: str,
    quando: datetime | None = None,
    canal: str = "WhatsApp 8133",
) -> str:
    """Monta a nota Kommo que o atendente humano lê no card do lead.

    Padrão:
      [Lia · Motor de Renovação 24h] · DD/MM/AAAA HH:MM BRT · WhatsApp 8133
      Estratégia: <texto-livre | template 1039 ativar grau de urgência>
      Para: <nome do contato> · <telefone E.164>

      <texto enviado | nome do template>
    """
    quando = quando or datetime.now(_TZ_BRT)
    when = quando.astimezone(_TZ_BRT).strftime("%d/%m/%Y %H:%M")
    if estrategia == "free_form":
        rotulo = "texto livre"
    elif estrategia == "template_1039":
        rotulo = "template 1039 ativar grau de urgência"
    else:
        rotulo = estrategia or "?"
    return (
        f"[Lia · Motor de Renovação 24h] · {when} BRT · {canal}\n"
        f"Estratégia: {rotulo}\n"
        f"Para: {nome_contato} · {telefone_e164}\n\n"
        f"{texto_ou_template}"
    )


def _gravar_nota_kommo(
    kommo_writer,
    lead_id: int,
    nota: str,
) -> dict:
    """Tenta gravar a nota; nunca levanta — devolve status no dict.

    kommo_writer pode ser:
      - função: kommo_writer(lead_id, nota)
      - objeto com .add_note(lead_id, text)
      - None → modo dry / sem cliente
    """
    if kommo_writer is None:
        return {"ok": False, "skipped": True, "reason": "sem_kommo_writer"}
    try:
        if callable(kommo_writer):
            kommo_writer(lead_id, nota)
        elif hasattr(kommo_writer, "add_note"):
            kommo_writer.add_note(lead_id, nota)
        else:
            return {"ok": False, "skipped": True, "reason": "writer_invalido"}
        return {"ok": True, "skipped": False, "reason": None}
    except Exception as exc:  # noqa: BLE001
        log.warning("[DISPATCHER] Falha gravar nota Kommo lead=%s: %s",
                    lead_id, exc)
        return {"ok": False, "skipped": False, "reason": str(exc)[:200]}


def _marcar_disparo(redis_client, lead_id: int) -> str | None:
    chave = REDIS_KEY_FMT.format(lead_id=lead_id)
    if redis_client is None:
        return chave  # devolve a chave que SERIA usada
    try:
        redis_client.set(chave, int(time.time()), ex=REDIS_TTL_SEG)
        return chave
    except Exception as exc:  # noqa: BLE001
        log.warning("[DISPATCHER] Falha Redis SET dedup: %s", exc)
        return chave


def dispatch_renovacao(
    snap: SnapshotLead,
    *,
    wa_client=None,          # WhatsAppCloudClient com send_text + send_template
    redis_client=None,       # Redis para dedup
    kommo_note_writer=None,  # função (lead_id, nota) OU obj com .add_note(...)
    agora: float | None = None,
    dry_run: bool = False,
    forcar_redispatch: bool = False,
) -> ResultadoDispatch:
    """Decide + dispara (ou dry-run) a renovação de janela.

    Retorna ResultadoDispatch sempre — nunca levanta. Erros vão em `.erro`.
    """
    elig = elegivel_renovar_janela(
        status_id=snap.status_id,
        ultima_msg_paciente_ts=snap.ultima_msg_paciente_ts,
        agora=agora if agora is not None else time.time(),
    )
    estr = decidir_estrategia(
        elig, paciente_ja_respondeu_na_vida=snap.paciente_ja_respondeu_na_vida,
    )

    res = ResultadoDispatch(
        lead_id=snap.lead_id,
        elegibilidade=elig,
        estrategia=estr.tipo,
        motivo=estr.motivo,
        enviado=False,
        skipped=False,
    )

    if estr.tipo == "nao_disparar":
        res.skipped = True
        res.razao_skip = estr.motivo
        return res

    # Dedup: já disparou nesta janela?
    if not forcar_redispatch and _ja_disparou_nesta_janela(redis_client, snap.lead_id):
        res.skipped = True
        res.razao_skip = "ja_disparado_nesta_janela"
        res.dedup_ja_existia = True
        return res

    # Valida telefone antes de tentar enviar.
    to_e164 = normalizar_telefone_e164(snap.telefone_e164)
    if not to_e164:
        res.skipped = True
        res.razao_skip = "telefone_invalido"
        return res

    # Monta payload conforme a estratégia.
    if estr.tipo == "template_1039":
        payload = build_template_ativar_urgencia(
            to_telefone=to_e164, nome_contato=snap.nome_contato,
        )
        if payload is None:
            res.skipped = True
            res.razao_skip = "payload_template_nulo"
            return res
        res.payload_preview = payload
        res.template_name = TEMPLATE_1039.template_name

        # Monta a nota Kommo (mesmo em dry_run → preview no JSON)
        descritor = (
            f"Template enviado: \"{TEMPLATE_1039.template_name}\" (pt_BR)\n"
            f"Parâmetro {{1}} = \"{snap.nome_contato}\"\n"
            f"Botões: 1ª Opção · 2ª Opção · 3ª Opção"
        )
        res.nota_preview = formatar_nota_kommo(
            estrategia="template_1039",
            nome_contato=snap.nome_contato,
            telefone_e164=to_e164,
            texto_ou_template=descritor,
        )

        if dry_run or wa_client is None:
            res.skipped = True
            res.razao_skip = "dry_run" if dry_run else "wa_client_ausente"
            return res
        try:
            wa_client.send_template(
                to=to_e164,
                name=TEMPLATE_1039.template_name,
                body_params=[snap.nome_contato],
            )
            res.enviado = True
            res.dedup_chave = _marcar_disparo(redis_client, snap.lead_id)
            res.kommo_nota = _gravar_nota_kommo(
                kommo_note_writer, snap.lead_id, res.nota_preview,
            )
            # Marca "aguardando resposta" pra o cron classificar-tick.
            try:
                from voice_agent.classificar import marcar_aguardando_resposta
                marcar_aguardando_resposta(
                    redis_client, snap.lead_id,
                    disparo_ts=time.time(),
                )
            except Exception as exc:  # noqa: BLE001
                log.warning("[DISPATCHER] marcar_aguardando_resposta: %s", exc)
        except Exception as exc:  # noqa: BLE001
            res.erro = str(exc)[:300]
        return res

    if estr.tipo == "free_form":
        texto = render_mensagem_renovar_janela(snap.nome_contato)
        res.payload_preview = {"to": to_e164, "text": texto}
        res.nota_preview = formatar_nota_kommo(
            estrategia="free_form",
            nome_contato=snap.nome_contato,
            telefone_e164=to_e164,
            texto_ou_template=texto,
        )

        if dry_run or wa_client is None:
            res.skipped = True
            res.razao_skip = "dry_run" if dry_run else "wa_client_ausente"
            return res
        try:
            wa_client.send_text(to=to_e164, text=texto)
            res.enviado = True
            res.dedup_chave = _marcar_disparo(redis_client, snap.lead_id)
            res.kommo_nota = _gravar_nota_kommo(
                kommo_note_writer, snap.lead_id, res.nota_preview,
            )
            try:
                from voice_agent.classificar import marcar_aguardando_resposta
                marcar_aguardando_resposta(
                    redis_client, snap.lead_id,
                    disparo_ts=time.time(),
                )
            except Exception as exc:  # noqa: BLE001
                log.warning("[DISPATCHER] marcar_aguardando_resposta: %s", exc)
        except Exception as exc:  # noqa: BLE001
            res.erro = str(exc)[:300]
        return res

    # Fallback defensivo — estratégia desconhecida.
    res.skipped = True
    res.razao_skip = f"estrategia_desconhecida:{estr.tipo}"
    return res
