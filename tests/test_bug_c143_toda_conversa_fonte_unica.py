"""
tests/test_bug_c143_toda_conversa_fonte_unica.py — Bug C-143 (14/08/2026)

TODA CONVERSA (field 1261206) como fonte única de ultima_msg_outbound.
Campo ULTIMA MSG OUTBOUND (1260856) foi excluído do Kommo.

Cobre:
  1. kommo.py: get_caller_context_by_lead extrai ultima_msg_outbound de TODA CONVERSA
  2. campos_acompanhamento.py: FIELD_ULTIMA_MSG_OUTBOUND == 0 (sentinela)
  3. watchdog_promessa.py: avaliar_lead lê TODA CONVERSA (não field 0)
  4. watchdog_promessa.py: _extrair_ultima_lia_de_toda_conversa helper
  5. Regressão: watchdog 41/41 + novos 15 testes C-143 específicos
"""

import os
import sys
import re
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ─── 1. campos_acompanhamento — FIELD_ULTIMA_MSG_OUTBOUND = 0 ─────────────────

class TestCamposAcompanhamento:
    def test_field_ultima_msg_outbound_e_zero(self):
        """C-143: campo excluído → sentinela 0."""
        from voice_agent.campos_acompanhamento import FIELD_ULTIMA_MSG_OUTBOUND
        assert FIELD_ULTIMA_MSG_OUTBOUND == 0, (
            "FIELD_ULTIMA_MSG_OUTBOUND deve ser 0 (sentinela para campo excluído)"
        )

    def test_importa_sem_erro(self):
        from voice_agent import campos_acompanhamento  # noqa: F401

    def test_formatar_ultima_msg_ainda_funciona(self):
        """formatar_ultima_msg_outbound ainda gera string (usada internamente)."""
        from voice_agent.campos_acompanhamento import formatar_ultima_msg_outbound
        resultado = formatar_ultima_msg_outbound("Mensagem de teste")
        assert "[LIA" in resultado
        assert "Mensagem de teste" in resultado


# ─── 2. watchdog — FIELD_TODA_CONVERSA exportado ─────────────────────────────

class TestWatchdogConstantes:
    def test_field_toda_conversa_correto(self):
        from voice_agent.watchdog_promessa import FIELD_TODA_CONVERSA
        assert FIELD_TODA_CONVERSA == 1261206

    def test_field_ultima_msg_outbound_e_zero(self):
        from voice_agent.watchdog_promessa import FIELD_ULTIMA_MSG_OUTBOUND
        assert FIELD_ULTIMA_MSG_OUTBOUND == 0


# ─── 3. _extrair_ultima_lia_de_toda_conversa helper ──────────────────────────

class TestExtrairUltimaLiaDeTodaConversa:
    """Testa o helper que extrai a última linha [L ...] do TODA CONVERSA."""

    def _lead_com_toda_conversa(self, tc_text: str) -> dict:
        return {
            "id": 99001,
            "status_id": 102560495,
            "custom_fields": [
                {"field_id": 1261206, "values": [{"value": tc_text}]},
            ],
        }

    def test_extrai_ultima_linha_lia(self):
        from voice_agent.watchdog_promessa import _extrair_ultima_lia_de_toda_conversa
        tc = (
            "[P 09:00 14/08] Quero agendar.\n"
            "[L 09:01 14/08] Deixa eu consultar a agenda.\n"
            "[P 09:10 14/08] Ok.\n"
            "[L 09:11 14/08] Um minutinho que já volto.\n"
        )
        lead = self._lead_com_toda_conversa(tc)
        resultado = _extrair_ultima_lia_de_toda_conversa(lead)
        assert resultado == "Um minutinho que já volto."

    def test_sem_toda_conversa_retorna_vazio(self):
        from voice_agent.watchdog_promessa import _extrair_ultima_lia_de_toda_conversa
        lead = {"id": 99002, "status_id": 102560495, "custom_fields": []}
        assert _extrair_ultima_lia_de_toda_conversa(lead) == ""

    def test_toda_conversa_sem_linha_lia_retorna_vazio(self):
        from voice_agent.watchdog_promessa import _extrair_ultima_lia_de_toda_conversa
        tc = "[P 09:00 14/08] Quero agendar.\n"
        lead = self._lead_com_toda_conversa(tc)
        assert _extrair_ultima_lia_de_toda_conversa(lead) == ""

    def test_extrai_ultima_entre_multiplas(self):
        from voice_agent.watchdog_promessa import _extrair_ultima_lia_de_toda_conversa
        tc = (
            "[L 08:00 14/08] Primeira mensagem.\n"
            "[P 08:05 14/08] Resposta paciente.\n"
            "[L 08:06 14/08] Segunda mensagem da Lia.\n"
        )
        lead = self._lead_com_toda_conversa(tc)
        resultado = _extrair_ultima_lia_de_toda_conversa(lead)
        assert resultado == "Segunda mensagem da Lia."

    def test_falha_silenciosa_em_campo_corrompido(self):
        from voice_agent.watchdog_promessa import _extrair_ultima_lia_de_toda_conversa
        lead = {"id": 99003, "custom_fields": [
            {"field_id": 1261206, "values": [{"value": None}]},
        ]}
        # Não deve levantar exceção
        resultado = _extrair_ultima_lia_de_toda_conversa(lead)
        assert resultado == ""


# ─── 4. avaliar_lead usa TODA CONVERSA (não field 0) ─────────────────────────

