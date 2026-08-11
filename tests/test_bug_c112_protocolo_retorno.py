"""
Pytest — Bug C-112: Protocolo retorno pediátrico — bloquear oferta prematura.

Cobre:
  - 1.MÊS PRÓX CONSULTA no futuro → bloqueia com data programada
  - 1.MÊS PRÓX CONSULTA no passado → não bloqueia (pode agendar)
  - 1.DIA CONSULTA recente (< janela) → bloqueia com data esperada de retorno
  - 1.DIA CONSULTA antigo (> janela) → não bloqueia
  - Faixas etárias: bebê 0-2a (6m), criança 3-12a (12m), adulto 13+ (12m)
  - ctx=None → None (fail-open)
  - Toggle OFF → None
  - Parse: "Maio 2027", "05/2027", "2027-05", "maio/2027"
  - Posição na chain: depois de C-110, antes de urgência
  - Caso real: lead 21545155 Maria Alice (12a, Maio 2027)
  - enriquecimento_ctx step 17 injeta campos Kommo em known
"""
from __future__ import annotations

import pathlib
from datetime import date, timedelta


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ctx(
    prox_consulta_mes: str = "",
    dia_consulta: str = "",
    nome: str = "Ana",
    idade_anos: int | None = None,
    data_nasc: str = "",
    lead_id: int = 9901,
) -> dict:
    known: dict = {}
    if prox_consulta_mes:
        known["prox_consulta_mes"] = prox_consulta_mes
    if dia_consulta:
        known["dia_consulta"] = dia_consulta
    if nome:
        known["nome_paciente"] = nome
    if idade_anos is not None:
        known["idade_anos"] = idade_anos
    if data_nasc:
        known["data_nasc"] = data_nasc
    return {"lead_id": lead_id, "known": known}


def _ctx_kommo(
    prox_mes_value: str = "",
    dia_consulta_value: str = "",
    nome: str = "Ana",
) -> dict:
    """ctx com campos nos custom_fields_values (como o Kommo retorna)."""
    campos = []
    if prox_mes_value:
        campos.append({
            "field_name": "1.MÊS PRÓX CONSULTA",
            "values": [{"value": prox_mes_value}],
        })
    if dia_consulta_value:
        campos.append({
            "field_name": "1.DIA CONSULTA",
            "values": [{"value": dia_consulta_value}],
        })
    return {"lead_id": 9901, "known": {"nome_paciente": nome}, "custom_fields_values": campos}


def _bloquear(ctx):
    from voice_agent.protocolo_retorno import deve_bloquear_oferta_retorno
    return deve_bloquear_oferta_retorno(ctx)


def _mes_futuro(meses: int = 6) -> str:
    """Retorna string 'Mês AAAA' para daqui a N meses."""
    hoje = date.today()
    m = hoje.month + meses
    a = hoje.year + (m - 1) // 12
    m = ((m - 1) % 12) + 1
    meses_pt = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
                "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
    return f"{meses_pt[m - 1]} {a}"


def _mes_passado(meses: int = 2) -> str:
    """Retorna string 'Mês AAAA' de N meses atrás."""
    hoje = date.today()
    m = hoje.month - meses
    a = hoje.year
    while m <= 0:
        m += 12
        a -= 1
    meses_pt = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
                "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
    return f"{meses_pt[m - 1]} {a}"


def _data_recente_iso(dias: int = 30) -> str:
    """ISO de N dias atrás."""
    return (date.today() - timedelta(days=dias)).isoformat()


def _data_antiga_iso(dias: int = 400) -> str:
    """ISO de N dias atrás (além da janela)."""
    return (date.today() - timedelta(days=dias)).isoformat()


# ---------------------------------------------------------------------------
# 1. 1.MÊS PRÓX CONSULTA — futuro bloqueia, passado libera
# ---------------------------------------------------------------------------

