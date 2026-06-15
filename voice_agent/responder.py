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
from .zep_adapter import recuperar_contexto as _zep_recuperar, gravar_turno as _zep_gravar

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
    # Avaliação do Processamento Visual / Estrabismo / Prisma
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
    """Bloco de HORÁRIOS REAIS — vagas livres consultadas no Medware.

    Quando NÃO há agenda no contexto (Medware silencioso, lento ou
    sem slots), entrega instrução POSITIVA pra Lia pedir 1min ao
    paciente, em vez de inventar "vou registrar pra equipe finalizar".
    Origem do FIX: lead 24053159 Juliene (31/05/2026).
    """
    agenda = (ctx or {}).get("agenda") or []
    if not agenda:
        return (
            "\n\n----------------------------------------------------------------"
            "\nAGENDA INDISPONÍVEL NESTE MOMENTO (CACHE/MEDWARE LENTO)"
            "\n----------------------------------------------------------------"
            "\n⚠️ O Medware não devolveu slots agora — pode ser lentidão"
            "\ntemporária da API, JWT vencido OU médico/unidade ainda não"
            "\nidentificados na conversa."
            "\n"
            "\n🚨 PROIBIDO inventar um caminho 'humano':"
            "\n  • 'Vou registrar sua preferência para a equipe finalizar'"
            "\n  • 'Retorno em horário comercial (seg–sex, 8h–18h)'"
            "\n  • 'A equipe entra em contato' / 'Nossa recepção retoma'"
            "\n  • 'Vou encaminhar para a equipe humana'"
            "\n"
            "\n✅ CAMINHO CERTO quando agenda está indisponível:"
            "\n"
            "\nResponda com SUAS PRÓPRIAS PALAVRAS (NÃO copie textos prontos)"
            "\numa frase humana e calorosa que comunique 3 ideias:"
            "\n  1) reconhecer que precisa reconsultar a agenda"
            "\n  2) pedir um curto instante (poucos minutos)"
            "\n  3) prometer voltar com opções concretas (dia + data + hora)"
            "\n"
            "\nIMPORTANTE — DIVERSIFIQUE as palavras a cada conversa: NÃO"
            "\nuse a mesma frase 2x seguidas em diferentes pacientes."
            "\nÉ proibido pedir 'responde oi' — peça paciência e diga que"
            "\nVOCÊ volta com as opções (sem precisar resposta dele)."
            "\n"
            "\nIdeias de tom (varie):"
            "\n  - 'Me dá 1 minuto que eu volto com os horários reais'"
            "\n  - 'Vou puxar a agenda exata aqui e já te respondo'"
            "\n  - 'Deixa eu confirmar os horários disponíveis e volto'"
            "\n----------------------------------------------------------------"
        )
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
        "\n⚠️ REGRA DE OURO — OFERTA IMEDIATA DE 2 SLOTS (revisão 03/06/2026):"
        "\n• Assim que houver agenda + médico + unidade definidos no ctx,"
        "\n  OFEREÇA imediatamente 2 horários concretos."
        "\n• **PROIBIDO perguntar 'qual turno', 'qual período do turno',"
        "\n  'qual dia da semana' ANTES de oferecer.** Erro grave de UX —"
        "\n  paciente quer ver opções, não responder formulário."
        "\n• Escolha os 2 slots assim:"
        "\n   (a) Se houver vaga em MANHÃ (hora < 12:00) e TARDE (≥ 12:00)"
        "\n       dentro dos próximos dias úteis, escolha 1 de cada turno"
        "\n       — o mais próximo possível. (Caso ideal para Alice/Carol,"
        "\n       Sabrina, etc. — atende qualquer agenda do paciente.)"
        "\n   (b) Se só houver de um turno, escolha os 2 mais próximos"
        "\n       desse turno."
        "\n   (c) Se já há `dia_turno` na preferência do paciente vinda do"
        "\n       Kommo, use isso como filtro extra."
        "\n• Formato humano da oferta (mantenha esse padrão):"
        "\n     'Tenho 2 horários abertos com a {{MÉDICO}}, {{UNIDADE}}:'"
        "\n     '1️⃣ {{dia}} ({{data}}) às {{hora1}}'"
        "\n     '2️⃣ {{dia}} ({{data}}) às {{hora2}}'"
        "\n     'Algum desses cabe pra você? Se preferir outro dia/horário,"
        "\n     me diz que ajusto.'"
        "\n• NUNCA liste a agenda toda. NUNCA mais de 2 horários por mensagem."
        "\n"
        "\n⚠️ SEQUÊNCIA OBRIGATÓRIA (Bug C-18 — Fábio 10/06/2026):"
        "\n  PASSO 1: oferta 2 slots concretos (regra acima)."
        "\n  PASSO 2: SE — e SOMENTE SE — o paciente RECUSAR os 2 slots OU"
        "\n            pedir dia/hora específico que não está na oferta,"
        "\n            AÍ SIM pergunte juntos NUMA SÓ mensagem:"
        "\n               'Qual dia da semana, qual turno (manhã/tarde) e"
        "\n               qual período do turno (início, meio ou fim) fica"
        "\n               melhor pra você?'"
        "\n            JÁ NO CONTEXTO certo: com {{MÉDICO}}, na {{UNIDADE}}."
        "\n  PASSO 3: com a resposta da preferência, escolha 2 NOVOS slots"
        "\n            que casem com dia+turno+período pedidos."
        "\n"
        "\nObjetivo da sequência: AGILIDADE. Mostrar opções concretas primeiro"
        "\n(o paciente quer ver, não responder formulário). Só quando NÃO der"
        "\nmatch, pergunte preferência — e pergunte uma vez só, sem ficar"
        "\nindo e vindo sem definição. O paciente NÃO carrega 3 decisões"
        "\nseparadas (dia → turno → período em 3 turnos). Tudo em UMA pergunta."
        "\n• Se paciente pedir DIA/HORA específicos (ex: 'sexta às 9h'):"
        "\n  procure na lista abaixo. Se tiver, oferece esse. Se NÃO tiver,"
        "\n  diga isso E ofereça o mais próximo da preferência dele."
        "\n• Nunca invente nem prometa horário fora desta lista."
        "\nEsta seção TEM PRECEDÊNCIA: havendo horário, o agente OFERECE"
        "\n(2 slots em formato 1️⃣/2️⃣), não pergunta turno/período. Depois"
        "\nque o paciente escolher, confirme os dados e informe que a"
        "\nrecepção finaliza o agendamento."
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

    # SAUDAÇÃO COM PROVA DE ESCUTA (Bug C-27 — Fábio 12/06/2026)
    # Quando há dados conhecidos do paciente, gera saudação personalizada
    # que cita até 4 campos (nome paciente, médico, convênio, unidade) e
    # demonstra reconhecimento. Substitui triagem do zero.
    saudacao_sugerida_block = ""
    try:
        from voice_agent.ativacao_inteligente import gerar_saudacao_de_ctx
        result = gerar_saudacao_de_ctx(ctx)
        if result.get("tipo") in ("personalizada", "lacuna_longa"):
            saudacao_sugerida_block = (
                "\n\nSAUDAÇÃO INICIAL SUGERIDA (regra E1.7-A — prova de escuta):\n"
                "Quando esta é a PRIMEIRA mensagem que você envia pro paciente "
                "nesta conversa, USE A SAUDAÇÃO ABAIXO em vez de triagem do "
                "zero. Ela demonstra que você sabe quem é, recapitula onde "
                "parou, e abre pra próxima etapa:\n\n"
                f"\"{result.get('saudacao')}\"\n\n"
                "DEPOIS disso, prossiga conforme o fluxo normal (E2..E9). "
                "Se o paciente já enviou conteúdo concreto na mensagem "
                "atual, RESPONDA O CONTEÚDO em vez de só saudar — mas "
                "ainda assim cite o que já sabemos dele (ex.: 'Vi aqui que "
                "era com Dra. Karla pelo {convenio}'). Anti-constrangimento: "
                "se {ancora_principal} for citado, NÃO repergunte essa "
                "informação."
            ).replace("{convenio}", str(known.get("convenio") or "convênio"))\
             .replace("{ancora_principal}", str(result.get("ancora_principal") or "dado conhecido"))
    except Exception:  # noqa: BLE001
        pass
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

    # Checklist dados mínimos (task #123, origem lead Juliene 24053159).
    # Se ainda falta dado essencial, INJETA bloco PRÉ-AGENDA antes do
    # _agenda_block — proíbe oferta de slot até dados completos.
    pre_agenda_block = ""
    checklist = ctx.get("checklist_dados_minimos") if isinstance(ctx, dict) else None
    if checklist and not checklist.get("pronto_para_oferecer_slot", True):
        try:
            from voice_agent.checklist_dados_minimos import (
                ChecklistResultado,
                render_bloco_pre_agenda,
            )
            _resultado = ChecklistResultado(
                nome_completo_ok=checklist.get("nome_completo_ok", False),
                data_nascimento_ok=checklist.get("data_nascimento_ok", False),
                cpf_ok=checklist.get("cpf_ok", False),
                convenio_definido_ok=checklist.get("convenio_definido_ok", False),
                campos_pendentes=tuple(checklist.get("campos_pendentes", [])),
            )
            pre_agenda_block = render_bloco_pre_agenda(_resultado)
        except Exception:  # noqa: BLE001
            pre_agenda_block = ""

    # Bloco TRAVA MÉDICO/UNIDADE (origem lead Diones 23742328 — 01/06/2026).
    # Caso: ctx tinha 'Médico: Dra. Karla Delalibera' mas Lia ofereceu
    # slots de Fabricio. Bloco explícito + regex pós-geração impedem.
    trava_medico = ""
    if known.get("medico") or known.get("unidade"):
        partes = []
        if known.get("medico"):
            partes.append(f"MÉDICO: **{known['medico']}** (NÃO trocar)")
        if known.get("unidade"):
            partes.append(f"UNIDADE: **{known['unidade']}** (NÃO trocar)")
        if known.get("dia_turno"):
            partes.append(f"PREFERÊNCIA dia/turno: **{known['dia_turno']}** (respeitar)")
        trava_medico = (
            "\n\n----------------------------------------------------------------"
            "\nTRAVA MÉDICO/UNIDADE — FONTE DE VERDADE"
            "\n----------------------------------------------------------------"
            "\n🚨 ESTES VALORES JÁ ESTÃO REGISTRADOS PARA ESTE PACIENTE:"
            "\n  • " + "\n  • ".join(partes)
            + "\n"
            "\n⚠️ PROIBIDO oferecer slot de OUTRO médico, OUTRA unidade,"
            "\nou ignorar a preferência de dia/turno acima."
            "\nSe a AGENDA REAL injetada abaixo trouxer slots de outro médico,"
            "\nFILTRE manualmente e ofereça SÓ os do médico acima."
            "\nSe NÃO houver slot do médico correto na lista, diga ao paciente"
            "\nhonestamente: 'No momento não tenho horários de {médico} disponíveis"
            "\nem {unidade} na sua preferência — me dá 2 minutos pra reconsultar"
            "\nas datas e turnos completos.' (Não invente dias da semana)."
            "\n"
            "\n❌ PROIBIDO inventar dias fixos de atendimento (ex: 'Karla atende"
            "\nterças e quintas') — a fonte é APENAS a AGENDA REAL abaixo."
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
        f"{trava_medico}"
        f"{saudacao_sugerida_block}"
        "\n"
        "\nREGRA: É PROIBIDO reperguntar qualquer dado já listado acima. Trate-os"
        "\ncomo confirmados e avance direto para a próxima etapa pendente do"
        "\nfluxo mestre (seção 0-B). Confirme de leve se fizer sentido"
        '("Você quer seguir com [convênio/médico] como da outra vez?"), mas'
        "\nnunca recolha de novo o que já está aqui."
        "\n================================================================"
    ) + pre_agenda_block + _agenda_block(ctx) + gravacao_block


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
    "manhã ou tarde? E algum dia específico da semana?"
)


