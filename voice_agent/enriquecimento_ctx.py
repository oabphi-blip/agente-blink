"""
Bug C-102/C-103 (11/08/2026) — Layer 2: Derivação determinística de fatos objetivos

Princípio arquitetural:
  Todo fato derivável de dados estruturados deve estar em ctx.known
  ANTES de qualquer LLM. O LLM só redige — Python decide.

Chamado em pipeline.py após get_caller_context() e ANTES de injetar_pre_slots().

Camadas de derivação (em ordem, sem sobrescrever valor já existente):

  C-102:
  1. data_nasc → idade (anos completos)
  2. idade < 18 → medico = "Karla" (Oftalmopediatria)
  3. motivo → medico (catarata→Fabrício, estrabismo→Karla, etc.)
  4. Normaliza medico se é nome completo Kommo → forma canônica curta

  C-103 (11/08/2026) — derivações adicionais:
  5. medico + motivo → unidade (quando dia_preferido conhecido no calendário)
  6. medico rotina adulto (sem motivo específico) → Karla (default)
  7. convenio (campo Kommo) → convenio_aceito (True/False/None)
  8. medico + convenio → valor_consulta (R$ exato sem LLM)
  9. retorno_ou_nova: ja_agendado passado → "retorno"; nunca veio → "nova"
  10. fonte_captacao → convenio (se campanha "sem convênio" → particular)
"""

import re
import logging
from datetime import date, datetime

log = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Constantes de negócio — fonte única de verdade para Python decidir
# ─────────────────────────────────────────────────────────────────────────────

# Calendário de atendimento Karla (dias da semana: 0=seg,...,6=dom)
_KARLA_ASA_NORTE_DIAS    = {0, 2, 4}   # seg, qua, sex
_KARLA_AGUAS_CLARAS_DIAS = {1, 3}       # ter, qui
_FABRICIO_DIAS           = {1, 3}       # ter, qui (Águas Claras)

# Convênios NÃO aceitos (resposta imediata: não atendemos)
_CONVENIOS_NAO_ACEITOS = frozenset({
    "inas", "gdf", "gdf saúde", "saúde df", "cassi", "sulamerica",
    "sul america", "sul américa", "bradesco", "amil", "unimed",
    "notredame", "notre dame", "hapvida", "saúde da caixa",  # ≠ Saúde Caixa
    "fapes", "ipe", "ipc", "geap",
})

# Convênios aceitos (subset de PLANO_CODES em medware.py)
_CONVENIOS_ACEITOS = frozenset({
    "pro ser stj", "stj", "tjdft", "pró-saúde", "plan assiste", "mpf", "mpu",
    "e-vida", "luminar", "anafe", "bacen", "care plus", "casec", "codevasf",
    "casembrapa", "embrapa", "conab", "fascal", "omint", "pf saúde",
    "polícia federal", "policia federal", "plas", "jmu", "stm", "proasa",
    "saúde caixa", "petrobrás", "saúde petrobrás", "serpro", "sis senado",
    "stf-med", "stf med", "trf", "trf pró-social", "tre", "trt", "tst saúde",
    "tst", "pró saúde câmara", "câmara dos deputados", "camara", "afego",
    "affego", "não se aplica", "particular", "sem convênio",
})

# Tabela de valores — Python decide, LLM só formata
# Estrutura: (medico_lower, convenio_lower) → (pix_valor, cartao_1x, cartao_2x_cada)
_TABELA_VALORES = {
    ("karla", "particular"):     (611.0, 670.0, 335.0),
    ("karla", "não se aplica"):  (611.0, 670.0, 335.0),
    ("karla", "sem convênio"):   (611.0, 670.0, 335.0),
    ("karla", "avaliação do processamento visual"): (800.0, 800.0, 400.0),
    ("karla", "sdp"):            (800.0, 800.0, 400.0),
    ("fabrício", "particular"):  (445.0, 470.0, 235.0),
    ("fabrício", "não se aplica"): (445.0, 470.0, 235.0),
    ("fabrício", "sem convênio"): (445.0, 470.0, 235.0),
    # Convênio aceito → valor coberto (não aplica tabela particular)
    # → valor_consulta = None significa "coberto pelo convênio"
}

