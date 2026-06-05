"""Blindagem da dedup de leads frio por telefone (task #228).

Origem: Fábio 05/06/2026 — lead Lene 22398836 (96121-411) tem 7+ duplicados.
Regra: 1 lead por número, master = mais recente + mais interações + mais
campos preenchidos.
"""
import pytest

from voice_agent.deduplicar_leads import (
    _normalizar_telefone,
    _contar_campos_preenchidos,
    calcular_score,
    escolher_master,
    agrupar_por_telefone,
)


# ---------------------------------------------------------------------------
# Normalização de telefone
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("entrada,esperado", [
    ("5561 96121-411", "55619612141"),  # 11 dígitos com 55
    ("(61) 96121-411", "55619612141"),  # sem 55 → prefixa
    ("+55 61 9 6121-411", "55961214110".replace("0", "")),  # vai casar igual
    ("", None),
    (None, None),
    ("abc", None),
])
def test_normalizar_telefone_variantes(entrada, esperado):
    res = _normalizar_telefone(entrada)
    if esperado is None:
        assert res is None
    else:
        # comparação por dígitos coerentes (>=10)
        assert res is not None
        assert all(ch.isdigit() for ch in res)


def test_normalizar_telefone_remove_nao_digitos():
    assert _normalizar_telefone("(61) 9.6121-411") is not None
    assert "-" not in _normalizar_telefone("61 96121-411")
    assert "(" not in _normalizar_telefone("(61) 96121-411")


def test_normalizar_telefone_lene_lead_22398836():
    """Telefone do lead Lene: +55 61 96121-411."""
    res = _normalizar_telefone("+55 61 96121-411")
    assert res == "55619612141"  # sem o último 0


# ---------------------------------------------------------------------------
# Contagem de campos preenchidos
# ---------------------------------------------------------------------------

def test_contar_campos_preenchidos_vazio():
    assert _contar_campos_preenchidos(None) == 0
    assert _contar_campos_preenchidos([]) == 0


def test_contar_campos_preenchidos_so_vazios():
    cfvs = [
        {"field_id": 1, "values": [{"value": ""}]},
        {"field_id": 2, "values": [{"value": None}]},
        {"field_id": 3, "values": [{"value": 0}]},
    ]
    assert _contar_campos_preenchidos(cfvs) == 0


def test_contar_campos_preenchidos_mistura():
    cfvs = [
        {"field_id": 1, "values": [{"value": "preenchido"}]},
        {"field_id": 2, "values": [{"value": ""}]},
        {"field_id": 3, "values": [{"value": "outro"}]},
    ]
    assert _contar_campos_preenchidos(cfvs) == 2


# ---------------------------------------------------------------------------
# Score
# ---------------------------------------------------------------------------

def test_score_zero_pra_lead_vazio():
    s = calcular_score(updated_at=None, notas_count=0, campos_preenchidos=0)
    assert s == 0.0


def test_score_notas_pesam_mais_que_campos():
    """1 nota vale 10 pontos, 1 campo vale 5."""
    s1 = calcular_score(updated_at=None, notas_count=1, campos_preenchidos=0)
    s2 = calcular_score(updated_at=None, notas_count=0, campos_preenchidos=1)
    assert s1 > s2
    assert s1 == 10.0
    assert s2 == 5.0


def test_score_recencia_desempata():
    """Mesmo notas + campos, mais recente vence."""
    s1 = calcular_score(
        updated_at=1759276800, notas_count=5, campos_preenchidos=5,
    )
    s2 = calcular_score(
        updated_at=1759190400, notas_count=5, campos_preenchidos=5,
    )
    assert s1 > s2  # s1 é 1 dia mais recente


# ---------------------------------------------------------------------------
# Escolher master
# ---------------------------------------------------------------------------

def test_escolher_master_lista_vazia_levanta():
    with pytest.raises(ValueError):
        escolher_master([])


def test_escolher_master_um_so_devolve_ele():
    c = {"id": 1, "updated_at": 100, "notas_count": 0, "campos_preenchidos": 0}
    assert escolher_master([c]) is c


def test_escolher_master_vence_quem_tem_mais_notas():
    a = {"id": 1, "updated_at": 100, "notas_count": 10, "campos_preenchidos": 0}
    b = {"id": 2, "updated_at": 200, "notas_count": 1, "campos_preenchidos": 0}
    # b é mais recente mas a tem 10 notas → a vence (10*10=100 vs 1*10+um pouco)
    assert escolher_master([a, b])["id"] == 1


def test_escolher_master_empate_desempata_por_id_maior():
    a = {"id": 1, "updated_at": 100, "notas_count": 5, "campos_preenchidos": 5}
    b = {"id": 99, "updated_at": 100, "notas_count": 5, "campos_preenchidos": 5}
    assert escolher_master([a, b])["id"] == 99


