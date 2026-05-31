"""Pytest dos 4 endpoints /admin/auditoria-* do webhook.py.

Usa FastAPI TestClient — sem precisar de Kommo/Medware reais.
"""
from __future__ import annotations

import importlib
import os
import pytest


@pytest.fixture(scope="module")
def client():
    # Garante settings de teste neutros.
    os.environ.setdefault("WEBHOOK_SECRET", "")
    os.environ.setdefault("SLACK_BOT_TOKEN_AUDITORIA", "")
    try:
        from fastapi.testclient import TestClient
    except ImportError:
        pytest.skip("fastapi.testclient não disponível")
    web = importlib.import_module("voice_agent.webhook")
    app = web.create_app()
    return TestClient(app)


class TestEndpointAuditoriaTick:

    def test_sem_lead_id_400(self, client):
        r = client.post("/admin/auditoria-tick")
        assert r.status_code == 400
        assert "lead_id" in r.json()["error"]

    def test_lead_invalido_400(self, client):
        r = client.post("/admin/auditoria-tick?lead_id=abc")
        assert r.status_code == 400

    def test_sem_body_pacientes_devolve_501(self, client):
        """Modo prod ainda não plugado em Kommo+Medware."""
        r = client.post("/admin/auditoria-tick?lead_id=999")
        assert r.status_code == 501
        body = r.json()
        assert body["lead_id"] == 999
        assert "Kommo" in body["hint"]

    def test_dry_run_com_pacientes_simulados_coincide(self, client):
        payload = {
            "pacientes": [{
                "idx": 1, "nome": "Maria Silva",
                "medico_nome": "Dra. Karla Delalíbera",
                "unidade": "Asa Norte", "convenio": "Saúde Caixa",
                "agrupador_planejado": "AGRUPADOR_1_ADULTO_ROTINA",
                "planejado_codigos": [1, 2, 3],
                "realizado_codigos": [3, 2, 1],
            }],
        }
        r = client.post(
            "/admin/auditoria-tick?lead_id=12345&dry_run=true",
            json=payload,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["lead_id"] == 12345
        assert body["dry_run"] is True
        assert len(body["resultados"]) == 1
        res = body["resultados"][0]
        assert res["status"] == "fechada"
        assert res["coincide"] is True
        assert res["slack"]["skipped"] is True
        assert res["slack"]["reason"] == "dry_run"
        # Mensagem preview gerada.
        assert "sem discrepância" in res["slack"]["preview"]

    def test_dry_run_com_discrepancia(self, client):
        payload = {
            "pacientes": [{
                "idx": 2, "nome": "João Costa",
                "medico_nome": "Dr. Fabrício Freitas",
                "unidade": "Águas Claras", "convenio": "Sem convênio",
                "agrupador_planejado": "AGRUPADOR_2_ADULTO_EMERGENCIA",
                "planejado_codigos": [10, 11, 12],
                "realizado_codigos": [10, 11, 12, 99],
            }],
        }
        r = client.post(
            "/admin/auditoria-tick?lead_id=200&dry_run=true",
            json=payload,
        )
        assert r.status_code == 200
        res = r.json()["resultados"][0]
        assert res["status"] == "aguardando_secretaria"
        assert res["exames_a_mais"] == [99]
        assert res["exames_a_menos"] == []
        assert "Secretaria Águas Claras" in res["slack"]["preview"]
        assert "Dr. Fabrício Freitas" in res["slack"]["preview"]

    def test_multiplos_pacientes(self, client):
        payload = {
            "pacientes": [
                {"idx": 1, "nome": "A", "medico_nome": "Karla",
                 "unidade": "Asa Norte", "convenio": "x",
                 "agrupador_planejado": "AGRUPADOR_1",
                 "planejado_codigos": [1], "realizado_codigos": [1]},
                {"idx": 2, "nome": "B", "medico_nome": "Karla",
                 "unidade": "Asa Norte", "convenio": "x",
                 "agrupador_planejado": "AGRUPADOR_3",
                 "planejado_codigos": [5], "realizado_codigos": []},
            ],
        }
        r = client.post(
            "/admin/auditoria-tick?lead_id=77&dry_run=true",
            json=payload,
        )
        assert r.status_code == 200
        body = r.json()
        assert len(body["resultados"]) == 2
        assert body["resultados"][0]["status"] == "fechada"
        assert body["resultados"][1]["status"] == "fonte_vazia"


class TestEndpointConfirma:

    def test_secretaria_avanca_para_medico(self, client):
        r = client.post(
            "/admin/auditoria-confirma"
            "?lead_id=1&paciente_idx=1"
            "&papel=secretaria_an&decisao=ok&autor=Mariana"
            "&status_atual=aguardando_secretaria",
        )
        assert r.status_code == 200
        body = r.json()
        assert body["novo_status"] == "aguardando_medico"
        assert "Mariana" in body["assinatura"]
        assert body["campo_assinatura"] == "sec"

    def test_medico_fecha_apos_secretaria(self, client):
        r = client.post(
            "/admin/auditoria-confirma"
            "?lead_id=1&paciente_idx=1"
            "&papel=medico_karla&decisao=ok&autor=Karla"
            "&status_atual=aguardando_medico",
        )
        body = r.json()
        assert body["novo_status"] == "fechada"
        assert body["ciclo_fechado"] is True

    def test_divergente_status_divergencia(self, client):
        r = client.post(
            "/admin/auditoria-confirma"
            "?lead_id=2&paciente_idx=1"
            "&papel=secretaria_ac&decisao=divergente&autor=Ana"
            "&status_atual=aguardando_secretaria",
        )
        body = r.json()
        assert body["novo_status"] == "divergencia"
        assert body["criar_tarefa_humana"] is True

    def test_papel_invalido_400(self, client):
        r = client.post(
            "/admin/auditoria-confirma"
            "?lead_id=1&paciente_idx=1"
            "&papel=enfermeira&decisao=ok&autor=X"
            "&status_atual=aguardando_secretaria",
        )
        assert r.status_code == 400
        assert "papel inválido" in r.json()["error"]


class TestEndpointFilas:

    def test_fila_secretaria_unidade_valida(self, client):
        r = client.get("/admin/secretaria-auditoria?unidade=asa-norte")
        assert r.status_code == 200
        body = r.json()
        assert body["unidade"] == "asa-norte"
        assert body["status"] == "stub"

    def test_fila_secretaria_unidade_invalida_400(self, client):
        r = client.get("/admin/secretaria-auditoria?unidade=brasilia")
        assert r.status_code == 400

    def test_fila_medico_valido(self, client):
        r = client.get("/admin/medico-auditoria?medico=karla")
        assert r.status_code == 200
        assert r.json()["medico"] == "karla"

    def test_fila_medico_invalido_400(self, client):
        r = client.get("/admin/medico-auditoria?medico=jose")
        assert r.status_code == 400


class TestEndpointRAG:
    """Memória ativa nível 1 — task #85."""

    def test_rag_status_devolve_estatisticas(self, client):
        r = client.get("/admin/rag-status")
        assert r.status_code == 200
        body = r.json()
        assert "ok" in body
        if body.get("ok"):
            assert body.get("total_trechos", 0) > 0
            assert "por_tipo" in body

    def test_rag_query_sem_q_400(self, client):
        r = client.get("/admin/rag-query")
        assert r.status_code == 400

    def test_rag_query_devolve_trechos(self, client):
        r = client.get("/admin/rag-query?q=Inas+GDF")
        assert r.status_code == 200
        body = r.json()
        assert body["query"] == "Inas GDF"
        assert "trechos" in body
        # Pode vir 0 se base sumiu, mas estrutura sempre presente
        if body["total_recuperado"] > 0:
            t = body["trechos"][0]
            assert "titulo" in t and "preview" in t and "similaridade" in t

    def test_rag_query_filtra_tipo(self, client):
        r = client.get("/admin/rag-query?q=consulta&tipo=licao")
        assert r.status_code == 200
        body = r.json()
        assert body["filtrar_tipo"] == "licao"
        for t in body["trechos"]:
            assert t["fonte_tipo"] == "licao"

    def test_rag_query_tipo_invalido_400(self, client):
        r = client.get("/admin/rag-query?q=teste&tipo=invalido")
        assert r.status_code == 400

    def test_rag_rebuild_funciona(self, client):
        r = client.post("/admin/rag-rebuild")
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        assert body["total_trechos"] >= 0


class TestEndpointRenovarJanela:
    """Task #87 — preview da mensagem de renovação 24h."""

    def test_preview_com_nome(self, client):
        r = client.get("/admin/renovar-janela-preview?nome=Marcela+Souza")
        assert r.status_code == 200
        body = r.json()
        assert "Marcela" in body["mensagem"]
        assert "Souza" not in body["mensagem"]
        assert body["validacao"]["ok"] is True
        assert body["tamanho_chars"] < 600

    def test_preview_sem_nome(self, client):
        r = client.get("/admin/renovar-janela-preview")
        body = r.json()
        assert r.status_code == 200
        assert body["mensagem"].startswith("Olá!")
        assert body["validacao"]["ok"] is True

    def test_preview_simula_elegivel_status_agendar_e_23h(self, client):
        r = client.get(
            "/admin/renovar-janela-preview"
            "?nome=Marcela&status_id=102560495&horas_desde_paciente=23"
        )
        body = r.json()
        assert r.status_code == 200
        assert body["elegibilidade"] is not None
        assert body["elegibilidade"]["elegivel"] is True

    def test_preview_simula_inelegivel_status_agendado(self, client):
        # 4-AGENDADO não deve renovar.
        r = client.get(
            "/admin/renovar-janela-preview"
            "?nome=Marcela&status_id=101507507&horas_desde_paciente=23"
        )
        body = r.json()
        elig = body["elegibilidade"]
        assert elig["elegivel"] is False
        assert elig["razao"] == "status_pos_agendado"

    def test_preview_simula_inelegivel_janela_morta(self, client):
        r = client.get(
            "/admin/renovar-janela-preview"
            "?nome=Joao&status_id=102560495&horas_desde_paciente=30"
        )
        elig = r.json()["elegibilidade"]
        assert elig["elegivel"] is False
        assert elig["razao"] == "janela_expirou_so_template"


class TestEndpointDispatch:
    """Task #94 — dispatcher /admin/renovacao-dispatch."""

    def test_sem_params_obrigatorios_400(self, client):
        r = client.post("/admin/renovacao-dispatch")
        assert r.status_code == 400

    def test_dry_run_janela_aberta_devolve_free_form(self, client):
        r = client.post(
            "/admin/renovacao-dispatch"
            "?lead_id=24048691"
            "&telefone=(61)+99999-0000"
            "&nome_contato=Marcela"
            "&status_id=102560495"
            "&horas_desde_paciente=23"
            "&ja_respondeu_na_vida=true"
            "&dry_run=true",
        )
        assert r.status_code == 200
        body = r.json()
        assert body["estrategia"] == "free_form"
        assert body["skipped"] is True  # dry_run
        assert body["razao_skip"] == "dry_run"
        assert "Marcela" in body["payload_preview"]["text"]

    def test_dry_run_janela_morta_devolve_template_1039(self, client):
        r = client.post(
            "/admin/renovacao-dispatch"
            "?lead_id=999"
            "&telefone=5561999990000"
            "&nome_contato=Maria+Soares"
            "&status_id=102560495"
            "&horas_desde_paciente=30"
            "&ja_respondeu_na_vida=true"
            "&dry_run=true",
        )
        body = r.json()
        assert body["estrategia"] == "template_1039"
        assert body["template_name"] == "1039_ativar_grau_de_urgencia"
        assert body["payload_preview"]["template"]["name"] == "1039_ativar_grau_de_urgencia"

    def test_lead_agendado_nao_dispara(self, client):
        r = client.post(
            "/admin/renovacao-dispatch"
            "?lead_id=1&telefone=5561999990000&nome_contato=X"
            "&status_id=101507507"  # 4-AGENDADO
            "&horas_desde_paciente=23"
            "&dry_run=true",
        )
        body = r.json()
        assert body["estrategia"] == "nao_disparar"
        assert body["razao_skip"] == "status_pos_agendado"

    def test_lead_invalido_400(self, client):
        r = client.post(
            "/admin/renovacao-dispatch"
            "?lead_id=abc&telefone=x&nome_contato=y",
        )
        assert r.status_code == 400
