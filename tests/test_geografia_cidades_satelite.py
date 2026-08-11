"""
Testa a regra de geografia — cidade satélite → unidade recomendada
(Regra adicionada 11/07/2026 conforme instrução Fábio).

Não roda contra a Lia em produção. Só valida que:
1. O bloco de referência está presente no `_MASTER_INSTRUCTION.md` (seção 8.3).
2. O bloco também está em `00_identidade_e_unidades.md` (pra RAG).
3. As cidades canônicas de cada lado estão listadas.
4. VERSAO_PROMPT foi bumpada.
"""

from __future__ import annotations

from pathlib import Path

import pytest

KB_DIR = (
    Path(__file__).resolve().parent.parent
    / "voice_agent"
    / "knowledge_base"
)

MASTER = KB_DIR / "_MASTER_INSTRUCTION.md"
IDENT = KB_DIR / "00_identidade_e_unidades.md"

CIDADES_AGUAS_CLARAS = [
    "Taguatinga",
    "Ceilândia",
    "Samambaia",
    "Vicente Pires",
    "Águas Lindas de Goiás",
    "Santo Antônio do Descoberto",
    "Brazlândia",
]

CIDADES_ASA_NORTE = [
    "Sobradinho",
    "Planaltina",
    "Lago Norte",
    "Varjão",
    "Paranoá",
]


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def test_master_tem_secao_geografia_cidades_satelite():
    txt = _read(MASTER)
    assert "8.3." in txt
    assert "CIDADE SATÉLITE" in txt.upper() or "CIDADE SATELITE" in txt.upper()


def test_master_lista_cidades_aguas_claras():
    txt = _read(MASTER)
    for cidade in CIDADES_AGUAS_CLARAS:
        assert cidade in txt, (
            f"Cidade '{cidade}' faltando na seção Águas Claras "
            f"do _MASTER_INSTRUCTION.md"
        )


def test_master_lista_cidades_asa_norte():
    txt = _read(MASTER)
    for cidade in CIDADES_ASA_NORTE:
        assert cidade in txt, (
            f"Cidade '{cidade}' faltando na seção Asa Norte "
            f"do _MASTER_INSTRUCTION.md"
        )


def test_master_menciona_script_canonico_recomendacao():
    txt = _read(MASTER)
    assert "fica mais perto" in txt.lower()


def test_master_versao_prompt_bumpada():
    txt = _read(MASTER)
    assert "2026-07-11-geografia-cidades-satelite-unidade" in txt


def test_identidade_tem_secao_proximidade():
    txt = _read(IDENT)
    assert "PROXIMIDADE" in txt.upper()


def test_identidade_lista_cidades_aguas_claras():
    txt = _read(IDENT)
    for cidade in CIDADES_AGUAS_CLARAS:
        assert cidade in txt, (
            f"Cidade '{cidade}' faltando na seção Águas Claras "
            f"do 00_identidade_e_unidades.md"
        )


def test_identidade_lista_cidades_asa_norte():
    txt = _read(IDENT)
    for cidade in CIDADES_ASA_NORTE:
        assert cidade in txt, (
            f"Cidade '{cidade}' faltando na seção Asa Norte "
            f"do 00_identidade_e_unidades.md"
        )


@pytest.mark.parametrize(
    "cidade,unidade",
    [
        ("Taguatinga", "Águas Claras"),
        ("Ceilândia", "Águas Claras"),
        ("Samambaia", "Águas Claras"),
        ("Vicente Pires", "Águas Claras"),
        ("Águas Lindas de Goiás", "Águas Claras"),
        ("Santo Antônio do Descoberto", "Águas Claras"),
        ("Brazlândia", "Águas Claras"),
        ("Sobradinho", "Asa Norte"),
        ("Planaltina", "Asa Norte"),
        ("Lago Norte", "Asa Norte"),
        ("Varjão", "Asa Norte"),
        ("Paranoá", "Asa Norte"),
    ],
)
def test_master_associa_cidade_a_unidade_correta(cidade: str, unidade: str):
    """
    Sanity: a cidade e a unidade correspondente aparecem próximas no texto
    (dentro de 800 chars uma da outra em qualquer direção). Não é um
    parser semântico, só protege contra swap acidental.
    """
    txt = _read(MASTER)
    idx_cidade = txt.find(cidade)
    assert idx_cidade >= 0, f"Cidade '{cidade}' não encontrada"
    janela = txt[max(0, idx_cidade - 800): idx_cidade + 800]
    assert unidade in janela, (
        f"Cidade '{cidade}' e unidade '{unidade}' não estão no mesmo "
        f"bloco — possível swap eixo oeste × eixo norte"
    )


def test_regra_cidades_nao_listadas_pergunta_sem_chutar():
    txt = _read(MASTER)
    # Frase-chave que instrui a NÃO chutar cidades não mapeadas
    assert "não chuta" in txt.lower() or "não chutar" in txt.lower()
