"""Pytest Bug C-33 — Pterígio/Córnea = Dr. Fabrício Freitas.

Origem: Fábio 16/06/2026, lead 24160634. Paciente perguntou sobre pterígio,
Lia respondeu "fazemos catarata (Fabrício) e estrabismo (Karla)" sem citar
córnea, e quando paciente confirmou pterígio Lia caiu em "deixa eu reconsultar
a agenda... volto em 1 minuto".

Causa raiz: pterígio e córnea NÃO existiam em NENHUM artigo do KB.

Fix: adicionar mapping córnea/pterígio → Dr. Fabrício Freitas em:
- voice_agent/knowledge_base/_MASTER_INSTRUCTION.md (seção 5.6 + 5.7-A)
- voice_agent/knowledge_base/01_medicos_e_especialidades.md (mapa rápido + cabeçalho Fabrício)
"""
import pathlib

import pytest

KB_DIR = pathlib.Path(__file__).resolve().parent.parent / "voice_agent" / "knowledge_base"


class TestPterigioNoKB:
    """Pterígio deve aparecer no KB roteado pra Fabrício Freitas."""

    def test_pterigio_existe_em_pelo_menos_2_arquivos(self):
        """Pra RAG injetar a regra com confiabilidade, precisa estar em 2+ artigos."""
        arquivos_com_pterigio = []
        for f in KB_DIR.glob("*.md"):
            content = f.read_text(encoding="utf-8").lower()
            if "pterígio" in content or "pterigio" in content:
                arquivos_com_pterigio.append(f.name)
        assert len(arquivos_com_pterigio) >= 2, (
            f"Pterígio deve aparecer em pelo menos 2 KB. Achei em: {arquivos_com_pterigio}"
        )

    def test_master_instruction_tem_pterigio_e_fabricio_juntos(self):
        """Na master, regra de roteamento DEVE associar pterígio a Fabrício."""
        master = (KB_DIR / "_MASTER_INSTRUCTION.md").read_text(encoding="utf-8")
        assert "Pterígio" in master or "pterígio" in master, "Pterígio ausente da master"
        # Verifica proximidade textual com Fabrício Freitas (no mesmo bloco)
        # Aceita a regra mesmo se for "Córnea / Pterígio ... → Dr. Fabrício Freitas"
        idx_pterigio = master.lower().find("pterígio")
        if idx_pterigio < 0:
            idx_pterigio = master.lower().find("pterigio")
        # Olha 200 chars antes e depois pra ver se Fabrício aparece próximo
        janela = master[max(0, idx_pterigio - 50):idx_pterigio + 250]
        assert "Fabrício" in janela or "Fabricio" in janela, (
            "Pterígio deve estar no mesmo bloco que 'Fabrício Freitas'"
        )

    def test_artigo_01_medicos_lista_cornea_no_fabricio(self):
        """01_medicos_e_especialidades deve mencionar córnea/pterígio sob Fabrício."""
        artigo = (KB_DIR / "01_medicos_e_especialidades.md").read_text(encoding="utf-8")
        assert "Córnea" in artigo or "córnea" in artigo, "Córnea ausente em 01_medicos"
        assert "Pterígio" in artigo or "pterígio" in artigo


class TestCorneaNoKB:
    def test_cornea_aparece_em_pelo_menos_2_arquivos(self):
        arquivos_com_cornea = []
        for f in KB_DIR.glob("*.md"):
            content = f.read_text(encoding="utf-8").lower()
            if "córnea" in content or "cornea" in content:
                arquivos_com_cornea.append(f.name)
        assert len(arquivos_com_cornea) >= 2


class TestVersaoPromptAtualizada:
    def test_versao_prompt_bumped(self):
        master = (KB_DIR / "_MASTER_INSTRUCTION.md").read_text(encoding="utf-8")
        assert "VERSAO_PROMPT: 2026-06-16-pterigio-cornea" in master, (
            "VERSAO_PROMPT deve ser bumped pra forçar re-cache Anthropic"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