def _viola_oferta_agenda(text: str, has_agenda: bool) -> bool:
    """True se a Lia fingiu que vai consultar agenda — quando JÁ tem agenda
    real no contexto, isso é violação grave (deveria oferecer imediatamente).
    """
    if not has_agenda or not text:
        return False
    return any(p.search(text) for p in _FAKE_AGENDA_LOOKUP)


# ------------------------------------------------------------------
# Filtro: perguntou turno/período quando tinha agenda real (Alice 21256807)
# ------------------------------------------------------------------
# Origem: lead 21256807 Alice (03/06/2026 22:09). Tudo já preenchido
# (nome, idade, médico, unidade, convênio, motivo) — Lia perguntou
# "Manhã ou Tarde? Início, Meio ou Fim do turno?" em vez de oferecer
# 2 slots reais. Fluxo aprovado por Fábio: ofertar primeiro, perguntar
# preferência só se paciente recusar os 2 ou pedir dia/hora específicos.

_PERGUNTA_TURNO_PERIODO_PATTERNS = [
    re.compile(r"manh[ãa]\s+ou\s+tarde", re.IGNORECASE),
    # "qual seu turno", "qual é o turno", "qual o turno", etc.
    re.compile(r"qual\b.{0,20}\b(turno|per[ií]odo)\b", re.IGNORECASE | re.DOTALL),
    re.compile(r"prefer[êe]ncia\s+de\s+(turno|per[ií]odo|dia)", re.IGNORECASE),
    re.compile(r"in[ií]cio[,\s].{0,12}meio.{0,12}fim", re.IGNORECASE | re.DOTALL),
    re.compile(r"per[ií]odo:\s*(in[ií]cio|meio|fim)", re.IGNORECASE),
    re.compile(r"\bturno:\s*(manh[ãa]|tarde)", re.IGNORECASE),
]


def _viola_pergunta_turno_periodo_com_agenda(
    text: str,
    ctx: Optional[dict],
) -> bool:
    """True se Lia perguntou turno/período TENDO agenda real no ctx.

    Política Blink (03/06/2026): com agenda em mãos, OFERECER 2 slots
    (1 manhã + 1 tarde quando possível) ANTES de perguntar preferência.
    """
    if not text:
        return False
    has_agenda = bool((ctx or {}).get("agenda"))
    if not has_agenda:
        return False
    return any(p.search(text) for p in _PERGUNTA_TURNO_PERIODO_PATTERNS)


def _selecionar_2_slots_inteligente(agenda: list) -> list:
    """Pega 2 slots ótimos: 1 manhã + 1 tarde se possível; senão 2 do mesmo turno.

    Manhã = hora < 12:00. Tarde = hora >= 12:00.
    Prioriza datas mais próximas (assume agenda já ordenada cronologicamente).
    """
    if not agenda:
        return []

    def _hora_int(s: dict) -> int:
        try:
            return int(str(s.get("hora", "00:00"))[:2])
        except (ValueError, TypeError):
            return 0

    manha = [s for s in agenda if _hora_int(s) < 12]
    tarde = [s for s in agenda if _hora_int(s) >= 12]
    if manha and tarde:
        return [manha[0], tarde[0]]
    return list(agenda[:2])


def _gerar_oferta_2_slots(ctx: Optional[dict]) -> str:
    """Constrói a mensagem humana com 2 slots (substituindo pergunta de turno)."""
    agenda = (ctx or {}).get("agenda") or []
    dois = _selecionar_2_slots_inteligente(agenda)
    if not dois:
        # Sem agenda — recai num fallback honesto.
        return (
            "Deixa eu reconferir a agenda real aqui e já volto com 2 horários "
            "concretos pra você escolher. Me dá só 1 minuto."
        )
    known = ((ctx or {}).get("known") or {})
    medico = (ctx or {}).get("medico") or known.get("medico") or "a médica"
    unidade = known.get("unidade") or "a unidade combinada"
    linhas = []
    for i, s in enumerate(dois, start=1):
        dia = s.get("dia_semana", "").capitalize() if s.get("dia_semana") else ""
        dbr = s.get("data_br", "")
        hora = s.get("hora", "")
        emoji = "1️⃣" if i == 1 else "2️⃣"
        prefixo = f"{dia} ({dbr})" if dia and dbr else dbr
        linhas.append(f"{emoji} {prefixo} às {hora}")
    return (
        f"Tenho 2 horários abertos com a {medico}, {unidade}:\n\n"
        + "\n".join(linhas)
        + "\n\nAlgum desses cabe pra você? Se preferir outro dia/horário, "
        "me diz que ajusto."
    )


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

