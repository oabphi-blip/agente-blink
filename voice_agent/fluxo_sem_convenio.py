"""Bug C-138 (14/08/2026) — Fluxo sem convênio 100% Python com benchmarks por especialidade.

Fábio (14/08/2026):
"Como ter um diálogo de atendimento sem convênio 100% com Python.
Pode criar uma versão conversacional para implantar python 100%.
Utilizando um benchmark na área oftalmologia estrabismo, oftalmopediatria,
processamento visual, catarata e refrativa. Para esta convertendo o
atendimento em agendamento. Superando todas objeções conforme os tipos
de preços ofertados no presente momento valores diferentes existentes nos campos."

Arquitetura:
    Quando o paciente é sem convênio e está engajando sem agendar, Python detecta
    a hesitação e entrega conteúdo de benchmark específico para a especialidade —
    o diferencial real da Blink vs uma clínica genérica.

    Escalação por nível (Redis, TTL 48h):
        Nível 0: benchmark de especialidade + valor + parcelamento
        Nível 1: fila de encaixe como alternativa mais acessível
        Nível 2: escalada humana para negociação direta
        Nível 3+: já escalou, não repetir

    Benchmarks por especialidade:
        - oftalmopediatria: janela crítica 0-7 anos (ambliopia/estrabismo precoce)
        - estrabismo: diagnóstico funcional vs estético
        - processamento visual (APV): protocolo 2-3h único em Brasília
        - catarata (Fabrício): biometria inclusa
        - refrativa / saúde ocular adulto 50+: prevenção glaucoma/DM

Toggle: FLUXO_SEM_CONVENIO_ATIVADO (default ON)
Fail-open: qualquer exceção → None (LLM continua normalmente)
"""
from __future__ import annotations

import logging
import os
import re
from typing import Optional

log = logging.getLogger(__name__)

_ATIVADO = os.environ.get("FLUXO_SEM_CONVENIO_ATIVADO", "1").lower() not in (
    "0", "false", "no", "off"
)

# Chave Redis: nível de escalação por lead
_REDIS_KEY_NIVEL = "blink:c138_nivel_sem_convenio:{lead_id}"
_TTL_NIVEL = 48 * 3600  # 48h

# ─────────────────────────────────────────────────────────────────────────────
# Detecção de sem convênio
# ─────────────────────────────────────────────────────────────────────────────

_VALORES_SEM_CONVENIO = frozenset({
    "não se aplica", "nao se aplica", "particular", "sem convênio",
    "sem convenio", "nenhum", "nenhuma", "", "none", "privado",
})

def _e_sem_convenio(ctx: Optional[dict]) -> bool:
    """True se o paciente está pagando sem convênio."""
    known = (ctx or {}).get("known") or {}
    convenio = (known.get("convenio") or "").lower().strip()
    if convenio in _VALORES_SEM_CONVENIO:
        return True
    # Também considerar leads sem convênio definido que chegaram sem info
    sem_flag = known.get("sem_convenio") or known.get("particular")
    return bool(sem_flag)


# ─────────────────────────────────────────────────────────────────────────────
# Detecção de hesitação pós-oferta
# ─────────────────────────────────────────────────────────────────────────────

# Sinais de "ainda pensando" — não é booking, não é objeção específica
_RE_HESITACAO = re.compile(
    r"\b(?:"
    r"vou\s+(?:pensar|ver|verificar|avaliar|considerar)"
    r"|preciso\s+(?:pensar|ver|avaliar|de\s+(?:um\s+)?(?:mais\s+)?tempo)"
    r"|deixa\s+(?:eu\s+)?ver|deixa\s+(?:eu\s+)?pensar"
    r"|vou\s+falar\s+com\s+(?:meu|minha|o\s+meu|a\s+minha)"
    r"|ainda\s+(?:n[aã]o\s+sei|estou\s+vendo|estou\s+pensando)"
    r"|n[aã]o\s+sei\s+ainda|n[aã]o\s+sei\s+ao\s+certo"
    r"|talvez|quem\s+sabe|pode\s+ser"
    r"|t[aá]\s+(?:certo|bom|ok)|ok|ok(?:ay)?|entendi|certo|anotado|beleza"
    r"|interessante|legal|\bah\b|\bhm+\b|\buhm+\b"
    r")\b",
    re.IGNORECASE | re.UNICODE,
)

