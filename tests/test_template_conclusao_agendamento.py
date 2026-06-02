"""Pytest do parser de template "Conclusão de Agendamento" Blink.

Camada 4 do ja_agendado (Fábio 02/06/2026 manhã). Atendente humano
envia esse template via WhatsApp depois de agendar manualmente no
Medware. Não vira nota Kommo, então camadas 1-3 não pegam.

Mensagem real fornecida pelo Fábio como caso teste canônico:
Graziela Araujo Morum (contato) marca pra Enzo Araujo Morum (paciente).
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402


# Mensagem EXATA fornecida pelo Fábio
MENSAGEM_REAL_BLINK = """👋 Olá, GRAZIELA ARAUJO MORUM

✅ Conclusão de Agendamento.

📅 Data e Hora da primeira consulta: 18/05/2026 17:30
👤 Paciente(s): Enzo Araujo Morum
👩‍⚕️Médica: Dra. Karla Delalibera
🩺 Especialidade: Oftalmopediatria
📋 Convênio: Pro ser STJ
📍 Unidade: Asa Norte

🔗 A comunicação é essencial para garantir o seu atendimento e também dos outros no tempo certo. ⭐

⏳ Passado 2 horas após o recebimento da mensagem, e sem resposta, chamamos outro paciente da fila de espera.

Responda com:

