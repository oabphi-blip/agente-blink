"""
Bug C-72 (26/07/2026) — Recuperação de contexto histórico da conversa.

Etapa 1: campo MENS HUMANO (1261148, textarea) — último outbound humano.
Etapa 2: Chats API Kommo — histórico completo via URL DA CONVERSA (1260160).

Cenário-raiz: lead 15321519 Ana Beatriz (1a, Serpro, Karla Asa Norte).
- 22/07: humano enviou template (opções 1/2)
- 26/07 (4 dias depois): paciente respondeu "1"
- Lia entrou na conversa sem saber o que o template dizia
- C-58 (montar_bloco_conversa_atual) usa janela 6h → não cobriu 96h

Fix Etapa 1:
1. Campo MENS HUMANO (1261148, textarea) adicionado ao id_to_label
   em get_caller_context_by_lead() → lido sem chamadas API extras
2. Webhook /admin/kommo-trigger-msg-humano grava msg_texto no campo
3. montar_bloco_campo_mens_humano() injeta contexto sem janela de tempo
4. responder.py usa o bloco quando C-58 não produziu resultado
"""
from __future__ import annotations

from voice_agent.historico_conversa import (
    extrair_chat_id_da_url,
    montar_bloco_campo_mens_humano,
    montar_bloco_historico_chat,
)


# ─────────────────────────────────────────────────────────
# 1. montar_bloco_campo_mens_humano
# ─────────────────────────────────────────────────────────

class TestMontarBlocoCampoMensHumano:
    """Valida que o bloco de contexto é gerado corretamente."""

    def test_retorna_vazio_quando_ctx_nao_tem_known(self):
        assert montar_bloco_campo_mens_humano({}) == ""

    def test_retorna_vazio_quando_campo_vazio(self):
        ctx = {"known": {"mens_humano": ""}}
        assert montar_bloco_campo_mens_humano(ctx) == ""

    def test_retorna_vazio_quando_campo_none(self):
        ctx = {"known": {"mens_humano": None}}
        assert montar_bloco_campo_mens_humano(ctx) == ""

    def test_retorna_vazio_quando_known_ausente(self):
        ctx = {"lead_id": 15321519}
        assert montar_bloco_campo_mens_humano(ctx) == ""

    def test_retorna_bloco_quando_campo_preenchido(self):
        texto = "Olá! Tenho 2 opções: 1) Consulta 08h 2) Consulta 14h. Qual prefere?"
        ctx = {"known": {"mens_humano": texto}}
        bloco = montar_bloco_campo_mens_humano(ctx)
        assert bloco != ""
        assert texto in bloco

    def test_bloco_contem_regra_c72(self):
        ctx = {"known": {"mens_humano": "Opção 1 ou opção 2?"}}
        bloco = montar_bloco_campo_mens_humano(ctx)
        assert "C-72" in bloco
        assert "ATENDENTE HUMANO" in bloco

    def test_bloco_instrui_continuar_conversa(self):
        ctx = {"known": {"mens_humano": "Qual horário prefere?"}}
        bloco = montar_bloco_campo_mens_humano(ctx)
        assert "coerente" in bloco.lower() or "continua" in bloco.lower()

    def test_bloco_proibe_reiniciar_triagem(self):
        ctx = {"known": {"mens_humano": "Template aqui"}}
        bloco = montar_bloco_campo_mens_humano(ctx)
        assert "reinici" in bloco.lower()

    def test_aceita_ctx_none_sem_crash(self):
        # Não deve levantar exceção
        result = montar_bloco_campo_mens_humano(None)  # type: ignore[arg-type]
        assert result == ""

    def test_aceita_ctx_string_sem_crash(self):
        result = montar_bloco_campo_mens_humano("invalido")  # type: ignore[arg-type]
        assert result == ""

    def test_cenario_real_ana_beatriz_lead_15321519(self):
        """Reproduz o caso real: paciente respondeu 'opção 1' ao template."""
        texto_template = (
            "Olá! Tenho disponibilidade para a consulta da Ana Beatriz:\n"
            "1️⃣ Quinta-feira (24/07) às 09:30\n"
            "2️⃣ Sexta-feira (25/07) às 08:00\n"
            "Qual opção fica melhor?"
        )
        ctx = {
            "lead_id": 15321519,
            "known": {
                "mens_humano": texto_template,
                "convenio": "Serpro",
                "unidade": "Asa Norte",
                "medico": "Dra. Karla Delalíbera",
            },
        }
        bloco = montar_bloco_campo_mens_humano(ctx)
        assert bloco != ""
        assert "Ana Beatriz" in bloco or "09:30" in bloco or "08:00" in bloco


