"""Bug C-60 — Classificador determinístico de convênios (20/07/2026).

Origem: Fábio 20/07 — lead 24325532 (CBMDF). Lia disse 'deixa eu verificar'
em vez de negar + oferecer particular. Regressão do Bug C-22 (Sandra GDF).

Fix: classificador Python puro. 3 buckets: aceito / não aceito / desconhecido.
Bypass em blindagens_deterministicas.py responde ANTES do LLM.
"""
from __future__ import annotations

import pytest

from voice_agent.classificador_convenio import (
    _normalizar,
    classificar_convenio,
    deve_responder_convenio,
    gerar_resposta_aceito,
    gerar_resposta_nao_aceito,
)


# ═══════════════════════════════════════════════════════════════════════
# NORMALIZAÇÃO
# ═══════════════════════════════════════════════════════════════════════

class TestNormalizacao:
    @pytest.mark.parametrize("entrada,esperado", [
        ("Saúde Caixa", "saudecaixa"),
        ("PF-Saúde", "pfsaude"),
        ("São Cristóvão", "saocristovao"),
        ("PLAS/JMU", "plasjmu"),
        ("CBMDF", "cbmdf"),
        ("Bacen", "bacen"),
        ("  Amil  ", "amil"),
    ])
    def test_normaliza(self, entrada, esperado):
        assert _normalizar(entrada) == esperado

    def test_vazio(self):
        assert _normalizar("") == ""
        assert _normalizar(None) == ""


# ═══════════════════════════════════════════════════════════════════════
# CONVÊNIOS ACEITOS
# ═══════════════════════════════════════════════════════════════════════

class TestAceitos:
    @pytest.mark.parametrize("texto,nome_esperado", [
        ("Aceita Bacen?", "Bacen"),
        ("Vocês pegam Saúde Caixa?", "Saúde Caixa"),
        ("Care Plus vale?", "Care Plus"),
        ("Tenho PF Saúde", "PF Saúde"),
        ("TJDFT atende?", "TJDFT Pró-Saúde"),
        ("Petrobras cobre?", "Petrobrás (Saúde Petrobrás)"),
        ("Meu plano é Anafe", "Anafe"),
        ("Convenio: Afego", "Afego"),
        ("aceita afego bh?", "Afego"),
    ])
    def test_detecta_aceito(self, texto, nome_esperado):
        r = classificar_convenio(texto)
        assert r["status"] == "aceito"
        assert r["nome_canonico"] == nome_esperado


# ═══════════════════════════════════════════════════════════════════════
# CONVÊNIOS NÃO ACEITOS
# ═══════════════════════════════════════════════════════════════════════

class TestNaoAceitos:
    @pytest.mark.parametrize("texto,nome_esperado", [
        ("Aceita CBMDF?", "CBMDF"),
        ("Aceita cbmdf pra oftalmologia", "CBMDF"),
        ("É credenciado ao Amil?", "Amil"),
        ("Bradesco Saúde funciona?", "Bradesco"),
        ("Tenho SulAmerica", "SulAmerica"),
        ("Unimed pega?", "Unimed"),
        ("Cassi", "Cassi"),
        ("Notre Dame Intermédica", "Notre Dame Intermédica"),
        ("Hapvida", "Hapvida"),
        ("GDF Saúde", "GDF"),
        ("Inas GDF", "Inas GDF"),
        ("FUNPRESP", "FUNPRESP"),
        ("Correios", "Correios"),
        ("GEAP saúde", "GEAP"),
    ])
    def test_detecta_nao_aceito(self, texto, nome_esperado):
        r = classificar_convenio(texto)
        assert r["status"] == "nao_aceito"
        assert r["nome_canonico"] == nome_esperado


# ═══════════════════════════════════════════════════════════════════════
# DESCONHECIDO
# ═══════════════════════════════════════════════════════════════════════

class TestDesconhecido:
    @pytest.mark.parametrize("texto", [
        "Tenho um convênio, aceita?",
        "Meu plano é X-Y-Z, vocês pegam?",
        "É credenciado com plano de saúde?",
    ])
    def test_menciona_convenio_generico(self, texto):
        r = classificar_convenio(texto)
        assert r["status"] == "desconhecido"


# ═══════════════════════════════════════════════════════════════════════
# SEM MENÇÃO DE CONVÊNIO
# ═══════════════════════════════════════════════════════════════════════

class TestSemMencao:
    @pytest.mark.parametrize("texto", [
        "Quero marcar consulta",
        "Estou com dor no olho",
        "Qual o horário disponível?",
        "",
        "   ",
    ])
    def test_texto_normal_nao_dispara(self, texto):
        r = classificar_convenio(texto)
        assert r["status"] == "sem_mencao"


# ═══════════════════════════════════════════════════════════════════════
# GERADORES DE RESPOSTA
# ═══════════════════════════════════════════════════════════════════════

