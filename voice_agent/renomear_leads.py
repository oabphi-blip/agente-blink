"""Renomeação em massa de leads do funil ATENDE pra padrão visual.

Origem: Fábio 04/06/2026 — pediu pra renomear 368 leads em 2.LEADS FRIO
de forma autônoma. Nome atual é caótico ("REAGENDAR", "AGENDAR_ paciente
não respondeu mais após o valor", etc.), atendente não consegue priorizar
sem abrir cada lead.

Padrão novo:
  [CAT] <nome_limpo>

Categorias:
  R - REAGENDAR/REMARCAÇÃO/FALTOU/DESMARCOU
  E - COM CONVÊNIO declarado
  V - sem resposta após VALOR apresentado
  C - SEM CONVÊNIO / particular
  A - AGENDAR_ genérico sem contexto
  X - convênio NÃO ACEITO (Inas, GDF, Cassi, Sulamerica, Bradesco)

Bug Pedro Miguel (#226) mostrou que precisamos ORDENAR cronológico —
mesma filosofia aqui: começar pelo mais ANTIGO (updated_at asc) é o
default, pra priorizar quem tá parado há mais tempo.
"""
from __future__ import annotations

import logging
import re
from typing import Optional

log = logging.getLogger(__name__)


# Palavras-chave por categoria (case-insensitive, sem acentos no match)
KEYWORDS_CATEGORIA = {
    "X": [
        "INAS", "GDF", "CASSI", "SULAMERICA", "SUL AMERICA",
        "BRADESCO", "UNIMED",  # Blink não atende Unimed
    ],
    "R": [
        "REAGENDAR", "REMARCAR", "REMARCAÇÃO", "REMARCACAO",
        "FALTOU", "FALTANTE", "DESMARCOU", "DESMARCAR",
        "DESMARCAÇÃO", "DESMARCACAO", "PÓS DESMARCAÇÃO",
        "REAGENDAMENTO",
    ],
    "E": [
        "COM CONVÊNIO", "COM CONVENIO",
    ],
    "C": [
        "SEM CONVÊNIO", "SEM CONVENIO", "PARTICULAR",
    ],
    "V": [
        "APRESENTADO VALOR", "APÓS VALOR", "APOS VALOR",
        "NÃO RESPONDEU APÓS", "NAO RESPONDEU APOS",
        "AGUARDANDO RETORNO", "AGUARDANDO RESPOSTA",
        "AGUARDANDO PACIENTE", "VERIFICAR COM MARIDO",
        "VERIFICAR VALOR", "AGUARDANDO CONCORDANCIA",
        "AGUARDANDO CONCORDÂNCIA", "SEM RESPOSTA",
        "PAROU DE RESPONDER",
    ],
    "A": [
        "AGENDAR_", "AGENDAR ROTINA", "AGENDAR CONSULTA",
        "CAPTAÇÃO", "CAPTACAO", "ATIVAR", "ATIVAÇÃO", "ATIVACAO",
        "ATIVADO", "ATIVAÇAO",
    ],
}

# Ordem de checagem (prioridade decrescente):
# X — convênio não aceito (excluir) sempre primeiro
# C — sem convênio / Particular (explícito vence "aguardando")
# E — com convênio declarado
# R — reagendar / faltou
# V — sem resposta após valor (heurístico)
# A — catch-all genérico
ORDEM_CATEGORIA = ["X", "C", "E", "R", "V", "A"]


def categorizar_nome(nome: str) -> str:
    """Recebe nome do lead e devolve categoria R/E/V/C/A/X.

    Default 'A' se nada casar (genérico AGENDAR).
    Se nome já vier no formato [X] preserva a categoria do prefixo.
    """
    if not nome:
        return "A"
    # Se já está no formato [X] <nome>, devolve a categoria do prefixo
    m = re.match(r"^\[([A-Z])\]\s", nome)
    if m:
        cat_pref = m.group(1)
        if cat_pref in ORDEM_CATEGORIA:
            return cat_pref
    nome_upper = nome.upper()
    for cat in ORDEM_CATEGORIA:
        keywords = KEYWORDS_CATEGORIA[cat]
        if any(kw in nome_upper for kw in keywords):
            return cat
    return "A"


def limpar_nome(nome: str, max_chars: int = 70) -> str:
    """Limpa o nome atual pra ficar mais legível na tabela Kommo.

    - Remove prefixos repetidos (AGENDAR_, AGENDAR ROTINA_, etc)
    - Tira underscores virando espaço
    - Trunca em max_chars com elipse
    - Normaliza espaços
    """
    if not nome:
        return ""

    # Remove prefixos verbais que NÃO carregam informação útil
    # (mantém FALTOU/REAGENDAR porque ajudam a entender o estado)
    prefixos = [
        r"^AGENDAR_+\s*", r"^AGENDAR\s+ROTINA[_\s]*",
        r"^AGENDAR\s+CONSULTA[_\s]*",
        r"^TENTANTO\s+REAGENDAR[_\s]*",
        r"^CAPTAÇÃO[_\s]*", r"^CAPTACAO[_\s]*",
        r"^ATIVAR[_\s]*", r"^ATIVAÇÃO[_\s]*", r"^ATIVADO[_\s]*",
    ]
    limpo = nome
    for pat in prefixos:
        novo = re.sub(pat, "", limpo, flags=re.IGNORECASE)
        if novo != limpo:
            limpo = novo
            break

    # Underscores viram espaço (mas mantém em CPFs/IDs)
    limpo = re.sub(r"_+", " ", limpo)
    # Normaliza espaços
    limpo = re.sub(r"\s+", " ", limpo).strip()
    # Remove "ativado 24h" e similares chatos
    limpo = re.sub(r"ativado\s+24h[_\s]*", "", limpo, flags=re.IGNORECASE).strip()

    # Se sobrou só uma palavra-keyword vazia de contexto, devolve placeholder
    palavras_vazias = {
        "AGENDAR", "REAGENDAR", "REMARCAR", "CAPTAÇÃO", "CAPTACAO",
        "ATIVAR", "ATIVAÇÃO", "ATIVACAO", "ATIVADO",
    }
    if limpo.upper().strip() in palavras_vazias:
        return "(sem contexto)"

    # Trunca
    if len(limpo) > max_chars:
        limpo = limpo[:max_chars].rstrip() + "…"

    return limpo or "(sem contexto)"


