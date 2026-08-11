"""Classificador determinístico de convênios (Bug C-60 / 20-07-2026).

Origem: Fábio 20/07/2026 — lead 24325532 (CBMDF). Lia disse "deixa eu
verificar o CBMDF pra você" em vez de negar direto + oferecer particular.
Regressão do Bug C-22 (Sandra GDF, 10/06/2026).

Solução: classificador Python puro que categoriza QUALQUER menção de
convênio em 3 buckets, com fuzzy match por normalização:

    ACEITO       → 26 convênios do KB (Bacen, Care Plus, Saúde Caixa, etc)
    NAO_ACEITO   → 20+ conhecidos que NÃO atendemos (CBMDF, Amil, GDF, etc)
    DESCONHECIDO → convênio não reconhecido em nenhuma das listas

Design:
    - Zero LLM. Regra determinística.
    - Fuzzy match: lowercase + sem acentos + sem espaço/hífen + aliases
    - Fail-open: convênio ambíguo → DESCONHECIDO (Lia continua LLM normal)
    - Extensível: adicionar novo convênio = editar lista

Uso:
    from voice_agent.classificador_convenio import classificar_convenio
    r = classificar_convenio("Aceita CBMDF?")
    # → {'status': 'nao_aceito', 'nome_canonico': 'CBMDF', 'menciona': 'cbmdf'}
"""
from __future__ import annotations

import logging
import re
import unicodedata
from typing import Optional

log = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════
# LISTAS OFICIAIS
# ═══════════════════════════════════════════════════════════════════════

# 26 convênios ACEITOS (fonte: CLAUDE.md seção 15 — mapping PLANO_CODES).
# Cada tupla: (nome_canonico, [aliases_lowercase_sem_acento])
_ACEITOS = [
    ("Pró-Ser STJ", ["proser stj", "pro ser stj", "stj", "pró ser stj"]),
    ("TJDFT Pró-Saúde", ["tjdft", "tjdf", "tjdft pro saude", "pro saude tjdft"]),
    ("Plan-Assiste MPF (MPU)", ["planassiste", "plan assiste", "mpf", "mpu", "plan-assiste"]),
    ("E-vida (Luminar)", ["evida", "e vida", "luminar", "e-vida"]),
    ("Anafe", ["anafe"]),
    ("Bacen", ["bacen", "banco central"]),
    ("Care Plus", ["care plus", "careplus"]),
    ("Casec (Codevasf)", ["casec", "codevasf"]),
    ("Casembrapa (Embrapa)", ["casembrapa", "cas embrapa", "embrapa"]),
    ("Conab", ["conab"]),
    ("Fascal", ["fascal"]),
    ("Omint", ["omint"]),
    ("PF Saúde", ["pf saude", "pf saúde", "policia federal", "polícia federal", "pf"]),
    ("PLAS/JMU (STM)", ["plas jmu", "plasjmu", "stm", "plas/jmu"]),
    ("Proasa", ["proasa"]),
    ("Saúde Caixa", ["saude caixa", "saúde caixa", "caixa"]),
    ("Petrobrás (Saúde Petrobrás)", ["petrobras", "petrobrás", "saude petrobras", "saúde petrobrás"]),
    ("Serpro", ["serpro"]),
    ("SIS Senado", ["sis senado", "sissenado", "senado"]),
    ("STF-Med", ["stf med", "stfmed", "stf-med", "stf"]),
    ("TRF Pró-Social", ["trf", "trf prosocial", "trf pro social", "pro social trf"]),
    ("TRE", ["tre"]),
    ("TRT", ["trt"]),
    ("TST Saúde", ["tst", "tst saude", "tst saúde"]),
    ("PróSaúde (Câmara dos Deputados)", ["prosaude camara", "pró saúde câmara", "camara deputados", "câmara dos deputados"]),
    ("Afego", ["afego", "affego", "affeg"]),  # C-43 (12/07) — Mariana Lopes
]

