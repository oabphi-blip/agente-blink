"""Deduplicação de leads do funil ATENDE 2.LEADS FRIO por telefone.

Origem: Fábio 05/06/2026 — lead 22398836 Lene (96121-411) tem 7+ leads
duplicados na pesquisa por telefone. Cada família tem 1 número → deve
ter 1 lead na fila. Atendente perde tempo enxergando lixo.

Regra do master (sobrevive):
  1. Resposta MAIS RECENTE (updated_at desc)
  2. MAIOR número de notas/interações
  3. MAIS campos preenchidos (proxy de "tem documentos")

Os duplicados:
  - Renomeados pra "[DUP→{master_id}] {nome}"
  - Movidos pra status "Closed-lost" (143) com tag DUPLICADO_DEDUP
  - Recebem nota explicativa apontando pro master
  - REVERSÍVEL — não deleta.

Aplica regra Bug C-06 do protocolo: operação de massa SEMPRE via
endpoint server-side, nunca via tool calls.
"""
from __future__ import annotations

import logging
from typing import Optional

log = logging.getLogger(__name__)

# Status default pra mover duplicados (Closed-lost universal Kommo)
STATUS_CLOSED_LOST_DEFAULT = 143
PIPELINE_ATENDE_DEFAULT = 8601819
STATUS_LEADS_FRIO_DEFAULT = 101508307


def _normalizar_telefone(tel: str | None) -> str | None:
    """Devolve só os dígitos do telefone, ou None se vazio.

    "5561 96121-411" → "556196121411"
    "(61) 96121-411" → "6196121411"
    """
    if not tel:
        return None
    digits = "".join(ch for ch in str(tel) if ch.isdigit())
    if not digits:
        return None
    # Normaliza: se começa com 55 (Brasil) e tem 13 dígitos, mantém.
    # Se tem 10-11 sem 55, prefixa.
    if len(digits) <= 11 and not digits.startswith("55"):
        digits = "55" + digits
    return digits


def _contar_campos_preenchidos(custom_fields_values: list[dict] | None) -> int:
    """Conta quantos custom_fields têm valor não vazio."""
    if not custom_fields_values:
        return 0
    n = 0
    for cf in custom_fields_values:
        vals = cf.get("values") or []
        for v in vals:
            valor = v.get("value")
            if valor not in (None, "", 0, "0"):
                n += 1
                break  # 1 valor preenchido já conta
    return n


def calcular_score(
    *,
    updated_at: int | None = None,
    notas_count: int = 0,
    campos_preenchidos: int = 0,
    last_activity_at: int | None = None,
    tem_inbound_recente: bool = False,
) -> float:
    """Score composto pra escolher master.

    Pesos:
      - tem_inbound_recente × 200 (paciente ESPERANDO resposta — preserva)
      - notas_count × 10 (interações reais)
      - campos_preenchidos × 5 (dados coletados)
      - recência × 0.001 (desempate só — usa last_activity_at se houver,
        senão updated_at; este último é menos confiável porque dispara em
        qualquer mudança de campo, regra Fábio 05/06)

    Maior score = master. Empate → maior lead_id (mais novo).
    """
    inbound_score = 200.0 if tem_inbound_recente else 0.0
    # Recência: prioriza last_activity_at (timestamp da última NOTA real,
    # equivalente operacional de "última mensagem"). Updated_at é só
    # fallback, com mesmo peso pra não distorcer.
    recency_ts = last_activity_at or updated_at or 0
    recency_score = float(recency_ts) / 86400.0 * 0.001
    return (
        inbound_score
        + (notas_count * 10.0)
        + (campos_preenchidos * 5.0)
        + recency_score
    )


def escolher_master(candidatos: list[dict]) -> dict:
    """Recebe lista de dicts {id, updated_at, notas_count, campos_preenchidos}
    e devolve o vencedor (maior score, desempate por id maior).

    Levanta ValueError se lista vazia.
    """
    if not candidatos:
        raise ValueError("escolher_master: lista vazia")
    if len(candidatos) == 1:
        return candidatos[0]

    def chave(c: dict) -> tuple:
        return (
            calcular_score(
                updated_at=c.get("updated_at"),
                notas_count=c.get("notas_count", 0),
                campos_preenchidos=c.get("campos_preenchidos", 0),
                last_activity_at=c.get("last_activity_at"),
                tem_inbound_recente=c.get("tem_inbound_recente", False),
            ),
            c.get("id", 0),  # desempate por id maior (mais novo)
        )

    return max(candidatos, key=chave)


