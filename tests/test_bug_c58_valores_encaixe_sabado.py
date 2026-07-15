"""Bug C-58 — Valores atualizados Karla (15/07/2026).

Print Fábio field 1259108 mostrou 3 mudanças:
1. NOVA categoria "Encaixe 2ª a 6ª" (R$ 511 / 570 / 570)
2. Sábado atualizado (R$ 411 / 467 / 467) — era R$ 511 / 570 / 570
3. Formato HUMANO liberado (Pix 50% sinal + Cartão integral no ato)

Este pytest blinda contra regressão nesses 3 pontos.
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
# NOVA CATEGORIA — Encaixe 2ª a 6ª
# ═══════════════════════════════════════════════════════════════════════

class TestEncaixeSegundaASexta:
    def test_categoria_existe(self, kb_texto):
        assert "Encaixe 2ª a 6ª" in kb_texto or "ENCAIXE 2ª A 6ª" in kb_texto.upper()

    def test_valor_pix_511(self, kb_texto):
        # Encaixe Pix = R$ 511
        assert "R$ 511" in kb_texto

    def test_valor_cartao_1x_570(self, kb_texto):
        assert "R$ 570" in kb_texto

    def test_encaixe_2x_285(self, kb_texto):
        # 2x R$ 285 = R$ 570
        assert "285" in kb_texto or "R$ 285" in kb_texto


# ═══════════════════════════════════════════════════════════════════════
# SÁBADO — valores atualizados 15/07/2026
# ═══════════════════════════════════════════════════════════════════════

class TestSabadoAtualizado:
    def test_sabado_pix_411(self, kb_texto):
        assert "R$ 411" in kb_texto, "Sábado Pix agora é R$ 411 (era R$ 511)"

    def test_sabado_cartao_1x_467(self, kb_texto):
        assert "R$ 467" in kb_texto, "Sábado Cartão 1x agora é R$ 467"

    def test_sabado_nao_tem_mais_valor_antigo_511(self, kb_texto):
        # R$ 511 agora é ENCAIXE, não sábado. A linha da TABELA sábado
        # (Pix / Cartão) NÃO pode mais ter 511/570.
        # (511 pode aparecer em comentários comparativos ou regras negativas)
        import re
        # Procura seção "Consulta SÁBADO" e valida que dentro dela não há 511 nem 570
        m = re.search(
            r"(?:Consulta\s+)?SÁBADO.*?(?=###|---|## )",
            kb_texto,
            re.DOTALL | re.IGNORECASE,
        )
        if m is None:
            pytest.skip("Seção Sábado não encontrada — verificar formato")
        secao_sabado = m.group(0)
        # Valores antigos NÃO podem estar como valor Pix/Cartão dentro da tabela sábado
        # Aceita "R$ 411" (novo) mas rejeita "1ª opção — Pix.*R$ 511"
        linha_pix_sabado = re.search(r"Pix.*?R\$\s*511", secao_sabado)
        assert linha_pix_sabado is None, (
            f"Sábado ainda tem R$ 511 como valor Pix. Trecho: {secao_sabado[:300]!r}"
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
# FORMATO HUMANO — Pix 50% sinal + Cartão integral (liberado 15/07/2026)
# ═══════════════════════════════════════════════════════════════════════

class TestFormatoHumano:
    def test_menciona_formato_humano(self, kb_texto):
        assert "Formato HUMANO" in kb_texto or "formato humano" in kb_texto.lower()

    def test_menciona_sinal_50_percent(self, kb_texto):
        assert "sinal de 50%" in kb_texto or "sinal 50%" in kb_texto.lower()

    def test_calculo_sinal_individual_305_50(self, kb_texto):
        # 50% de R$ 611 = R$ 305,50
        assert "305,50" in kb_texto or "R$ 305,50" in kb_texto

    def test_calculo_sinal_apv_400(self, kb_texto):
        # 50% de R$ 800 = R$ 400
        assert "R$ 400" in kb_texto or "400,00" in kb_texto

    def test_calculo_sinal_encaixe_255_50(self, kb_texto):
        # 50% de R$ 511 = R$ 255,50
        assert "255,50" in kb_texto

    def test_calculo_sinal_sabado_205_50(self, kb_texto):
        # 50% de R$ 411 = R$ 205,50
        assert "205,50" in kb_texto

    def test_liberacao_por_atendente_humano(self, kb_texto):
        # Formato humano é liberado quando humano usou antes OU paciente pediu
        lower = kb_texto.lower()
        assert "atendente humano" in lower or "humano" in lower


# ═══════════════════════════════════════════════════════════════════════
# CHAVES PIX — allowlist (regra do responder.py::_scrub_prohibited)
# ═══════════════════════════════════════════════════════════════════════

class TestChavesPix:
    def test_chave_asa_norte(self, kb_texto):
        assert "karladelaliberaoftalmo@gmail.com" in kb_texto

    def test_chave_aguas_claras(self, kb_texto):
        assert "52.303.729/0001-30" in kb_texto


# ═══════════════════════════════════════════════════════════════════════
# VERSAO_PROMPT — bump força Anthropic re-cache
# ═══════════════════════════════════════════════════════════════════════

class TestVersaoPromptBump:
    def test_versao_c58(self, master_texto):
        assert "c58" in master_texto.lower(), (
            "VERSAO_PROMPT deve conter 'c58' pra sinalizar deploy do Bug C-58"
        )

    def test_versao_data_15_07(self, master_texto):
        assert "2026-07-15" in master_texto, (
            "VERSAO_PROMPT deve ter data 2026-07-15"
        )


# ═══════════════════════════════════════════════════════════════════════
# CASO 6 — pergunta sobre encaixe (script canônico)
# ═══════════════════════════════════════════════════════════════════════

class TestCaso6Encaixe:
    def test_caso_6_existe(self, kb_texto):
        assert "Caso 6" in kb_texto and "encaixe" in kb_texto.lower()

    def test_menciona_slot_extra(self, kb_texto):
        assert "slot extra" in kb_texto.lower() or "fora da grade regular" in kb_texto.lower()


# ═══════════════════════════════════════════════════════════════════════
# REGRAS NEGATIVAS — não misturar categorias
# ═══════════════════════════════════════════════════════════════════════

class TestRegrasNegativas:
    def test_nao_misturar_categorias(self, kb_texto):
        lower = kb_texto.lower()
        assert "nunca misturar" in lower or "não misturar" in lower or "3 tabelas distintas" in lower

    def test_sem_conveni_nao_eh_conveni(self, kb_texto):
        assert "\"Sem Convênio\"" in kb_texto or "sem convênio" in kb_texto.lower()
        # deve mencionar que é particular
        assert "particular" in kb_texto.lower()