def gerar_novo_nome(nome_atual: str) -> tuple[str, str]:
    """Devolve (categoria, novo_nome).

    Exemplos:
      "REAGENDAR" -> ("R", "[R] REAGENDAR")
      "AGENDAR_ paciente não respondeu mais após o valor"
        -> ("V", "[V] paciente não respondeu mais após o valor")
      "INAS_Se não conseguir..." -> ("X", "[X] INAS Se não conseguir...")
    """
    cat = categorizar_nome(nome_atual)
    limpo = limpar_nome(nome_atual)

    # Se nome já começa com [X] não duplica
    if re.match(r"^\[[A-Z]\]\s", nome_atual or ""):
        # Já está no padrão — devolve nome igual + categoria detectada
        return cat, nome_atual

    novo = f"[{cat}] {limpo}"
    return cat, novo


def renomear_batch(
    kommo_client,
    *,
    pipeline_id: int = 8601819,
    status_id: int = 101508307,
    max_leads: int = 500,
    dry_run: bool = True,
    skip_ja_padronizado: bool = True,
) -> dict:
    """Lista leads em status_id e renomeia conforme padrão.

    Args:
        kommo_client: instância KommoClient
        pipeline_id: default ATENDE 8601819
        status_id: default 2.LEADS FRIO 101508307
        max_leads: máximo 500 por execução (segurança)
        dry_run: se True, NÃO atualiza Kommo — só devolve preview
        skip_ja_padronizado: se True, ignora leads já no formato [X]

    Retorna:
        {
            ok, total_lidos, ja_padronizados, candidatos,
            renomeados, falhas, dry_run,
            por_categoria: {R: N, E: N, V: N, C: N, A: N, X: N},
            amostra_preview: [{id, nome_atual, nome_novo, cat}, ...]
        }
    """
    if not kommo_client:
        return {"ok": False, "razao": "sem_kommo_client"}

    total_lidos = 0
    ja_padronizados = 0
    candidatos = []
    renomeados = 0
    falhas = 0
    por_categoria = {c: 0 for c in ORDEM_CATEGORIA}

    page = 1
    LIMITE_POR_PAGE = 250
    enquanto_houver = True

    while enquanto_houver and total_lidos < max_leads:
        try:
            leads = kommo_client.list_leads_by_status(
                pipeline_id=pipeline_id,
                status_ids=[status_id],
                limit=LIMITE_POR_PAGE,
                page=page,
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("[RENOMEAR] erro list_leads page=%d: %s", page, exc)
            break

        if not leads:
            enquanto_houver = False
            break

        for lead in leads:
            if total_lidos >= max_leads:
                enquanto_houver = False
                break
            total_lidos += 1
            nome_atual = lead.get("name") or ""
            lead_id = lead.get("id")
            if not lead_id:
                continue

            if skip_ja_padronizado and re.match(r"^\[[A-Z]\]\s", nome_atual):
                ja_padronizados += 1
                cat = categorizar_nome(nome_atual)
                por_categoria[cat] = por_categoria.get(cat, 0) + 1
                continue

            cat, novo_nome = gerar_novo_nome(nome_atual)
            por_categoria[cat] = por_categoria.get(cat, 0) + 1
            candidatos.append({
                "id": lead_id,
                "nome_atual": nome_atual[:100],
                "nome_novo": novo_nome,
                "cat": cat,
            })

        if len(leads) < LIMITE_POR_PAGE:
            enquanto_houver = False
        else:
            page += 1

    # Aplica renomeação se NÃO dry_run
    if not dry_run:
        for c in candidatos:
            try:
                ok = _aplicar_nome(kommo_client, c["id"], c["nome_novo"])
                if ok:
                    renomeados += 1
                else:
                    falhas += 1
            except Exception as exc:  # noqa: BLE001
                falhas += 1
                log.warning(
                    "[RENOMEAR] update lead %s falhou: %s", c["id"], exc,
                )

    amostra = candidatos[:20]  # preview dos 20 primeiros

    return {
        "ok": True,
        "total_lidos": total_lidos,
        "ja_padronizados": ja_padronizados,
        "candidatos_pra_renomear": len(candidatos),
        "renomeados": renomeados,
        "falhas": falhas,
        "dry_run": dry_run,
        "por_categoria": por_categoria,
        "amostra_preview": amostra,
    }


def _aplicar_nome(kommo_client, lead_id: int, novo_nome: str) -> bool:
    """PATCH no Kommo pra atualizar só o nome do lead."""
    import httpx
    url = f"{kommo_client._base}/leads/{lead_id}"
    payload = {"name": novo_nome}
    try:
        with httpx.Client(timeout=10.0) as c:
            r = c.patch(url, json=payload, headers=kommo_client._headers)
        if r.status_code // 100 == 2:
            return True
        log.warning(
            "[RENOMEAR] lead %d HTTP %d: %s",
            lead_id, r.status_code, (r.text or "")[:200],
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("[RENOMEAR] lead %d exception: %s", lead_id, exc)
    return False
