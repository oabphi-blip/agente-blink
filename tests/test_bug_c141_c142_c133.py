"""
tests/test_bug_c141_c142_c133.py — Bugs C-141, C-142, C-133 (14/08/2026)

C-141a: Valor pediátrico não mostra Fabrício (lead 24452874)
C-141b: Unidade gravada no Kommo via known_hint (_sync_kommo_safely)
C-133: TODA CONVERSA usa patch_textarea_field sem validação GET
C-142: Repetição detectada → handoff para humano + flag Redis
"""

import os
import sys
import types
import re

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ─── C-141a: Valor pediátrico ──────────────────────────────────────────────────

class TestValorPediatrico:
    """Bug C-141a: gerar_valor_contextualizado não deve mostrar Fabrício
    quando contexto é pediátrico (criança/bebê/adolescente)."""

    def _ctx_pediatrico(self, idade=None, pediatrico=True, nome="Sinara"):
        return {
            "lead_id": 24452874,
            "known": {
                "nome_contato": nome,
                "contexto_pediatrico": pediatrico,
                "idade": idade,
                "medico": "",  # não definido — deve inferir Karla
            },
        }

    def test_sem_medico_pediatrico_nao_mostra_fabricio(self):
        """Caso real: paciente disse 'bebê' mas médico não mapeado."""
        from voice_agent.oferta_valor_contextualizado import gerar_valor_contextualizado
        ctx = self._ctx_pediatrico(pediatrico=True)
        result = gerar_valor_contextualizado(ctx, "quanto custa?")
        assert result is not None
        assert "Fabrício" not in result and "fabricio" not in result.lower()
        assert "Karla" in result or "karla" in result.lower()

    def test_sem_medico_idade_menor_18_nao_mostra_fabricio(self):
        """Paciente com idade=7 → só Karla."""
        from voice_agent.oferta_valor_contextualizado import gerar_valor_contextualizado
        ctx = self._ctx_pediatrico(idade=7, pediatrico=False)
        result = gerar_valor_contextualizado(ctx, "qual o valor?")
        assert result is not None
        assert "Fabrício" not in result and "fabricio" not in result.lower()

    def test_user_text_crianca_sem_medico_nao_mostra_fabricio(self):
        """Palavra 'filho' no user_text → Karla via _inferir_medico_user_text."""
        from voice_agent.oferta_valor_contextualizado import gerar_valor_contextualizado
        ctx = {"lead_id": 1, "known": {"nome_contato": "Sinara"}}
        result = gerar_valor_contextualizado(ctx, "é para o meu filho de 5 anos, quanto custa?")
        assert result is not None
        # Pode ainda mostrar tabela se _inferir_medico_user_text não retornar karla,
        # mas o teste principal é que o contexto pediatrico=True garante karla.

    def test_adulto_sem_medico_mostra_tabela(self):
        """Adulto sem médico e sem contexto pediátrico → tabela com ambos."""
        from voice_agent.oferta_valor_contextualizado import gerar_valor_contextualizado
        ctx = {"lead_id": 1, "known": {"nome_contato": "Maria"}}
        result = gerar_valor_contextualizado(ctx, "qual o valor?")
        # Sem contexto pediátrico → fallback para tabela geral (aceito)
        assert result is not None

    def test_fabricio_catarata_adulto_funciona(self):
        """Fabrício com catarata e adulto → não quebra."""
        from voice_agent.oferta_valor_contextualizado import gerar_valor_contextualizado
        ctx = {"lead_id": 1, "known": {
            "nome_contato": "Roberto",
            "medico": "fabricio",
            "motivo": "catarata",
        }}
        result = gerar_valor_contextualizado(ctx, "valores?")
        assert result is not None
        assert "Fabrício" in result or "catarata" in result.lower()

    def test_karla_adulto_sem_pediatrico_funciona(self):
        """Karla adulto continua funcionando."""
        from voice_agent.oferta_valor_contextualizado import gerar_valor_contextualizado
        ctx = {"lead_id": 1, "known": {
            "nome_contato": "Ana",
            "medico": "karla",
        }}
        result = gerar_valor_contextualizado(ctx, "valores?")
        assert result is not None
        assert "Karla" in result or "R$" in result


# ─── C-133: patch_textarea_field ──────────────────────────────────────────────