# Anti-padrão: não é hesitação se está agendando ou confirmando slot
_RE_NAO_HESITACAO = re.compile(
    r"\b(?:"
    r"quero\s+(?:marcar|agendar|confirmar|reservar)"
    r"|pode\s+(?:marcar|agendar|confirmar|reservar)"
    r"|sim\s*[,!]?\s*(?:pode\s+)?(?:marcar|agendar|confirmar)"
    r"|vou\s+(?:marcar|agendar|confirmar)"
    r"|opc[aã]o\s*[123]|op[çc][aã]o\s*[123]"
    r"|[1-3️⃣]\s*[:.]"
    r"|primeiro|segundo|terceiro|1[oº]|2[oº]"
    r")\b",
    re.IGNORECASE | re.UNICODE,
)

def _e_hesitacao(user_text: str) -> bool:
    """True se o paciente está hesitando sem objeção específica."""
    if not user_text or len(user_text.strip()) < 2:
        return False
    if _RE_NAO_HESITACAO.search(user_text):
        return False
    return bool(_RE_HESITACAO.search(user_text))


# ─────────────────────────────────────────────────────────────────────────────
# Derivação de especialidade do ctx
# ─────────────────────────────────────────────────────────────────────────────

def _derivar_especialidade(ctx: Optional[dict]) -> str:
    """Retorna tag de especialidade para selecionar benchmark.

    Tags: 'apv', 'estrabismo', 'oftalmopediatria', 'catarata', 'refrativa', 'geral'
    """
    known = (ctx or {}).get("known") or {}
    medico_raw = (known.get("medico") or "").lower()
    motivo = (known.get("motivo") or known.get("especialidade") or "").lower()
    idade = known.get("idade")
    pediatrico = known.get("contexto_pediatrico", False)

    # APV / Processamento Visual
    if any(k in motivo for k in ("apv", "processamento visual", "sdp", "prisma",
                                  "cefaleia", "cansaco visual", "concentracao")):
        return "apv"

    # Estrabismo
    if any(k in motivo for k in ("estrabismo", "olho torto", "desalinhado",
                                  "lazy eye", "estrabic")):
        return "estrabismo"

    # Catarata
    if any(k in motivo for k in ("catarata", "vista embaçada", "vista embacada",
                                  "nevoeiro", "neblina")):
        return "catarata"
    if "fabr" in medico_raw and "catarata" not in motivo:
        # Fabrício sem catarata explícita → refrativa adulto 50+
        return "refrativa"

    # Oftalmopediatria (Karla + pediátrico)
    if pediatrico or (idade is not None and isinstance(idade, (int, float)) and idade < 18):
        return "oftalmopediatria"

    # Motivo geral infantil
    if any(k in motivo for k in ("crianca", "criança", "bebe", "bebê", "infantil",
                                  "pediatr", "escolar")):
        return "oftalmopediatria"

    # Adulto genérico com Fabrício
    if "fabr" in medico_raw:
        return "refrativa"

    # Padrão Karla adulto
    return "geral"


# ─────────────────────────────────────────────────────────────────────────────
# Benchmarks por especialidade (Nível 0)
# ─────────────────────────────────────────────────────────────────────────────

