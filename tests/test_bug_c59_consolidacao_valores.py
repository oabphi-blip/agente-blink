"""Bug C-59 — Consolidação Encaixe/Sábado/Mais de 2 (15/07/2026 noite).

Print Fábio consolidou 2 categorias antes separadas:
- Encaixe 2ª-6ª (R$ 511)
- Sábado (R$ 411 na versão C-58)

Agora: UMA categoria "Encaixe/Sábado/Mais de 2 pacientes" (R$ 511/570/570).
Sábado NÃO tem mais R$ 411 (foi anulado na consolidação).
"""
from __future__ import annotations

from pathlib import Path

import pytest


KB_PATH = Path("voice_agent/knowledge_base/39_valores_consulta.md")
MASTER_PATH = Path("voice_agent/knowledge_base/_MASTER_INSTRUCTION.md")


@pytest.fixture(scope="module")
def kb_texto():
    return KB_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def master_texto():
    return MASTER_PATH.read_text(encoding="utf-8")


# ═══════════════════════════════════════════════════════════════════════
# Categoria consolidada Encaixe/Sábado/Mais de 2
# ═══════════════════════════════════════════════════════════════════════

class TestCategoriaConsolidada:
    def test_categoria_menciona_encaixe_sabado_mais2(self, kb_texto):
        # Deve mencionar as 3 palavras (encaixe, sábado, mais de 2)
        lower = kb_texto.lower()
        assert "encaixe" in lower
        assert "sábado" in lower
        assert "mais de 2" in lower or "3+" in lower or "família" in lower

    def test_valor_consolidado_511(self, kb_texto):
        assert "R$ 511" in kb_texto

    def test_valor_consolidado_570(self, kb_texto):
        assert "R$ 570" in kb_texto

    def test_sabado_nao_tem_mais_411(self, kb_texto):
        # Valor antigo (C-58) foi CANCELADO na consolidação
        # R$ 411 pode aparecer só em contextos históricos, mas nunca como
        # valor Pix da tabela sábado atual
        import re
        # Procura "Consulta SÁBADO/ENCAIXE" section...
        # (Como agora é consolidado, valida que R$ 411 NÃO aparece como valor de tabela)
        # Aceita "R$ 411" só se estiver em contexto de "era" ou histórico
        m_411 = re.findall(r"R\$\s*411", kb_texto)
        # Idealmente zero; permite até 1 (menção histórica em nota de revisão)
        assert len(m_411) <= 0, (
            f"R$ 411 aparece {len(m_411)}x no KB — deveria ter sido removido "
            f"na consolidação Bug C-59"
        )


# ═══════════════════════════════════════════════════════════════════════
# INDIVIDUAL + APV + FABRÍCIO — mantidos
# ═══════════════════════════════════════════════════════════════════════

class TestValoresMantidos:
    def test_individual_611(self, kb_texto):
        assert "R$ 611" in kb_texto

    def test_individual_670(self, kb_texto):
        assert "R$ 670" in kb_texto

    def test_apv_800(self, kb_texto):
        assert "R$ 800" in kb_texto

    def test_apv_870(self, kb_texto):
        assert "R$ 870" in kb_texto

    def test_fabricio_445(self, kb_texto):
        assert "R$ 445" in kb_texto

    def test_fabricio_470(self, kb_texto):
        assert "R$ 470" in kb_texto


# ═══════════════════════════════════════════════════════════════════════
# FORMATO HUMANO — Pix 50% sinal (mantido, cálculos atualizados)
# ═══════════════════════════════════════════════════════════════════════

class TestFormatoHumano:
    def test_menciona_formato_humano(self, kb_texto):
        assert "Formato HUMANO" in kb_texto or "formato humano" in kb_texto.lower()

    def test_sinal_individual_305_50(self, kb_texto):
        # 50% de R$ 611 = R$ 305,50
        assert "305,50" in kb_texto

    def test_sinal_encaixe_sabado_255_50(self, kb_texto):
        # 50% de R$ 511 = R$ 255,50
        assert "255,50" in kb_texto

    def test_sinal_apv_400(self, kb_texto):
        # 50% de R$ 800 = R$ 400
        assert "R$ 400" in kb_texto or "400,00" in kb_texto

    def test_sinal_fabricio_222_50(self, kb_texto):
        # 50% de R$ 445 = R$ 222,50
        assert "222,50" in kb_texto


# ═══════════════════════════════════════════════════════════════════════
# CASOS 5, 6, 7 — sábado / encaixe / família (todos MESMO valor)
# ═══════════════════════════════════════════════════════════════════════

class TestCasosConsolidados:
    def test_caso_5_sabado(self, kb_texto):
        assert "Caso 5" in kb_texto
        # Sábado com R$ 511 (não R$ 411)
        pos_caso5 = kb_texto.find("Caso 5")
        pos_caso6 = kb_texto.find("Caso 6")
        secao = kb_texto[pos_caso5:pos_caso6 if pos_caso6 > 0 else pos_caso5 + 2000]
        assert "R$ 511" in secao

    def test_caso_6_encaixe(self, kb_texto):
        assert "Caso 6" in kb_texto and "encaixe" in kb_texto.lower()

    def test_caso_7_familia_mais2(self, kb_texto):
        assert "Caso 7" in kb_texto
        # Deve mencionar 3+ pacientes ou família
        pos = kb_texto.find("Caso 7")
        secao = kb_texto[pos:pos + 500]
        assert "3" in secao and ("família" in secao.lower() or "pacientes" in secao.lower())


# ═══════════════════════════════════════════════════════════════════════
# CHAVES PIX — allowlist mantida
# ═══════════════════════════════════════════════════════════════════════

class TestChavesPix:
    def test_chave_asa_norte(self, kb_texto):
        assert "karladelaliberaoftalmo@gmail.com" in kb_texto

    def test_chave_aguas_claras(self, kb_texto):
        assert "52.303.729/0001-30" in kb_texto


# ═══════════════════════════════════════════════════════════════════════
# VERSAO_PROMPT bump
# ═══════════════════════════════════════════════════════════════════════

class TestVersaoPrompt:
    def test_versao_c59(self, master_texto):
        assert "c59" in master_texto.lower()

    def test_versao_data_15_07(self, master_texto):
        assert "2026-07-15" in master_texto


# ═══════════════════════════════════════════════════════════════════════
# REGRA NEGATIVA — nao misturar categorias
# ═══════════════════════════════════════════════════════════════════════

class TestRegrasNegativas:
    def test_regra_nao_misturar(self, kb_texto):
        lower = kb_texto.lower()
        # Deve avisar pra não misturar encaixe/sábado (R$ 511) com individual (R$ 611)
        assert "nunca misturar" in lower or "não misturar" in lower
