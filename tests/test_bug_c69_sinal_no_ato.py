"""Bug C-69 — Script sinal 50% no ato do agendamento (22/07/2026).

Origem: Fábio 22/07/2026 — alta taxa de desmarcação, precisa criar
compromisso financeiro no ato do agendamento.

Testa que o prompt tem:
    (a) Nova seção 0-AF explícita
    (b) VERSAO_PROMPT bumped pra c69
    (c) Script canônico com 3 opções (2 datas + encaixe)
    (d) Menção ao sinal 50% Pix pras opções 1 e 2
    (e) Encaixe (opção 3) paga no dia
    (f) Regras negativas explícitas
"""
from __future__ import annotations

from pathlib import Path

import pytest


MASTER_PATH = Path("voice_agent/knowledge_base/_MASTER_INSTRUCTION.md")


@pytest.fixture(scope="module")
def master_texto():
    return MASTER_PATH.read_text(encoding="utf-8")


# ═══════════════════════════════════════════════════════════════════════
# VERSAO_PROMPT bump
# ═══════════════════════════════════════════════════════════════════════

class TestVersaoBump:
    def test_versao_c69(self, master_texto):
        assert "c69" in master_texto.lower()

    def test_versao_data_22_07(self, master_texto):
        assert "2026-07-22" in master_texto


# ═══════════════════════════════════════════════════════════════════════
# Seção 0-AF adicionada
# ═══════════════════════════════════════════════════════════════════════

class TestSecaoAF:
    def test_secao_existe(self, master_texto):
        assert "0-AF" in master_texto
        assert "OFERTA DE 2 SLOTS" in master_texto

    def test_menciona_combate_desmarcacao(self, master_texto):
        lower = master_texto.lower()
        assert "desmarca" in lower  # "desmarcação" ou "desmarcar"

    def test_menciona_sinal_50(self, master_texto):
        assert "sinal de 50%" in master_texto or "sinal 50%" in master_texto

    def test_menciona_pix_no_ato(self, master_texto):
        lower = master_texto.lower()
        assert "pix" in lower and "no ato" in lower


# ═══════════════════════════════════════════════════════════════════════
# Script canônico completo
# ═══════════════════════════════════════════════════════════════════════

class TestScriptCanonico:
    def test_3_opcoes(self, master_texto):
        # Deve mencionar todas as 3 opções
        assert "1️⃣" in master_texto
        assert "2️⃣" in master_texto
        assert "3️⃣" in master_texto

    def test_intro_com_base_em_preferencias(self, master_texto):
        assert "Com base em suas preferências" in master_texto

    def test_menciona_unidade(self, master_texto):
        assert "Unidade: [UNIDADE]" in master_texto or "**Unidade:" in master_texto

    def test_lista_espera_encaixe(self, master_texto):
        lower = master_texto.lower()
        assert "lista de espera" in lower
        assert "encaixe" in lower
        assert "pagamento no dia" in lower

    def test_cta_qual_escolha(self, master_texto):
        assert "Qual a sua escolha?" in master_texto


# ═══════════════════════════════════════════════════════════════════════
# Cálculo do sinal por categoria
# ═══════════════════════════════════════════════════════════════════════

class TestCalculoSinal:
    def test_menciona_karla_611_e_305_50(self, master_texto):
        assert "R$ 611" in master_texto
        assert "305,50" in master_texto

    def test_menciona_apv_800_e_400(self, master_texto):
        assert "R$ 800" in master_texto
        assert "R$ 400" in master_texto or "400,00" in master_texto

    def test_menciona_encaixe_511_e_255_50(self, master_texto):
        assert "R$ 511" in master_texto
        assert "255,50" in master_texto

    def test_menciona_fabricio_445_e_222_50(self, master_texto):
        assert "R$ 445" in master_texto
        assert "222,50" in master_texto


# ═══════════════════════════════════════════════════════════════════════
# Regras negativas
# ═══════════════════════════════════════════════════════════════════════

class TestRegrasNegativas:
    def test_proibicao_inventar_slot(self, master_texto):
        lower = master_texto.lower()
        assert "nunca" in lower or "proibido" in lower or "❌" in master_texto

    def test_proibicao_aceitar_pagar_tudo_no_dia_opcao_1_2(self, master_texto):
        lower = master_texto.lower()
        # Regra: opções 1/2 exigem sinal; só encaixe (3) paga no dia
        assert "pago tudo no dia" in lower or "pagar tudo no dia" in lower


# ═══════════════════════════════════════════════════════════════════════
# Racional / ROI
# ═══════════════════════════════════════════════════════════════════════

class TestRacionalROI:
    def test_menciona_no_show(self, master_texto):
        lower = master_texto.lower()
        assert "no-show" in lower or "no show" in lower

    def test_menciona_compromisso(self, master_texto):
        lower = master_texto.lower()
        assert "compromisso" in lower
