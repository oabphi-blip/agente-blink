"""
Bug C-58 / Task #413 (14-15/07/2026) — Handoff humano preserva contexto.

Caso Emmy Rodrigues Santana (lead 24300272):
  1. Paciente conversa com Lia
  2. Ariany manda mensagem no meio ("Estou verificando aqui pra você")
  3. Paciente responde ao humano
  4. Lia é reativada
  5. Lia PERDE contexto — trata como nova conversa OU silencia

Fix: quando `caller_context.notas_historico` tem nota humana das últimas
6h, injeta bloco CONVERSA_ATUAL no system prompt com últimas 20 notas
cronológicas (Lia + Humano + Paciente). Lia lê e continua do ponto.

Módulos:
- voice_agent/historico_conversa.py — helpers + montar_bloco_conversa_atual
- voice_agent/kommo.py::get_caller_context_by_lead — expõe notas_historico
- voice_agent/responder.py — injeta bloco no bloco_variavel do system prompt
"""

from __future__ import annotations

import time
from datetime import datetime, timezone


from voice_agent.historico_conversa import (
    houve_handoff_humano_recente,
    montar_bloco_conversa_atual,
    _autor_da_nota,
    _texto_limpo,
    _eh_nota_lia,
    _eh_nota_humano_lendo_paciente,
    _eh_nota_paciente,
)


# ---------- Helpers de teste ----------

def _ts_iso(offset_seg: int = 0) -> str:
    """ISO 8601 UTC com offset em segundos relativo a agora."""
    ts = time.time() + offset_seg
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat().replace(
        "+00:00", "Z"
    )


def _nota_lia(texto: str, min_atras: int = 5) -> dict:
    return {
        "text": f"🤖 Lia (WhatsApp): {texto}",
        "created_by": 0,
        "created_at": _ts_iso(-min_atras * 60),
    }


def _nota_paciente(texto: str, min_atras: int = 4) -> dict:
    return {
        "text": f"💬 Paciente (WhatsApp): {texto}",
        "created_by": 0,
        "created_at": _ts_iso(-min_atras * 60),
    }


def _nota_humana(texto: str, min_atras: int = 3, uid: int = 14326384) -> dict:
    return {
        "text": texto,
        "created_by": uid,
        "created_at": _ts_iso(-min_atras * 60),
    }


# ---------- Detecção de handoff ----------

def test_c58_handoff_recente_detectado():
    """Nota humana das últimas 6h → handoff detectado."""
    notas = [
        _nota_lia("Olá!", min_atras=30),
        _nota_humana("Aqui é a Ariany, vou te ajudar", min_atras=10),
    ]
    assert houve_handoff_humano_recente(notas) is True


def test_c58_sem_handoff_humano_falso():
    """Só bot + paciente, sem humano → handoff=False."""
    notas = [
        _nota_lia("Olá!", min_atras=30),
        _nota_paciente("Oi", min_atras=25),
        _nota_lia("Como posso ajudar?", min_atras=20),
    ]
    assert houve_handoff_humano_recente(notas) is False


def test_c58_handoff_antigo_ignorado():
    """Nota humana de >6h → não é handoff atual."""
    notas = [
        _nota_humana("Aqui é a Stephany", min_atras=60 * 8),  # 8h atrás
        _nota_lia("Retomando conversa", min_atras=5),
    ]
    assert houve_handoff_humano_recente(notas) is False


def test_c58_notas_vazias_sem_handoff():
    assert houve_handoff_humano_recente(None) is False
    assert houve_handoff_humano_recente([]) is False


# ---------- Bloco CONVERSA_ATUAL ----------

def test_c58_bloco_conversa_gera_quando_ha_handoff():
    """Bloco NÃO é vazio quando há handoff recente."""
    notas = [
        _nota_lia("Olá! Qual seu convênio?", min_atras=30),
        _nota_paciente("Saúde Caixa", min_atras=28),
        _nota_humana("Aqui é a Ariany, vou verificar", min_atras=10),
        _nota_paciente("Obrigada!", min_atras=5),
    ]
    bloco = montar_bloco_conversa_atual(notas)
    assert bloco != ""
    assert "CONVERSA ATUAL" in bloco
    assert "REGRA DE OURO" in bloco


def test_c58_bloco_vazio_sem_handoff():
    """Sem handoff humano → bloco NÃO é injetado (evita ruído)."""
    notas = [
        _nota_lia("Olá!", min_atras=30),
        _nota_paciente("Oi", min_atras=25),
    ]
    bloco = montar_bloco_conversa_atual(notas)
    assert bloco == ""


def test_c58_bloco_bate_formato_esperado():
    """Bloco tem entradas [LIA HH:MM], [HUMANO HH:MM], [PACIENTE HH:MM]."""
    notas = [
        _nota_lia("Bom dia!", min_atras=20),
        _nota_humana("Aqui é a Ariany", min_atras=15),
        _nota_paciente("Obrigada", min_atras=10),
    ]
    bloco = montar_bloco_conversa_atual(notas)
    assert "[LIA " in bloco
    assert "[HUMANO " in bloco
    assert "[PACIENTE " in bloco
    assert "Bom dia" in bloco
    assert "Ariany" in bloco
    assert "Obrigada" in bloco


