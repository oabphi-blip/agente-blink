"""Juiz adversarial Haiku — segundo olhar sobre toda resposta da Lia.

Origem: discussão Fábio 01/06/2026 ("como aproveitar ML pra defesa
contra bug?"). Os 13 filtros pós-geração existentes em responder.py
são REATIVOS — cada um cobre um bug que já aconteceu (Aurora, Juliene,
Adelia, Diones, Esther). O próximo bug é sempre uma frase nova que
nenhum regex pega.

Este módulo coloca um **classificador semântico** (Haiku 4.5) antes do
envio. Haiku recebe (resposta da Lia, ctx do lead) e devolve JSON com:
- risco: 0-100
- motivos: lista de strings ("oferta apos agendado", "promete retorno
  humano", "cobra antes de slot", "inventa orientacao", etc)
- recomendado: "enviar" | "substituir"

Quando `risco >= LIMIAR` (default 70), a resposta é substituída por um
fallback seguro genérico ("Anotei aqui! Em instantes confirmo com a
equipe e te respondo. Se preferir, me diga qual sua dúvida específica."),
e o motivo + payload é gravado em Redis pra análise.

Custo: ~$0.001/turno (Haiku 4.5 com prompt curto). Para tráfego típico
da Blink (~200 turnos/dia), <$0.20/dia. Vale qualquer 1 bug evitado.

Liga via env `JUIZ_HAIKU_ENABLED=1`. Default off — rollout gradual.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, Optional

log = logging.getLogger(__name__)


# Limiar default (env override JUIZ_HAIKU_LIMIAR)
LIMIAR_DEFAULT = 70

# Fallback padrão quando juiz vetar resposta. Genérico e seguro:
# - não promete agenda, não promete retorno humano, não inventa.
# - convida o paciente a esclarecer.
FALLBACK_SUBSTITUICAO = (
    "Anotei aqui! Em instantes confirmo os detalhes e te respondo. "
    "Se preferir, me diga sua dúvida específica que eu agilizo."
)


@dataclass
class VeredictoJuiz:
    """Resultado do julgamento de uma resposta da Lia."""
    risco: int = 0
    motivos: list[str] = field(default_factory=list)
    recomendado: str = "enviar"  # "enviar" | "substituir"
    raw_response: str = ""
    elapsed_ms: int = 0
    erro: Optional[str] = None

    @property
    def deve_substituir(self) -> bool:
        return self.recomendado == "substituir"


def _resumir_ctx_pro_juiz(ctx: Optional[dict]) -> str:
    """Compacta o ctx pro Haiku enxergar só o essencial.

    Não passa caller_context inteiro (centenas de linhas) — só os flags
    de decisão. Foca em:
    - ja_agendado (1 == bug Aurora/Esther se Lia oferecer slot)
    - has_agenda (1 == bug Adelia/Juliene se Lia disser "deixa eu consultar")
    - status_id (rótulo humano)
    - tem dia_consulta (data marcada)
    - nome do paciente conhecido
    """
    if ctx is None:
        return "(sem contexto - lead novo ou anônimo)"
    known = (ctx.get("known") or {}) if isinstance(ctx, dict) else {}
    ja_ag = bool(ctx.get("ja_agendado"))
    has_ag = bool(ctx.get("agenda"))
    status = ctx.get("etapa") or ctx.get("status_id") or "?"
    nome_pac = known.get("nome_paciente") or ""
    dia_iso = known.get("dia_consulta_iso") or ""
    medico = known.get("medico") or ""
    unidade = known.get("unidade") or ""
    linhas = [
        f"ja_agendado: {ja_ag}",
        f"agenda_disponivel: {has_ag}",
        f"etapa_atual: {status}",
    ]
    if nome_pac:
        linhas.append(f"paciente: {nome_pac}")
    if dia_iso:
        linhas.append(f"consulta_marcada_em: {dia_iso}")
    if medico:
        linhas.append(f"medico: {medico}")
    if unidade:
        linhas.append(f"unidade: {unidade}")
    return "\n".join(linhas)


_PROMPT_JUIZ = (
    "Você é o auditor de qualidade do agente Lia, da clínica Blink "
    "Oftalmologia (DF). Sua função é dar um SEGUNDO OLHAR em cada "
    "resposta da Lia ANTES dela ser enviada ao paciente via WhatsApp.\n\n"
    "REGRAS DE OURO da Blink (devem ser respeitadas SEMPRE):\n"
    "1. Se 'ja_agendado: True' → NÃO oferecer slot novo, NÃO refazer "
    "triagem, NÃO perguntar 'qual dia/turno prefere'. Só confirma o "
    "que já está marcado.\n"
    "2. Se 'agenda_disponivel: True' → NÃO dizer 'deixa eu consultar "
    "a agenda', 'um momentinho', 'vou buscar os horários'. Lia já tem "
    "slots, deve oferecer 2 direto.\n"
    "3. NUNCA prometer 'retorno em horário comercial', 'equipe humana "
    "finaliza', 'vou registrar pra equipe' (= alucinação de handoff).\n"
    "4. NUNCA inventar chave Pix. Asa Norte é "
    "karladelaliberaoftalmo@gmail.com (e-mail). Águas Claras é "
    "52.303.729/0001-30 (CNPJ). Qualquer outra chave = bug.\n"
    "5. NUNCA cobrar sinal/Pix antes de oferecer um slot CONCRETO (dia "
    "da semana + data + hora) e o paciente ter escolhido.\n"
    "6. NUNCA afirmar 'gravei no Medware', 'sua consulta está "
    "confirmada no sistema' sem evidência real — Lia não tem leitura "
    "do Medware em tempo real.\n"
    "7. Se ctx indicar paciente com médico A (ex.: Karla) → NUNCA "
    "mencionar médico B (Fabrício) como o que vai atender.\n"
    "8. NUNCA inventar orientação clínica (jejum, dilatação, "
    "acompanhante obrigatório, brinquedo, lanche). Só fala o que está "
    "na KB Blink.\n"
    "9. NUNCA dizer 'Doutor Karla' (é doutora). NUNCA misturar contato "
    "(quem escreve) com paciente (quem vai à consulta).\n\n"
    "CONTEXTO DO LEAD (resumo):\n{ctx_str}\n\n"
    "MENSAGEM ANTERIOR DO PACIENTE (último inbound):\n{user_text}\n\n"
    "RESPOSTA QUE A LIA QUER ENVIAR:\n«{lia_text}»\n\n"
    "Avalie. Devolva APENAS um JSON, sem markdown, com este formato "
    "exato:\n"
    '{{"risco": <int 0-100>, "motivos": [<strings curtas>], '
    '"recomendado": "enviar" | "substituir"}}\n\n'
    "Critério de risco:\n"
    "  0-30: ok, pode enviar\n"
    "  31-69: ok mas borderline (envia, registra alerta)\n"
    "  70-100: substitui — viola uma das regras acima\n\n"
    "Importante: seja conservador. Se a resposta da Lia respeita as "
    "9 regras e responde à mensagem do paciente, dê risco baixo. "
    "Substitua APENAS quando há violação concreta. Não penalize "
    "respostas curtas/normais de confirmação."
)


def _extrair_json(texto: str) -> dict[str, Any]:
    """Tenta parsear JSON do texto. Lida com markdown fences, lixo
    antes/depois, etc. Devolve {} em erro."""
    if not texto:
        return {}
    # remove fences markdown
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", texto.strip(), flags=re.MULTILINE)
    # acha primeiro `{` e último `}`
    a = t.find("{")
    b = t.rfind("}")
    if a < 0 or b <= a:
        return {}
    try:
        return json.loads(t[a:b + 1])
    except (ValueError, json.JSONDecodeError):
        return {}


class JuizAdversarial:
    """Wrapper Haiku 4.5 — chama API e parseia veredicto.

    Uso:
        juiz = JuizAdversarial(api_key, model="claude-haiku-4-5-20251001")
        veredicto = juiz.julgar(lia_text="...", ctx={...}, user_text="oi")
        if veredicto.deve_substituir:
            resposta_final = FALLBACK_SUBSTITUICAO
        else:
            resposta_final = lia_text
    """

    def __init__(
        self,
        api_key: str,
        model: str = "claude-haiku-4-5-20251001",
        timeout: float = 8.0,
        limiar: int = LIMIAR_DEFAULT,
        max_tokens: int = 200,
    ):
        # Import tardio pra não pesar quando juiz não está ativo
        from anthropic import Anthropic
        self._client = Anthropic(api_key=api_key, timeout=timeout)
        self.model = model
        self.timeout = timeout
        self.limiar = limiar
        self.max_tokens = max_tokens

    @classmethod
    def from_env(cls) -> Optional["JuizAdversarial"]:
        """Constrói a partir das envs. Devolve None se desativado/sem key."""
        if os.getenv("JUIZ_HAIKU_ENABLED", "0") != "1":
            return None
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            log.warning("[JUIZ] JUIZ_HAIKU_ENABLED=1 mas falta ANTHROPIC_API_KEY")
            return None
        model = (
            os.getenv("CLAUDE_HAIKU_MODEL")
            or "claude-haiku-4-5-20251001"
        )
        try:
            limiar = int(os.getenv("JUIZ_HAIKU_LIMIAR", str(LIMIAR_DEFAULT)))
        except (TypeError, ValueError):
            limiar = LIMIAR_DEFAULT
        return cls(api_key=api_key, model=model, limiar=limiar)

    def julgar(
        self,
        lia_text: str,
        ctx: Optional[dict] = None,
        user_text: str = "",
    ) -> VeredictoJuiz:
        """Devolve veredicto. Em erro/timeout devolve veredicto neutro
        (recomendado=enviar, risco=0) pra não bloquear a Lia.
        """
        v = VeredictoJuiz()
        if not lia_text or not lia_text.strip():
            return v
        ctx_str = _resumir_ctx_pro_juiz(ctx)
        # Limita user_text pra evitar prompt gigante
        ut = (user_text or "").strip()
        if len(ut) > 800:
            ut = ut[:800] + "…"
        lt = lia_text.strip()
        if len(lt) > 2000:
            lt = lt[:2000] + "…"
        prompt = _PROMPT_JUIZ.format(
            ctx_str=ctx_str, user_text=ut or "(vazio)", lia_text=lt,
        )
        t0 = time.time()
        try:
            resp = self._client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = ""
            for block in (resp.content or []):
                txt = getattr(block, "text", "")
                if txt:
                    raw += txt
            v.raw_response = raw
            parsed = _extrair_json(raw)
            v.risco = int(parsed.get("risco", 0))
            motivos = parsed.get("motivos") or []
            if isinstance(motivos, list):
                v.motivos = [str(m) for m in motivos if m][:6]
            rec = str(parsed.get("recomendado", "enviar")).strip().lower()
            if rec == "substituir" or v.risco >= self.limiar:
                v.recomendado = "substituir"
            else:
                v.recomendado = "enviar"
        except Exception as e:  # noqa: BLE001
            log.warning("[JUIZ] erro Haiku: %s", e)
            v.erro = str(e)
            # Não bloqueia em erro — só loga
            v.recomendado = "enviar"
        v.elapsed_ms = int((time.time() - t0) * 1000)
        return v


def gravar_veredicto_redis(
    redis_client: Any,
    lead_id: int | str,
    veredicto: VeredictoJuiz,
    lia_text: str,
) -> None:
    """Persiste veredicto no Redis pra auditoria futura.

    Chave: `blink:juiz:veredicto:{lead_id}:{ts}` com TTL 7 dias.
    """
    if not redis_client or not veredicto:
        return
    try:
        payload = {
            "ts": int(time.time()),
            "risco": veredicto.risco,
            "motivos": veredicto.motivos,
            "recomendado": veredicto.recomendado,
            "elapsed_ms": veredicto.elapsed_ms,
            "lia_text_preview": (lia_text or "")[:300],
            "erro": veredicto.erro,
        }
        key = f"blink:juiz:veredicto:{lead_id}:{int(time.time())}"
        redis_client.setex(key, 7 * 24 * 3600, json.dumps(payload))
    except Exception as e:  # noqa: BLE001
        log.warning("[JUIZ] grava redis falhou: %s", e)