# Regex captura "<dia-da-semana>[,/ -()] DD/MM[/AAAA]" — formatos típicos
# que a Lia usa:
#   "terça-feira, 03/06" (caso Aurora/Sabrina maio/26)
#   "quinta 04/06"
#   "Terça-Feira 10/06/2026"
#   "sexta-feira (06/06)" (caso Priscila lead 24055629, 03/06/2026 — bug que escapou
#                          do regex original porque ele NÃO aceitava parênteses
#                          antes da data; agora a classe [\s,\-()\[\]*] cobre todos
#                          os separadores observados em prod)
_DIA_DATA_REGEX = re.compile(
    r"(segunda|ter(?:ç|c)a|quarta|quinta|sexta|s(?:á|a)bado|domingo)"
    r"(?:[\s-]*feira)?"
    r"[\s,\-()\[\]*]*"
    r"(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?",
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
            year_raw = match.group(4)
            if year_raw:
                year = int(year_raw)
                if year < 100:
                    year += 2000  # "26" → 2026
            else:
                year = current_year
            data = datetime(year, month, day).date()
        except (ValueError, TypeError):
            # Data inválida (ex: 31/02) — conta como violação, paciente
            # vai ficar confuso. Substitui pelo fallback.
            return ("data_invalida", f"{match.group(2)}/{match.group(3)}", "data inválida")

        # Se a data inferida cair muito no passado (>30 dias atrás), Lia
        # provavelmente quis dizer o próximo ano (oferta de janeiro do ano
        # que vem em dezembro, p.ex.). Reavalia com year+1.
        hoje = datetime.now(_TZ_BRT).date()
        if not match.group(4) and (hoje - data).days > 30:
            try:
                data = datetime(year + 1, month, day).date()
            except ValueError:
                pass

        dia_real = _DIA_SEMANA_PT[data.weekday()]
        if dia_falado != dia_real:
            return (dia_falado, f"{day:02d}/{month:02d}/{data.year}", dia_real)

    return None


_DIA_SEMANA_FALLBACK = (
    "Deixa eu reconferir os horários com o calendário aqui. "
    "Qual dia da semana e turno funcionam melhor pra você? "
    "Assim já volto com as opções concretas — com a data e o dia da semana certinhos."
)


# ------------------------------------------------------------------
# Filtro: oferta em dia que o médico NÃO atende
# ------------------------------------------------------------------
# Origem: lead 24055629 Priscila (01/06/2026 12:30). Lia ofereceu
# "9h de sexta-feira (06/06)" — 06/06 é SÁBADO, e Dra. Karla NÃO atende
# sábado. Paciente questionou: "Dia 5, sexta ou 6, sábado?".
# O _viola_dia_semana cobre a divergência data↔dia-semana, mas não
# bloqueia oferta em dia que o médico simplesmente não trabalha.
# Esta é a segunda rede.

# Mapa weekday() (0=segunda ... 6=domingo) → dias atendidos por médico.
# Fonte: política operacional Blink + Medware (Karla seg-sex; Fabrício
# ter/qui; Kátia em pausa).
_DIAS_ATENDIMENTO_POR_MEDICO = {
    "karla": {0, 1, 2, 3, 4},      # seg-sex
    "fabricio": {1, 3},             # ter, qui
    "fabrício": {1, 3},
    "katia": set(),                  # em pausa
    "kátia": set(),
}


def _normaliza_medico(nome: Optional[str]) -> str:
    if not nome:
        return ""
    return nome.lower().replace("dra.", "").replace("dr.", "").replace(
        "delalibera", ""
    ).replace("freitas", "").replace("pacheco", "").strip().split()[0] if nome.strip() else ""


def _viola_oferta_em_dia_nao_atendido(
    text: str,
    ctx: Optional[dict] = None,
) -> Optional[tuple[str, str, str]]:
    """Detecta oferta em data que cai em dia que o médico não atende.

    Retorna (medico_norm, "DD/MM/YYYY", dia_semana_real) ou None.
    """
    if not text:
        return None
    medico_raw = ((ctx or {}).get("medico") or "").lower()
    # Pega só o primeiro nome — alinha com o mapa
    medico_norm = ""
    for m in _DIAS_ATENDIMENTO_POR_MEDICO:
        if m in medico_raw:
            medico_norm = m
            break
    if not medico_norm:
        return None  # médico desconhecido — não bloqueia (evita falso positivo)

    permitidos = _DIAS_ATENDIMENTO_POR_MEDICO[medico_norm]
    if not permitidos:
        # Médico em pausa — qualquer oferta é violação
        permitidos = set()

    hoje = datetime.now(_TZ_BRT).date()
    current_year = hoje.year

    for match in _DIA_DATA_REGEX.finditer(text):
        try:
            day = int(match.group(2))
            month = int(match.group(3))
            year_raw = match.group(4)
            if year_raw:
                year = int(year_raw)
                if year < 100:
                    year += 2000
            else:
                year = current_year
            data = datetime(year, month, day).date()
            if not year_raw and (hoje - data).days > 30:
                data = datetime(year + 1, month, day).date()
        except (ValueError, TypeError):
            continue

        if data.weekday() not in permitidos:
            return (medico_norm, data.strftime("%d/%m/%Y"),
                    _DIA_SEMANA_PT[data.weekday()])

    return None


_DIA_NAO_ATENDIDO_FALLBACK = (
    "Deixa eu reconferir a agenda — preciso confirmar os dias que esse "
    "médico atende essa semana. Qual turno funciona melhor pra você "
    "(manhã ou tarde)? Volto em 1 minuto com horários certos."
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


# ------------------------------------------------------------------
# Filtro MÉDICO TROCADO — origem lead Diones 23742328 (01/06/2026)
# ------------------------------------------------------------------
# Bug: ctx tinha 'Médico: Dra. Karla Delalibera' mas Lia ofereceu
# slots com Dr. Fabrício Freitas. Padrão clássico de alucinação:
# Medware retornou slots de outro médico e Lia ofereceu sem cruzar
# com o que está no ONBOARDING.
#
# Detecção: se ctx.known.medico contém "Karla" mas resposta menciona
# "Fabricio" como médico atendente, é violação. (Vice-versa também.)
_RE_KARLA_NA_RESPOSTA = re.compile(
    r"\b(?:dra?\.?\s+)?karla\b", re.IGNORECASE,
)
_RE_FABRICIO_NA_RESPOSTA = re.compile(
    r"\b(?:dr\.?\s+)?fabr[íi]cio\b", re.IGNORECASE,
)


def _viola_medico_trocado(
    text: str, ctx: Optional[dict] = None,
) -> Optional[str]:
    """True se Lia ofereceu/mencionou médico diferente do ONBOARDING.

    Retorna o motivo ('ctx=karla mas resposta=fabricio' etc) ou None.
    """
    if not text or not ctx:
        return None
    known = (ctx or {}).get("known") or {}
    medico_ctx = (known.get("medico") or "").lower()
    if not medico_ctx:
        return None
    tem_karla_resp = bool(_RE_KARLA_NA_RESPOSTA.search(text))
    tem_fabr_resp = bool(_RE_FABRICIO_NA_RESPOSTA.search(text))
    if "karla" in medico_ctx and tem_fabr_resp and not tem_karla_resp:
        return "ctx=karla mas resposta menciona fabricio"
    if "fabr" in medico_ctx and tem_karla_resp and not tem_fabr_resp:
        return "ctx=fabricio mas resposta menciona karla"
    return None


_MEDICO_TROCADO_FALLBACK = (
    "Deixa eu reconferir aqui qual médico você tinha preferência. "
    "Pode me confirmar o nome do médico que você quer atender? Assim "
    "eu te trago os horários certos."
)


# ------------------------------------------------------------------
# Filtro PROMESSA DE RETORNO HUMANO — origem lead 24053159 (31/05/2026)
# ------------------------------------------------------------------
# Bug: Juliene escolheu Terça/manhã/meio. Lia recebeu ctx["agenda"]
# VAZIO (Medware sem slots, ou silenciado) e inventou:
#   "Vou registrar sua preferência para a equipe finalizar
#    — retorno em horário comercial (seg–sex, 8h–18h)."
# Frase não existe em nenhum arquivo do voice_agent — alucinação pura
# que driblou os outros 4 filtros (não menciona "consultar", não cobra
# Pix, não afirma gravação, não tem dia-da-semana).
#
# Cosmoética Blink: NUNCA fingir que a equipe humana vai retomar quando
# isso não está garantido. Ou Lia oferece slot real, ou pede ao paciente
# aguardar 1 minuto enquanto ela busca de novo.
_PROMETE_RETORNO_HUMANO_PATTERNS = [
    re.compile(
        r"registrar(?:ei)?\s+(?:sua|a)\s+prefer[êe]ncia.{0,40}equipe.{0,40}finaliza",
        re.IGNORECASE | re.DOTALL,
    ),
    re.compile(
        r"prefer[êe]ncia\s+(?:para|pra)\s+(?:a\s+)?equipe.{0,40}finaliza",
        re.IGNORECASE | re.DOTALL,
    ),
    re.compile(
        r"retorno\s+em\s+hor[áa]rio\s+comercial",
        re.IGNORECASE,
    ),
    re.compile(
        r"equipe\s+(?:humana|finaliza|entra(?:r[áa])?\s+em\s+contato).{0,80}"
        r"hor[áa]rio\s+comercial",
        re.IGNORECASE | re.DOTALL,
    ),
    re.compile(
        r"seg(?:unda)?[\s\-]*(?:a|para|–|-|à)?\s*sex(?:ta)?.{0,60}(?:8h|08h).{0,15}18h",
        re.IGNORECASE | re.DOTALL,
    ),
]


def _viola_promete_retorno_humano(text: str) -> bool:
    """True se a Lia inventou que a equipe humana vai finalizar/retornar.

    Pega o padrão "vou registrar preferência → equipe finaliza → retorno
    em horário comercial" e variações. Tem que ser bloqueado SEMPRE
    porque é evasão: ou Lia oferece slot real agora, ou pede 1 min para
    re-consultar.
    """
    if not text:
        return False
    return any(p.search(text) for p in _PROMETE_RETORNO_HUMANO_PATTERNS)


# Fallback quando NÃO há agenda real no contexto — Lia diz a verdade:
# que está re-consultando, e pede 1 minuto.
_PROMETE_RETORNO_HUMANO_FALLBACK_SEM_AGENDA = (
    "Deixa eu reconsultar a agenda real aqui pra você. "
    "Me responde 'oi' em 1 minuto que eu volto com 2 opções concretas — "
    "dia, data e hora — pra você escolher."
)


# ------------------------------------------------------------------
# Filtro PERGUNTA REDUNDANTE DE CONVÊNIO
# Origem: lead 24063769 Adriana (02/06/2026). Paciente perguntou
# valor, Lia perguntou 4x: "convênio ou sem?", "quem?", "convênio?",
# "motivo?". Convênio JÁ ESTAVA preenchido no ctx ("Não se aplica" =
# particular). Lia ignorou o ctx e fez triagem redundante.
# ------------------------------------------------------------------
_RE_PERGUNTA_CONVENIO = re.compile(
    r"(com\s+conv[êe]nio\s+ou\s+sem|"
    r"ser[áa]?\s+por\s+conv[êe]nio|"
    r"\bsem\s+conv[êe]nio\b\s*\?|"
    r"qual\s+(?:o\s+seu\s+)?conv[êe]nio|"
    r"(?:vai|voc[êe])\s+usar\s+conv[êe]nio|"
    r"(?:é|eh)\s+(?:por\s+)?conv[êe]nio)",
    re.IGNORECASE,
)


def _viola_pergunta_redundante_convenio(
    text: str, ctx: Optional[dict] = None,
) -> bool:
    """True se Lia perguntou sobre convênio quando ctx já tem.

    Cobre o cenário Adriana 24063769: ctx.known.convenio preenchido
    (qualquer valor, incluindo "Não se aplica") + Lia pergunta de
    novo. Pergunta redundante.
    """
    if not text or not ctx:
        return False
    known = (ctx or {}).get("known") or {}
    convenio_ja_conhecido = known.get("convenio")
    if not convenio_ja_conhecido:
        return False
    return bool(_RE_PERGUNTA_CONVENIO.search(text))


def _gerar_resposta_valor_sem_repergunta(ctx: Optional[dict]) -> str:
    """Gera resposta orientada a próxima ação — sem repergunta de
    convênio. Usa o que já está no ctx pra falar do valor certo."""
    if not ctx:
        ctx = {}
    known = ctx.get("known") or {}
    medico = known.get("medico") or ""
    especialidade = known.get("especialidade") or ""
    convenio = known.get("convenio") or ""
    # Decide qual valor mencionar baseado no ctx
    if "fabr" in medico.lower() or "catarata" in especialidade.lower():
        valor_str = "R$ 297 (avaliação com Dr. Fabrício Freitas)"
    elif "sdp" in especialidade.lower() or "aprend" in especialidade.lower():
        valor_str = "R$ 800 (Avaliação do Processamento Visual — Dra. Karla)"
    elif "karla" in medico.lower() or medico:
        valor_str = "R$ 611 (consulta com Dra. Karla Delalibera)"
    else:
        # Sem médico definido — passa tabela inteira
        return (
            "Os valores são:\n"
            "• Consulta Dra. Karla (rotina, oftalmopediatria, "
            "estrabismo): **R$ 611**\n"
            "• Avaliação catarata Dr. Fabrício: **R$ 297**\n"
            "• Avaliação do Processamento Visual (Dra. Karla): **R$ 800**\n\n"
            "Qual desses atendimentos interessa pra você? "
            "Já te passo o horário."
        )
    # Convênio já conhecido — usa ele
    if convenio and convenio not in ("Não se aplica", "", "Particular"):
        return (
            f"Pelo seu convênio ({convenio}) a consulta é coberta — "
            "você não paga direto à clínica (pode ter co-participação "
            "dependendo do plano). Quer seguir pro horário?"
        )
    # Particular
    return (
        f"O valor da consulta é **{valor_str}**, pagamento via Pix. "
        "Quer já ver os horários disponíveis?"
    )


# ------------------------------------------------------------------
# Filtro OFERTA DE SLOT APÓS JÁ TER AGENDADO
# Origem: lead 24060221 Esther Dias Guimarães (01/06/2026 17:39 BRT).
# ------------------------------------------------------------------
# Cenário: Esther já tinha consulta gravada (5-AGENDADO em 09/06 às
# 18:30 com Karla, Águas Claras). Paciente enviou foto da carteirinha.
# Handler de imagem do webhook gerou o user_text sintético:
#     "[Paciente enviou imagem (...). Confirme o recebimento de forma
#     calorosa, diga que a equipe vai conferir, e siga o atendimento
#     normalmente.]"
# O "siga o atendimento normalmente" foi interpretado pelo LLM como
# permissão pra re-oferecer slots. Resposta produzida:
#     "Recebi, obrigado! Nossa equipe vai conferir os documentos.
#     Enquanto isso, deixa eu trazer os horários disponíveis para a
#     Esther com a Dra. Karla em Águas Claras no início da noite.
#     Me dá só mais um instante! ⏳"
# A TRAVA "🚨 JÁ TEM CONSULTA MARCADA" estava injetada no prompt MAS
# o LLM priorizou a instrução no user_text. Filtro pós-geração é a
# defesa final.
_OFERTA_POS_AGENDADO_PATTERNS = [
    # "deixa eu trazer / buscar / consultar os horários"
    re.compile(
        r"(?:deixa\s+eu|vou)\s+(?:trazer|buscar|consultar|listar|"
        r"verificar|olhar|mostrar)\s+(?:os?|a)\s+(?:hor[áa]rios?|agenda|"
        r"op[çc][õo]es?|disponibilidad[es]?)",
        re.IGNORECASE,
    ),
    # "horários disponíveis para / com a Dra"
    re.compile(
        r"hor[áa]rios?\s+dispon[íi]ve(?:l|is).{0,30}(?:para|pra|com)",
        re.IGNORECASE | re.DOTALL,
    ),
    # "tenho essas opções com" (oferta de slots)
    re.compile(
        r"tenho\s+(?:essas|estas|as)?\s*(?:duas|2|tr[êe]s|3)?\s*op[çc][õo]es?",
        re.IGNORECASE,
    ),
    # "vou consultar a agenda" (mesmo de _viola_oferta_agenda, mas
    # aqui dispara independente de has_agenda — basta ja_agendado)
    re.compile(
        r"vou\s+(?:consultar|verificar|buscar|olhar)\s+(?:a|na)\s+agenda",
        re.IGNORECASE,
    ),
    # "1️⃣ ... 2️⃣ ..." formatação de lista de slots
    re.compile(r"1️⃣.{0,200}2️⃣", re.IGNORECASE | re.DOTALL),
    # "quer agendar / posso agendar" (re-coleta)
    re.compile(
        r"(?:quer|gostaria|posso)\s+(?:de\s+)?agendar",
        re.IGNORECASE,
    ),
    # Pergunta de coleta nova de preferência: "qual (dia|turno|período)
    # você (prefere|gostaria|deseja)" ou "manhã ou tarde/noite"
    re.compile(
        r"qual\s+(?:dia|turno|per[íi]odo|hor[áa]rio).{0,40}"
        r"(?:prefere|gostaria|deseja|escolhe|quer|prefer[êe]ncia)",
        re.IGNORECASE | re.DOTALL,
    ),
    re.compile(
        r"(?:manh[ãa]|tarde|noite|in[íi]cio\s+da\s+noite).{0,20}"
        r"(?:ou|/)\s*(?:tarde|noite|manh[ãa])",
        re.IGNORECASE,
    ),
]


def _viola_oferta_apos_agendado(
    text: str, ctx: Optional[dict] = None,
) -> bool:
    """True se Lia ofereceu/quis oferecer slot novo num lead JÁ AGENDADO.

    Dispara SOMENTE quando ctx.ja_agendado=True (status_id em
    ST_JA_AGENDADO OU 1.DIA CONSULTA no futuro). É independente do
    has_agenda do `_viola_oferta_agenda` — aqui o problema não é fingir
    consultar; é refazer triagem sobre lead já fechado.
    """
    if not text or not ctx:
        return False
    if not ctx.get("ja_agendado"):
        return False
    return any(p.search(text) for p in _OFERTA_POS_AGENDADO_PATTERNS)


# ────────────────────────────────────────────────────────────────────────
# Filtro CONFIRMAÇÃO-FAKE (caso Carolina 24145994 + Carmen 24142996)
# ────────────────────────────────────────────────────────────────────────
# Lia envia "✨ Agendamento confirmado!" com dia/hora/médica/unidade SEM ter
# chamado medware.criar_agendamento. Bug recorrente: paciente recebe
# confirmação de algo que não existe; depois Lia entra em loop "vou
# reconsultar". Detecta padrão "Agendamento confirmado" + "Dia/Hora" no
# texto e bloqueia se ctx.medware_grava_ok != True.
_FRASES_CONFIRMACAO_RGX = re.compile(
    r"(?:✨|✅|\bagendamento\b)\s*(?:confirmad[oa]|"
    r"finalizad[oa]|conclu[íi]d[oa])",
    re.IGNORECASE,
)
_MARCADORES_CONCLUSAO_RGX = re.compile(
    r"(?:dia/hora|dia\s+da\s+consulta|hor[áa]rio\s+marcado|"
    r"unidade\s+de\s+atendimento)",
    re.IGNORECASE,
)


def _viola_confirmacao_sem_gravacao(
    text: str, ctx: Optional[dict] = None,
) -> bool:
    """True se Lia confirmou agendamento sem ter gravado no Medware."""
    if not text:
        return False
    if not _FRASES_CONFIRMACAO_RGX.search(text):
        return False
    if not _MARCADORES_CONCLUSAO_RGX.search(text):
        # frase de confirmação sem detalhes operacionais — provavelmente
        # acknowledgment genérico, não conclusão real. Não bloqueia.
        return False
    if not ctx:
        # sem ctx pra confirmar gravação, é mais seguro bloquear
        return True
    return not bool(ctx.get("medware_grava_ok"))


_CONFIRMACAO_FAKE_FALLBACK = (
    "Deixa eu finalizar a gravação no sistema primeiro — volto em 1 minuto "
    "com a confirmação oficial. Se em 2 min eu não voltar, me chama "
    "que escalo pra equipe humana imediatamente."
)


def _gerar_oferta_pos_agendado_fallback(ctx: Optional[dict]) -> str:
    """Fallback informa data marcada (se conhecida) + agradece doc/contato."""
    if not ctx:
        ctx = {}
    known = ctx.get("known") or {}
    nome = known.get("nome_paciente") or ""
    dia_iso = known.get("dia_consulta_iso")
    data_humano = ""
    if dia_iso:
        try:
            from datetime import datetime as _dt
            _d = _dt.fromisoformat(dia_iso)
            data_humano = _d.strftime("%d/%m às %H:%M")
        except (ValueError, TypeError):
            data_humano = ""
    paciente_str = f" da {nome}" if nome else ""
    if data_humano:
        marcada = f" já está marcada para **{data_humano}**"
    else:
        marcada = " já está marcada (data no campo 1.DIA CONSULTA)"
    return (
        f"Recebi, obrigada! A consulta{paciente_str}{marcada}. "
        "Nossa equipe vai conferir tudo. Se precisar **remarcar** ou "
        "**cancelar**, é só me avisar — caso contrário, te espero "
        "no dia marcado!"
    )


# ────────────────────────────────────────────────────────────────────────
# Bug C-16 — Inas / convênios NÃO ACEITOS
# ────────────────────────────────────────────────────────────────────────
# Lead 24117314 Maria Agostini (08/06/2026 11:41 BRT).
# Lia respondeu "Perfeito! Atendemos o INAS GDF" + perguntou data nasc pra
# "solicitar autorização do convênio". KB artigo 18 marca Inas como NÃO
# ACEITO sem exceção. Causa raiz: enum Kommo CONVÊNIO 925312 tem texto
# enganoso "Inas GDf (somente Dr. Fabrício Freitas)" — Lia leu literal e
# tratou como aceito com restrição. Filtro pós-geração é a defesa final.

# Lista canônica de convênios NÃO aceitos (extraída de KB 18, lowercase).
# Cada item tem variantes; matching por substring case-insensitive.
_CONVENIOS_NAO_ACEITOS_KB18 = frozenset({
    "afeb", "afego", "amil", "assefaz", "asete", "aste",
    "bradesco", "brb",
    "cassi", "caeme", "caesan", "camed", "cnti",
    "eletronorte", "embratel",
    "fusex", "fapes",
    "geap", "golden",
    "hapvida", "hap vida", "hap-vida",
    "inas", "gdf inas", "inas gdf", "inas-gdf", "gdf saúde", "gdf saude",
    "gdf",  # token isolado — quase sempre se refere ao GDF Saúde (Bug C-22 Sandra)
    "notre dame", "notredame",
    "polícia militar", "policia militar", "porto seguro",
    "quality",
    "sul américa", "sul america", "sulamérica", "sulamerica", "sul-américa",
    "sus",
    "unimed", "unafisco", "sindifisco",
})

# Padrões de AFIRMAÇÃO POSITIVA sobre convênio: "atendemos", "cobrimos",
# "aceitamos", "credenciamos", "está na rede". Tolerantes a pontuação.
_AFIRMACAO_ATENDE_CONVENIO_PATTERNS = (
    re.compile(r"\b(atende[mr]o?s?|atende[mr]?)\b.{0,40}\b(o\s+)?", re.IGNORECASE),
    re.compile(r"\b(cobr[ei]mos|cobertura\s+do)\b", re.IGNORECASE),
    re.compile(r"\b(aceita?mos|aceito|aceita)\b", re.IGNORECASE),
    re.compile(r"\b(credenci(amos|ado|ada))\b", re.IGNORECASE),
    re.compile(r"\b(est[áa]\s+na\s+(nossa\s+)?rede)\b", re.IGNORECASE),
)


def _detectar_convenio_nao_aceito_no_texto(text: str) -> Optional[str]:
    """Retorna o convênio NÃO aceito mencionado no texto, ou None.

    Match case-insensitive contra `_CONVENIOS_NAO_ACEITOS_KB18`. Retorna
    a chave canônica curta que casou (pra log/teste). Quando texto tem
    variantes longas e curtas (ex: "inas gdf"), retorna a CURTA ("inas").
    Itera por ordem crescente de tamanho pra dar prioridade à forma curta.
    """
    if not text:
        return None
    low = text.lower()
    for conv in sorted(_CONVENIOS_NAO_ACEITOS_KB18, key=len):
        if conv in low:
            return conv
    return None


def _viola_disse_atende_convenio_nao_aceito(
    text: str, ctx: Optional[dict] = None,
) -> Optional[str]:
    """True+nome se Lia afirmou que atendemos convênio listado em KB 18.

    Caso real: lead 24117314 — Lia disse "Perfeito! Atendemos o INAS GDF".
    Detecta combinação: (afirmação positiva) AND (convênio não aceito).
    Retorna o convênio que casou, pra log + script de transição.
    """
    if not text:
        return None
    conv = _detectar_convenio_nao_aceito_no_texto(text)
    if not conv:
        return None
    low = text.lower()
    # Precisa ter afirmação positiva — não basta mencionar o nome.
    # Caso negativo (queremos evitar falso-positivo): "infelizmente NÃO
    # atendemos Inas" não viola — é correto. Padrões cobrem:
    #   - "não atendemos/cobrimos/aceitamos/credenciamos"
    #   - "não está credenciada/coberto/na rede"
    #   - "não cobre"
    _NEGATIVE = (
        r"\bn[ãa]o\s+(atende|cobr|aceit|credenc"
        r"|est[áa]\s+(credenc|coberto|cobert|na\s+(nossa\s+)?rede)"
        r"|cobre\b"
        r")"
    )
    if re.search(_NEGATIVE, low):
        return None
    if not any(p.search(text) for p in _AFIRMACAO_ATENDE_CONVENIO_PATTERNS):
        return None
    return conv


def _gerar_script_convenio_nao_aceito(
    conv_detectado: str, ctx: Optional[dict] = None,
) -> str:
    """Script artigo 18 KB — recusa direta + 2 opções."""
    nome = ""
    if ctx:
        known = ctx.get("known") or {}
        nome = known.get("nome_paciente") or known.get("nome_contato") or ""
    saudacao = f"{nome.split()[0]}, " if nome else ""
    # Texto bonito do convênio (Inas/GDF/SUS sempre uppercase; resto title).
    _SEMPRE_UPPER = {"inas", "gdf", "sus", "brb", "geap", "pm", "cnti", "afeb"}
    if any(u in conv_detectado.lower() for u in _SEMPRE_UPPER):
        label = "INAS GDF" if "inas" in conv_detectado.lower() else conv_detectado.upper()
    elif len(conv_detectado) <= 4:
        label = conv_detectado.upper()
    else:
        label = conv_detectado.title()
    return (
        f"{saudacao}preciso te corrigir uma informação: o **{label}** "
        "não está credenciado na nossa rede — pra nenhum dos profissionais "
        "(Dra. Karla, Dr. Fabrício ou Dra. Kátia). Sem exceção.\n\n"
        "Mas não quero te deixar sem solução 💙 — temos atendimento sem "
        "convênio com incentivos especiais pra quem tem plano que não "
        "cobrimos.\n\n"
        "Como prefere seguir?\n"
        "1️⃣ Seguir sem convênio (te apresento valor + parcelamento)\n"
        "2️⃣ Somente com convênio (encerro o atendimento aqui)"
    )


# Bug C-19 (Fábio 10/06/2026) — Lia cai em "anotar preferência + equipe contata"
# quando Medware está fora. Lead 24129390 Julia/Lucas + lead 24129498 Sarah.
#
# Filtro SEMPRE-ON (não depende de FILTROS_LEGACY) — invariante ético duro.
# Detecta padrões de fallback "humano vai te ligar / equipe vai consultar".
# Substitui pela frase honesta: "deixa eu reconsultar, volto em 1 min".

_FALLBACK_EQUIPE_CONTATA_PATTERNS = (
    re.compile(r"equipe\s+(vai\s+)?(entrar?\s+em\s+contato|consult|retorn|te\s+avis)", re.IGNORECASE),
    re.compile(r"nossa\s+equipe\s+(retorna|entra|vai)", re.IGNORECASE),
    re.compile(r"anotar?\s+(sua\s+)?prefer[êe]ncia.{0,80}(equipe|humano|nosso\s+time)", re.IGNORECASE | re.DOTALL),
    re.compile(r"(vou|vamos)\s+anotar.{0,80}(equipe|equipe\s+entra|equipe\s+retorna|humano)", re.IGNORECASE | re.DOTALL),
    re.compile(r"vou\s+(passar|encaminhar)\s+(pra|para)\s+(nossa\s+)?equipe", re.IGNORECASE),
    re.compile(r"vou\s+te\s+passar\s+(pra|para)\s+(um|nosso)\s+(atendente|humano|colega)", re.IGNORECASE),
    re.compile(r"(retorno|volta(rei)?|entrarei)\s+em\s+contato.{0,40}(em\s+breve|hor[áa]rio\s+comercial|amanh[ãa])", re.IGNORECASE),
)


def _viola_fallback_equipe_contata(text: str, ctx: Optional[dict] = None) -> bool:
    """True se Lia caiu em fallback 'equipe vai te contatar / anotar preferência'.

    Não vale se o paciente foi REALMENTE escalado pra humano (handoff válido).
    Casos reais: leads 24129390 Julia/Lucas, 24129498 Sarah — Medware 503 deixou
    Lia em loop "deixa eu consultar" → caiu em "equipe entra em contato".
    """
    if not text:
        return False
    for p in _FALLBACK_EQUIPE_CONTATA_PATTERNS:
        if p.search(text):
            return True
    return False


def _gerar_resposta_honesta_medware_down(ctx: Optional[dict] = None) -> str:
    """Substitui fallback 'equipe contata' pela frase honesta de reconsulta."""
    known = (ctx or {}).get("known") or {}
    nome = known.get("nome_contato") or known.get("nome_paciente") or ""
    saudacao = f"{nome.split()[0]}, " if nome else ""
    return (
        f"{saudacao}deixa eu reconsultar a agenda real aqui pra você — "
        "volto em 1 minuto com os horários certos."
    )


# Bug C-22 (Fábio 10/06/2026) — Lia ignora pergunta sobre convênio NÃO aceito.
# Lead 24130752 Sandra: "vocês atendem GDF?" — Lia simplesmente PULOU pra
# "vamos marcar com Karla, me passa dados". Sem reconhecer GDF não credenciado,
# sem oferecer condições especiais.
#
# Diferença vs Bug C-16:
#   C-16: paciente menciona, Lia AFIRMA que atende (errado positivo)
#   C-22: paciente PERGUNTA, Lia IGNORA e pula pra outro assunto (errado por omissão)
#
# Detecção: olha último user_text no ctx, vê se menciona convênio NÃO aceito,
# E verifica se text outbound atual NÃO reconhece a recusa.

_RECUSA_OU_OFERTA_PADRAO_PATTERNS = (
    re.compile(r"\bn[ãa]o\s+(somos|estamos|est[aá])?\s*credenc", re.IGNORECASE),
    re.compile(r"\bn[ãa]o\s+(atende[mr]?o?s?|cobr[iemo]+s?|aceit[aoe]?m?o?s?)", re.IGNORECASE),
    re.compile(r"\bn[ãa]o\s+est[áa]\s+(coberto|na\s+(nossa\s+)?rede)", re.IGNORECASE),
    re.compile(r"sem\s+conv[êe]nio", re.IGNORECASE),
    re.compile(r"condi[çc][oõ]es?\s+(especi|diferenc)", re.IGNORECASE),
    re.compile(r"incentiv", re.IGNORECASE),
    re.compile(r"plano\s+(que\s+)?n[ãa]o\s+(cobr|atend|aceit)", re.IGNORECASE),
)


def _viola_omitiu_resposta_convenio_nao_aceito(
    text: str, ctx: Optional[dict] = None,
) -> Optional[str]:
    """True+conv se paciente perguntou sobre conv NÃO aceito e Lia ignorou.

    Caso real: lead 24130752 Sandra perguntou "atendem GDF?" — Lia respondeu
    "Ótimo! Vamos marcar com Dra. Karla, me passa nome e data nascimento".

    Algoritmo:
      1. Pega último user_text do ctx (ou ctx['user_text']).
      2. Detecta se user_text menciona conv NÃO aceito (KB 18).
      3. Se sim: verifica se TEXT outbound atual contém alguma das marcas
         de reconhecimento (não credenciado / sem convênio / condições
         especiais / incentivos).
      4. Se text NÃO reconhece → bug. Retorna nome do convênio.

    Não vale como bug se Lia SÓ enviou saudação inicial (1ª resposta).
    """
    if not text or not ctx:
        return None
    user_text = ctx.get("user_text") or ""
    if not user_text:
        # Tentar achar no histórico
        hist = ctx.get("history") or ctx.get("historico") or []
        for h in reversed(hist[-5:] if hist else []):
            if isinstance(h, dict) and h.get("role") == "user":
                user_text = h.get("content") or h.get("text") or ""
                if user_text:
                    break
    if not user_text:
        return None
    conv = _detectar_convenio_nao_aceito_no_texto(user_text)
    if not conv:
        return None
    # Verifica se text outbound RECONHECE a recusa (qualquer um dos padrões)
    for p in _RECUSA_OU_OFERTA_PADRAO_PATTERNS:
        if p.search(text):
            return None
    # Se também menciona o convênio explicitamente E está respondendo (não
    # pulou pra outro assunto), ainda assim conta como omissão se NÃO houve
    # reconhecimento — caso da Sandra.
    return conv


_FILTROS_LEGACY_ATIVOS = os.getenv("FILTROS_LEGACY", "0") == "1"
# Flag pra desligar os 5 filtros pós-geração reativos (cada um criado
# pra prender 1 bug específico do passado, hoje gerando falso positivo).
# Bug Sabrina lead 21392947 (02/06/2026) foi a gota: _viola_dia_semana
# substituiu resposta confirmando agendamento pelo fallback genérico.
# Filtros desligados quando FILTROS_LEGACY=0 (default):
#   _viola_pergunta_redundante_convenio (Adriana)
#   _viola_oferta_apos_agendado (Esther)
#   _viola_oferta_agenda
#   _viola_promete_retorno_humano (Juliene)
# Filtro NOVO C-16 sempre-ON (invariante duro): _viola_disse_atende_convenio_nao_aceito
#   _viola_dia_semana (Aurora, Sabrina)
# Filtros MANTIDOS sempre (invariantes duros):
#   _scrub_prohibited Pix chave inválida
#   _viola_mentiu_gravou_medware
#   _viola_cobranca_antes_slot
# Reativar: setar FILTROS_LEGACY=1 no Easypanel.



# ===== FILTROS E-SERIES (lead 24154908, 15/06/2026) =====

# Filtro #14
def _viola_primeira_mensagem_longa(text: str, ctx: dict) -> bool:
    """Primeira mensagem de sessao nova nao pode passar de 80 palavras."""
    if (ctx or {}).get("turno_numero", 0) > 1:
        return False
    palavras = len(text.split())
    return palavras > 80


# Filtro #15
def _viola_markdown_whatsapp(text: str) -> bool:
    """Detecta ## headers, --- separadores, *** triple asterisk."""
    padroes = [
        r"^##\s",
        r"^---\s*$",
        r"\*\*\*",
        r"___",
    ]
    return any(re.search(p, text, re.MULTILINE) for p in padroes)


# Filtro #16
_DICAS_BANIDAS_PATTERNS = [
    r"\b\d{1,3}\s*(a|a|ate)\s*\d{1,3}\s*minutos\b",
    r"\b\d{1,2}\s*(a|a|ate)\s*\d{1,2}\s*horas\b",
    r"\bvisao\s+(fica\s+)?embacada\b",
    r"\bevitar\s+(voltar\s+)?(pra|para)\s+(a\s+)?escola\b",
    r"\b\d{1,2}\s*anos?\s+de\s+experi[ee]ncia\b",
    r"\btrazer\s+brinquedo\b",
    r"\bjejum\b",
]


def _viola_dicas_banidas(text: str) -> bool:
    """Detecta dicas banidas da lista negra E2.X."""
    return any(re.search(p, text, re.IGNORECASE) for p in _DICAS_BANIDAS_PATTERNS)


# Filtro #17
def _viola_inicio_noite(text: str) -> bool:
    """Aguas Claras e Asa Norte NAO tem turno Noite ofertado."""
    return bool(re.search(
        r"\bin[ii]cio\s+(da\s+)?noite\b|\bturno\s+(da\s+)?noite\b",
        text, re.IGNORECASE
    ))



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

    # 0-INAS. Bug C-16 (lead 24117314 Maria Agostini, 08/06/2026 11:41 BRT).

    # === FILTROS E-SERIES (lead 24154908, 15/06/2026) ===
    _FALLBACK_CURTO_E = "Boa tarde! Pra eu ver os horarios disponiveis, qual e o nome do paciente?"

    # Filtro #14 - Primeira mensagem longa
    if _viola_primeira_mensagem_longa(text, ctx or {}):
        log.error(
            "[FILTRO E-14] PRIMEIRA MENSAGEM LONGA bloqueada - %d palavras. Texto: %r",
            len(text.split()), text[:200],
        )
        return _FALLBACK_CURTO_E

    # Filtro #15 - Markdown incompativel com WhatsApp
    if _viola_markdown_whatsapp(text):
        log.error(
            "[FILTRO E-15] MARKDOWN WHATSAPP bloqueado. Texto: %r", text[:200]
        )
        return _FALLBACK_CURTO_E

    # Filtro #16 - Dicas banidas lista negra E2.X
    if _viola_dicas_banidas(text):
        log.error(
            "[FILTRO E-16] DICA BANIDA detectada. Texto: %r", text[:200]
        )
        return _FALLBACK_CURTO_E

    # Filtro #17 - Turno Noite banido
    if _viola_inicio_noite(text):
        log.error(
            "[FILTRO E-17] TURNO NOITE banido detectado. Texto: %r", text[:200]
        )
        return _FALLBACK_CURTO_E

    # Lia disse "Perfeito! Atendemos o INAS GDF" violando KB 18 (Inas é
    # NÃO-aceito sem exceção). Filtro sempre-ON: detecta afirmação positiva
    # sobre qualquer convênio listado em KB 18 e substitui pelo script de
    # transição. Vence todos os outros filtros porque é fundamental ético.
    _conv_violado = _viola_disse_atende_convenio_nao_aceito(text, ctx)
    if _conv_violado:
        log.error(
            "[FILTRO C-16] AFIRMACAO ATENDE CONVENIO NAO ACEITO bloqueada — "
            "Lia disse que atendemos %r (KB 18 marca como NÃO aceito). "
            "Texto: %r",
            _conv_violado, text[:200],
        )
        return _gerar_script_convenio_nao_aceito(_conv_violado, ctx)

    # 0-Juliene. Bug C-19 (leads 24129390 Julia/Lucas + 24129498 Sarah,
    # 10/06/2026). Quando Medware está fora (HTTP 503) Lia tentou consultar,
    # falhou, e caiu em fallback "equipe vai entrar em contato" / "anotar
    # preferência + equipe consulta". Filtro SEMPRE-ON (independe de
    # FILTROS_LEGACY) substitui pela frase honesta de reconsulta.
    if _viola_fallback_equipe_contata(text, ctx):
        log.error(
            "[FILTRO C-19] FALLBACK EQUIPE CONTATA bloqueado — Lia caiu em "
            "'equipe vai contatar/anotar preferência'. Texto: %r", text[:200],
        )
        return _gerar_resposta_honesta_medware_down(ctx)

    # 0-INAS-bis. Bug C-22 (lead 24130752 Sandra, 10/06/2026 17:54 BRT).
    # Paciente perguntou "atendem GDF?" — Lia ignorou e pulou pra "vamos
    # marcar com Karla". Filtro detecta omissão: inbound menciona conv NÃO
    # aceito + outbound NÃO reconhece a recusa → substitui pelo script.
    _conv_omitido = _viola_omitiu_resposta_convenio_nao_aceito(text, ctx)
    if _conv_omitido:
        log.error(
            "[FILTRO C-22] OMISSAO RESPOSTA CONVENIO NAO ACEITO bloqueada — "
            "paciente perguntou sobre %r e Lia ignorou. user_text=%r outbound=%r",
            _conv_omitido,
            ((ctx or {}).get("user_text") or "")[:120],
            text[:200],
        )
        return _gerar_script_convenio_nao_aceito(_conv_omitido, ctx)

    # 0-pre-bis. PERGUNTA REDUNDANTE DE CONVÊNIO (lead 24063769 Adriana,
    # 02/06/2026). Convênio já no ctx mas Lia perguntou de novo.
    if _FILTROS_LEGACY_ATIVOS and _viola_pergunta_redundante_convenio(text, ctx):
        log.error(
            "[FILTRO] PERGUNTA REDUNDANTE CONVÊNIO bloqueada — ctx já "
            "tem convenio=%r. Texto: %r",
            ((ctx or {}).get("known") or {}).get("convenio"), text[:200],
        )
        return _gerar_resposta_valor_sem_repergunta(ctx)

    # 0-Pedro-A. PERGUNTA CONCEITUAL IGNORADA (lead 24102510 Pedro, 04/06/2026)
    # Paciente perguntou "o que é convênio?" e Lia respondeu "qual é o nome
    # do seu convênio?" — ignorou a dúvida. Filtro detecta padrão "o que é X"
    # na ÚLTIMA inbound + falta de explicação na resposta → substitui.
    try:
        from voice_agent.filtros_pedro_miguel import (
            _viola_ignorar_pergunta_conceitual as _viola_concept,
            _gerar_explicacao_e_retoma as _gerar_explic,
        )
        _viola_pc, _conceito = _viola_concept(text, ctx)
        if _viola_pc and _conceito:
            log.error(
                "[FILTRO] PERGUNTA CONCEITUAL IGNORADA (%s) — Lia não "
                "explicou. user_text=%r, lia_resp=%r",
                _conceito,
                (ctx or {}).get("user_text", "")[:100],
                text[:200],
            )
            return _gerar_explic(_conceito, ctx)
    except Exception as _e_pc:  # noqa: BLE001
        log.warning("[FILTRO] pergunta-conceitual fail: %s", _e_pc)

    # 0-Pedro-B. DATA DISTANTE TENDO PRÓXIMA (lead 24102510 Pedro, 04/06/2026)
    # Lia ofereceu D+30 (30/06) e D+02/07 ignorando quinta 11/06 (D+7)
    # que tinha 7 vacâncias na agenda. Filtro detecta gap cronológico.
    try:
        from voice_agent.filtros_pedro_miguel import (
            _viola_data_distante as _viola_dd,
            _gerar_oferta_mais_proxima as _gerar_oferta_proxima,
        )
        if _viola_dd(text, ctx, limite_dias_aceitavel=10):
            log.error(
                "[FILTRO] DATA DISTANTE — Lia ofereceu data >10d depois "
                "da mais próxima da agenda. Texto: %r", text[:200],
            )
            return _gerar_oferta_proxima(ctx)
    except Exception as _e_dd:  # noqa: BLE001
        log.warning("[FILTRO] data-distante fail: %s", _e_dd)

    # 0-pre. OFERTA APÓS JÁ AGENDADO (lead 24060221 Esther, 01/06/2026)
    # Lead em 5-AGENDADO + paciente envia carteirinha → Lia volta a
    # oferecer slot. Filtro pós-geração é a defesa final quando o LLM
    # ignora a TRAVA "🚨 JÁ AGENDADO" do system prompt. Dispara antes
    # de qualquer outro filtro porque, se vale aqui, vale logo.
    if _FILTROS_LEGACY_ATIVOS and _viola_oferta_apos_agendado(text, ctx):
        log.error(
            "[FILTRO] OFERTA POS-AGENDADO bloqueada — Lia tentou oferecer "
            "slot novo num lead já com consulta marcada. ja_agendado=True. "
            "Texto: %r", text[:200],
        )
        return _gerar_oferta_pos_agendado_fallback(ctx)

    # 0. Fingiu consultar agenda — quando JÁ tem horários no contexto.
    # Esse bug deixa a Lia em loop de "deixa eu consultar..." sem nunca voltar.
    if _FILTROS_LEGACY_ATIVOS and _viola_oferta_agenda(text, has_agenda):
        log.error(
            "[FILTRO] FAKE AGENDA LOOKUP bloqueado — Lia disse que ia consultar "
            "agenda quando JÁ tinha %d slots no contexto. Texto: %r",
            len(ctx.get("agenda", [])), text[:200],
        )
        return _FAKE_AGENDA_LOOKUP_FALLBACK

    # 0a. ANTI-CONFIRMAÇÃO-FAKE (caso Carolina/Heloísa 24145994 + Carmen 24142996)
    # Lia envia "✨ Agendamento confirmado!" SEM ter gravado no Medware. Padrão
    # destrutivo: paciente recebe confirmação de algo que não existe. Detecta
    # frase de conclusão e bloqueia se ctx.medware_grava_ok != True.
    if _viola_confirmacao_sem_gravacao(text, ctx):
        log.error(
            "[FILTRO] CONFIRMACAO-FAKE bloqueada — Lia confirmou agendamento "
            "SEM ter gravado no Medware. ctx.medware_grava_ok=%s. Texto: %r",
            (ctx or {}).get("medware_grava_ok"), text[:200],
        )
        return _CONFIRMACAO_FAKE_FALLBACK

    # 0-bis. PERGUNTA TURNO/PERÍODO COM AGENDA (lead 21256807 Alice, 03/06/2026)
    # Tudo já preenchido + agenda real disponível → Lia perguntou
    # "manhã ou tarde? início, meio ou fim?" em vez de oferecer 2 slots.
    # Fluxo aprovado por Fábio: ofertar primeiro, perguntar só se recusar.
    if _viola_pergunta_turno_periodo_com_agenda(text, ctx):
        log.error(
            "[FILTRO] PERGUNTA TURNO/PERIODO COM AGENDA — Lia perguntou "
            "preferência quando tinha %d slots no ctx. Substituindo por "
            "oferta direta de 2 slots. Texto: %r",
            len(ctx.get("agenda", [])), text[:200],
        )
        return _gerar_oferta_2_slots(ctx)

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

    # 0c-bis. MÉDICO TROCADO (lead 23742328 Diones, 01/06/2026)
    # Detecta se Lia ofereceu/mencionou médico diferente do ONBOARDING.
    motivo_med = _viola_medico_trocado(text, ctx)
    if motivo_med:
        log.error(
            "[FILTRO] MEDICO TROCADO bloqueado — %s. Texto: %r",
            motivo_med, text[:200],
        )
        return _MEDICO_TROCADO_FALLBACK

    # 0d. PROMESSA RETORNO HUMANO (lead 24053159 Juliene, 31/05/2026)
    # Lia inventou "vou registrar preferência → equipe finaliza → retorno
    # em horário comercial". Sem o filtro, escapa dos outros 4 detectores.
    # Se já temos agenda → reformula oferecendo os 2 melhores slots.
    # Se NÃO temos agenda → pede 1min e prometendo voltar com opções reais.
    # SEMPRE ON — caso Kamila 02/06 11:50 BRT mostrou Lia inventando
    # "retorno em horário comercial seg-sex 8h-18h" (Blink é 24h!).
    # Rollback do rollback: filtro fica obrigatório de novo.
    # (Iara 21344999 silêncio NÃO foi causa do filtro — outro problema.)
    if _viola_promete_retorno_humano(text):
        log.error(
            "[FILTRO] PROMESSA RETORNO HUMANO BLOQUEADA — Lia inventou "
            "encaminhamento humano. has_agenda=%s. Texto: %r",
            has_agenda, text[:200],
        )
        if has_agenda:
            # Tem agenda — pega 2 primeiros slots e oferece concreto.
            agenda = ctx.get("agenda", [])[:2]
            linhas = []
            for s in agenda:
                dia = s.get("dia_semana", "")
                dbr = s.get("data_br", "")
                hora = s.get("hora", "")
                if dia and dbr and hora:
                    linhas.append(f"• {dia.capitalize()}, {dbr} às {hora}")
            if linhas:
                return (
                    "Consultei a agenda real aqui. Tenho essas duas "
                    "opções concretas que cabem na sua preferência:\n\n"
                    + "\n".join(linhas)
                    + "\n\nQual fica melhor pra você?"
                )
        # Sem agenda — honestidade: re-consulto e volto em 1 min.
        return _PROMETE_RETORNO_HUMANO_FALLBACK_SEM_AGENDA

    # 0b. Dia da semana INVENTADO (lead 24038029, 29/05/2026)
    # Python valida cada par "<dia-semana>, DD/MM" do texto contra o
    # calendário real. Se Lia escreveu "terça-feira, 03/06" e Python
    # diz que é quarta, bloqueia e força regenerar via fallback.
    #
    # EXCEÇÃO crítica (lead 21392947 Sabrina, 02/06/2026 tarde): se o
    # paciente JÁ ESTÁ AGENDADO (ja_agendado=True), QUALQUER menção a
    # dia/data na resposta é CONFIRMAÇÃO/REFERÊNCIA — não oferta nova.
    # Substituir pelo fallback genérico "deixa eu reconferir o calendário"
    # QUEBRA o contexto: paciente respondeu "1" (Tudo Correto) ao template
    # de conclusão, e Lia abriu reconferência. Skip do filtro nesse caso.
    if _FILTROS_LEGACY_ATIVOS and not (ctx and ctx.get("ja_agendado")):
        violacao_dia = _viola_dia_semana(text)
        if violacao_dia:
            dia_falado, data_str, dia_real = violacao_dia
            log.error(
                "[FILTRO] DIA DA SEMANA INVENTADO — Lia disse '%s' para %s, "
                "mas Python calculou '%s'. Texto ORIGINAL completo: %r",
                dia_falado, data_str, dia_real, text,
            )
            return _DIA_SEMANA_FALLBACK

        # 0b-ter. OFERTA EM DIA QUE O MÉDICO NÃO ATENDE (Priscila lead 24055629)
        # Lia disse "9h de sexta-feira (06/06)" — 06/06 é SÁBADO e Dra. Karla
        # não atende sábado. _viola_dia_semana validou que a sexta era da Lia
        # vs sábado real, mas mesmo se o regex anterior tivesse falhado, este
        # filtro pega a oferta em sábado/domingo pra Karla diretamente.
        violacao_dia_med = _viola_oferta_em_dia_nao_atendido(text, ctx)
        if violacao_dia_med:
            medico_norm, data_str, dia_real = violacao_dia_med
            log.error(
                "[FILTRO] OFERTA EM DIA NAO ATENDIDO — médico=%r data=%s "
                "cai em %s. Médico não trabalha nesse dia. Texto: %r",
                medico_norm, data_str, dia_real, text[:300],
            )
            return _DIA_NAO_ATENDIDO_FALLBACK
    else:
        # Log preventivo: paciente já agendado, NÃO aplicamos o filtro
        # de dia-da-semana. Se Lia disse algo errado, vai aparecer aqui.
        violacao_dia_check = _viola_dia_semana(text)
        if violacao_dia_check:
            dia_falado, data_str, dia_real = violacao_dia_check
            log.warning(
                "[FILTRO PULADO ja_agendado=True] _viola_dia_semana detectou "
                "mismatch '%s' vs '%s' em %s, mas paciente já agendado — "
                "considerando confirmação/referência, não oferta. Texto: %r",
                dia_falado, dia_real, data_str, text,
            )

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

    # 4-bis. MEMORIA DE BUGS — similaridade cosine vs bugs históricos
    # Origem: discussão Fábio 01/06/2026 noite — terceira camada de
    # defesa, complementa juiz Haiku e regex. Cada bug histórico
    # (Aurora, Juliene, Adelia, Diones, Esther) tem embedding em Redis.
    # Resposta nova é comparada por cosine; se >= 0.85 = igual a bug
    # antigo, substitui. Custo ~$0.0001/turno. Opt-in via
    # MEMORIA_BUGS_ENABLED=1.
    try:
        import os as _os
        if _os.getenv("MEMORIA_BUGS_ENABLED", "0") == "1":
            from voice_agent.memoria_bugs import (
                MemoriaBugs, FALLBACK_SIMILAR_BUG,
            )
            # Pega redis client do ctx (responder não tem direto)
            redis_client = (ctx or {}).get("_redis_client")
            mem = MemoriaBugs.from_env(redis_client)
            if mem is not None:
                # Lazy-carrega catálogo + semente (idempotente)
                mem.carregar_semente_se_vazio()
                match = mem.checar(text, ctx)
                if match.deve_substituir:
                    log.error(
                        "[MEMORIA_BUGS] resposta similar a bug=%s "
                        "(similaridade=%.3f) — substituida. Motivo: %s",
                        match.bug_id, match.similaridade, match.motivo,
                    )
                    return FALLBACK_SIMILAR_BUG
                elif match.similaridade >= 0.70:
                    log.warning(
                        "[MEMORIA_BUGS] similaridade borderline com "
                        "bug=%s sim=%.3f (não substitui)",
                        match.bug_id, match.similaridade,
                    )
    except Exception as e:  # noqa: BLE001
        log.warning("[MEMORIA_BUGS] erro — passando direto: %s", e)

    # 4. JUIZ ADVERSARIAL Haiku (último olhar — defesa semântica)
    # Origem: discussão Fábio 01/06/2026 — regex não pega bug novo.
    # Haiku 4.5 lê (lia_text, ctx, user_text) e classifica risco 0-100.
    # Se risco>=limiar, substitui pelo FALLBACK_SUBSTITUICAO.
    # Opt-in via JUIZ_HAIKU_ENABLED=1. Em erro/timeout, não bloqueia.
    try:
        from voice_agent.juiz_adversarial import (
            JuizAdversarial, FALLBACK_SUBSTITUICAO,
        )
        juiz = JuizAdversarial.from_env()
        if juiz is not None:
            veredicto = juiz.julgar(
                lia_text=text,
                ctx=ctx,
                user_text=(ctx or {}).get("_user_text_atual", ""),
            )
            if veredicto.deve_substituir:
                log.error(
                    "[JUIZ] resposta substituida — risco=%d motivos=%s "
                    "elapsed_ms=%d. Texto: %r",
                    veredicto.risco, veredicto.motivos,
                    veredicto.elapsed_ms, text[:200],
                )
                return FALLBACK_SUBSTITUICAO
            elif veredicto.risco >= 30:
                log.warning(
                    "[JUIZ] borderline — risco=%d motivos=%s",
                    veredicto.risco, veredicto.motivos,
                )
    except Exception as e:  # noqa: BLE001
        log.warning("[JUIZ] erro ao executar — passando direto: %s", e)

    return text


def _route_model(user_text: str, history_len: int, sonnet: str, haiku: str) -> str:
    """Roteador Sonnet vs Haiku por complexidade.

    Regras:
    - Sonnet se mensagem contém gatilho sensível (urgência, catarata, Avaliação do Processamento Visual, objeção, criança).
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


def _select_model_for_state(
    estado_fsm: str,
    ctx_agenda: list | None,
    opus_model: str,
    opus_agenda_enabled: bool,
) -> str | None:
    """Upgrade seletivo pra Opus 4.6 em FSM=AGENDA (task 07/06/2026).

    Retorna `opus_model` SE:
        - flag LIA_OPUS_AGENDA_ENABLED=True
        - estado FSM == 'AGENDA' (paciente pronto pra receber slot)
        - ctx_agenda tem slots (Medware respondeu com horários reais)

    Caso contrário retorna None — caller cai pro roteador padrão (Sonnet/Haiku).

    Por que: Sonnet 4.5 em AGENDA decide probabilisticamente entre tool calling
    e texto livre, gerando bug "vou consultar e já volto" que NÃO volta. Opus 4.6
    obedece tool_choice forçado com muito mais disciplina, eliminando o bug.

    Casos cobertos: Sabrina/Kamila/Janeide/Iara/Keyla (02/06 tarde),
    Alice (03/06 00:11), Grace (07/06 10:58), Juliene (01/06).

    Custo: ~5x Sonnet por turno, mas usado em <15% dos turnos → +$200/mês,
    compensado por ~20 agendamentos extras recuperados (ROI ~50x).
    """
    if not opus_agenda_enabled:
        return None
    if (estado_fsm or "").upper() != "AGENDA":
        return None
    # CORREÇÃO 07/06/2026 noite — paciente Karla Delalibera Pacheco
    # (lead 24039387). Antes a regra era "só Opus se ctx_agenda preenchido".
    # Erro: quando state=AGENDA mas Sonnet ainda não chamou tool oferecer_slot,
    # ctx.agenda está vazio → meu helper retornava None → caía pro Sonnet → ciclo
    # do "vou consultar e não volta" se repetia. É EXATAMENTE quando ctx.agenda
    # está vazio que precisamos do Opus pra chamar a tool e popular ctx.agenda.
    # ctx_agenda agora é só logging/observabilidade, não decisão.
    _ = ctx_agenda  # parâmetro mantido na assinatura pra compat de teste/log
    return opus_model


class Responder:
    """Especialista em atendimento e conversão da Blink Oftalmologia."""

    def __init__(
        self,
        api_key: str,
        sonnet_model: str = "claude-sonnet-4-5",
        haiku_model: str = "claude-haiku-4-5-20251001",
        opus_model: str = "claude-opus-4-6",
        opus_agenda_enabled: bool = False,
        system_prompt: str | None = None,
        max_response_chars: int = 1200,
        knowledge_base: KnowledgeBase | None = None,
        conversation_store: Optional[ConversationStore] = None,
    ):
        self._client = Anthropic(api_key=api_key)
        self._sonnet = sonnet_model
        self._haiku = haiku_model
        # Opus 4.6 seletivo em FSM=AGENDA (task 07/06/2026, default OFF).
        # Ativar via env LIA_OPUS_AGENDA_ENABLED=1. Custo +$200/mês mas
        # elimina bug "vou consultar e não volta" (Sabrina/Kamila/Alice/Grace).
        self._opus = opus_model
        self._opus_agenda_enabled = opus_agenda_enabled
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
        # FSM (task #125) — bloco de estado da conversa pra Claude
        # respeitar a transição válida. Persistido em Redis.
        try:
            from voice_agent.fsm_conversa import (
                EstadoConversa,
                SnapshotFSM,
                render_bloco_estado,
            )
            _fsm_dict = (caller_context or {}).get("fsm") if isinstance(caller_context, dict) else None
            if _fsm_dict:
                _snap = SnapshotFSM(
                    estado=EstadoConversa(_fsm_dict.get("estado", "TRIAGEM")),
                    ultima_transicao_ts=0.0,
                    tentativas_no_estado=int(_fsm_dict.get("tentativas_no_estado", 0)),
                    motivo_ultima_transicao=str(_fsm_dict.get("motivo_ultima_transicao", "")),
                )
                bloco_variavel += render_bloco_estado(_snap)
        except Exception:  # noqa: BLE001
            pass
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

        # Zep: recupera contexto de longo prazo ANTES do historico Redis
        _zep_ctx = _zep_recuperar(conversation_key)
        # 3. Monta histórico no formato Anthropic (sem system, só user/assistant)
        history = self._convos.get(conversation_key)
        messages = _sanitize_messages(
            _zep_ctx + history + [{"role": "user", "content": user_text}]
        )

        # 4. Decide modelo
        # 4a. Upgrade SELETIVO pra Opus 4.6 em FSM=AGENDA (07/06/2026).
        # Quando paciente já está pronto pra receber slot E ctx tem agenda
        # Medware, usar Opus pra garantir tool calling disciplinado.
        # Caso contrário cai pro roteador padrão Sonnet/Haiku.
        _estado_fsm_for_model = (caller_context or {}).get("fsm", {}).get("estado") or ""
        _ctx_agenda_for_model = (caller_context or {}).get("agenda") or []
        _opus_choice = _select_model_for_state(
            estado_fsm=_estado_fsm_for_model,
            ctx_agenda=_ctx_agenda_for_model,
            opus_model=self._opus,
            opus_agenda_enabled=self._opus_agenda_enabled,
        )
        if _opus_choice:
            model = _opus_choice
        else:
            model = _route_model(user_text, len(history), self._sonnet, self._haiku)

        # 5. Chama Claude — com tool calling estruturado se habilitado
        # (task #126). Toggle via LIA_TOOLS_ENABLED — default off.
        from voice_agent.tools_lia import (
            ALL_TOOLS,
            executar_tool,
            tools_habilitadas,
        )
        tool_iter_log: list[dict] = []
        if tools_habilitadas():
            # Loop de tool_use — máximo 4 iterações pra evitar runaway
            messages_acc = list(messages)
            answer = ""
            # FORÇA tool ESPECÍFICA por estado FSM (upgrade 06/06/2026, task #183).
            # Antes: `tool_choice={"type":"any"}` deixava modelo escolher tool.
            # Agora: tool_choice={"type":"tool","name":"X"} amarra UMA tool por
            # estado — modelo NÃO PODE escrever texto livre quando estado
            # exige ação determinística.
            # Bugs cobertos: Sabrina/Kamila/Janeide/Iara/Keyla (02/06 tarde),
            # Alice (03/06 00:11 "vou consultar"), gravação Medware ausente 15d.
            _agenda_ctx = (caller_context or {}).get("agenda") or []
            _estado_fsm = (
                (caller_context or {}).get("fsm", {}).get("estado") or ""
            )
            _ja_agendado = (caller_context or {}).get("ja_agendado", False)
            _force_tool_kwargs: dict = {}
            # Mapa estado FSM → tool obrigatória
            _TOOL_POR_ESTADO = {
                "AGENDA": "oferecer_slot",
                "CONFIRMACAO": "confirmar_dados_paciente",
                "GRAVACAO": "gravar_agendamento_medware",
            }
            _tool_obrigatoria = _TOOL_POR_ESTADO.get(_estado_fsm)
            if _tool_obrigatoria and not _ja_agendado:
                # Estado FSM diz qual tool. Amarra exatamente essa.
                _force_tool_kwargs["tool_choice"] = {
                    "type": "tool", "name": _tool_obrigatoria,
                }
            elif _agenda_ctx and not _ja_agendado:
                # Fallback: tem agenda real do Medware mas FSM não sinalizou
                # estado → força qualquer tool (geralmente oferecer_slot).
                _force_tool_kwargs["tool_choice"] = {"type": "any"}
            for _iter in range(4):
                # Só força tool na 1ª iteração — depois deixa modelo escrever
                # resposta humana em cima do tool_result.
                _iter_kwargs = _force_tool_kwargs if _iter == 0 else {}
                response = self._client.messages.create(
                    model=model,
                    max_tokens=600,
                    system=system_field,
                    messages=messages_acc,
                    temperature=0.3,
                    tools=ALL_TOOLS,
                    **_iter_kwargs,
                )
                # Processa blocks: text vai direto pra answer; tool_use
                # dispara handler + injeta tool_result.
                tool_uses = [
                    b for b in response.content if b.type == "tool_use"
                ]
                texts = [
                    b.text for b in response.content if b.type == "text"
                ]
                answer = "\n".join(texts).strip()
                if not tool_uses or response.stop_reason != "tool_use":
                    break  # texto final, sai do loop
                # Executa cada tool e prepara tool_result
                assistant_blocks = list(response.content)
                tool_results = []
                for tu in tool_uses:
                    if caller_context is not None:
                        caller_context.setdefault(
                            "conversation_key", conversation_key,
                        )
                    res = executar_tool(
                        tu.name,
                        tu.input,
                        caller_context,
                        kommo_client=getattr(self, "_kommo", None),
                        medware_client=getattr(self, "_medware", None),
                        redis_client=getattr(self, "_redis", None),
                    )
                    tool_iter_log.append({
                        "name": tu.name,
                        "erro": res.erro,
                        "efeitos": res.efeitos_colaterais,
                    })
                    payload = {
                        "ok": res.erro is None,
                        "texto_para_paciente": res.texto_para_paciente,
                    }
                    if res.erro:
                        payload["erro"] = res.erro
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tu.id,
                        "content": __import__("json").dumps(payload),
                    })
                # Adiciona ao histórico pra próxima rodada
                messages_acc.append({
                    "role": "assistant",
                    "content": assistant_blocks,
                })
                messages_acc.append({
                    "role": "user",
                    "content": tool_results,
                })
            if tool_iter_log:
                log.info(
                    "[TOOLS] convo=%s iters=%d log=%s",
                    conversation_key, len(tool_iter_log), tool_iter_log,
                )
        else:
            response = self._client.messages.create(
                model=model,
                max_tokens=600,
                system=system_field,
                messages=messages,
                temperature=0.3,  # baixa pra seguir regras estritas
            )
            answer_parts = [
                block.text for block in response.content if block.type == "text"
            ]
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
        # Injeta user_text no ctx pra filtros que precisam (pergunta conceitual).
        _before_scrub = answer
        if caller_context is not None and user_text:
            caller_context["user_text"] = user_text
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
        # Zep: grava turno para memoria de longo prazo
        _zep_gravar(conversation_key, user_text, answer)

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
                            "Estrabismo / Avaliação do Processamento Visual / Oftalmologia Geral / consulta "
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
                            "Oftalmopediatria", "Estrabismo", "Avaliação do Processamento Visual",
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