def _benchmark_oftalmopediatria(nome: str, idade: Optional[int]) -> str:
    """Diferencial: janela crítica 0-7 anos. Ambliopia e estrabismo precoce."""
    faixa = "crianças"
    if idade is not None and idade <= 2:
        faixa = "bebês e recém-nascidos"
    elif idade is not None and isinstance(idade, (int, float)) and idade <= 6:
        faixa = f"crianças de {idade} anos"

    return (
        f"{nome}, entendo — vou te explicar o que está incluso na consulta para "
        f"você entender o valor. 😊\n\n"
        "A Dra. Karla Delalíbera é especialista em oftalmopediatria. Para "
        f"{faixa}, há uma janela crítica até os 7 anos: problemas como "
        "ambliopia (olho preguiçoso) e estrabismo detectados e tratados "
        "agora têm resultado muito melhor do que depois dos 7 anos — "
        "quando o sistema visual já está formado.\n\n"
        "A consulta inclui avaliação completa: acuidade visual adaptada à "
        "idade, refração cicloplégica, fundo de olho e alinhamento ocular. "
        "Em clínicas gerais, nem sempre tem essa especialização para crianças.\n\n"
        "Para facilitar o pagamento:\n"
        "1️⃣ *Pix:* R$ 611\n"
        "2️⃣ *Cartão 1x:* R$ 670\n"
        "3️⃣ *Cartão 2x:* 2x R$ 335 sem juros\n\n"
        "Qual opção funciona melhor para vocês?"
    )


def _benchmark_estrabismo(nome: str) -> str:
    """Diferencial: diagnóstico funcional (não só estético) + window de tratamento."""
    return (
        f"{nome}, sobre a consulta — deixa eu explicar o que está incluso. 😊\n\n"
        "Estrabismo não é só uma questão estética. O olho desalinhado muitas "
        "vezes não trabalha junto com o outro, comprometendo a visão binocular "
        "e a percepção de profundidade — o que afeta coordenação e até aprendizado "
        "escolar em crianças.\n\n"
        "A avaliação da Dra. Karla Delalíbera define se é tratamento clínico "
        "(óculos, oclusão) ou cirúrgico — e ela faz os dois, então você já "
        "sai com o plano completo, sem precisar de segunda opinião.\n\n"
        "Para facilitar:\n"
        "1️⃣ *Pix:* R$ 611\n"
        "2️⃣ *Cartão 2x:* 2x R$ 335 sem juros\n\n"
        "Qual forma de pagamento funciona melhor?"
    )


def _benchmark_apv(nome: str) -> str:
    """Diferencial: protocolo 2-3h único em Brasília."""
    return (
        f"{nome}, sobre a Avaliação do Processamento Visual — "
        "vou explicar o que torna essa consulta diferente. 😊\n\n"
        "É uma avaliação de 2 a 3 horas — bem diferente de uma consulta "
        "de rotina de 30 minutos. A Dra. Karla Delalíbera usa testes "
        "específicos para investigar como a visão se relaciona com sintomas "
        "como cefaleia, cansaço ao ler, dificuldade de concentração e "
        "sensibilidade à luz.\n\n"
        "A maioria das clínicas em Brasília não realiza esse protocolo "
        "completo — é uma especialização que exige equipamento específico "
        "e horas de avaliação dedicada.\n\n"
        "Para facilitar:\n"
        "1️⃣ *Pix:* R$ 800\n"
        "2️⃣ *Cartão 2x:* 2x R$ 435 sem juros\n\n"
        "Qual forma encaixa melhor na sua agenda e orçamento?"
    )


def _benchmark_catarata(nome: str) -> str:
    """Diferencial: biometria inclusa (cobrada separado em muitos lugares)."""
    return (
        f"{nome}, sobre a avaliação com o Dr. Fabrício Freitas — "
        "vou explicar o que está incluso. 😊\n\n"
        "Para catarata, a avaliação inclui biometria ocular — que é o "
        "exame que define os parâmetros exatos da lente intraocular para "
        "a cirurgia. Em muitas clínicas, a biometria é cobrada separado "
        "(R$ 200 a R$ 400). Aqui está inclusa na consulta.\n\n"
        "Você sai com o diagnóstico completo, o grau de opacificação "
        "classificado e o planejamento cirúrgico — se indicado — "
        "tudo em um único atendimento.\n\n"
        "Para facilitar:\n"
        "1️⃣ *Pix:* R$ 445\n"
        "2️⃣ *Cartão 2x:* 2x R$ 235 sem juros\n\n"
        "Qual opção funciona melhor para você?"
    )