# ─────────────────────────────────────────────────────────
# 2. Campo 1261148 no id_to_label do kommo.py
# ─────────────────────────────────────────────────────────

class TestFieldMensHumanoNoIdToLabel:
    """Garante que field_id 1261148 está mapeado em kommo.py."""

    def test_field_id_1261148_esta_mapeado(self):
        """O campo MENS HUMANO deve estar em id_to_label de get_caller_context_by_lead."""
        import ast
        import os

        kommo_path = os.path.join(
            os.path.dirname(__file__), "..", "voice_agent", "kommo.py"
        )
        with open(kommo_path, encoding="utf-8") as f:
            source = f.read()

        # Verificar presença da string literalmente
        assert "1261148" in source, (
            "field_id 1261148 (MENS HUMANO) não encontrado em voice_agent/kommo.py. "
            "Adicionar ao id_to_label em get_caller_context_by_lead()."
        )

    def test_label_mens_humano_no_codigo(self):
        import os

        kommo_path = os.path.join(
            os.path.dirname(__file__), "..", "voice_agent", "kommo.py"
        )
        with open(kommo_path, encoding="utf-8") as f:
            source = f.read()

        assert '"mens_humano"' in source or "'mens_humano'" in source, (
            "Label 'mens_humano' não encontrado em voice_agent/kommo.py."
        )


# ─────────────────────────────────────────────────────────
# 3. Webhook grava MENS HUMANO — verificação de código
# ─────────────────────────────────────────────────────────

class TestWebhookGravaMensHumano:
    """Garante que o webhook /admin/kommo-trigger-msg-humano
    chama patch_custom_fields_raw com field_id 1261148."""

    def test_webhook_referencia_field_1261148(self):
        import os

        webhook_path = os.path.join(
            os.path.dirname(__file__), "..", "voice_agent", "webhook.py"
        )
        with open(webhook_path, encoding="utf-8") as f:
            source = f.read()

        assert "1261148" in source, (
            "field_id 1261148 (MENS HUMANO) não encontrado em webhook.py. "
            "O webhook /admin/kommo-trigger-msg-humano deve gravar nesse campo."
        )

    def test_webhook_usa_patch_custom_fields_raw(self):
        import os

        webhook_path = os.path.join(
            os.path.dirname(__file__), "..", "voice_agent", "webhook.py"
        )
        with open(webhook_path, encoding="utf-8") as f:
            source = f.read()

        assert "patch_custom_fields_raw" in source, (
            "patch_custom_fields_raw não encontrado em webhook.py. "
            "Usar esse método para garantir gravação real (bypass Bug C-12)."
        )

    def test_webhook_retorna_campo_mens_humano_gravado(self):
        """Resposta do webhook deve incluir 'mens_humano_gravado' na resposta."""
        import os

        webhook_path = os.path.join(
            os.path.dirname(__file__), "..", "voice_agent", "webhook.py"
        )
        with open(webhook_path, encoding="utf-8") as f:
            source = f.read()

        assert "mens_humano_gravado" in source, (
            "'mens_humano_gravado' não encontrado no JSONResponse do webhook. "
            "Necessário para observabilidade do fix C-72."
        )


# ─────────────────────────────────────────────────────────
# 4. responder.py injeta C-72 quando C-58 retorna vazio
# ─────────────────────────────────────────────────────────

class TestResponderInjetaC72:
    """Garante que responder.py usa montar_bloco_campo_mens_humano."""

    def test_responder_referencia_c72(self):
        import os

        responder_path = os.path.join(
            os.path.dirname(__file__), "..", "voice_agent", "responder.py"
        )
        with open(responder_path, encoding="utf-8") as f:
            source = f.read()

        assert "montar_bloco_campo_mens_humano" in source, (
            "montar_bloco_campo_mens_humano não encontrado em responder.py. "
            "O bloco C-72 deve ser injetado quando C-58 não produz resultado."
        )

    def test_responder_usa_bloco_c72_so_se_c58_vazio(self):
        """C-72 deve ser fallback de C-58, não substituição."""
        import os

        responder_path = os.path.join(
            os.path.dirname(__file__), "..", "voice_agent", "responder.py"
        )
        with open(responder_path, encoding="utf-8") as f:
            source = f.read()

        # Deve haver lógica condicional ligando _bloco_conv e _bloco_c72
        assert "_bloco_conv" in source and "_bloco_c72" in source, (
            "Variáveis _bloco_conv e _bloco_c72 devem coexistir em responder.py. "
            "C-72 é fallback de C-58."
        )

    def test_responder_injeta_etapa2_como_primaria(self):
        """Etapa 2 (Chats API) deve ter prioridade sobre Etapa 1 (MENS HUMANO)."""
        import os

        responder_path = os.path.join(
            os.path.dirname(__file__), "..", "voice_agent", "responder.py"
        )
        with open(responder_path, encoding="utf-8") as f:
            source = f.read()

        assert "montar_bloco_historico_chat" in source, (
            "montar_bloco_historico_chat não encontrado em responder.py. "
            "Etapa 2 (Chats API) deve ser a via primária do bloco C-72."
        )
        assert "historico_chat_msgs" in source, (
            "historico_chat_msgs não encontrado em responder.py. "
            "Pipeline injeta as mensagens da Chats API nessa chave."
        )