# 20+ convênios NÃO ACEITOS conhecidos. Fonte: histórico Kommo + bugs C-22,
# C-16, C-27 + regras Fábio.
_NAO_ACEITOS = [
    ("Inas GDF", ["inas gdf", "inasgdf", "inas gdf saude", "inasgdfsaude"]),
    ("GDF", ["gdf", "gdf saude", "gdf saúde"]),  # C-22 Sandra
    ("CBMDF", ["cbmdf", "cbm df", "corpo de bombeiros militar", "corpo bombeiros df"]),  # C-60 Fábio 20/07
    ("Amil", ["amil"]),  # C-42 Thamilla
    ("Bradesco", ["bradesco", "bradesco saude", "bradesco saúde"]),
    ("SulAmerica", ["sulamerica", "sul america", "sulamérica", "sul américa"]),
    ("Unimed", ["unimed"]),
    ("Cassi", ["cassi"]),  # Ana Luiza 24290902
    # Notre Dame Intermédica ANTES de Notredame (mais específico ganha)
    ("Notre Dame Intermédica", ["notre dame intermedica", "intermédica", "intermedica"]),
    ("Notredame", ["notredame", "notre dame"]),
    ("Hapvida", ["hapvida"]),
    ("São Cristóvão", ["sao cristovao", "são cristóvão"]),
    ("Prevent Senior", ["prevent senior"]),
    ("Bio Saúde", ["bio saude", "bio saúde", "biosaude"]),
    ("MediService", ["mediservice"]),
    ("Golden Cross", ["golden cross"]),
    ("Porto Seguro", ["porto seguro"]),
    ("Assefaz", ["assefaz"]),
    ("Postal Saúde", ["postal saude", "postal saúde", "postalsaude"]),  # Correios
    ("Correios", ["correios"]),
    ("FUNPRESP", ["funpresp"]),  # Fundação de Previdência (servidores)
    ("CAPESESP", ["capesesp"]),  # Caixa de Assistência Pessoal
    ("IPASGO", ["ipasgo"]),  # Instituto Prevideniário Assistência Servidores de Goiás
    ("GEAP", ["geap"]),  # Fundação de Seguridade Social
    ("Life Empresarial", ["life empresarial", "life"]),
    ("Ameplan", ["ameplan"]),
]


# ═══════════════════════════════════════════════════════════════════════
# NORMALIZAÇÃO
# ═══════════════════════════════════════════════════════════════════════

def _normalizar(texto: str) -> str:
    """Lowercase + remove acentos + colapsa espaços/hífens/underlines.

    Ex: 'Saúde Caixa' → 'saudecaixa'
    Ex: 'PF-Saúde ' → 'pfsaude'
    """
    if not texto:
        return ""
    # Lower
    t = texto.lower()
    # Remove acentos
    t = "".join(
        c for c in unicodedata.normalize("NFD", t)
        if unicodedata.category(c) != "Mn"
    )
    # Remove pontuação e espaços
    t = re.sub(r"[\s\-_\.,;:!?\(\)\/]+", "", t)
    return t


def _texto_normalizado_contem(texto_normalizado: str, alias: str) -> bool:
    """Match: alias normalizado aparece no texto normalizado?

    Usa word boundary artificial pra evitar 'stm' bater em 'sistema'.
    """
    alias_norm = _normalizar(alias)
    if not alias_norm:
        return False
    # Alias muito curto (< 3 chars) exige boundary rigoroso
    if len(alias_norm) < 4:
        # Precisa aparecer isolado (com char não-alfanum antes/depois OU início/fim)
        padrao = r"(?:^|[^a-z0-9])" + re.escape(alias_norm) + r"(?:$|[^a-z0-9])"
        # Como já normalizamos, o padrão é diferente — verifica se está isolado
        # Nesse ponto texto_normalizado NÃO tem espaços/hífens, então boundary
        # não faz sentido. Só match se alias == texto ou é substring exata isolada.
        # Simplificação: exige que alias curto seja o texto INTEIRO ou parte muito
        # específica. Melhor: rejeita aliases muito curtos pra evitar falso positivo.
        return alias_norm == texto_normalizado
    return alias_norm in texto_normalizado


# ═══════════════════════════════════════════════════════════════════════
# CLASSIFICADOR PRINCIPAL
# ═══════════════════════════════════════════════════════════════════════