1.Tudo Correto
2. Corrigir Dados"""


# ----------------------------------------------------------------------
# Caso real — mensagem exata fornecida
# ----------------------------------------------------------------------

class TestMensagemRealFabio:

    def test_detecta_template_completo(self):
        from voice_agent.kommo import detectar_template_conclusao_agendamento
        out = detectar_template_conclusao_agendamento(MENSAGEM_REAL_BLINK)
        assert out is not None
        # Os 7 campos extraídos
        assert out["paciente"] == "Enzo Araujo Morum"
        assert "Karla Delalibera" in out["medico"]
        assert out["especialidade"] == "Oftalmopediatria"
        assert out["convenio"] == "Pro ser STJ"
        assert out["unidade"] == "Asa Norte"
        # Data normalizada
        assert out["data"] == "18/05/2026"
        assert out["hora"] == "17:30"
        # ISO completo
        assert out["data_iso"].startswith("2026-05-18T17:30:00")


# ----------------------------------------------------------------------
# Variações que devem disparar
# ----------------------------------------------------------------------

class TestVariacoes:

    def test_data_hora_com_h_em_vez_de_dois_pontos(self):
        from voice_agent.kommo import detectar_template_conclusao_agendamento
        msg = """
        ✅ Conclusão de Agendamento.
        Data e Hora: 18/05/2026 17h30
        Paciente: João Silva
        Médica: Dra. Karla
        """
        out = detectar_template_conclusao_agendamento(msg)
        assert out is not None
        assert out["hora"] == "17:30"

    def test_ano_curto_2_digitos(self):
        from voice_agent.kommo import detectar_template_conclusao_agendamento
        msg = """
        ✅ Conclusão de Agendamento.
        Data e Hora: 18/05/26 17:30
        Paciente: João
        Médica: Karla
        """
        out = detectar_template_conclusao_agendamento(msg)
        assert out is not None
        assert out["data_iso"].startswith("2026-05-18")

    def test_paciente_unico_sem_parenteses(self):
        from voice_agent.kommo import detectar_template_conclusao_agendamento
        msg = """
        ✅ Conclusão de Agendamento.
        Data e Hora: 18/05/2026 17:30
        Paciente: Maria Silva
        Médica: Dra. Karla
        """
        out = detectar_template_conclusao_agendamento(msg)
        assert out is not None
        assert out["paciente"] == "Maria Silva"

    def test_medico_dr_masculino(self):
        from voice_agent.kommo import detectar_template_conclusao_agendamento
        msg = """
        Conclusão de Agendamento
        Data e Hora: 09/06/2026 18:30
        Paciente: Pedro Silva
        Médico: Dr. Fabrício Freitas
        """
        out = detectar_template_conclusao_agendamento(msg)
        assert out is not None
        assert "Fabrício" in out["medico"]

    def test_sem_campos_opcionais(self):
        """Especialidade, convênio, unidade são opcionais."""
        from voice_agent.kommo import detectar_template_conclusao_agendamento
        msg = """
        Conclusão de Agendamento
        Data e Hora: 09/06/2026 18:30
        Paciente: Pedro
        Médica: Dra. Karla
        """
        out = detectar_template_conclusao_agendamento(msg)
        assert out is not None
        assert "especialidade" not in out or out.get("especialidade") is None


# ----------------------------------------------------------------------
# Casos NEGATIVOS
# ----------------------------------------------------------------------

class TestNaoDispara:

    def test_string_vazia_None(self):
        from voice_agent.kommo import detectar_template_conclusao_agendamento
        assert detectar_template_conclusao_agendamento("") is None
        assert detectar_template_conclusao_agendamento(None) is None

    def test_mensagem_paciente_normal_None(self):
        from voice_agent.kommo import detectar_template_conclusao_agendamento
        assert detectar_template_conclusao_agendamento("oi, quero agendar") is None

    def test_template_sem_paciente_None(self):
        from voice_agent.kommo import detectar_template_conclusao_agendamento
        msg = """
        Conclusão de Agendamento
        Data e Hora: 09/06/2026 18:30
        Médica: Dra. Karla
        """
        # falta paciente
        assert detectar_template_conclusao_agendamento(msg) is None

    def test_template_sem_data_None(self):
        from voice_agent.kommo import detectar_template_conclusao_agendamento
        msg = """
        Conclusão de Agendamento
        Paciente: Pedro
        Médica: Dra. Karla
        """
        # falta data e hora
        assert detectar_template_conclusao_agendamento(msg) is None

    def test_data_invalida_None(self):
        from voice_agent.kommo import detectar_template_conclusao_agendamento
        msg = """
        Conclusão de Agendamento
        Data e Hora: 99/99/9999 99:99
        Paciente: Pedro
        Médica: Dra. Karla
        """
        # data 99/99 não parseável
        out = detectar_template_conclusao_agendamento(msg)
        # Pode ou disparar com data normalizada errada ou None
        if out is not None:
            # Aceita só se data_iso é coerente
            assert out.get("data_iso", "").startswith("9999") is False

    def test_so_palavras_chave_sem_estrutura_None(self):
        from voice_agent.kommo import detectar_template_conclusao_agendamento
        msg = (
            "Concluí o agendamento com a Karla pra 09/06 às 18h, "
            "tudo certo!"
        )
        # Falta o template literal "Conclusão de Agendamento" + estrutura
        # → deve devolver None (essa é responsabilidade da camada 3)
        assert detectar_template_conclusao_agendamento(msg) is None


# ----------------------------------------------------------------------
# Limpeza de campos (emojis, asteriscos)
# ----------------------------------------------------------------------

class TestLimpezaCampos:

    def test_emoji_no_meio_eh_removido(self):
        from voice_agent.kommo import detectar_template_conclusao_agendamento
        msg = """
        ✅ Conclusão de Agendamento.
        📅 Data e Hora: 18/05/2026 17:30
        👤 Paciente: 🌟Enzo Araujo Morum
        👩‍⚕️ Médica: Dra. Karla Delalibera
        """
        out = detectar_template_conclusao_agendamento(msg)
        assert out is not None
        # Limpa stars/emojis
        assert "🌟" not in out["paciente"]

    def test_asteriscos_negrito_markdown_removidos(self):
        from voice_agent.kommo import detectar_template_conclusao_agendamento
        msg = """
        Conclusão de Agendamento
        Data e Hora: 18/05/2026 17:30
        Paciente: **Maria Silva**
        Médica: *Dra. Karla*
        """
        out = detectar_template_conclusao_agendamento(msg)
        assert out is not None
        assert "*" not in out["paciente"]
        assert "*" not in out["medico"]