def agrupar_por_telefone(leads_enriquecidos: list[dict]) -> dict[str, list[dict]]:
    """Recebe lista [{id, telefone, ...}] e agrupa por telefone normalizado.

    Leads sem telefone ficam EXCLUÍDOS do agrupamento (não podem deduplicar).
    """
    grupos: dict[str, list[dict]] = {}
    for ld in leads_enriquecidos:
        tel = _normalizar_telefone(ld.get("telefone"))
        if not tel:
            continue
        grupos.setdefault(tel, []).append(ld)
    return grupos


def enriquecer_lead(kommo_client, lead_id: int) -> dict | None:
    """Busca dados ricos do lead pra scoring de master.

    Retorna dict com:
      {id, name, telefone, updated_at, notas_count, campos_preenchidos}
    ou None se erro.
    """
    import httpx
    try:
        with httpx.Client(timeout=15.0) as c:
            r = c.get(
                f"{kommo_client._base}/leads/{lead_id}",
                params={"with": "contacts"},
                headers=kommo_client._headers,
            )
            if r.status_code != 200:
                return None
            data = r.json() or {}
            updated_at = data.get("updated_at")
            campos_preenchidos = _contar_campos_preenchidos(
                data.get("custom_fields_values")
            )
            # Telefone do contato principal
            contacts = ((data.get("_embedded") or {}).get("contacts") or [])
            telefone = None
            if contacts:
                main = next(
                    (ct for ct in contacts if ct.get("is_main")), contacts[0]
                )
                cid = main.get("id")
                if cid:
                    r2 = c.get(
                        f"{kommo_client._base}/contacts/{cid}",
                        headers=kommo_client._headers,
                    )
                    if r2.status_code == 200:
                        cdata = r2.json() or {}
                        for cf in (cdata.get("custom_fields_values") or []):
                            if cf.get("field_code") == "PHONE":
                                vals = cf.get("values") or []
                                if vals and vals[0].get("value"):
                                    telefone = str(vals[0]["value"])
                                    break
        # Notas (separadas) — extrai timestamp da última atividade real
        notas = kommo_client.get_lead_notes(lead_id, limit=250) or []
        notas_count = len(notas)
        last_activity_at = None
        tem_inbound_recente = False
        if notas:
            # get_lead_notes vem ordenado desc — primeira = mais recente
            last_activity_at = notas[0].get("created_at") or updated_at
            # Heurística "inbound recente": olha 5 notas mais recentes
            # — se alguma é mensagem do cliente (params.is_from_lead=True
            # ou note_type=service_message com campo inbound), marca.
            for n in notas[:5]:
                params = n.get("params") or {}
                if params.get("is_from_lead") is True:
                    tem_inbound_recente = True
                    break
                ntype = (n.get("note_type") or "").lower()
                txt = (params.get("text") or "").lower()
                # mensagens inbound costumam vir com note_type específico
                if ntype == "service_message" and "→ ariany" not in txt:
                    if params.get("inbound") is True:
                        tem_inbound_recente = True
                        break
        return {
            "id": lead_id,
            "name": data.get("name"),
            "telefone": telefone,
            "updated_at": updated_at,
            "last_activity_at": last_activity_at,
            "tem_inbound_recente": tem_inbound_recente,
            "notas_count": notas_count,
            "campos_preenchidos": campos_preenchidos,
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("[DEDUP] enriquecer lead %s falhou: %s", lead_id, exc)
        return None


# Etapas frias/inativas — seguras pra dedup automática.
# Etapas ativas (AGENDADO/CONFIRMAR/REALIZADO/ATENDIMENTO HUMANO) ficam de fora.
STATUS_IDS_DEDUP_SEGUROS = [
    96441724,   # 0-ETAPA ENTRADA
    101508307,  # 2.LEADS FRIO
    102560495,  # 3-AGENDAR
    106184631,  # 4.REAGENDAR
    106184983,  # 7.1-NO-SHOW (ATIVAR)
    106919911,  # 0-a classificar
]

NOMES_ETAPAS = {
    96441724: "0-ETAPA ENTRADA",
    101508307: "2.LEADS FRIO",
    102560495: "3-AGENDAR",
    106184631: "4.REAGENDAR",
    106184983: "7.1-NO-SHOW",
    106919911: "0-a classificar",
    143: "Closed-lost",
}


def deduplicar_batch(
    kommo_client,
    *,
    pipeline_id: int = PIPELINE_ATENDE_DEFAULT,
    status_id: int | None = None,
    status_ids: list[int] | None = None,
    status_destino_duplicado: int = STATUS_CLOSED_LOST_DEFAULT,
    max_leads: int = 500,
    dry_run: bool = True,
    progress_callback=None,
) -> dict:
    """Varre leads em status_id(s), agrupa por telefone, marca duplicados.

    Args:
        kommo_client: instância KommoClient
        pipeline_id: default ATENDE
        status_id: legacy — etapa única
        status_ids: nova — lista de etapas. Se None usa STATUS_IDS_DEDUP_SEGUROS
        status_destino_duplicado: default 143 lost
        max_leads: corte total agregado
        dry_run: True = só preview, False = aplica
        progress_callback: opcional, recebe dict com {fase, total_lidos,
            com_telefone, grupos_duplicados, etapa_atual, movidos, ...}
            chamado a cada lead lido e a cada lead movido.

    Retorna sumário ampliado com `por_etapa` (qtd duplicados por etapa).
    """
    if not kommo_client:
        return {"ok": False, "razao": "sem_kommo_client"}

    # Resolve etapas alvo (multi-etapa)
    if status_ids:
        alvo_etapas = list(status_ids)
    elif status_id:
        alvo_etapas = [status_id]
    else:
        alvo_etapas = list(STATUS_IDS_DEDUP_SEGUROS)

    enriquecidos: list[dict] = []
    sem_telefone = 0
    total_lidos = 0
    LIMITE = 250

    def _notify(fase, **extras):
        if progress_callback:
            try:
                progress_callback({
                    "fase": fase,
                    "total_lidos": total_lidos,
                    "com_telefone": len(enriquecidos),
                    "sem_telefone": sem_telefone,
                    "max_leads": max_leads,
                    **extras,
                })
            except Exception:  # noqa: BLE001
                pass

    # FASE 1: ler leads (uma etapa por vez)
    for etapa_id in alvo_etapas:
        if total_lidos >= max_leads:
            break
        page = 1
        _notify("lendo_etapa", etapa_atual=etapa_id,
                etapa_nome=NOMES_ETAPAS.get(etapa_id, str(etapa_id)))
        while total_lidos < max_leads:
            try:
                leads = kommo_client.list_leads_by_status(
                    pipeline_id=pipeline_id, status_ids=[etapa_id],
                    limit=LIMITE, page=page,
                )
            except Exception as exc:  # noqa: BLE001
                log.warning(
                    "[DEDUP] list_leads etapa=%s page=%d erro: %s",
                    etapa_id, page, exc,
                )
                break
            if not leads:
                break

            for ld in leads:
                if total_lidos >= max_leads:
                    break
                total_lidos += 1
                lid = ld.get("id")
                if not lid:
                    continue
                enriquecido = enriquecer_lead(kommo_client, lid)
                if not enriquecido:
                    continue
                # injeta etapa de origem pra breakdown
                enriquecido["etapa_id"] = etapa_id
                if not enriquecido.get("telefone"):
                    sem_telefone += 1
                    continue
                enriquecidos.append(enriquecido)
                # notifica a cada 10 leads pra não floodar Redis
                if total_lidos % 10 == 0:
                    _notify("enriquecendo", etapa_atual=etapa_id)

            if len(leads) < LIMITE:
                break
            page += 1

    # FASE 2: agrupar
    _notify("agrupando")
    grupos = agrupar_por_telefone(enriquecidos)
    grupos_com_dup = {tel: ld for tel, ld in grupos.items() if len(ld) > 1}

    # FASE 3: decidir master + plano
    plano: list[dict] = []
    total_duplicados = 0
    por_etapa: dict[int, int] = {}
    for tel, candidatos in grupos_com_dup.items():
        master = escolher_master(candidatos)
        duplicados = [c for c in candidatos if c["id"] != master["id"]]
        total_duplicados += len(duplicados)
        for d in duplicados:
            eid = d.get("etapa_id")
            if eid:
                por_etapa[eid] = por_etapa.get(eid, 0) + 1
        plano.append({
            "telefone": tel,
            "master_id": master["id"],
            "master_nome": master.get("name"),
            "master_etapa": NOMES_ETAPAS.get(
                master.get("etapa_id"), str(master.get("etapa_id"))
            ),
            "master_notas": master.get("notas_count"),
            "master_inbound_recente": master.get("tem_inbound_recente", False),
            "master_last_activity_at": master.get("last_activity_at"),
            "master_score": calcular_score(
                updated_at=master.get("updated_at"),
                notas_count=master.get("notas_count", 0),
                campos_preenchidos=master.get("campos_preenchidos", 0),
                last_activity_at=master.get("last_activity_at"),
                tem_inbound_recente=master.get("tem_inbound_recente", False),
            ),
            "duplicados_ids": [d["id"] for d in duplicados],
            "duplicados_nomes": [d.get("name") for d in duplicados],
            "duplicados_etapas": [
                NOMES_ETAPAS.get(d.get("etapa_id"), str(d.get("etapa_id")))
                for d in duplicados
            ],
            "total_no_grupo": len(candidatos),
        })

    movidos = 0
    falhas = 0

    # FASE 4: aplicar (se não dry_run)
    if not dry_run:
        _notify("aplicando", total_duplicados=total_duplicados,
                grupos_duplicados=len(grupos_com_dup))
        for grupo in plano:
            master_id = grupo["master_id"]
            for dup_id, dup_nome in zip(
                grupo["duplicados_ids"], grupo["duplicados_nomes"]
            ):
                ok = _marcar_como_duplicado(
                    kommo_client, dup_id, master_id, dup_nome,
                    status_destino=status_destino_duplicado,
                )
                if ok:
                    movidos += 1
                else:
                    falhas += 1
                # progresso a cada movido
                _notify("movendo", movidos=movidos, falhas=falhas,
                        total_duplicados=total_duplicados,
                        grupos_duplicados=len(grupos_com_dup))

    por_etapa_nomes = {
        NOMES_ETAPAS.get(eid, str(eid)): qtd for eid, qtd in por_etapa.items()
    }

    resultado = {
        "ok": True,
        "etapas_varridas": alvo_etapas,
        "total_lidos": total_lidos,
        "com_telefone": len(enriquecidos),
        "sem_telefone": sem_telefone,
        "grupos_duplicados": len(grupos_com_dup),
        "total_duplicados": total_duplicados,
        "masters_count": len(grupos_com_dup),
        "movidos": movidos,
        "falhas": falhas,
        "dry_run": dry_run,
        "por_etapa": por_etapa_nomes,
        "amostra_grupos": plano[:30],
    }
    _notify("concluido", resultado=resultado)
    return resultado


def _marcar_como_duplicado(
    kommo_client, lead_id: int, master_id: int,
    nome_original: str | None, *, status_destino: int,
) -> bool:
    """Marca um lead como duplicado: rename + nota + move pra closed-lost.

    Reversível: não deleta. Apenas move e renomeia com prefix [DUP→X].
    """
    try:
        # 1) Rename pra deixar visual: [DUP→MASTER_ID] nome_original
        nome_atual = (nome_original or "lead").strip()
        # Evita duplicar prefix se já tem
        if not nome_atual.startswith("[DUP"):
            novo_nome = f"[DUP→{master_id}] {nome_atual}"[:240]
            kommo_client.rename_lead(lead_id, novo_nome)

        # 2) Nota explicativa
        try:
            kommo_client.add_note(
                lead_id,
                (
                    f"🔁 Lead identificado como DUPLICADO via dedup automático.\n"
                    f"Master (sobrevive): lead {master_id}.\n"
                    f"Critério: master tem mais interações + dados mais recentes.\n"
                    f"Reversível — basta renomear e mover de volta se erro."
                ),
            )
        except Exception:  # noqa: BLE001
            pass  # nota é nice-to-have, não bloqueia

        # 3) Move pra Closed-lost
        ok_status = kommo_client.update_lead_status(lead_id, status_destino)
        return bool(ok_status)
    except Exception as exc:  # noqa: BLE001
        log.warning("[DEDUP] marcar duplicado lead %s falhou: %s", lead_id, exc)
        return False
