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
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

from anthropic import Anthropic

from .knowledge import KB_DIR, KnowledgeBase
from .store import ConversationStore
from .zep_adapter import recuperar_contexto as _zep_recuperar, gravar_turno as _zep_gravar


# Chaos test gate — module-level redis ref set externamente (webhook startup).
_CHAOS_REDIS = None


def set_chaos_redis(redis_client) -> None:  # noqa: D401
    """Setter pra o webhook injetar o redis_client após boot."""
    global _CHAOS_REDIS
    _CHAOS_REDIS = redis_client


def _chaos_ativo_anthropic() -> bool:
    """Retorna True se chaos test estiver ativo pra serviço anthropic."""
    if _CHAOS_REDIS is None:
        return False
    try:
        from voice_agent import chaos as _chaos  # noqa: WPS433
        return _chaos.esta_em_chaos(_CHAOS_REDIS, "anthropic")
    except Exception:  # noqa: BLE001
        return False

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

    Camada 3 memória ativa (15/07/2026): DEFAULT ON.
    Desligar com `MEMORIA_RAG_ENABLED=0` em caso de emergência.

    Mudança: era default OFF (`==1`), agora default ON (`not in off-list`).
    Segue mesmo padrão do Bug C-32 (defaults ON pra envs críticas).
    """
    return (os.environ.get("MEMORIA_RAG_ENABLED") or "1").lower() not in (
        "0", "false", "no", "off", "",
    )


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
            # Bug C-47 — se veio naive (fallback antigo), assume BRT.
            # Se veio com tz, normaliza pra BRT.
            if _d.tzinfo is None:
                _d = _d.replace(tzinfo=_TZ_BRT)
            else:
                _d = _d.astimezone(_TZ_BRT)
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
        "sistema.pe@gmail.com",           # Sistema PE
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
    # Bug C-30 (Sofia 24158652, 16/06/2026) — frases exatas de stall:
    re.compile(r"reconsultar.{0,30}(agenda|horário|disponibilidade)", re.IGNORECASE | re.DOTALL),
    re.compile(r"reconferir.{0,30}(agenda|horário|disponibilidade)", re.IGNORECASE | re.DOTALL),
    re.compile(r"medware n[ãa]o.{0,30}(retorn|devolv|respond|dispon)", re.IGNORECASE | re.DOTALL),
    re.compile(r"agenda.{0,25}n[ãa]o est[áa].{0,25}(retorn|dispon|respond)", re.IGNORECASE | re.DOTALL),
    re.compile(r"volto (?:em|com|já com|ja com).{0,25}(minuto|instante|opç|op[çc][õo]es|hor[áa]rio)", re.IGNORECASE | re.DOTALL),
    re.compile(r"(?:lentid[ãa]o|inst[áa]vel|fora do ar|indispon[íi]vel).{0,25}(medware|agenda|sistema)", re.IGNORECASE | re.DOTALL),
    re.compile(r"(?:puxar|buscar).{0,15}(?:a\s+)?agenda.{0,20}(?:exata|real|aqui)", re.IGNORECASE | re.DOTALL),
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


# Bug C-30A (16/06/2026) — variante do C-30 pra cenário Medware vazio.
# Caso real: Sofia 24158652, depois das 13:07 BRT — Medware ficou intermitente,
# Lia ficou em loop "deixa eu reconsultar a agenda real aqui pra você" 4x sem
# voltar com slots. O filtro C-30 original NÃO age porque `has_agenda=False`
# (ctx.agenda vazio). C-30A fecha esse buraco.

def _texto_contem_hesitacao_stall(text: str) -> bool:
    """True se o texto contém QUALQUER padrão de stall — sem gate has_agenda.

    Reusa os mesmos padrões de `_FAKE_AGENDA_LOOKUP` mas independente do
    contexto ter agenda. Usado pela rede C-30A quando ctx.agenda está vazio
    mas a Lia escreveu "deixa eu consultar / reconsultar / volto em 1 min".
    """
    if not text:
        return False
    return any(p.search(text) for p in _FAKE_AGENDA_LOOKUP)


def _lia_em_estado_agenda_provavel(ctx: Optional[dict]) -> bool:
    """True se ctx indica que Lia estava prestes a ofertar slot.

    Heurística — se médico+unidade definidos OU médico+motivo definidos, é
    provável que estivesse em FSM=AGENDA tentando bater Medware. Evita falso
    positivo em fases iniciais da conversa (triagem/dados).
    """
    if not ctx:
        return False
    known = (ctx or {}).get("known") or {}
    medico = (known.get("medico") or "").strip()
    unidade = (known.get("unidade") or "").strip()
    motivo = (known.get("motivo") or "").strip()
    if medico and unidade:
        return True
    if medico and motivo:
        return True
    # Aceita também estado FSM explícito
    estado = (ctx.get("fsm") or ctx.get("estado") or "").upper()
    if estado in ("AGENDA", "CONFIRMACAO"):
        return True
    return False


def _sinalizar_escalation_medware_down(ctx: Optional[dict]) -> None:
    """Grava flag Redis pro watchdog/pipeline escalar lead pra atendimento humano.

    Chave: blink:c30a_medware_down:{lead_id} TTL 30min
    Watchdog Promessa Não Cumprida pega esse marker e move lead pra
    1-ATENDIMENTO HUMANO + nota "AÇÃO HUMANA: Medware indisponível, ofertar
    agenda quando subir".

    Falha silenciosa se Redis não disponível — não pode quebrar resposta.
    """
    if not ctx:
        return
    lead_id = (ctx or {}).get("lead_id") or ((ctx or {}).get("known") or {}).get("lead_id")
    if not lead_id:
        return
    try:
        # Import lazy — evita ciclo de import e não quebra teste sem Redis
        from voice_agent.redis_client import get_redis  # type: ignore
        r = get_redis()
        if r is None:
            return
        key = f"blink:c30a_medware_down:{lead_id}"
        r.setex(key, 30 * 60, "1")
    except Exception:
        # Best-effort: filtro continua, escalação só não dispara
        return


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
# BUG C-31 (16/06/2026, lead 24113652 Fábio Philipe). Mapping antigo
# `_DIAS_ATENDIMENTO_POR_MEDICO` dava "karla": {0,1,2,3,4} (seg-sex) — inclui
# QUINTA, mas Karla Asa Norte NÃO atende quinta. Mapeamento real por
# médico+unidade (fonte: voice_agent/knowledge_base/22_agenda_dra_karla.md):
#
# Karla Asa Norte:     segunda, quarta, sexta   (weekday 0, 2, 4)
# Karla Águas Claras:  terça, quinta             (weekday 1, 3)
# Karla sábado/dom:    NUNCA
# Fabrício (qualquer): terça, quinta             (weekday 1, 3)
# Kátia:               em pausa (set vazio)
#
# Sem unidade definida no ctx: usa UNIÃO dos dias (mais permissivo) — só
# bloqueia se cair em fim-de-semana ou dia que nenhuma unidade atende.

# Bug C-53 (11/07/2026) — Tabela de dias por médico+unidade agora é lida
# do arquivo `voice_agent/calendar_atendimento.json`. Fonte única de verdade.
# Editar o JSON = mudança em prod, sem redeploy. Cache TTL 60s pra não bater
# no disco a cada mensagem. Se o JSON não carregar, cai em fallback hard-coded
# (o mesmo dos últimos 6 meses) — jamais deixa a Lia sem defesa.

_CALENDARIO_JSON_PATH = str(
    Path(__file__).resolve().parent / "calendar_atendimento.json"
)
_CALENDARIO_CACHE_TTL_SEG = 60
_calendario_cache: dict = {"carregado_em": 0.0, "dados": None}

_DIAS_ATENDIMENTO_POR_MEDICO_UNIDADE_FALLBACK = {
    ("karla", "asa norte"):     {0, 2, 4},
    ("karla", "águas claras"):  {1, 3},
    ("karla", "aguas claras"):  {1, 3},
    ("fabricio", "asa norte"):    {1, 3},
    ("fabrício", "asa norte"):    {1, 3},
    ("fabricio", "águas claras"): {1, 3},
    ("fabrício", "águas claras"): {1, 3},
    ("fabricio", "aguas claras"): {1, 3},
    ("fabrício", "aguas claras"): {1, 3},
    ("katia", "asa norte"):    set(),
    ("kátia", "asa norte"):    set(),
}

_DIAS_ATENDIMENTO_POR_MEDICO_FALLBACK = {
    "karla":    {0, 1, 2, 3, 4},
    "fabricio": {1, 3},
    "fabrício": {1, 3},
    "katia":    set(),
    "kátia":    set(),
}


def _carregar_calendario_atendimento() -> dict:
    """Carrega o JSON com dias × médico × unidade. Cache TTL 60s.

    Retorna dict com chaves:
      - medicos_unidades: {(medico, unidade): set(weekdays)}
      - medicos_fallback_uniao: {medico: set(weekdays)}
      - cidades_satelite_unidade: {cidade_lower: 'Asa Norte'|'Águas Claras'}
      - fonte: 'json' ou 'fallback_hardcoded'
    """
    import json as _json
    import time as _time

    agora = _time.time()
    if (
        _calendario_cache["dados"] is not None
        and agora - _calendario_cache["carregado_em"] < _CALENDARIO_CACHE_TTL_SEG
    ):
        return _calendario_cache["dados"]

    try:
        with open(_CALENDARIO_JSON_PATH, "r", encoding="utf-8") as f:
            raw = _json.load(f)
        medicos_unidades = {}
        for chave_str, dias in (raw.get("medicos_unidades") or {}).items():
            if "|" not in chave_str:
                continue
            medico, unidade = chave_str.split("|", 1)
            medicos_unidades[(medico.strip().lower(), unidade.strip().lower())] = set(dias)
        medicos_fallback = {
            m.strip().lower(): set(d)
            for m, d in (raw.get("medicos_fallback_uniao") or {}).items()
        }
        cidades = {
            c.strip().lower(): u
            for c, u in (raw.get("cidades_satelite_unidade") or {}).items()
        }
        dados = {
            "medicos_unidades": medicos_unidades,
            "medicos_fallback_uniao": medicos_fallback,
            "cidades_satelite_unidade": cidades,
            "fonte": "json",
        }
    except Exception as exc:  # noqa: BLE001
        log.error(
            "[CALENDARIO] Falha ao carregar %s: %s. Usando fallback hardcoded.",
            _CALENDARIO_JSON_PATH, exc,
        )
        dados = {
            "medicos_unidades": dict(_DIAS_ATENDIMENTO_POR_MEDICO_UNIDADE_FALLBACK),
            "medicos_fallback_uniao": dict(_DIAS_ATENDIMENTO_POR_MEDICO_FALLBACK),
            "cidades_satelite_unidade": {},
            "fonte": "fallback_hardcoded",
        }

    _calendario_cache["dados"] = dados
    _calendario_cache["carregado_em"] = agora
    return dados


# Acessos legados — mantidos como propriedade dinâmica pra compatibilidade
# com qualquer código que ainda importe os nomes antigos. Nunca CACHEAR
# esses dicts fora do helper (senão TTL não vale).
def _get_dias_por_medico_unidade():
    return _carregar_calendario_atendimento()["medicos_unidades"]


def _get_dias_por_medico():
    return _carregar_calendario_atendimento()["medicos_fallback_uniao"]


# Manter símbolos usados por outros arquivos apontando pra função (property-like).
_DIAS_ATENDIMENTO_POR_MEDICO_UNIDADE = _DIAS_ATENDIMENTO_POR_MEDICO_UNIDADE_FALLBACK
_DIAS_ATENDIMENTO_POR_MEDICO = _DIAS_ATENDIMENTO_POR_MEDICO_FALLBACK


# ----- Bug C-53 helper: detectar padrão de OFERTA nova no texto -----
# Quando ja_agendado=True + texto tem padrão de OFERTA, filtros C-31 rodam
# assim mesmo. Confirmação/referência a agendamento passado NÃO usa esses
# padrões (nunca escreve "1️⃣ Sexta-feira (07/08)...").
_PADROES_OFERTA_NOVA = [
    "1️⃣",
    "2️⃣",
    "posso oferecer",
    "posso te oferecer",
    "tenho 2 horários",
    "tenho dois horários",
    "tenho 3 horários",
    "tenho três horários",
    "tenho horários abertos",
    "horários abertos com",
    "horários disponíveis",
    "estas opções",
    "essas opções",
    "algum desses cabe",
    "algum desses funciona",
    "algum desses horários",
    "algum desses dias",
    "qual desses",
    "prefere qual",
    "prefere um deles",
    "opção 1",
    "opção 2",
]


def _texto_parece_oferta_nova(text: str) -> bool:
    """True se o texto contém padrões inequívocos de OFERTA de slot novo.

    Usado por C-53 pra decidir se aplica os filtros C-31 mesmo com
    ja_agendado=True. Deve dar false pra:
      - Confirmação: "sua consulta está confirmada para..."
      - Referência histórica: "sua última consulta foi em..."
      - Resumo pós-agendamento: "Resumo do Atendimento: paciente..."
    """
    if not text:
        return False
    t = text.lower()
    for p in _PADROES_OFERTA_NOVA:
        if p in t:
            return True
    return False


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

    Considera UNIDADE quando presente no ctx (Bug C-31): Karla Asa Norte
    atende só seg/qua/sex; Karla Águas Claras só ter/qui. Sem unidade,
    usa união dos dias possíveis.

    Retorna (medico_norm, "DD/MM/YYYY", dia_semana_real) ou None.
    """
    if not text:
        return None
    known = ((ctx or {}).get("known") or ctx or {})
    medico_raw = (known.get("medico") or (ctx or {}).get("medico") or "").lower()
    unidade_raw = (known.get("unidade") or (ctx or {}).get("unidade") or "").lower().strip()

    # Carrega tabela do JSON externo (fonte única de verdade). Bug C-53:
    # antes estava hard-coded — qualquer mudança operacional exigia deploy.
    dias_por_med_unid = _get_dias_por_medico_unidade()
    dias_por_med_uniao = _get_dias_por_medico()

    # Pega só o primeiro nome — alinha com o mapa
    medico_norm = ""
    for m in dias_por_med_uniao:
        if m in medico_raw:
            medico_norm = m
            break
    if not medico_norm:
        return None  # médico desconhecido — não bloqueia (evita falso positivo)

    # Bug C-31 — usar mapping médico+unidade quando unidade está no ctx
    if unidade_raw:
        chave = (medico_norm, unidade_raw)
        if chave in dias_por_med_unid:
            permitidos = dias_por_med_unid[chave]
        else:
            # Unidade não reconhecida (ex: typo) — fallback pra mapa simples
            permitidos = dias_por_med_uniao[medico_norm]
    else:
        permitidos = dias_por_med_uniao[medico_norm]

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
# Filtro C-54 (13/07/2026, lead 24185000 Ubirata/Lucas) —
# menção a dia-da-semana SEM data numérica, cruzada com unidade do ctx.
# ------------------------------------------------------------------
# O filtro C-31b acima só valida quando o texto tem DD/MM. Ubirata disse
# "quinta ou sexta" e a Lia gravou "quinta ou sexta na Asa Norte" — mas
# quinta em Asa Norte é impossível (Karla está em Águas Claras).
# Este filtro pega a variante SEM data.

