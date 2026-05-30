"""Agrupadores de procedimentos por faixa etária e motivo da consulta.

Conceito definido pela Blink em 30/05/2026: secretaria escolhe UM agrupador
em vez de selecionar exame por exame. Reduz tempo operacional e evita
esquecimento de exames obrigatórios do protocolo.

Os 4 agrupadores combinam dois eixos:

| Faixa etária       | Rotina            | Emergência/Urgência |
|--------------------|-------------------|---------------------|
| ≥ 3 anos           | AGRUPADOR_1       | AGRUPADOR_2         |
| < 3 anos           | AGRUPADOR_3       | AGRUPADOR_4         |

Cada agrupador é uma lista de codProcedimento Medware. Quando a Lia grava
o agendamento, ela seleciona automaticamente o agrupador baseado em:
  - Idade do paciente (calculada a partir de data_nascimento)
  - Motivo da consulta (extraído pelo Haiku: "rotina" vs "urgência")
"""
from __future__ import annotations

from datetime import date


# ============================================================
# CÓDIGOS DE PROCEDIMENTO (cadastrados no Medware)
# ============================================================

PROC_MAPEAMENTO_RETINA = 41301250         # Mapeamento de Retina Ambos Olhos
PROC_PAQUIMETRIA = 41501128               # Paquimetria Ultrassônica AO
PROC_BIOMETRIA = 41501012                 # Biometria Ultrassônica AO
PROC_MOTILIDADE = 41301200                # Exame de Motilidade
PROC_TONOMETRIA = 41301323                # Tonometria
PROC_RETINOGRAFIA_MONOCULAR = 41301315    # Retinografia Monocular AO
PROC_CERATOSCOPIA = 41301080              # Ceratoscopia Computadorizada AO
PROC_TESTE_CORES = 41401271               # Teste de Cores AO
PROC_MICROSCOPIA_ESPECULAR = 41301269     # Microscopia Especular de Córnea


# Nomes legíveis (para log + Kommo nota + Medware OBS)
PROC_NOMES = {
    PROC_MAPEAMENTO_RETINA: "Mapeamento de Retina AO",
    PROC_PAQUIMETRIA: "Paquimetria Ultrassônica AO",
    PROC_BIOMETRIA: "Biometria Ultrassônica AO",
    PROC_MOTILIDADE: "Exame de Motilidade",
    PROC_TONOMETRIA: "Tonometria",
    PROC_RETINOGRAFIA_MONOCULAR: "Retinografia Monocular AO",
    PROC_CERATOSCOPIA: "Ceratoscopia Computadorizada AO",
    PROC_TESTE_CORES: "Teste de Cores AO",
    PROC_MICROSCOPIA_ESPECULAR: "Microscopia Especular de Córnea",
}


# ============================================================
# OS 4 AGRUPADORES
# ============================================================

# Agrupador 1 — Paciente ≥ 3 anos, consulta de ROTINA
# (9 exames — protocolo completo de rotina adulto/criança maior)
AGRUPADOR_ADULTO_ROTINA: list[int] = [
    PROC_MAPEAMENTO_RETINA,
    PROC_PAQUIMETRIA,
    PROC_BIOMETRIA,
    PROC_MOTILIDADE,
    PROC_TONOMETRIA,
    PROC_RETINOGRAFIA_MONOCULAR,
    PROC_CERATOSCOPIA,
    PROC_TESTE_CORES,
    PROC_MICROSCOPIA_ESPECULAR,
]

# Agrupador 2 — Paciente ≥ 3 anos, consulta de EMERGÊNCIA
# (6 exames — pula mapeamento, retinografia e teste de cores)
AGRUPADOR_ADULTO_EMERGENCIA: list[int] = [
    PROC_PAQUIMETRIA,
    PROC_BIOMETRIA,
    PROC_MOTILIDADE,
    PROC_TONOMETRIA,
    PROC_CERATOSCOPIA,
    PROC_MICROSCOPIA_ESPECULAR,
]

# Agrupador 3 — Paciente < 3 anos, consulta de ROTINA
# (6 exames — pula ceratoscopia, teste de cores e microscopia)
AGRUPADOR_CRIANCA_ROTINA: list[int] = [
    PROC_MAPEAMENTO_RETINA,
    PROC_PAQUIMETRIA,
    PROC_BIOMETRIA,
    PROC_MOTILIDADE,
    PROC_TONOMETRIA,
    PROC_RETINOGRAFIA_MONOCULAR,
]

# Agrupador 4 — Paciente < 3 anos, consulta de URGÊNCIA
# (5 exames — pula mapeamento)
AGRUPADOR_CRIANCA_URGENCIA: list[int] = [
    PROC_PAQUIMETRIA,
    PROC_BIOMETRIA,
    PROC_MOTILIDADE,
    PROC_TONOMETRIA,
    PROC_RETINOGRAFIA_MONOCULAR,
]


