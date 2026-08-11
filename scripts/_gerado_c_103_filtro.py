# ─── Bug C-103 (11/08/2026) ─────────────────────────────────────────────────────
# LLM pergunta convênio quando ctx.known.convenio já está preenchido
_FRASES_PROIBIDAS_C_103 = re.compile(
    r"(?:(?:Atendimento\s+será\s+por\s+convênio)|(?:atendimento\s+sem\s+convênio)|(?:qual\s+convênio\s+você\s+utiliza)|(?:convênio\s+ou\s+particular))",
    re.IGNORECASE,
)

def _viola_bug_c_103(text: str, ctx: dict) -> "str | None":
    """LLM pergunta convênio quando ctx.known.convenio já está preenchido — Bug C-103.
    Retorna substituição se violação detectada, None se OK."""
    # Condição de contexto: só bloqueia quando bool((caller_context.get('known') or {}).get('convenio'))
    if not (bool((caller_context.get('known') or {}).get('convenio'))):
        return None
    if _FRASES_PROIBIDAS_C_103.search(text):
        log.warning("[C-103] frase proibida detectada: %r", text[:120])
        return (
            "Deixa eu verificar os horários disponíveis para você."
        )
    return None