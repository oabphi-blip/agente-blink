"""Learning Loop Automático — pytest das 3 peças."""
from __future__ import annotations

import os
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from voice_agent.learning_loop import (
    _PADROES_CORRECAO,
    _eh_nota_humana,
    _eh_nota_lia,
    _proximo_bug_auto_id,
    append_bug_no_claude_md,
    detectar_correcao_humana,
    gerar_entrada_bug_auto,
    processar_lead,
    re_indexar_se_mudou,
)


# ═══════════════════════════════════════════════════════════════════════
# PEÇA 1 — Detector
# ═══════════════════════════════════════════════════════════════════════

class TestPadroesRegex:
    @pytest.mark.parametrize("texto", [
        "Lia, não é assim",
        "Não é isso, corrija",
        "Lia, cuidado — não é assim",
        "A forma correta é...",
        "O correto é dizer...",
        "Ela está errado aí",
        "Nunca diga isso pro paciente",
        "Regra correta é...",
        "Erro da Lia — corrigindo",
    ])
    def test_detecta_padrao_correcao(self, texto):
        assert _PADROES_CORRECAO.search(texto) is not None

    @pytest.mark.parametrize("texto", [
        "Obrigado!",
        "Perfeito.",
        "Vou verificar",
        "Está bem",
    ])
    def test_nao_detecta_em_texto_normal(self, texto):
        assert _PADROES_CORRECAO.search(texto) is None


class TestClassificacaoNota:
    def test_lia_created_by_zero(self):
        assert _eh_nota_lia({"created_by": 0}) is True
        assert _eh_nota_humana({"created_by": 0}) is False

    def test_humano_created_by_id(self):
        assert _eh_nota_lia({"created_by": 12345}) is False
        assert _eh_nota_humana({"created_by": 12345}) is True


class TestDetectarCorrecao:
    def _mock_kommo(self, notas):
        m = MagicMock()
        m.get_lead_notes = MagicMock(return_value=notas)
        return m

    def test_par_lia_humano_curto_janela_ok(self):
        agora = time.time()
        # Notas vêm desc (mais recente primeiro)
        notas = [
            {"id": 2, "created_by": 12345, "created_at": agora,
             "text": "Lia, não é assim — o correto é X"},
            {"id": 1, "created_by": 0, "created_at": agora - 60,
             "text": "Vou reconferir a agenda..."},
        ]
        r = detectar_correcao_humana(999, self._mock_kommo(notas))
        assert r is not None
        assert r["padrao_explicito"] is True
        assert "não é assim" in r["correcao_humana"].lower()

    def test_par_fora_janela_ignora(self):
        agora = time.time()
        # 2 horas de gap = fora da janela 15min
        notas = [
            {"id": 2, "created_by": 12345, "created_at": agora,
             "text": "Lia, não é assim"},
            {"id": 1, "created_by": 0, "created_at": agora - 7200,
             "text": "Resposta velha da Lia"},
        ]
        r = detectar_correcao_humana(999, self._mock_kommo(notas))
        assert r is None

    def test_humano_longo_sem_padrao_captura(self):
        # Sinal "humano assumiu" — resposta longa sem padrão explícito
        agora = time.time()
        notas = [
            {"id": 2, "created_by": 12345, "created_at": agora,
             "text": "Boa tarde! Vou te passar os horários certos. "
                     "Terça 15h e quinta 10h com Dra. Karla em Águas Claras."},
            {"id": 1, "created_by": 0, "created_at": agora - 120,
             "text": "Vou consultar a agenda"},
        ]
        r = detectar_correcao_humana(999, self._mock_kommo(notas))
        assert r is not None
        assert r["padrao_explicito"] is False

    def test_lista_vazia_retorna_none(self):
        assert detectar_correcao_humana(999, self._mock_kommo([])) is None

    def test_toggle_off_retorna_none(self, monkeypatch):
        monkeypatch.setenv("LEARNING_LOOP_ATIVADO", "0")
        agora = time.time()
        notas = [
            {"id": 2, "created_by": 12345, "created_at": agora,
             "text": "Lia, não é assim"},
            {"id": 1, "created_by": 0, "created_at": agora - 60,
             "text": "..."},
        ]
        assert detectar_correcao_humana(999, self._mock_kommo(notas)) is None


# ═══════════════════════════════════════════════════════════════════════
# PEÇA 2 — Auto-append no CLAUDE.md
# ═══════════════════════════════════════════════════════════════════════

@pytest.fixture
def claude_md_temp(tmp_path):
    arq = tmp_path / "CLAUDE.md"
    arq.write_text(
        "# CLAUDE.md — teste\n\n"
        "## 0. ÚLTIMAS 5 LIÇÕES DURAS — LER PRIMEIRO (rolling log)\n\n"
        "### 0. (10/07/2026) Bug C-100 — teste velho\n\n"
        "corpo do bug antigo\n",
        encoding="utf-8",
    )
    return arq


class TestGerarEntrada:
    def test_gera_entrada_valida(self):
        correcao = {
            "resposta_lia": "Vou consultar a agenda",
            "correcao_humana": "Lia, não é assim. Ofereça direto.",
            "lead_id": 12345,
            "padrao_explicito": True,
        }
        entrada = gerar_entrada_bug_auto(correcao, bug_id="C-AUTO-042")
        assert "C-AUTO-042" in entrada
        assert "12345" in entrada
        assert "Vou consultar a agenda" in entrada
        assert "PADRÃO EXPLÍCITO" in entrada


