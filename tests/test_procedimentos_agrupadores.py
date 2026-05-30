"""Pytest blindando os 4 agrupadores de procedimentos.

Conceito Blink 30/05/2026: cada agendamento usa UM dos 4 agrupadores
de exames pré-definidos baseado em (faixa etária, motivo). Não é mais
seleção manual exame por exame.

Cenários:
1. Adulto (≥3) + Rotina → AGRUPADOR_1 (9 exames completos)
2. Adulto (≥3) + Emergência → AGRUPADOR_2 (6 exames focais)
3. Criança (<3) + Rotina → AGRUPADOR_3 (6 exames sem ceratoscopia/cores)
4. Criança (<3) + Urgência → AGRUPADOR_4 (5 exames sem mapa retina)
5. Detecção de urgência por palavras-chave
6. Cálculo de idade a partir de data nascimento
"""
from __future__ import annotations

from datetime import date

import pytest

from voice_agent.procedimentos import (
    AGRUPADOR_ADULTO_ROTINA,
    AGRUPADOR_ADULTO_EMERGENCIA,
    AGRUPADOR_CRIANCA_ROTINA,
    AGRUPADOR_CRIANCA_URGENCIA,
    PROC_MAPEAMENTO_RETINA,
    PROC_CERATOSCOPIA,
    PROC_TESTE_CORES,
    PROC_MICROSCOPIA_ESPECULAR,
    PROC_RETINOGRAFIA_MONOCULAR,
    is_menor_de_3,
    is_urgencia,
    selecionar_agrupador,
)


class TestSelecaoAgrupador:

    def test_adulto_rotina_devolve_agrupador_1(self):
        nome, procs = selecionar_agrupador(
            perfil_kommo="Acima de 50 anos",
            motivo="consulta de rotina anual",
        )
        assert nome == "AGRUPADOR_1_ADULTO_ROTINA"
        assert procs == AGRUPADOR_ADULTO_ROTINA
        assert len(procs) == 9
        # Confirma que exames adultos avançados estão inclusos
        assert PROC_CERATOSCOPIA in procs
        assert PROC_TESTE_CORES in procs
        assert PROC_MICROSCOPIA_ESPECULAR in procs

    def test_adulto_urgencia_devolve_agrupador_2(self):
        nome, procs = selecionar_agrupador(
            perfil_kommo="Adulto de 19 a 49",
            motivo="dor forte no olho desde ontem, urgente",
        )
        assert nome == "AGRUPADOR_2_ADULTO_EMERGENCIA"
        assert procs == AGRUPADOR_ADULTO_EMERGENCIA
        assert len(procs) == 6
        # Mapeamento de retina e retinografia NÃO entram em emergência
        assert PROC_MAPEAMENTO_RETINA not in procs
        assert PROC_RETINOGRAFIA_MONOCULAR not in procs
        # Teste de cores também NÃO em emergência
        assert PROC_TESTE_CORES not in procs

    def test_crianca_rotina_devolve_agrupador_3(self):
        nome, procs = selecionar_agrupador(
            perfil_kommo="Bebê de 0 a 2 anos",
            motivo="primeira consulta de rotina",
        )
        assert nome == "AGRUPADOR_3_CRIANCA_ROTINA"
        assert procs == AGRUPADOR_CRIANCA_ROTINA
        assert len(procs) == 6
        # Mapeamento entra em rotina infantil
        assert PROC_MAPEAMENTO_RETINA in procs
        # Mas ceratoscopia/cores/microscopia NÃO entram em criança
        assert PROC_CERATOSCOPIA not in procs
        assert PROC_TESTE_CORES not in procs
        assert PROC_MICROSCOPIA_ESPECULAR not in procs

    def test_crianca_urgencia_devolve_agrupador_4(self):
        nome, procs = selecionar_agrupador(
            perfil_kommo="Bebê de 0 a 2 anos",
            motivo="bebê com olho vermelho e sangramento",
        )
        assert nome == "AGRUPADOR_4_CRIANCA_URGENCIA"
        assert procs == AGRUPADOR_CRIANCA_URGENCIA
        assert len(procs) == 5
        # Em urgência infantil mapeamento NÃO entra
        assert PROC_MAPEAMENTO_RETINA not in procs

    def test_motivo_vazio_assume_rotina(self):
        nome, _ = selecionar_agrupador(
            perfil_kommo="Acima de 50 anos", motivo=None,
        )
        assert nome == "AGRUPADOR_1_ADULTO_ROTINA"

    def test_perfil_vazio_assume_adulto(self):
        nome, _ = selecionar_agrupador(
            perfil_kommo=None, motivo="rotina",
        )
        assert nome == "AGRUPADOR_1_ADULTO_ROTINA"


class TestIdadeCalculada:

    def test_data_nascimento_menor_3_vira_crianca(self):
        # Bebê nascido há ~1 ano
        nome, _ = selecionar_agrupador(
            birth_date_iso="2025-05-30",
            motivo="rotina",
            hoje=date(2026, 5, 30),
        )
        assert nome == "AGRUPADOR_3_CRIANCA_ROTINA"

    def test_data_nascimento_maior_3_vira_adulto(self):
        # Criança com 5 anos
        nome, _ = selecionar_agrupador(
            birth_date_iso="2021-01-15",
            motivo="rotina",
            hoje=date(2026, 5, 30),
        )
        assert nome == "AGRUPADOR_1_ADULTO_ROTINA"

    def test_exatos_3_anos_e_adulto(self):
        # Criança que faz 3 anos hoje
        nome, _ = selecionar_agrupador(
            birth_date_iso="2023-05-30",
            motivo="rotina",
            hoje=date(2026, 5, 30),
        )
        assert nome == "AGRUPADOR_1_ADULTO_ROTINA"

    def test_data_invalida_cai_em_perfil_kommo(self):
        nome, _ = selecionar_agrupador(
            birth_date_iso="data-invalida",
            perfil_kommo="Bebê de 0 a 2 anos",
            motivo="rotina",
        )
        assert nome == "AGRUPADOR_3_CRIANCA_ROTINA"

    def test_data_prioriza_sobre_perfil_kommo(self):
        # Kommo diz adulto, mas birth date diz bebê — birth date ganha
        nome, _ = selecionar_agrupador(
            birth_date_iso="2025-01-01",
            perfil_kommo="Acima de 50 anos",  # campo desatualizado
            motivo="rotina",
            hoje=date(2026, 5, 30),
        )
        assert nome == "AGRUPADOR_3_CRIANCA_ROTINA"


class TestDeteccaoUrgencia:

    def test_palavras_chave_urgencia(self):
        for motivo in (
            "urgente",
            "consulta de emergência",
            "dor forte no olho",
            "perdi a visão de uma hora pra outra",
            "tem corpo estranho no olho",
            "sangramento ocular",
            "bebê com trauma após queda",
        ):
            assert is_urgencia(motivo) is True, f"falhou em: {motivo}"

    def test_palavras_neutras_assume_rotina(self):
        for motivo in (
            "consulta de rotina",
            "primeira consulta",
            "renovar receita",
            "vista cansada",
            None,
            "",
        ):
            assert is_urgencia(motivo) is False, f"falsa urgência em: {motivo}"


class TestIsMenorDe3:

    def test_kommo_bebe_e_menor_de_3(self):
        assert is_menor_de_3("Bebê de 0 a 2 anos") is True

    def test_kommo_crianca_3_a_12_e_maior_de_3(self):
        assert is_menor_de_3("Criança de 3 a 12 anos") is False

    def test_kommo_acima_de_50_e_maior_de_3(self):
        assert is_menor_de_3("Acima de 50 anos") is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