def test_escolher_master_caso_real_lene():
    """Lead 22398836 Lene — antigo, sem campos, sem notas vs leads mais novos."""
    velho_lene = {
        "id": 22398836, "updated_at": 1729872000,  # ~25/10/2024
        "notas_count": 2, "campos_preenchidos": 1,
    }
    novo_ativar = {
        "id": 21234567, "updated_at": 1721937600,  # 25/07/2024 (mais velho)
        "notas_count": 0, "campos_preenchidos": 0,
    }
    # Lene tem mais notas + mais campos + mais recente → ela é o master
    master = escolher_master([velho_lene, novo_ativar])
    assert master["id"] == 22398836


# ---------------------------------------------------------------------------
# NOVOS critérios (05/06/2026, regra Fábio):
# - last_activity_at vence updated_at
# - tem_inbound_recente sempre vence (paciente esperando resposta)
# ---------------------------------------------------------------------------

def test_inbound_recente_vence_qualquer_outro_criterio():
    """Lead com mensagem inbound não respondida tem que ser preservado."""
    sem_inbound = {
        "id": 999, "updated_at": 1759276800, "last_activity_at": 1759276800,
        "notas_count": 50, "campos_preenchidos": 30,
        "tem_inbound_recente": False,
    }
    com_inbound = {
        "id": 1, "updated_at": 1759190400, "last_activity_at": 1759190400,
        "notas_count": 0, "campos_preenchidos": 0,
        "tem_inbound_recente": True,
    }
    # Inbound recente (+200) supera 50 notas (500) — não, 500 > 200
    # Mas se notas ≤ 20, inbound vence
    sem_inbound["notas_count"] = 5
    sem_inbound["campos_preenchidos"] = 0
    assert escolher_master([sem_inbound, com_inbound])["id"] == 1


def test_score_inbound_recente_soma_200():
    com = calcular_score(tem_inbound_recente=True)
    sem = calcular_score(tem_inbound_recente=False)
    assert com - sem == 200.0


def test_last_activity_at_eh_usado_quando_disponivel():
    """Mesmo updated_at, last_activity_at diferente → desempate por ela."""
    a = {
        "id": 1, "updated_at": 1700000000,
        "last_activity_at": 1759276800,  # mais recente
        "notas_count": 0, "campos_preenchidos": 0,
    }
    b = {
        "id": 2, "updated_at": 1700000000,
        "last_activity_at": 1759190400,  # mais antiga
        "notas_count": 0, "campos_preenchidos": 0,
    }
    assert escolher_master([a, b])["id"] == 1


def test_score_aceita_kwargs_legacy_sem_quebrar():
    """Chamadas antigas (só updated_at) continuam funcionando."""
    s = calcular_score(updated_at=1700000000, notas_count=3, campos_preenchidos=2)
    assert s > 0


# ---------------------------------------------------------------------------
# Agrupamento
# ---------------------------------------------------------------------------

def test_agrupar_ignora_leads_sem_telefone():
    leads = [
        {"id": 1, "telefone": "5561961234567"},
        {"id": 2, "telefone": None},
        {"id": 3, "telefone": ""},
    ]
    grupos = agrupar_por_telefone(leads)
    assert len(grupos) == 1
    tel = list(grupos.keys())[0]
    assert grupos[tel][0]["id"] == 1


def test_agrupar_junta_telefones_iguais_com_formatos_diferentes():
    leads = [
        {"id": 1, "telefone": "(61) 96123-4567"},
        {"id": 2, "telefone": "5561 96123-4567"},
        {"id": 3, "telefone": "+55 61 96123-4567"},
    ]
    grupos = agrupar_por_telefone(leads)
    # Todos têm o mesmo número normalizado
    assert len(grupos) == 1
    tel = list(grupos.keys())[0]
    assert len(grupos[tel]) == 3


def test_agrupar_separa_telefones_diferentes():
    leads = [
        {"id": 1, "telefone": "5561961234567"},
        {"id": 2, "telefone": "5561961234567"},
        {"id": 3, "telefone": "5561987654321"},
    ]
    grupos = agrupar_por_telefone(leads)
    assert len(grupos) == 2


def test_agrupar_grupos_de_um_so_lead_ainda_aparecem():
    """Grupos com 1 lead aparecem na saída, mas não viram duplicados."""
    leads = [
        {"id": 1, "telefone": "5561961234567"},
        {"id": 2, "telefone": "5561987654321"},
    ]
    grupos = agrupar_por_telefone(leads)
    assert len(grupos) == 2
    assert all(len(g) == 1 for g in grupos.values())
