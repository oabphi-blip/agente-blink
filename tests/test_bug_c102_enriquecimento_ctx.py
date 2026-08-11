"""
Bug C-102 (11/08/2026) — Layer 2: Derivação determinística de ctx.known

Verifica que enriquecer_known() transforma dados Kommo em fatos derivados
antes do LLM ser chamado, eliminando perguntas desnecessárias.

Cenários cobertos:
  A. data_nasc → idade (múltiplos formatos)
  B. idade < 18 → medico = Karla
  C. motivo → medico (Fabrício / Karla)
  D. Normalização de nome completo Kommo → forma canônica
  E. Guards — não sobrescreve valor existente, fail-safe
"""

import pytest
from unittest.mock import patch
from datetime import date, timedelta

from voice_agent.enriquecimento_ctx import (
    enriquecer_known,
    _calcular_idade,
    _normalizar_medico,
    _medico_por_motivo,
)


# ─── A. Cálculo de idade ─────────────────────────────────────────────────────

class TestCalcularIdade:

    def test_iso_string_10_anos(self):
        nasc = date.today().replace(year=date.today().year - 10)
        assert _calcular_idade(nasc.isoformat()) == 10

    def test_iso_datetime_kommo_format(self):
        """Formato que o add_date do Kommo grava: 'YYYY-MM-DDT00:00:00-03:00'."""
        nasc = date.today().replace(year=date.today().year - 7)
        val = f"{nasc.isoformat()}T00:00:00-03:00"
        assert _calcular_idade(val) == 7

    def test_unix_timestamp(self):
        from datetime import datetime
        import time
        nasc_dt = datetime(2015, 6, 15)
        ts = int(nasc_dt.timestamp())
        idade = _calcular_idade(ts)
        assert idade is not None
        assert 9 <= idade <= 12  # faixa razoável

    def test_unix_timestamp_str(self):
        from datetime import datetime
        nasc_dt = datetime(2018, 1, 1)
        ts = str(int(nasc_dt.timestamp()))
        idade = _calcular_idade(ts)
        assert idade is not None
        assert 6 <= idade <= 9

    def test_menor_de_18(self):
        nasc = date.today().replace(year=date.today().year - 3)
        assert _calcular_idade(nasc.isoformat()) == 3

    def test_adulto_30_anos(self):
        nasc = date.today().replace(year=date.today().year - 30)
        assert _calcular_idade(nasc.isoformat()) == 30

    def test_valor_none_retorna_none(self):
        assert _calcular_idade(None) is None

    def test_valor_vazio_retorna_none(self):
        assert _calcular_idade("") is None

    def test_string_invalida_retorna_none(self):
        assert _calcular_idade("não-é-uma-data") is None


# ─── B. Normalização de médico ───────────────────────────────────────────────

class TestNormalizarMedico:

    def test_dra_karla_delalibera(self):
        assert _normalizar_medico("Dra. Karla Delalibera") == "Karla"

    def test_dra_karla_delalibera_acento(self):
        assert _normalizar_medico("Dra. Karla Delalíbera") == "Karla"

    def test_dr_fabricio_freitas(self):
        assert _normalizar_medico("Dr. Fabrício Freitas") == "Fabrício"

    def test_dr_fabricio_sem_acento(self):
        assert _normalizar_medico("Dr. Fabricio Freitas") == "Fabrício"

    def test_dra_katia(self):
        assert _normalizar_medico("Dra. Kátia Delalibera") == "Kátia"

    def test_curto_preservado(self):
        """Nome já canônico (≤12 chars) não deve ser alterado."""
        assert _normalizar_medico("Karla") == "Karla"
        assert _normalizar_medico("Fabrício") == "Fabrício"

    def test_desconhecido_preservado(self):
        assert _normalizar_medico("Dr. Outro Nome") == "Dr. Outro Nome"


# ─── C. Motivo → médico ──────────────────────────────────────────────────────

class TestMedicoPorMotivo:

    def test_catarata_fabricio(self):
        assert _medico_por_motivo("catarata") == "Fabrício"

    def test_cornea_fabricio(self):
        assert _medico_por_motivo("córnea") == "Fabrício"

    def test_pterigio_fabricio(self):
        assert _medico_por_motivo("pterígio") == "Fabrício"

    def test_estrabismo_karla(self):
        assert _medico_por_motivo("estrabismo") == "Karla"

    def test_oftalmopediatria_karla(self):
        assert _medico_por_motivo("oftalmopediatria") == "Karla"

    def test_processamento_visual_karla(self):
        assert _medico_por_motivo("processamento visual") == "Karla"

    def test_rotina_adulto_sem_inferencia(self):
        """Rotina de óculos / check-up adulto → sem inferência → LLM decide."""
        assert _medico_por_motivo("rotina de óculos") == ""

    def test_vazio_retorna_vazio(self):
        assert _medico_por_motivo("") == ""


# ─── D. enriquecer_known — fluxo completo ────────────────────────────────────

def _ctx(known: dict) -> dict:
    return {"found": True, "lead_id": 99999, "name": "Teste", "known": known}


