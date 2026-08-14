"""
Bug C-144 (14/08/2026) — TODA CONVERSA não gravada no canal WA Cloud (8133).

Causa raiz: o bloco de gravação de TODA CONVERSA estava em pipeline.run(), mas
mensagens do canal WhatsApp Cloud (8133) passam por _process_whatsapp_cloud →
responder.reply() diretamente, nunca chamando pipeline.run(). Resultado: campo
1261206 permanecia vazio → Lia cega → repetia perguntas já respondidas.

Fix:
  1. Remover bloco C-133 de pipeline.run() (evita double-write com Evolution).
  2. Mover write para _sync_kommo_safely — cobrindo WA Cloud + Evolution:
     • Evolution → pipeline.run() → _sync_kommo_safely ✅
     • WA Cloud  → _process_whatsapp_cloud → _sync_kommo_safely ✅
  3. Adicionar write a _process_kommo (Salesbot/Kommo path):
     • Kommo/Salesbot → _process_kommo → write direto ✅

Testes cobrem:
  A. pipeline.run() NÃO tem mais bloco C-133 de escrita direta.
  B. _sync_kommo_safely TEM bloco C-144 de escrita.
  C. _process_kommo TEM bloco C-144.
  D. appender_turno gera formato correto [P][L].
  E. gravar_toda_conversa usa ctx['toda_conversa'] lido do Kommo.
  F. Fail-open: exceção não propaga para fora.
  G. Texto vazio (turno só com answer ou só com user_text) não quebra.
"""
import re
import unittest
from unittest.mock import MagicMock, patch, call
import inspect


class TestPipelineRunNaoTemEscritaC133(unittest.TestCase):
    """pipeline.run() NÃO deve mais ter o bloco de gravação C-133."""

    def test_pipeline_run_nao_tem_c133_block(self):
        """O comentário '# C-133' de gravação ativa foi removido de pipeline.run()."""
        import voice_agent.pipeline as _mod
        src = inspect.getsource(_mod)
        # O bloco antigo tinha: threading.Thread(target=_tc_gravar,
        # Após C-144 esse bloco foi eliminado — só deve existir o comentário
        # explicativo de que foi movido para _sync_kommo_safely.
        # Não deve existir '_tc_gravar' na função run() principal.
        # Verificação: o token '_tc_gravar' dentro de pipeline.run() foi removido.
        # Buscamos no source inteiro (conservador): o bloco C-133 ativo tinha
        # 'C-133' + 'threading.Thread' na mesma função. Agora só temos comentário.
        # Garante que não há 'target=_tc_gravar' (era o método de disparo da thread).
        self.assertNotIn(
            "target=_tc_gravar",
            src,
            "Bloco C-133 ativo (threading.Thread com _tc_gravar) ainda existe "
            "em pipeline.py — deveria ter sido removido pelo C-144.",
        )

    def test_pipeline_run_tem_comentario_c144(self):
        """pipeline.run() deve ter comentário explicando que TODA CONVERSA foi para _sync_kommo_safely."""
        import voice_agent.pipeline as _mod
        src = inspect.getsource(_mod)
        self.assertIn("C-133/C-144", src)
        self.assertIn("_sync_kommo_safely", src)