class TestRespostas:
    def test_resposta_aceito_com_nome(self):
        texto = gerar_resposta_aceito("Bacen", "Maria")
        assert "Maria" in texto
        assert "Bacen" in texto
        assert "atendemos" in texto.lower()
        assert "Asa Norte" in texto
        assert "Águas Claras" in texto

    def test_resposta_aceito_sem_nome(self):
        texto = gerar_resposta_aceito("Saúde Caixa")
        assert "Saúde Caixa" in texto
        assert "atendemos" in texto.lower()

    def test_resposta_nao_aceito_menciona_particular(self):
        texto = gerar_resposta_nao_aceito("CBMDF", "João")
        assert "João" in texto
        assert "CBMDF" in texto
        assert "não atende" in texto.lower()
        # Deve oferecer particular
        assert "particular" in texto.lower()
        # Deve ter os 3 valores
        assert "R$ 611" in texto
        assert "R$ 670" in texto
        # Deve mencionar exames
        assert "tonometria" in texto.lower()

    def test_resposta_nao_aceito_incentivo_visivel(self):
        texto = gerar_resposta_nao_aceito("Amil")
        assert "incentivad" in texto.lower() or "particular" in texto.lower()


# ═══════════════════════════════════════════════════════════════════════
# BYPASS — integração com ctx
# ═══════════════════════════════════════════════════════════════════════

class TestBypass:
    def test_cbmdf_gera_negativa(self):
        ctx = {
            "known": {"nome_paciente": "Ana Silva"},
        }
        texto = deve_responder_convenio(ctx, "Aceita CBMDF?")
        assert texto is not None
        assert "CBMDF" in texto
        assert "não atende" in texto.lower()
        assert "R$ 611" in texto

    def test_bacen_gera_confirmacao(self):
        ctx = {"known": {"nome_paciente": "Pedro"}}
        texto = deve_responder_convenio(ctx, "Meu plano é Bacen")
        assert texto is not None
        assert "Bacen" in texto
        assert "Pedro" in texto
        assert "atendemos" in texto.lower()

    def test_convenio_ja_conhecido_nao_sobrescreve(self):
        ctx = {"known": {"convenio": "Saúde Caixa"}}
        texto = deve_responder_convenio(ctx, "Aceita CBMDF?")
        # Não sobrescreve porque convenio já preenchido
        assert texto is None

    def test_desconhecido_deixa_llm_seguir(self):
        ctx = {"known": {}}
        texto = deve_responder_convenio(ctx, "Meu plano é XYZ empresarial")
        assert texto is None

    def test_texto_normal_nao_dispara(self):
        ctx = {"known": {}}
        assert deve_responder_convenio(ctx, "Bom dia") is None
        assert deve_responder_convenio(ctx, "Quero agendar") is None

    def test_toggle_off(self, monkeypatch):
        monkeypatch.setenv("BLINDAGEM_CONVENIO_ATIVADO", "0")
        ctx = {"known": {}}
        assert deve_responder_convenio(ctx, "Aceita CBMDF?") is None

    def test_ctx_none_seguro(self):
        # Não deve estourar
        texto = deve_responder_convenio(None, "Aceita Bacen?")
        assert texto is not None

    def test_lead_24325532_texto_real(self):
        """Reproduz caso Fábio 20/07/2026 exato."""
        ctx = {"known": {}}
        # Paciente escreveu algo como "aceita CBMDF?"
        texto = deve_responder_convenio(ctx, "Aceita CBMDF?")
        assert texto is not None
        assert "CBMDF" in texto
        assert "particular" in texto.lower()


# ═══════════════════════════════════════════════════════════════════════
# INTEGRAÇÃO COM tentar_bypass_deterministico
# ═══════════════════════════════════════════════════════════════════════

class TestIntegracaoOrquestrador:
    def test_orquestrador_pega_convenio(self):
        from voice_agent.blindagens_deterministicas import (
            tentar_bypass_deterministico,
        )
        ctx = {"known": {}}
        r = tentar_bypass_deterministico(ctx, "Aceita CBMDF?")
        assert r is not None
        nome_bypass, texto = r
        assert nome_bypass == "convenio"
        assert "CBMDF" in texto

    def test_orquestrador_urgencia_ganha_de_convenio(self):
        """Urgência tem prioridade absoluta mesmo se paciente mencionar convênio."""
        from voice_agent.blindagens_deterministicas import (
            tentar_bypass_deterministico,
        )
        ctx = {"known": {}}
        # Paciente com trauma + menciona convênio
        r = tentar_bypass_deterministico(
            ctx, "Aceita CBMDF? Estou com trauma na córnea",
        )
        assert r is not None
        nome_bypass, _ = r
        # Urgência deve ganhar
        assert nome_bypass == "urgencia"