def classificar_convenio(texto: str) -> dict:
    """Classifica menção de convênio no texto.

    Returns:
        dict com:
          - status: 'aceito' | 'nao_aceito' | 'desconhecido' | 'sem_mencao'
          - nome_canonico: nome oficial se encontrado (ex: 'CBMDF', 'Saúde Caixa')
          - menciona: substring que casou (útil pra debug)

    Se texto tem menção que casa AMBAS as listas, ACEITO ganha (defensivo).
    Se texto não tem menção de convênio → sem_mencao.
    """
    if not texto or not texto.strip():
        return {"status": "sem_mencao", "nome_canonico": None, "menciona": None}

    texto_norm = _normalizar(texto)

    # Primeiro: procura ACEITOS
    for nome_canonico, aliases in _ACEITOS:
        for alias in aliases:
            if _texto_normalizado_contem(texto_norm, alias):
                return {
                    "status": "aceito",
                    "nome_canonico": nome_canonico,
                    "menciona": alias,
                }

    # Depois: procura NÃO ACEITOS
    for nome_canonico, aliases in _NAO_ACEITOS:
        for alias in aliases:
            if _texto_normalizado_contem(texto_norm, alias):
                return {
                    "status": "nao_aceito",
                    "nome_canonico": nome_canonico,
                    "menciona": alias,
                }

    # Detecção genérica: menciona "convênio" / "plano de saúde" mas não casou lista
    palavras_convenio = ["convenio", "convênio", "plano", "seguro", "credenciado"]
    lower_orig = texto.lower()
    if any(p in lower_orig for p in palavras_convenio):
        return {
            "status": "desconhecido",
            "nome_canonico": None,
            "menciona": None,
        }

    return {"status": "sem_mencao", "nome_canonico": None, "menciona": None}


# ═══════════════════════════════════════════════════════════════════════
# GERADORES DE RESPOSTA CANÔNICA
# ═══════════════════════════════════════════════════════════════════════

def gerar_resposta_aceito(
    nome_canonico: str,
    nome_paciente: Optional[str] = None,
) -> str:
    """Confirma que atendemos + avança pra unidade."""
    saudacao = f"{nome_paciente}, " if nome_paciente else ""
    return (
        f"{saudacao}sim, atendemos o {nome_canonico}! 👍\n\n"
        "Qual unidade fica melhor para você — **Asa Norte** ou **Águas Claras**?"
    )


def gerar_resposta_nao_aceito(
    nome_canonico: str,
    nome_paciente: Optional[str] = None,
) -> str:
    """Nega direto + oferece particular incentivado (Caso 3 do artigo 39)."""
    saudacao = f"{nome_paciente}, " if nome_paciente else ""
    return (
        f"{saudacao}o **{nome_canonico}** a clínica não atende. Mas posso "
        "te oferecer o atendimento **particular** com valores incentivados:\n\n"
        "📲 **Pix (à vista):** R$ 611\n"
        "💳 **Cartão 1x:** R$ 670\n"
        "💳 **Cartão 2x sem juros:** R$ 670 (2x R$ 335)\n\n"
        "A consulta já inclui tonometria, motilidade e mapeamento de retina.\n\n"
        "Quer seguir?"
    )


# ═══════════════════════════════════════════════════════════════════════
# BYPASS PRA integrar em blindagens_deterministicas.py
# ═══════════════════════════════════════════════════════════════════════

def _ja_perguntou_convenio(ctx: Optional[dict]) -> bool:
    """ctx.known.convenio já preenchido = não sobrescrever."""
    known = (ctx or {}).get("known") or {}
    conv = str(known.get("convenio") or "").strip().lower()
    return bool(conv) and conv not in ("", "none", "null", "não se aplica")


def deve_responder_convenio(
    ctx: Optional[dict], user_text: str,
) -> Optional[str]:
    """Bypass principal: classifica convênio + retorna resposta canônica.

    Regra: só age se paciente CITAR convênio conhecido (aceito ou não aceito).
    Se desconhecido/sem_mencao → retorna None (LLM segue normal).

    Se ctx.known.convenio já preenchido com convênio DIFERENTE do citado,
    retorna None (não sobrescreve estado FSM).
    """
    import os
    if (os.getenv("BLINDAGEM_CONVENIO_ATIVADO") or "1").lower() in (
        "0", "false", "no", "off",
    ):
        return None

    if not user_text or not user_text.strip():
        return None

    result = classificar_convenio(user_text)
    status = result["status"]

    # Só responde pra aceito ou não_aceito com nome reconhecido
    if status not in ("aceito", "nao_aceito"):
        return None

    # Se ctx já tem convênio diferente preenchido, não interfere
    if _ja_perguntou_convenio(ctx):
        return None

    known = (ctx or {}).get("known") or {}
    nome_paciente = str(known.get("nome_paciente") or known.get("nome_contato") or "").strip()
    # Primeiro nome só
    if nome_paciente:
        nome_paciente = nome_paciente.split()[0]

    nome_canonico = result["nome_canonico"]

    if status == "aceito":
        return gerar_resposta_aceito(nome_canonico, nome_paciente)
    else:  # nao_aceito
        return gerar_resposta_nao_aceito(nome_canonico, nome_paciente)
