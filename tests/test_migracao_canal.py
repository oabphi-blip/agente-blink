"""Pytest do detector + mensageiro de migração canal legado → 8133 (07/06/2026).

Cobertura:
1. is_canal_legado() detecta WhatsApp Lite / Evolution / 0710.
2. is_canal_oficial() detecta WhatsApp Business / Cloud / 8133.
3. mensagem_migracao_8133() personaliza com nome + médico + link wa.me.
4. deve_migrar_lead() respeita toggle, evita loop, limita histórico.
5. Toggle LIA_MIGRACAO_CANAL_ENABLED via env.
6. Vocabulário: mensagem NÃO contém palavras proibidas ("slot", "ofertar", etc).

Caso real de regressão: Marcelo 23934832 (07/06 17:03) — voltou no canal Lite
após Closed-lost de 15/05; Lia deve detectar e migrar sozinha.
"""
from __future__ import annotations

import pytest

from voice_agent.migracao_canal import (
    NUMERO_OFICIAL_8133,
    NUMERO_OFICIAL_E164,
    deve_migrar_lead,
    is_canal_legado,
    is_canal_oficial,
    mensagem_migracao_8133,
    migracao_habilitada,
)


class TestDeteccaoCanal:
    @pytest.mark.parametrize("canal", [
        "WhatsApp Lite", "whatsapp_lite", "WHATSAPP LITE",
        "Evolution API", "evolution-0710", "wa-lite",
        "Canal 0710", "wa_lite",
    ])
    def test_canais_legados_detectados(self, canal):
        assert is_canal_legado(canal) is True, f"Falhou pra canal {canal!r}"

    @pytest.mark.parametrize("canal", [
        "WhatsApp Business", "whatsapp_cloud", "WA-Cloud",
        "Official Channel", "Canal 8133", "wa_cloud",
    ])
    def test_canais_oficiais_detectados(self, canal):
        assert is_canal_oficial(canal) is True
        # Oficiais NÃO são legados
        assert is_canal_legado(canal) is False

    def test_canal_vazio_nao_e_legado(self):
        assert is_canal_legado(None) is False
        assert is_canal_legado("") is False

    def test_canal_desconhecido_nao_e_legado(self):
        # Conservador: só migra se reconhecer o canal como legado conhecido.
        assert is_canal_legado("Telegram Bot") is False
        assert is_canal_legado("Slack Connect") is False


class TestMensagemMigracao:
    def test_mensagem_contem_numero_oficial(self):
        msg = mensagem_migracao_8133(nome="Marcelo")
        assert NUMERO_OFICIAL_8133 in msg
        assert NUMERO_OFICIAL_E164 in msg, "Link wa.me precisa do número E.164"

    def test_personaliza_nome(self):
        msg = mensagem_migracao_8133(nome="Marcelo Silva")
        assert "Marcelo" in msg, "Primeiro nome deve aparecer na saudação"
        assert "Silva" not in msg, "Sobrenome NÃO deve aparecer (intimidade)"

    def test_sem_nome_usa_saudacao_neutra(self):
        msg = mensagem_migracao_8133()
        assert "Olá" in msg or "Boa notícia" in msg

    def test_inclui_link_wame(self):
        msg = mensagem_migracao_8133(nome="Carol", motivo="incentivos Dra. Karla")
        assert "wa.me/" in msg
        assert "Carol" in msg

    def test_inclui_medico_quando_passado(self):
        msg = mensagem_migracao_8133(nome="Ana", medico="Dr. Fabrício Freitas")
        assert "Dr. Fabrício Freitas" in msg

    def test_pede_pra_salvar_contato(self):
        msg = mensagem_migracao_8133(nome="X")
        assert "Salva" in msg or "salva" in msg
        assert "Blink Oftalmologia" in msg

    def test_avisa_que_numero_atual_sai_de_uso(self):
        msg = mensagem_migracao_8133(nome="X")
        assert "sair de uso" in msg.lower() or "saindo de uso" in msg.lower()


class TestVocabularioProibido:
    """Garante que a mensagem segue a regra do KB (07/06/2026)."""

    @pytest.mark.parametrize("proibido", [
        "slot", "slots", "ofertar", "dispatch", "outbound",
        "canary", "fallback", "smoke test",
    ])
    def test_msg_nao_contem_jargao_tecnico(self, proibido):
        msg = mensagem_migracao_8133(
            nome="Teste", motivo="agendamento", medico="Dra. Karla",
        )
        assert proibido.lower() not in msg.lower(), \
            f"Mensagem contém termo proibido {proibido!r}"


class TestDeveMigrar:
    def test_canal_legado_sem_status_migracao_e_inicio_conversa(self):
        assert deve_migrar_lead(
            canal_atual="WhatsApp Lite",
            status_conversa=None,
            historico_msgs_neste_canal=0,
        ) is True

    def test_canal_oficial_nao_migra(self):
        assert deve_migrar_lead(
            canal_atual="WhatsApp Business",
            status_conversa=None,
        ) is False

    def test_canal_legado_mas_ja_migracao_em_andamento_nao_repete(self):
        assert deve_migrar_lead(
            canal_atual="WhatsApp Lite",
            status_conversa="aguardando_migracao_8133",
        ) is False

    def test_canal_legado_mas_conversa_avancada_nao_atrapalha(self):
        # Se já trocou várias mensagens, NÃO interrompe agora.
        assert deve_migrar_lead(
            canal_atual="WhatsApp Lite",
            historico_msgs_neste_canal=5,
        ) is False

    def test_canal_legado_2_msgs_ainda_migra(self):
        # Limite é > 2.
        assert deve_migrar_lead(
            canal_atual="WhatsApp Lite",
            historico_msgs_neste_canal=2,
        ) is True

    def test_toggle_off_nao_migra_nada(self, monkeypatch):
        monkeypatch.setenv("LIA_MIGRACAO_CANAL_ENABLED", "0")
        assert migracao_habilitada() is False
        assert deve_migrar_lead(canal_atual="WhatsApp Lite") is False

    def test_toggle_default_on(self, monkeypatch):
        monkeypatch.delenv("LIA_MIGRACAO_CANAL_ENABLED", raising=False)
        assert migracao_habilitada() is True


class TestCasoMarcelo:
    """Cenário real: lead Marcelo 23934832 voltou em 07/06 17:00 no canal Lite
    após Closed-lost de 15/05/2026. Lia deve detectar e migrar.
    """

    def test_marcelo_dispara_migracao(self):
        assert deve_migrar_lead(
            canal_atual="WhatsApp Lite",
            status_conversa="",
            historico_msgs_neste_canal=1,
        ) is True

    def test_marcelo_msg_personalizada(self):
        msg = mensagem_migracao_8133(
            nome="Marcelo", motivo="incentivos",
            medico="Dra. Karla Delalíbera",
        )
        # Tudo que deve aparecer
        assert "Marcelo" in msg
        assert "Dra. Karla Delalíbera" in msg
        assert "(61) 8133-1005" in msg
        assert "wa.me/556181331005" in msg
        # Nada do que NÃO deve aparecer
        assert "slot" not in msg.lower()
        assert "convênio" not in msg.lower(), \
            "Não pergunta convênio na migração — só convida pro canal novo"
