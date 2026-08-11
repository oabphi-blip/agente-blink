"""Observabilidade Meta → Kommo — Parte 2 (task #379).

Gravar nos 5 custom fields de acompanhamento de templates Meta a cada
disparo via WhatsApp Cloud, e mapear `wamid → lead_id` em Redis pra que
o callback de status (delivered/read/failed) da Meta consiga atualizar
o campo STATUS ÚLTIMO DISPARO no lead correto.

Custom fields esperados (criados por
``voice_agent/scripts/criar_campos_kommo_templates_meta.py``):

  - ULTIMO TEMPLATE META       (select)
  - TEMPLATES JÁ RECEBIDOS     (multiselect)
  - CATEGORIA TEMPLATE         (select)
  - DATA ÚLTIMO DISPARO META   (date_time)
  - STATUS ÚLTIMO DISPARO      (select)

Os field_ids são descobertos via ``kommo_client.list_custom_fields()``
na primeira chamada e ficam cacheados em variável de módulo (cleared
chamando :func:`resetar_cache_field_ids`, útil em testes).
"""
from __future__ import annotations

import logging
import time
from typing import Any

log = logging.getLogger(__name__)


# Mapeamento NOME-CANÔNICO (UPPERCASE) → chave usada pelo
# ``kommo_client.update_lead_fields`` (semântica do KommoClient).
CAMPO_TO_KOMMO_KEY: dict[str, str] = {
    "ULTIMO TEMPLATE META": "ultimo_template_meta",
    "TEMPLATES JÁ RECEBIDOS": "templates_ja_recebidos",
    "CATEGORIA TEMPLATE": "categoria_template",
    "DATA ÚLTIMO DISPARO META": "data_ultimo_disparo_meta_ts",
    "STATUS ÚLTIMO DISPARO": "status_ultimo_disparo",
}

NOMES_CAMPOS = tuple(CAMPO_TO_KOMMO_KEY.keys())

# Cache de field_ids descoberto via list_custom_fields().
# Chave = NOME UPPERCASE; valor = field_id (int).
_field_id_cache: dict[str, int] | None = None

# TTL do mapping wamid→lead_id no Redis (7 dias).
WAMID_LEAD_TTL_SEG = 7 * 24 * 3600
WAMID_LEAD_KEY_FMT = "blink:wamid_lead:{wamid}"


def resetar_cache_field_ids() -> None:
    """Limpa o cache de field_ids — usado em testes."""
    global _field_id_cache
    _field_id_cache = None


def descobrir_field_ids(kommo_client) -> dict[str, int]:
    """Descobre os field_ids dos 5 campos via list_custom_fields().

    Retorna um dict {NOME_UPPERCASE: field_id}. Em caso de erro ou cliente
    sem suporte, retorna {} silenciosamente — `gravar_template_disparado`
    deixa de gravar mas não derruba o fluxo principal.
    """
    global _field_id_cache
    if _field_id_cache is not None:
        return _field_id_cache
    if kommo_client is None or not hasattr(kommo_client, "list_custom_fields"):
        return {}
    try:
        items = kommo_client.list_custom_fields("leads") or []
    except Exception as exc:  # noqa: BLE001
        log.warning(
            "[templates_obs] list_custom_fields falhou: %s", exc,
        )
        return {}
    mapping: dict[str, int] = {}
    for cf in items:
        if not isinstance(cf, dict):
            continue
        nome = (cf.get("name") or "").strip().upper()
        if nome in CAMPO_TO_KOMMO_KEY and cf.get("id"):
            try:
                mapping[nome] = int(cf["id"])
            except (TypeError, ValueError):
                continue
    _field_id_cache = mapping
    if len(mapping) < len(CAMPO_TO_KOMMO_KEY):
        faltam = [n for n in NOMES_CAMPOS if n not in mapping]
        log.warning(
            "[templates_obs] campos Kommo nao encontrados: %s",
            faltam,
        )
    return mapping


def _categoria_para(template_name: str) -> str:
    """Calcula categoria via ``sync_meta_to_kommo._categorizar``.

    Import lazy pra evitar custo no boot do app e pra facilitar o pytest
    com mocks. Retorna 'Operacional' como fallback final.
    """
    try:
        from voice_agent.scripts.sync_meta_to_kommo import _categorizar
        return _categorizar(template_name)
    except Exception as exc:  # noqa: BLE001
        log.warning(
            "[templates_obs] _categorizar falhou para %s: %s",
            template_name, exc,
        )
        return "Operacional"


def _gravar_wamid_lead_em_redis(
    redis_client: Any,
    wamid: str,
    lead_id: int,
) -> bool:
    """Grava o mapping wamid→lead_id em Redis (TTL 7 dias).

    Retorna True se gravou, False se sem redis ou em erro.
    """
    if not wamid or not redis_client:
        return False
    chave = WAMID_LEAD_KEY_FMT.format(wamid=wamid)
    try:
        # Usa setex se disponível, senão set + expire.
        if hasattr(redis_client, "setex"):
            redis_client.setex(chave, WAMID_LEAD_TTL_SEG, str(int(lead_id)))
        else:
            redis_client.set(chave, str(int(lead_id)), ex=WAMID_LEAD_TTL_SEG)
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning(
            "[templates_obs] falha ao gravar wamid→lead em Redis: %s", exc,
        )
        return False


