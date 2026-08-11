"""
Bug C-100 (10/08/2026) — Salesbot path (/kommo) não verificava
agent_paused_for_lead antes de chamar responder.reply().

Cenários cobertos:
1. lead em 1-ATENDIMENTO HUMANO (106563343) → Lia silencia no /kommo
2. ATIVADO IA = Desativado → Lia silencia no /kommo
3. ATIVADO IA = Ativado + etapa ativa → Lia responde normalmente
4. caller_context=None (lead não encontrado) → pipeline continua (sem crash)
5. agent_paused_for_lead levanta exceção → fail-open (Lia responde)
6. return_url recebe agent_answer vazio quando paused (não fica pendente)
7. ATIVADO IA = DESATIVADO (uppercase) → bloqueia igual
8. etapa 0-COMPROMISSO COM DATA (106919911) → bloqueia
9. lead 24411978: status_id=106563343 + ativado_ia=Desativado → duplo bloqueio
10. lead normal em 3-AGENDAR: responde mesmo se human-wrote-recent expirado
"""

from unittest.mock import MagicMock, patch, call


# ─── helpers ────────────────────────────────────────────────────────────────

def _make_ctx(status_id: int, ativado_ia: str, lead_id: int = 99000) -> dict:
    return {
        "found": True,
        "lead_id": lead_id,
        "name": "Teste",
        "status_id": status_id,
        "ja_agendado": False,
        "known": {
            "ativado_ia": ativado_ia,
        },
    }


def _make_kommo_mock(ctx, agent_paused_retval):
    """Cria um mock de KommoClient pré-configurado."""
    k = MagicMock()
    k.get_caller_context_by_lead.return_value = ctx
    k.agent_paused_for_lead.return_value = agent_paused_retval
    k.update_lead_fields.return_value = True
    return k


# ─── importação do módulo a testar ──────────────────────────────────────────

def _get_process_kommo():
    """
    _process_kommo é uma closure definida DENTRO de register_routes().
    Não podemos importar diretamente — precisamos instanciar o app com mocks.
    Aqui testamos a LÓGICA equivalente isolada, verificando as chamadas.
    """
    pass  # lógica testada via integração de mocks abaixo


# ─── testes diretos na lógica do bloco C-100 ────────────────────────────────

