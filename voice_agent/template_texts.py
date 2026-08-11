"""
voice_agent/template_texts.py — TEXTOS dos templates Meta + PRÓXIMO PASSO atendente.

Origem: Fábio 11/06/2026 noite — equipe humana não sabia o que foi enviado
nem o que fazer com a resposta do paciente. Lia gravava nota Kommo só com
o NOME do template e telefone; o conteúdo ficava invisível.

Este módulo centraliza:
  1. Texto renderizado provável de cada template (body + botões)
  2. Próximo passo sugerido pro atendente humano

Quando Fábio criar ou alterar um template no Meta Business Manager, atualizar
aqui. Quem usar:

    from voice_agent.template_texts import (
        renderizar_texto_template, proximo_passo_atendente,
    )

NOTA SOBRE PRECISÃO: o texto aqui é a versão APROVADA QUE TEMOS REGISTRADA.
Se o template foi editado e re-aprovado, atualizar. Pra texto 100% via API
real, ver `/admin/template-detalhes/{name}` (TODO próxima sessão — chama
Meta Graph com fields=components).
"""

from __future__ import annotations
from typing import Sequence


# ---------------------------------------------------------------------------
# Textos provavéis (body + botões) por template_name
# ---------------------------------------------------------------------------
# Formato: dict {nome_template: {body, botoes, descricao_curta}}
# Body usa {1}, {2}, {3}... no lugar dos {{N}} originais — pra .format() padrão.

TEMPLATES: dict[str, dict] = {
    # ----- Reativação genérica (Slack #04 e cold leads sem categoria) -----
    "1089_mens_ativar_conv_parada_qz7kbz": {
        "descricao_curta": "Ativar paciente cuja conversa está parada / sem retorno há tempo",
        "body": (
            "Olá, {1}! 👋\n\n"
            "Aqui é a Lia da Blink Oftalmologia. "
            "Faz um tempo que não nos falamos e queremos saber se "
            "podemos te ajudar com sua próxima consulta.\n\n"
            "Quer agendar?"
        ),
        "botoes": ["Quero agendar", "Mais informações", "Não, obrigado"],
    },

    "1079_ativar_conversa_de_imediato_odlmcy": {
        "descricao_curta": "Ativação imediata — chama atenção pra resposta rápida",
        "body": (
            "Oi, {1}! 👋\n\n"
            "Aqui é a Lia da Blink Oftalmologia. "
            "Quer agendar sua consulta agora?\n\n"
            "Posso te oferecer 2 horários hoje mesmo."
        ),
        "botoes": ["Sim, quero agendar", "Mais tarde", "Não, obrigado"],
    },

    # ----- Apresentação Dr. Fabrício pra base Karla (catarata 50+) -----
    "7711_apresentar_dr_fabricio_freitas_6qcphu": {
        "descricao_curta": "Apresenta Dr. Fabrício Freitas (catarata + saúde 50+) pra base existente",
        "body": (
            "Olá, {1}! 👋\n\n"
            "Sou Dr. Fabrício Freitas, especialista em catarata e saúde "
            "ocular do adulto 50+, da Blink Oftalmologia.\n\n"
            "Atendo na Asa Norte e Águas Claras (DF). Se você tem "
            "interesse em avaliação preventiva ou tem dúvida sobre "
            "catarata, posso te ajudar.\n\n"
            "Quer marcar uma consulta?"
        ),
        "botoes": ["Quero agendar", "Quero saber mais", "Outro momento"],
    },

    # ----- Retorno > 1 ano sem consulta (template aprovado novo) -----
    "1020_retorno_mais_de_1_ano_v1": {
        "descricao_curta": "Lembrete pra paciente que não consulta há mais de 1 ano",
        "body": (
            "Olá, {1}!\n\n"
            "Faz mais de um ano que {2} não consulta com a "
            "Dra. Karla (última visita: {3}).\n\n"
            "Hora da próxima consulta 💙"
        ),
        "botoes": ["Agendar agora", "Me lembre depois"],
    },

    # ----- Templates LF (Leads Frio) categorizados -----
    "blink_lf_a_convenio_aceito_v1": {
        "descricao_curta": "Lead frio com convênio aceito — convidar agendar com cobertura",
        "body": (
            "Olá, {1}! 👋\n\n"
            "Vi que você tem cobertura pelo {2}. Quer agendar sua "
            "próxima consulta com cobertura pelo convênio?\n\n"
            "Atendemos na Asa Norte e Águas Claras."
        ),
        "botoes": ["Asa Norte", "Águas Claras", "Prefiro que me liguem"],
    },

    "blink_lf_b_particular_v1": {
        "descricao_curta": "Lead frio particular — apresentar valor + sinal Pix 50%",
        "body": (
            "Olá, {1}! 👋\n\n"
            "Aqui é a Lia da Blink Oftalmologia. Vi que você tem "
            "interesse em agendar particular. Quer que eu te mostre "
            "os horários disponíveis?\n\n"
            "Reserva com 50% via Pix garante o slot."
        ),
        "botoes": ["Essa semana", "Próximas 2 semanas", "Link avaliação online"],
    },

    "blink_lf_c_pediatrico_v1": {
        "descricao_curta": "Lead frio pediátrico — convite oftalmopediatria Karla",
        "body": (
            "Olá, {1}! 👋\n\n"
            "Quer agendar a próxima consulta pediátrica com a "
            "Dra. Karla? O acompanhamento periódico é essencial pra "
            "saúde visual da criança."
        ),
        "botoes": ["Quero agendar", "Mais informações", "Outro momento"],
    },
}


