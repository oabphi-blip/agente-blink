"""Pytest blindando regra: nome+sobrenome do médico em TODOS os KB.

Origem: Fábio 16/06/2026 — toda menção a médico no prompt agente deve
incluir nome E sobrenome. Substituições aplicadas em 26 arquivos KB
(106 ocorrências). Esse pytest garante que nenhuma edição futura volte
a introduzir "Dra. Karla" / "Dr. Fabrício" sem sobrenome.

Regra:
- 'Dra. Karla' → permitido SÓ se seguido de 'Delalíbera' / 'Delalibera'
- 'Dr. Fabrício' / 'Dr. Fabricio' → permitido SÓ se seguido de 'Freitas'

Exceções aceitas (NÃO disparam falha):
- 'Karla 30min' / 'Fabrício 40min' — contexto técnico interno (sem Dr/Dra)
- 'Dra. Kátia' — outra médica, fora desta regra
- 'KARLA DELALÍBERA' em UPPERCASE em headings
"""
import os
import re
import pathlib

import pytest

KB_DIR = pathlib.Path(__file__).resolve().parent.parent / "voice_agent" / "knowledge_base"

# Permite "Dra. Karla Delalíbera" / "Dra. Karla Delalibera" — bloqueia o resto
RGX_KARLA_VIOLADO = re.compile(r"\bDra\.\s+Karla\b(?!\s+Delal)")

# Permite "Dr. Fabrício Freitas" / "Dr. Fabricio Freitas" — bloqueia o resto
RGX_FAB_VIOLADO = re.compile(r"\bDr\.\s+Fabr[ií]cio\b(?!\s+Freitas)")


def _coletar_kb_md() -> list[pathlib.Path]:
    return sorted(KB_DIR.glob("*.md"))


class TestNomeCompletoMedicosKB:
    """Validações estruturais — rodam em cada arquivo .md do KB."""

    def test_kb_dir_existe(self):
        assert KB_DIR.exists(), f"KB dir não encontrado: {KB_DIR}"

    def test_pelo_menos_30_kb_files(self):
        # Sanidade — KB tem muitos artigos
        files = _coletar_kb_md()
        assert len(files) >= 30, (
            f"Esperado pelo menos 30 artigos KB, encontrado {len(files)}"
        )

    def _linha_eh_anti_exemplo(self, linha: str) -> bool:
        """True se a linha é anti-exemplo (regra do que NÃO fazer).

        Anti-exemplos contém marcador de proibição: ❌, "PROIBIDO", "NÃO",
        "incompleto", "informal demais", aspas de quote ao redor, "abreviado".
        Essas linhas existem PRA mostrar o errado — não são violação.
        """
        marcadores = ("❌", "Nunca ", "nunca ", "(incompleto)", "(informal", "abreviado")
        return any(m in linha for m in marcadores)

    def test_zero_dra_karla_sem_sobrenome_em_kb(self):
        """REGRA P0: nenhum artigo KB pode ter 'Dra. Karla' sem 'Delalíbera'.

        Ignora anti-exemplos (linhas com ❌, 'nunca', '(incompleto)', etc).
        """
        violacoes = []
        for fpath in _coletar_kb_md():
            lines = fpath.read_text(encoding="utf-8").splitlines()
            for i, line in enumerate(lines, start=1):
                if self._linha_eh_anti_exemplo(line):
                    continue
                if RGX_KARLA_VIOLADO.search(line):
                    violacoes.append(f"{fpath.name}:{i}  {line.strip()[:80]!r}")
        assert not violacoes, (
            "Encontradas referências a 'Dra. Karla' SEM sobrenome:\n"
            + "\n".join(violacoes)
        )

    def test_zero_dr_fabricio_sem_sobrenome_em_kb(self):
        """REGRA P0: nenhum artigo KB pode ter 'Dr. Fabrício' sem 'Freitas'.

        Ignora anti-exemplos (linhas com ❌, 'nunca', '(incompleto)', etc).
        """
        violacoes = []
        for fpath in _coletar_kb_md():
            lines = fpath.read_text(encoding="utf-8").splitlines()
            for i, line in enumerate(lines, start=1):
                if self._linha_eh_anti_exemplo(line):
                    continue
                if RGX_FAB_VIOLADO.search(line):
                    violacoes.append(f"{fpath.name}:{i}  {line.strip()[:80]!r}")
        assert not violacoes, (
            "Encontradas referências a 'Dr. Fabrício' SEM sobrenome:\n"
            + "\n".join(violacoes)
        )

    def test_master_instruction_tem_regra_explicita(self):
        """0AA.5 deve conter a regra IMPERATIVA do nome+sobrenome."""
        master = KB_DIR / "_MASTER_INSTRUCTION.md"
        content = master.read_text(encoding="utf-8")
        # Marker mínimo da regra
        assert "NOME + SOBRENOME SEMPRE" in content, (
            "Regra 0AA.5 imperativa ausente em _MASTER_INSTRUCTION.md"
        )
        assert "Dra. Karla Delalíbera" in content
        assert "Dr. Fabrício Freitas" in content

    def test_master_instruction_versao_atualizada(self):
        """Bump VERSAO_PROMPT força re-cache Anthropic."""
        master = KB_DIR / "_MASTER_INSTRUCTION.md"
        content = master.read_text(encoding="utf-8")
        # Versão tem que ser de 16/06 ou mais recente
        assert "VERSAO_PROMPT: 2026-06-16-nome-sobrenome" in content or \
               "VERSAO_PROMPT: 2026-06-1" in content, (
            "VERSAO_PROMPT desatualizada — bumpar pra forçar re-cache"
        )


class TestRegexFunciona:
    """Validação dos regex em si — pra não criarem falso positivo."""

    def test_karla_com_sobrenome_passa(self):
        assert not RGX_KARLA_VIOLADO.search("Dra. Karla Delalíbera é...")
        assert not RGX_KARLA_VIOLADO.search("Dra. Karla Delalibera (sem acento)")

    def test_karla_sem_sobrenome_falha(self):
        assert RGX_KARLA_VIOLADO.search("Dra. Karla atende...")
        assert RGX_KARLA_VIOLADO.search("com Dra. Karla, na Asa Norte")
        assert RGX_KARLA_VIOLADO.search("Dra. Karla.")

    def test_karla_sozinha_sem_dra_nao_dispara(self):
        # 'Karla' sem 'Dra.' é contexto técnico (ex: 'Karla 30min')
        assert not RGX_KARLA_VIOLADO.search("Karla atende 30min por slot")

    def test_fabricio_com_sobrenome_passa(self):
        assert not RGX_FAB_VIOLADO.search("Dr. Fabrício Freitas é cirurgião")
        assert not RGX_FAB_VIOLADO.search("Dr. Fabricio Freitas (sem acento)")

    def test_fabricio_sem_sobrenome_falha(self):
        assert RGX_FAB_VIOLADO.search("Dr. Fabrício atende catarata")
        assert RGX_FAB_VIOLADO.search("Dr. Fabricio na Asa Norte")
        assert RGX_FAB_VIOLADO.search("Dr. Fabrício.")

    def test_outras_dras_nao_disparam(self):
        # Dra. Kátia ou Dra. Maria — fora desta regra
        assert not RGX_KARLA_VIOLADO.search("Dra. Kátia atende retina")
        assert not RGX_FAB_VIOLADO.search("Dr. Joao Silva")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