# nome -> weekday
_DIAS_SEMANA_PT_TO_WEEKDAY = {
    "segunda": 0, "segunda-feira": 0, "seg": 0,
    "terça": 1, "terca": 1, "terça-feira": 1, "terca-feira": 1, "ter": 1,
    "quarta": 2, "quarta-feira": 2, "qua": 2,
    "quinta": 3, "quinta-feira": 3, "qui": 3,
    "sexta": 4, "sexta-feira": 4, "sex": 4,
    "sábado": 5, "sabado": 5, "sáb": 5, "sab": 5,
    "domingo": 6, "dom": 6,
}

# Padrão: dia-da-semana isolado (não seguido de número DD/MM)
_DIA_SEM_DATA_REGEX = re.compile(
    r"\b(segunda|ter(?:ç|c)a|quarta|quinta|sexta|s(?:á|a)bado|domingo)"
    r"(?:[\s-]*feira)?\b",
    re.IGNORECASE,
)


def _viola_dia_sem_data_incompativel_unidade(
    text: str,
    ctx: Optional[dict] = None,
) -> Optional[tuple[str, str, str]]:
    """Detecta menção a dia-da-semana (sem data DD/MM) que é impossível
    naquela unidade dado o médico do ctx.

    Ex: ctx tem `medico=Karla` e `unidade=Asa Norte`. Texto tem "quinta"
    (sem data). Karla Asa Norte atende seg/qua/sex — quinta é impossível.
    Retorna (dia_mencionado, medico_norm, unidade_norm).

    Só dispara se:
      - ctx tem médico E unidade
      - texto tem dia-da-semana isolado (sem DD/MM próximo)
      - dia-da-semana NÃO bate com os dias permitidos

    Não bloqueia se o texto TAMBÉM tem uma data DD/MM (nesse caso é o
    filtro C-31b que age).
    """
    if not text:
        return None
    known = ((ctx or {}).get("known") or ctx or {})
    medico_raw = (known.get("medico") or (ctx or {}).get("medico") or "").lower()
    unidade_raw = (
        known.get("unidade") or (ctx or {}).get("unidade") or ""
    ).lower().strip()
    if not medico_raw or not unidade_raw:
        return None

    dias_por_med_unid = _get_dias_por_medico_unidade()
    dias_por_med_uniao = _get_dias_por_medico()

    medico_norm = ""
    for m in dias_por_med_uniao:
        if m in medico_raw:
            medico_norm = m
            break
    if not medico_norm:
        return None

    chave = (medico_norm, unidade_raw)
    permitidos = dias_por_med_unid.get(chave)
    if not permitidos:
        # Se combinação médico+unidade não está mapeada (Kátia em pausa,
        # unidade nova), não bloqueia. Deixa filtro C-31b lidar.
        return None

    # Se o texto TAMBÉM tem uma data DD/MM próxima do dia-da-semana,
    # deixa o filtro C-31b tratar (ele valida a data completa).
    if _DIA_DATA_REGEX.search(text):
        return None

    # Detecta dia-da-semana isolado no texto e checa se NENHUMA das
    # menções bate com permitidos.
    dias_mencionados = set()
    for match in _DIA_SEM_DATA_REGEX.finditer(text):
        dia_raw = match.group(1).lower().replace("terca", "terça")
        wd = _DIAS_SEMANA_PT_TO_WEEKDAY.get(dia_raw)
        if wd is None:
            # tenta com -feira
            wd = _DIAS_SEMANA_PT_TO_WEEKDAY.get(dia_raw + "-feira")
        if wd is not None:
            dias_mencionados.add((dia_raw, wd))

    if not dias_mencionados:
        return None

    # Se PELO MENOS UM dia mencionado É atendido, tudo bem (ex: "sexta"
    # sozinha em Asa Norte é ok — sexta é seg/qua/sex).
    for dia_raw, wd in dias_mencionados:
        if wd in permitidos:
            return None

    # Todos os dias mencionados são IMPOSSÍVEIS naquela unidade.
    # Retorna o primeiro pra log/alerta.
    dia_raw, _ = next(iter(dias_mencionados))
    return (dia_raw, medico_norm, unidade_raw)


