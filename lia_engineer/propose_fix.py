"""Chama Claude Opus 4.6 pra gerar fix (diff) pro bug detectado.

Recebe BugReport + contexto do código atual → retorna FixProposal com:
- arquivo(s) modificado(s)
- diff completo
- pytest novo cobrindo o caso
- mensagem de commit
- estimativa de risco (low/medium/high)

Não aplica nada. Só propõe. apply_fix.py decide se aplica.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from .detect_bugs import BugReport


CLAUDE_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
OPUS_MODEL = os.getenv("CLAUDE_OPUS_MODEL", "claude-opus-4-6")


@dataclass
class FixProposal:
    """Patch proposto pelo Opus pra resolver um BugReport."""

    bug_report: BugReport
    arquivo_principal: str
    """ex: voice_agent/responder.py"""

    diff_unified: str
    """Patch no formato unified diff (aplicável com `patch -p0`)."""

    arquivo_teste: str
    """ex: tests/test_bug_NNN_descricao.py"""

    teste_codigo: str
    """Código pytest completo cobrindo o caso real."""

    commit_message: str
    """Convencional: fix(cat1): descrição. Refs lead 24125064."""

    risco: str
    """"low" | "medium" | "high" — baseado em quantos arquivos toca."""

    confianca: int
    """0-100, baseado em similaridade com bugs anteriores corrigidos."""

    rollback_plan: str
    """Como reverter se der ruim em prod."""


# ────────────────────────────────────────────────────────────────────────
# Templates de prompt por categoria de bug
# ────────────────────────────────────────────────────────────────────────

PROMPTS_POR_CATEGORIA = {
    "cat1_tool_calling_nao_forcado_em_AGENDA": """
Você é um engenheiro Python sênior da Blink Oftalmologia. Lia (agent WhatsApp)
disse "{texto_lia}" no lead {lead_id} mas a regra é: em FSM=AGENDA, modelo
DEVE chamar a tool `oferecer_slot` em vez de escrever texto livre.

O código atual está em voice_agent/responder.py linhas ~2100-2200 (método
`reply`). Já existe `_select_model_for_state` que faz upgrade pra Opus em
AGENDA, mas hoje o `tool_choice` não é forçado em todos os turnos AGENDA.

PROPOSTA DE FIX (Opus 4.6):
1. Forçar `tool_choice={{"type":"tool","name":"oferecer_slot"}}` em AGENDA
   QUANDO ctx.agenda preenchido E paciente ainda não escolheu slot.
2. Forçar fallback: se modelo NÃO chamou tool → log ERROR + Slack + responder
   com texto gerado pelo helper `_gerar_oferta_2_slots(ctx)` deterministicamente.

Saída esperada: diff unified + pytest novo cobrindo o caso da {texto_lia}.
""",
    "cat1_race_condition_pipeline_lock": """
Race condition: Lia respondeu 2x em <15s. Task #183 (pipeline lock por
`conversation_key`) foi marcada completed mas o bug repete. Investigar:

1. `voice_agent/pipeline.py` — existe lock? está sendo adquirido?
2. Lock por chave correta? (`conv_key = f"lia:lock:{lead_id}"` em Redis com
   SET NX EX 30)
3. Se outro request entra durante lock, está enfileirando ou descartando?

PROPOSTA: SET NX EX 30 + retry 3x com backoff 200ms. Se ainda locked, ENFILEIRAR
inbound em queue Redis (`lia:queue:{conv_key}`). Worker consome queue 1 por vez.

Pytest: simular 3 inbounds em <100ms → esperar EXATAMENTE 1 resposta gerada.
""",
    "cat2_filtro_regex_escapou": """
Filtro `_viola_data_vs_dia_semana` em responder.py NÃO pegou "quarta-feira,
11/06" (deveria ser quarta=10/06). Provavelmente regex não cobre formato
sem hífen ou com espaço diferente.

PROPOSTA: substituir regex por validador semântico:
1. Extrair TODAS as ocorrências `(\\w+)-?feira[,\\s]+(\\d{{1,2}})/(\\d{{1,2}})`
2. Pra cada match: calcular weekday real
3. Se NÃO bate → substituir resposta inteira pelo helper que recalcula
   com dia certo

Pytest: 10 formatos diferentes do mesmo bug. Inclui o caso Tatiana 24125064.
""",
    "cat6_formulario_em_vez_de_dialogo": """