# ---------------------------------------------------------------------------
# Próximos passos pra atendente humano por template
# ---------------------------------------------------------------------------

PROXIMOS_PASSOS: dict[str, str] = {
    "1089_mens_ativar_conv_parada_qz7kbz": (
        "• Resposta SIM/quer agendar → Lia oferece slots automaticamente.\n"
        "• Resposta NÃO/desistiu → MOVER pra 'Closed-lost' e desativar IA.\n"
        "• Resposta DÚVIDA → Lia tenta resolver; se travar, atendente assume.\n\n"
        "⚠️ SE PACIENTE JÁ ESTAVA AGENDADO (status 5+) e pediu cancelar/remarcar (regra E1.7 / Bug C-26):\n\n"
        "1. NÃO oferecer slot novo. Lia pergunta motivo PRIMEIRO.\n\n"
        "2. COM CONVÊNIO — Lia investiga: imprevisto pessoal / problema autorização / sem interesse / sintoma novo.\n"
        "   • Imprevisto → 2.LEADS FRIO + A FAZER=Encaixe + IA Off\n"
        "   • Autorização → 1-ATENDIMENTO HUMANO + IA Off\n"
        "   • Sem interesse → Closed-lost + IA Off\n"
        "   • Sintoma/urgência → 1-ATENDIMENTO HUMANO + AÇÕES=Urgente + IA Off\n\n"
        "3. SEM CONVÊNIO (particular) — Lia investiga: imprevisto / financeiro / sem interesse / urgência.\n"
        "   • Imprevisto → 2.LEADS FRIO + Encaixe + IA Off\n"
        "   • Financeiro → escada 3 turnos: 2x R$ 335 → sábado família R$ 511 → fila incentivo\n"
        "   • Sem interesse → Closed-lost + IA Off\n"
        "   • Urgência → 1-ATENDIMENTO HUMANO + Urgente + IA Off"
    ),

    "1079_ativar_conversa_de_imediato_odlmcy": (
        "• Resposta SIM → Lia oferece 2 slots imediatos (Asa Norte ou Águas Claras).\n"
        "• Resposta MAIS TARDE → agendar follow-up D+3 (Lia faz auto).\n"
        "• Resposta NÃO → mover pra Closed-lost ou perguntar motivo."
    ),

    "7711_apresentar_dr_fabricio_freitas_6qcphu": (
        "• Resposta SIM (agendar) → Lia direciona pra Dr. Fabrício, "
        "explica avaliação inicial (R$ 297 ou Pix 50% R$ 148,50), oferece slots "
        "Asa Norte/Águas Claras.\n"
        "• Resposta MAIS INFO → Lia explica especialidade catarata + saúde 50+ + "
        "atendimento. Atendente intervém se paciente pedir contato direto.\n"
        "• Resposta OUTRO MOMENTO → mover pra 2.LEADS FRIO com tag 'Fabrício futuro'."
    ),

    "1020_retorno_mais_de_1_ano_v1": (
        "• Resposta AGENDAR → Lia oferece slots Dra. Karla na unidade que paciente "
        "preferir.\n"
        "• Resposta ME LEMBRE DEPOIS → agendar follow-up D+30 (Salesbot ou Lia).\n"
        "• Sem resposta após 24h → marca 0-A CLASSIFICAR pra atendente avaliar."
    ),

    "blink_lf_a_convenio_aceito_v1": (
        "• Resposta UNIDADE → Lia oferece 2 slots na unidade escolhida cobertos.\n"
        "• Resposta ME LIGUEM → criar tarefa Kommo 'Ligar' com prazo 4h "
        "horário comercial."
    ),

    "blink_lf_b_particular_v1": (
        "• Resposta ESSA SEMANA → Lia oferece 2 slots dessa semana.\n"
        "• Resposta 2 SEMANAS → Lia oferece slots período mais flexível.\n"
        "• Resposta LINK ONLINE → Lia envia link avaliação online se aplicável."
    ),

    "blink_lf_c_pediatrico_v1": (
        "• Resposta AGENDAR → Lia oferece slots Dra. Karla pediatria.\n"
        "• Resposta MAIS INFO → Lia explica importância retorno pediátrico "
        "0-2anos/6m, 3-12/anual.\n"
        "• Sem resposta → mover pra Closed-lost após 7 dias."
    ),
}