_DIA_SEM_DATA_FALLBACK = (
    "Deixa eu conferir os dias direito antes de gravar. A Dra. Karla "
    "Delalíbera atende **seg/qua/sex em Asa Norte** e **ter/qui em "
    "Águas Claras**. Me diz de novo qual dia funciona melhor e eu já "
    "confirmo a unidade certa pra esse dia."
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
# Bug C-37 (18/06/2026 — lead 21341221 Lívia/Linielle):
# Lia inventou afirmações sobre comunicação interna ("vou avisar a
# equipe", "Dra. Karla aguarda", "a recepção foi notificada"). Ela
# NÃO tem canal pra falar com a recepção física da clínica.
# Filtro SEMPRE-ON. Substitui por escalation honesta.
# ------------------------------------------------------------------
_INVENCAO_COMUNICACAO_INTERNA_PATTERNS = [
    # "(já) (vou|estou|aviso) (a) equipe/recepção/médica..."
    re.compile(
        r"(?:j[aá]\s+)?(?:vou\s+|estou\s+|estamos\s+)?avis(?:ar|ando|o)\s+"
        r"(?:te\s+|j[aá]\s+|logo\s+)?(?:a\s+|o\s+)?"
        r"(?:equipe|recep[çc][aã]o|m[eé]dica?|m[eé]dico|dra?\.?|dr\.?)",
        re.IGNORECASE,
    ),
    # "(a) equipe (já) está ciente/avisada/notificada/sabe"
    re.compile(
        r"(?:a\s+)?equipe\s+(?:j[aá]\s+)?(?:est[aá]\s+|foi\s+)?"
        r"(?:ciente|avisada|notificada|sabe|informada)",
        re.IGNORECASE,
    ),
    # "(a) recepção foi/está avisada/notificada/ciente/informada"
    re.compile(
        r"(?:a\s+)?recep[çc][aã]o\s+(?:j[aá]\s+)?(?:foi|est[aá])\s+"
        r"(?:avisada|notificada|ciente|informada)",
        re.IGNORECASE,
    ),
    # "(a) Dr(a). NOME (NOME) aguarda/está aguardando/fará consulta/já sabe..."
    re.compile(
        r"(?:a\s+)?dra?\.?\s+(?:\w+\s*){1,4}"
        r"(?:aguarda|est[aá]\s+aguardando|ir[aá]\s+atend[eê]|"
        r"far[aá]\s+(?:a\s+|sua\s+)?consulta(?:\s+normalmente)?|"
        r"j[aá]?\s+sabe|"
        r"foi\s+(?:avisada|comunicada|notificada))",
        re.IGNORECASE,
    ),
    # "vou comunicar internamente/com a equipe"
    re.compile(
        r"vou\s+comunic(?:ar|ando)\s+(?:internamente|com\s+(?:a\s+)?equipe)",
        re.IGNORECASE,
    ),
    # "(já) informei/informo (a) equipe/médica/médico"
    re.compile(
        r"(?:j[aá]\s+)?inform(?:ei|ando|amos|o)\s+"
        r"(?:a\s+|o\s+)?(?:equipe|recep[çc][aã]o|m[eé]dica?|m[eé]dico|dra?\.?|dr\.?)",
        re.IGNORECASE,
    ),
]


def _viola_invencao_comunicacao_interna(text: str) -> bool:
    """True se a Lia afirmou comunicação interna que NÃO tem como fazer.

    Bug C-37 (Lívia 21341221, 18/06/2026): paciente avisou atraso, Lia
    respondeu 'já aviso a equipe / Dra. Karla aguarda / equipe ciente'.
    Lia só conversa pelo WhatsApp — não fala com recepção física, nem
    com o médico em consulta. Toda afirmação assim é INVENÇÃO.
    """
    if not text:
        return False
    return any(p.search(text) for p in _INVENCAO_COMUNICACAO_INTERNA_PATTERNS)


_INVENCAO_COMUNICACAO_INTERNA_FALLBACK = (
    "Entendido. Vou escalar agora pra equipe humana confirmar com a "
    "médica se ainda dá pra atender no horário possível. Te aviso "
    "em poucos minutos."
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
            # Bug C-47 — normalizar tz pra BRT antes de formatar.
            if _d.tzinfo is None:
                _d = _d.replace(tzinfo=_TZ_BRT)
            else:
                _d = _d.astimezone(_TZ_BRT)
            data_humano = _d.strftime("%d/%m às %H:%M")
        except (ValueError, TypeError):
            data_humano = ""
    # Bug C-48 (Fábio 02/07/2026) — proibido vazar nome de campo interno
    # ("1.DIA CONSULTA", "N.DATA NASC" etc) pro paciente. Se não temos data
    # humana pra mostrar, encaminha pra especialista em remarcação em vez
    # de escrever texto técnico.
    paciente_str = f" da {nome}" if nome else ""
    if data_humano:
        return (
            f"Recebi, obrigada! A consulta{paciente_str} já está "
            f"marcada para **{data_humano}**. Nossa equipe vai conferir "
            "tudo. Se precisar **remarcar** ou **cancelar**, é só me "
            "avisar — caso contrário, te espero no dia marcado!"
        )
    # Sem data humana → NÃO improvisa nem cita campo interno.
    return _gerar_encaminhamento_remarcacao(ctx)


# ────────────────────────────────────────────────────────────────────────
# Bug C-16 — Inas / convênios NÃO ACEITOS
# ────────────────────────────────────────────────────────────────────────
# Lead 24117314 Maria Agostini (08/06/2026 11:41 BRT).
# Lia respondeu "Perfeito! Atendemos o INAS GDF" + perguntou data nasc pra
# "solicitar autorização do convênio". KB artigo 18 marca Inas como NÃO
# ACEITO sem exceção. Causa raiz: enum Kommo CONVÊNIO 925312 tem texto
# enganoso "Inas GDf (somente Dr. Fabrício Freitas)" — Lia leu literal e
# tratou como aceito com restrição. Filtro pós-geração é a defesa final.

# Task #400 (20/07/2026): fonte agora é JSON externo com cache TTL 60s.
# _CONVENIOS_NAO_ACEITOS_KB18 vira alias LAZY pro loader.
# Mudança em prod = editar voice_agent/convenios_nao_aceitos.json (sem redeploy).
# Fallback hard-coded no loader (safety net idêntico ao antigo).
try:
    from voice_agent.convenios_nao_aceitos_loader import (
        convenios_nao_aceitos as _convenios_nao_aceitos_carregar,
        detectar_convenio_nao_aceito as _detectar_conv_do_loader,
    )
    _CONVENIOS_NAO_ACEITOS_KB18 = _convenios_nao_aceitos_carregar()
except Exception:  # noqa: BLE001
    # Fallback ULTIMA-LINHA — se loader nem importa, mantém hard-coded.
    _detectar_conv_do_loader = None  # type: ignore[assignment]
    _CONVENIOS_NAO_ACEITOS_KB18 = frozenset({
        "afeb", "afego", "amil", "assefaz", "asete", "aste",
        "bradesco", "brb",
        "cassi", "caeme", "caesan", "camed", "cnti",
        "eletronorte", "embratel",
        "fusex", "fapes",
        "geap", "golden",
        "hapvida", "hap vida", "hap-vida",
        "inas", "gdf inas", "inas gdf", "inas-gdf",
        "gdf saúde", "gdf saude", "gdf",
        "notre dame", "notredame",
        "polícia militar", "policia militar", "porto seguro",
        "quality",
        "sul américa", "sul america", "sulamérica", "sulamerica",
        "sul-américa",
        "sus", "unimed", "unafisco", "sindifisco",
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


_DIAS_SEMANA_PT = [
    "segunda-feira", "terça-feira", "quarta-feira", "quinta-feira",
    "sexta-feira", "sábado", "domingo",
]


def _fallback_slots_from_kommo(ctx: Optional[dict]) -> list:
    """FONTE B de agenda (02/07/2026) — quando o Medware ao vivo cai.

    Lê os campos "1./2. DIA COM CONVÊNIO" (epochs em known['dia_conv_1_ts'] e
    ['dia_conv_2_ts'], expostos por kommo.get_caller_context_by_lead) e monta
    slots no MESMO formato que o Medware entrega ({dia_semana, data_br, hora}).

    O dia-da-semana é DERIVADO do epoch via datetime — nunca digitado à mão —
    então é impossível reincidir no Bug C-35 (dia inventado). Só retorna slots
    que apontam pro futuro (a captura no kommo.py já filtra ts > agora, aqui
    reforça). Ordena cronologicamente.

    Caso Carolina 21225483: Medware fora, mas 14/07 14:00 (terça) e 23/07 14:30
    (quinta) estavam gravados aqui — batendo Águas Claras (Karla ter/qui) e a
    preferência dela (tarde início). Este helper transforma isso em oferta real.
    """
    known = (ctx or {}).get("known") or {}
    agora = datetime.now(_TZ_BRT)
    slots: list = []
    for _key in ("dia_conv_1_ts", "dia_conv_2_ts"):
        ts = known.get(_key)
        if not ts:
            continue
        try:
            d = datetime.fromtimestamp(int(ts), _TZ_BRT)
        except (ValueError, TypeError, OSError):
            continue
        if d <= agora:
            continue
        slots.append({
            "dia_semana": _DIAS_SEMANA_PT[d.weekday()],
            "data_br": d.strftime("%d/%m"),
            "hora": d.strftime("%H:%M"),
            "_epoch": int(ts),
            "_origem": "kommo_fallback",
        })
    slots.sort(key=lambda s: s.get("_epoch", 0))
    return slots


def _gerar_slots_do_calendario_json(ctx: Optional[dict] = None) -> list:
    """Bug Sofia 22843522 (11/07/2026) — Camada C.

    Quando Medware DOWN E fallback Kommo vazio, gera 2 slots plausíveis
    baseados no calendar_atendimento.json (fonte única de verdade dos
    dias em que o médico+unidade atende). Não é slot Medware real —
    é slot "pré-reserva sujeita a confirmação pela recepção", igual ao
    padrão humano da equipe Blink quando o Medware oscila.

    Retorna lista de dicts no MESMO formato de ctx.agenda:
        [{"data": "DD/MM/YYYY", "hora": "HH:MM", "dia": "quinta-feira"}, ...]

    Regras:
      - Precisa médico + unidade no ctx.known pra saber que dias oferecer.
      - Sem médico/unidade → retorna [] (chamador cai no fallback honesto).
      - Escolhe os 2 PRÓXIMOS dias que o médico atende naquela unidade.
      - Horário fixo padrão: manhã 10:00 e tarde 14:00 (comum na Blink).
    """
    known = ((ctx or {}).get("known") or ctx or {})
    medico_raw = (known.get("medico") or (ctx or {}).get("medico") or "").lower()
    unidade_raw = (
        known.get("unidade") or (ctx or {}).get("unidade") or ""
    ).lower().strip()

    if not medico_raw or not unidade_raw:
        return []

    dias_por_med_unid = _get_dias_por_medico_unidade()

    medico_norm = ""
    for m in _get_dias_por_medico():
        if m in medico_raw:
            medico_norm = m
            break
    if not medico_norm:
        return []

    chave = (medico_norm, unidade_raw)
    permitidos = dias_por_med_unid.get(chave)
    if not permitidos:
        return []

    hoje = datetime.now(_TZ_BRT).date()
    slots = []
    # Varre próximos 30 dias, coleta os 2 primeiros que o médico atende.
    # Formato compatível com _selecionar_2_slots_inteligente + _gerar_oferta_2_slots:
    # data_br, dia_semana, hora, hora_int são as chaves consumidas.
    for offset in range(1, 31):
        data = hoje + timedelta(days=offset)
        if data.weekday() in permitidos:
            hora = "10:00" if len(slots) == 0 else "14:00"
            hora_int = int(hora.split(":")[0])
            slots.append({
                "data_br": data.strftime("%d/%m/%Y"),
                "hora": hora,
                "hora_int": hora_int,
                "dia_semana": _DIA_SEMANA_PT[data.weekday()],
                "origem": "calendario_json",
            })
            if len(slots) >= 2:
                break
    return slots


def _gerar_resposta_honesta_medware_down(ctx: Optional[dict] = None) -> str:
    """Medware down: cascata de 3 fontes ANTES de admitir espera.

    Ordem (11/07/2026 — bug Sofia 22843522 adicionou Camada C):
      1. Se ctx.agenda já tem slots (Medware respondeu) → oferta com eles.
      2. Fallback Kommo (campos "1./2. DIA COM CONVÊNIO"): slot histórico
         futuro → oferta real (fim do loop Carolina 21225483).
      3. Fallback CALENDÁRIO JSON: se médico+unidade conhecidos, gera 2
         próximos dias válidos (Karla AC → próxima terça 10h + próxima
         quinta 14h; Karla AN → próxima seg/qua/sex; etc). Sujeito a
         confirmação da recepção. Encerra o padrão "agenda fora do ar".
      4. Só se NENHUMA fonte tiver slot → frase honesta curta. Escalação
         pra humano já foi sinalizada pelo chamador (C-30A).
    """
    agenda = (ctx or {}).get("agenda") or []
    if not agenda:
        agenda = _fallback_slots_from_kommo(ctx)
    if not agenda:
        agenda = _gerar_slots_do_calendario_json(ctx)
    if agenda:
        ctx_com_agenda = dict(ctx or {})
        ctx_com_agenda["agenda"] = agenda
        return _gerar_oferta_2_slots(ctx_com_agenda)

    # Sem NENHUMA fonte de agenda: admite honestamente + garante escalação.
    _sinalizar_escalation_medware_down(ctx)
    known = (ctx or {}).get("known") or {}
    nome = known.get("nome_contato") or known.get("nome_paciente") or ""
    saudacao = f"{nome.split()[0]}, " if nome else ""
    return (
        f"{saudacao}nossa agenda está fora do ar neste exato momento. "
        "Já pedi pra equipe puxar os horários e te retorno com as opções "
        "concretas em instantes — não vou te deixar sem resposta."
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


# ========================================================================
# FILTRO C-36 (Fabio 17/06/2026, lead 22071351 Karina)
# Lia disse "consulta esta marcada, comparecer?" sem ja_agendado=True.
# Causa: campos do historico (paciente antigo + medico + convenio) usados
# como se fossem agendamento ativo. Filtro sempre-ON.
# ========================================================================

_AFIRMACAO_CONSULTA_ATIVA_C36 = (
    re.compile(r"\bconsulta\s+est[áa]\s+marcada\b", re.IGNORECASE),
    re.compile(r"\bconsulta\s+estava\s+marcada\b", re.IGNORECASE),
    re.compile(r"\bconsulta\s+est[áa]\s+agendada\b", re.IGNORECASE),
    re.compile(r"\bestava\s+marcada\s+(?:para|com)\b", re.IGNORECASE),
    re.compile(r"\btudo\s+certo\s+(?:para\s+|pra\s+)?comparec\w+", re.IGNORECASE),
    re.compile(r"\bconfirmar\s+sua\s+presen[çc]a\s+na\s+consulta\b", re.IGNORECASE),
)


def _viola_afirmou_consulta_ativa_c36(
    text: str, ctx: Optional[dict] = None,
) -> bool:
    """Detecta Lia afirmando consulta ativa quando ja_agendado=False.

    Sempre-ON. Substitui resposta por saudacao historica.
    """
    if not text:
        return False
    if (ctx or {}).get("ja_agendado"):
        return False
    return any(p.search(text) for p in _AFIRMACAO_CONSULTA_ATIVA_C36)


def _gerar_saudacao_historica_c36(ctx: Optional[dict] = None) -> str:
    """Fallback C-36: reconhece historico SEM afirmar consulta marcada."""
    known = (ctx or {}).get("known") or {}
    nome_contato = (ctx or {}).get("name") or ""
    medico = known.get("medico") or ""
    convenio = known.get("convenio") or ""

    saudacao = f"Olá, {nome_contato}!" if nome_contato else "Olá!"
    if medico and "Karla" in medico:
        med_str = "Dra. Karla"
    elif medico and ("Fabrício" in medico or "Fabricio" in medico):
        med_str = "Dr. Fabrício"
    else:
        med_str = "nossa equipe"

    if convenio and convenio not in ("Não se aplica", "particular"):
        return (
            f"{saudacao} Vi aqui que você já passou pelo nosso atendimento "
            f"com {med_str} pelo {convenio}. Como posso te ajudar hoje?"
        )
    return (
        f"{saudacao} Vi aqui que você já passou pelo nosso atendimento "
        f"com {med_str}. Como posso te ajudar hoje?"
    )


# ─── FILTRO C-41 (Bug Milena 24182212, 20/06/2026) ──────────────────────────
# Lia escreveu "Combinado, Henrique! Segunda-feira, 22/06 às 10:00..." e
# montou Resumo do Atendimento SEM ter convênio definido E SEM sinal Pix
# recebido. Confirmação de slot != reserva firmada. Reserva exige UMA das 2
# trilhas:
#   A) Convênio nominal aceito + foto carteirinha + RG/certidão
#   B) Sinal Pix 50% comprovado
# Filtro sempre-ON. Substitui afirmação prematura pela frase canônica
# pré-reserva 10min.

_AFIRMACAO_RESERVA_PATTERNS = [
    re.compile(r"\bcombinad[ao]\b[,!.\s]*[A-ZÁÉÍÓÚÂÊÔÃÕÇ][a-záéíóúâêôãõç]+", re.IGNORECASE),
    re.compile(r"\bagendamento\s+confirmado\b", re.IGNORECASE),
    re.compile(r"\b(esta|está|fica|ficou)\s+reservad[ao]\b", re.IGNORECASE),
    re.compile(r"\breserva\s+(firmad[ao]|confirmad[ao])\b", re.IGNORECASE),
    re.compile(r"horário\s+está?\s+(reservado|garantido|firmado)", re.IGNORECASE),
    re.compile(r"resumo\s+do\s+atendimento", re.IGNORECASE),
    re.compile(r"perfeito[,!.]?\s+(seu|sua|o)\s+(agendamento|horário|consulta)", re.IGNORECASE),
]


def _viola_afirmou_reserva_sem_cobertura(
    text: str, ctx: Optional[dict] = None,
) -> bool:
    """Detecta Lia afirmando reserva firmada sem convênio definido nem sinal Pix.

    Retorna True quando:
    - texto bate algum padrão de afirmação de reserva (Combinado/reservado/Resumo)
    - E ctx.known.convenio está vazio/indefinido OU
    - E ctx.known.sinal_recebido != True
    - E ctx.ja_agendado != True (paciente que JÁ tem consulta gravada não é bug)
    """
    if not text:
        return False
    if (ctx or {}).get("ja_agendado"):
        return False

    known = (ctx or {}).get("known") or {}
    convenio = (known.get("convenio") or "").strip().lower()
    sinal_recebido = bool(known.get("sinal_recebido"))

    # Convênio "definido" = não vazio, não "a definir", não "indefinido"
    convenio_definido = bool(convenio) and convenio not in (
        "", "a definir", "indefinido", "não sei", "nao sei",
        "ver depois", "vou ver", "?",
    )

    if convenio_definido or sinal_recebido:
        return False  # Reserva pode ser firmada — trilha A ou B fechada

    # Sem cobertura — verifica se texto afirma reserva
    return any(p.search(text) for p in _AFIRMACAO_RESERVA_PATTERNS)


def _gerar_pre_reserva_10min(ctx: Optional[dict] = None) -> str:
    """Fallback C-41: frase canônica de pré-reserva 10min.

    Substitui afirmação prematura de reserva por solicitação clara das 2
    trilhas (convênio ou Pix 50%). Usa dados do ctx quando disponível.
    """
    known = (ctx or {}).get("known") or {}
    nome_contato = (ctx or {}).get("name") or ""
    medico = known.get("medico") or ""
    unidade = (known.get("unidade") or "").strip()

    if medico and "Karla" in medico:
        med_str = "Dra. Karla Delalíbera"
        valor_consulta = "R$ 670"
        valor_sinal = "R$ 335"
    elif medico and ("Fabrício" in medico or "Fabricio" in medico):
        med_str = "Dr. Fabrício Freitas"
        valor_consulta = "R$ 297"
        valor_sinal = "R$ 148,50"
    else:
        med_str = "nossa equipe"
        valor_consulta = "R$ 670"
        valor_sinal = "R$ 335"

    # Chave Pix por unidade
    if "águas claras" in unidade.lower() or "aguas claras" in unidade.lower():
        chave_pix = "52.303.729/0001-30 (CNPJ Águas Claras)"
    else:
        chave_pix = "karladelaliberaoftalmo@gmail.com (e-mail Asa Norte)"

    saudacao = f"{nome_contato}, " if nome_contato else ""

    return (
        f"{saudacao}posso pré-reservar esse horário por 10 minutos enquanto "
        f"você me confirma uma coisa: o atendimento vai ser por convênio ou "
        f"particular?\n\n"
        f"• Por convênio: me envia a foto da carteirinha + RG (ou certidão se "
        f"for menor) que eu já autorizo antes da consulta.\n\n"
        f"• Particular: consulta com {med_str} = {valor_consulta}, e pra "
        f"firmar a reserva pedimos um sinal de 50% via Pix ({valor_sinal}). "
        f"Chave Pix: {chave_pix}. Em caso de cancelamento <24h, o sinal não "
        f"é devolvido.\n\n"
        f"Qual prefere?"
    )


# ────────────────────────────────────────────────────────────────────────
# Bug C-39 (01/07/2026, lead em status PRÓXIMA CONSULTA sendo tratado como AGENDAR)
# ────────────────────────────────────────────────────────────────────────
# Import local pra time (a função usa time.time() abaixo). Import global
# de `time` fica no bloco a seguir pra garantir disponibilidade sempre-ON.
import time as _time_c39  # noqa: E402


# ═══════════════════════════════════════════════════════════════════════════
# BUG C-44 (Fábio 12/07/2026 lead Clarice 22544990) — Papéis inventados
# ═══════════════════════════════════════════════════════════════════════════
# Sintoma: Lia escreveu 4× "vou encaminhar você para nossa especialista em
# remarcação" em intervalos de 22s-2h. Papel inexistente. Prompt bumped
# não bloqueou (cache Anthropic 5min TTL). Filtro SEMPRE-ON pós-geração
# blinda: qualquer variante de "especialista em [X que não seja Karla/
# Fabrício]" ou "vou encaminhar pra nossa/nosso [cargo]" vira frase
# canônica de handoff humano.
#
# Não depende de FSM=AGENDA. Não depende de deve_ofertar_agora. Sempre-ON.

_PAPEIS_INVENTADOS = re.compile(
    r"(especialista\s+em\s+(?:remarca[cç][aã]o|remarca[cç][oõ]es|agendamento|"
    r"cancelamento|altera[cç][aã]o|mudan[cç]a|troca|hor[áa]rios?)"
    r"|nossa?\s+especialista\s+em\s+\w+"
    r"|nosso?\s+especialista\s+em\s+\w+"
    r"|vou\s+(?:te\s+)?encaminhar\s+(?:voc[eê]\s+)?(?:para|pra)\s+"
    r"(?:nossa|nosso|a|o)\s+(?:especialista|equipe\s+de|departamento))",
    re.IGNORECASE,
)


# ═══════════════════════════════════════════════════════════════════════
# FILTRO C-61 — Anti-cobertura quando convênio é "Sem Convênio"/particular
# Origem: Fábio 20/07/2026, lead 24325544 (Patrícia/Maria bebê Amil→particular)
# Lia disse "pelo seu convênio (Sem Convênio), a consulta é coberta —
# você não paga direto (pode ter coparticipação)". PROIBIDO. Sem Convênio
# = particular, valor R$ 611. Zero cobertura/coparticipação/reembolso.
# Regressão do Bug C-55 (Dani/Emilly 13/07).
# ═══════════════════════════════════════════════════════════════════════

_PALAVRAS_COBERTURA = re.compile(
    r"("
    r"copart(?:icipa[cç][aã]o|icipa)"
    r"|(?:est[aá]|é|será|fica)\s+cobert[oa]"  # 'está coberta / é coberto / fica coberta'
    r"|cobert[oa]\s+pelo"                       # 'coberto pelo (plano|convênio)'
    r"|cobertur[a]?\s+(?:do|pelo)"
    r"|reembols(?:o|ar|áveis?)"
    r"|n[aã]o\s+paga\s+direto"
    r"|depende\s+do\s+(?:seu\s+)?plano"
    r")",
    re.IGNORECASE,
)


def _convenio_particular_ou_sem(ctx: Optional[dict]) -> bool:
    """True se ctx.convenio for particular / sem convênio / não se aplica."""
    if not ctx:
        return False
    known = ctx.get("known") or {}
    conv = str(known.get("convenio") or "").strip().lower()
    if not conv:
        return False
    return conv in (
        "sem convênio", "sem convenio", "particular",
        "não se aplica", "nao se aplica", "sem plano",
        "não tem", "nao tem",
    )


def _viola_cobertura_sem_convenio(text: str, ctx: Optional[dict]) -> bool:
    """C-61: Lia falou em 'cobertura/coparticipação/reembolso' pra particular."""
    if not text or not ctx:
        return False
    if not _convenio_particular_ou_sem(ctx):
        return False
    return bool(_PALAVRAS_COBERTURA.search(text))


def _gerar_fallback_particular(ctx: Optional[dict]) -> str:
    """C-61: substituição canônica pra particular. Valor direto SEM cobertura."""
    known = (ctx or {}).get("known") or {}
    nome = str(known.get("nome_contato") or known.get("nome_paciente") or "").strip()
    primeiro = nome.split()[0] if nome else ""
    saudacao = f"{primeiro}, " if primeiro else ""

    # Detecta APV pra faixa correta
    motivo = str(known.get("motivo") or "").lower()
    medico = str(known.get("medico") or "").lower()

    if "processamento" in motivo or "apv" in motivo:
        linha_valor = "**Pix (à vista):** R$ 800 · **Cartão 1x:** R$ 870 · **Cartão 2x:** R$ 870 (2x R$ 435)"
        info = "Avaliação do Processamento Visual (APV)"
    elif "catarata" in motivo or "fabr" in medico:
        linha_valor = "**Pix (à vista):** R$ 445 · **Cartão 1x:** R$ 470 · **Cartão 2x:** R$ 470 (2x R$ 235)"
        info = "Avaliação de catarata com Dr. Fabrício Freitas"
    else:
        linha_valor = "**Pix (à vista):** R$ 611 · **Cartão 1x:** R$ 670 · **Cartão 2x:** R$ 670 (2x R$ 335)"
        info = "Consulta com Dra. Karla Delalíbera (inclui tonometria, motilidade e mapeamento de retina)"

    return (
        f"{saudacao}o valor da consulta particular é:\n\n"
        f"📲💳 {linha_valor}\n\n"
        f"{info}.\n\n"
        "Qual forma de pagamento fica melhor pra você?"
    )


def _viola_papel_inventado(text: str) -> bool:
    """C-44: Lia inventou cargo/papel que não existe na Blink.

    Papéis reais da Blink (esses PODEM aparecer):
        - Dra. Karla Delalíbera
        - Dr. Fabrício Freitas
        - Nossa equipe (genérico)
        - Secretaria
        - Um atendente humano

    Qualquer variante de "especialista em X" (remarcação, agendamento,
    cancelamento, alteração, mudança, troca, horários) OU "vou encaminhar
    você para nossa/nosso [algo]" bate no filtro.
    """
    if not text:
        return False
    return bool(_PAPEIS_INVENTADOS.search(text))


def _gerar_fallback_papel_inventado(ctx: Optional[dict]) -> str:
    """C-44: substituição canônica quando Lia inventa cargo.

    Frase única, curta, honesta. Sinaliza handoff humano sem prometer
    cargo específico. Pipeline complementa desativando IA + movendo lead
    pra 1-ATENDIMENTO HUMANO.
    """
    known = (ctx or {}).get("known") or {}
    nome = known.get("nome_paciente") or ""
    primeiro = str(nome).strip().split()[0] if nome else ""
    saudacao = f"{primeiro}, " if primeiro else ""
    return (
        f"{saudacao}vou te conectar com nossa equipe pra dar continuidade — "
        "só um momento, já retornam com você."
    )


def _viola_agendar_em_proxima_consulta(text: str, ctx: dict) -> bool:
    """C-39: Lia oferecendo slot ou chamando tool AGENDAR quando lead em PRÓXIMA CONSULTA."""
    if int((ctx or {}).get("lead", {}).get("status_id", 0)) != 106157327:
        return False
    padrao = re.compile(
        r"(oferecer[_\s]slot|posso agendar|qual dia|qual hor[áa]rio|preferência de turno)",
        re.IGNORECASE,
    )
    return bool(padrao.search(text or ""))


def _viola_afirmou_consulta_marcada_data_passada(text: str, ctx: dict) -> bool:
    """C-39: Lia dizendo 'consulta marcada' baseada em 1.DIA CONSULTA que é PASSADA."""
    dia_consulta_ts = (
        (ctx or {}).get("lead", {}).get("known", {}).get("dia_consulta_ts")
    )
    if not dia_consulta_ts:
        return False
    try:
        ts_val = float(dia_consulta_ts)
    except (TypeError, ValueError):
        return False
    if ts_val >= _time_c39.time():
        return False  # data futura, ok
    return bool(re.search(r"consulta (marcada|agendada|confirmada)", (text or "").lower()))


def _gerar_fallback_c39(ctx: dict) -> str:
    """Fallback C-39a: acompanhamento pós-consulta sem oferecer agenda."""
    known = ((ctx or {}).get("lead", {}).get("known") or {}) or (
        (ctx or {}).get("known") or {}
    )
    ultima = known.get("ultima_medware") or "data anterior"
    return (
        f"Sua última consulta com a Dra./o Dr. foi em {ultima}. "
        f"Sua próxima consulta está prevista para daqui a 1 ano "
        f"(protocolo médico). Continuo à disposição."
    )


# ────────────────────────────────────────────────────────────────────────
# Bug C-51 (03/07/2026 madrugada, lead 24243754 Ani — mesmo lead C-50)
# ────────────────────────────────────────────────────────────────────────
# 4 bugs simultâneos:
# 1. Ani disse "sem convênio" (CONVENIO=Não se aplica gravado). Lia
#    perguntou "convênio ou particular?" de novo.
# 2. Uso da palavra "particular" — Fábio proibiu ("sem convênio").
# 3. Despejou valor R$ 670 + Pix R$ 335 + chave sem paciente perguntar.
# 4. Múltiplos assuntos em 1 mensagem (violação regra E1).
# ────────────────────────────────────────────────────────────────────────
_C51_VALOR_PATTERNS = (
    r"r\$\s*\d",
    r"valor.*consulta",
    r"chave pix",
    r"pix\s*.*\d",
    r"sinal\s*de\s*50",
    r"cancelamento.*24h",
    r"karladelaliberaoftalmo",
    r"52\.303\.729",
)


def _paciente_ja_definiu_convenio(ctx: Optional[dict]) -> bool:
    """True se ctx.known tem convênio preenchido (aceito ou 'sem convênio')."""
    if not ctx:
        return False
    known = ctx.get("known") or {}
    conv = (known.get("convenio") or "").strip().lower()
    # 'Não se aplica' = sem convênio
    if not conv:
        return False
    return conv not in ("", "none", "null")


def _texto_repergunta_convenio(text: str) -> bool:
    if not text:
        return False
    baixo = text.lower()
    return any(p in baixo for p in (
        "convenio ou particular", "convênio ou particular",
        "convenio ou sem convenio", "convênio ou sem convênio",
        "por convenio ou", "por convênio ou",
        "sera por convenio", "será por convênio",
        "atendimento sera por", "atendimento será por",
    ))


def _texto_usa_palavra_particular(text: str) -> bool:
    if not text:
        return False
    import re as _re
    # "particular" como categoria de pagamento (NÃO como "consulta particular médica")
    return bool(_re.search(r"\bparticular\b", text.lower()))


def _paciente_perguntou_valor(inbound_text: Optional[str]) -> bool:
    if not inbound_text:
        return False
    baixo = inbound_text.lower()
    return any(p in baixo for p in (
        "valor", "preço", "preco", "quanto", "custa",
        "custo", "quanto é", "quanto e", "pix", "sinal", "r$",
    ))


def _texto_despeja_valor(text: str) -> bool:
    if not text:
        return False
    import re as _re
    baixo = text.lower()
    return any(_re.search(p, baixo) for p in _C51_VALOR_PATTERNS)


def _gerar_proxima_pergunta_sem_convenio(ctx: Optional[dict] = None) -> str:
    """Reconhecimento curto + próxima pergunta (unidade ou preferência)."""
    known = (ctx or {}).get("known") or {}
    nome = (known.get("nome_contato") or "").split()[0] if known.get("nome_contato") else ""
    saudacao = f"Anotado, {nome}." if nome else "Anotado."
    if not known.get("unidade"):
        return (
            f"{saudacao} Qual unidade fica melhor pra vocês — "
            "Asa Norte ou Águas Claras?"
        )
    return (
        f"{saudacao} Qual dia da semana e turno funcionam melhor "
        "pra vocês?"
    )


def _substituir_particular_por_sem_convenio(text: str) -> str:
    """Troca 'particular' por 'sem convênio' preservando estrutura."""
    import re as _re
    # Substituições ordenadas (mais especificas primeiro)
    subs = [
        (r"[Cc]onvênio ou [Pp]articular", "convênio ou sem convênio"),
        (r"[Cc]onvenio ou [Pp]articular", "convênio ou sem convênio"),
        (r"[Pp]articular:", "Sem convênio:"),
        (r"por [Pp]articular", "sem convênio"),
        (r"no [Pp]articular", "sem convênio"),
        (r"como [Pp]articular", "sem convênio"),
        (r"\b[Pp]articular\b", "sem convênio"),
    ]
    out = text
    for pat, rep in subs:
        out = _re.sub(pat, rep, out)
    return out


# ────────────────────────────────────────────────────────────────────────
# Bug C-50 (02/07/2026 noite, lead 24243754 Ani/Ysis)
# ────────────────────────────────────────────────────────────────────────
# Paciente Ani forneceu "Ysis Hellena, 12/09/2020". Lia respondeu
# "So pra confirmar — a data e 12 de setembro de 2020, certo?".
# Redundancia desnecessaria (a Lia ja gravou o dado no campo Kommo).
# Regra Fabio: NUNCA pedir confirmacao de dado recem-fornecido.
# ────────────────────────────────────────────────────────────────────────
_C50_PADROES_CONFIRMACAO_REDUNDANTE = (
    "so pra confirmar", "só pra confirmar",
    "so para confirmar", "só para confirmar",
    "so pra ter certeza", "só pra ter certeza",
    "so para ter certeza", "só para ter certeza",
    "confirma que e", "confirma que é",
    "e isso mesmo", "é isso mesmo",
    "ficou correto", "esta correto", "está correto",
    "certo? e", "certo? é",
    "ta certo", "tá certo",
    "posso confirmar", "vou confirmar então",
    "so confirmando", "só confirmando",
)

# Marcas que sugerem que o dado FOI fornecido no turno anterior.
# (Se o inbound do paciente tem numero, data ou palavra-chave de dado,
# a Lia NAO deve repetir confirmacao no proximo turn.)
_C50_MARCAS_DADO_INBOUND = (
    # Datas
    r"\d{1,2}/\d{1,2}/\d{2,4}",
    r"\d{1,2}\s*(de\s+)?(jan|fev|mar|abr|mai|jun|jul|ago|set|out|nov|dez)",
    # CPF, RG, telefone (numeros longos)
    r"\d{9,11}",
    # Nome completo (2+ palavras capitalizadas)
    r"[A-ZÁ-Ú][a-zá-ú]+\s+[A-ZÁ-Ú][a-zá-ú]+",
)


def _paciente_forneceu_dado_no_turno(inbound_text: Optional[str]) -> bool:
    """True se inbound tem indicios de dado estruturado (data/nome/CPF)."""
    if not inbound_text or len(inbound_text.strip()) < 3:
        return False
    import re as _re
    for padrao in _C50_MARCAS_DADO_INBOUND:
        if _re.search(padrao, inbound_text):
            return True
    return False


def _texto_pede_confirmacao_redundante(text: str) -> bool:
    if not text:
        return False
    baixo = text.lower()
    return any(p in baixo for p in _C50_PADROES_CONFIRMACAO_REDUNDANTE)


def _gerar_reconhecimento_curto_e_avanca(ctx: Optional[dict] = None) -> str:
    """Frase curta de reconhecimento + prox pergunta contextual do FSM."""
    known = (ctx or {}).get("known") or {}
    nome = (known.get("nome_contato") or "").split()[0] if known.get("nome_contato") else ""
    abertura = f"Anotado{',' if nome else '.'} {nome}." if nome else "Anotado."
    # Prox pergunta depende do que ja tem
    if not known.get("convenio"):
        return f"{abertura} O atendimento sera por convenio ou sem convenio?"
    if not known.get("unidade"):
        return f"{abertura} Qual unidade fica melhor — Asa Norte ou Aguas Claras?"
    if not known.get("preferencia_dia") and not known.get("preferencia_turno"):
        return f"{abertura} Qual dia da semana e turno funcionam melhor pra voce?"
    return f"{abertura} Vou verificar os horarios disponiveis."


# ────────────────────────────────────────────────────────────────────────
# Bug C-47 (02/07/2026, lead 22838100 Manoela Dantas)
# ────────────────────────────────────────────────────────────────────────
# 1. Lia informou "consulta 10/07 às 19:30" — timezone bug já corrigido
#    em kommo.py (1.DIA CONSULTA fromtimestamp com tz=BRT).
# 2. Quando paciente pede REMARCAÇÃO, Lia deve:
#    (a) NÃO mencionar "atendimento humano" ou "equipe humana";
#    (b) Dizer "vou encaminhar você para nossa especialista em remarcação";
#    (c) Encerrar a resposta (única frase curta).
#    Regra Fábio 02/07/2026.
# ────────────────────────────────────────────────────────────────────────
import re as _re_c47

# Termos proibidos que a Lia às vezes usa e revelam camada IA/humana ao paciente.
_C47_TERMOS_PROIBIDOS = (
    "equipe humana", "equipe manual", "atendimento humano",
    "vou passar pra equipe", "vou passar para a equipe",
    "vou passar pra nossa equipe", "vou passar para nossa equipe",
    "encaminhar para nossa equipe humana", "para nossa equipe humana",
    "transferir para atendimento humano", "transferir para nossa equipe",
    "encaminhar para atendimento humano", "para o atendimento humano",
    "equipe de atendimento humano", "atendente humano",
    "encaminho para humano", "passo pro humano",
)

# Termos que sinalizam intenção de REMARCAÇÃO no inbound do paciente.
_C47_TERMOS_REMARCACAO = (
    "remarcar", "remarcação", "remarcacao", "reagendar", "reagendamento",
    "mudar horário", "mudar horario", "trocar horário", "trocar horario",
    "trocar de horário", "mudar data", "trocar data", "trocar dia",
    "adiar consulta", "adiar a consulta", "adiar minha consulta",
    "não vou conseguir na", "nao vou conseguir na",
    "não consigo mais no", "nao consigo mais no",
    "queria mudar", "quero mudar",
    "trocar o dia", "trocar o horário", "trocar o horario",
    "mudar o dia", "mudar o horário", "mudar o horario",
    "outro dia", "outro horário", "outro horario",
    "posso mudar", "posso trocar", "posso remarcar", "posso reagendar",
)


def _paciente_pediu_remarcacao(inbound_text: Optional[str]) -> bool:
    """True se a última mensagem do paciente indica intenção de remarcar."""
    if not inbound_text:
        return False
    baixo = inbound_text.lower().strip()
    return any(t in baixo for t in _C47_TERMOS_REMARCACAO)


def _texto_menciona_atendimento_humano(text: str) -> bool:
    """True se a resposta da Lia contém termos que expõem camada humana/IA."""
    if not text:
        return False
    baixo = text.lower()
    return any(t in baixo for t in _C47_TERMOS_PROIBIDOS)


def _gerar_encaminhamento_remarcacao(ctx: Optional[dict] = None) -> str:
    """Frase canônica pra encaminhar remarcação sem revelar camada humana/IA."""
    known = (ctx or {}).get("known") or {}
    nome_contato = (known.get("nome_contato") or "").split()[0] if known.get("nome_contato") else ""
    saudacao = f"{nome_contato}, entendi! " if nome_contato else "Entendi! "
    return (
        f"{saudacao}Vou encaminhar você para nossa "
        "**especialista em remarcação**, que vai cuidar dessa alteração "
        "com você. Só um instante."
    )


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

    # === FILTRO C-62 SEMPRE-ON (Fábio 20/07/2026, lead 24325532 CBMDF) ===
    # Anti-loop outbound. Se mesma mensagem foi enviada 3× em <3min pro
    # mesmo lead → substitui pela nota canônica de handoff.
    # Origem: Lia mandou 'Anotado. Qual dia da semana...' 7× seguidas
    # em 5min. Paciente disse 'meu deus' e desistiu.
    try:
        from voice_agent.dedup_outbound import (
            resposta_canonica_loop, verificar_e_registrar,
        )
        _lead = (ctx or {}).get("lead") or {}
        _lead_id = _lead.get("id") or (ctx or {}).get("lead_id")
        if _lead_id:
            # Redis do responder — tenta importar do settings/pipeline
            _redis_client = None
            try:
                from voice_agent.settings import get_redis
                _redis_client = get_redis()
            except Exception:  # noqa: BLE001
                pass
            _dedup = verificar_e_registrar(_lead_id, text, _redis_client)
            if _dedup.get("loop_detectado"):
                log.error(
                    "[FILTRO C-62] LOOP OUTBOUND detectado lead=%s hash=%s",
                    _lead_id, _dedup.get("hash"),
                )
                _known = (ctx or {}).get("known") or {}
                _nome = str(_known.get("nome_contato") or _known.get("nome_paciente") or "").strip() or None
                return resposta_canonica_loop(_nome)
    except Exception as e:  # noqa: BLE001
        log.warning("[FILTRO C-62] falhou (fail-open): %s", e)

    # === FILTRO C-61 SEMPRE-ON (Fábio 20/07/2026, lead Patrícia 24325544) ===
    # Sem Convênio / Particular → NUNCA falar "coberta/coparticipação/reembolso".
    # Detecção antes do C-44 pra bloquear regressão Bug C-55.
    if _viola_cobertura_sem_convenio(text, ctx):
        log.error(
            "[FILTRO C-61] COBERTURA em Sem Convênio. texto=%r",
            text[:200],
        )
        return _gerar_fallback_particular(ctx)

    # === FILTRO C-44 SEMPRE-ON (Fábio 12/07/2026, lead Clarice 22544990) ===
    # Detecta "especialista em [remarcação/agendamento/etc]" e "vou encaminhar
    # você para nossa/nosso [cargo]". Papéis inexistentes na Blink. Substitui
    # por frase canônica de handoff humano. Não depende de FSM nem status.
    if _viola_papel_inventado(text):
        log.error(
            "[FILTRO C-44] PAPEL INVENTADO detectado. texto=%r",
            text[:200],
        )
        return _gerar_fallback_papel_inventado(ctx)

    # === FILTRO C-39 SEMPRE-ON (01/07/2026, lead status=PRÓXIMA CONSULTA 106157327) ===
    # Sempre-ON, independe de FILTROS_LEGACY. Fatos objetivos (status_id +
    # timestamp) — invariantes duros. Duas variantes:
    #   (a) Lia oferecendo slot / perguntando dia-hora em lead PRÓXIMA CONSULTA
    #   (b) Lia afirmando "consulta marcada" com dia_consulta_ts NO PASSADO
    # Ambas viram fallback C-39a (acompanhamento pós-consulta).
    _ctx_c39 = ctx or {}
    if _viola_agendar_em_proxima_consulta(text, _ctx_c39):
        log.error(
            "[FILTRO C-39a] AGENDAR em lead PRÓXIMA CONSULTA. "
            "status_id=%s texto=%r",
            _ctx_c39.get("lead", {}).get("status_id"), text[:200],
        )
        return _gerar_fallback_c39(_ctx_c39)
    if _viola_afirmou_consulta_marcada_data_passada(text, _ctx_c39):
        log.error(
            "[FILTRO C-39b] AFIRMOU consulta marcada com data PASSADA. "
            "dia_consulta_ts=%s texto=%r",
            _ctx_c39.get("lead", {}).get("known", {}).get("dia_consulta_ts"),
            text[:200],
        )
        return _gerar_fallback_c39(_ctx_c39)

    # === FILTRO C-51 SEMPRE-ON (Fábio 03/07/2026 madrugada, lead 24243754 Ani) ===
    # 4 fixes simultâneos:
    # 1. Nunca reperguntar convênio se ctx.known.convenio já preenchido
    # 2. Nunca escrever "particular" — substitui por "sem convênio"
    # 3. Nunca despejar valor/Pix se paciente NÃO perguntou
    # 4. Um assunto por turno (regra E1 reforçada)
    _inbound_c51 = (ctx or {}).get("inbound_text") or (ctx or {}).get(
        "last_inbound_text"
    ) or ""

    # Sub-fix 1 — Reperguntou convênio já definido
    if (
        _paciente_ja_definiu_convenio(ctx)
        and _texto_repergunta_convenio(text)
    ):
        log.warning(
            "[FILTRO C-51.1] Repergunta convenio bloqueada. "
            "convenio_ctx=%r texto=%r",
            ((ctx or {}).get("known") or {}).get("convenio"),
            text[:200],
        )
        return _gerar_proxima_pergunta_sem_convenio(ctx)

    # Sub-fix 3 — Despejou valor sem paciente perguntar
    if (
        _texto_despeja_valor(text)
        and not _paciente_perguntou_valor(_inbound_c51)
    ):
        log.warning(
            "[FILTRO C-51.3] Despejo de valor bloqueado. "
            "inbound=%r texto=%r",
            _inbound_c51[:120], text[:200],
        )
        # Substitui por continuação do fluxo (avança sem falar de valor)
        return _gerar_proxima_pergunta_sem_convenio(ctx)

    # Sub-fix 2 — Substitui "particular" por "sem convênio"
    # (aplicado depois dos outros, faz cirurgia no texto)
    if _texto_usa_palavra_particular(text):
        _texto_antes = text
        text = _substituir_particular_por_sem_convenio(text)
        log.warning(
            "[FILTRO C-51.2] Palavra 'particular' substituida. "
            "antes=%r depois=%r",
            _texto_antes[:150], text[:150],
        )

    # === FILTRO C-50 SEMPRE-ON (Fábio 02/07/2026 noite, lead 24243754 Ani/Ysis) ===
    # Se paciente forneceu dado estruturado (data/nome/CPF) no inbound
    # E Lia tenta pedir confirmação redundante → substitui por reconhecimento
    # curto + próxima pergunta contextual.
    _inbound_c50 = (ctx or {}).get("inbound_text") or (ctx or {}).get(
        "last_inbound_text"
    ) or ""
    if (
        _paciente_forneceu_dado_no_turno(_inbound_c50)
        and _texto_pede_confirmacao_redundante(text)
    ):
        log.warning(
            "[FILTRO C-50] Confirmacao redundante bloqueada. "
            "inbound=%r texto=%r",
            _inbound_c50[:120], text[:200],
        )
        return _gerar_reconhecimento_curto_e_avanca(ctx)

    # === FILTRO C-48 SEMPRE-ON (Fábio 02/07/2026, lead 21259287 Samuel) ===
    # Lia vazou "(data no campo 1.DIA CONSULTA)" pro paciente. Proibido
    # citar nome de campo interno do Kommo em qualquer mensagem outbound.
    _C48_PADROES_VAZAMENTO = (
        "1.dia consulta", "n.dia consulta", "campo 1.", "campo n.",
        "n.data nasc", "1.data nascimento", "n.data nascimento",
        "n.nome paciente", "1.nome paciente", "campo dia_consulta",
        "custom_fields", "field_id", "ctx.known", "ctx.agenda",
        "n.perfil", "n.motivo", "n.exames", "campo unidade",
        "campo medicos", "campo convenio", "kommo.get_lead",
        "medware.criar_agendamento", "responder.py",
    )
    _texto_baixo = text.lower()
    if any(p in _texto_baixo for p in _C48_PADROES_VAZAMENTO):
        log.error(
            "[FILTRO C-48] VAZAMENTO de campo interno na resposta. "
            "texto=%r ctx.known=%r",
            text[:300], ((ctx or {}).get("known") or {}),
        )
        # Substitui por frase segura — encaminha remarcação (transparente
        # sem expor camada interna).
        return _gerar_encaminhamento_remarcacao(ctx)

    # === FILTRO C-47 SEMPRE-ON (Fábio 02/07/2026, lead 22838100 Manoela) ===
    # (a) Se Lia mencionou "equipe humana"/"atendimento humano" → troca pela
    #     frase canônica "especialista em remarcação".
    # (b) Se inbound do paciente pediu remarcação, força resposta canônica
    #     e curta (evita Lia inventar horário, escala mais rápido).
    _inbound_text = (ctx or {}).get("inbound_text") or (ctx or {}).get(
        "last_inbound_text"
    ) or ""
    _pediu_remarcar = _paciente_pediu_remarcacao(_inbound_text)
    _mencionou_humano = _texto_menciona_atendimento_humano(text)
    if _pediu_remarcar or _mencionou_humano:
        log.warning(
            "[FILTRO C-47] Encaminhamento remarcação forçado. "
            "pediu_remarcar=%s mencionou_humano=%s texto=%r inbound=%r",
            _pediu_remarcar, _mencionou_humano, text[:200], _inbound_text[:100],
        )
        return _gerar_encaminhamento_remarcacao(ctx)

    has_agenda = bool((ctx or {}).get("agenda"))

    # 0-INAS. Bug C-16 (lead 24117314 Maria Agostini, 08/06/2026 11:41 BRT).

    # === FILTRO C-36 (lead 22071351 Karina, 17/06/2026) ===
    # Lia afirmou "consulta esta marcada, comparecer?" com ja_agendado=False.
    # Roda PRIMEIRO porque a falha eh semantica e cara (paciente confuso).
    if _viola_afirmou_consulta_ativa_c36(text, ctx):
        log.error(
            "[FILTRO C-36] AFIRMOU consulta ativa SEM ja_agendado. ctx.known=%r, texto=%r",
            ((ctx or {}).get("known") or {}), text[:300],
        )
        return _gerar_saudacao_historica_c36(ctx)

    # === FILTRO C-41 (lead 24182212 Milena, 20/06/2026) ===
    # Lia escreveu "Combinado, Henrique! Segunda-feira, 22/06 às 10:00..." +
    # Resumo do Atendimento SEM ter convênio definido E SEM sinal Pix recebido.
    # Sempre-ON. Toggle LIA_ANTI_RESERVA_SEM_COBERTURA (default "1"):
    #   "1"      → substitui de fato
    #   "shadow" → só LOGA (validação 24h, regra 11-E)
    #   "0"      → desligado
    if _viola_afirmou_reserva_sem_cobertura(text, ctx):
        _modo_c41 = os.getenv("LIA_ANTI_RESERVA_SEM_COBERTURA", "1").lower()
        if _modo_c41 == "shadow":
            log.warning(
                "[FILTRO C-41 SHADOW] SUBSTITUIRIA afirmacao de reserva sem "
                "cobertura. ctx.known.convenio=%r, sinal_recebido=%r, texto=%r",
                ((ctx or {}).get("known") or {}).get("convenio"),
                ((ctx or {}).get("known") or {}).get("sinal_recebido"),
                text[:300],
            )
        elif _modo_c41 != "0":
            log.error(
                "[FILTRO C-41] AFIRMOU reserva firmada SEM cobertura "
                "(convenio vazio E sinal nao recebido). ctx.known=%r, texto=%r",
                ((ctx or {}).get("known") or {}), text[:300],
            )
            return _gerar_pre_reserva_10min(ctx)

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

    # 0-C30. ANTI-HESITAÇÃO COM AGENDA REAL (Bug C-30, lead Sofia 24158652,
    # 16/06/2026). Quando há slots reais no ctx e a Lia escreve QUALQUER
    # variação de stall ("deixa eu consultar / reconsultar a agenda", "Medware
    # não está retornando", "volto em 1 minuto", "vou puxar a agenda exata"),
    # substitui pela OFERTA REAL de 2 slots — zero hesitação. Antes esse filtro
    # estava atrás do gate FILTROS_LEGACY (OFF em prod), por isso a Lia hesitou.
    #
    # Toggle LIA_ANTI_HESITACAO_AGENDA (default "1" = ativo):
    #   "1"      → substitui de fato (garantia dura de zero hesitação)
    #   "shadow" → só LOGA o que substituiria (validação 24h, regra 11-E)
    #   "0"      → desligado
    if has_agenda and _viola_oferta_agenda(text, has_agenda):
        _modo_c30 = os.getenv("LIA_ANTI_HESITACAO_AGENDA", "1").lower()
        if _modo_c30 == "shadow":
            log.warning(
                "[FILTRO C-30 SHADOW] SUBSTITUIRIA hesitacao com %d slots no "
                "ctx (sem substituir). Texto: %r",
                len((ctx or {}).get("agenda", [])), text[:200],
            )
        elif _modo_c30 != "0":
            log.error(
                "[FILTRO C-30] HESITACAO COM AGENDA REAL bloqueada — Lia "
                "hesitou tendo %d slots no ctx. Substituindo pela oferta real. "
                "Texto: %r",
                len((ctx or {}).get("agenda", [])), text[:200],
            )
            return _gerar_oferta_2_slots(ctx)

    # 0-C30A. ANTI-HESITAÇÃO SEM AGENDA — Medware indisponível (Bug C-30A,
    # Sofia 24158652 13:07-13:40 BRT, 16/06/2026). Quando Medware está
    # intermitente/down, ctx.agenda=[] mas Lia já estava em FSM=AGENDA
    # (médico+unidade definidos no known). Lia continuou hesitando "deixa eu
    # reconsultar a agenda real" 4x sem voltar. Filtro substitui pela frase
    # honesta de Medware down E grava flag Redis pra watchdog escalar pra
    # 1-ATENDIMENTO HUMANO.
    #
    # Reaproveita toggle LIA_ANTI_HESITACAO_AGENDA (mesmo controle do C-30).
    if (
        not has_agenda
        and _texto_contem_hesitacao_stall(text)
        and _lia_em_estado_agenda_provavel(ctx)
    ):
        _modo_c30a = os.getenv("LIA_ANTI_HESITACAO_AGENDA", "1").lower()
        if _modo_c30a == "shadow":
            log.warning(
                "[FILTRO C-30A SHADOW] SUBSTITUIRIA hesitacao sem agenda "
                "(Medware vazio) + sinalizaria escalation. Texto: %r",
                text[:200],
            )
        elif _modo_c30a != "0":
            log.error(
                "[FILTRO C-30A] HESITACAO SEM AGENDA — Medware indisponivel. "
                "Substituindo pela frase honesta + flag escalation Redis. "
                "Texto: %r", text[:200],
            )
            _sinalizar_escalation_medware_down(ctx)
            return _gerar_resposta_honesta_medware_down(ctx)

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
    # Bug C-37c (Fábio 18/06/2026 — benchmark engenheiro): filtro estava
    # gateado por FILTROS_LEGACY=0 (off em prod). Por isso bug Adriana
    # 24063769 continuava acontecendo apesar de filtro existir.
    # Agora SEMPRE-ON — convênio já no ctx é fato objetivo.
    if _viola_pergunta_redundante_convenio(text, ctx):
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
    # Bug C-37c (Fábio 18/06/2026 — benchmark engenheiro): filtro estava
    # gateado por FILTROS_LEGACY=0. Caso Esther 24060221 + Manuela 24165262.
    # Agora SEMPRE-ON — ja_agendado é fato objetivo.
    if _viola_oferta_apos_agendado(text, ctx):
        log.error(
            "[FILTRO] OFERTA POS-AGENDADO bloqueada — Lia tentou oferecer "
            "slot novo num lead já com consulta marcada. ja_agendado=True. "
            "Texto: %r", text[:200],
        )
        return _gerar_oferta_pos_agendado_fallback(ctx)

    # 0. Fingiu consultar agenda — quando JÁ tem horários no contexto.
    # Esse bug deixa a Lia em loop de "deixa eu consultar..." sem nunca voltar.
    # Bug C-37c (Fábio 18/06/2026 — benchmark engenheiro): filtro estava
    # gateado por FILTROS_LEGACY=0. Loop "deixa eu consultar..." Sabrina,
    # Sofia, Adelia, Maitê — todos esses casos teriam sido bloqueados.
    # Agora SEMPRE-ON — has_agenda é fato objetivo (consultou ou não).
    if _viola_oferta_agenda(text, has_agenda):
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
    # Bug C-37 (Lívia 21341221, 18/06/2026): Lia inventou afirmações
    # sobre comunicação interna ("vou avisar a equipe", "Dra. Karla
    # aguarda"). Lia NÃO tem como falar com recepção física da clínica.
    # SEMPRE-ON. Substitui pela escalation honesta.
    if _viola_invencao_comunicacao_interna(text):
        log.error(
            "[FILTRO C-37] INVENÇÃO COMUNICAÇÃO INTERNA BLOQUEADA — "
            "Lia afirmou comunicação com equipe física. Texto: %r",
            text[:200],
        )
        return _INVENCAO_COMUNICACAO_INTERNA_FALLBACK

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
    # Bug C-31 (16/06/2026) — _viola_dia_semana e _viola_oferta_em_dia_nao_atendido
    # SEMPRE-ON (fora do gate FILTROS_LEGACY). Esses são INVARIANTES DUROS, não
    # regras subjetivas: dia-da-semana é fato calculável, médico atende ou não
    # atende é fato operacional. Bug Fábio Philipe 24113652: Lia ofereceu
    # "quarta 18/06" (era quinta) e "sexta 20/06" (era sábado, fim-de-semana,
    # Karla não atende) porque ambos os filtros estavam atrás de FILTROS_LEGACY=0.
    #
    # Bug C-53 (11/07/2026) Beatriz 16843614 — filtro C-31b estava atrás do
    # gate `not ja_agendado`. Lead em 5-AGENDADO com 1.DIA CONSULTA de
    # 07/08/2025 (passado) → ja_agendado=True → filtro pulado → Lia ofereceu
    # "Sexta (07/08) 10:00" e "Segunda (17/08) 10:00" para Karla Águas Claras
    # (que só atende ter/qui). Bug composto: (a) ja_agendado incorretamente
    # True por consulta passada, (b) filtro que valida DIA IMPOSSÍVEL não
    # deveria depender de estado do lead — dia impossível é impossível
    # em qualquer contexto. Fix: quando o texto tem padrão de OFERTA
    # (emoji 1️⃣ 2️⃣, "tenho N horários", "posso oferecer"), rodar os 2
    # filtros SEMPRE, mesmo com ja_agendado=True. Confirmação/referência
    # a agendamento passado NÃO usa esses padrões.
    _padrao_oferta = _texto_parece_oferta_nova(text)
    _pular_por_agendado = bool(ctx and ctx.get("ja_agendado")) and not _padrao_oferta

    if not _pular_por_agendado:
        violacao_dia = _viola_dia_semana(text)
        if violacao_dia:
            dia_falado, data_str, dia_real = violacao_dia
            log.error(
                "[FILTRO C-31a] DIA DA SEMANA INVENTADO — Lia disse '%s' para %s, "
                "mas Python calculou '%s'. ja_agendado=%s padrao_oferta=%s "
                "Texto ORIGINAL completo: %r",
                dia_falado, data_str, dia_real,
                bool(ctx and ctx.get("ja_agendado")), _padrao_oferta, text,
            )
            return _DIA_SEMANA_FALLBACK

        # OFERTA EM DIA QUE O MÉDICO NÃO ATENDE (considera médico+unidade)
        violacao_dia_med = _viola_oferta_em_dia_nao_atendido(text, ctx)
        if violacao_dia_med:
            medico_norm, data_str, dia_real = violacao_dia_med
            log.error(
                "[FILTRO C-31b] OFERTA EM DIA NAO ATENDIDO — médico=%r data=%s "
                "cai em %s. Médico não trabalha nesse dia/unidade. "
                "ja_agendado=%s padrao_oferta=%s Texto: %r",
                medico_norm, data_str, dia_real,
                bool(ctx and ctx.get("ja_agendado")), _padrao_oferta, text[:300],
            )
            return _DIA_NAO_ATENDIDO_FALLBACK

        # C-54 (13/07/2026 — Ubirata/Lucas 24185000): menção a dia-da-semana
        # SEM data (ex: "quinta ou sexta") + unidade no ctx que não bate.
        violacao_dia_sem_data = _viola_dia_sem_data_incompativel_unidade(text, ctx)
        if violacao_dia_sem_data:
            dia_men, medico_norm, unidade_norm = violacao_dia_sem_data
            log.error(
                "[FILTRO C-54] DIA SEM DATA INCOMPATIVEL UNIDADE — "
                "texto menciona %r mas ctx tem medico=%s unidade=%s "
                "(dias permitidos nessa unidade não incluem %r). Texto: %r",
                dia_men, medico_norm, unidade_norm, dia_men, text[:300],
            )
            return _DIA_SEM_DATA_FALLBACK
    else:
        # Log preventivo: paciente já agendado E texto NÃO parece oferta nova
        # → tratamos como confirmação/referência. Se Lia disse algo errado,
        # aparece aqui pra investigar depois.
        violacao_dia_check = _viola_dia_semana(text)
        if violacao_dia_check:
            dia_falado, data_str, dia_real = violacao_dia_check
            log.warning(
                "[FILTRO PULADO ja_agendado=True] _viola_dia_semana detectou "
                "mismatch '%s' vs '%s' em %s, mas paciente já agendado e texto "
                "não parece oferta — considerando confirmação/referência. Texto: %r",
                dia_falado, dia_real, data_str, text,
            )
        violacao_dia_med_check = _viola_oferta_em_dia_nao_atendido(text, ctx)
        if violacao_dia_med_check:
            medico_norm, data_str, dia_real = violacao_dia_med_check
            log.warning(
                "[FILTRO PULADO ja_agendado=True] _viola_oferta_em_dia_nao_atendido "
                "detectou médico=%r data=%s cai em %s (não atende), mas paciente já "
                "agendado e texto não parece oferta — investigar. Texto: %r",
                medico_norm, data_str, dia_real, text[:300],
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
        # Chaos gate — força timeout quando flag Redis ativa (default OFF).
        if _chaos_ativo_anthropic():
            raise TimeoutError("chaos_test_active")

        # ================================================================
        # BYPASS DETERMINÍSTICO DE OFERTA DE AGENDA
        # ================================================================
        # Origem: Fábio 08/07/2026, lead Mariana 24273236. Bug crônico 60d
        # de "Lia inventa frase e trava" nos filtros regex reativos.
        #
        # Quando FSM=AGENDA + dados prontos + médico/unidade + ctx.agenda
        # já pré-buscada pelo pipeline (linha ~347), a mensagem de oferta
        # é montada em PYTHON PURO — LLM NÃO é chamado.
        #
        # Se Medware retornou vazio (ctx.agenda=[]), Python devolve UMA
        # frase canônica de escalação; pipeline complementa desativando
        # IA + movendo pra 1-ATENDIMENTO HUMANO (webhook.py).
        #
        # Toggle rollback: AGENDA_DETERMINISTICA=0 (default ON).
        # ================================================================
        # ================================================================
        # NÍVEL 3 EXPANDIDO — bypasses determinísticos (Fábio 12/07/2026)
        # ================================================================
        # 4 pontos críticos onde LLM inventa. Python monta texto exato.
        # Ordem em `tentar_bypass_deterministico`:
        #   1. urgencia (segurança clínica)
        #   2. valor consulta
        #   3. aceite de slot (paciente disse "1️⃣" ou similar)
        #   4. endereço pós-agenda (agenda gravada + envio pendente)
        # Cada toggle é independente (BLINDAGEM_*_ATIVADO), default ON.
        # ================================================================
        try:
            from voice_agent import blindagens_deterministicas as _blind
            _bypass_result = _blind.tentar_bypass_deterministico(
                caller_context, user_text,
            )
            if _bypass_result is not None:
                _nome_bypass, _texto = _bypass_result
                return {
                    "answer": _texto,
                    "model_used": f"blindagem_{_nome_bypass}",
                    "articles_used": [],
                }
        except Exception:  # noqa: BLE001
            log.exception("[BLINDAGEM] bypass falhou — caindo pra LLM")

        try:
            from voice_agent import oferta_deterministica as _oferta_det
            if _oferta_det.deve_ofertar_agora(caller_context):
                _slots_agenda = (caller_context or {}).get("agenda") or []
                if _slots_agenda:
                    _texto = _oferta_det.montar_texto_2_slots(
                        _slots_agenda, caller_context,
                    )
                    return {
                        "answer": _texto,
                        "model_used": "deterministica_agenda",
                        "articles_used": [],
                    }
                else:
                    _texto = _oferta_det.frase_escalacao_humano(caller_context)
                    return {
                        "answer": _texto,
                        "model_used": "escalacao_medware_vazio",
                        "articles_used": [],
                    }
        except AssertionError:
            # Contrato violado (frase banida vazou) — deixa fluxo normal
            # seguir. Sentinela loga em runtime pra investigação.
            log.exception("[OFERTA_DET] sentinela disparou — caindo pra LLM")
        except Exception:  # noqa: BLE001
            # Qualquer erro (import, ctx malformado, etc) NÃO bloqueia o
            # atendimento. Log e segue pro LLM.
            log.exception("[OFERTA_DET] falha no bypass — caindo pra LLM")

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

        # Task #413 (14/07/2026) — bloco CONVERSA_ATUAL. Quando humano
        # (Ariany/Stephany/etc) mandou mensagem nas últimas 6h, injeta as
        # últimas 20 notas cronológicas (Lia + Humano + Paciente) pra Lia
        # NÃO perder contexto após handoff. Retorna string vazia se não
        # houve handoff humano recente.
        try:
            from voice_agent.historico_conversa import montar_bloco_conversa_atual
            _notas_hist = None
            if isinstance(caller_context, dict):
                _notas_hist = caller_context.get("notas_historico")
            _bloco_conv = montar_bloco_conversa_atual(_notas_hist)
            if _bloco_conv:
                bloco_variavel += _bloco_conv
        except Exception:  # noqa: BLE001
            # Fail-silent: bloco é apenas melhoria, não é obrigatório.
            pass

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
