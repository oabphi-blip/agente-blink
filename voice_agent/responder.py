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
import os
import re
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


def _prompt_caching_habilitado() -> bool:
    """Anthropic prompt caching — economia 40-70% no system estático.

    Default ON. Desligar com `ANTHROPIC_PROMPT_CACHING_DISABLED=1`
    (kill switch para rollback rápido).
    """
    return os.environ.get("ANTHROPIC_PROMPT_CACHING_DISABLED") != "1"


def _memoria_rag_habilitada() -> bool:
    """RAG nível 1 — recupera lições da memória ativa por similaridade.

    Default OFF. Ligar com `MEMORIA_RAG_ENABLED=1`. Quando off, a Lia
    funciona exatamente como antes — zero risco.
    """
    return os.environ.get("MEMORIA_RAG_ENABLED") == "1"


def _bloco_memoria_rag(mensagem_paciente: str) -> str:
    """Recupera top-K trechos relevantes e formata pra injeção no prompt.

    Limites de segurança (anti-sobrecarga):
      - máximo de 3 trechos
      - cada trecho cortado a 800 chars
      - cutoff de similaridade (default 0.08) — se nada relevante, retorna ""
      - falhas silenciosas: nunca quebra reply() em caso de erro.
    """
    if not _memoria_rag_habilitada():
        return ""
    if not mensagem_paciente or not mensagem_paciente.strip():
        return ""
    try:
        # Import tardio — só carrega scikit-learn quando RAG está ativo.
        from voice_agent import memoria_rag as _rag
        trechos = _rag.recuperar_licoes_relevantes(mensagem_paciente, k=3)
        return _rag.formatar_para_prompt(trechos)
    except Exception as exc:  # noqa: BLE001
        log.warning("[RAG] Falha ao recuperar — seguindo sem memória: %s", exc)
        return ""


