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
    updated_at: int | None,
    notas_count: int,
    campos_preenchidos: int,
) -> float:
    """Score composto pra escolher master.

    Pesos:
      - notas_count × 10 (interações reais valem muito)
      - campos_preenchidos × 5 (proxy de dados coletados)
      - updated_at_dias × 0.5 (recencia, normalizada em dias-desde-epoch)

    Maior score = master. Empate → maior lead_id (mais novo).
    """
    upd_score = 0.0
    if updated_at:
        # divide por 86400 (segundos por dia) → score em "dias-desde-epoch"
        upd_score = float(updated_at) / 86400.0 * 0.5
    return (notas_count * 10.0) + (campos_preenchidos * 5.0) + upd_score


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
        # Notas (separadas)
        notas = kommo_client.get_lead_notes(lead_id, limit=250) or []
        notas_count = len(notas)
        return {
            "id": lead_id,
            "name": data.get("name"),
            "telefone": telefone,
            "updated_at": updated_at,
            "notas_count": notas_count,
            "campos_preenchidos": campos_preenchidos,
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("[DEDUP] enriquecer lead %s falhou: %s", lead_id, exc)
        return None


def deduplicar_batch(
    kommo_client,
    *,
    pipeline_id: int = PIPELINE_ATENDE_DEFAULT,
    status_id: int = STATUS_LEADS_FRIO_DEFAULT,
    status_destino_duplicado: int = STATUS_CLOSED_LOST_DEFAULT,
    max_leads: int = 500,
    dry_run: bool = True,
) -> dict:
    """Varre leads em status_id, agrupa por telefone, marca duplicados.

    Args:
        kommo_client: instância KommoClient
        pipeline_id: default ATENDE
        status_id: default 2.LEADS FRIO
        status_destino_duplicado: pra onde mover duplicados (default 143 lost)
        max_leads: corte de segurança
        dry_run: True = só preview, False = aplica

    Retorna:
        {
            ok, total_lidos, com_telefone, sem_telefone,
            grupos_duplicados, total_duplicados,
            masters_count, movidos, falhas, dry_run,
            amostra_grupos: [{tel, master_id, duplicados_ids}, ...]
        }
    """
    if not kommo_client:
        return {"ok": False, "razao": "sem_kommo_client"}

    enriquecidos: list[dict] = []
    sem_telefone = 0
    total_lidos = 0
    page = 1
    LIMITE = 250

    while total_lidos < max_leads:
        try:
            leads = kommo_client.list_leads_by_status(
                pipeline_id=pipeline_id, status_ids=[status_id],
                limit=LIMITE, page=page,
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("[DEDUP] list_leads page=%d erro: %s", page, exc)
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
            if not enriquecido.get("telefone"):
                sem_telefone += 1
                continue
            enriquecidos.append(enriquecido)

        if len(leads) < LIMITE:
            break
        page += 1

    # Agrupa
    grupos = agrupar_por_telefone(enriquecidos)
    grupos_com_dup = {tel: ld for tel, ld in grupos.items() if len(ld) > 1}

    # Decide master + duplicados por grupo
    plano: list[dict] = []
    total_duplicados = 0
    for tel, candidatos in grupos_com_dup.items():
        master = escolher_master(candidatos)
        duplicados = [c for c in candidatos if c["id"] != master["id"]]
        total_duplicados += len(duplicados)
        plano.append({
            "telefone": tel,
            "master_id": master["id"],
            "master_nome": master.get("name"),
            "master_notas": master.get("notas_count"),
            "master_score": calcular_score(
                updated_at=master.get("updated_at"),
                notas_count=master.get("notas_count", 0),
                campos_preenchidos=master.get("campos_preenchidos", 0),
            ),
            "duplicados_ids": [d["id"] for d in duplicados],
            "duplicados_nomes": [d.get("name") for d in duplicados],
            "total_no_grupo": len(candidatos),
        })

    movidos = 0
    falhas = 0
    if not dry_run:
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

    return {
        "ok": True,
        "total_lidos": total_lidos,
        "com_telefone": len(enriquecidos),
        "sem_telefone": sem_telefone,
        "grupos_duplicados": len(grupos_com_dup),
        "total_duplicados": total_duplicados,
        "masters_count": len(grupos_com_dup),
        "movidos": movidos,
        "falhas": falhas,
        "dry_run": dry_run,
        "amostra_grupos": plano[:30],  # primeiros 30 grupos pra inspeção
    }


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
