"""Templates Meta WhatsApp Cloud — Blink Oftalmologia 8133-1005.

Templates APROVADOS no Meta Business Manager (WABA 1990931811727552).

Quando usar template vs free-form:
  - Dentro da janela 24h (paciente respondeu há < 24h):
    pode mandar texto livre via /messages com "type":"text".
  - Fora da janela (≥ 24h) OU paciente nunca respondeu:
    é OBRIGATÓRIO usar template aprovado.

Os payloads aqui seguem o formato exato da Cloud API:
https://developers.facebook.com/docs/whatsapp/cloud-api/reference/messages

REGRA DE OURO (Cosmoética Blink): NUNCA inventar template_name. Se um
template não está aprovado, o envio FALHA com erro 132000+. Os valores
abaixo são os que o Fábio confirmou em 31/05/2026 no painel Meta.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Identificadores fixos
# ---------------------------------------------------------------------------

WABA_ID = "1990931811727552"               # Blink Oftalmologia
PHONE_NUMBER_ID = "668422093022140"        # +55 61 8133-1005
LANGUAGE_BR = "pt_BR"


# ---------------------------------------------------------------------------
# Template 1039 — ATIVAR GRAU DE URGÊNCIA
# ---------------------------------------------------------------------------
# Estado em 31/05/2026: APROVADO. Categoria: marketing.
#
# Corpo (conforme print do painel Meta):
#   [Nome de contato],
#
#   Para agendamento no seu tempo, qual a sua escolha:
#
#   1️⃣ Agendamento Imediato para Consulta imediata ou nesta semana;
#   2️⃣ Agendamento Imediato para Consulta neste mês;
#   3️⃣ Paciente prefere fazer contato.
#
#   Escolha uma opção: 1, 2, ou 3
#
# Botões Quick Reply (fixos no template aprovado):
#   [1ª Opção] [2ª Opção] [3ª Opção]
#
# Parâmetros do body:
#   {{1}} = Nome do contato (ex.: "Carla A. de Oliveira", "Maria Soares")
#
# IMPORTANTE: o nome técnico (template_name) DEVE bater EXATAMENTE com o
# slug aprovado no Meta. O nome de exibição "1039 ATIVAR GRAU DE URGÊNCIA"
# vira slug. Default abaixo é o palpite mais provável — se Meta rejeitar
# com "template_name_does_not_exist", basta corrigir a env sem deploy.

# Default = "1079_ativar_conversa_de_imediato_odlmcy" — único template de
# "ativar conversa" 100% similar ao conceito que aprovado no Meta em
# 31/05/2026. O nome de exibição "1039 ATIVAR GRAU DE URGÊNCIA" que o
# Fábio mostrou NÃO foi encontrado via /whatsapp/templates — pode estar
# pendente de aprovação ou rejeitado. Quando aprovar, sobrescrever via env
# WHATSAPP_TEMPLATE_ATIVAR_URGENCIA_NAME=<slug_exato>.
TEMPLATE_ATIVAR_URGENCIA_NAME = os.environ.get(
    "WHATSAPP_TEMPLATE_ATIVAR_URGENCIA_NAME",
    "1079_ativar_conversa_de_imediato_odlmcy",
)

# Como confirmar o slug exato sem precisar de Chrome:
#
# 1) Endpoint que já existe no voice_agent:
#       curl -s https://blink-agent.6prkfn.easypanel.host/whatsapp/templates | jq
#    Procurar pelo objeto cujo "name" comece com "1039" — esse é o slug.
#
# 2) Pelo painel Meta Business Manager (Fábio):
#       business.facebook.com → WhatsApp Manager → Templates → 1039 ATIVAR
#       Slug aparece logo abaixo do nome de exibição (snake_case minúsculo).
#
# 3) Graph API direto:
#       GET /v22.0/1990931811727552/message_templates?fields=name,status,language
#       Authorization: Bearer $WHATSAPP_CLOUD_TOKEN
#
# Se o default acima não bater, basta atualizar
# `WHATSAPP_TEMPLATE_ATIVAR_URGENCIA_NAME` no Easypanel SEM precisar deploy.


@dataclass
class TemplateMeta:
    """Metadata de um template aprovado."""
    template_name: str
    language_code: str
    descricao: str
    parametros_body: list[str]    # nomes legíveis dos {{N}}
    botoes_quick_reply: list[str] # texto dos botões fixos


TEMPLATE_1039 = TemplateMeta(
    template_name=TEMPLATE_ATIVAR_URGENCIA_NAME,
    language_code=LANGUAGE_BR,
    descricao="Reengajar lead pré-agendamento — perguntar grau de urgência",
    parametros_body=["nome_contato"],
    botoes_quick_reply=["1ª Opção", "2ª Opção", "3ª Opção"],
)


# ---------------------------------------------------------------------------
# Builder do payload pra Graph API
# ---------------------------------------------------------------------------

def normalizar_telefone_e164(numero: str) -> str | None:
    """'(61) 99999-0000' / '61999990000' / '5561...' → '5561999990000'.

    Devolve None se inválido. Cloud API exige E.164 sem '+'.
    """
    if not numero:
        return None
    digitos = "".join(c for c in numero if c.isdigit())
    if not digitos:
        return None
    if not digitos.startswith("55"):
        # Assume Brasil quando vier só DDD+numero.
        if len(digitos) in (10, 11):
            digitos = "55" + digitos
    if len(digitos) < 12 or len(digitos) > 13:
        return None
    return digitos


def build_template_ativar_urgencia(
    *,
    to_telefone: str,
    nome_contato: str,
    template_name: str | None = None,
    language_code: str = LANGUAGE_BR,
) -> dict | None:
    """Payload pronto pra POST /v22.0/{phone_number_id}/messages.

    Retorna None se o telefone for inválido ou nome vazio.
    """
    to_e164 = normalizar_telefone_e164(to_telefone)
    if not to_e164:
        return None
    nome = (nome_contato or "").strip()
    if not nome:
        return None
    # Cloud API NÃO permite quebra de linha em parâmetro de texto;
    # apenas espaços. Sanitiza pra evitar HTTP 400.
    nome_limpo = " ".join(nome.split())[:120]
    name = template_name or TEMPLATE_1039.template_name
    return {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to_e164,
        "type": "template",
        "template": {
            "name": name,
            "language": {"code": language_code},
            "components": [
                {
                    "type": "body",
                    "parameters": [
                        {"type": "text", "text": nome_limpo},
                    ],
                }
            ],
        },
    }


# ---------------------------------------------------------------------------
# Estratégia: free-form vs template
# ---------------------------------------------------------------------------

@dataclass
class EstrategiaRenovacao:
    """Saída do decisor — diz qual mecanismo usar."""
    tipo: str            # "free_form" | "template_1039" | "nao_disparar"
    motivo: str | None   # explicação curta pra log
    detalhe: dict | None # info auxiliar (template_name etc)


def decidir_estrategia(
    elegibilidade: dict,
    *,
    paciente_ja_respondeu_na_vida: bool,
) -> EstrategiaRenovacao:
    """Decide se manda free-form, template aprovado, ou não dispara.

    Entrada:
      - elegibilidade: dict de elegivel_renovar_janela()
      - paciente_ja_respondeu_na_vida: True se em algum momento o paciente
        já falou com a Lia. Usado pra distinguir lead frio puro vs lead em
        conversa com janela expirada.

    Regras (Cosmoética Blink):
      - elegivel=True → free-form (janela aberta, mais cordial)
      - razao=janela_morta E paciente já respondeu → template_1039 (reabre conversa)
      - razao=sem_interacao E lead frio → template_1039 (engajamento inicial)
      - razao=status_pos_agendado → nao_disparar (paciente JÁ agendou)
      - razao=ainda_cedo → nao_disparar (próxima janela cuida)
    """
    if elegibilidade.get("elegivel"):
        return EstrategiaRenovacao(
            tipo="free_form",
            motivo="janela_24h_aberta_perto_de_expirar",
            detalhe=None,
        )

    razao = elegibilidade.get("razao")

    if razao == "janela_expirou_so_template":
        return EstrategiaRenovacao(
            tipo="template_1039",
            motivo="janela_24h_fechou_precisa_template_aprovado",
            detalhe={
                "template_name": TEMPLATE_1039.template_name,
                "language": TEMPLATE_1039.language_code,
            },
        )

    if razao == "paciente_nunca_falou":
        # Lead frio puro — usar template 1039 pra abrir conversa.
        return EstrategiaRenovacao(
            tipo="template_1039",
            motivo="lead_frio_puro_engajamento_inicial",
            detalhe={
                "template_name": TEMPLATE_1039.template_name,
                "language": TEMPLATE_1039.language_code,
            },
        )

    # status_pos_agendado, ainda_cedo, ou qualquer outro caso → não dispara
    return EstrategiaRenovacao(
        tipo="nao_disparar",
        motivo=razao or "razao_desconhecida",
        detalhe=None,
    )


# ---------------------------------------------------------------------------
# Templates PROX_CONSULTA aprovados 04/07/2026 — retorno programado por paciente
# ---------------------------------------------------------------------------
# Contexto (Fábio 04/07/2026 22h BRT):
#   - No Kommo, cada lead pode ter até 6 pacientes (1.PACIENTE .. 6.PACIENTE)
#     replicando os campos 1.DIA CONSULTA, 1.MES PROX CONSULTA, 1.UNIDADE etc.
#     Isso cobre família (mãe + pai + 4 filhos, por exemplo).
#
#   - Cadências de retorno programadas pela Dra. Karla:
#       6 meses  → pediátrico 0-2 anos, pós-op recente
#       anual    → pediátrico 3+ anos, adulto rotina
#
#   - Meta rejeita templates com body idêntico entre variantes numeradas
#     01..06 (INVALID_FORMAT). Por isso submetemos UM template genérico por
#     cadência. O dispatcher itera sobre os 6 pacientes do lead e dispara
#     N vezes com body_params diferentes.
#
# Estrutura do body (7 variáveis, mesma ordem nos 2 templates):
#   {{1}} nome_contato        — quem responde WhatsApp (mãe/pai/o próprio paciente)
#   {{2}} nome_paciente       — nome de UM paciente específico do lead
#   {{3}} data_ultima_consulta — 1.DIA CONSULTA (dd/mm/aaaa)
#   {{4}} data_prox_prevista  — 1.MES PROX CONSULTA / data-alvo (dd/mm/aaaa)
#   {{5}} unidade             — "Asa Norte" | "Águas Claras"
#   {{6}} slot_1              — "12/01/2026 às 09h" (mais próximo)
#   {{7}} slot_2              — "15/01/2026 às 14h" (alternativa)
#
# Aprovação Meta confirmada via Graph API em 04/07/2026 22h:
#   APPROVED blink_prox_consulta_6m_karla_v3
#   APPROVED blink_prox_consulta_1ano_karla_v3

TEMPLATE_PROX_CONSULTA_6M_KARLA_NAME = os.environ.get(
    "WHATSAPP_TEMPLATE_PROX_CONSULTA_6M_KARLA_NAME",
    "blink_prox_consulta_6m_karla_v3",
)

TEMPLATE_PROX_CONSULTA_1ANO_KARLA_NAME = os.environ.get(
    "WHATSAPP_TEMPLATE_PROX_CONSULTA_1ANO_KARLA_NAME",
    "blink_prox_consulta_1ano_karla_v3",
)

_PARAMS_PROX_CONSULTA = [
    "nome_contato",
    "nome_paciente",
    "data_ultima_consulta",
    "data_prox_prevista",
    "unidade",
    "slot_1",
    "slot_2",
]

TEMPLATE_PROX_CONSULTA_6M_KARLA = TemplateMeta(
    template_name=TEMPLATE_PROX_CONSULTA_6M_KARLA_NAME,
    language_code=LANGUAGE_BR,
    descricao="Retorno programado 6 meses — Dra. Karla (pediátrico 0-2a, pós-op)",
    parametros_body=list(_PARAMS_PROX_CONSULTA),
    botoes_quick_reply=[],
)

TEMPLATE_PROX_CONSULTA_1ANO_KARLA = TemplateMeta(
    template_name=TEMPLATE_PROX_CONSULTA_1ANO_KARLA_NAME,
    language_code=LANGUAGE_BR,
    descricao="Retorno programado anual — Dra. Karla (pediátrico 3+, adulto rotina)",
    parametros_body=list(_PARAMS_PROX_CONSULTA),
    botoes_quick_reply=[],
)


def _sanitizar_param(valor: str, max_chars: int = 120) -> str | None:
    """Normaliza um parâmetro pra Cloud API.

    Cloud API rejeita:
      - vazio/None
      - quebras de linha (\\n, \\r, \\t)
      - tab

    Aceita:
      - texto plano
      - emojis
      - números (converte pra str)

    Trunca em max_chars pra evitar HTTP 400.
    """
    if valor is None:
        return None
    txt = str(valor).strip()
    if not txt:
        return None
    # Substitui quebras/tabs por espaço; colapsa espaços múltiplos.
    txt = " ".join(txt.replace("\n", " ").replace("\r", " ").replace("\t", " ").split())
    if not txt:
        return None
    return txt[:max_chars]


def build_template_prox_consulta(
    *,
    to_telefone: str,
    cadencia: str,          # "6m" ou "1ano"
    nome_contato: str,
    nome_paciente: str,
    data_ultima_consulta: str,
    data_prox_prevista: str,
    unidade: str,
    slot_1: str,
    slot_2: str,
    template_name: str | None = None,
    language_code: str = LANGUAGE_BR,
) -> dict | None:
    """Payload pra POST /v22.0/{phone_number_id}/messages usando os 2 templates aprovados.

    Retorna None se:
      - telefone inválido
      - cadência não em {"6m","1ano"}
      - qualquer parâmetro obrigatório vazio

    Uso típico (dispatcher itera sobre N pacientes do lead):
        for pac in lead.pacientes_elegiveis(cadencia="6m"):
            payload = build_template_prox_consulta(
                to_telefone=lead.contato_telefone,
                cadencia="6m",
                nome_contato=lead.nome_contato,
                nome_paciente=pac.nome,
                data_ultima_consulta=pac.dia_consulta_fmt,
                data_prox_prevista=pac.mes_prox_consulta_fmt,
                unidade=pac.unidade,
                slot_1=slots[0].fmt,
                slot_2=slots[1].fmt,
            )
            if payload:
                cloud_api.enviar(payload)
    """
    to_e164 = normalizar_telefone_e164(to_telefone)
    if not to_e164:
        return None

    cad = (cadencia or "").strip().lower()
    if cad in ("6m", "6meses", "6_meses", "6-meses"):
        name = template_name or TEMPLATE_PROX_CONSULTA_6M_KARLA.template_name
    elif cad in ("1ano", "anual", "1_ano", "1-ano", "12m"):
        name = template_name or TEMPLATE_PROX_CONSULTA_1ANO_KARLA.template_name
    else:
        return None

    valores = [
        _sanitizar_param(nome_contato, max_chars=60),
        _sanitizar_param(nome_paciente, max_chars=60),
        _sanitizar_param(data_ultima_consulta, max_chars=20),
        _sanitizar_param(data_prox_prevista, max_chars=20),
        _sanitizar_param(unidade, max_chars=40),
        _sanitizar_param(slot_1, max_chars=40),
        _sanitizar_param(slot_2, max_chars=40),
    ]
    if any(v is None for v in valores):
        return None

    return {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to_e164,
        "type": "template",
        "template": {
            "name": name,
            "language": {"code": language_code},
            "components": [
                {
                    "type": "body",
                    "parameters": [{"type": "text", "text": v} for v in valores],
                }
            ],
        },
    }


# ---------------------------------------------------------------------------
# Roteador: dado um lead com N pacientes, decidir quais têm retorno vencendo
# ---------------------------------------------------------------------------

from dataclasses import field
from datetime import date, datetime, timedelta


@dataclass
class PacienteDoLead:
    """Um dos até 6 pacientes de um lead Kommo."""
    indice: int                              # 1..6 (1.PACIENTE, 2.PACIENTE, ...)
    nome: str
    dia_consulta: date | None                # 1.DIA CONSULTA (última realizada)
    mes_prox_consulta: date | None           # 1.MES PROX CONSULTA (data-alvo)
    unidade: str | None                      # "Asa Norte" | "Águas Claras"
    cadencia: str | None = None              # "6m" | "1ano" | None (indefinido)


@dataclass
class DecisaoRetornoProgramado:
    """Saída do roteador — 1 registro por paciente que precisa disparo agora."""
    paciente: PacienteDoLead
    cadencia_normalizada: str                # "6m" | "1ano"
    template_name: str
    dias_ate_prox: int                       # negativo = já venceu
    motivo: str


def _formatar_data_br(d: date | None) -> str:
    if d is None:
        return "-"
    return d.strftime("%d/%m/%Y")


def normalizar_cadencia(cadencia: str | None) -> str | None:
    """Aceita variantes ('6 meses', '6m', 'anual', '1 ano', '12m') → '6m' | '1ano'."""
    if not cadencia:
        return None
    c = str(cadencia).strip().lower().replace(" ", "").replace("-", "").replace("_", "")
    if c in ("6m", "6meses", "6mes", "seis meses".replace(" ", ""), "seismeses"):
        return "6m"
    if c in ("1ano", "12m", "12meses", "anual", "umano"):
        return "1ano"
    return None


def rotear_pacientes_para_disparo(
    pacientes: list[PacienteDoLead],
    *,
    hoje: date | None = None,
    janela_antecedencia_dias: int = 30,
    janela_atraso_dias: int = 90,
) -> list[DecisaoRetornoProgramado]:
    """Dado até 6 pacientes de um lead, devolve os que precisam disparo agora.

    Elegibilidade por paciente:
      - cadencia normaliza pra "6m" ou "1ano"
      - mes_prox_consulta existe
      - hoje está entre (mes_prox - antecedencia) e (mes_prox + atraso)
        → dispara "cedo" pra antecipar reagendamento sem constrangimento,
          mas não muito tarde pra evitar batch retroativo antigo.

    Ordena por dias_ate_prox crescente (urgência primeiro).

    Não faz side effect — quem dispara é o dispatcher externo.
    """
    if hoje is None:
        hoje = date.today()

    decisoes: list[DecisaoRetornoProgramado] = []
    for pac in pacientes:
        cad = normalizar_cadencia(pac.cadencia)
        if cad not in ("6m", "1ano"):
            continue
        if pac.mes_prox_consulta is None:
            continue

        delta = (pac.mes_prox_consulta - hoje).days
        # cedo: até 30 dias antes da data-alvo
        # atrasado: até 90 dias depois da data-alvo
        if delta > janela_antecedencia_dias:
            continue
        if delta < -janela_atraso_dias:
            continue

        template = (
            TEMPLATE_PROX_CONSULTA_6M_KARLA.template_name
            if cad == "6m"
            else TEMPLATE_PROX_CONSULTA_1ANO_KARLA.template_name
        )

        if delta < 0:
            motivo = f"vencido_ha_{abs(delta)}_dias"
        elif delta == 0:
            motivo = "vence_hoje"
        else:
            motivo = f"vence_em_{delta}_dias"

        decisoes.append(
            DecisaoRetornoProgramado(
                paciente=pac,
                cadencia_normalizada=cad,
                template_name=template,
                dias_ate_prox=delta,
                motivo=motivo,
            )
        )

    decisoes.sort(key=lambda d: d.dias_ate_prox)
    return decisoes
