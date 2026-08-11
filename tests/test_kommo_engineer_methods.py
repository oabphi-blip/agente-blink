"""Pytest dos métodos novos do KommoClient pra Lia Engineer.

Cobre `list_recent_notes` e `search_leads_by_window` com mocks de httpx.
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

import pytest


def _client_minimo(monkeypatch):
    from voice_agent.kommo import KommoClient
    return KommoClient(subdomain="univeja", token="fake-token")


def _mock_httpx_get(resp_mock):
    """Helper que retorna um patch context p/ httpx.Client retornar resp_mock no .get()."""
    cm = MagicMock()
    inner = MagicMock()
    inner.get = MagicMock(return_value=resp_mock)
    cm.__enter__ = MagicMock(return_value=inner)
    cm.__exit__ = MagicMock(return_value=False)
    return patch("voice_agent.kommo.httpx.Client", return_value=cm)


class TestListRecentNotes:
    def test_retorna_lista_em_caso_200(self, monkeypatch):
        client = _client_minimo(monkeypatch)
        resp_mock = MagicMock()
        resp_mock.status_code = 200
        resp_mock.json.return_value = {
            "_embedded": {
                "notes": [
                    {"id": 1, "entity_id": 99, "created_by": 0, "created_at": 1700000000,
                     "note_type": "common", "params": {"text": "Lia falou"}},
                    {"id": 2, "entity_id": 88, "created_by": 0, "created_at": 1700000100,
                     "note_type": "common", "params": {"text": "Lia falou de novo"}},
                ]
            }
        }
        with _mock_httpx_get(resp_mock):
            since = datetime(2026, 6, 9, 20, 0, tzinfo=timezone.utc)
            notes = client.list_recent_notes(since=since, author_user_id=0)
        assert len(notes) == 2
        assert notes[0]["lead_id"] == 99
        assert notes[1]["lead_id"] == 88

    def test_204_retorna_vazio(self, monkeypatch):
        client = _client_minimo(monkeypatch)
        resp_mock = MagicMock()
        resp_mock.status_code = 204
        with _mock_httpx_get(resp_mock):
            since = datetime(2026, 6, 9, 20, 0, tzinfo=timezone.utc)
            notes = client.list_recent_notes(since=since)
        assert notes == []

    def test_500_retorna_vazio_e_loga(self, monkeypatch):
        client = _client_minimo(monkeypatch)
        resp_mock = MagicMock()
        resp_mock.status_code = 500
        with _mock_httpx_get(resp_mock):
            since = datetime(2026, 6, 9, 20, 0, tzinfo=timezone.utc)
            notes = client.list_recent_notes(since=since)
        assert notes == []

    def test_aceita_datetime_naive_e_normaliza_pra_utc(self, monkeypatch):
        client = _client_minimo(monkeypatch)
        resp_mock = MagicMock()
        resp_mock.status_code = 200
        resp_mock.json.return_value = {"_embedded": {"notes": []}}
        with _mock_httpx_get(resp_mock):
            since = datetime(2026, 6, 9, 20, 0)
            notes = client.list_recent_notes(since=since)
        assert notes == []


class TestSearchLeadsByWindow:
    def test_pagina_ate_resultado_vazio(self, monkeypatch):
        client = _client_minimo(monkeypatch)
        # 1ª chamada retorna 2 leads, 2ª retorna 0 → para
        page_responses = [
            {"_embedded": {"leads": [
                {"id": 1, "status_id": 102560495, "custom_fields_values": []},
                {"id": 2, "status_id": 101507507, "custom_fields_values": []},
            ]}},
            {"_embedded": {"leads": []}},
        ]
        call_count = {"n": 0}

        def fake_get(*args, **kwargs):
            resp = MagicMock()
            resp.status_code = 200
            resp.json.return_value = page_responses[min(call_count["n"], len(page_responses)-1)]
            call_count["n"] += 1
            return resp

        cm = MagicMock()
        client_mock = MagicMock(get=fake_get)
        cm.__enter__ = MagicMock(return_value=client_mock)
        cm.__exit__ = MagicMock(return_value=False)
        with patch("voice_agent.kommo.httpx.Client", return_value=cm):
            leads = client.search_leads_by_window(
                pipeline_id=8601819, ts_from=1700000000, ts_to=1700000100,
            )
        assert len(leads) == 2

    def test_204_retorna_vazio(self, monkeypatch):
        client = _client_minimo(monkeypatch)
        resp_mock = MagicMock()
        resp_mock.status_code = 204
        with _mock_httpx_get(resp_mock):
            leads = client.search_leads_by_window(
                pipeline_id=8601819, ts_from=1700000000, ts_to=1700000100,
            )
        assert leads == []


class TestColetarMetricasJanela:
    def test_funil_classifica_leads_por_status(self, monkeypatch):
        """coletar_metricas_janela classifica corretamente os 8 status."""
        from lia_engineer.eval_loop import coletar_metricas_janela, FunilMetricas

        class FakeKommo:
            def search_leads_by_window(self, pipeline_id, ts_from, ts_to):
                return [
                    # 0-ETAPA ENTRADA = não respondeu
                    {"id": 1, "status_id": 96441724, "custom_fields_values": []},
                    # 2.LEADS FRIO = respondeu, sem dados, sem oferta
                    {"id": 2, "status_id": 101508307, "custom_fields_values": []},
                    # 3-AGENDAR = oferta feita
                    {"id": 3, "status_id": 102560495, "custom_fields_values": [
                        {"field_id": 1255723, "values": [{"value": "Laura"}]},
                        {"field_id": 853206, "values": [{"value": "SIS Senado"}]},
                    ]},
                    # 5-AGENDADO = aceitou + gravou
                    {"id": 4, "status_id": 101507507, "custom_fields_values": []},
                    # 8-REALIZADO = compareceu
                    {"id": 5, "status_id": 91486864, "custom_fields_values": []},
                    # 7.1-NO-SHOW
                    {"id": 6, "status_id": 106184983, "custom_fields_values": []},
                ]

        agora = datetime(2026, 6, 9, 23, 59, tzinfo=timezone.utc)
        ontem = datetime(2026, 6, 8, 23, 59, tzinfo=timezone.utc)
        m = coletar_metricas_janela(FakeKommo(), ontem, agora)

        assert m.leads_criados == 6
        assert m.leads_responderam == 5
        assert m.leads_dados_minimos == 1
        # Status oferecidos = 3-AGENDAR(102560495), 5-AGENDADO(101507507),
        # 8-REALIZADO(91486864). 7.1-NO-SHOW NÃO está nessa lista.
        assert m.leads_oferecidos_slot == 3
        assert m.leads_aceitaram_slot == 2  # leads 4 e 5
        assert m.leads_gravados_medware == 2  # leads 4 e 5
        assert m.leads_compareceram == 1  # só lead 5
        assert m.no_shows == 1

    def test_funil_taxas_calcula_corretamente(self):
        from lia_engineer.eval_loop import FunilMetricas
        m = FunilMetricas(
            janela_inicio=datetime(2026, 6, 9, tzinfo=timezone.utc),
            janela_fim=datetime(2026, 6, 10, tzinfo=timezone.utc),
            leads_criados=100,
            leads_responderam=80,
            leads_dados_minimos=60,
            leads_oferecidos_slot=50,
            leads_aceitaram_slot=40,
            leads_gravados_medware=35,
            leads_compareceram=30,
            no_shows=5,
        )
        taxas = m.funil_taxas()
        assert taxas["responderam_de_criados"] == 80.0
        assert taxas["dados_de_responderam"] == 75.0
        assert taxas["conversao_total_criado_compareceu"] == 30.0
        assert taxas["no_show_rate"] == round(100*5/35, 1)


class TestComparacaoJanelas:
    def test_detecta_degradacao_acima_limiar(self):
        from lia_engineer.eval_loop import FunilMetricas, ComparacaoJanelas
        atual = FunilMetricas(
            janela_inicio=datetime(2026, 6, 9, tzinfo=timezone.utc),
            janela_fim=datetime(2026, 6, 10, tzinfo=timezone.utc),
            leads_criados=100, leads_compareceram=15,
        )
        anterior = FunilMetricas(
            janela_inicio=datetime(2026, 6, 8, tzinfo=timezone.utc),
            janela_fim=datetime(2026, 6, 9, tzinfo=timezone.utc),
            leads_criados=100, leads_compareceram=30,  # caiu de 30% pra 15% (-50%)
        )
        comp = ComparacaoJanelas(atual=atual, anterior=anterior)
        deg = comp.degradacoes_detectadas()
        assert any(d["metrica"] == "conversao_total_criado_compareceu" for d in deg)

    def test_no_show_subir_e_degradacao(self):
        from lia_engineer.eval_loop import FunilMetricas, ComparacaoJanelas
        atual = FunilMetricas(
            janela_inicio=datetime(2026, 6, 9, tzinfo=timezone.utc),
            janela_fim=datetime(2026, 6, 10, tzinfo=timezone.utc),
            leads_gravados_medware=50, no_shows=15,  # 30% no-show
        )
        anterior = FunilMetricas(
            janela_inicio=datetime(2026, 6, 8, tzinfo=timezone.utc),
            janela_fim=datetime(2026, 6, 9, tzinfo=timezone.utc),
            leads_gravados_medware=50, no_shows=5,  # 10% no-show (subiu 200%)
        )
        comp = ComparacaoJanelas(atual=atual, anterior=anterior)
        deg = comp.degradacoes_detectadas()
        # no_show subindo é DEGRADAÇÃO
        assert any(d["metrica"] == "no_show_rate" for d in deg)