def _benchmark_refrativa(nome: str) -> str:
    """Diferencial: saúde ocular adulto 50+ — prevenção glaucoma/DM/pressão."""
    return (
        f"{nome}, sobre a consulta com o Dr. Fabrício Freitas — "
        "vou explicar o que está incluso. 😊\n\n"
        "Para adultos 50+, a consulta vai além dos óculos. O Dr. Fabrício "
        "inclui tonometria (pressão ocular — essencial para rastrear glaucoma), "
        "mapeamento de retina e avaliação de córnea — condições que podem "
        "se desenvolver silenciosamente nessa faixa etária.\n\n"
        "Glaucoma e retinopatia diabética detectados cedo têm tratamento "
        "muito mais eficaz. Isso é prevenção real, não só consulta de rotina.\n\n"
        "Para facilitar:\n"
        "1️⃣ *Pix:* R$ 611\n"
        "2️⃣ *Cartão 2x:* 2x R$ 335 sem juros\n\n"
        "Qual forma de pagamento encaixa melhor?"
    )


def _benchmark_geral(nome: str) -> str:
    """Fallback quando especialidade não identificada."""
    return (
        f"{nome}, sobre a consulta — o valor inclui avaliação completa: "
        "acuidade visual, tonometria, biomicroscopia e orientação "
        "personalizada no mesmo atendimento. 😊\n\n"
        "Não cobramos separado por cada exame realizado durante a consulta.\n\n"
        "Para facilitar:\n"
        "1️⃣ *Pix:* R$ 611\n"
        "2️⃣ *Cartão 2x:* 2x R$ 335 sem juros\n\n"
        "Qual opção funciona melhor para você?"
    )


def _nivel0_benchmark(especialidade: str, nome: str, ctx: Optional[dict]) -> str:
    """Entrega o benchmark de especialidade (Nível 0)."""
    known = (ctx or {}).get("known") or {}
    idade = known.get("idade")

    if especialidade == "apv":
        return _benchmark_apv(nome)
    if especialidade == "estrabismo":
        return _benchmark_estrabismo(nome)
    if especialidade == "oftalmopediatria":
        return _benchmark_oftalmopediatria(nome, idade)
    if especialidade == "catarata":
        return _benchmark_catarata(nome)
    if especialidade == "refrativa":
        return _benchmark_refrativa(nome)
    return _benchmark_geral(nome)


# ─────────────────────────────────────────────────────────────────────────────
# Nível 1: Fila de encaixe como alternativa mais acessível
# ─────────────────────────────────────────────────────────────────────────────