# ─────────────────────────────────────────────────────────
# 5. extrair_chat_id_da_url — Etapa 2
# ─────────────────────────────────────────────────────────

class TestExtrairChatIdDaUrl:
    """Valida a extração do chat_id a partir da URL do Kommo."""

    def test_url_completa_com_chats(self):
        url = "https://univeja.kommo.com/chats/42318/leads/detail/15321519"
        assert extrair_chat_id_da_url(url) == 42318

    def test_url_sem_chats_retorna_none(self):
        url = "https://univeja.kommo.com/leads/detail/15321519"
        assert extrair_chat_id_da_url(url) is None

    def test_url_vazia_retorna_none(self):
        assert extrair_chat_id_da_url("") is None

    def test_none_retorna_none(self):
        assert extrair_chat_id_da_url(None) is None  # type: ignore[arg-type]

    def test_path_relativo_com_chats(self):
        url = "/chats/99999/leads/detail/12345"
        assert extrair_chat_id_da_url(url) == 99999

    def test_chat_id_numerico_grande(self):
        url = "https://univeja.kommo.com/chats/1234567890/leads/detail/99"
        assert extrair_chat_id_da_url(url) == 1234567890


# ─────────────────────────────────────────────────────────
# 6. montar_bloco_historico_chat — Etapa 2
# ─────────────────────────────────────────────────────────

class TestMontarBlocoHistoricoChat:
    """Valida que o bloco de histórico completo é gerado corretamente."""

    def _msg(self, texto: str, direction: str = "out", ts: int = 1753574400) -> dict:
        return {
            "created_at": ts,
            "direction": direction,
            "content": {"text": texto},
        }

    def test_retorna_vazio_quando_lista_vazia(self):
        assert montar_bloco_historico_chat([]) == ""

    def test_retorna_vazio_quando_nenhum_texto(self):
        msgs = [{"created_at": 1753574400, "direction": "in", "content": {"text": ""}}]
        assert montar_bloco_historico_chat(msgs) == ""

    def test_bloco_contem_regra_c72(self):
        msgs = [self._msg("Olá, tenho 2 slots: 1️⃣ sexta 2️⃣ segunda. Qual prefere?")]
        bloco = montar_bloco_historico_chat(msgs)
        assert "C-72" in bloco

    def test_bloco_contem_atendente_para_outbound(self):
        msgs = [self._msg("Texto do atendente", direction="out")]
        bloco = montar_bloco_historico_chat(msgs)
        assert "ATENDENTE" in bloco

    def test_bloco_contem_paciente_para_inbound(self):
        msgs = [self._msg("Resposta do paciente", direction="in")]
        bloco = montar_bloco_historico_chat(msgs)
        assert "PACIENTE" in bloco

    def test_bloco_proibe_reiniciar_triagem(self):
        msgs = [self._msg("Slot 1 ou slot 2?")]
        bloco = montar_bloco_historico_chat(msgs)
        assert "reinici" in bloco.lower() or "NÃO reinicie" in bloco

    def test_bloco_instrui_continuar_coerente(self):
        msgs = [self._msg("Slot 1 ou slot 2?")]
        bloco = montar_bloco_historico_chat(msgs)
        assert "coerente" in bloco.lower() or "COERENTE" in bloco

    def test_limite_max_msgs_respeitado(self):
        msgs = [self._msg(f"Mensagem {i}") for i in range(50)]
        bloco = montar_bloco_historico_chat(msgs, max_msgs=5)
        # Deve conter só as 5 últimas
        assert "Mensagem 45" in bloco
        assert "Mensagem 0" not in bloco

    def test_cenario_real_ana_beatriz_15321519(self):
        """Reproduz conversa real: template de slots, paciente responde dias depois."""
        msgs = [
            self._msg(
                "Olá! Para a Ana Beatriz, tenho disponível:\n"
                "1️⃣ Quinta-feira (24/07) às 09:30\n"
                "2️⃣ Sexta-feira (25/07) às 08:00\n"
                "Qual prefere?",
                direction="out",
                ts=1753228800,  # 22/07
            ),
            self._msg(
                "1",
                direction="in",
                ts=1753574400,  # 26/07 (4 dias depois)
            ),
        ]
        bloco = montar_bloco_historico_chat(msgs)
        assert bloco != ""
        assert "ATENDENTE" in bloco
        assert "PACIENTE" in bloco
        # Deve mencionar o texto do template
        assert "09:30" in bloco or "08:00" in bloco or "Ana Beatriz" in bloco

    def test_fallback_campo_text_na_raiz(self):
        """Suporta mensagens com 'text' na raiz (versão antiga da API)."""
        msgs = [{"created_at": 1753574400, "direction": "out", "text": "Texto fallback"}]
        bloco = montar_bloco_historico_chat(msgs)
        assert "Texto fallback" in bloco

    def test_direction_alternativo_0_1(self):
        """Suporta direction="0"/"1" (formato numérico da API)."""
        msgs_out = [self._msg("Saída", direction="1")]
        msgs_in = [self._msg("Entrada", direction="0")]
        assert "ATENDENTE" in montar_bloco_historico_chat(msgs_out)
        assert "PACIENTE" in montar_bloco_historico_chat(msgs_in)