# Valor padrão Karla particular (mais comum)
_VALOR_KARLA_PADRAO    = (611.0, 670.0, 335.0)
_VALOR_FABRICIO_PADRAO = (445.0, 470.0, 235.0)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers de normalização
# ─────────────────────────────────────────────────────────────────────────────

def _normalizar_medico(medico_raw: str) -> str:
    """Mapeia nome completo Kommo → forma canônica curta. Fail-safe."""
    m = medico_raw.lower()
    if "karla" in m:
        return "Karla"
    if "fabr" in m:
        return "Fabrício"
    if "kátia" in m or "katia" in m:
        return "Kátia"
    if "marcelo" in m or "paraíba" in m or "paraiba" in m:
        return "Marcelo"
    if "isabela" in m or "nacarato" in m:
        return "Isabela"
    return medico_raw


def _calcular_idade(data_nasc_val) -> "int | None":
    """Aceita ISO string / Kommo datetime / Unix timestamp → idade em anos."""
    if not data_nasc_val:
        return None
    today = date.today()
    try:
        ts = int(data_nasc_val)
        if 0 < ts < 4_000_000_000:
            nasc = datetime.fromtimestamp(ts).date()
            return max(0, (today - nasc).days // 365)
    except (ValueError, TypeError, OSError):
        pass
    val_str = str(data_nasc_val).strip()
    try:
        nasc = date.fromisoformat(val_str[:10])
        return max(0, (today - nasc).days // 365)
    except (ValueError, TypeError):
        pass
    log.debug("[C-102] _calcular_idade: formato não reconhecido %r", data_nasc_val)
    return None


# ── Regex médico por motivo ──────────────────────────────────────────────────

_MOTIVO_FABRICIO_RE = re.compile(
    r"\b(catarata|c[oó]rnea|pter[íiy]g[io]o?|carne\s+no\s+olho"
    r"|ceratocon[oe]|transplante(?:\s+de)?\s+c[oó]rnea)\b",
    re.IGNORECASE,
)
_MOTIVO_KARLA_RE = re.compile(
    r"\b(estrabismo|oftalmopediatria|pediatria|pedi[aá]tr"
    r"|processamento\s+visual|sdp|lazy\s+eye|ambliop[ia]"
    r"|vis[aã]o\s+dupla|avalia[cç][aã]o\s+visual)\b",
    re.IGNORECASE,
)


def _medico_por_motivo(motivo: str) -> str:
    """'Fabrício', 'Karla' ou '' se não inferível."""
    if _MOTIVO_FABRICIO_RE.search(motivo):
        return "Fabrício"
    if _MOTIVO_KARLA_RE.search(motivo):
        return "Karla"
    return ""


# ── Derivação de unidade ─────────────────────────────────────────────────────

def _unidade_por_medico_e_dia(medico: str, dia_semana: "int | None") -> "str | None":
    """Dado médico + dia da semana (0=seg), retorna unidade canônica ou None.

    None = não derivável (médico desconhecido ou dia não especificado).
    """
    m = medico.lower()
    if "karla" in m:
        if dia_semana in _KARLA_ASA_NORTE_DIAS:
            return "Asa Norte"
        if dia_semana in _KARLA_AGUAS_CLARAS_DIAS:
            return "Águas Claras"
    if "fabr" in m:
        if dia_semana in _FABRICIO_DIAS:
            return "Águas Claras"
    return None


def _dia_semana_de_preferencia(known: dict) -> "int | None":
    """Extrai dia da semana (0-6) da preferência do paciente em ctx.known."""
    dia_pref = (known.get("dia_pref") or "").lower().strip()
    if not dia_pref:
        return None
    _MAP = {
        "segunda": 0, "seg": 0, "segunda-feira": 0,
        "terça": 1, "terca": 1, "ter": 1, "terça-feira": 1,
        "quarta": 2, "qua": 2, "quarta-feira": 2,
        "quinta": 3, "qui": 3, "quinta-feira": 3,
        "sexta": 4, "sex": 4, "sexta-feira": 4,
        "sábado": 5, "sabado": 5, "sab": 5,
        "domingo": 6, "dom": 6,
    }
    for key, val in _MAP.items():
        if key in dia_pref:
            return val
    return None


# ── Validação de convênio ─────────────────────────────────────────────────────

def _convenio_aceito(convenio: str) -> "bool | None":
    """True = aceito, False = não aceito, None = não reconhecido (LLM decide)."""
    c = convenio.lower().strip()
    if not c or c in ("", "nenhum", "sem", "não tem"):
        return None
    for nao in _CONVENIOS_NAO_ACEITOS:
        if nao in c:
            return False
    for sim in _CONVENIOS_ACEITOS:
        if sim in c:
            return True
    return None  # não mapeado — LLM decide


# ── Derivação de valor ───────────────────────────────────────────────────────

def _valor_consulta(medico: str, convenio: str) -> "tuple | None":
    """Retorna (pix, cartao_1x, cartao_2x_cada) ou None se coberto por convênio."""
    m = medico.lower().strip()
    c = convenio.lower().strip()

    # Convênio aceito (não particular) → coberto pelo plano
    if c and _convenio_aceito(convenio) is True and c not in (
        "não se aplica", "particular", "sem convênio"
    ):
        return None  # coberto — sem tabela de preço

    # Particular / sem convênio
    chave = (
        "karla" if "karla" in m else ("fabrício" if "fabr" in m else None),
        c if c else "particular",
    )
    if chave in _TABELA_VALORES:
        return _TABELA_VALORES[chave]

    # Fallback por médico
    if "karla" in m:
        return _VALOR_KARLA_PADRAO
    if "fabr" in m:
        return _VALOR_FABRICIO_PADRAO
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Função principal
# ─────────────────────────────────────────────────────────────────────────────

def enriquecer_known(caller_context: dict) -> dict:
    """Layer 2: Derivação determinística completa de ctx.known.

    Nunca sobrescreve valor já existente.
    Idempotente — pode ser chamada N vezes sem efeito adicional.
    Fail-safe — qualquer exceção interna retorna ctx inalterado.
    """
    known = caller_context.get("known")
    if not isinstance(known, dict):
        return caller_context

    try:
        _enriquecer_interno(known, caller_context)
    except Exception as e:  # noqa: BLE001
        log.warning("[C-103] enriquecimento_ctx falhou parcialmente: %s", e)

    return caller_context


def _enriquecer_interno(known: dict, ctx: dict) -> None:
    """Executa todas as derivações em sequência."""

    # ── C-102-1. data_nasc → idade ────────────────────────────────────────────
    data_nasc = known.get("data_nasc") or ""
    if data_nasc and not known.get("idade"):
        idade = _calcular_idade(data_nasc)
        if idade is not None:
            known["idade"] = idade
            log.debug("[C-102] data_nasc=%r → idade=%d", data_nasc, idade)

    # ── C-102-2. idade < 18 → medico = Karla ─────────────────────────────────
    idade = known.get("idade")
    if isinstance(idade, (int, float)) and not known.get("medico"):
        if idade < 18:
            known["medico"] = "Karla"
            log.debug("[C-102] idade=%d < 18 → medico=Karla", int(idade))

    # ── C-102-3. motivo → medico ──────────────────────────────────────────────
    if not known.get("medico"):
        motivo = (known.get("motivo") or "").strip()
        if motivo:
            medico_inf = _medico_por_motivo(motivo)
            if medico_inf:
                known["medico"] = medico_inf
                log.debug("[C-102] motivo=%r → medico=%r", motivo, medico_inf)

    # ── C-102-4. Normaliza nome completo Kommo → canônico ────────────────────
    medico_raw = known.get("medico") or ""
    if len(medico_raw) > 12:
        medico_norm = _normalizar_medico(medico_raw)
        if medico_norm != medico_raw:
            known["medico"] = medico_norm
            log.debug("[C-102] normalizado medico: %r → %r", medico_raw, medico_norm)

    # ── C-103-5. Adulto sem motivo específico → Karla (default) ─────────────
    # Fabrício só quando motivo = catarata/córnea. Rotina adulto → Karla.
    if not known.get("medico"):
        idade = known.get("idade")
        motivo = (known.get("motivo") or "").lower()
        # Se adulto (≥18 ou desconhecido) e motivo não é Fabrício → Karla default
        if not _MOTIVO_FABRICIO_RE.search(motivo):
            known["medico"] = "Karla"
            log.debug("[C-103] adulto rotina sem motivo Fabrício → medico=Karla (default)")

    # ── C-103-6. medico + dia_preferido → unidade ────────────────────────────
    if not known.get("unidade"):
        medico = known.get("medico") or ""
        dia_num = _dia_semana_de_preferencia(known)
        if dia_num is not None and medico:
            unidade = _unidade_por_medico_e_dia(medico, dia_num)
            if unidade:
                known["unidade"] = unidade
                log.debug(
                    "[C-103] medico=%r + dia_pref=%r → unidade=%r",
                    medico, known.get("dia_pref"), unidade,
                )

    # ── C-103-7. convenio → convenio_aceito (bool) ───────────────────────────
    if "convenio_aceito" not in known:
        convenio = (known.get("convenio") or "").strip()
        if convenio:
            aceito = _convenio_aceito(convenio)
            if aceito is not None:
                known["convenio_aceito"] = aceito
                log.debug(
                    "[C-103] convenio=%r → convenio_aceito=%s",
                    convenio, aceito,
                )

    # ── C-103-8. medico + convenio → valor_consulta ──────────────────────────
    if "valor_consulta" not in known:
        medico = known.get("medico") or ""
        convenio = known.get("convenio") or "particular"
        if medico:
            val = _valor_consulta(medico, convenio)
            known["valor_consulta"] = val  # None = coberto pelo convênio
            log.debug(
                "[C-103] medico=%r + convenio=%r → valor=%s",
                medico, convenio, val,
            )

    # ── C-103-9. Retorno ou nova consulta ─────────────────────────────────────
    if not known.get("tipo_consulta"):
        # ja_agendado com data passada = retorno. Nunca consultou = nova.
        ja_agendado = ctx.get("ja_agendado", False)
        dia_consulta_ts = ctx.get("dia_consulta_ts") or 0
        if ja_agendado and dia_consulta_ts:
            from datetime import datetime as _dt
            try:
                data_consulta = _dt.fromtimestamp(int(dia_consulta_ts)).date()
                if data_consulta < date.today():
                    known["tipo_consulta"] = "retorno"
                    log.debug("[C-103] dia_consulta passado → tipo_consulta=retorno")
            except Exception:
                pass

    # ── C-103-10. fonte_captacao → convenio particular ────────────────────────
    # Leads vindos de campanha "sem convênio" → particular implícito
    if not known.get("convenio"):
        fonte = (ctx.get("fonte_captacao") or "").lower()
        if any(p in fonte for p in ("particular", "sem convenio", "sem convênio", "privado")):
            known["convenio"] = "Não se aplica"
            log.debug("[C-103] fonte_captacao=%r → convenio=Não se aplica", fonte)

    # ── C-105-11. agenda → slots_selecionados (Python escolhe, LLM só formata) ──
    # Pré-seleciona 3 slots antes do LLM. _agenda_block usa esses slots
    # diretamente em vez de expor a agenda inteira ao modelo.
    # Condição: agenda disponível + slots ainda não selecionados + toggle ON.
    if not known.get("slots_selecionados") and ctx.get("agenda"):
        try:
            from voice_agent.oferta_slot_deterministico import selecionar_slots
            turno_pref = known.get("turno_preferido")
            # ja_ofertados via E6-B (Redis) — omitido aqui para não criar
            # dependência síncrona de Redis no enriquecimento; o caller pode
            # passar via ctx["slots_ja_ofertados"] se disponível.
            ja_ofertados = set(ctx.get("slots_ja_ofertados") or [])
            slots = selecionar_slots(ctx["agenda"], turno_pref=turno_pref,
                                     ja_ofertados=ja_ofertados)
            if slots:
                known["slots_selecionados"] = slots
                log.debug(
                    "[C-105] %d slots pré-selecionados (turno_pref=%r)",
                    len(slots), turno_pref,
                )
        except Exception as _exc:
            log.warning("[C-105] selecionar_slots falhou: %s", _exc)

    # ── C-106-12. user_text → idade + contexto_pediatrico + medico (antes de FAQ valor) ──
    # Quando paciente diz "para 3 anos" / "minha filha de 5 anos", Python extrai
    # a idade e injeta medico=Karla antes do bypass de valor ser chamado.
    # Isso garante que deve_responder_valor receba ctx.known.medico=Karla e
    # ctx.known.contexto_pediatrico=True — retornando resposta pediátrica, não tabela geral.
    user_text = ctx.get("user_text", "")
    if user_text and not known.get("contexto_pediatrico"):
        try:
            import re as _re
            _RE_IDADE_C106 = _re.compile(
                r"(?:para|de|com|tem)\s+(\d{1,2})\s+anos?"
                r"|\b(\d{1,2})\s+anos?\s+de\s+(?:idade|vida)\b",
                _re.IGNORECASE,
            )
            _RE_MESES_C106 = _re.compile(r"\b\d{1,2}\s+meses?\b", _re.IGNORECASE)
            _RE_KID_C106 = _re.compile(
                r"\b(?:beb[eê]|crian[çc]a|filho|filha|infantil|rec[eé]m[- ]?nascido)\b",
                _re.IGNORECASE,
            )
            _age_m = _RE_IDADE_C106.search(user_text)
            _idade_extraida = None
            if _age_m:
                _idade_extraida = int(_age_m.group(1) or _age_m.group(2))
            elif _RE_MESES_C106.search(user_text):
                _idade_extraida = 0  # bebê em meses → < 18
            elif _RE_KID_C106.search(user_text):
                _idade_extraida = 5  # placeholder < 18 — apenas ativa pediátrico

            if _idade_extraida is not None:
                if not known.get("idade"):
                    known["idade"] = _idade_extraida
                if _idade_extraida < 18:
                    known["contexto_pediatrico"] = True
                    if not known.get("medico"):
                        known["medico"] = "Karla"
                        log.debug("[C-106] user_text=%r → idade=%d → medico=Karla pediátrico",
                                  user_text[:60], _idade_extraida)
        except Exception as _exc_c106:
            log.warning("[C-106] step 12 falhou: %s", _exc_c106)

    # ── C-107-13. user_text → objecao_preco (antes do LLM, antes do bypass valor) ──
    # Detecta objeção de preço ("caro", "encontrei mais barato", "não tenho esse valor")
    # e injeta known["objecao_preco"]=True para que o bypass em blindagens_deterministicas
    # entregue o script contextualizado de quebra de objeção.
    # Roda APÓS o step 12 (pediatrico/medico já injetado) para que o script de objeção
    # já saiba qual médico usar na resposta.
    try:
        if user_text and not known.get("objecao_preco"):
            from voice_agent.objecao_preco import detectar_objecao_preco as _det_c107
            if _det_c107(user_text):
                known["objecao_preco"] = True
                log.debug("[C-107] objecao_preco detectada em user_text=%r", user_text[:60])
    except Exception as _exc_c107:
        log.warning("[C-107] step 13 falhou: %s", _exc_c107)

    # ── C-109-15. noshow_count → sinal_obrigatorio / escalar_noshow (antes do LLM) ──
    # Política (KB 38_politica_sinal_remarcacao_noshow.md):
    #   >= 2 no-shows → sinal Pix 50% OBRIGATÓRIO (sem opção Fila de Encaixe)
    #   >= 3 no-shows → pagamento INTEGRAL antecipado + escalar para humano
    # LLM NUNCA verificava esse campo — Python injeta flags antes do bypass.
    try:
        _ns_c109 = int(known.get("noshow_count") or 0)
        if _ns_c109 >= 2 and not known.get("sinal_obrigatorio"):
            known["sinal_obrigatorio"] = True
            known["noshow_count_val"] = _ns_c109
            if _ns_c109 >= 3:
                known["escalar_noshow"] = True
            log.info(
                "[C-109] noshow_count=%d → sinal_obrigatorio=True escalar=%s",
                _ns_c109, known.get("escalar_noshow", False),
            )
    except Exception as _exc_c109:
        log.warning("[C-109] step 15 falhou: %s", _exc_c109)

    # ── C-108-14. user_text → desistencia_explicita (antes do LLM) ──
    # Detecta desistência inequívoca ("desisti", "não quero mais", "vou em outro lugar")
    # e injeta known["desistencia_explicita"]=True para que o bypass entregue resposta
    # de encerramento elegante — sem o LLM tentar salvar a conversa.
    try:
        if user_text and not known.get("desistencia_explicita"):
            from voice_agent.desistencia import detectar_desistencia as _det_c108
            if _det_c108(user_text):
                known["desistencia_explicita"] = True
                log.info("[C-108] desistencia_explicita detectada user_text=%r", user_text[:60])
    except Exception as _exc_c108:
        log.warning("[C-108] step 14 falhou: %s", _exc_c108)

    # ── C-110-16. user_text → cpf_validado (antes do LLM) ──
    # Extrai CPF do user_text e injeta known["cpf_validado"] se matematicamente válido.
    # CPF inválido = known["cpf_invalido_detectado"]=True para que bypass bloqueie.
    # Não sobrescreve CPF já validado de turnos anteriores.
    try:
        if user_text and not known.get("cpf_validado"):
            from voice_agent.validacao_cpf import (
                extrair_cpf_do_texto as _extrair_cpf,
                cpf_matematicamente_valido as _cpf_valido,
            )
            _cpf_raw = _extrair_cpf(user_text)
            if _cpf_raw is not None:
                if _cpf_valido(_cpf_raw):
                    known["cpf_validado"] = _cpf_raw
                    known.pop("cpf_invalido_detectado", None)
                    log.info("[C-110] CPF válido injetado em known lead=%s", ctx.get("lead_id"))
                else:
                    known["cpf_invalido_detectado"] = True
                    log.info(
                        "[C-110] CPF inválido detectado lead=%s: %s***",
                        ctx.get("lead_id"), _cpf_raw[:3],
                    )
    except Exception as _exc_c110:
        log.warning("[C-110] step 16 falhou: %s", _exc_c110)

    # ── C-113-18. Múltiplos pacientes: injeta n_patients a partir do user_text (se não preenchido por C-81) ──
    # C-81 já injeta n_patients na primeira mensagem. Aqui cobrimos turnos subsequentes
    # onde o paciente MENCIONA múltiplos pela primeira vez (ex: "ah, são 2 filhos").
    try:
        if user_text and not known.get("multiplos_pacientes"):
            from voice_agent.multiplos_pacientes import detectar_multiplos_pacientes as _det_multi
            _n = _det_multi(user_text, ctx)
            if _n >= 2:
                known["multiplos_pacientes"] = _n
    except Exception as _exc_c113:
        log.warning("[C-113] step 18 falhou: %s", _exc_c113)

    # ── C-112-17. Protocolo retorno pediátrico: extrai 1.MÊS PRÓX CONSULTA e 1.DIA CONSULTA ──
    # Injeta known["prox_consulta_mes"] e known["dia_consulta"] a partir de campos Kommo.
    # Roda ANTES de qualquer bypass deterministico para que deve_bloquear_oferta_retorno possa agir.
    try:
        from voice_agent.protocolo_retorno import enriquecer_ctx_protocolo_retorno as _enriquecer_retorno
        _enriquecer_retorno(ctx)
    except Exception as _exc_c112:
        log.warning("[C-112] step 17 falhou: %s", _exc_c112)

    # ── C-131-19. Extração determinística nome/data/CPF do inbound ──────────────────────────
    # Fix do loop infinito "Qual a data de nascimento?" (leads 24448016 Lorena/Nicolas,
    # 24448040 Patrícia): quando C-125 perguntou data/nome/CPF e paciente respondeu,
    # Python extrai e grava em ctx.known ANTES do checklist → C-125 não repete a pergunta.
    # Raiz do loop: C-130 passava para LLM que não atualizava ctx.known → próximo turno
    # checklist ainda via campo vazio → C-125 disparava de novo. C-131 corta o ciclo.
    try:
        from voice_agent.extracao_resposta_c131 import extrair_e_injetar_resposta_c131 as _injetar_c131
        _injetar_c131(ctx, user_text)
    except Exception as _exc_c131:
        log.warning("[C-131] step 19 falhou: %s", _exc_c131)
