"""Auditoria pós-consulta — dupla checagem secretaria + médico.

Implementa a seção 25 do `_MASTER_INSTRUCTION.md`. Quando um lead é movido
para `6-REALIZADO CONSULTA`, compara o agrupador planejado (N.EXAMES) com
os procedimentos realmente executados no Medware. Se houver discrepância,
posta no canal `#auditoria-autorização` do Slack e abre fila de dupla
assinatura (secretaria da unidade + médico responsável).

Status: ESQUELETO — task #82.

Implementar nesta ordem:
1. `comparar_agrupamento()` — função pura, fácil de testar.
2. `montar_mensagem_slack()` — formata o bloco markdown do Slack.
3. `enviar_slack_auditoria()` — POST httpx com retry.
4. `processar_lead_realizado()` — orquestra: lista pacientes, compara,
   posta, atualiza Kommo.
5. Endpoints em `webhook.py`:
   - GET /admin/secretaria-auditoria?unidade=...
   - GET /admin/medico-auditoria?medico=...
   - POST /admin/auditoria-confirma?...
   - POST /admin/auditoria-tick
6. Pytest em `tests/test_auditoria_pos_consulta.py` cobrindo:
   - coincide → sem mensagem Slack, status `fechada` auto
   - a_mais → mensagem detalhada, status `aguardando_secretaria`
   - a_menos → idem
   - fonte_vazia → nota Kommo, tarefa Fábio
   - timeout 48h sem secretaria → ping
   - dupla assinatura → status `fechada` + nota consolidada
   - reaction `:x:` → status `divergencia` + tarefa Fábio

Pré-requisitos no Kommo a criar manualmente (6 campos por paciente):
- `N.AGRUPAMENTO ALTERADO` (checkbox)
- `N.AUDITORIA STATUS` (select: aguardando_secretaria / aguardando_medico /
  fechada / divergencia)
- `N.AUDITORIA SECRETARIA` (text — quem assinou + timestamp)
- `N.AUDITORIA MEDICO` (text — quem assinou + timestamp)

Última atualização: 31/05/2026 — esqueleto criado, implementação pendente.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Iterable


# ---------------------------------------------------------------------------
# Tipos e constantes
# ---------------------------------------------------------------------------

SLACK_WEBHOOK_AUDITORIA_URL = os.getenv("SLACK_WEBHOOK_AUDITORIA_URL", "")
AUDITORIA_TIMEOUT_HORAS = int(os.getenv("AUDITORIA_TIMEOUT_HORAS", "48"))

# Slack — canal #auditoria-autorização (workspace blink10).
# Criado em 31/05/2026 pelo Fábio. URL:
#   https://blink10.slack.com/archives/C0B83BK5SMN
SLACK_AUDITORIA_CHANNEL_ID = "C0B83BK5SMN"
SLACK_AUDITORIA_WORKSPACE = "blink10"
# Token bot OAuth (alternativa ao webhook) — preencher quando bot for criado.
SLACK_BOT_TOKEN_AUDITORIA = os.getenv("SLACK_BOT_TOKEN_AUDITORIA", "")

# ---------------------------------------------------------------------------
# Campos Kommo criados em 31/05/2026 — IDs capturados via Chrome MCP.
# 4 campos por paciente × 6 pacientes = 24 campos.
# Group: leads_94241749068044 (aba "Pacientes").
# ---------------------------------------------------------------------------

# field_ids por paciente. Chaves: alterado | status | sec | med.
KOMMO_AUDITORIA_FIELDS: dict[int, dict[str, int]] = {
    1: {"alterado": 1260763, "status": 1260765, "sec": 1260787, "med": 1260789},
    2: {"alterado": 1260767, "status": 1260769, "sec": 1260791, "med": 1260793},
    3: {"alterado": 1260771, "status": 1260773, "sec": 1260795, "med": 1260797},
    4: {"alterado": 1260775, "status": 1260777, "sec": 1260799, "med": 1260801},
    5: {"alterado": 1260779, "status": 1260781, "sec": 1260803, "med": 1260805},
    6: {"alterado": 1260783, "status": 1260785, "sec": 1260807, "med": 1260809},
}

# enum_ids do AUDITORIA STATUS por paciente. Chaves = valores do AuditoriaStatus.
KOMMO_AUDITORIA_STATUS_ENUMS: dict[int, dict[str, int]] = {
    1: {"aguardando_secretaria": 926953, "aguardando_medico": 926955,
        "fechada": 926957, "divergencia": 926959, "fonte_vazia": 926961},
    2: {"aguardando_secretaria": 926963, "aguardando_medico": 926965,
        "fechada": 926967, "divergencia": 926969, "fonte_vazia": 926971},
    3: {"aguardando_secretaria": 926973, "aguardando_medico": 926975,
        "fechada": 926977, "divergencia": 926979, "fonte_vazia": 926981},
    4: {"aguardando_secretaria": 926983, "aguardando_medico": 926985,
        "fechada": 926987, "divergencia": 926989, "fonte_vazia": 926991},
    5: {"aguardando_secretaria": 926993, "aguardando_medico": 926995,
        "fechada": 926997, "divergencia": 926999, "fonte_vazia": 927001},
    6: {"aguardando_secretaria": 927003, "aguardando_medico": 927005,
        "fechada": 927007, "divergencia": 927009, "fonte_vazia": 927011},
}


def kommo_field_id(paciente_idx: int, papel: str) -> int | None:
    """Devolve o field_id Kommo para (paciente, papel).

    papel ∈ {"alterado", "status", "sec", "med"}.
    """
    bucket = KOMMO_AUDITORIA_FIELDS.get(paciente_idx)
    if not bucket:
        return None
    return bucket.get(papel)


def kommo_status_enum_id(paciente_idx: int, status: AuditoriaStatus | str) -> int | None:
    """Devolve o enum_id do AUDITORIA STATUS para (paciente, valor)."""
    bucket = KOMMO_AUDITORIA_STATUS_ENUMS.get(paciente_idx)
    if not bucket:
        return None
    if isinstance(status, AuditoriaStatus):
        status = status.value
    return bucket.get(status)

# Mapeamento médico → canal de assinatura esperado.
MEDICOS_AUDITORIA = {
    "karla": "Dra. Karla Delalíbera",
    "fabricio": "Dr. Fabrício Freitas",
    "katia": "Dra. Kátia Delalíbera",
}

# Mapeamento unidade → secretaria responsável.
SECRETARIAS_AUDITORIA = {
    "asa-norte": "Secretaria Asa Norte",
    "aguas-claras": "Secretaria Águas Claras",
}


class AuditoriaStatus(str, Enum):
    AGUARDANDO_SECRETARIA = "aguardando_secretaria"
    AGUARDANDO_MEDICO = "aguardando_medico"
    FECHADA = "fechada"
    DIVERGENCIA = "divergencia"
    FONTE_VAZIA = "fonte_vazia"


@dataclass
class ResultadoComparacao:
    """Resultado puro da comparação planejado vs realizado.

    Não fala com Kommo nem Slack — só matemática. Permite testar isolado.
    """
    coincide: bool
    exames_a_mais: list[int] = field(default_factory=list)
    exames_a_menos: list[int] = field(default_factory=list)
    fonte_vazia: bool = False
    razao_fonte_vazia: str | None = None


# ---------------------------------------------------------------------------
# Função pura — núcleo testável
# ---------------------------------------------------------------------------

def comparar_agrupamento(
    planejado: Iterable[int] | None,
    realizado: Iterable[int] | None,
) -> ResultadoComparacao:
    """Compara conjunto planejado (N.EXAMES) vs realizado (Medware).

    Retorna ResultadoComparacao. Nenhum efeito colateral.

    Casos:
      - Ambas listas existem e batem → coincide=True
      - Realizado tem item fora do planejado → exames_a_mais não vazio
      - Planejado tem item não realizado → exames_a_menos não vazio
      - Uma das duas é None ou vazia → fonte_vazia=True
    """
    plan_list = list(planejado) if planejado else []
    real_list = list(realizado) if realizado else []

    if not plan_list and not real_list:
        return ResultadoComparacao(
            coincide=False,
            fonte_vazia=True,
            razao_fonte_vazia="planejado e realizado ambos vazios",
        )
    if not plan_list:
        return ResultadoComparacao(
            coincide=False,
            fonte_vazia=True,
            razao_fonte_vazia="planejado vazio (N.EXAMES não foi preenchido)",
        )
    if not real_list:
        return ResultadoComparacao(
            coincide=False,
            fonte_vazia=True,
            razao_fonte_vazia="realizado vazio (Medware sem procedimentos)",
        )

    plan_set = set(plan_list)
    real_set = set(real_list)
    a_mais = sorted(real_set - plan_set)
    a_menos = sorted(plan_set - real_set)
    return ResultadoComparacao(
        coincide=(not a_mais and not a_menos),
        exames_a_mais=a_mais,
        exames_a_menos=a_menos,
    )


# ---------------------------------------------------------------------------
# Formatação de mensagem Slack
# ---------------------------------------------------------------------------

def montar_mensagem_slack(
    lead_id: int,
    paciente_idx: int,
    paciente_nome: str,
    medico_nome: str,
    unidade: str,
    convenio: str,
    agrupador_planejado: str,
    resultado: ResultadoComparacao,
    nomes_procedimentos: dict[int, str] | None = None,
    kommo_url: str | None = None,
) -> str:
    """Monta o markdown da mensagem 1 (discrepância detectada).

    A formatação segue a regra 25.2 do prompt — não inventar.
    """
    nomes = nomes_procedimentos or {}
    secretaria = SECRETARIAS_AUDITORIA.get(
        _slug_unidade(unidade), "Secretaria"
    )

    linhas = [
        ":warning: *Auditoria pós-consulta — discrepância detectada*",
        f"Lead: {lead_id} · Paciente {paciente_idx}: {paciente_nome}",
        f"Médico: {medico_nome} · Unidade: {unidade}",
        f"Convênio: {convenio}",
        f"Agrupador planejado: {agrupador_planejado}",
    ]
    if resultado.exames_a_mais:
        linhas.append("*Exames a MAIS realizados (não autorizados):*")
        for cod in resultado.exames_a_mais:
            nome = nomes.get(cod, "?")
            linhas.append(f"  • {cod} — {nome}")
    if resultado.exames_a_menos:
        linhas.append("*Exames a MENOS (autorizados e não realizados):*")
        for cod in resultado.exames_a_menos:
            nome = nomes.get(cod, "?")
            linhas.append(f"  • {cod} — {nome}")
    linhas.append("")
    linhas.append("*Aguardando:*")
    linhas.append(
        f"[1] {secretaria} revisar → reagir com :white_check_mark:"
    )
    linhas.append(
        f"[2] {medico_nome} confirmar → reagir com :white_check_mark:"
    )
    if kommo_url:
        linhas.append(f"Link Kommo: {kommo_url}")
    return "\n".join(linhas)


def _slug_unidade(unidade: str) -> str:
    """Normaliza 'Asa Norte' → 'asa-norte', 'Águas Claras' → 'aguas-claras'."""
    return (
        (unidade or "")
        .lower()
        .replace("á", "a").replace("ã", "a")
        .replace("ç", "c")
        .replace(" ", "-")
        .strip("- ")
    )


# ---------------------------------------------------------------------------
# Sender Slack — bot OAuth via Web API (mais robusto que webhook)
# ---------------------------------------------------------------------------

def enviar_slack_auditoria(
    payload_markdown: str,
    *,
    bot_token: str | None = None,
    channel_id: str | None = None,
    http_post=None,  # callable injetável p/ testes
) -> dict:
    """POST chat.postMessage para o canal de auditoria.

    Retorna {"ok": bool, "ts": str|None, "channel": str|None, "skipped": bool,
             "reason": str|None}.
    Se token vazio, NÃO faz request, devolve skipped=True (modo dry-run).
    """
    tok = bot_token if bot_token is not None else SLACK_BOT_TOKEN_AUDITORIA
    chan = channel_id or SLACK_AUDITORIA_CHANNEL_ID
    if not tok:
        return {"ok": False, "skipped": True, "reason": "SLACK_BOT_TOKEN_AUDITORIA vazio",
                "ts": None, "channel": chan}
    if http_post is None:
        try:
            import httpx
        except ImportError:
            return {"ok": False, "skipped": True, "reason": "httpx ausente",
                    "ts": None, "channel": chan}

        def http_post(url, headers, json_body):
            return httpx.post(url, headers=headers, json=json_body, timeout=10.0)

    headers = {
        "Authorization": f"Bearer {tok}",
        "Content-Type": "application/json; charset=utf-8",
    }
    body = {"channel": chan, "text": payload_markdown, "mrkdwn": True}
    try:
        r = http_post("https://slack.com/api/chat.postMessage", headers, body)
        data = r.json() if hasattr(r, "json") else {}
        ok = bool(data.get("ok"))
        return {
            "ok": ok,
            "ts": data.get("ts"),
            "channel": data.get("channel") or chan,
            "skipped": False,
            "reason": None if ok else (data.get("error") or f"HTTP {getattr(r, 'status_code', '?')}"),
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "skipped": False, "reason": str(exc), "ts": None, "channel": chan}


def montar_mensagem_coincide(
    lead_id: int, paciente_idx: int, paciente_nome: str,
    medico_nome: str, unidade: str, agrupador_planejado: str,
) -> str:
    """Mensagem 2 — sem discrepância. Não exige assinatura."""
    return (
        f":white_check_mark: *Auditoria pós-consulta — sem discrepância*\n"
        f"Lead {lead_id} · Paciente {paciente_idx}: {paciente_nome} · "
        f"{medico_nome} · {unidade}\n"
        f"Agrupador {agrupador_planejado} mantido. Sem ação necessária."
    )


# ---------------------------------------------------------------------------
# Orquestração de alto nível
# ---------------------------------------------------------------------------

@dataclass
class PacienteAuditoria:
    """Snapshot do que o orquestrador precisa por paciente."""
    idx: int
    nome: str
    medico_nome: str
    unidade: str
    convenio: str
    agrupador_planejado: str          # ex.: "AGRUPADOR_1_ADULTO_ROTINA"
    planejado_codigos: list[int]      # codProcedimento da lista
    realizado_codigos: list[int]
    nomes_procedimentos: dict[int, str] | None = None


@dataclass
class ResultadoAuditoria:
    """Saída do orquestrador por paciente."""
    paciente_idx: int
    status: AuditoriaStatus
    comparacao: ResultadoComparacao
    slack: dict | None = None
    kommo: dict | None = None


def _norm_txt(s: str | None) -> str:
    import unicodedata
    if not s:
        return ""
    s = unicodedata.normalize("NFD", str(s).strip())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return s.lower().replace("-", " ")


def montar_fila_auditoria(
    leads_jsons: list[dict],
    *,
    status_alvo: str,
    unidade: str | None = None,
    medico: str | None = None,
) -> list[dict]:
    """Monta a fila de pendências de auditoria a partir de leads já lidos.

    Para cada lead, varre os 6 slots de paciente e coleta os que estão no
    `status_alvo` (ex.: 'aguardando_secretaria'). Filtra opcionalmente por
    unidade (secretaria) ou médico. Função pura — endpoint injeta os JSONs.
    """
    from . import kommo as _k

    alvo = _norm_txt(status_alvo)
    filtro_uni = _norm_txt(unidade) if unidade else None
    filtro_med = _norm_txt(medico) if medico else None

    fila: list[dict] = []
    for lead in leads_jsons or []:
        if not isinstance(lead, dict):
            continue
        lead_unidade = _k.ler_cf_valor(lead, _k.FIELD_UNIDADE[0])
        lead_medico = _k.ler_cf_valor(lead, _k.FIELD_MEDICOS[0])
        if filtro_uni and filtro_uni not in _norm_txt(lead_unidade):
            continue
        if filtro_med and filtro_med not in _norm_txt(lead_medico):
            continue
        pendentes = []
        for idx in range(1, 7):
            fid = kommo_field_id(idx, "status")
            if not fid:
                continue
            val = _k.ler_cf_valor(lead, fid)
            if val and _norm_txt(val) == alvo:
                nome = (_k.ler_cf_valor(lead, _k.FIELD_NOME_PACIENTES[idx])
                        or f"Paciente {idx}")
                pendentes.append({"paciente_idx": idx, "nome": nome})
        if pendentes:
            fila.append({
                "lead_id": lead.get("id"),
                "nome": lead.get("name"),
                "unidade": lead_unidade,
                "medico": lead_medico,
                "pendentes": pendentes,
            })
    return fila


def montar_snapshot_pacientes(
    lead_json: dict,
    realizado_por_idx: dict[int, list[int]] | None = None,
    *,
    cod_agendamento: int | None = None,
    realizado_fetcher=None,   # callable(cod_agendamento) -> list[int]
) -> list[PacienteAuditoria]:
    """Constrói os PacienteAuditoria a partir do JSON bruto do lead Kommo.

    Lê, por paciente (1..6), o N.EXAMES (planejado) e o N.NOME; do lead lê
    médico/unidade/convênio (campos únicos). O conjunto REALIZADO vem de:
      - `realizado_por_idx[idx]` (injetado — modo teste/simulação), OU
      - `realizado_fetcher(cod_agendamento)` (modo prod — Medware).

    Só inclui pacientes com N.EXAMES preenchido (slots vazios são ignorados).
    Função desacoplada de I/O: o fetcher é injetado. Pura e testável.

    NOTA prod: o Kommo guarda UM cod_agendamento por lead
    (FIELD_COD_AGENDAMENTO), então o realizado do fetcher é o mesmo pra todos
    os pacientes do lead — limitação conhecida e aceita (o caso comum é lead
    de 1 paciente). Quando houver agendamento por paciente, evoluir aqui.
    """
    from . import kommo as _k
    from . import procedimentos as _p

    realizado_por_idx = realizado_por_idx or {}

    medico = _k.ler_cf_valor(lead_json, _k.FIELD_MEDICOS[0]) or "?"
    unidade = _k.ler_cf_valor(lead_json, _k.FIELD_UNIDADE[0]) or "?"
    convenio = _k.ler_cf_valor(lead_json, _k.FIELD_CONVENIO[0]) or "?"

    if cod_agendamento is None:
        cod_raw = _k.ler_cf_valor(lead_json, _k.FIELD_COD_AGENDAMENTO)
        try:
            cod_agendamento = int(cod_raw) if cod_raw else None
        except (TypeError, ValueError):
            cod_agendamento = None

    # Cache do realizado por cod_agendamento (1 chamada Medware por lead).
    _realizado_cache: list[int] | None = None

    pacientes: list[PacienteAuditoria] = []
    for idx in range(1, 7):
        exames_field = _k.FIELD_EXAMES_PACIENTES.get(idx)
        if not exames_field:
            continue
        label = _k.ler_cf_valor(lead_json, exames_field[0])
        if not label:
            continue  # paciente sem agrupador planejado → fora da auditoria
        nome_agr, planejado = _p.codigos_por_label_kommo(label)
        nome_pac = _k.ler_cf_valor(lead_json, _k.FIELD_NOME_PACIENTES[idx]) or f"Paciente {idx}"

        if idx in realizado_por_idx:
            realizado = list(realizado_por_idx[idx])
        else:
            if _realizado_cache is None and realizado_fetcher and cod_agendamento:
                try:
                    _realizado_cache = list(realizado_fetcher(cod_agendamento))
                except Exception:  # noqa: BLE001
                    _realizado_cache = []
            realizado = list(_realizado_cache or [])

        pacientes.append(PacienteAuditoria(
            idx=idx, nome=nome_pac, medico_nome=medico, unidade=unidade,
            convenio=convenio,
            agrupador_planejado=nome_agr or label,
            planejado_codigos=planejado,
            realizado_codigos=realizado,
        ))
    return pacientes


def processar_lead_realizado(
    lead_id: int,
    pacientes: list[PacienteAuditoria],
    kommo_url: str | None = None,
    *,
    slack_sender=enviar_slack_auditoria,
    kommo_writer=None,   # callable (lead_id, paciente_idx, status_enum_id, alterado:bool) -> dict
) -> list[ResultadoAuditoria]:
    """Orquestra a auditoria de TODOS os pacientes do lead.

    Recebe o snapshot já lido — desacoplado de Kommo/Medware pra ser
    testável. O endpoint /admin/auditoria-tick é quem monta os snapshots.

    Para cada paciente:
      1. compara_agrupamento(planejado, realizado).
      2. Se coincide → posta mensagem 2 no Slack, status=FECHADA.
      3. Se discrepância → posta mensagem 1 no Slack, status=AGUARDANDO_SECRETARIA.
      4. Se fonte_vazia → posta alerta, status=FONTE_VAZIA.
      5. Grava status no Kommo (kommo_writer) se houver.
    """
    saidas: list[ResultadoAuditoria] = []
    for p in pacientes:
        comp = comparar_agrupamento(p.planejado_codigos, p.realizado_codigos)
        if comp.fonte_vazia:
            status = AuditoriaStatus.FONTE_VAZIA
            msg = (
                f":exclamation: *Auditoria — fonte vazia*\n"
                f"Lead {lead_id} · Paciente {p.idx}: {p.nome}\n"
                f"Motivo: {comp.razao_fonte_vazia}\n"
                f"Verificar manualmente."
            )
        elif comp.coincide:
            status = AuditoriaStatus.FECHADA
            msg = montar_mensagem_coincide(
                lead_id, p.idx, p.nome, p.medico_nome, p.unidade,
                p.agrupador_planejado,
            )
        else:
            status = AuditoriaStatus.AGUARDANDO_SECRETARIA
            msg = montar_mensagem_slack(
                lead_id=lead_id, paciente_idx=p.idx, paciente_nome=p.nome,
                medico_nome=p.medico_nome, unidade=p.unidade,
                convenio=p.convenio,
                agrupador_planejado=p.agrupador_planejado,
                resultado=comp,
                nomes_procedimentos=p.nomes_procedimentos,
                kommo_url=kommo_url,
            )
        slack = slack_sender(msg) if slack_sender else None
        kommo = None
        if kommo_writer is not None:
            try:
                enum_id = kommo_status_enum_id(p.idx, status)
                alterado = not comp.coincide and not comp.fonte_vazia
                kommo = kommo_writer(lead_id, p.idx, enum_id, alterado)
            except Exception as exc:  # noqa: BLE001
                kommo = {"ok": False, "error": str(exc)}
        saidas.append(ResultadoAuditoria(
            paciente_idx=p.idx, status=status, comparacao=comp,
            slack=slack, kommo=kommo,
        ))
    return saidas


# ---------------------------------------------------------------------------
# Confirmação de assinatura — dupla checagem
# ---------------------------------------------------------------------------

# Papéis válidos.
PAPEIS_SECRETARIA = {"secretaria_an", "secretaria_ac"}
PAPEIS_MEDICO = {"medico_karla", "medico_fabricio", "medico_katia"}


def confirmar_assinatura(
    lead_id: int,
    paciente_idx: int,
    papel: str,
    decisao: str,
    autor: str,
    *,
    status_atual: AuditoriaStatus | str,
    agora: datetime | None = None,
) -> dict:
    """Avança o status do ciclo. Função pura (sem I/O).

    Caller (endpoint webhook) é responsável por:
      - ler status_atual do Kommo
      - persistir o status retornado + autor + timestamp.

    Regras:
      - decisao='divergente' → DIVERGENCIA (ambos papéis).
      - secretaria + AGUARDANDO_SECRETARIA + ok → AGUARDANDO_MEDICO.
      - medico + AGUARDANDO_MEDICO + ok → FECHADA.
      - Idempotente: mesma assinatura quando já FECHADA → mantém FECHADA.
      - papel/decisao inválidos → ValueError.
    """
    if papel not in PAPEIS_SECRETARIA | PAPEIS_MEDICO:
        raise ValueError(f"papel inválido: {papel}")
    if decisao not in ("ok", "divergente"):
        raise ValueError(f"decisao inválida: {decisao}")
    if isinstance(status_atual, str):
        try:
            status_atual = AuditoriaStatus(status_atual)
        except ValueError:
            raise ValueError(f"status_atual inválido: {status_atual}")
    if agora is None:
        agora = datetime.now(timezone.utc)

    timestamp = agora.astimezone().strftime("%d/%m/%Y %H:%M %Z")
    assinatura_str = f"{autor} — {timestamp}"

    # Divergência fecha o ciclo em qualquer papel.
    if decisao == "divergente":
        return {
            "novo_status": AuditoriaStatus.DIVERGENCIA,
            "campo_assinatura": "sec" if papel in PAPEIS_SECRETARIA else "med",
            "assinatura": assinatura_str,
            "criar_tarefa_humana": True,
            "tarefa_titulo": (
                f"Auditoria DIVERGENTE — lead {lead_id} paciente {paciente_idx} — "
                f"{papel} discordou ({autor}). Revisão manual urgente."
            ),
        }

    if papel in PAPEIS_SECRETARIA:
        if status_atual == AuditoriaStatus.AGUARDANDO_SECRETARIA:
            return {
                "novo_status": AuditoriaStatus.AGUARDANDO_MEDICO,
                "campo_assinatura": "sec",
                "assinatura": assinatura_str,
                "criar_tarefa_humana": False,
            }
        # Idempotente — secretaria assina duas vezes, mantém.
        return {
            "novo_status": status_atual,
            "campo_assinatura": "sec",
            "assinatura": assinatura_str,
            "criar_tarefa_humana": False,
            "ja_assinado": True,
        }

    # Médico.
    if status_atual == AuditoriaStatus.AGUARDANDO_MEDICO:
        return {
            "novo_status": AuditoriaStatus.FECHADA,
            "campo_assinatura": "med",
            "assinatura": assinatura_str,
            "criar_tarefa_humana": False,
            "ciclo_fechado": True,
        }
    if status_atual == AuditoriaStatus.AGUARDANDO_SECRETARIA:
        # Médico tentou assinar antes da secretaria — rejeitar.
        return {
            "novo_status": status_atual,
            "campo_assinatura": None,
            "assinatura": None,
            "criar_tarefa_humana": False,
            "erro": "secretaria ainda não confirmou",
        }
    # Idempotente — médico assina depois de FECHADA.
    return {
        "novo_status": status_atual,
        "campo_assinatura": "med",
        "assinatura": assinatura_str,
        "criar_tarefa_humana": False,
        "ja_assinado": True,
    }


# ---------------------------------------------------------------------------
# Timeouts
# ---------------------------------------------------------------------------

def detectar_timeouts(
    pendencias: list[dict],
    *,
    agora: datetime | None = None,
    timeout_horas: int | None = None,
) -> list[dict]:
    """Lista pings a postar no Slack.

    pendencias = lista de dicts {lead_id, paciente_idx, status, criado_em (datetime)}.
    Devolve só as que ultrapassaram o timeout. Função pura.
    """
    if agora is None:
        agora = datetime.now(timezone.utc)
    horas = timeout_horas if timeout_horas is not None else AUDITORIA_TIMEOUT_HORAS
    cutoff = agora - timedelta(hours=horas)
    pings = []
    for p in pendencias:
        status = p.get("status")
        criado = p.get("criado_em")
        if not criado or not isinstance(criado, datetime):
            continue
        if criado > cutoff:
            continue
        if status not in (
            AuditoriaStatus.AGUARDANDO_SECRETARIA,
            AuditoriaStatus.AGUARDANDO_SECRETARIA.value,
            AuditoriaStatus.AGUARDANDO_MEDICO,
            AuditoriaStatus.AGUARDANDO_MEDICO.value,
        ):
            continue
        horas_pendente = int((agora - criado).total_seconds() // 3600)
        pings.append({
            "lead_id": p.get("lead_id"),
            "paciente_idx": p.get("paciente_idx"),
            "status": status if isinstance(status, str) else status.value,
            "horas_pendente": horas_pendente,
            "mensagem": (
                f":hourglass_flowing_sand: Lembrete — lead {p.get('lead_id')} "
                f"paciente {p.get('paciente_idx')} aguarda "
                f"{status if isinstance(status, str) else status.value} "
                f"há {horas_pendente}h."
            ),
        })
    return pings