# Identificadores legíveis dos agrupadores
AGRUPADORES: dict[str, list[int]] = {
    "AGRUPADOR_1_ADULTO_ROTINA": AGRUPADOR_ADULTO_ROTINA,
    "AGRUPADOR_2_ADULTO_EMERGENCIA": AGRUPADOR_ADULTO_EMERGENCIA,
    "AGRUPADOR_3_CRIANCA_ROTINA": AGRUPADOR_CRIANCA_ROTINA,
    "AGRUPADOR_4_CRIANCA_URGENCIA": AGRUPADOR_CRIANCA_URGENCIA,
}


# ============================================================
# LÓGICA DE SELEÇÃO
# ============================================================

# Faixas etárias do Kommo (PERFIL 1º PACIENTE) — quais contam como "< 3 anos"
KOMMO_PERFIL_MENOR_DE_3 = {"Bebê de 0 a 2 anos"}
KOMMO_PERFIL_MAIOR_OU_IGUAL_3 = {
    "Criança de 3 a 12 anos",
    "Adolescente de 13 a 18 anos",
    "Adulto de 19 a 49",
    "Acima de 50 anos",
}

# Palavras-chave que indicam consulta de EMERGÊNCIA/URGÊNCIA
# (extraídas do motivo livre que paciente escreveu)
PALAVRAS_URGENCIA = {
    "urgente", "urgencia", "urgência",
    "emergencia", "emergência",
    "dor forte", "muita dor",
    "trauma", "machucou", "bateu", "acidente",
    "perdi a visao", "perdi a visão",
    "nao enxergo", "não enxergo",
    "sangrando", "sangramento",
    "objeto no olho", "corpo estranho",
    "queimadura",
}


def is_menor_de_3(perfil_kommo: str | None = None,
                  birth_date_iso: str | None = None,
                  hoje: date | None = None) -> bool:
    """Decide se o paciente tem menos de 3 anos.

    Aceita 2 fontes:
      - perfil_kommo: o que está no campo "PERFIL 1º PACIENTE" do Kommo
      - birth_date_iso: data de nascimento "YYYY-MM-DD"

    Se ambos disponíveis, prioriza a data calculada.
    """
    if birth_date_iso:
        try:
            yyyy, mm, dd = birth_date_iso[:10].split("-")
            nasc = date(int(yyyy), int(mm), int(dd))
            ref = hoje or date.today()
            anos = (
                ref.year - nasc.year
                - ((ref.month, ref.day) < (nasc.month, nasc.day))
            )
            return anos < 3
        except (ValueError, IndexError):
            pass
    if perfil_kommo:
        return perfil_kommo.strip() in KOMMO_PERFIL_MENOR_DE_3
    return False


def is_urgencia(motivo: str | None) -> bool:
    """Decide se o motivo descrito é uma consulta de urgência/emergência.

    Match case-insensitive em palavras-chave conhecidas. Se nenhuma bater,
    assume rotina (caso mais comum).
    """
    if not motivo:
        return False
    m = motivo.lower()
    return any(palavra in m for palavra in PALAVRAS_URGENCIA)


def selecionar_agrupador(
    *,
    perfil_kommo: str | None = None,
    birth_date_iso: str | None = None,
    motivo: str | None = None,
    hoje: date | None = None,
) -> tuple[str, list[int]]:
    """Seleciona o agrupador correto baseado em idade + motivo.

    Retorna (nome_do_agrupador, lista_de_codProcedimentos).

    Exemplos:
        >>> nome, procs = selecionar_agrupador(
        ...     birth_date_iso="2020-06-01",
        ...     motivo="consulta de rotina",
        ... )
        >>> nome
        'AGRUPADOR_3_CRIANCA_ROTINA'

        >>> nome, procs = selecionar_agrupador(
        ...     perfil_kommo="Acima de 50 anos",
        ...     motivo="urgência: dor forte no olho direito",
        ... )
        >>> nome
        'AGRUPADOR_2_ADULTO_EMERGENCIA'
    """
    crianca = is_menor_de_3(perfil_kommo, birth_date_iso, hoje)
    urgencia = is_urgencia(motivo)

    if crianca and urgencia:
        return ("AGRUPADOR_4_CRIANCA_URGENCIA", AGRUPADOR_CRIANCA_URGENCIA)
    if crianca and not urgencia:
        return ("AGRUPADOR_3_CRIANCA_ROTINA", AGRUPADOR_CRIANCA_ROTINA)
    if not crianca and urgencia:
        return ("AGRUPADOR_2_ADULTO_EMERGENCIA", AGRUPADOR_ADULTO_EMERGENCIA)
    return ("AGRUPADOR_1_ADULTO_ROTINA", AGRUPADOR_ADULTO_ROTINA)
