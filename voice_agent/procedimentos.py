"""Agrupadores de procedimentos por faixa etária e motivo da consulta.

REGRA DE NEGÓCIO BLINK (definida 30/05/2026):
  A clínica SÓ FAZ consulta + exame completo. Não existe "só consulta
  avulsa". Logo, TODO agendamento usa exatamente UM dos 4 agrupadores —
  sem opção "Personalizado", sem fallback, sem exceção.

Os 4 agrupadores combinam dois eixos:

| Faixa etária       | Rotina            | Emergência/Urgência |
|--------------------|-------------------|---------------------|
| ≥ 3 anos           | AGRUPADOR_1       | AGRUPADOR_2         |
| < 3 anos           | AGRUPADOR_3       | AGRUPADOR_4         |

Cada agrupador é uma lista de codProcedimento Medware. Quando a Lia grava
o agendamento, ela seleciona automaticamente o agrupador baseado em:
  - Idade do paciente (calculada a partir de data_nascimento)
  - Tipo de motivo (enum "1.TIPO MOTIVO" no Kommo, preferencial)
  - OU motivo livre (extraído pelo Haiku: "rotina" vs "urgência")
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

# Mapeamento agrupador → label exato do enum no Kommo "N.EXAMES"
# (usado pelo kommo.update_lead_fields pra preencher os campos novos
# criados em 31/05/2026).
AGRUPADOR_KOMMO_LABEL: dict[str, str] = {
    "AGRUPADOR_1_ADULTO_ROTINA": "Agrupa1-Adulto Rotina (9 exames)",
    "AGRUPADOR_2_ADULTO_EMERGENCIA": "Agrupa2-Adulto Emergência (6 exames)",
    "AGRUPADOR_3_CRIANCA_ROTINA": "Agrupa3-Criança Rotina (6 exames)",
    "AGRUPADOR_4_CRIANCA_URGENCIA": "Agrupa4-Criança Urgência(5 exames)",
}

# Label do enum "Personalizado" — quando atendente humano escolheu
# manualmente, em vez da seleção automática pela Lia.
AGRUPADOR_KOMMO_PERSONALIZADO = "Agrupa5-Personalizado (escolha manual)"

# Nome interno do agrupador → lista de codProcedimento. Usado pela
# auditoria (task #82) pra reconstruir o PLANEJADO a partir do N.EXAMES
# lido do Kommo.
AGRUPADOR_NOME_CODIGOS: dict[str, list[int]] = {
    "AGRUPADOR_1_ADULTO_ROTINA": AGRUPADOR_ADULTO_ROTINA,
    "AGRUPADOR_2_ADULTO_EMERGENCIA": AGRUPADOR_ADULTO_EMERGENCIA,
    "AGRUPADOR_3_CRIANCA_ROTINA": AGRUPADOR_CRIANCA_ROTINA,
    "AGRUPADOR_4_CRIANCA_URGENCIA": AGRUPADOR_CRIANCA_URGENCIA,
}

# Reverso do label do enum N.EXAMES → nome interno do agrupador.
_KOMMO_LABEL_PARA_NOME: dict[str, str] = {
    label: nome for nome, label in AGRUPADOR_KOMMO_LABEL.items()
}


def codigos_por_label_kommo(label: str | None) -> tuple[str, list[int]]:
    """Inverso de agrupador_label_kommo: label do N.EXAMES → (nome, códigos).

    Usado pela auditoria pra reconstruir o conjunto PLANEJADO a partir do
    que está gravado no Kommo. "Personalizado"/desconhecido → ("", []) —
    a auditoria trata como fonte indefinida (não inventa procedimentos).
    """
    if not label:
        return ("", [])
    nome = _KOMMO_LABEL_PARA_NOME.get(label.strip())
    if not nome:
        return ("", [])
    return (nome, list(AGRUPADOR_NOME_CODIGOS.get(nome, [])))


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


# Enums padronizados do novo campo "1.TIPO MOTIVO" no Kommo (a ser criado).
# Quando preenchido, prevalece sobre detecção por palavra-chave.
KOMMO_TIPO_MOTIVO_URGENCIA = {
    "Emergência / Urgência",
    "Emergencia / Urgencia",
    "Emergência",
    "Urgência",
}
KOMMO_TIPO_MOTIVO_ROTINA = {
    "Rotina / Check-up",
    "Rotina / Check up",
    "Rotina",
    "Check-up",
    "Retorno / Acompanhamento",
    "Acompanhamento",
    "Pré-operatório",
    "Pós-operatório",
}


def is_urgencia(motivo: str | None,
                tipo_motivo_kommo: str | None = None) -> bool:
    """Decide se a consulta é de urgência/emergência.

    Prioridade:
      1. `tipo_motivo_kommo` — enum do campo "1.TIPO MOTIVO" (preferido,
         sem ambiguidade).
      2. `motivo` — texto livre do campo "1.MOTIVO CONSULTA" — match em
         palavras-chave conhecidas.

    Se nenhuma fonte indica urgência, assume rotina (caso mais comum).
    """
    if tipo_motivo_kommo:
        clean = tipo_motivo_kommo.strip()
        if clean in KOMMO_TIPO_MOTIVO_URGENCIA:
            return True
        if clean in KOMMO_TIPO_MOTIVO_ROTINA:
            return False
        # Enum desconhecido → cai pro fallback de palavra-chave
    if not motivo:
        return False
    m = motivo.lower()
    return any(palavra in m for palavra in PALAVRAS_URGENCIA)


# ============================================================
# CLASSIFICAÇÃO N.MOTIVO (5 categorias) — task #80
# ============================================================
# Labels EXATOS do enum "N.MOTIVO" no Kommo (FIELD_MOTIVO_TIPO_PACIENTES).
# Estes textos têm que casar com _pick_enum em kommo.py (case/acento
# insensitive), então mantemos a grafia idêntica à tabela de enum.
MOTIVO_TIPO_ROTINA = "Rotina/Check-up"
MOTIVO_TIPO_RETORNO = "Retorno/Acompanhamento"
MOTIVO_TIPO_PRE_OP = "Pré-operatório"
MOTIVO_TIPO_URGENCIA = "Emergência/Urgência"
MOTIVO_TIPO_POS_OP = "Pós-Operatório"

# Palavras-chave por categoria (sobre o texto livre do motivo).
_PALAVRAS_POS_OP = {
    "pos-op", "pós-op", "pos op", "pós op",
    "pos-operatorio", "pós-operatório", "pos operatorio", "pós operatório",
    "depois da cirurgia", "depois da operacao", "depois da operação",
    "pos cirurgia", "pós cirurgia", "retorno da cirurgia", "ja operei",
    "já operei", "operei", "fiz a cirurgia", "fiz cirurgia",
}
_PALAVRAS_PRE_OP = {
    "pre-op", "pré-op", "pre op", "pré op",
    "pre-operatorio", "pré-operatório", "pre operatorio", "pré operatório",
    "antes da cirurgia", "avaliacao cirurgica", "avaliação cirúrgica",
    "vou operar", "pre cirurgico", "pré-cirúrgico", "pre-cirurgico",
    "avaliacao pre operatoria", "avaliação pré operatória",
}
_PALAVRAS_RETORNO = {
    "retorno", "acompanhamento", "revisao", "revisão",
    "reavaliacao", "reavaliação", "ja consultei", "já consultei",
    "controle", "rever", "mostrar exame", "trazer exame",
    "resultado de exame", "resultado do exame",
}


def classificar_motivo_tipo_kommo(
    motivo: str | None,
    tipo_motivo_kommo: str | None = None,
) -> str:
    """Classifica o motivo livre numa das 5 categorias do enum N.MOTIVO.

    Retorna sempre um dos cinco labels (default: Rotina/Check-up).

    Prioridade:
      1. `tipo_motivo_kommo` — se já vier num dos 5 labels conhecidos,
         respeita (atendente humano classificou).
      2. urgência (reaproveita `is_urgencia`, que cobre palavras-chave).
      3. pós-operatório > pré-operatório > retorno (mais específico antes).
      4. fallback: rotina (caso mais comum).
    """
    # 1) Enum explícito já classificado.
    if tipo_motivo_kommo:
        clean = tipo_motivo_kommo.strip()
        for label in (
            MOTIVO_TIPO_ROTINA, MOTIVO_TIPO_RETORNO, MOTIVO_TIPO_PRE_OP,
            MOTIVO_TIPO_URGENCIA, MOTIVO_TIPO_POS_OP,
        ):
            if clean.lower() == label.lower():
                return label

    # 2) Urgência tem prioridade absoluta (segurança clínica).
    if is_urgencia(motivo, tipo_motivo_kommo):
        return MOTIVO_TIPO_URGENCIA

    m = (motivo or "").lower()
    # 3) Pós antes de pré (quem já operou não é mais pré-op).
    if any(p in m for p in _PALAVRAS_POS_OP):
        return MOTIVO_TIPO_POS_OP
    if any(p in m for p in _PALAVRAS_PRE_OP):
        return MOTIVO_TIPO_PRE_OP
    if any(p in m for p in _PALAVRAS_RETORNO):
        return MOTIVO_TIPO_RETORNO

    # 4) Default.
    return MOTIVO_TIPO_ROTINA


def agrupador_label_kommo(nome_agrupador: str | None) -> str:
    """Converte o nome interno do agrupador no label do enum N.EXAMES.

    Desconhecido/None → label "Personalizado" (escolha manual humana).
    """
    if not nome_agrupador:
        return AGRUPADOR_KOMMO_PERSONALIZADO
    return AGRUPADOR_KOMMO_LABEL.get(
        nome_agrupador, AGRUPADOR_KOMMO_PERSONALIZADO,
    )


def selecionar_agrupador(
    *,
    perfil_kommo: str | None = None,
    birth_date_iso: str | None = None,
    motivo: str | None = None,
    tipo_motivo_kommo: str | None = None,
    agrupador_manual_kommo: str | None = None,
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
    # 1) Override manual: se atendente humano escolheu agrupador no Kommo
    #    (campo "1.AGRUPADOR EXAMES" a ser criado), respeita sem reavaliar.
    if agrupador_manual_kommo:
        clean = agrupador_manual_kommo.strip().lower()
        if "adulto" in clean and "rotina" in clean:
            return ("AGRUPADOR_1_ADULTO_ROTINA", AGRUPADOR_ADULTO_ROTINA)
        if "adulto" in clean and (
            "emerg" in clean or "urg" in clean
        ):
            return (
                "AGRUPADOR_2_ADULTO_EMERGENCIA",
                AGRUPADOR_ADULTO_EMERGENCIA,
            )
        if (
            ("crianca" in clean or "criança" in clean or "bebê" in clean
             or "bebe" in clean)
            and "rotina" in clean
        ):
            return ("AGRUPADOR_3_CRIANCA_ROTINA", AGRUPADOR_CRIANCA_ROTINA)
        if (
            ("crianca" in clean or "criança" in clean or "bebê" in clean
             or "bebe" in clean)
            and (
                "emerg" in clean or "urg" in clean
            )
        ):
            return (
                "AGRUPADOR_4_CRIANCA_URGENCIA",
                AGRUPADOR_CRIANCA_URGENCIA,
            )
        # Manual desconhecido → cai pra escolha automática

    # 2) Escolha automática: idade × motivo
    crianca = is_menor_de_3(perfil_kommo, birth_date_iso, hoje)
    urgencia = is_urgencia(motivo, tipo_motivo_kommo)

    if crianca and urgencia:
        return ("AGRUPADOR_4_CRIANCA_URGENCIA", AGRUPADOR_CRIANCA_URGENCIA)
    if crianca and not urgencia:
        return ("AGRUPADOR_3_CRIANCA_ROTINA", AGRUPADOR_CRIANCA_ROTINA)
    if not crianca and urgencia:
        return ("AGRUPADOR_2_ADULTO_EMERGENCIA", AGRUPADOR_ADULTO_EMERGENCIA)
    return ("AGRUPADOR_1_ADULTO_ROTINA", AGRUPADOR_ADULTO_ROTINA)