def lookup_lead_por_wamid(redis_client: Any, wamid: str) -> int | None:
    """Resolve wamid → lead_id consultando o Redis."""
    if not wamid or not redis_client:
        return None
    chave = WAMID_LEAD_KEY_FMT.format(wamid=wamid)
    try:
        raw = redis_client.get(chave)
    except Exception as exc:  # noqa: BLE001
        log.warning(
            "[templates_obs] falha ao ler wamid→lead em Redis: %s", exc,
        )
        return None
    if raw is None:
        return None
    try:
        if isinstance(raw, (bytes, bytearray)):
            raw = raw.decode("utf-8")
        return int(raw)
    except (TypeError, ValueError):
        return None


def _ler_templates_atuais(kommo_client, lead_id: int) -> list[str]:
    """Lê o multiselect TEMPLATES JÁ RECEBIDOS do lead, se possível.

    O update_lead_fields do KommoClient grava `add_select` por enum
    individual (sobrescreve). Pro multiselect manter histórico, a gente
    poderia listar os valores atuais e mandar union. Hoje update_lead_fields
    só aceita 1 valor por campo, então a estratégia é simples: passamos o
    template atual e cabe ao MCP / update futuro lidar. Por enquanto
    retorna [] (best-effort).
    """
    # Implementação intencionalmente leve — o write hoje passa só o
    # nome do template atual; histórico fica no campo ULTIMO TEMPLATE
    # META + nas notas Kommo do dispatcher.
    return []


def gravar_template_disparado(
    kommo_client,
    lead_id: int,
    template_name: str,
    categoria: str | None = None,
    wamid: str | None = None,
    redis_client: Any = None,
    timestamp: int | None = None,
) -> dict:
    """Grava nos 5 custom fields que esse template foi disparado.

    - ULTIMO TEMPLATE META       (select)    = template_name
    - TEMPLATES JÁ RECEBIDOS     (multiselect) = template_name (best-effort)
    - CATEGORIA TEMPLATE         (select)    = categoria (auto se None)
    - DATA ÚLTIMO DISPARO META   (date_time) = timestamp (int(time.time()))
    - STATUS ÚLTIMO DISPARO      (select)    = "sent"

    Adicionalmente: se ``wamid`` e ``redis_client`` forem fornecidos,
    grava ``blink:wamid_lead:{wamid}`` com TTL 7 dias pra que o webhook
    de status da Meta consiga resolver wamid→lead_id.

    Retorna:
      {ok: bool, fields_atualizados: list[str], erro: str | None,
       wamid_gravado_redis: bool}
    """
    res = {
        "ok": False,
        "fields_atualizados": [],
        "erro": None,
        "wamid_gravado_redis": False,
    }

    if not template_name:
        res["erro"] = "template_name_vazio"
        return res

    if kommo_client is None or not hasattr(kommo_client, "update_lead_fields"):
        res["erro"] = "kommo_client_invalido"
        return res

    # Resolver categoria (auto se None).
    cat = categoria if categoria else _categoria_para(template_name)

    ts = int(timestamp) if timestamp is not None else int(time.time())

    payload: dict[str, Any] = {
        CAMPO_TO_KOMMO_KEY["ULTIMO TEMPLATE META"]: template_name,
        CAMPO_TO_KOMMO_KEY["TEMPLATES JÁ RECEBIDOS"]: template_name,
        CAMPO_TO_KOMMO_KEY["CATEGORIA TEMPLATE"]: cat,
        CAMPO_TO_KOMMO_KEY["DATA ÚLTIMO DISPARO META"]: ts,
        CAMPO_TO_KOMMO_KEY["STATUS ÚLTIMO DISPARO"]: "sent",
    }

    fields_atualizados = list(NOMES_CAMPOS)

    try:
        ok_update = kommo_client.update_lead_fields(int(lead_id), payload)
    except Exception as exc:  # noqa: BLE001
        log.warning(
            "[templates_obs] update_lead_fields excecao lead=%s: %s",
            lead_id, exc,
        )
        res["erro"] = f"update_excecao: {str(exc)[:200]}"
        return res

    if not ok_update:
        res["erro"] = "update_lead_fields_retornou_false"
        return res

    res["ok"] = True
    res["fields_atualizados"] = fields_atualizados

    # Mapping wamid→lead pra webhook Meta status callback.
    if wamid and redis_client is not None:
        gravou = _gravar_wamid_lead_em_redis(redis_client, wamid, int(lead_id))
        res["wamid_gravado_redis"] = gravou

    log.info(
        "[templates_obs] OK lead=%s template=%s cat=%s wamid=%s ts=%d",
        lead_id, template_name, cat, wamid or "-", ts,
    )
    return res


def atualizar_status_ultimo_disparo(
    kommo_client,
    lead_id: int,
    novo_status: str,
) -> dict:
    """Atualiza só o STATUS ÚLTIMO DISPARO no lead.

    Usado pelo webhook de status callback da Meta (delivered/read/failed).
    Retorna {ok, erro}.
    """
    res = {"ok": False, "erro": None}
    if kommo_client is None or not hasattr(kommo_client, "update_lead_fields"):
        res["erro"] = "kommo_client_invalido"
        return res
    if not novo_status:
        res["erro"] = "status_vazio"
        return res
    try:
        ok = kommo_client.update_lead_fields(
            int(lead_id),
            {
                CAMPO_TO_KOMMO_KEY["STATUS ÚLTIMO DISPARO"]: novo_status,
            },
        )
    except Exception as exc:  # noqa: BLE001
        res["erro"] = f"update_excecao: {str(exc)[:200]}"
        return res
    if not ok:
        res["erro"] = "update_lead_fields_retornou_false"
        return res
    res["ok"] = True
    log.info(
        "[templates_obs] STATUS atualizado lead=%s status=%s",
        lead_id, novo_status,
    )
    return res