def test_c58_bloco_ordenado_cronologicamente():
    """Notas mais recentes aparecem por último no bloco."""
    notas = [
        _nota_humana("Terceira", min_atras=5),
        _nota_lia("Primeira", min_atras=30),
        _nota_paciente("Segunda", min_atras=15),
    ]
    bloco = montar_bloco_conversa_atual(notas)
    pos_primeira = bloco.find("Primeira")
    pos_segunda = bloco.find("Segunda")
    pos_terceira = bloco.find("Terceira")
    assert pos_primeira < pos_segunda < pos_terceira


def test_c58_bloco_limita_20_notas():
    """Se há >20 notas, mantém apenas as últimas 20."""
    notas = []
    for i in range(30):
        notas.append(_nota_lia(f"turno{i}", min_atras=60 - i * 2))
    # Adiciona nota humana recente pra ativar bloco
    notas.append(_nota_humana("humano aqui", min_atras=1))

    bloco = montar_bloco_conversa_atual(notas, max_notas=20)
    # Conta linhas de turno
    assert "turno0" not in bloco  # 1º descartado
    assert "turno29" in bloco  # último mantido
    assert "humano aqui" in bloco


# ---------- Casos reais Emmy 24300272 ----------

def test_c58_caso_emmy_lia_pergunta_humano_responde():
    """Cenário real: Lia perguntou, humano respondeu, paciente continuou.
    Lia reativada precisa saber o que humano disse."""
    notas = [
        _nota_lia("Qual médico você prefere?", min_atras=25),
        _nota_paciente("Não sei, me indica um bom", min_atras=22),
        _nota_humana(
            "Emmy, aqui é a Ariany. Recomendo a Dra. Karla Delalíbera.",
            min_atras=15,
        ),
        _nota_paciente("Ok, aceito", min_atras=10),
    ]
    bloco = montar_bloco_conversa_atual(notas)
    assert "Karla Delalíbera" in bloco
    assert "aceito" in bloco
    # Lia NÃO pode repetir "qual médico você prefere?"
    assert "REGRA DE OURO" in bloco


def test_c58_caso_emmy_paciente_ja_deu_convenio_pro_humano():
    """Paciente respondeu convênio ao humano — Lia não pode repetir."""
    notas = [
        _nota_lia("Você tem convênio?", min_atras=30),
        _nota_humana("Oi Emmy, aqui é a Stephany. Qual seu convênio?", min_atras=25),
        _nota_paciente("Bacen", min_atras=20),
        _nota_humana("Bacen ok, atendemos!", min_atras=15),
    ]
    bloco = montar_bloco_conversa_atual(notas)
    assert "Bacen" in bloco
    assert "atendemos" in bloco


# ---------- Helpers internos ----------

def test_c58_eh_nota_lia_detecta_prefixo():
    n = _nota_lia("teste")
    assert _eh_nota_lia(n) is True


def test_c58_eh_nota_humana_created_by_positivo():
    n = _nota_humana("teste")
    assert _eh_nota_humano_lendo_paciente(n) is True


def test_c58_eh_nota_paciente_prefixo_emoji():
    n = _nota_paciente("teste")
    assert _eh_nota_paciente(n) is True


def test_c58_autor_categoriza_correto():
    assert _autor_da_nota(_nota_lia("x")) == "LIA"
    assert _autor_da_nota(_nota_paciente("x")) == "PACIENTE"
    assert _autor_da_nota(_nota_humana("x")) == "HUMANO"
    assert _autor_da_nota({"created_by": 0, "text": "sistema qualquer"}) == "SISTEMA"


def test_c58_texto_limpo_remove_prefixos():
    assert _texto_limpo(_nota_lia("hello")) == "hello"
    assert _texto_limpo(_nota_paciente("world")) == "world"
    assert _texto_limpo({"text": "sem prefixo"}) == "sem prefixo"


# ---------- Integração ----------

def test_c58_responder_importa_montar_bloco():
    """responder.py deve importar e chamar montar_bloco_conversa_atual."""
    from pathlib import Path
    responder_py = (
        Path(__file__).resolve().parent.parent / "voice_agent" / "responder.py"
    ).read_text(encoding="utf-8")
    assert "montar_bloco_conversa_atual" in responder_py, (
        "responder.py deve importar montar_bloco_conversa_atual"
    )
    assert "notas_historico" in responder_py, (
        "responder.py deve ler caller_context['notas_historico']"
    )


def test_c58_kommo_expoe_notas_historico():
    """kommo.py::get_caller_context_by_lead deve popular ctx['notas_historico']."""
    from pathlib import Path
    kommo_py = (
        Path(__file__).resolve().parent.parent / "voice_agent" / "kommo.py"
    ).read_text(encoding="utf-8")
    assert 'out["notas_historico"]' in kommo_py or "out['notas_historico']" in kommo_py, (
        "kommo.py deve popular out['notas_historico'] em get_caller_context_by_lead"
    )