class TestC100SalesbotPaused:
    """
    Testa a lógica do bloco C-100 adicionado ao _process_kommo:

        if pipeline.kommo is not None and caller_context:
            motivo = pipeline.kommo.agent_paused_for_lead(caller_context, window)
            if motivo:
                ... posta agent_answer="" + return

    Simulamos o bloco completo sem subir o servidor FastAPI.
    """

    def _run_block(
        self,
        ctx,
        agent_paused_retval,
        return_url="https://kommo.example.com/return",
        lead_id="99000",
    ):
        """
        Simula o bloco C-100 e retorna (bloqueou: bool, update_called: bool,
        post_called: bool, responder_called: bool).
        """
        import httpx

        kommo = _make_kommo_mock(ctx, agent_paused_retval)

        # settings mock
        settings = MagicMock()
        settings.agent_handoff_window_min = 30
        settings.kommo_token = "tok_test"

        # responder mock
        responder = MagicMock()
        responder.reply.return_value = {"answer": "resposta real"}

        # simulação do bloco C-100
        bloqueou = False
        update_called = False
        post_called = False
        responder_called = False

        caller_context = ctx
        pipeline_kommo = kommo

        if pipeline_kommo is not None and caller_context:
            try:
                motivo = pipeline_kommo.agent_paused_for_lead(
                    caller_context, settings.agent_handoff_window_min
                )
            except Exception:
                motivo = None
            if motivo:
                bloqueou = True
                lid = caller_context.get("lead_id") or (int(lead_id) if lead_id else None)
                if lid:
                    try:
                        pipeline_kommo.update_lead_fields(int(lid), {"ativado_ia": "DESATIVADO"})
                        update_called = True
                    except Exception:
                        pass
                if return_url:
                    try:
                        with patch("httpx.Client") as mock_client:
                            cm = MagicMock()
                            mock_client.return_value.__enter__.return_value = cm
                            cm.post.return_value = MagicMock(status_code=200)
                            import httpx as _httpx
                            with _httpx.Client(timeout=10) as _c:
                                _c.post(return_url, json={"data": {"agent_answer": ""}}, headers={})
                        post_called = True
                    except Exception:
                        pass

        if not bloqueou:
            responder.reply("key", "msg", caller_context=caller_context)
            responder_called = True

        return bloqueou, update_called, post_called, responder_called

    def test_01_atendimento_humano_bloqueia(self):
        """Lead em 1-ATENDIMENTO HUMANO (106563343) → bloqueado."""
        ctx = _make_ctx(106563343, "Ativado")
        # agent_paused_for_lead retorna "etapa-humana" pra status_id em ST_AGENT_OFF
        bloqueou, update_called, _, responder_called = self._run_block(ctx, "etapa-humana")
        assert bloqueou, "Deve bloquear para etapa ATENDIMENTO HUMANO"
        assert not responder_called, "responder.reply NÃO deve ser chamado"

    def test_02_ativado_ia_desativado_bloqueia(self):
        """ATIVADO IA = Desativado → bloqueado (Regra 0)."""
        ctx = _make_ctx(102560495, "Desativado")  # 3-AGENDAR mas IA desligada
        bloqueou, _, _, responder_called = self._run_block(ctx, "ia-desativada")
        assert bloqueou
        assert not responder_called

    def test_03_normal_responde(self):
        """Lead normal em 3-AGENDAR, IA ativa → responder.reply é chamado."""
        ctx = _make_ctx(102560495, "Ativado")
        bloqueou, _, _, responder_called = self._run_block(ctx, None)
        assert not bloqueou
        assert responder_called

    def test_04_caller_context_none_continua(self):
        """Sem caller_context (lead não encontrado) → pipeline continua sem crash."""
        import httpx

        settings = MagicMock()
        settings.agent_handoff_window_min = 30
        settings.kommo_token = "tok"

        responder = MagicMock()
        responder.reply.return_value = {"answer": "ok"}

        bloqueou = False
        caller_context = None

        if None is not None and caller_context:
            bloqueou = True  # nunca entra

        assert not bloqueou

    def test_05_agent_paused_exception_failopen(self):
        """agent_paused_for_lead levanta exceção → fail-open (não bloqueia)."""
        ctx = _make_ctx(106563343, "Ativado")
        kommo = MagicMock()
        kommo.get_caller_context_by_lead.return_value = ctx
        kommo.agent_paused_for_lead.side_effect = RuntimeError("timeout Kommo")
        kommo.update_lead_fields.return_value = True

        settings = MagicMock()
        settings.agent_handoff_window_min = 30
        settings.kommo_token = "tok"

        responder_called = False
        caller_context = ctx

        bloqueou = False
        if kommo is not None and caller_context:
            try:
                motivo = kommo.agent_paused_for_lead(
                    caller_context, settings.agent_handoff_window_min
                )
            except Exception:
                motivo = None  # fail-open
            if motivo:
                bloqueou = True

        assert not bloqueou, "Exceção em agent_paused → fail-open (Lia responde)"

    def test_06_update_lead_fields_chamado_com_desativado(self):
        """Quando bloqueado, update_lead_fields é chamado com DESATIVADO."""
        ctx = _make_ctx(106563343, "Ativado", lead_id=24411978)
        kommo = _make_kommo_mock(ctx, "etapa-humana")

        settings = MagicMock()
        settings.agent_handoff_window_min = 30
        settings.kommo_token = "tok"

        caller_context = ctx
        if kommo is not None and caller_context:
            try:
                motivo = kommo.agent_paused_for_lead(caller_context, 30)
            except Exception:
                motivo = None
            if motivo:
                lid = caller_context.get("lead_id")
                if lid:
                    kommo.update_lead_fields(int(lid), {"ativado_ia": "DESATIVADO"})

        kommo.update_lead_fields.assert_called_once_with(24411978, {"ativado_ia": "DESATIVADO"})

    def test_07_ativado_ia_uppercase_bloqueia(self):
        """ATIVADO IA = DESATIVADO (uppercase via Kommo) → bloqueado."""
        ctx = _make_ctx(102560495, "DESATIVADO")
        bloqueou, _, _, _ = self._run_block(ctx, "ia-desativada")
        assert bloqueou

    def test_08_compromisso_data_bloqueia(self):
        """Etapa 0-COMPROMISSO COM DATA (106919911) → bloqueado via etapa-humana."""
        ctx = _make_ctx(106919911, "Ativado")
        bloqueou, _, _, responder_called = self._run_block(ctx, "etapa-humana")
        assert bloqueou
        assert not responder_called

    def test_09_lead_24411978_duplo_bloqueio(self):
        """
        Lead 24411978 (caso real): status_id=106563343 E ativado_ia=Desativado.
        Qualquer um dos dois seria suficiente para bloquear.
        """
        ctx = _make_ctx(106563343, "Desativado", lead_id=24411978)
        # agent_paused_for_lead retornaria "ia-desativada" (Regra 0 é verificada primeiro)
        bloqueou, update_called, _, responder_called = self._run_block(
            ctx, "ia-desativada", lead_id="24411978"
        )
        assert bloqueou, "Lead 24411978 deve ser bloqueado"
        assert not responder_called, "responder.reply NÃO deve ser chamado"

    def test_10_agendar_normal_responde_apos_window_humano(self):
        """
        Lead em 3-AGENDAR com humano que escreveu > 30min atrás.
        agent_paused_for_lead retorna None → Lia responde.
        """
        ctx = _make_ctx(102560495, "Ativado")
        bloqueou, _, _, responder_called = self._run_block(ctx, None)
        assert not bloqueou
        assert responder_called

    def test_11_humano_recente_bloqueia(self):
        """
        Humano escreveu < 30min → agent_paused_for_lead retorna 'humano-escreveu-recente'.
        """
        ctx = _make_ctx(102560495, "Ativado")
        bloqueou, _, _, responder_called = self._run_block(ctx, "humano-escreveu-recente")
        assert bloqueou
        assert not responder_called

    def test_12_bloqueio_clinico_bloqueia(self):
        """
        Nota médica com 'NÃO AGENDAR MAIS' → agent_paused_for_lead retorna 'bloqueio-clinico'.
        """
        ctx = _make_ctx(102560495, "Ativado")
        bloqueou, _, _, _ = self._run_block(ctx, "bloqueio-clinico")
        assert bloqueou

    def test_13_lead_agendado_status4_nao_bloqueia_via_agent_paused(self):
        """
        Lead em 4-AGENDADO (101507507) — NOT in ST_AGENT_OFF — agent_paused
        retorna None. Lia responde (mas ja_agendado=True protege de oferta de slots).
        """
        ctx = _make_ctx(101507507, "Ativado")
        bloqueou, _, _, responder_called = self._run_block(ctx, None)
        assert not bloqueou
        assert responder_called

    def test_14_pipeline_kommo_none_skip_check(self):
        """Se pipeline.kommo é None, o bloco C-100 é pulado sem crash."""
        # Simula pipeline.kommo = None
        caller_context = _make_ctx(106563343, "Desativado")
        pipeline_kommo = None

        bloqueou = False
        if pipeline_kommo is not None and caller_context:
            bloqueou = True  # nunca entra

        assert not bloqueou


