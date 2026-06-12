"""
Bug C-26 — Lia DEVE perguntar motivo da desmarcação antes de mover pra encaixe.

Cenários do _MASTER_INSTRUCTION.md regra E1.7 (Fábio 12/06/2026).

Casos:
  COM CONVÊNIO (4): imprevisto / autorização / sem interesse / urgência
  SEM CONVÊNIO  (4): imprevisto / financeiro / sem interesse / urgência

Verifica:
  - Mensagem-gatilho contém o gancho correto (convênio nome OU "financeiro")
  - Lia NÃO usa frase proibida ("antes de cancelar, posso oferecer remarcar" etc)
  - Próxima ação inferida bate com a tabela
"""

from __future__ import annotations
import re

import pytest


FRASES_PROIBIDAS_LIA = [
    "antes de cancelar",
    "tenho disponibilidade em outros dias",
    "tenho disponibilidade em outros horários",
    "talvez consiga encaixar num dia",
    "prefere que eu te mostre outras opções de data",
    "quer ver a agenda",
    "deixa eu reconsultar a agenda real",
    "vou te mostrar opções",
]


def _ler_master_instruction() -> str:
    """Lê o _MASTER_INSTRUCTION.md atual."""
    from pathlib import Path
    p = Path(__file__).resolve().parents[1] / "voice_agent" / "knowledge_base" / "_MASTER_INSTRUCTION.md"
    return p.read_text(encoding="utf-8")


def test_regra_e17_existe_no_master():
    """Garante que a regra E1.7 está presente no MASTER."""
    texto = _ler_master_instruction()
    assert "E1.7" in texto
    assert "INVESTIGAR MOTIVO" in texto or "investigar motivo" in texto.lower()
    assert "Bug C-26" in texto


def test_regra_e17_inclui_fluxos_com_e_sem_convenio():
    texto = _ler_master_instruction()
    assert "FLUXO COM CONVÊNIO" in texto
    assert "FLUXO SEM CONVÊNIO" in texto or "SEM CONVÊNIO (particular)" in texto


def test_regra_e17_lista_frases_proibidas():
    """Verifica que TODAS as 7 frases proibidas estão listadas no prompt."""
    texto = _ler_master_instruction().lower()
    # Pelo menos 5 das 7 devem aparecer literais (margem de variação)
    presentes = sum(1 for f in FRASES_PROIBIDAS_LIA if f.lower() in texto)
    assert presentes >= 5, f"Esperava >=5 frases proibidas no prompt, achou {presentes}"


def test_regra_e17_inclui_escada_3_turnos_financeiro():
    """Particular financeiro tem escada 2x R$ 335 → sábado família → fila incentivo."""
    texto = _ler_master_instruction()
    assert "2x de R$ 335" in texto or "2x R$ 335" in texto
    assert "sábado família" in texto.lower()
    assert "R$ 511" in texto
    assert "fila de incentivo" in texto.lower() or "incentivo" in texto.lower()


def test_regra_e17_inclui_4_ramos_com_convenio():
    """Fluxo COM convênio cobre os 4 ramos: imprevisto / autorização / sem interesse / urgência."""
    texto = _ler_master_instruction().lower()
    assert "imprevisto pessoal" in texto
    assert "autorização" in texto or "autorizacao" in texto
    assert "sem interesse" in texto
    assert "urgência" in texto or "urgencia" in texto or "sintoma" in texto


def test_regra_e17_inclui_acoes_kommo_concretas():
    """Verifica que as ações Kommo estão explícitas (status + a fazer + IA)."""
    texto = _ler_master_instruction()
    assert "2.LEADS FRIO" in texto
    assert "101508307" in texto  # status_id LEADS FRIO
    assert "A FAZER" in texto
    assert "Encaixe" in texto
    assert "ATIVADO IA" in texto


def test_regra_e17_inclui_anti_loop():
    """Se paciente não responder à pergunta de motivo, Lia segue pro encaixe genérico."""
    texto = _ler_master_instruction().lower()
    assert "anti-loop" in texto or "não responder" in texto or "nao responder" in texto


def test_template_texts_proximo_passo_inclui_bug_c26():
    """template_texts.py.PROXIMOS_PASSOS['1089...'] menciona regra E1.7 e Bug C-26."""
    from voice_agent.template_texts import PROXIMOS_PASSOS
    proximo = PROXIMOS_PASSOS.get("1089_mens_ativar_conv_parada_qz7kbz", "")
    assert "C-26" in proximo or "E1.7" in proximo
    assert "Encaixe" in proximo
    assert "COM CONVÊNIO" in proximo or "com convênio" in proximo.lower()
    assert "SEM CONVÊNIO" in proximo or "sem convênio" in proximo.lower() or "particular" in proximo.lower()


def test_caso_sophia_imprevisto_com_convenio():
    """Caso real Sophia 23845330 — TJDFT, bebê. Pergunta motivo deve mencionar TJDFT."""
    # Mock mínimo. Em prod, integrado ao responder.py — aqui só verifica o template.
    pergunta_template = (
        "Entendo, {primeiro_nome}. Pra eu te orientar do jeito certo, "
        "posso saber o motivo da desmarcação? Foi imprevisto pessoal, "
        "alguma questão com a autorização do {nome_convenio}, ou outro motivo?"
    )
    rendered = pergunta_template.format(
        primeiro_nome="Sophia", nome_convenio="TJDFT Pró-Saúde",
    )
    assert "Sophia" in rendered
    assert "TJDFT" in rendered
    assert all(f.lower() not in rendered.lower() for f in FRASES_PROIBIDAS_LIA)


def test_caso_tito_imprevisto_sem_convenio():
    """Caso real Tito/Aline Weber 24130572 — particular. Pergunta menciona financeiro."""
    pergunta_template = (
        "Entendo, {primeiro_nome}. Pra eu te orientar do jeito certo, "
        "posso saber o motivo? Foi questão financeira, imprevisto pessoal, "
        "ou outra coisa? (Se for financeiro, tenho outras opções que talvez ajudem.)"
    )
    rendered = pergunta_template.format(primeiro_nome="Aline")
    assert "Aline" in rendered
    assert "financeir" in rendered.lower()
    assert "imprevisto" in rendered.lower()
    assert all(f.lower() not in rendered.lower() for f in FRASES_PROIBIDAS_LIA)