Lia mandou {n_perguntas} perguntas numa mensagem só. Bug C-14 indexado.

PROPOSTA: adicionar `_viola_multiplas_perguntas` em responder.py que:
1. Conta `?` na resposta
2. Se >1 E FSM in (DADOS, CONVENIO): trunca pra primeira pergunta
3. Guarda restante em Redis pra próximo turno

Pytest: cenário Alessandro 24112156 + Tatiana 24125064 turno 4.
""",
    "cat3_kb_kommo_enum_desincronizado": """
Lia disse "Atendemos {convenio}" mas KB 18 marca como NÃO aceito.
Filtro C-16 já existe (`_viola_disse_atende_convenio_nao_aceito`) — verificar
se está em prod. Se não, push imediato. Se sim, regex cobre o convênio?
""",
}


# ────────────────────────────────────────────────────────────────────────
# Funções principais
# ────────────────────────────────────────────────────────────────────────

def montar_prompt(bug: BugReport, codigo_atual: str) -> str:
    """Monta o prompt pro Opus baseado na categoria do bug."""
    template = PROMPTS_POR_CATEGORIA.get(bug.categoria_raiz, PROMPTS_POR_CATEGORIA["cat1_tool_calling_nao_forcado_em_AGENDA"])
    n_perg = bug.texto_lia.count("?")
    return template.format(
        texto_lia=bug.texto_lia[:300],
        lead_id=bug.lead_id,
        convenio=_extrair_convenio(bug.texto_lia),
        n_perguntas=n_perg,
    ) + f"\n\nCÓDIGO ATUAL (excerto):\n```python\n{codigo_atual[:3000]}\n```\n"


def _extrair_convenio(texto: str) -> str:
    import re
    for conv in ["INAS GDF", "Bradesco", "Cassi", "Sul América", "Unimed"]:
        if conv.lower() in texto.lower():
            return conv
    return "<convênio>"


def propor_fix(
    bug: BugReport,
    arquivo_codigo: Path,
    anthropic_client=None,
) -> Optional[FixProposal]:
    """Gera FixProposal chamando Opus 4.6.

    Args:
        bug: BugReport detectado.
        arquivo_codigo: Path do arquivo principal (geralmente responder.py).
        anthropic_client: cliente Anthropic injetado (pra teste).

    Returns:
        FixProposal ou None se Opus não conseguir propor fix com confiança >70.
    """
    if anthropic_client is None:
        from anthropic import Anthropic
        anthropic_client = Anthropic(api_key=CLAUDE_API_KEY)

    codigo_atual = arquivo_codigo.read_text(encoding="utf-8") if arquivo_codigo.exists() else ""
    prompt = montar_prompt(bug, codigo_atual)

    try:
        resp = anthropic_client.messages.create(
            model=OPUS_MODEL,
            max_tokens=8000,
            system=(
                "Você é engenheiro Python sênior da Blink. Gere fixes precisos, "
                "testáveis, com pytest cobrindo o caso real. Sempre incluir "
                "rollback_plan. Confiança honesta — se não tem certeza, "
                "retorne confianca<70 e o sistema escala humano. "
                "Saída SEMPRE em JSON estruturado: "
                "{arquivo_principal, diff_unified, arquivo_teste, teste_codigo, "
                "commit_message, risco, confianca, rollback_plan}."
            ),
            messages=[{"role": "user", "content": prompt}],
        )
        content = resp.content[0].text
        # Extrair JSON da resposta (Opus pode envolver em markdown)
        import re
        m = re.search(r"\{[\s\S]*\}", content)
        if not m:
            return None
        data = json.loads(m.group(0))

        return FixProposal(
            bug_report=bug,
            arquivo_principal=data["arquivo_principal"],
            diff_unified=data["diff_unified"],
            arquivo_teste=data["arquivo_teste"],
            teste_codigo=data["teste_codigo"],
            commit_message=data["commit_message"],
            risco=data.get("risco", "medium"),
            confianca=int(data.get("confianca", 50)),
            rollback_plan=data.get("rollback_plan", "git revert HEAD"),
        )
    except Exception as e:
        # Log e retorna None pra escalar humano
        return None


def confianca_suficiente(proposta: FixProposal, limiar: int = 70) -> bool:
    """True se podemos aplicar sem revisão humana."""
    if proposta.risco == "high":
        return False  # high risk sempre escala
    return proposta.confianca >= limiar
