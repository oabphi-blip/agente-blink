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
from datetime import datetime, timedelta
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


# Nomes dos dias da semana e meses — índices alinhados ao datetime.weekday()
# (0 = segunda-feira ... 6 = domingo).
_WEEKDAYS_PT = [
    "segunda-feira", "terça-feira", "quarta-feira", "quinta-feira",
    "sexta-feira", "sábado", "domingo",
]
_MONTHS_PT = [
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
]


def _offer_window_block() -> str:
    """Janela de oferta de agenda — os próximos 5 dias úteis, já com a data
    e o dia da semana CALCULADOS pelo código (à prova de erro).

    Por que isto existe: o Claude não tem um calendário confiável. Se ele
    "calcula" sozinho a que dia da semana cai uma data futura, erra — foi
    exatamente o bug do lead Alonso Marques (ofereceu 31/05 chamando de
    segunda-feira, quando era domingo). Aqui o código entrega a lista
    pronta, e o agente fica PROIBIDO de oferecer data fora dela ou de
    inventar o dia da semana.

    A janela começa AMANHÃ (hoje não se oferece — o horário exato é
    confirmado depois pela equipe humana) e cobre 5 dias úteis (seg–sex).
    Sábados que caiam dentro desse intervalo são listados à parte como
    Agenda Extra de sábado.
    """
    now = datetime.now(_TZ_BRT)
    today = now.date()

    business: list = []   # próximos 5 dias úteis (seg–sex)
    saturdays: list = []  # sábados dentro do mesmo intervalo (Agenda Extra)

    d = today + timedelta(days=1)  # começa amanhã
    while len(business) < 5:
        wd = d.weekday()
        if wd < 5:            # segunda a sexta
            business.append(d)
        elif wd == 5:         # sábado
            saturdays.append(d)
        d = d + timedelta(days=1)

    def _fmt(dt) -> str:
        return f"{_WEEKDAYS_PT[dt.weekday()]}, {dt.day:02d}/{dt.month:02d}/{dt.year}"

    linhas_uteis = "\n".join(f"   - {_fmt(dt)}" for dt in business)
    if saturdays:
        linhas_sab = "\n".join(
            f"   - {_fmt(dt)} (Agenda Extra de sábado)" for dt in saturdays
        )
        sab_block = (
            "\n\nSábado(s) dentro do mesmo intervalo (oferecer SÓ como Agenda"
            "\nExtra, quando a regra 11.2 da Instrução Mestra permitir):"
            f"\n{linhas_sab}"
        )
    else:
        sab_block = ""

    primeiro, ultimo = business[0], business[-1]
    return (
        "\n\n================================================================"
        "\nJANELA DE OFERTA DE AGENDA — PRÓXIMOS 5 DIAS ÚTEIS"
        "\n(datas e dias da semana calculados pelo sistema — fonte de verdade)"
        "\n================================================================"
        "\nEstas são as ÚNICAS datas que você pode oferecer ao paciente. Cada"
        "\nlinha já traz o dia da semana CORRETO — copie exatamente como está."
        f"\n\nDias úteis disponíveis para oferta "
        f"(de {primeiro.day:02d}/{primeiro.month:02d} a {ultimo.day:02d}/{ultimo.month:02d}):"
        f"\n{linhas_uteis}"
        f"{sab_block}"
        "\n"
        "\nREGRAS OBRIGATÓRIAS DE OFERTA DE DATA:"
        "\n1. SÓ ofereça datas que aparecem na lista acima. É PROIBIDO oferecer"
        "\n   qualquer data fora desta janela de 5 dias úteis."
        "\n2. É PROIBIDO calcular, deduzir ou inventar o dia da semana de uma"
        "\n   data. Use SOMENTE o dia da semana escrito ao lado de cada data."
        "\n3. Ao citar uma data, escreva sempre dia-da-semana + data JUNTOS,"
        "\n   exatamente como na lista (ex.: \"quinta-feira, "
        f"{primeiro.day:02d}/{primeiro.month:02d}/{primeiro.year}\")."
        "\n4. Cruze com os dias de atendimento do médico (artigos 22/34): ofereça"
        "\n   apenas as datas da lista cujo dia da semana o médico atende."
        "\n5. Se o paciente pedir um dia fora desta janela, informe gentilmente"
        "\n   as opções da lista e ofereça as da lista — NUNCA confirme nem"
        "\n   invente data fora dela."
        "\n6. O horário exato (HH:MM) é confirmado pela equipe humana. Você"
        "\n   oferece o DIA; não invente horário cheio."
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


def _agenda_block(ctx: Optional[dict]) -> str:
    """Bloco de HORÁRIOS REAIS — vagas livres consultadas no Medware."""
    agenda = (ctx or {}).get("agenda") or []
    if not agenda:
        return ""
    por_dia: dict = {}
    ordem: list = []
    for s in agenda:
        key = (s.get("dia_semana", ""), s.get("data_br", ""))
        if key not in por_dia:
            por_dia[key] = []
            ordem.append(key)
        por_dia[key].append(s.get("hora", ""))
    # TRAVA 1 — amostra enxuta: no máximo 3 dias, e só 2 horários por dia.
    # O agente NUNCA recebe a agenda inteira, então não tem como despejá-la.
    linhas = []
    for (dia, dbr) in ordem[:3]:
        horas = [h for h in por_dia[(dia, dbr)] if h][:2]
        if horas:
            linhas.append(f"- {dia} {dbr}: {', '.join(horas)}")
    return (
        "\n\n----------------------------------------------------------------"
        "\nAGENDA REAL — AMOSTRA DE HORÁRIOS LIVRES (consultada no Medware)"
        "\n----------------------------------------------------------------"
        "\nEstas são vagas LIVRES de verdade na agenda do médico."
        "\n\n⚠️ REGRA DE OURO — PRINCÍPIO DA ESCASSEZ:"
        "\n• Ofereça ao paciente NO MÁXIMO 2 horários por vez."
        "\n• NUNCA liste vários horários nem 'a agenda toda'. Despejar muitas"
        "\n  vagas passa a impressão de clínica vazia, destrói o senso de"
        "\n  oportunidade e derruba a conversão — é um erro grave."
        "\n• Escolha os 2 horários que MAIS combinam com a preferência de"
        "\n  dia/turno que o paciente já deu. Se ele ainda não deu preferência,"
        "\n  pergunte o melhor dia/turno ANTES de oferecer."
        "\n• Só se o paciente recusar os 2, aí ofereça outros 2."
        "\n• Nunca invente nem prometa horário fora desta lista."
        "\nEsta seção TEM PRECEDÊNCIA: havendo horário, o agente OFERECE"
        "\n(no máximo 2), não apenas coleta a preferência. Depois que o"
        "\npaciente escolher, confirme os dados e informe que a recepção"
        "\nfinaliza o agendamento."
        f"\n{chr(10).join(linhas)}"
        "\n----------------------------------------------------------------"
    )


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
        ) + _agenda_block(ctx)
    known = ctx.get("known") or {}
    nome = ctx.get("name")
    etapa = ctx.get("etapa")
    ja_agendado = bool(ctx.get("ja_agendado"))
    linhas = []
    rotulos = {
        "nome_paciente": "Nome do paciente", "motivo": "Motivo registrado",
        "convenio": "Convênio", "unidade": "Unidade", "medico": "Médico",
        "especialidade": "Especialidade", "dia_turno": "Preferência dia/turno",
    }
    for k, label in rotulos.items():
        if known.get(k):
            linhas.append(f"- {label}: {known[k]}")
    if etapa:
        linhas.append(f"- Etapa atual no funil: {etapa}")
    dados = "\n".join(linhas) if linhas else "- (lead existe, mas sem campos preenchidos ainda)"
    saudacao = (
        f'O CONTATO que está escrevendo se chama {nome}. Cumprimente '
        f'SEMPRE por esse nome — "Olá, {nome}!" — de forma calorosa. '
        f'ATENÇÃO: {nome} é o nome de QUEM ESCREVE; o paciente pode ser '
        f'outra pessoa (ex.: a mãe escreve, a consulta é do filho). '
        f'NUNCA cumprimente nem se dirija à pessoa usando o nome do '
        f'paciente — para isso, use só o nome do contato ({nome}).'
        if nome else "Há um lead existente para este contato."
    )
    alerta = ""
    if ja_agendado:
        alerta = (
            "\n"
            "\n⚠️ ATENÇÃO — ESTE LEAD JÁ TEM CONSULTA MARCADA/REALIZADA."
            f"\nA etapa do funil ({etapa}) confirma que o agendamento já existe."
            "\nEsta conversa NÃO é um novo agendamento. É confirmação de presença,"
            "\ndúvida ou ajuste sobre a consulta que JÁ ESTÁ marcada. É PROIBIDO"
            "\nrefazer a triagem — não pergunte de novo motivo, convênio, médico,"
            "\nunidade ou horário. Leia o histórico, entenda o que a pessoa precisa"
            "\nAGORA e responda só isso. Se não tiver certeza de algum dado, NÃO"
            "\nINVENTE — diga que vai verificar com a equipe."
        )
    return (
        "\n\n================================================================"
        "\nONBOARDING — CONTATO JÁ CONHECIDO PELO CRM"
        "\n================================================================"
        f"\n{saudacao}"
        "\nO CRM já tem estes dados deste contato:"
        f"\n{dados}"
        f"{alerta}"
        "\n"
        "\nREGRA: É PROIBIDO reperguntar qualquer dado já listado acima. Trate-os"
        "\ncomo confirmados e avance direto para a próxima etapa pendente do"
        "\nfluxo mestre (seção 0-B). Confirme de leve se fizer sentido"
        '("Você quer seguir com [convênio/médico] como da outra vez?"), mas'
        "\nnunca recolha de novo o que já está aqui."
        "\n================================================================"
    ) + _agenda_block(ctx)


