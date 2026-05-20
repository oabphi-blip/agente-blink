"""Responder com Claude Sonnet/Haiku — especialista em atendimento e conversão.

Arquitetura:
- INSTRUÇÃO MESTRA oficial Blink como system prompt (autoridade máxima).
- RAG por keywords dos 40 artigos da knowledge_base.
- Roteador inteligente Sonnet vs Haiku por complexidade da mensagem.
- Histórico curto por contato (sliding window).
- Cache de resposta de 30s para evitar duplicata de webhook.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

from anthropic import Anthropic

from .knowledge import KB_DIR, KnowledgeBase
from .store import ConversationStore

# Fuso horário oficial da clínica (Brasília) — usado pra cálculo de idade
# e data de "hoje" injetada no system prompt.
_TZ_BRT = ZoneInfo("America/Sao_Paulo")


def _today_brt_block() -> str:
    """Bloco de data de hoje (BRT) com instruções de cálculo de idade.

    Inclui a data por extenso, ISO e dia da semana — o Claude por padrão
    não tem acesso a relógio do sistema, então sem essa injeção ele chuta
    com base no cutoff de treino e erra idades por 1 ou mais anos.
    """
    now = datetime.now(_TZ_BRT)
    months = [
        "janeiro", "fevereiro", "março", "abril", "maio", "junho",
        "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
    ]
    weekdays = [
        "segunda-feira", "terça-feira", "quarta-feira", "quinta-feira",
        "sexta-feira", "sábado", "domingo",
    ]
    extenso = f"{weekdays[now.weekday()]}, {now.day} de {months[now.month-1]} de {now.year}"
    iso = now.strftime("%Y-%m-%d")
    hora = now.strftime("%H:%M")
    # Saudação correta conforme a hora BRT — calculada no código (à prova de erro)
    h = now.hour
    if h < 12:
        saudacao, periodo = "Bom dia", "manhã"
    elif h < 18:
        saudacao, periodo = "Boa tarde", "tarde"
    else:
        saudacao, periodo = "Boa noite", "noite"
    return (
        "\n\n================================================================"
        "\nDATA DE HOJE (fuso Brasília — fonte de verdade para cálculos)"
        "\n================================================================"
        f"\nHoje é {extenso} ({iso}), {hora} BRT."
        f"\nPeríodo do dia agora: {periodo}."
        f"\nSAUDAÇÃO CORRETA AGORA: \"{saudacao}\"."
        "\nSe for cumprimentar pelo período do dia, use EXATAMENTE \"" + saudacao + "\"."
        "\nÉ PROIBIDO usar outra saudação de período (não diga 'Bom dia' à tarde/noite)."
        "\nNa dúvida, use apenas \"Olá!\" — neutro, nunca erra."
        "\n"
        "\nREGRA OBRIGATÓRIA DE CÁLCULO DE IDADE:"
        "\n1. Idade = (ano de hoje − ano de nascimento)"
        "\n2. SE (mês de hoje, dia de hoje) < (mês de nascimento, dia de nascimento):"
        "\n   subtrair 1 da idade (ainda não fez aniversário este ano)"
        "\n3. SENÃO: manter o valor (já fez aniversário ou faz hoje)"
        "\n"
        "\nExemplo: nascido em 23/07/1976. Hoje é 20/05/2026."
        "\n  Ano: 2026 − 1976 = 50. Mês/dia hoje (05/20) < mês/dia nasc (07/23)."
        "\n  Logo idade = 50 − 1 = 49 anos."
        "\n"
        "\nÉ PROIBIDO usar conhecimento interno de 'data atual'. SEMPRE usar a data"
        "\nacima como hoje. PROIBIDO inventar ano, mês ou dia."
        "\n================================================================"
    )

log = logging.getLogger(__name__)


def _load_master_instruction() -> str:
    path = KB_DIR / "_MASTER_INSTRUCTION.md"
    if path.is_file():
        return path.read_text(encoding="utf-8")
    return "Você é a Lia, assistente virtual da Blink Oftalmologia."


# Palavras/contextos que exigem Sonnet (mais inteligente, mais caro)
# Para tudo o resto, Haiku (rápido, barato).
SONNET_TRIGGERS = {
    # Urgência e segurança
    "urgência", "urgencia", "emergência", "emergencia", "socorro",
    "trauma", "perdi a visão", "perdi visao", "respingo", "dor forte",
    "dor intensa", "flashes", "secreção", "secrecao", "vermelho extremo",
    # Catarata e venda complexa
    "catarata", "cirurgia", "lente intraocular", "lio", "multifocal",
    "premium", "dr fabricio", "dr fabrício", "fabricio freitas",
    # SDP / Estrabismo / Prisma
    "sdp", "síndrome postural", "sindrome postural", "estrabismo",
    "prisma", "tontura", "deficiência postural", "deficiencia postural",
    # Objeções e situações sensíveis
    "está caro", "esta caro", "muito caro", "vou pensar",
    "cancelar", "reembolso", "remarcar",
    "humano", "atendente", "pessoa de verdade",
    "reclamar", "reclamação", "reclamacao",
    # Pediatria (criança = sensível)
    "filho", "filha", "criança", "crianca", "bebê", "bebe", "filhinho", "filhinha",
}


def _caller_context_block(ctx: Optional[dict]) -> str:
    """Bloco de ONBOARDING — o que o CRM já sabe sobre quem está conversando.

    Sem isto o agente repergunta dados que a clínica já tem. Com isto, ele
    saúda de forma personalizada e pula etapas já satisfeitas.
    """
    if not ctx or not ctx.get("found"):
        return (
            "\n\n================================================================"
            "\nONBOARDING — CONTATO NOVO"
            "\n================================================================"
            "\nNão há registro anterior deste contato no CRM. Trate como primeiro"
            "\ncontato: boas-vindas padrão e triagem normal."
            "\n================================================================"
        )
    known = ctx.get("known") or {}
    nome = ctx.get("name")
    linhas = []
    rotulos = {
        "nome_paciente": "Nome do paciente", "motivo": "Motivo registrado",
        "convenio": "Convênio", "unidade": "Unidade", "medico": "Médico",
        "especialidade": "Especialidade", "dia_turno": "Preferência dia/turno",
    }
    for k, label in rotulos.items():
        if known.get(k):
            linhas.append(f"- {label}: {known[k]}")
    dados = "\n".join(linhas) if linhas else "- (lead existe, mas sem campos preenchidos ainda)"
    saudacao = (
        f'Cumprimente pelo nome ("Olá, {nome}!") de forma calorosa.'
        if nome else "Há um lead existente para este contato."
    )
    return (
        "\n\n================================================================"
        "\nONBOARDING — CONTATO JÁ CONHECIDO PELO CRM"
        "\n================================================================"
        f"\n{saudacao}"
        "\nO CRM já tem estes dados deste contato:"
        f"\n{dados}"
        "\n"
        "\nREGRA: É PROIBIDO reperguntar qualquer dado já listado acima. Trate-os"
        "\ncomo confirmados e avance direto para a próxima etapa pendente do"
        "\nfluxo mestre (seção 0-B). Confirme de leve se fizer sentido"
        '("Você quer seguir com [convênio/médico] como da outra vez?"), mas'
        "\nnunca recolha de novo o que já está aqui."
        "\n================================================================"
    )


def _route_model(user_text: str, history_len: int, sonnet: str, haiku: str) -> str:
    """Roteador Sonnet vs Haiku por complexidade.

    Regras:
    - Sonnet se mensagem contém gatilho sensível (urgência, catarata, SDP, objeção, criança).
    - Sonnet se for primeira interação (history vazia) — abre conversa bem.
    - Sonnet em conversas longas (>10 turnos) — manter qualidade.
    - Haiku para confirmações/agradecimentos simples no meio da conversa.
    """
    text_lower = (user_text or "").lower()

    # Primeira interação merece o melhor (cria boa primeira impressão)
    if history_len == 0:
        return sonnet

    # Conversa já bem desenvolvida — manter qualidade
    if history_len > 20:
        return sonnet

    # Triggers sensíveis
    for trig in SONNET_TRIGGERS:
        if trig in text_lower:
            return sonnet

    # Default: Haiku (rápido e barato)
    return haiku


class Responder:
    """Especialista em atendimento e conversão da Blink Oftalmologia."""

    def __init__(
        self,
        api_key: str,
        sonnet_model: str = "claude-sonnet-4-5",
        haiku_model: str = "claude-haiku-4-5-20251001",
        system_prompt: str | None = None,
        max_response_chars: int = 1200,
        knowledge_base: KnowledgeBase | None = None,
        conversation_store: Optional[ConversationStore] = None,
    ):
        self._client = Anthropic(api_key=api_key)
        self._sonnet = sonnet_model
        self._haiku = haiku_model
        # System prompt oficial = INSTRUÇÃO MESTRA + artigos por contexto
        self._base_system_prompt = system_prompt or _load_master_instruction()
        self._max_chars = max_response_chars
        # Store de conversa — persistente (Redis) se fornecido; senão memória.
        self._convos = conversation_store or ConversationStore()
        self._kb = knowledge_base or KnowledgeBase()

    def reply(
        self, conversation_key: str, user_text: str,
        caller_context: Optional[dict] = None,
    ) -> dict:
        """Gera resposta para o paciente.

        Args:
            caller_context: dict opcional com o que o CRM já sabe sobre o
                contato (onboarding orquestrado). Injetado no system prompt.

        Returns:
            {"answer": str, "model_used": str, "articles_used": list[str]}
        """
        # 1. Seleciona artigos relevantes da KB
        relevant = self._kb.select_relevant(user_text, max_articles=3, max_chars=12000)

        # 1b. SEMPRE injetar as listas oficiais de convênios (artigos 17 e 18) —
        # são pequenas (~10KB juntas) e críticas: o agente NUNCA pode afirmar
        # "não aceitamos X" sem o catálogo completo na frente. Isso elimina o
        # bug onde "Tribunal" / "STJ" eram negados erradamente.
        mandatory_filenames = [
            "17_convenios_aceitos_lista_oficial.md",
            "18_convenios_NAO_aceitos_lista_oficial.md",
        ]
        existing_filenames = {a.filename for a in relevant}
        mandatory_articles = []
        for fn in mandatory_filenames:
            if fn in existing_filenames:
                continue
            art = self._kb._articles.get(fn)
            if art is not None:
                mandatory_articles.append(art)
        # Listas oficiais primeiro, depois os artigos por RAG
        combined = mandatory_articles + list(relevant)

        kb_block = self._kb.format_for_prompt(combined) if combined else ""

        # 2. Monta system prompt = INSTRUÇÃO MESTRA + DATA DE HOJE + KB contextual
        system_prompt = self._base_system_prompt + _today_brt_block()
        system_prompt += _caller_context_block(caller_context)
        if kb_block:
            system_prompt += (
                "\n\n================================================================"
                "\nCONHECIMENTO BLINK RELEVANTE PARA ESTA CONVERSA"
                "\n================================================================"
                f"\n{kb_block}"
                "\n\n================================================================"
                "\nFIM DO CONHECIMENTO. APLIQUE COM AS REGRAS DA INSTRUÇÃO MESTRA ACIMA."
                "\n================================================================"
            )

        # 3. Monta histórico no formato Anthropic (sem system, só user/assistant)
        history = self._convos.get(conversation_key)
        messages = history + [{"role": "user", "content": user_text}]

        # 4. Decide modelo
        model = _route_model(user_text, len(history), self._sonnet, self._haiku)

        # 5. Chama Claude
        response = self._client.messages.create(
            model=model,
            max_tokens=600,
            system=system_prompt,
            messages=messages,
            temperature=0.3,  # baixa pra seguir as regras estritas da Blink
        )

        # Extrai texto da resposta
        answer_parts = [block.text for block in response.content if block.type == "text"]
        answer = "\n".join(answer_parts).strip()

        if len(answer) > self._max_chars:
            answer = answer[: self._max_chars - 1].rstrip() + "…"

        # 6. Persiste no histórico
        self._convos.append(conversation_key, "user", user_text)
        self._convos.append(conversation_key, "assistant", answer)

        log.info(
            "Claude %s respondeu (%d chars, hist=%d, kb=%d artigos)",
            model, len(answer), len(history), len(combined),
        )

        return {
            "answer": answer,
            "model_used": model,
            "articles_used": [a.filename for a in combined],
        }

    def reset(self, conversation_key: str) -> None:
        self._convos.reset(conversation_key)

    # ----------------------------------------------------- Kommo extraction

    def extract_lead_fields(self, conversation_key: str) -> dict:
        """Lê o histórico da conversa e devolve campos estruturados pro Kommo.

        Usa Claude Haiku (barato, ~5¢/MM tokens) e tool_use pra garantir JSON
        bem formado. Retorna {} se ainda não houver dado suficiente.

        Chaves possíveis:
          name, birth_date_iso (YYYY-MM-DD), reason,
          convenio, unidade, medico, especialidade, tipo_agendamento,
          perfil_paciente, num_pacientes, dia_turno_periodo
        """
        history = self._convos.get(conversation_key)
        if not history:
            return {}

        # Formata histórico como texto simples
        transcript = []
        for msg in history:
            role = "PACIENTE" if msg["role"] == "user" else "AGENTE"
            transcript.append(f"[{role}] {msg['content']}")
        conversation = "\n".join(transcript)

        tool_schema = {
            "name": "save_lead_fields",
            "description": (
                "Salva os dados estruturados do paciente extraídos da conversa. "
                "Só preencha um campo se a informação foi DITA EXPLICITAMENTE "
                "pelo paciente ou pelo agente. Não invente."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Nome completo do paciente"},
                    "birth_date_iso": {
                        "type": "string",
                        "description": "Data de nascimento em formato YYYY-MM-DD",
                    },
                    "reason": {"type": "string", "description": "Motivo/queixa da consulta"},
                    "convenio": {
                        "type": "string",
                        "description": "Nome do convênio (ex: 'Pro Ser STJ') ou 'Particular'",
                    },
                    "unidade": {
                        "type": "string",
                        "enum": ["Asa Norte", "Águas Claras"],
                    },
                    "medico": {
                        "type": "string",
                        "description": "Nome do médico (Dra. Karla Delalibera, Dr. Fabricio Freitas, Dra. Katia Delalibera, etc.)",
                    },
                    "especialidade": {
                        "type": "string",
                        "enum": [
                            "Oftalmopediatria", "Estrabismo", "SDP",
                            "Catarata", "Retina", "Oftalmologia Geral",
                            "Lentes", "Refrativa",
                        ],
                    },
                    "tipo_agendamento": {
                        "type": "string",
                        "enum": ["Fixo/Definido", "Encaixe", "Domiciliar"],
                    },
                    "perfil_paciente": {
                        "type": "string",
                        "enum": [
                            "Bebê 0-2", "Criança 3-12", "Adolescente 13-18",
                            "Adulto de 19 a 49", "Acima de 50",
                        ],
                    },
                    "num_pacientes": {
                        "type": "string",
                        "enum": ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10"],
                    },
                    "dia_turno_periodo": {
                        "type": "string",
                        "description": "Preferência do paciente em texto livre, ex: 'Segunda-feira — manhã — início (8h-9h)'",
                    },
                },
            },
        }

        system = (
            "Você é um extrator de dados estruturados de conversas de atendimento "
            "da clínica Blink Oftalmologia. Leia a conversa entre AGENTE e PACIENTE "
            "e chame save_lead_fields APENAS com os campos cuja informação foi "
            "explicitamente confirmada na conversa. Se um campo não foi dito, "
            "NÃO inclua. Não chute idade — só preencha perfil_paciente se a data "
            "de nascimento ou idade foi dita."
        )

        try:
            response = self._client.messages.create(
                model=self._haiku,
                max_tokens=600,
                system=system,
                tools=[tool_schema],
                tool_choice={"type": "tool", "name": "save_lead_fields"},
                messages=[{"role": "user", "content": conversation}],
                temperature=0,
            )
            for block in response.content:
                if block.type == "tool_use" and block.name == "save_lead_fields":
                    extracted = dict(block.input or {})
                    # Remove vazios
                    return {k: v for k, v in extracted.items() if v}
        except Exception as e:  # noqa: BLE001
            log.warning("extract_lead_fields falhou: %s", e)
        return {}