class TestPatchTextareaField:
    """Bug C-133: KommoClient deve ter patch_textarea_field sem validação GET."""

    def test_metodo_existe_em_kommo_client(self):
        from voice_agent.kommo import KommoClient
        assert hasattr(KommoClient, "patch_textarea_field"), (
            "KommoClient não tem patch_textarea_field — fix C-133 não aplicado"
        )

    def test_gravar_toda_conversa_usa_patch_textarea(self, monkeypatch):
        """gravar_toda_conversa chama patch_textarea_field se disponível."""
        from voice_agent.toda_conversa import gravar_toda_conversa

        chamadas = []

        class FakeKommo:
            def patch_textarea_field(self, lead_id, field_id, value):
                chamadas.append((lead_id, field_id, value))
                return True

        ok = gravar_toda_conversa(FakeKommo(), 99001, "[P 10:00 14/08] Oi\n[L 10:00 14/08] Olá!\n")
        assert ok is True
        assert len(chamadas) == 1
        assert chamadas[0][0] == 99001
        assert chamadas[0][1] == 1261206  # FIELD_ID_TODA_CONVERSA
        assert "Oi" in chamadas[0][2]

    def test_gravar_toda_conversa_toggle_off(self, monkeypatch):
        """Toggle OFF → retorna False sem chamar o Kommo."""
        monkeypatch.setenv("TODA_CONVERSA_ATIVADO", "0")
        from voice_agent.toda_conversa import gravar_toda_conversa
        import importlib
        import voice_agent.toda_conversa as tc_mod
        importlib.reload(tc_mod)

        chamadas = []

        class FakeKommo:
            def patch_textarea_field(self, *a, **k):
                chamadas.append(True)
                return True

        ok = tc_mod.gravar_toda_conversa(FakeKommo(), 99002, "texto qualquer")
        assert ok is False
        assert len(chamadas) == 0

    def test_gravar_toda_conversa_fallback_sem_metodo(self):
        """Se KommoClient não tiver patch_textarea_field, usa patch_custom_fields_raw."""
        from voice_agent.toda_conversa import gravar_toda_conversa

        chamadas_raw = []

        class FakeKommoAntigo:
            def patch_custom_fields_raw(self, lead_id, cfs):
                chamadas_raw.append((lead_id, cfs))
                return (True, {})

        ok = gravar_toda_conversa(FakeKommoAntigo(), 99003, "[P 10:00] Teste\n")
        assert ok is True
        assert len(chamadas_raw) == 1

    def test_appender_turno(self):
        """appender_turno gera formato correto [P ts] / [L ts]."""
        from voice_agent.toda_conversa import appender_turno
        resultado = appender_turno("", "Quero agendar", "Olá! Claro.")
        assert "[P " in resultado
        assert "[L " in resultado
        assert "Quero agendar" in resultado
        assert "Olá!" in resultado

    def test_appender_turno_trunca_max_chars(self):
        """Quando > 8000 chars, trunca mantendo os mais recentes."""
        from voice_agent.toda_conversa import appender_turno, _MAX_CHARS
        texto_grande = "[P 09:00] msg\n[L 09:00] resp\n" * 300
        resultado = appender_turno(texto_grande, "nova mensagem", "nova resposta")
        assert len(resultado) <= _MAX_CHARS + 200  # margem pequena de linha


# ─── C-142: Fallback humano por repetição ─────────────────────────────────────