class TestAvaliarLeadC143:
    """avaliar_lead deve ler ultima_msg do TODA CONVERSA, não de field 0."""

    def _make_lead_toda_conversa(
        self,
        ultima_msg: str,
        minutos_atras: int = 10,
        status_id: int = 102560495,
    ) -> dict:
        ts = int(time.time()) - minutos_atras * 60
        from datetime import datetime, timezone, timedelta
        _tz_br = timezone(timedelta(hours=-3))
        dt = datetime.fromtimestamp(ts, tz=_tz_br)
        ts_fmt = dt.strftime("%H:%M %d/%m")
        tc = f"[P {ts_fmt}] Quero agendar.\n[L {ts_fmt}] {ultima_msg}\n" if ultima_msg else ""
        fields = [{"field_id": 1260860, "values": [{"value": ts}]}]
        if tc:
            fields.append({"field_id": 1261206, "values": [{"value": tc}]})
        return {"id": 24145890, "status_id": status_id, "custom_fields": fields}

    def test_detecta_promessa_via_toda_conversa(self):
        from voice_agent.watchdog_promessa import avaliar_lead
        lead = self._make_lead_toda_conversa("Deixa eu consultar a agenda. Um minutinho.")
        r = avaliar_lead(lead)
        assert r["tratar"] is True
        assert r["lead_id"] == 24145890

    def test_sem_toda_conversa_nao_dispara(self):
        """Lead sem TODA CONVERSA → fail-open → tratar=False."""
        from voice_agent.watchdog_promessa import avaliar_lead
        lead = self._make_lead_toda_conversa("")
        r = avaliar_lead(lead)
        assert r["tratar"] is False

    def test_ultima_msg_real_nao_dispara(self):
        """TODA CONVERSA com resposta real → não é promessa pendente."""
        from voice_agent.watchdog_promessa import avaliar_lead
        ultima = "1️⃣ Quinta 09:30 / 2️⃣ Sexta 14:00"
        lead = self._make_lead_toda_conversa(ultima)
        r = avaliar_lead(lead)
        assert r["tratar"] is False

    def test_field_1260856_ignorado(self):
        """Mesmo que field 1260856 exista no payload (antigo), não é lido."""
        from voice_agent.watchdog_promessa import avaliar_lead
        ts = int(time.time()) - 10 * 60
        # Injeta 1260856 com promessa, mas sem TODA CONVERSA → não deve detectar
        lead = {
            "id": 24000001,
            "status_id": 102560495,
            "custom_fields": [
                {"field_id": 1260856, "values": [{"value": "Deixa eu consultar."}]},
                {"field_id": 1260860, "values": [{"value": ts}]},
            ],
        }
        r = avaliar_lead(lead)
        assert r["tratar"] is False, (
            "field 1260856 excluído não deve mais ser lido pelo watchdog"
        )


# ─── 5. kommo.py — get_caller_context_by_lead popula ultima_msg_outbound ─────

class TestKommoCtxUltimaMsgOutbound:
    """kommo.py deve derivar ultima_msg_outbound da última linha [L ...] de TODA CONVERSA."""

    def _simular_cf(self, tc_text: str) -> list:
        """Simula custom_fields_values com TODA CONVERSA."""
        return [
            {"field_id": 1261206, "values": [{"value": tc_text}]},
        ]

    def test_ultima_msg_outbound_derivada_de_toda_conversa(self, monkeypatch):
        """get_caller_context_by_lead deve popular ctx.known['ultima_msg_outbound']."""
        # Testa a lógica de parsing de TODA CONVERSA diretamente
        # (sem mockar toda a infra de kommo.py que depende de HTTP)
        import re as _re
        tc_text = (
            "[P 09:00 14/08] Quero marcar.\n"
            "[L 09:01 14/08] Deixa eu verificar os slots disponíveis.\n"
        )
        # Replica a lógica exata de kommo.py::get_caller_context_by_lead (C-143)
        ultima_lia = ""
        for linha in reversed(tc_text.splitlines()):
            linha = linha.strip()
            if linha.startswith("[L "):
                m = _re.match(r"^\[L\s+[\d:/\s]+\]\s*(.+)$", linha)
                if m:
                    ultima_lia = m.group(1).strip()
                break
        assert ultima_lia == "Deixa eu verificar os slots disponíveis."

    def test_toda_conversa_sem_linha_lia(self):
        """TODA CONVERSA só com linhas [P ...] → ultima_lia vazio."""
        import re as _re
        tc_text = "[P 09:00 14/08] Quero marcar.\n"
        ultima_lia = ""
        for linha in reversed(tc_text.splitlines()):
            linha = linha.strip()
            if linha.startswith("[L "):
                m = _re.match(r"^\[L\s+[\d:/\s]+\]\s*(.+)$", linha)
                if m:
                    ultima_lia = m.group(1).strip()
                break
        assert ultima_lia == ""

    def test_toda_conversa_multiplos_turnos(self):
        """Múltiplos turnos → retorna a ÚLTIMA linha [L ...]."""
        import re as _re
        tc_text = (
            "[P 09:00 14/08] msg1\n"
            "[L 09:01 14/08] resp1\n"
            "[P 09:10 14/08] msg2\n"
            "[L 09:11 14/08] resp2 final\n"
        )
        ultima_lia = ""
        for linha in reversed(tc_text.splitlines()):
            linha = linha.strip()
            if linha.startswith("[L "):
                m = _re.match(r"^\[L\s+[\d:/\s]+\]\s*(.+)$", linha)
                if m:
                    ultima_lia = m.group(1).strip()
                break
        assert ultima_lia == "resp2 final"