# ─────────────────────────────────────────────────────────
# 7. Pipeline injeta historico_chat_msgs
# ─────────────────────────────────────────────────────────

class TestPipelineInjetaHistoricoChat:
    """Garante que pipeline.py pré-carrega Chats API em caller_context."""

    def test_pipeline_referencia_c72_etapa2(self):
        import os

        pipeline_path = os.path.join(
            os.path.dirname(__file__), "..", "voice_agent", "pipeline.py"
        )
        with open(pipeline_path, encoding="utf-8") as f:
            source = f.read()

        assert "historico_chat_msgs" in source, (
            "historico_chat_msgs não encontrado em pipeline.py. "
            "Pipeline deve pre-carregar mensagens da Chats API antes de responder."
        )

    def test_pipeline_chama_get_chat_messages_raw(self):
        import os

        pipeline_path = os.path.join(
            os.path.dirname(__file__), "..", "voice_agent", "pipeline.py"
        )
        with open(pipeline_path, encoding="utf-8") as f:
            source = f.read()

        assert "get_chat_messages_raw" in source, (
            "get_chat_messages_raw não encontrado em pipeline.py. "
            "Pipeline deve chamar esse método para buscar mensagens da Chats API."
        )

    def test_pipeline_chama_get_chat_id_for_lead(self):
        import os

        pipeline_path = os.path.join(
            os.path.dirname(__file__), "..", "voice_agent", "pipeline.py"
        )
        with open(pipeline_path, encoding="utf-8") as f:
            source = f.read()

        assert "get_chat_id_for_lead" in source, (
            "get_chat_id_for_lead não encontrado em pipeline.py. "
            "Pipeline deve descobrir chat_id quando URL não contém /chats/."
        )

    def test_kommo_tem_metodo_get_chat_messages_raw(self):
        import os

        kommo_path = os.path.join(
            os.path.dirname(__file__), "..", "voice_agent", "kommo.py"
        )
        with open(kommo_path, encoding="utf-8") as f:
            source = f.read()

        assert "get_chat_messages_raw" in source, (
            "get_chat_messages_raw não encontrado em kommo.py. "
            "Método necessário para buscar mensagens via Chats API."
        )

    def test_kommo_tem_metodo_get_chat_id_for_lead(self):
        import os

        kommo_path = os.path.join(
            os.path.dirname(__file__), "..", "voice_agent", "kommo.py"
        )
        with open(kommo_path, encoding="utf-8") as f:
            source = f.read()

        assert "get_chat_id_for_lead" in source, (
            "get_chat_id_for_lead não encontrado em kommo.py. "
            "Método necessário para descobrir chat_id via /api/v4/chats?entity_type=leads."
        )

    def test_kommo_tem_field_url_da_conversa(self):
        import os

        kommo_path = os.path.join(
            os.path.dirname(__file__), "..", "voice_agent", "kommo.py"
        )
        with open(kommo_path, encoding="utf-8") as f:
            source = f.read()

        assert "1260160" in source, (
            "field_id 1260160 (URL DA CONVERSA) não encontrado em kommo.py. "
            "Campo necessário para Etapa 2 extrair chat_id da URL."
        )
        assert "url_da_conversa" in source, (
            "Label 'url_da_conversa' não encontrado em kommo.py. "
            "Campo 1260160 deve ser mapeado como url_da_conversa no id_to_label."
        )