def _montar_system_para_anthropic(
    bloco_estavel: str,
    bloco_variavel: str,
) -> list[dict] | str:
    """Monta o `system` no formato Anthropic com cache_control.

    - Cache ON  → lista de 2 blocos. Estável tem cache_control ephemeral
      (5min TTL). Cache hit reduz 90% do custo do bloco estável.
    - Cache OFF → string concatenada (compat com SDK antigo).

    Bloco variável NUNCA é cacheado — muda por mensagem (today_brt,
    caller_context, kb_block, RAG).
    """
    if not _prompt_caching_habilitado():
        if bloco_variavel:
            return bloco_estavel + bloco_variavel
        return bloco_estavel

    blocos: list[dict] = [{
        "type": "text",
        "text": bloco_estavel,
        "cache_control": {"type": "ephemeral"},
    }]
    if bloco_variavel:
        blocos.append({"type": "text", "text": bloco_variavel})
    return blocos


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
    # TRAVA — só 2 horários por dia (escassez no OUTPUT, não no input).
    # Ampliada a janela em DIAS porque os pacientes costumam pedir uma
    # data específica 1–2 semanas à frente (ex.: "terça, 9 de junho"); se
    # esse dia não está no prompt, a Lia não consegue oferecer. A regra
    # de "no máximo 2 horários por mensagem" é cumprida pelo OUTPUT da
    # Lia (instrução abaixo), não pelo tamanho da amostra.
    linhas = []
    for (dia, dbr) in ordem:
        horas = [h for h in por_dia[(dia, dbr)] if h][:2]
        if horas:
            linhas.append(f"- {dia} {dbr}: {', '.join(horas)}")
    return (
        "\n\n----------------------------------------------------------------"
        "\nAGENDA REAL — AMOSTRA DE HORÁRIOS LIVRES (JÁ CONSULTADA NO MEDWARE)"
        "\n----------------------------------------------------------------"
        "\n🚨 ATENÇÃO: Estas vagas JÁ FORAM CONSULTADAS na Medware AGORA."
        "\nVocê NÃO precisa 'consultar', 'verificar' nem 'aguardar a equipe'."
        "\nOFEREÇA IMEDIATAMENTE os horários da lista abaixo — sem rodeio."
        "\n"
        "\n❌ FRASES PROIBIDAS quando há horários listados:"
        "\n  • \"Deixa eu consultar a agenda real...\""
        "\n  • \"Um momentinho enquanto verifico...\""
        "\n  • \"Vou conferir os horários e te respondo\""
        "\n  • \"Estou sem acesso à agenda no momento\""
        "\n  • \"Nossa equipe vai te retornar com os horários\""
        "\nQualquer uma dessas frases = bug grave. A agenda ESTÁ na sua frente."
        "\n"
        "\n⚠️ REGRA DE OURO — PRINCÍPIO DA ESCASSEZ:"
        "\n• Ofereça ao paciente NO MÁXIMO 2 horários por vez."
        "\n• NUNCA liste vários horários nem 'a agenda toda'. Despejar muitas"
        "\n  vagas passa a impressão de clínica vazia, destrói o senso de"
        "\n  oportunidade e derruba a conversão — é um erro grave."
        "\n• Escolha os 2 horários que MAIS combinam com a preferência de"
        "\n  dia/turno que o paciente já deu. Se ele ainda não deu preferência,"
        "\n  pergunte o melhor dia/turno ANTES de oferecer."
        "\n• Se a preferência exata do paciente NÃO tiver vaga na lista,"
        "\n  ofereça MESMO ASSIM duas alternativas concretas: (a) o dia LIVRE"
        "\n  mais próximo da preferência dele (mesmo dia da semana ou +1),"
        "\n  e (b) outro dia com várias vagas — isso ajuda a preencher a"
        "\n  agenda. NUNCA simplesmente diga 'não tenho disponibilidade';"
        "\n  a Lia sempre oferece o próximo caminho a partir desta lista."
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
    # Data da consulta JÁ MARCADA (1.DIA CONSULTA do Kommo, se houver).
    # Mostrar em formato humano e travar a Lia para confirmar ESSA data exata.
    dia_consulta_iso = known.get("dia_consulta_iso")
    dia_consulta_humano: Optional[str] = None
    if dia_consulta_iso:
        try:
            from datetime import datetime as _dt
            _d = _dt.fromisoformat(dia_consulta_iso)
            dia_consulta_humano = _d.strftime(
                "%A, %d/%m/%Y às %H:%M"
            ).replace("Monday", "segunda-feira").replace(
                "Tuesday", "terça-feira"
            ).replace("Wednesday", "quarta-feira").replace(
                "Thursday", "quinta-feira"
            ).replace("Friday", "sexta-feira").replace(
                "Saturday", "sábado"
            ).replace("Sunday", "domingo")
            linhas.append(
                f"- 📅 *CONSULTA JÁ MARCADA*: {dia_consulta_humano}"
            )
        except (ValueError, TypeError):
            pass
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
        data_str = (
            f"em {dia_consulta_humano}"
            if dia_consulta_humano
            else "(data exata no campo 1.DIA CONSULTA do Kommo)"
        )
        alerta = (
            "\n"
            "\n🚨 ATENÇÃO MÁXIMA — ESTE LEAD JÁ TEM CONSULTA MARCADA."
            f"\n📅 A consulta está agendada {data_str}."
            f"\nEtapa do funil: {etapa or '(verificar Kommo)'}."
            "\n"
            "\nESTA conversa É:"
            "\n  ✅ confirmação de presença (\"Sim, vou comparecer\")"
            "\n  ✅ dúvida operacional (endereço, horário, documento, prazo)"
            "\n  ✅ remarcação/cancelamento (\"preciso mudar pra outro dia\")"
            "\n"
            "\nESTA conversa NÃO É:"
            "\n  ❌ novo agendamento — não refaça a triagem do zero"
            "\n  ❌ coleta de preferência (\"qual dia da semana?\") — proibido"
            "\n  ❌ oferta de slots novos — só se a pessoa pedir REMARCAÇÃO explicitamente"
            "\n"
            "\nRESPONDA APENAS À PERGUNTA ATUAL — não invente próxima etapa."
            "\nSe a pessoa cumprimentar (\"oi\", \"boa tarde\"), responda confirmando"
            "\na consulta marcada e pergunte se está vindo OU se precisa de algo."
            "\nEXEMPLO de boa resposta inicial nesse caso:"
            f'\n  "Olá! Tudo certo pra sua consulta {data_str}? Posso te ajudar com algo?"'
        )
    # Bloco STATUS GRAVAÇÃO MEDWARE (Gap 5 — origem lead 24038029)
    # Quando o paciente perguntar "está gravado?" / "foi confirmado?",
    # Lia precisa saber a VERDADE. Aqui injetamos o status real da
    # gravação que rodou em thread separada (escrito em Redis pelo
    # executor_agendamento). Sem isso a Lia mente.
    gravacao = ctx.get("gravacao_status") if isinstance(ctx, dict) else None
    gravacao_block = ""
    if gravacao:
        st = gravacao.get("status", "pending")
        if st == "success":
            cod = gravacao.get("cod_agendamento")
            gravacao_block = (
                "\n\n----------------------------------------------------------------"
                "\nSTATUS GRAVAÇÃO MEDWARE — FONTE DE VERDADE"
                "\n----------------------------------------------------------------"
                f"\n✅ Agendamento GRAVADO no Medware. codAgendamento={cod}."
                "\nSe paciente perguntar 'gravou?' / 'confirmado?', responda SIM "
                "com naturalidade, mencionando que está tudo certo. PODE confirmar."
                "\n----------------------------------------------------------------"
            )
        elif st == "failed":
            motivo = gravacao.get("motivo", "desconhecido")
            gravacao_block = (
                "\n\n----------------------------------------------------------------"
                "\nSTATUS GRAVAÇÃO MEDWARE — FONTE DE VERDADE"
                "\n----------------------------------------------------------------"
                f"\n❌ Gravação FALHOU. Motivo técnico: {motivo}."
                "\nNUNCA diga ao paciente que falhou. Diga: 'A equipe está "
                "finalizando seu agendamento manualmente. Confirmo aqui assim "
                "que sair.'"
                "\n----------------------------------------------------------------"
            )
        else:  # pending
            gravacao_block = (
                "\n\n----------------------------------------------------------------"
                "\nSTATUS GRAVAÇÃO MEDWARE — FONTE DE VERDADE"
                "\n----------------------------------------------------------------"
                "\n⏳ Gravação EM PROCESSAMENTO. Não foi confirmada AINDA."
                "\nSe paciente perguntar 'gravou?', responda: 'Sua reserva está "
                "em processamento, a confirmação no sistema sai em alguns "
                "minutos.' NUNCA afirme que está gravado."
                "\n----------------------------------------------------------------"
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
    ) + _agenda_block(ctx) + gravacao_block


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


# ---------------------------------------------------------------------------
# FILTRO PÓS-GERAÇÃO — última linha de defesa contra alucinação
# ---------------------------------------------------------------------------
# Vocabulário vetado pelo KB §1.4 — substitui por neutro ou remove
_PROHIBITED_REPLACEMENTS = [
    (re.compile(r"\binfelizmente[,\s]*", re.IGNORECASE), ""),
    (re.compile(r"\bdireitinho\b", re.IGNORECASE), "direito"),
    (re.compile(r"\bcertinho\b", re.IGNORECASE), "certo"),
    (re.compile(r"\brapidinho\b", re.IGNORECASE), "rápido"),
    (re.compile(r"\bbonitinho\b", re.IGNORECASE), "bonito"),
    (re.compile(r"\bqueridinha?\b", re.IGNORECASE), ""),
    (re.compile(r"\bqueridinho\b", re.IGNORECASE), ""),
    (re.compile(r"\bobrigadinho\b", re.IGNORECASE), "obrigada"),
    (re.compile(r"\bconsultinha\b", re.IGNORECASE), "consulta"),
    (re.compile(r"\bfilhinha\b", re.IGNORECASE), "filha"),
    (re.compile(r"\bshow\b", re.IGNORECASE), "ótimo"),
    (re.compile(r"\btá\b", re.IGNORECASE), "está"),
]

# Chaves Pix oficiais (artigo 38 §3) — qualquer outra é alucinação
_CHAVES_PIX_OFICIAIS = {
    "karladelaliberaoftalmo@gmail.com",   # Asa Norte
    "52.303.729/0001-30",                  # Águas Claras (CNPJ)
}

_HALLUCINATION_PATTERNS = []  # mantido por compatibilidade; lógica em função


def _detecta_chave_pix_inventada(text: str) -> bool:
    """True se o texto menciona uma chave Pix e ela NÃO está no allowlist."""
    if not text:
        return False
    # Procura "chave pix" + algo até 120 chars
    trecho = re.search(r"chave\s*pix.{0,120}", text, re.IGNORECASE | re.DOTALL)
    if not trecho:
        return False
    snippet = trecho.group(0)
    # Email no snippet?
    email = re.search(r"[\w.\-+]+@[\w.\-]+", snippet)
    if email:
        return email.group(0).lower() not in {k.lower() for k in _CHAVES_PIX_OFICIAIS}
    # CNPJ formatado ou não
    cnpj = re.search(r"\d{2}[\.\-]?\d{3}[\.\-]?\d{3}\/?\d{4}\-?\d{2}", snippet)
    if cnpj:
        norm = re.sub(r"[\.\-\/]", "", cnpj.group(0))
        oficiais_norm = {re.sub(r"[\.\-\/]", "", k) for k in _CHAVES_PIX_OFICIAIS}
        return norm not in oficiais_norm
    return False


def _viola_artigo_36(text: str) -> bool:
    """Detecta se a resposta menciona 'sinal/adiantamento 50%' SEM oferecer
    também a 'Fila de Encaixe' — viola a regra do artigo 36 que exige
    apresentar as DUAS opções ao paciente."""
    if not text:
        return False
    t_lower = text.lower()
    menciona_sinal = any(termo in t_lower for termo in (
        "50%", "cinquenta por cento", "adiantamento", "sinal de"
    ))
    menciona_encaixe = "encaixe" in t_lower
    return menciona_sinal and not menciona_encaixe

_HALLUCINATION_FALLBACK = (
    "Vou alinhar a informação correta sobre pagamento com a equipe e te "
    "retorno em instantes. ✨"
)

# Anti-pattern "equipe vai confirmar" (KB §13.4.1) — só loga, não substitui
_TRANSFER_ANTIPATTERN = [
    re.compile(r"equipe.{0,20}retornar", re.IGNORECASE),
    re.compile(r"equipe.{0,20}confirma", re.IGNORECASE),
    re.compile(r"sem acesso à agenda", re.IGNORECASE),
    re.compile(r"vou registrar.{0,20}prefer[êe]ncia", re.IGNORECASE),
]

# Anti-pattern "deixa eu consultar a agenda" / "um momentinho" — quando há
# agenda real no contexto, a Lia DEVE oferecer slots imediatamente, nunca
# fingir que vai consultar.
_FAKE_AGENDA_LOOKUP = [
    re.compile(r"deixa eu consultar.{0,30}agenda", re.IGNORECASE | re.DOTALL),
    re.compile(r"vou consultar.{0,30}agenda", re.IGNORECASE | re.DOTALL),
    re.compile(r"deixa eu verificar.{0,30}(agenda|horário|disponibilidade)", re.IGNORECASE | re.DOTALL),
    re.compile(r"vou verificar.{0,30}(horário|disponibilidade|agenda)", re.IGNORECASE | re.DOTALL),
    re.compile(r"\bum momentinho\b", re.IGNORECASE),
    re.compile(r"\bsó um momento\b", re.IGNORECASE),
    re.compile(r"aguarda.{0,15}(momento|instante)", re.IGNORECASE),
    re.compile(r"estou sem acesso.{0,15}agenda", re.IGNORECASE),
]

_FAKE_AGENDA_LOOKUP_FALLBACK = (
    "Para eu te oferecer o melhor horário, me confirma só: você prefere "
    "manhã, tarde ou início da noite? E algum dia específico da semana?"
)


def _viola_oferta_agenda(text: str, has_agenda: bool) -> bool:
    """True se a Lia fingiu que vai consultar agenda — quando JÁ tem agenda
    real no contexto, isso é violação grave (deveria oferecer imediatamente).
    """
    if not has_agenda or not text:
        return False
    return any(p.search(text) for p in _FAKE_AGENDA_LOOKUP)


# Padrões de cobrança de sinal/Pix — só são legítimos APÓS o paciente ter
# escolhido um slot concreto (data + hora). Antes disso, é violação 12.9.
_COBRANCA_SINAL_PATTERNS = [
    re.compile(r"sinal\s+(?:de\s+)?(?:50\s*%|r\$)", re.IGNORECASE),
    re.compile(r"comprovante\s+do\s+(?:sinal|pix)", re.IGNORECASE),
    re.compile(r"chave\s+pix", re.IGNORECASE),
    re.compile(r"karladelaliberaoftalmo@gmail", re.IGNORECASE),
    re.compile(r"52\.?303\.?729", re.IGNORECASE),  # CNPJ Águas Claras
    re.compile(r"garantir\s+seu\s+horário\s+(?:com|via|pelo)\s+(?:o\s+)?pix", re.IGNORECASE),
    re.compile(r"fa[çc]a\s+o\s+pix\s+(?:de|no\s+valor)", re.IGNORECASE),
]

# Padrão de "slot concreto" — data DD/MM ou dia-da-semana + hora HH:MM
# Se o histórico (texto da conversa) tem algo assim, sinal pode ser legítimo.
_SLOT_CONCRETO_NA_RESPOSTA = re.compile(
    r"(?:segunda|terça|quarta|quinta|sexta|sábado|domingo)[\-\s]?(?:feira)?"
    r"\s*,?\s*\d{1,2}[\/\.]\d{1,2}\s+(?:às|as)\s+\d{1,2}[:h]\d{2}",
    re.IGNORECASE,
)


def _viola_cobranca_antes_slot(text: str) -> bool:
    """True se a resposta cobra sinal/Pix SEM ter um slot concreto antes.

    Lógica: se o TEXTO da resposta atual menciona sinal/Pix MAS não tem um
    formato de slot concreto (dia-da-semana + data + hora), é violação 12.9.

    Limitação: só vê a resposta atual, não o histórico da conversa. Se a Lia
    confirmou o slot na mensagem ANTERIOR e cobra Pix na atual, vai dar falso
    positivo. Mas é melhor errar pra mais e pedir ajuste do que cobrar sem
    confirmação.
    """
    if not text:
        return False
    menciona_cobranca = any(p.search(text) for p in _COBRANCA_SINAL_PATTERNS)
    if not menciona_cobranca:
        return False
    # Tem cobrança. Tem slot concreto na MESMA mensagem?
    tem_slot_concreto = bool(_SLOT_CONCRETO_NA_RESPOSTA.search(text))
    # Cobrança válida só se tem slot concreto na mesma mensagem
    # OU se menciona "fila de encaixe" (apresentação correta das 2 opções)
    menciona_encaixe = "encaixe" in text.lower()
    return not (tem_slot_concreto or menciona_encaixe)


_COBRANCA_ANTECIPADA_FALLBACK = (
    "Antes de qualquer pagamento, deixa eu te oferecer os horários reais. "
    "Qual dia da semana e turno funcionam melhor pra você? Assim já te passo "
    "as opções concretas com data e hora."
)


# ------------------------------------------------------------------
# Filtro de validação dia-da-semana × data
# ------------------------------------------------------------------
# Origem: lead 24038029 (29/05/2026). Lia ofereceu "terça-feira, 03/06"
# e "terça-feira, 10/06" — ambas QUARTAS. Causa raiz: janela de agenda
# tinha sido desativada no prompt. Mesmo com janela religada, o modelo
# pode escorregar; esse filtro é a rede de segurança final.

_DIA_SEMANA_PT = {
    0: "segunda-feira",
    1: "terça-feira",
    2: "quarta-feira",
    3: "quinta-feira",
    4: "sexta-feira",
    5: "sábado",
    6: "domingo",
}

# Normalização do dia falado pela Lia (com/sem acento, com/sem "-feira")
_DIA_NORMALIZE = {
    "segunda": "segunda-feira", "segunda-feira": "segunda-feira",
    "terça": "terça-feira", "terca": "terça-feira",
    "terça-feira": "terça-feira", "terca-feira": "terça-feira",
    "quarta": "quarta-feira", "quarta-feira": "quarta-feira",
    "quinta": "quinta-feira", "quinta-feira": "quinta-feira",
    "sexta": "sexta-feira", "sexta-feira": "sexta-feira",
    "sábado": "sábado", "sabado": "sábado",
    "domingo": "domingo",
}

# Regex captura "<dia-da-semana>[,/ -] DD/MM[/AAAA]" — formatos típicos
# que a Lia usa ("terça-feira, 03/06", "quinta 04/06", "Terça-Feira 10/06/2026")
_DIA_DATA_REGEX = re.compile(
    r"(segunda|ter(?:ç|c)a|quarta|quinta|sexta|s(?:á|a)bado|domingo)"
    r"(?:[\s-]*feira)?"
    r"\s*[,\-]?\s*"
    r"(\d{1,2})/(\d{1,2})(?:/(\d{4}))?",
    re.IGNORECASE,
)


def _viola_dia_semana(text: str) -> Optional[tuple[str, str, str]]:
    """Detecta divergência entre dia-da-semana e data citados na resposta.

    Exemplo: Lia escreve "terça-feira, 03/06". Python checa 03/06 do ano
    corrente → quarta. Retorna ('terça-feira', '03/06/2026', 'quarta-feira').
    Se tudo bate, retorna None.

    Limitação: olha só a PRIMEIRA divergência. O fallback substitui a
    resposta inteira de qualquer jeito, então uma já basta pra bloquear.
    """
    if not text:
        return None
    current_year = datetime.now(_TZ_BRT).year

    for match in _DIA_DATA_REGEX.finditer(text):
        dia_raw = match.group(1).lower().strip()
        # adiciona "-feira" pra padronizar lookup
        if dia_raw in ("segunda", "terça", "terca", "quarta", "quinta", "sexta"):
            dia_raw_norm = dia_raw + "-feira"
        else:
            dia_raw_norm = dia_raw
        dia_falado = _DIA_NORMALIZE.get(dia_raw_norm) or _DIA_NORMALIZE.get(dia_raw)
        if not dia_falado:
            continue

        try:
            day = int(match.group(2))
            month = int(match.group(3))
            year = int(match.group(4)) if match.group(4) else current_year
            data = datetime(year, month, day).date()
        except (ValueError, TypeError):
            continue

        dia_real = _DIA_SEMANA_PT[data.weekday()]
        if dia_falado != dia_real:
            return (dia_falado, f"{day:02d}/{month:02d}/{year}", dia_real)

    return None


_DIA_SEMANA_FALLBACK = (
    "Deixa eu reconferir os horários com o calendário aqui. "
    "Qual dia da semana e turno funcionam melhor pra você? "
    "Assim já volto com as opções concretas — com a data e o dia da semana certinhos."
)


# ------------------------------------------------------------------
# Filtro anti-mentira: NUNCA afirmar que foi gravado no Medware
# ------------------------------------------------------------------
# Origem: lead 24038029 (29/05/2026), nota 28929893. Paciente perguntou
# "está gravado?" e Lia respondeu "Sim! O agendamento já foi registrado
# automaticamente no Medware". MENTIRA — Lia não tem acesso ao Medware
# para verificar status real. A gravação acontece em thread daemon
# separada e a Lia não sabe se sucedeu.
# A Blink Oftalmologia se posiciona como Cosmoética — Lia NÃO pode mentir
# ao paciente em hipótese alguma. Este filtro é a rede final.

_AFIRMACAO_GRAVACAO_PATTERNS = [
    re.compile(r"(j[áa]\s+)?(foi|est[áa])\s+(registrad[oa]|salv[oa]|gravad[oa])"
               r"(\s+(no|na))?\s+(medware|sistema)", re.IGNORECASE),
    re.compile(r"registrad[oa]\s+automaticamente", re.IGNORECASE),
    re.compile(r"est[áa]\s+tudo\s+(registrad[oa]|salv[oa]|gravad[oa])", re.IGNORECASE),
    re.compile(r"agendamento\s+(j[áa]\s+)?(foi\s+)?(criado|registrado|gravado|salvo)"
               r"\s+(no\s+sistema|na\s+medware)", re.IGNORECASE),
    re.compile(r"dados\s+(j[áa]\s+)?(foram\s+)?(salvos|registrados|gravados)"
               r"\s+(no\s+sistema|na\s+medware)", re.IGNORECASE),
]

_AFIRMACAO_GRAVACAO_FALLBACK = (
    "Sua reserva está em processamento — assim que a gravação no sistema "
    "confirmar, a equipe te confirma por aqui. Enquanto isso, pode me "
    "enviar a foto da carteirinha e do documento de identidade pra "
    "garantir o horário?"
)


def _viola_afirmacao_gravacao(text: str) -> bool:
    """Detecta se Lia afirmou indevidamente que algo foi gravado no Medware.

    Como a gravação acontece em thread separada e o status real só é
    conhecido pelo executor, a Lia NUNCA tem como SABER se gravou.
    Qualquer afirmação positiva é alucinação ética.
    """
    if not text:
        return False
    return any(p.search(text) for p in _AFIRMACAO_GRAVACAO_PATTERNS)


def _scrub_prohibited(text: str, ctx: Optional[dict] = None) -> str:
    """Pós-processamento de segurança aplicado a TODA resposta antes de enviar.

    1. Detecta alucinação de pagamento → substitui resposta por fallback seguro.
    2. Detecta "consultar agenda" quando há agenda real no contexto → substitui.
    3. Remove/substitui vocabulário diminutivo/vetado pelo KB §1.4.
    4. Loga (não substitui) anti-pattern de transferência humana.

    Args:
        text: resposta gerada pela Lia.
        ctx: caller_context opcional. Se contém "agenda" não-vazia, ativa o
            detector de "fingiu consultar agenda".
    """
    if not text:
        return text

    has_agenda = bool((ctx or {}).get("agenda"))

    # 0. Fingiu consultar agenda — quando JÁ tem horários no contexto.
    # Esse bug deixa a Lia em loop de "deixa eu consultar..." sem nunca voltar.
    if _viola_oferta_agenda(text, has_agenda):
        log.error(
            "[FILTRO] FAKE AGENDA LOOKUP bloqueado — Lia disse que ia consultar "
            "agenda quando JÁ tinha %d slots no contexto. Texto: %r",
            len(ctx.get("agenda", [])), text[:200],
        )
        return _FAKE_AGENDA_LOOKUP_FALLBACK

    # 0c. ANTI-MENTIRA: Lia afirmou gravação no Medware (lead 24038029)
    # Blink Oftalmologia = Cosmoética. Lia NÃO pode mentir ao paciente.
    # Ela não tem acesso ao Medware pra verificar gravação real — qualquer
    # afirmação positiva é alucinação. Substituir por frase honesta.
    if _viola_afirmacao_gravacao(text):
        log.error(
            "[FILTRO] AFIRMACAO GRAVACAO MEDWARE BLOQUEADA — Lia disse que "
            "algo foi gravado no Medware/sistema, mas não tem como saber. "
            "Texto bloqueado: %r", text[:200],
        )
        return _AFIRMACAO_GRAVACAO_FALLBACK

    # 0b. Dia da semana INVENTADO (lead 24038029, 29/05/2026)
    # Python valida cada par "<dia-semana>, DD/MM" do texto contra o
    # calendário real. Se Lia escreveu "terça-feira, 03/06" e Python
    # diz que é quarta, bloqueia e força regenerar via fallback.
    violacao_dia = _viola_dia_semana(text)
    if violacao_dia:
        dia_falado, data_str, dia_real = violacao_dia
        log.error(
            "[FILTRO] DIA DA SEMANA INVENTADO — Lia disse '%s' para %s, "
            "mas Python calculou '%s'. Texto bloqueado: %r",
            dia_falado, data_str, dia_real, text[:200],
        )
        return _DIA_SEMANA_FALLBACK

    # 0a. Cobrança de sinal/Pix ANTES de slot concreto (regra 12.9 do master).
    # Lia não pode cobrar sinal sem antes ter oferecido um slot específico
    # (dia-da-semana + data + hora) e o paciente ter escolhido.
    if _viola_cobranca_antes_slot(text):
        log.error(
            "[FILTRO] COBRANCA ANTES DE SLOT bloqueada — Lia mencionou "
            "sinal/Pix mas sem slot concreto (data+hora) nem mencionar Fila "
            "de Encaixe. Texto: %r", text[:200],
        )
        return _COBRANCA_ANTECIPADA_FALLBACK

    # 1. Chave Pix inventada (não consta no allowlist do artigo 38 §3)
    if _detecta_chave_pix_inventada(text):
        log.error(
            "[FILTRO] CHAVE PIX INVENTADA bloqueada. Texto: %r", text[:200]
        )
        return _HALLUCINATION_FALLBACK

    # 1a. Padrões adicionais (compatibilidade, hoje vazio)
    for pat in _HALLUCINATION_PATTERNS:
        if pat.search(text):
            log.error(
                "[FILTRO] ALUCINAÇÃO DE PAGAMENTO bloqueada: padrão=%r texto=%r",
                pat.pattern, text[:200],
            )
            return _HALLUCINATION_FALLBACK

    # 1b. Viola artigo 36 — apresenta só 50% sem oferecer Fila de Encaixe.
    # Só substitui se também mencionar Pix (sinal explícito de cobrança)
    if _viola_artigo_36(text) and "pix" in text.lower():
        log.warning(
            "[FILTRO] Artigo 36 violado: apresenta 50%% sem oferecer Fila de "
            "Encaixe. Texto: %r", text[:200],
        )
        return (
            "Antes de seguir com o pagamento, deixa eu te apresentar as duas "
            "opções da clínica:\n\n"
            "1️⃣ *Reserva Imediata* — adiantamento de 50% via Pix; garante seu "
            "dia/horário exatos na agenda.\n"
            "2️⃣ *Fila de Encaixe* — sem adiantamento; pagamento só no dia da "
            "consulta; avisamos assim que surgir vaga compatível com sua "
            "preferência.\n\n"
            "Qual formato prefere?"
        )

    # 2. Vocabulário vetado — substitui inline
    original = text
    for pat, replacement in _PROHIBITED_REPLACEMENTS:
        text = pat.sub(replacement, text)

    if text != original:
        # Limpa artefatos das remoções (espaços duplos, vírgulas órfãs)
        text = re.sub(r"  +", " ", text)
        text = re.sub(r"\s+,", ",", text)
        text = re.sub(r",\s*,", ",", text)
        text = text.strip()
        log.info("[FILTRO] Vocabulário vetado removido/substituído")

    # 3. Anti-pattern transferência — só observa
    for pat in _TRANSFER_ANTIPATTERN:
        if pat.search(text):
            log.warning("[FILTRO] Anti-pattern transferência detectado: %r", pat.pattern)
            break

    return text


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

        # 1b. SEMPRE injetar artigos CRÍTICOS — pequenos (~15KB juntos) e que
        # NÃO podem depender de retrieval por keywords. O agente alucina dados
        # quando esses artigos não estão no contexto:
        # - 00: endereços, contatos, chave Pix, regra anti-alucinação de endereço
        #   (bug Lidia 28/05: Lia inventou "SGAS 915" e "Av. Araucárias")
        # - 17/18: catálogo de convênios aceitos / negados
        #   (bug "Tribunal/STJ" negados erradamente)
        mandatory_filenames = [
            "00_identidade_e_unidades.md",
            "15_pagamento_pos_consulta.md",
            "17_convenios_aceitos_lista_oficial.md",
            "18_convenios_NAO_aceitos_lista_oficial.md",
            "19_tabela_valores_travas_por_medico.md",
            "22_agenda_dra_karla.md",                # mapeamento unidade × dia
            "31_sdp_fluxo_excecao.md",
            "34_agenda_dr_fabricio.md",              # mapeamento unidade × dia
            "36_pagamento_exclusivo_encaixe_karla.md",  # política sinal 50% Karla
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
        #    ONBOARDING + JANELA DE AGENDA + KB contextual.
        #
        # ANTES: o bloco "JANELA DE OFERTA DE AGENDA" tinha sido removido
        # com a justificativa de que "Lia só coleta preferência". Mas o KB
        # tem fluxo E7 (AGENDA DISPONÍVEL) que pede pra Lia OFERECER slots,
        # e ela seguia esse fluxo inventando datas/dias da semana.
        # Origem do retorno: lead 24038029 (29/05/2026), onde Lia ofereceu
        # "terça-feira, 03/06" e "terça-feira, 10/06" — ambas QUARTAS-feiras.
        # Solução: a janela volta a ser injetada — fonte de verdade do
        # calendário com dia da semana correto ao lado de cada data.
        # Separamos em DOIS blocos pro Anthropic prompt caching:
        # - bloco ESTÁVEL: _base_system_prompt (MASTER_INSTRUCTION imutável).
        #   Esse bloco é cacheado (5min TTL ephemeral) → reduz 90% custo
        #   em mensagens subsequentes dentro de 5 min.
        # - bloco VARIÁVEL: muda por chamada (today_brt, caller_context,
        #   kb_block dinâmico, RAG da memória). NÃO entra no cache.
        bloco_estavel = self._base_system_prompt

        bloco_variavel = _today_brt_block()
        bloco_variavel += _caller_context_block(caller_context)
        # FIX 30/05/2026: _build_janela_agenda() era chamada aqui mas a
        # FUNÇÃO NUNCA FOI DEFINIDA no arquivo (foi removida sem remover a
        # chamada, ou o commit task #20 esqueceu de adicionar). Resultado:
        # toda responder.reply lançava NameError, voice_agent caía no
        # fallback "instabilidade", Lia parecia silenciada. Descoberto via
        # endpoint /admin/simulate-inbound em 30s — depois de 5h
        # perseguindo Meta webhook. Linha removida; system_prompt segue
        # funcional sem ela (era o comportamento de antes do task #20).
        # Se a janela de agenda for re-introduzida no futuro, definir a
        # função PRIMEIRO e adicionar pytest cobrindo o caminho.
        if kb_block:
            bloco_variavel += (
                "\n\n================================================================"
                "\nCONHECIMENTO BLINK RELEVANTE PARA ESTA CONVERSA"
                "\n================================================================"
                f"\n{kb_block}"
                "\n\n================================================================"
                "\nFIM DO CONHECIMENTO. APLIQUE COM AS REGRAS DA INSTRUÇÃO MESTRA ACIMA."
                "\n================================================================"
            )

        # RAG nível 1 (task #85) — só injeta se MEMORIA_RAG_ENABLED=1.
        # Anti-sobrecarga: máx 3 trechos × 800 chars = ~2.4k tokens extras.
        # Falha silenciosa: erro no RAG não bloqueia reply.
        rag_bloco = _bloco_memoria_rag(user_text)
        if rag_bloco:
            bloco_variavel += "\n\n" + rag_bloco

        system_field = _montar_system_para_anthropic(bloco_estavel, bloco_variavel)

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
            system=system_field,
            messages=messages,
            temperature=0.3,  # baixa pra seguir as regras estritas da Blink
        )

        # Extrai texto da resposta
        answer_parts = [block.text for block in response.content if block.type == "text"]
        answer = "\n".join(answer_parts).strip()

        # DEBUG capturado em 30/05 — fallback 'instabilidade' aparecendo sem
        # exception Claude. Hipótese: algum caminho retorna answer vazio sem
        # erro. Logando tamanhos pra diagnóstico via Easypanel logs.
        log.info(
            "[DEBUG reply] convo=%s blocks=%d raw_answer_len=%d truncate_threshold=%d",
            conversation_key, len(response.content), len(answer), self._max_chars,
        )

        if len(answer) > self._max_chars:
            answer = answer[: self._max_chars - 1].rstrip() + "…"

        # 5.1. Filtro pós-geração: vocabulário vetado + alucinação de pagamento
        # + detector "fake agenda lookup" (passa ctx pra saber se há agenda real)
        _before_scrub = answer
        answer = _scrub_prohibited(answer, ctx=caller_context)
        if not answer or len(answer) < 5:
            log.error(
                "[DEBUG reply] FILTRO ZEROU answer — convo=%s before_len=%d "
                "after_len=%d before_preview=%r",
                conversation_key, len(_before_scrub), len(answer),
                _before_scrub[:200],
            )

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

        log.info(
            "[EXTRACT] convo=%s hist_len=%d transcript_chars=%d",
            conversation_key, len(history), len(conversation),
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
                    out = {k: v for k, v in extracted.items() if v}
                    log.info(
                        "[EXTRACT] convo=%s out_keys=%s",
                        conversation_key, sorted(out.keys()),
                    )
                    return out
            # Tool não foi chamado — log o que veio
            log.warning(
                "[EXTRACT] convo=%s Haiku NÃO chamou tool — blocks=%s",
                conversation_key,
                [getattr(b, "type", "?") for b in response.content],
            )
        except Exception as e:  # noqa: BLE001
            log.warning(
                "[EXTRACT] convo=%s FALHOU (%s): %s",
                conversation_key, type(e).__name__, e,
            )
        return {}