class TestProxConsultaMes:
    def test_futuro_bloqueia(self):
        ctx = _ctx(prox_consulta_mes=_mes_futuro(6))
        result = _bloquear(ctx)
        assert result is not None
        assert "Dra. Karla" in result or "retorno" in result.lower()

    def test_passado_nao_bloqueia(self):
        ctx = _ctx(prox_consulta_mes=_mes_passado(2))
        result = _bloquear(ctx)
        assert result is None

    def test_futuro_menciona_mes_programado(self):
        ctx = _ctx(prox_consulta_mes="Maio 2027")
        result = _bloquear(ctx)
        assert result is not None
        assert "2027" in result or "Maio" in result

    def test_caso_real_maria_alice_21545155(self):
        """Lead 21545155 Maria Alice: 1.MÊS PRÓX CONSULTA = 'Maio 2027'."""
        ctx = _ctx(prox_consulta_mes="Maio 2027", nome="Maria Alice", lead_id=21545155)
        result = _bloquear(ctx)
        assert result is not None  # deve bloquear
        assert "2027" in result

    def test_nome_aparece_na_mensagem(self):
        ctx = _ctx(prox_consulta_mes=_mes_futuro(3), nome="Luísa")
        result = _bloquear(ctx)
        assert result is not None
        assert "Luísa" in result


# ---------------------------------------------------------------------------
# 2. Parse de formatos de data de próximo mês
# ---------------------------------------------------------------------------

class TestParseMesAno:
    def test_formato_nome_ano(self):
        from voice_agent.protocolo_retorno import _parse_mes_ano
        d = _parse_mes_ano("Maio 2027")
        assert d is not None
        assert d.month == 5 and d.year == 2027

    def test_formato_numerico_barra(self):
        from voice_agent.protocolo_retorno import _parse_mes_ano
        d = _parse_mes_ano("05/2027")
        assert d is not None
        assert d.month == 5 and d.year == 2027

    def test_formato_iso(self):
        from voice_agent.protocolo_retorno import _parse_mes_ano
        d = _parse_mes_ano("2027-05")
        assert d is not None
        assert d.month == 5 and d.year == 2027

    def test_formato_nome_barra(self):
        from voice_agent.protocolo_retorno import _parse_mes_ano
        d = _parse_mes_ano("maio/2027")
        assert d is not None
        assert d.month == 5 and d.year == 2027

    def test_formato_abrev(self):
        from voice_agent.protocolo_retorno import _parse_mes_ano
        d = _parse_mes_ano("jan 2028")
        assert d is not None
        assert d.month == 1 and d.year == 2028

    def test_texto_vazio_retorna_none(self):
        from voice_agent.protocolo_retorno import _parse_mes_ano
        assert _parse_mes_ano("") is None
        assert _parse_mes_ano(None) is None

    def test_sem_data_retorna_none(self):
        from voice_agent.protocolo_retorno import _parse_mes_ano
        assert _parse_mes_ano("sem informação") is None


# ---------------------------------------------------------------------------
# 3. 1.DIA CONSULTA — janela mínima por faixa etária
# ---------------------------------------------------------------------------

class TestDiaConsultaJanela:
    def test_bebe_0_2a_janela_6m_bloqueia(self):
        """Bebê com consulta há 30 dias → bloqueia (janela 6 meses)."""
        ctx = _ctx(dia_consulta=_data_recente_iso(30), idade_anos=1)
        result = _bloquear(ctx)
        assert result is not None

    def test_bebe_0_2a_janela_6m_libera_apos(self):
        """Bebê com consulta há 200 dias → libera (além dos 180 dias)."""
        ctx = _ctx(dia_consulta=_data_antiga_iso(200), idade_anos=1)
        result = _bloquear(ctx)
        assert result is None

    def test_crianca_3_12a_janela_12m_bloqueia(self):
        """Criança 8 anos com consulta há 3 meses → bloqueia."""
        ctx = _ctx(dia_consulta=_data_recente_iso(90), idade_anos=8)
        result = _bloquear(ctx)
        assert result is not None

    def test_crianca_3_12a_janela_12m_libera_apos(self):
        """Criança com consulta há 400 dias → libera."""
        ctx = _ctx(dia_consulta=_data_antiga_iso(400), idade_anos=8)
        result = _bloquear(ctx)
        assert result is None

    def test_adulto_13_mais_janela_12m_bloqueia(self):
        """Adulto com consulta há 6 meses → bloqueia."""
        ctx = _ctx(dia_consulta=_data_recente_iso(180), idade_anos=25)
        result = _bloquear(ctx)
        assert result is not None

    def test_adulto_13_mais_janela_12m_libera(self):
        """Adulto com consulta há 400 dias → libera."""
        ctx = _ctx(dia_consulta=_data_antiga_iso(400), idade_anos=25)
        result = _bloquear(ctx)
        assert result is None

    def test_consulta_futura_nao_bloqueia(self):
        """Data de consulta no futuro — não é 'última consulta', não deve bloquear."""
        data_futura = (date.today() + timedelta(days=30)).isoformat()
        ctx = _ctx(dia_consulta=data_futura, idade_anos=8)
        result = _bloquear(ctx)
        assert result is None

    def test_mensagem_menciona_data_esperada(self):
        """Mensagem deve incluir quando será o retorno esperado."""
        ctx = _ctx(dia_consulta=_data_recente_iso(30), idade_anos=5)
        result = _bloquear(ctx)
        assert result is not None
        # Deve ter alguma data (dia/mês/ano ou referência temporal)
        assert "/" in result or "mês" in result.lower() or "2026" in result or "2027" in result


