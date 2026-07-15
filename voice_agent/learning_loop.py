"""Learning Loop Automático — fecha o ciclo de aprendizagem sem intervenção manual.

3 peças:

1. `detectar_correcao_humana(lead_id, kommo_client)` — parseia notas do lead,
   detecta se humano corrigiu Lia em janela recente.

2. `append_bug_no_claude_md(correcao, arquivo)` — adiciona entrada nova no
   CLAUDE.md no formato "### 0. (DATA) Bug auto-detectado C-AUTO-NNN".

3. `re_indexar_se_mudou(arquivo)` — checa mtime do CLAUDE.md. Se mudou desde
   última indexação, invalida cache do memoria_rag → próxima busca re-carrega.

Uso end-to-end:
    from voice_agent import learning_loop
    resultado = learning_loop.processar_lead(lead_id, kommo_client)
    # {'detectou': True, 'bug_id': 'C-AUTO-042', 'appendou': True, ...}

Toggle: LEARNING_LOOP_ATIVADO (default ON, off com "0").
"""
from __future__ import annotations

import logging
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
ARQUIVO_CLAUDE_MD = _PROJECT_ROOT / "CLAUDE.md"

# Padrões que indicam correção humana explícita (regex insensitive)
_PADROES_CORRECAO = re.compile(
    r"("
    r"n[aã]o\s+[eé]\s+(?:assim|isso)"
    r"|Lia,?\s+(?:n[aã]o|corrig|cuidado|para)"
    r"|corrigindo\s+(?:a\s+)?Lia"
    r"|(?:ela\s+)?(?:est[aá]|esta)\s+errad"
    r"|forma\s+correta\s+[eé]"
    r"|o\s+correto\s+[eé]"
    r"|nunca\s+(?:diga|diz|escreva)"
    r"|regra\s+correta"
    r"|erro\s+da?\s+Lia"
    r")",
    re.IGNORECASE,
)

# Janela: se humano escreveu logo depois da Lia, considera "resposta correcional"
JANELA_CORRECAO_SEG = 15 * 60  # 15min


def _ativado() -> bool:
    return (os.getenv("LEARNING_LOOP_ATIVADO") or "1").lower() not in (
        "0", "false", "no", "off",
    )


# ═══════════════════════════════════════════════════════════════════════
# PEÇA 1 — Detector de correção humana
# ═══════════════════════════════════════════════════════════════════════

def _eh_nota_lia(nota: dict) -> bool:
    """Nota da Lia: created_by == 0 (bot)."""
    return int(nota.get("created_by", 0) or 0) == 0


def _eh_nota_humana(nota: dict) -> bool:
    """Nota de humano: created_by != 0."""
    return int(nota.get("created_by", 0) or 0) != 0


def _texto_nota(nota: dict) -> str:
    """Extrai texto da nota (formato Kommo tem várias variantes)."""
    if isinstance(nota.get("text"), str):
        return nota["text"]
    # Formato params.text
    params = nota.get("params") or {}
    return str(params.get("text") or "")


def detectar_correcao_humana(
    lead_id: int | str,
    kommo_client: Any,
    janela_seg: int = JANELA_CORRECAO_SEG,
) -> Optional[dict]:
    """Detecta correção humana recente. Retorna dict ou None.

    Heurística: procura par (Lia outbound → humano outbound no mesmo lead
    em <15min) OU nota humana contendo padrões de correção explícita.

    Returns:
        None se nada detectado
        dict {
            'resposta_lia': str,     # o que Lia disse
            'correcao_humana': str,  # o que humano disse depois
            'lead_id': int,
            'ts_lia': float,
            'ts_humano': float,
            'padrao_explicito': bool,  # True se pegou regex de correção
        }
    """
    if not _ativado():
        return None

    try:
        notas = kommo_client.get_lead_notes(lead_id, limit=30) or []
    except Exception as e:  # noqa: BLE001
        log.warning("[LEARNING] Falha ao ler notas lead=%s: %s", lead_id, e)
        return None

    if len(notas) < 2:
        return None

    # Notas vêm desc (mais recentes primeiro). Reverte pra ordem cronológica.
    notas_cron = list(reversed(notas))

    for i in range(len(notas_cron) - 1):
        n1 = notas_cron[i]
        n2 = notas_cron[i + 1]

        if not _eh_nota_lia(n1):
            continue
        if not _eh_nota_humana(n2):
            continue

        ts1 = float(n1.get("created_at", 0) or 0)
        ts2 = float(n2.get("created_at", 0) or 0)
        if ts2 - ts1 > janela_seg or ts2 - ts1 < 0:
            continue

        texto_lia = _texto_nota(n1)
        texto_humano = _texto_nota(n2)

        if not texto_lia or not texto_humano:
            continue

        padrao_match = bool(_PADROES_CORRECAO.search(texto_humano))

        # Retorna se: (a) regex de correção casou OU
        # (b) humano escreveu resposta LONGA (>40 chars) logo após Lia
        # (indicando que o humano "assumiu" o atendimento — sinal de bug)
        if padrao_match or len(texto_humano) > 40:
            return {
                "resposta_lia": texto_lia,
                "correcao_humana": texto_humano,
                "lead_id": int(lead_id) if str(lead_id).isdigit() else lead_id,
                "ts_lia": ts1,
                "ts_humano": ts2,
                "padrao_explicito": padrao_match,
            }

    return None