# Fallback genérico quando template não está cadastrado aqui
_FALLBACK_TEXTO = (
    "(Texto exato não cadastrado no Kommo — ver template '{template_name}' "
    "no WhatsApp Business Manager: business.facebook.com → WhatsApp Manager → "
    "Templates → procurar pelo nome técnico.)"
)

_FALLBACK_PROXIMO_PASSO = (
    "• Verificar resposta do paciente acima e responder conforme contexto.\n"
    "• Lia continua ativa — só intervir se IA estiver travando ou caso complexo.\n"
    "• Se paciente desistir, mover pra Closed-lost e desativar IA."
)


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------


def renderizar_texto_template(
    template_name: str,
    body_params: Sequence[str] | None,
    primeiro_nome: str = "",
) -> str:
    """Renderiza body + botões do template com os params substituídos.

    Args:
        template_name: nome técnico aprovado (ex '1089_mens_ativar_conv_parada_qz7kbz')
        body_params: lista de valores pros {1}, {2}, ... do body
        primeiro_nome: usado se body_params vazio (fallback {1}=primeiro_nome)

    Returns:
        String multi-linha com BODY renderizado + 'Botões:' embaixo.
    """
    meta = TEMPLATES.get(template_name)
    if not meta:
        return _FALLBACK_TEXTO.format(template_name=template_name)

    body = meta["body"]
    botoes = meta.get("botoes") or []

    params = list(body_params or [])
    if not params and primeiro_nome:
        params = [primeiro_nome]

    # Substitui {1}, {2}, ... — usa .format se possível, fallback manual.
    try:
        body_renderizado = body.format(*params) if params else body
    except (IndexError, KeyError):
        # Param insuficiente — preenche faltantes com placeholder
        body_renderizado = body
        for i, p in enumerate(params, start=1):
            body_renderizado = body_renderizado.replace(f"{{{i}}}", str(p))

    if botoes:
        bts = " · ".join(botoes)
        return f"{body_renderizado}\n\n[Botões: {bts}]"
    return body_renderizado


def proximo_passo_atendente(template_name: str) -> str:
    """Retorna texto de próximo passo sugerido pro atendente humano."""
    return PROXIMOS_PASSOS.get(template_name, _FALLBACK_PROXIMO_PASSO)


def template_descricao_curta(template_name: str) -> str:
    """Descrição curta (1 linha) do propósito do template."""
    meta = TEMPLATES.get(template_name) or {}
    return meta.get("descricao_curta", "(propósito não cadastrado)")