# ---------------------------------------------------------------------------
# 4. Fail-open e edge cases
# ---------------------------------------------------------------------------

class TestFailOpen:
    def test_ctx_none_retorna_none(self):
        result = _bloquear(None)
        assert result is None

    def test_sem_campos_retorna_none(self):
        ctx = _ctx()  # known vazio
        result = _bloquear(ctx)
        assert result is None

    def test_toggle_off_retorna_none(self):
        from voice_agent import protocolo_retorno as mod
        original = mod._ATIVADO
        mod._ATIVADO = False
        try:
            ctx = _ctx(prox_consulta_mes="Maio 2027")
            result = mod.deve_bloquear_oferta_retorno(ctx)
            assert result is None
        finally:
            mod._ATIVADO = original

    def test_prox_mes_sem_ano_valido_nao_bloqueia(self):
        """String sem ano válido não deve bloquear."""
        ctx = _ctx(prox_consulta_mes="próximo mês")
        result = _bloquear(ctx)
        assert result is None


# ---------------------------------------------------------------------------
# 5. Extração de campos Kommo (via custom_fields_values)
# ---------------------------------------------------------------------------

class TestExtracaoKommo:
    def test_extrai_prox_mes_de_custom_fields(self):
        from voice_agent.protocolo_retorno import enriquecer_ctx_protocolo_retorno
        ctx = _ctx_kommo(prox_mes_value="Maio 2027")
        enriquecer_ctx_protocolo_retorno(ctx)
        assert ctx["known"].get("prox_consulta_mes") == "Maio 2027"

    def test_extrai_dia_consulta_de_custom_fields(self):
        from voice_agent.protocolo_retorno import enriquecer_ctx_protocolo_retorno
        ctx = _ctx_kommo(dia_consulta_value="2026-07-01")
        enriquecer_ctx_protocolo_retorno(ctx)
        assert ctx["known"].get("dia_consulta") == "2026-07-01"

    def test_nao_sobrescreve_se_ja_preenchido(self):
        from voice_agent.protocolo_retorno import enriquecer_ctx_protocolo_retorno
        ctx = _ctx_kommo(prox_mes_value="Agosto 2027")
        ctx["known"]["prox_consulta_mes"] = "Junho 2027"  # já preenchido
        enriquecer_ctx_protocolo_retorno(ctx)
        assert ctx["known"]["prox_consulta_mes"] == "Junho 2027"  # não sobrescreveu


# ---------------------------------------------------------------------------
# 6. Posição na chain (C-112 depois de C-110, antes de urgência)
# ---------------------------------------------------------------------------

class TestPosicaoNaChain:
    def test_c112_depois_de_c110_antes_urgencia(self):
        base = pathlib.Path(__file__).parent.parent
        conteudo = (base / "voice_agent/blindagens_deterministicas.py").read_text(encoding="utf-8")

        inicio = conteudo.find("def tentar_bypass_deterministico")
        assert inicio >= 0
        corpo = conteudo[inicio:]

        pos_c110 = corpo.find("C-110")
        pos_c112 = corpo.find("C-112")
        pos_urgencia = corpo.find("deve_orientar_urgencia(ctx")

        assert pos_c110 >= 0, "C-110 não encontrado"
        assert pos_c112 >= 0, "C-112 não encontrado"
        assert pos_urgencia >= 0, "deve_orientar_urgencia não encontrado"

        assert pos_c110 < pos_c112, "C-110 deve vir antes de C-112"
        assert pos_c112 < pos_urgencia, "C-112 deve vir antes de urgência"

    def test_step17_em_enriquecimento_ctx(self):
        base = pathlib.Path(__file__).parent.parent
        conteudo = (base / "voice_agent/enriquecimento_ctx.py").read_text(encoding="utf-8")
        assert "C-112-17" in conteudo, "Step 17 C-112 não encontrado em enriquecimento_ctx.py"