class TestEnriquecerKnown:

    def test_data_nasc_injeta_idade(self):
        nasc = date.today().replace(year=date.today().year - 5)
        ctx = _ctx({"data_nasc": nasc.isoformat()})
        enriquecer_known(ctx)
        assert ctx["known"]["idade"] == 5

    def test_data_nasc_menor_injeta_karla(self):
        nasc = date.today().replace(year=date.today().year - 8)
        ctx = _ctx({"data_nasc": nasc.isoformat()})
        enriquecer_known(ctx)
        assert ctx["known"]["medico"] == "Karla"

    def test_data_nasc_adulto_injeta_karla_default(self):
        """C-103 step 5: adulto sem motivo específico → Karla (rotina default).
        Atualizado de C-102 (não injetava) para C-103 (Karla default).
        """
        nasc = date.today().replace(year=date.today().year - 35)
        ctx = _ctx({"data_nasc": nasc.isoformat()})
        enriquecer_known(ctx)
        # C-103 step 5: adulto sem motivo Fabrício → Karla default
        assert ctx["known"].get("medico") == "Karla"

    def test_motivo_catarata_injeta_fabricio(self):
        ctx = _ctx({"motivo": "catarata"})
        enriquecer_known(ctx)
        assert ctx["known"]["medico"] == "Fabrício"

    def test_motivo_estrabismo_injeta_karla(self):
        ctx = _ctx({"motivo": "estrabismo"})
        enriquecer_known(ctx)
        assert ctx["known"]["medico"] == "Karla"

    def test_medico_existente_nao_sobrescrito(self):
        """Se médico já está preenchido, não deve ser alterado."""
        ctx = _ctx({"motivo": "catarata", "medico": "Karla"})
        enriquecer_known(ctx)
        # motivo diz Fabrício, mas medico já estava como Karla → preservar
        assert ctx["known"]["medico"] == "Karla"

    def test_normalizacao_nome_completo(self):
        ctx = _ctx({"medico": "Dra. Karla Delalíbera"})
        enriquecer_known(ctx)
        assert ctx["known"]["medico"] == "Karla"

    def test_normalizacao_fabricio_completo(self):
        ctx = _ctx({"medico": "Dr. Fabrício Freitas"})
        enriquecer_known(ctx)
        assert ctx["known"]["medico"] == "Fabrício"

    def test_medico_canonico_nao_alterado(self):
        """Forma canônica curta não deve ser "normalizada" (loop)."""
        ctx = _ctx({"medico": "Karla"})
        enriquecer_known(ctx)
        assert ctx["known"]["medico"] == "Karla"

    def test_known_none_nao_crasha(self):
        ctx = {"found": True, "known": None}
        result = enriquecer_known(ctx)
        assert result is not None

    def test_known_ausente_nao_crasha(self):
        ctx = {"found": True}
        result = enriquecer_known(ctx)
        assert result is not None

    def test_ctx_vazio_nao_crasha(self):
        result = enriquecer_known({})
        assert result == {}

    def test_idade_nao_sobrescrita_se_ja_existir(self):
        """Se idade já calculada por outro meio, não recalcular."""
        ctx = _ctx({"data_nasc": "2000-01-01", "idade": 5})
        enriquecer_known(ctx)
        # data_nasc daria ~25 anos, mas idade=5 já existia
        assert ctx["known"]["idade"] == 5

    def test_data_nasc_kommo_format(self):
        """Formato Kommo real: 'YYYY-MM-DDT00:00:00-03:00'."""
        nasc = date.today().replace(year=date.today().year - 12)
        val = f"{nasc.isoformat()}T00:00:00-03:00"
        ctx = _ctx({"data_nasc": val})
        enriquecer_known(ctx)
        assert ctx["known"]["idade"] == 12
        assert ctx["known"]["medico"] == "Karla"

    def test_medico_normalizado_antes_de_motivo(self):
        """Normalização ocorre no step 4, não interfere nos steps 2-3."""
        ctx = _ctx({"medico": "Dr. Fabrício Freitas", "motivo": "estrabismo"})
        enriquecer_known(ctx)
        # motivo diz Karla, mas medico já existe (Fabrício) → não sobrescrever
        # Normalização: "Dr. Fabrício Freitas" → "Fabrício"
        assert ctx["known"]["medico"] == "Fabrício"


# ─── E. Integração com pipeline.py ───────────────────────────────────────────

class TestEnriquecimentoEstaNoCodigoCerto:

    def test_enriquecimento_importavel(self):
        """Módulo deve ser importável sem erros."""
        from voice_agent.enriquecimento_ctx import enriquecer_known
        assert callable(enriquecer_known)

    def test_pipeline_chama_enriquecimento(self):
        """pipeline.py deve conter chamada ao enriquecer_known (C-102)."""
        import os
        pipeline_path = os.path.join(
            os.path.dirname(__file__), "..", "voice_agent", "pipeline.py"
        )
        with open(pipeline_path, encoding="utf-8") as f:
            content = f.read()
        assert "enriquecimento_ctx" in content, (
            "pipeline.py não importa enriquecimento_ctx — C-102 não está plugado"
        )
        assert "_enriquecer_c102" in content, (
            "pipeline.py não chama enriquecer_known — C-102 não está ativo"
        )

    def test_kommo_expoe_data_nasc(self):
        """kommo.py deve mapear FIELD_DATA_NASCIMENTO_PACIENTE_1 → 'data_nasc'."""
        import os
        kommo_path = os.path.join(
            os.path.dirname(__file__), "..", "voice_agent", "kommo.py"
        )
        with open(kommo_path, encoding="utf-8") as f:
            content = f.read()
        assert "data_nasc" in content, (
            "kommo.py não mapeia data_nasc — data de nascimento não chega ao ctx.known"
        )
        assert "FIELD_DATA_NASCIMENTO_PACIENTE_1" in content
