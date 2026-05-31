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

TEMPLATE_ATIVAR_URGENCIA_NAME = os.environ.get(
    "WHATSAPP_TEMPLATE_ATIVAR_URGENCIA_NAME",
    "1039_ativar_grau_de_urgencia",
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