class TestProximoBugAutoId:
    def test_arquivo_sem_bug_auto(self, tmp_path):
        arq = tmp_path / "CLAUDE.md"
        arq.write_text("# vazio\n", encoding="utf-8")
        assert _proximo_bug_auto_id(arq) == "C-AUTO-001"

    def test_incrementa_ultimo(self, tmp_path):
        arq = tmp_path / "CLAUDE.md"
        arq.write_text(
            "C-AUTO-005 primeiro\nC-AUTO-012 outro\nC-AUTO-003 mais um\n",
            encoding="utf-8",
        )
        assert _proximo_bug_auto_id(arq) == "C-AUTO-013"


class TestAppendCLAUDEMD:
    def test_append_no_topo_da_secao_0(self, claude_md_temp):
        entrada = "### 0. (15/07) Bug C-AUTO-001 — teste"
        ok = append_bug_no_claude_md(entrada, claude_md_temp)
        assert ok is True
        texto = claude_md_temp.read_text(encoding="utf-8")
        # Nova entrada deve vir ANTES do bug antigo
        pos_novo = texto.find("C-AUTO-001")
        pos_velho = texto.find("C-100")
        assert pos_novo != -1 and pos_velho != -1
        assert pos_novo < pos_velho

    def test_arquivo_inexistente_retorna_false(self, tmp_path):
        arq = tmp_path / "nao_existe.md"
        assert append_bug_no_claude_md("qualquer", arq) is False


# ═══════════════════════════════════════════════════════════════════════
# PEÇA 3 — Re-index em tempo real
# ═══════════════════════════════════════════════════════════════════════

class TestReindexSeMudou:
    def test_arquivo_inexistente_retorna_false(self, tmp_path):
        assert re_indexar_se_mudou(tmp_path / "nao_existe.md") is False

    def test_primeira_call_detecta_mudanca(self, claude_md_temp):
        # Reset estado global
        from voice_agent import learning_loop
        learning_loop._ULTIMO_MTIME_CLAUDE_MD["mtime"] = 0.0
        r = re_indexar_se_mudou(claude_md_temp)
        assert r is True

    def test_segunda_call_sem_mudanca_retorna_false(self, claude_md_temp):
        from voice_agent import learning_loop
        learning_loop._ULTIMO_MTIME_CLAUDE_MD["mtime"] = 0.0
        re_indexar_se_mudou(claude_md_temp)
        # Segunda call sem modificar arquivo
        r = re_indexar_se_mudou(claude_md_temp)
        assert r is False

    def test_apos_modificar_detecta(self, claude_md_temp):
        from voice_agent import learning_loop
        learning_loop._ULTIMO_MTIME_CLAUDE_MD["mtime"] = 0.0
        re_indexar_se_mudou(claude_md_temp)
        time.sleep(0.05)
        # Modifica arquivo
        claude_md_temp.write_text("novo conteúdo", encoding="utf-8")
        r = re_indexar_se_mudou(claude_md_temp)
        assert r is True


# ═══════════════════════════════════════════════════════════════════════
# ORQUESTRADOR — end-to-end
# ═══════════════════════════════════════════════════════════════════════

class TestProcessarLead:
    def _mock_kommo(self, notas):
        m = MagicMock()
        m.get_lead_notes = MagicMock(return_value=notas)
        return m

    def test_lead_sem_correcao_retorna_nao_detectou(self):
        m = self._mock_kommo([])
        r = processar_lead(999, m)
        assert r["detectou"] is False
        assert r["appendou"] is False

    def test_lead_com_correcao_completo(self, tmp_path, monkeypatch):
        # Redireciona CLAUDE.md pra temp
        from voice_agent import learning_loop
        arq = tmp_path / "CLAUDE.md"
        arq.write_text(
            "## 0. ÚLTIMAS 5 LIÇÕES DURAS — LER PRIMEIRO (rolling log)\n\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(learning_loop, "ARQUIVO_CLAUDE_MD", arq)

        agora = time.time()
        notas = [
            {"id": 2, "created_by": 12345, "created_at": agora,
             "text": "Lia, não é assim, o correto é X"},
            {"id": 1, "created_by": 0, "created_at": agora - 60,
             "text": "Resposta problemática"},
        ]
        r = processar_lead(999, self._mock_kommo(notas))
        assert r["detectou"] is True
        assert r["appendou"] is True
        assert r["bug_id"].startswith("C-AUTO-")
        # Arquivo tem a entrada
        assert r["bug_id"] in arq.read_text()

    def test_dedup_pula_segunda_chamada(self, tmp_path, monkeypatch):
        from voice_agent import learning_loop
        arq = tmp_path / "CLAUDE.md"
        arq.write_text(
            "## 0. ÚLTIMAS 5 LIÇÕES DURAS — LER PRIMEIRO (rolling log)\n\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(learning_loop, "ARQUIVO_CLAUDE_MD", arq)

        agora = time.time()
        notas = [
            {"id": 2, "created_by": 12345, "created_at": agora,
             "text": "Lia, não é assim"},
            {"id": 1, "created_by": 0, "created_at": agora - 60,
             "text": "Erro"},
        ]

        # Mock Redis com estado
        redis_mock = MagicMock()
        _state = {"visto": False}

        def get_side(k):
            return "1" if _state["visto"] else None

        def setex_side(k, ttl, v):
            _state["visto"] = True

        redis_mock.get = MagicMock(side_effect=get_side)
        redis_mock.setex = MagicMock(side_effect=setex_side)

        r1 = processar_lead(999, self._mock_kommo(notas), dedup_redis=redis_mock)
        r2 = processar_lead(999, self._mock_kommo(notas), dedup_redis=redis_mock)

        assert r1["dedup_pulou"] is False
        assert r2["dedup_pulou"] is True

    def test_toggle_off_retorna_erro(self, monkeypatch):
        monkeypatch.setenv("LEARNING_LOOP_ATIVADO", "0")
        m = self._mock_kommo([])
        r = processar_lead(999, m)
        assert r.get("erro") == "toggle_off"