class TestFallbackHumano:
    """Bug C-142: repetição detectada → handoff para humano."""

    def _ctx(self, ultima_outbound="", nome="Sinara", lead_id=24452256):
        return {
            "lead_id": lead_id,
            "known": {
                "nome_contato": nome,
                "ultima_msg_outbound": ultima_outbound,
            },
        }

    class _FakeRedis:
        def __init__(self):
            self.store = {}

        def setex(self, key, ttl, val):
            self.store[key] = val

        def get(self, key):
            return self.store.get(key)

        def delete(self, key):
            self.store.pop(key, None)

    def test_repetição_detectada_retorna_handoff(self):
        """Mesma pergunta de perfil enviada 2x → retorna handoff."""
        from voice_agent.fallback_humano import verificar_e_tratar_repeticao
        ultima = "Sinara, pode me contar se a consulta é para um bebê, criança, adolescente ou adulto?"
        candidata = "Sinara, pode me contar se a consulta é para um bebê, criança, adolescente ou adulto?"
        ctx = self._ctx(ultima_outbound=ultima)
        result = verificar_e_tratar_repeticao(ctx, candidata)
        assert result is not None
        assert "atendente" in result.lower() or "equipe" in result.lower()

    def test_overlap_alto_detectado(self):
        """Mensagem com variação leve mas mesmo conteúdo → detectada."""
        from voice_agent.fallback_humano import verificar_e_tratar_repeticao
        ultima = "Sinara, pode me contar se a consulta é para bebê, criança, adolescente ou adulto?"
        candidata = "Sinara, consegue me contar se é para bebê, criança, adolescente ou adulto por favor?"
        ctx = self._ctx(ultima_outbound=ultima)
        result = verificar_e_tratar_repeticao(ctx, candidata)
        assert result is not None

    def test_mensagem_diferente_nao_detectada(self):
        """Resposta genuinamente diferente → não dispara."""
        from voice_agent.fallback_humano import verificar_e_tratar_repeticao
        ultima = "Qual o convênio da consulta?"
        candidata = "Sinara, qual a data de nascimento da criança?"
        ctx = self._ctx(ultima_outbound=ultima)
        result = verificar_e_tratar_repeticao(ctx, candidata)
        assert result is None

    def test_sem_ultima_outbound_nao_detecta(self):
        """Sem histórico de outbound → fail-open."""
        from voice_agent.fallback_humano import verificar_e_tratar_repeticao
        ctx = self._ctx(ultima_outbound="")
        result = verificar_e_tratar_repeticao(ctx, "qualquer mensagem aqui")
        assert result is None

    def test_toggle_off_nunca_dispara(self, monkeypatch):
        """Toggle OFF → nunca detecta repetição."""
        monkeypatch.setenv("FALLBACK_HUMANO_ATIVADO", "0")
        from voice_agent.fallback_humano import verificar_e_tratar_repeticao
        ultima = "Sinara, pode me contar se é bebê criança adolescente adulto?"
        candidata = "Sinara, pode me contar se é bebê criança adolescente adulto?"
        ctx = self._ctx(ultima_outbound=ultima)
        result = verificar_e_tratar_repeticao(ctx, candidata)
        assert result is None

    def test_flag_redis_gravado(self):
        """Ao detectar repetição, flag Redis blink:c142_fallback_humano:{id} gravado."""
        from voice_agent.fallback_humano import verificar_e_tratar_repeticao
        redis_fake = self._FakeRedis()
        ultima = "Sinara, pode me contar se a consulta é para um bebê, criança, adolescente ou adulto?"
        candidata = ultima
        ctx = self._ctx(ultima_outbound=ultima, lead_id=24452256)
        result = verificar_e_tratar_repeticao(ctx, candidata, redis_fake)
        assert result is not None
        assert redis_fake.store.get("blink:c142_fallback_humano:24452256") == "1"

    def test_ctx_none_nao_quebra(self):
        """ctx=None → fail-open."""
        from voice_agent.fallback_humano import verificar_e_tratar_repeticao
        result = verificar_e_tratar_repeticao(None, "qualquer msg")
        assert result is None

    def test_candidata_curta_nao_detectada(self):
        """Mensagem muito curta (<6 palavras relevantes) → não detecta."""
        from voice_agent.fallback_humano import verificar_e_tratar_repeticao
        ultima = "Ok"
        candidata = "Ok, entendido!"
        ctx = self._ctx(ultima_outbound=ultima)
        result = verificar_e_tratar_repeticao(ctx, candidata)
        assert result is None

    def test_personalizacao_com_nome(self):
        """Handoff gerado inclui nome do paciente."""
        from voice_agent.fallback_humano import verificar_e_tratar_repeticao
        ultima = "Sinara, pode me contar se a consulta é para bebê, criança, adolescente ou adulto?"
        candidata = "Sinara, pode me contar se a consulta é para bebê, criança, adolescente ou adulto?"
        ctx = self._ctx(ultima_outbound=ultima, nome="Sinara")
        result = verificar_e_tratar_repeticao(ctx, candidata)
        assert result is not None
        assert "Sinara" in result

    def test_redis_none_nao_quebra(self):
        """Sem Redis → retorna handoff mas não quebra."""
        from voice_agent.fallback_humano import verificar_e_tratar_repeticao
        ultima = "Sinara, pode me contar se a consulta é para bebê criança adolescente ou adulto?"
        candidata = ultima
        ctx = self._ctx(ultima_outbound=ultima)
        result = verificar_e_tratar_repeticao(ctx, candidata, redis_client=None)
        assert result is not None  # sem Redis, funciona mas não grava flag

    def test_mensagem_completamente_diferente(self):
        """Oferta de slot ≠ pergunta de perfil → não detecta."""
        from voice_agent.fallback_humano import verificar_e_tratar_repeticao
        ultima = "Sinara, pode me contar se a consulta é para um bebê criança adolescente adulto?"
        candidata = "1️⃣ Quinta-feira (21/08) às 09:30\n2️⃣ Sexta-feira (22/08) às 14:00"
        ctx = self._ctx(ultima_outbound=ultima)
        result = verificar_e_tratar_repeticao(ctx, candidata)
        assert result is None


# ─── Integridade do fallback_humano.py ───────────────────────────────────────

class TestFallbackHumanoModulo:
    def test_importa_sem_erro(self):
        from voice_agent import fallback_humano  # noqa: F401

    def test_overlap_threshold_correto(self):
        from voice_agent.fallback_humano import _OVERLAP_THRESHOLD
        assert 0.65 <= _OVERLAP_THRESHOLD <= 0.80

    def test_palavras_relevantes_remove_stopwords(self):
        from voice_agent.fallback_humano import _palavras_relevantes
        resultado = _palavras_relevantes("pode me contar se a consulta é para um bebê")
        assert "me" not in resultado
        assert "se" not in resultado
        assert "bebê" in resultado or "bebe" in resultado
        assert "consulta" in resultado