class TestSyncKommoSafelyTemEscritaC144(unittest.TestCase):
    """_sync_kommo_safely deve gravar TODA CONVERSA após ler ctx."""

    def test_sync_kommo_safely_tem_c144_block(self):
        """_sync_kommo_safely deve conter o bloco C-144."""
        import voice_agent.pipeline as _mod
        src_sync = inspect.getsource(_mod.VoicePipeline._sync_kommo_safely)
        self.assertIn("C-144", src_sync)
        self.assertIn("toda_conversa", src_sync)
        self.assertIn("appender_turno", src_sync)
        self.assertIn("gravar_toda_conversa", src_sync)

    def test_sync_kommo_safely_le_toda_conversa_do_ctx(self):
        """_sync_kommo_safely usa ctx.get('toda_conversa') — não caller_context."""
        import voice_agent.pipeline as _mod
        src_sync = inspect.getsource(_mod.VoicePipeline._sync_kommo_safely)
        # Deve usar ctx (lido do Kommo nesta função), não caller_context (stale)
        self.assertIn("ctx.get(\"toda_conversa\")", src_sync)
        # Não deve usar caller_context.get para toda_conversa nesta função
        self.assertNotIn("caller_context.get(\"toda_conversa\")", src_sync)

    def test_sync_kommo_safely_tem_fail_open(self):
        """_sync_kommo_safely deve ter try/except para TODA CONVERSA."""
        import voice_agent.pipeline as _mod
        src_sync = inspect.getsource(_mod.VoicePipeline._sync_kommo_safely)
        self.assertIn("_tc_exc", src_sync)

    def test_sync_kommo_chama_gravar_toda_conversa(self):
        """Simula _sync_kommo_safely e verifica que gravar_toda_conversa é chamado."""
        from voice_agent.pipeline import VoicePipeline

        pipeline = MagicMock(spec=VoicePipeline)
        pipeline._redis = None

        kommo_mock = MagicMock()
        kommo_mock.find_lead_id_by_phone.return_value = 24456556
        kommo_mock.get_caller_context_by_lead.return_value = {
            "lead_id": 24456556,
            "toda_conversa": "[P 09:00 14/08] ola\n[L 09:01 14/08] Oi! Como posso ajudar?",
            "status_id": 102560495,
            "known": {},
        }
        kommo_mock.add_note = MagicMock()
        kommo_mock.update_lead_fields = MagicMock()
        pipeline.kommo = kommo_mock

        responder_mock = MagicMock()
        responder_mock.extract_lead_fields.return_value = {}
        pipeline.responder = responder_mock

        gravar_chamado = []

        def fake_gravar(kommo_client, lead_id, novo_texto):
            gravar_chamado.append({
                "lead_id": lead_id,
                "texto": novo_texto,
            })
            return True

        with patch("voice_agent.toda_conversa.gravar_toda_conversa", side_effect=fake_gravar), \
             patch("voice_agent.toda_conversa.appender_turno", side_effect=lambda atual, u, l: atual + f"\n[P] {u}\n[L] {l}"):
            VoicePipeline._sync_kommo_safely(
                pipeline,
                phone="5561999990001",
                conversation_key="wa:5561999990001",
                user_text="8 anos e 5 anos",
                answer="Perfeito! Vou verificar os horários.",
                channel="81331005",
            )

        self.assertTrue(len(gravar_chamado) > 0, "gravar_toda_conversa não foi chamado")
        self.assertEqual(gravar_chamado[0]["lead_id"], 24456556)
        self.assertIn("8 anos e 5 anos", gravar_chamado[0]["texto"])


class TestProcessKommoTemEscritaC144(unittest.TestCase):
    """_process_kommo (Salesbot) deve gravar TODA CONVERSA diretamente."""

    def test_process_kommo_tem_c144_block(self):
        """_process_kommo deve conter o bloco C-144."""
        import voice_agent.webhook as _mod
        src = inspect.getsource(_mod)
        # Busca pelo bloco C-144 no contexto do _process_kommo
        self.assertIn("C-144/kommo", src)
        self.assertIn("toda_conversa", src)


class TestAppenderTurnoFormato(unittest.TestCase):
    """appender_turno gera formato correto independente do canal."""

    def test_formato_P_e_L(self):
        from voice_agent.toda_conversa import appender_turno
        result = appender_turno("", "8 anos e 5 anos", "Entendi! Para qual médico?")
        self.assertIn("[P ", result)
        self.assertIn("[L ", result)
        self.assertIn("8 anos e 5 anos", result)
        self.assertIn("Entendi! Para qual médico?", result)

    def test_acumula_turnos_anteriores(self):
        from voice_agent.toda_conversa import appender_turno
        anterior = "[P 09:00 14/08] ola\n[L 09:01 14/08] Oi!"
        result = appender_turno(anterior, "quero agendar", "Claro!")
        self.assertIn("ola", result)
        self.assertIn("quero agendar", result)
        self.assertIn("Claro!", result)

    def test_user_text_vazio_nao_quebra(self):
        from voice_agent.toda_conversa import appender_turno
        result = appender_turno("", "", "Oi! Como posso ajudar?")
        self.assertIsInstance(result, str)

    def test_answer_vazio_nao_quebra(self):
        from voice_agent.toda_conversa import appender_turno
        result = appender_turno("", "ola", "")
        self.assertIsInstance(result, str)