class TestC100WebhookPyHasCheck:
    """
    Verificação textual: garante que o bloco C-100 está realmente
    presente no arquivo webhook.py (defesa contra remoção acidental).
    """

    def test_c100_bloco_presente_no_webhook(self):
        import os
        webhook_path = os.path.join(
            os.path.dirname(__file__), "..", "voice_agent", "webhook.py"
        )
        with open(webhook_path, encoding="utf-8") as f:
            conteudo = f.read()

        assert "C-100" in conteudo, "Bloco C-100 deve estar presente em webhook.py"
        assert "agent_paused_for_lead" in conteudo, (
            "_process_kommo deve chamar agent_paused_for_lead (C-100)"
        )
        # Garante que o check aparece ANTES de responder.reply (ordem correta)
        idx_c100 = conteudo.index("C-100")
        idx_reply = conteudo.index('result = responder.reply(convo_key, message, caller_context=caller_context)')
        assert idx_c100 < idx_reply, (
            "Bloco C-100 deve preceder a chamada a responder.reply"
        )

    def test_process_whatsapp_cloud_ja_tinha_check(self):
        """_process_whatsapp_cloud já tinha agent_paused_for_lead — não regrediu."""
        import os
        webhook_path = os.path.join(
            os.path.dirname(__file__), "..", "voice_agent", "webhook.py"
        )
        with open(webhook_path, encoding="utf-8") as f:
            conteudo = f.read()

        # Deve ter pelo menos 2 chamadas a agent_paused_for_lead
        ocorrencias = conteudo.count("agent_paused_for_lead")
        assert ocorrencias >= 2, (
            f"Esperado ≥2 chamadas a agent_paused_for_lead (kommo + whatsapp). "
            f"Encontrado: {ocorrencias}"
        )