def _sanitize_messages(msgs: list[dict]) -> list[dict]:
    """Devolve uma lista de mensagens SEMPRE válida para a API Anthropic.

    A API exige: começar com 'user', papéis alternados e conteúdo não
    vazio. Se o histórico salvo da conversa estiver corrompido (conteúdo
    vazio, papéis fora de ordem, dois 'user' seguidos), a chamada falha
    SEMPRE e a conversa trava para sempre. Esta função conserta o
    histórico em tempo de execução — a conversa se autocorrige na próxima
    mensagem: descarta conteúdo vazio, descarta 'assistant' inicial e
    funde mensagens consecutivas do mesmo papel.
    """
    out: list[dict] = []
    for m in msgs:
        role = m.get("role")
        content = str(m.get("content") or "").strip()
        if role not in ("user", "assistant") or not content:
            continue
        if not out and role != "user":
            continue  # a conversa precisa começar com 'user'
        if out and out[-1]["role"] == role:
            out[-1]["content"] = out[-1]["content"] + "\n" + content
        else:
            out.append({"role": role, "content": content})
    return out


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

        # 2. Monta system prompt = INSTRUÇÃO MESTRA + DATA DE HOJE +
        #    ONBOARDING + KB contextual.
        # NOTA: o bloco "JANELA DE OFERTA DE AGENDA" foi removido de
        # propósito — a Lia não oferece datas/horários, apenas coleta a
        # preferência do paciente (seção 12 da instrução mestra).
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
        messages = _sanitize_messages(
            history + [{"role": "user", "content": user_text}]
        )

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
                "pelo paciente ou pelo agente. Não invente. "
                "EXCEÇÃO — 'especialidade' e 'medico' DEVEM ser inferidos "
                "(não é inventar, é regra fixa da clínica): assim que o "
                "ASSUNTO ficar claro (anúncio, queixa ou motivo), preencha a "
                "especialidade; e, com a especialidade, preencha o médico "
                "correspondente pelo mapa fixo — mesmo que o paciente não "
                "tenha nomeado o médico. Isso vale já na PRIMEIRA mensagem "
                "de um lead de anúncio."
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
                    "cpf": {
                        "type": "string",
                        "description": (
                            "CPF do paciente que vai ser atendido, quando "
                            "informado na conversa. Aceite só dígitos ou o "
                            "formato 000.000.000-00. É o CPF de quem VAI ser "
                            "atendido, não necessariamente de quem escreve."
                        ),
                    },
                    "pacientes": {
                        "type": "array",
                        "description": (
                            "Lista de TODOS os pacientes que vão ser "
                            "atendidos nesta conversa — um item por pessoa. "
                            "Use sempre que houver paciente identificado; "
                            "ESSENCIAL quando há mais de um (ex.: uma mãe "
                            "agendando dois ou três filhos). O primeiro item "
                            "é o paciente principal e deve coincidir com os "
                            "campos 'name'/'birth_date_iso'/'cpf'/'reason'. "
                            "Inclua um paciente só com os dados realmente "
                            "ditos na conversa — não invente."
                        ),
                        "items": {
                            "type": "object",
                            "properties": {
                                "nome": {
                                    "type": "string",
                                    "description": "Nome completo deste paciente",
                                },
                                "birth_date_iso": {
                                    "type": "string",
                                    "description": "Data de nascimento YYYY-MM-DD",
                                },
                                "cpf": {
                                    "type": "string",
                                    "description": "CPF deste paciente (dígitos)",
                                },
                                "reason": {
                                    "type": "string",
                                    "description": "Motivo/queixa da consulta deste paciente",
                                },
                            },
                        },
                    },
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
                        "description": (
                            "Nome do médico. INFERIR pela especialidade "
                            "(mapa fixo da clínica), mesmo sem o paciente "
                            "nomear: Catarata / Refrativa / Lentes → "
                            "'Dr. Fabricio Freitas'; Oftalmopediatria / "
                            "Estrabismo / SDP / Oftalmologia Geral / consulta "
                            "de rotina → 'Dra. Karla Delalibera'; "
                            "Retina → 'Dra. Katia Delalibera'."
                        ),
                    },
                    "especialidade": {
                        "type": "string",
                        "description": (
                            "Inferir pelo assunto/anúncio/queixa já no "
                            "início: catarata, cirurgia de catarata, lente "
                            "intraocular → 'Catarata'; estrabismo → "
                            "'Estrabismo'; retina, mancha/sombra na visão → "
                            "'Retina'; criança/bebê/pediatria → "
                            "'Oftalmopediatria'; cirurgia para parar de usar "
                            "óculos → 'Refrativa'."
                        ),
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
                    "acoes": {
                        "type": "string",
                        "enum": ["Agendar Encaixe", "Agendar Domiciliar"],
                        "description": "Preencher SOMENTE se o atendimento virou um encaixe (paciente precisa de horário fora da grade normal / consulta já existente passou e quer novo atendimento rápido) ou consulta domiciliar. Caso contrário, NÃO incluir este campo.",
                    },
                    "nao_aceito_convenio": {
                        "type": "string",
                        "enum": [
                            "Afeb", "Amil", "Assefaz", "Bradesco", "BRB",
                            "Cassi", "Fusex", "GEAP", "HAP VIDA", "Inas GDF",
                            "Notre Dame", "PM", "Porto Seguro", "SUS",
                            "Sul América", "Unimed", "Outro",
                        ],
                        "description": "Preencher SOMENTE quando o paciente quis usar um convênio que a clínica NÃO credencia/aceita e, por causa disso, hesitou ou não seguiu com o agendamento. Informe qual convênio o paciente queria. Use 'Outro' se o convênio citado não estiver na lista. Se o paciente não citou convênio não aceito, NÃO incluir este campo.",
                    },
                    "motivo_perda": {
                        "type": "string",
                        "enum": ["Somente Convênio"],
                        "description": "Preencher SOMENTE quando o paciente deixou CLARO que NÃO vai prosseguir com o atendimento porque só aceita ser atendido por um convênio que a clínica não credencia — ou seja, o lead foi perdido por causa do convênio. Se o paciente ainda está decidindo, negociando, ou aberto ao atendimento particular, NÃO incluir este campo.",
                    },
                    "denominacao": {
                        "type": "string",
                        "description": "Rótulo CURTO (3 a 8 palavras) que resume a situação ATUAL do lead com base na última mensagem, para dar visibilidade rápida à equipe humana. Ex.: 'viu valor estrabismo, decidindo', 'quer pediatria sábado de manhã', 'pediu localização Águas Claras', 'aguardando data de nascimento'. Preencher sempre que houver conversa. Não incluir o nome do paciente nem prefixo de etapa.",
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
            "de nascimento ou idade foi dita.\n\n"
            "REGRA DA INFORMAÇÃO MAIS RECENTE: se um dado foi mencionado mais de "
            "uma vez, mudou, ou foi corrigido ao longo da conversa, use SEMPRE o "
            "valor MAIS RECENTE — a última vez que apareceu. Nunca use um valor "
            "antigo que já foi substituído. A conversa pode conter mais de uma "
            "tentativa de agendamento; o que vale é sempre o estado final.\n\n"
            "QUEM É O PACIENTE: o campo 'name' é o nome de quem VAI SER ATENDIDO. "
            "Pode ser diferente de quem está escrevendo — por exemplo, um familiar "
            "agendando para outra pessoa. Se a consulta é para outra pessoa, use o "
            "nome do paciente, NUNCA o de quem apenas enviou as mensagens.\n\n"
            "MÚLTIPLOS PACIENTES: sempre que houver um paciente identificado, "
            "preencha também a lista 'pacientes' — um item por pessoa que vai "
            "ser atendida. Quando uma mesma pessoa agenda para mais de alguém "
            "(ex.: mãe com dois ou três filhos), cada filho é um item da lista, "
            "com o nome, a data de nascimento e o CPF DAQUELE paciente. O "
            "primeiro item da lista é o paciente principal e deve bater com "
            "'name'/'birth_date_iso'/'cpf'. Associe cada CPF ao paciente certo; "
            "se um dado de um paciente ainda não foi dito, deixe-o em branco."
        )

        try:
            response = self._client.messages.create(
                model=self._haiku,
                max_tokens=1200,
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