# ═══════════════════════════════════════════════════════════════════════
# PEÇA 2 — Auto-append no CLAUDE.md
# ═══════════════════════════════════════════════════════════════════════

def _proximo_bug_auto_id(arquivo: Path) -> str:
    """Descobre próximo C-AUTO-NNN disponível."""
    if not arquivo.exists():
        return "C-AUTO-001"
    texto = arquivo.read_text(encoding="utf-8", errors="ignore")
    ids = re.findall(r"C-AUTO-(\d+)", texto)
    if not ids:
        return "C-AUTO-001"
    proximo = max(int(i) for i in ids) + 1
    return f"C-AUTO-{proximo:03d}"


def gerar_entrada_bug_auto(correcao: dict, bug_id: Optional[str] = None) -> str:
    """Gera bloco markdown pra CLAUDE.md."""
    if bug_id is None:
        bug_id = _proximo_bug_auto_id(ARQUIVO_CLAUDE_MD)

    data = datetime.now(timezone.utc).astimezone().strftime("%d/%m/%Y")

    resposta_lia = str(correcao.get("resposta_lia", ""))[:500]
    correcao_humana = str(correcao.get("correcao_humana", ""))[:500]
    lead_id = correcao.get("lead_id", "N/A")

    tag_padrao = "PADRÃO EXPLÍCITO" if correcao.get("padrao_explicito") else "handoff"

    entrada = f"""
### 0. ({data}) Bug auto-detectado {bug_id} — Learning Loop (lead {lead_id})

**Origem:** captura automática via `learning_loop.detectar_correcao_humana` ({tag_padrao}).

**Resposta da Lia (problemática):**
> {resposta_lia}

**Correção/resposta humana (padrão a seguir):**
> {correcao_humana}

**Contexto:** lead {lead_id}, correção humana em janela <15min após Lia.

**Regra:** Lia deve evitar o padrão da resposta problemática e adotar o tom/conteúdo da correção humana quando contexto for similar.

**Ação:** revisar em auditoria semanal se esse padrão recorre. Se sim, promover pra filtro reativo em `responder.py::_scrub_prohibited`.
"""
    return entrada.strip()


def append_bug_no_claude_md(
    entrada: str,
    arquivo: Path = ARQUIVO_CLAUDE_MD,
) -> bool:
    """Adiciona entrada nova no topo da seção 0 do CLAUDE.md.

    Insere logo após a linha "## 0. ÚLTIMAS 5 LIÇÕES DURAS — LER PRIMEIRO".
    Retorna True em sucesso.
    """
    if not arquivo.exists():
        log.warning("[LEARNING] CLAUDE.md não encontrado em %s", arquivo)
        return False

    try:
        texto = arquivo.read_text(encoding="utf-8")
        marcador = "## 0. ÚLTIMAS 5 LIÇÕES DURAS"
        idx = texto.find(marcador)
        if idx < 0:
            # Fallback: append no final
            log.warning("[LEARNING] Marcador não achado, appendo no final")
            arquivo.write_text(texto + "\n\n" + entrada + "\n", encoding="utf-8")
            return True

        # Encontra fim da linha do marcador
        fim_linha = texto.find("\n", idx)
        if fim_linha < 0:
            fim_linha = len(texto)

        # Insere logo após o header + 1 linha em branco
        novo_texto = (
            texto[:fim_linha + 1]
            + "\n"
            + entrada
            + "\n\n"
            + texto[fim_linha + 1:]
        )
        arquivo.write_text(novo_texto, encoding="utf-8")
        return True
    except Exception as e:  # noqa: BLE001
        log.warning("[LEARNING] Falha append CLAUDE.md: %s", e)
        return False