def _nivel1_fila_encaixe(nome: str) -> str:
    return (
        f"{nome}, entendo que o momento pode não ser o ideal. 😊\n\n"
        "Temos uma opção chamada *fila de encaixe*: você entra na fila "
        "e, quando surge uma vaga de encaixe, entramos em contato com "
        "condições diferenciadas — sem precisar pagar a consulta completa agora.\n\n"
        "Essa opção existe justamente para não perder o cuidado com a saúde "
        "por conta do valor no momento.\n\n"
        "Quer entrar na fila de encaixe?"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Nível 2: Escalada humana
# ─────────────────────────────────────────────────────────────────────────────

def _nivel2_escalar(nome: str) -> str:
    return (
        f"{nome}, vou passar você para nossa equipe de atendimento — "
        "elas podem verificar as melhores condições para o seu caso "
        "e te ajudar a encontrar uma solução. 😊\n\n"
        "Aguarda um momento!"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Redis helpers para nível de escalação
# ─────────────────────────────────────────────────────────────────────────────

def _get_nivel(lead_id: str, redis_client) -> int:
    """Lê o nível de escalação do lead. Retorna 0 se não encontrado."""
    try:
        val = redis_client.get(_REDIS_KEY_NIVEL.format(lead_id=lead_id))
        return int(val or 0)
    except Exception:  # noqa: BLE001
        return 0


def _set_nivel(lead_id: str, nivel: int, redis_client) -> None:
    """Grava o nível de escalação com TTL 48h."""
    try:
        redis_client.setex(
            _REDIS_KEY_NIVEL.format(lead_id=lead_id),
            _TTL_NIVEL,
            str(nivel),
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("[C-138] falha ao gravar nivel Redis: %s", exc)


def _extrair_lead_id(ctx: Optional[dict]) -> Optional[str]:
    """Extrai lead_id do ctx."""
    if not ctx:
        return None
    lid = ctx.get("lead_id") or ctx.get("id")
    return str(lid) if lid else None


def _extrair_nome(ctx: Optional[dict]) -> str:
    """Extrai primeiro nome do contato."""
    if not ctx:
        return ""
    known = ctx.get("known") or {}
    nome = (
        known.get("nome_contato")
        or known.get("nome_paciente")
        or ctx.get("name")
        or ctx.get("contact_name")
        or ""
    ).strip()
    if not nome or nome.lower() in ("você", "cliente", "lead", "inbra"):
        return ""
    return nome.split()[0].capitalize()


# ─────────────────────────────────────────────────────────────────────────────
# Função principal
# ─────────────────────────────────────────────────────────────────────────────

def deve_aprofundar_especialidade(
    ctx: Optional[dict],
    user_text: str,
    redis_client=None,
) -> Optional[str]:
    """C-138: quando o paciente é sem convênio e está hesitando sem agendar,
    retorna conteúdo de benchmark específico para a especialidade.

    Progressão por nível (Redis):
        0 → benchmark especialidade + valor + parcelamento
        1 → fila de encaixe como alternativa
        2 → escalada humana
        3+ → None (não repetir, LLM assume)

    Gatilho:
        - Paciente sem convênio
        - Ainda não agendou
        - Inbound com sinal de hesitação ("vou pensar", "entendi", "ok", etc.)
        - Especialidade identificável

    Fail-open: qualquer exceção → None.
    Toggle: FLUXO_SEM_CONVENIO_ATIVADO
    """
    if not _ATIVADO:
        return None

    try:
        if not ctx:
            return None

        known = (ctx or {}).get("known") or {}

        # Gate 1: sem convênio
        if not _e_sem_convenio(ctx):
            return None

        # Gate 2: não agendado ainda
        if known.get("ja_agendado"):
            return None

        # Gate 3: sinal de hesitação no inbound
        if not _e_hesitacao(user_text):
            return None

        # Gate 4: especialidade identificável (ou médico identificado)
        especialidade = _derivar_especialidade(ctx)
        nome = _extrair_nome(ctx)
        lead_id = _extrair_lead_id(ctx)

        # Nível de escalação via Redis
        nivel = 0
        if redis_client and lead_id:
            nivel = _get_nivel(lead_id, redis_client)

        if nivel >= 3:
            # Já escalou tudo — não repetir, deixar LLM assumir
            return None

        # Gerar resposta por nível
        if nivel == 0:
            resposta = _nivel0_benchmark(especialidade, nome, ctx)
        elif nivel == 1:
            resposta = _nivel1_fila_encaixe(nome)
        else:  # nivel == 2
            resposta = _nivel2_escalar(nome)

        # Incrementar nível para próxima vez
        if redis_client and lead_id:
            _set_nivel(lead_id, nivel + 1, redis_client)

        log.info(
            "[C-138] sem_convenio nivel=%d especialidade=%s lead=%s",
            nivel, especialidade, lead_id,
        )
        return resposta

    except Exception as exc:
        log.warning("[C-138] deve_aprofundar_especialidade falhou: %s", exc)
        return None  # fail-open