class TestGravarTodaConversa(unittest.TestCase):
    """gravar_toda_conversa usa patch_textarea_field (sem validação GET)."""

    def test_usa_patch_textarea_field_quando_disponivel(self):
        from voice_agent.toda_conversa import gravar_toda_conversa, FIELD_ID_TODA_CONVERSA

        kommo_mock = MagicMock()
        kommo_mock.patch_textarea_field.return_value = True

        result = gravar_toda_conversa(kommo_mock, 12345, "texto de teste")

        kommo_mock.patch_textarea_field.assert_called_once_with(
            12345, FIELD_ID_TODA_CONVERSA, "texto de teste"
        )
        self.assertTrue(result)

    def test_fail_open_em_excecao(self):
        from voice_agent.toda_conversa import gravar_toda_conversa

        kommo_mock = MagicMock()
        kommo_mock.patch_textarea_field.side_effect = Exception("timeout")

        # Não deve propagar exceção
        result = gravar_toda_conversa(kommo_mock, 12345, "texto")
        self.assertFalse(result)

    def test_field_id_correto(self):
        from voice_agent.toda_conversa import FIELD_ID_TODA_CONVERSA
        self.assertEqual(FIELD_ID_TODA_CONVERSA, 1261206)


class TestWACloudPathUsaSyncKommo(unittest.TestCase):
    """_process_whatsapp_cloud chama _sync_kommo_safely que agora grava TODA CONVERSA."""

    def test_webhook_chama_sync_kommo_safely_com_user_text_e_answer(self):
        """_process_whatsapp_cloud deve passar user_text e answer para _sync_kommo_safely."""
        import voice_agent.webhook as _mod
        src = inspect.getsource(_mod)

        # Localiza a função _process_whatsapp_cloud
        idx_wa_cloud = src.find("def _process_whatsapp_cloud")
        self.assertGreater(idx_wa_cloud, 0, "_process_whatsapp_cloud não encontrada")

        # Encontra o bloco da função (até a próxima função de mesmo nível)
        # Busca _sync_kommo_safely dentro desse bloco
        idx_sync = src.find("_sync_kommo_safely", idx_wa_cloud)
        self.assertGreater(idx_sync, idx_wa_cloud,
            "_process_whatsapp_cloud não chama _sync_kommo_safely")

        # Localiza a chamada real com args: busca o parêntese de abertura após _sync_kommo_safely
        # e verifica que tanto user_text quanto answer aparecem nos args
        # Pega um trecho maior a partir da linha que contém _sync_kommo_safely
        trecho_longo = src[idx_sync:idx_sync + 600]
        # A chamada tem os args como tupla: (phone, convo_key, user_text, answer, ...)
        # ou como kwargs. Verifica que ambos aparecem no trecho
        self.assertIn("user_text", trecho_longo,
            "user_text não passado para _sync_kommo_safely em _process_whatsapp_cloud")
        self.assertIn("answer", trecho_longo,
            "answer não passado para _sync_kommo_safely em _process_whatsapp_cloud")


class TestCasoRealLead24456556(unittest.TestCase):
    """Simula o caso real do lead 24456556 onde paciente disse '8 anos e 5 anos'."""

    def test_lia_nao_repete_pergunta_apos_ctx_populado(self):
        """
        Com TODA CONVERSA populada, get_caller_context_by_lead retorna
        ultima_msg_outbound derivada da última linha [L ...].
        O contexto permite que bypasses detectem o que já foi respondido.
        """
        from voice_agent.toda_conversa import appender_turno

        # Simula 2 turnos acumulados
        tc = ""
        tc = appender_turno(tc,
            "boa tarde, quero agendar",
            "Olá! A consulta é para um bebê, criança, adolescente ou adulto?")
        tc = appender_turno(tc,
            "8 anos e 5 anos",
            "Perfeito! Duas crianças. Para confirmar: consulta com a Dra. Karla, certo?")

        # Simula leitura do Kommo: extrai última linha [L ...]
        ultima_lia = ""
        for linha in reversed(tc.splitlines()):
            linha = linha.strip()
            if linha.startswith("[L "):
                m = re.match(r"^\[L\s+[\d:/\s]+\]\s*(.+)$", linha)
                if m:
                    ultima_lia = m.group(1).strip()
                break

        self.assertIn("Duas crianças", ultima_lia,
            "ultima_msg_outbound deveria ser a segunda resposta (sobre 2 crianças)")
        # Confirma que a pergunta sobre bebê/criança NÃO é a última
        self.assertNotIn("bebê, criança, adolescente ou adulto", ultima_lia,
            "última msg outbound NÃO deve ser a pergunta sobre perfil — paciente já respondeu")


if __name__ == "__main__":
    unittest.main(verbosity=2)