# ═══════════════════════════════════════════════════════════════════════
# PEÇA 3 — Re-index em tempo real (mtime check)
# ═══════════════════════════════════════════════════════════════════════

_ULTIMO_MTIME_CLAUDE_MD: dict[str, float] = {"mtime": 0.0}


def re_indexar_se_mudou(arquivo: Path = ARQUIVO_CLAUDE_MD) -> bool:
    """Checa mtime do CLAUDE.md. Se mudou, invalida cache RAG.

    Retorna True se invalidou (arquivo mudou), False se não precisou.
    """
    if not arquivo.exists():
        return False
    try:
        mtime_atual = arquivo.stat().st_mtime
        mtime_ultimo = _ULTIMO_MTIME_CLAUDE_MD["mtime"]
        if mtime_atual > mtime_ultimo:
            _ULTIMO_MTIME_CLAUDE_MD["mtime"] = mtime_atual
            # Invalida cache do memoria_rag
            try:
                from voice_agent import memoria_rag
                memoria_rag.limpar_cache()
                log.info(
                    "[LEARNING] CLAUDE.md mudou (mtime=%.0f). "
                    "Cache RAG invalidado.",
                    mtime_atual,
                )
            except Exception as e:  # noqa: BLE001
                log.warning("[LEARNING] Falha invalidar cache RAG: %s", e)
            return True
        return False
    except Exception as e:  # noqa: BLE001
        log.warning("[LEARNING] Falha check mtime CLAUDE.md: %s", e)
        return False


# ═══════════════════════════════════════════════════════════════════════
# ORQUESTRADOR — chamado pelo pipeline em handoff humano
# ═══════════════════════════════════════════════════════════════════════

def processar_lead(
    lead_id: int | str,
    kommo_client: Any,
    dedup_redis: Optional[Any] = None,
) -> dict:
    """Fluxo end-to-end pra um lead.

    Sequência:
    1. Detecta correção humana nas notas
    2. Se detectou, gera entrada + append no CLAUDE.md
    3. Invalida cache RAG (próxima busca já pega novo bug)
    4. Dedup Redis: só processa mesmo lead 1x/24h

    Retorna dict com resultado detalhado.
    """
    resultado = {
        "detectou": False,
        "appendou": False,
        "reindexou": False,
        "bug_id": None,
        "erro": None,
        "dedup_pulou": False,
    }

    if not _ativado():
        resultado["erro"] = "toggle_off"
        return resultado

    # Dedup: 1 correção por lead por 24h
    if dedup_redis is not None:
        try:
            chave = f"blink:learning_loop:{lead_id}"
            if dedup_redis.get(chave):
                resultado["dedup_pulou"] = True
                return resultado
            dedup_redis.setex(chave, 86400, "1")
        except Exception:  # noqa: BLE001
            pass  # dedup best-effort

    # 1. Detectar
    try:
        correcao = detectar_correcao_humana(lead_id, kommo_client)
    except Exception as e:  # noqa: BLE001
        resultado["erro"] = f"detect_failed: {e}"
        return resultado

    if correcao is None:
        return resultado

    resultado["detectou"] = True

    # 2. Gerar entrada + append
    # Lê arquivo dinâmicamente pra permitir monkeypatch em testes
    from voice_agent import learning_loop as _self
    arquivo = _self.ARQUIVO_CLAUDE_MD
    try:
        bug_id = _proximo_bug_auto_id(arquivo)
        entrada = gerar_entrada_bug_auto(correcao, bug_id=bug_id)
        ok_append = append_bug_no_claude_md(entrada, arquivo)
        resultado["appendou"] = ok_append
        resultado["bug_id"] = bug_id
    except Exception as e:  # noqa: BLE001
        resultado["erro"] = f"append_failed: {e}"
        return resultado

    # 3. Re-indexar RAG
    try:
        resultado["reindexou"] = re_indexar_se_mudou(arquivo)
    except Exception as e:  # noqa: BLE001
        log.warning("[LEARNING] reindex falhou: %s", e)

    log.info(
        "[LEARNING] Lead %s: correção capturada como %s "
        "(append=%s, reindex=%s)",
        lead_id, resultado["bug_id"],
        resultado["appendou"], resultado["reindexou"],
    )
    return resultado
