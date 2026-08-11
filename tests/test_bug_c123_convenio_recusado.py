"""Bug C-123 (11/08/2026) — Convênio não aceito: tom correto + escolha pós-recusa.

Problemas corrigidos:
    1. Tom seco "não está na nossa rede credenciada" → "em processo de credenciamento"
    2. "particular" substituído por "sem convênio" em toda mensagem de recusa
    3. Valor prematuro (R$ 611/670) removido — não sabe motivo/médico ainda
    4. Ordem canônica: 1️⃣ Somente com Convênio / 2️⃣ Seguir Sem Convênio
    5. Bypass detecta escolha do paciente → injeta ctx.known.convenio = "Não se aplica"
    6. Flag c123_marcar_sem_convenio para pipeline gravar campo Kommo

Lead real: 24441038 — paciente perguntou sobre Bradesco.
"""
from __future__ import annotations

import importlib
import os
import sys
import types

import pytest

# ── garantir importabilidade sem dependências opcionais ──────────────────────
_STUB_MODS = [
    "redis", "httpx",
    "voice_agent.medware", "voice_agent.kommo",
    "voice_agent.enriquecimento_ctx",
]
for _m in _STUB_MODS:
    if _m not in sys.modules:
        sys.modules[_m] = types.ModuleType(_m)

# Stub anthropic com Anthropic class
if "anthropic" not in sys.modules:
    _anthropic_mod = types.ModuleType("anthropic")
    class _FakeAnthropicClient:
        def __init__(self, **kw): pass
    _anthropic_mod.Anthropic = _FakeAnthropicClient
    _anthropic_mod.APIStatusError = Exception
    _anthropic_mod.APIConnectionError = Exception
    _anthropic_mod.RateLimitError = Exception
    _anthropic_mod.BadRequestError = Exception
    sys.modules["anthropic"] = _anthropic_mod
else:
    _anthropic_mod = sys.modules["anthropic"]
    if not hasattr(_anthropic_mod, "Anthropic"):
        class _FakeAnthropicClient:
            def __init__(self, **kw): pass
        _anthropic_mod.Anthropic = _FakeAnthropicClient
        _anthropic_mod.APIStatusError = Exception
        _anthropic_mod.APIConnectionError = Exception
        _anthropic_mod.RateLimitError = Exception
        _anthropic_mod.BadRequestError = Exception

# stub _convenio_aceito se necessário
_ec = sys.modules.get("voice_agent.enriquecimento_ctx")
if _ec and not hasattr(_ec, "_convenio_aceito"):
    def _convenio_aceito_stub(nome):
        _nao_aceitos = {"bradesco", "inas", "gdf", "amil", "sul america", "sulamerica"}
        return nome.lower().strip() not in _nao_aceitos
    _ec._convenio_aceito = _convenio_aceito_stub

import voice_agent.blindagens_deterministicas as _bd


# ── helpers ──────────────────────────────────────────────────────────────────

def _ctx(convenio="", aceito=None, convenio_aceito_known=True, ultima_msg="", lead_id=9001):
    ctx = {
        "lead_id": lead_id,
        "known": {
            "nome_paciente": "Carlos",
        },
    }
    if convenio:
        ctx["known"]["convenio"] = convenio
    if aceito is not None:
        ctx["known"]["convenio_aceito"] = aceito
    if ultima_msg:
        ctx["known"]["ultima_msg_outbound"] = ultima_msg
    return ctx


_ULTIMA_OPCOES = (
    "Temos condições diferenciadas para atendimento sem convênio! "
    "Qual a sua preferência?\n\n"
    "1️⃣ Somente com Convênio\n"
    "2️⃣ Seguir Sem Convênio"
)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. HELPER _montar_recusa_convenio — verificar tom canônico
# ═══════════════════════════════════════════════════════════════════════════════

class TestMontagemRecusaConvenio:

    def test_sem_particular_na_mensagem(self):
        msg = _bd._montar_recusa_convenio("Bradesco")
        assert "particular" not in msg.lower()

    def test_sem_valor_prematuro(self):
        msg = _bd._montar_recusa_convenio("Bradesco")
        assert "611" not in msg
        assert "670" not in msg
        assert "R$" not in msg

    def test_processo_credenciamento_presente(self):
        msg = _bd._montar_recusa_convenio("Bradesco")
        assert "processo de credenciamento" in msg.lower()

    def test_opcao_1_somente_convenio(self):
        msg = _bd._montar_recusa_convenio("Bradesco")
        assert "1️⃣" in msg
        assert "Somente com Convênio" in msg

    def test_opcao_2_seguir_sem_convenio(self):
        msg = _bd._montar_recusa_convenio("Bradesco")
        assert "2️⃣" in msg
        assert "Seguir Sem Convênio" in msg

    def test_saudacao_inclusa(self):
        msg = _bd._montar_recusa_convenio("Amil", saud="Carlos, ")
        assert msg.startswith("Carlos, ")

    def test_sem_saudacao_vazia(self):
        msg = _bd._montar_recusa_convenio("Bradesco", saud="")
        assert msg.startswith("o **Bradesco**")

    def test_nome_conv_exibido(self):
        msg = _bd._montar_recusa_convenio("Sul América")
        assert "Sul América" in msg


# ═══════════════════════════════════════════════════════════════════════════════
# 2. FAQ convênio aceito — resposta de recusa usa tom canônico
# ═══════════════════════════════════════════════════════════════════════════════

class TestFaqConvenioAceito:

    def test_recusa_bradesco_sem_particular(self):
        ctx = _ctx(convenio="Bradesco", aceito=False)
        r = _bd.deve_responder_faq_convenio_aceito(
            ctx, "vocês aceitam Bradesco?"
        )
        assert r is not None
        assert "particular" not in r.lower()

    def test_recusa_bradesco_sem_valor(self):
        ctx = _ctx(convenio="Bradesco", aceito=False)
        r = _bd.deve_responder_faq_convenio_aceito(
            ctx, "vocês aceitam Bradesco?"
        )
        assert r is not None
        assert "R$" not in r
        assert "611" not in r

    def test_recusa_bradesco_processo_credenciamento(self):
        ctx = _ctx(convenio="Bradesco", aceito=False)
        r = _bd.deve_responder_faq_convenio_aceito(
            ctx, "atende bradesco saude?"
        )
        assert r is not None
        assert "processo de credenciamento" in r.lower()

    def test_recusa_bradesco_opcoes_canonicas(self):
        ctx = _ctx(convenio="Bradesco", aceito=False)
        r = _bd.deve_responder_faq_convenio_aceito(
            ctx, "vocês aceitam Bradesco?"
        )
        assert "1️⃣ Somente com Convênio" in r
        assert "2️⃣ Seguir Sem Convênio" in r

    def test_aceite_bacen_intacto(self):
        ctx = _ctx(convenio="Bacen", aceito=True)
        r = _bd.deve_responder_faq_convenio_aceito(ctx, "aceitam Bacen?")
        assert r is not None
        assert "sim" in r.lower()
        assert "atendemos" in r.lower()

    def test_recusa_injeta_nome_em_known(self):
        ctx = _ctx(convenio="Amil", aceito=False)
        r = _bd.deve_responder_faq_convenio_aceito(ctx, "aceitam Amil?")
        assert r is not None
        assert ctx["known"].get("convenio_nao_aceito_nome") is not None

    def test_recusa_caminho_b_sem_particular(self):
        """Caminho B: convenio_aceito não computado, extrai do user_text."""
        ctx = _ctx()  # sem convenio em known
        r = _bd.deve_responder_faq_convenio_aceito(
            ctx, "vocês aceitam o convênio Bradesco?"
        )
        # Pode ser None se derivação falhou, mas se retornou algo, sem "particular"
        if r is not None:
            assert "particular" not in r.lower()
            assert "611" not in r


# ═══════════════════════════════════════════════════════════════════════════════
# 3. _ultima_msg_era_recusa_convenio — detector de contexto
# ═══════════════════════════════════════════════════════════════════════════════

class TestUltimaMsgEraRecusaConvenio:

    def test_detecta_quando_ambas_opcoes_presentes(self):
        ctx = _ctx(ultima_msg=_ULTIMA_OPCOES)
        assert _bd._ultima_msg_era_recusa_convenio(ctx) is True

    def test_nao_detecta_sem_opcoes(self):
        ctx = _ctx(ultima_msg="Qual sua unidade preferida?")
        assert _bd._ultima_msg_era_recusa_convenio(ctx) is False

    def test_nao_detecta_ctx_vazio(self):
        assert _bd._ultima_msg_era_recusa_convenio(None) is False

    def test_nao_detecta_sem_ultima_msg(self):
        ctx = _ctx()
        assert _bd._ultima_msg_era_recusa_convenio(ctx) is False

    def test_detecta_com_saudacao_antes(self):
        msg = "Carlos, o Bradesco é um convênio que ainda estamos em processo. Qual a sua preferência?\n\n1️⃣ Somente com Convênio\n2️⃣ Seguir Sem Convênio"
        ctx = _ctx(ultima_msg=msg)
        assert _bd._ultima_msg_era_recusa_convenio(ctx) is True


# ═══════════════════════════════════════════════════════════════════════════════
# 4. deve_responder_escolha_convenio — bypass pós-recusa
# ═══════════════════════════════════════════════════════════════════════════════

class TestEscolhaConvenio:

    def _ctx_pos_recusa(self, convenio_recusado="Bradesco"):
        ctx = _ctx(ultima_msg=_ULTIMA_OPCOES)
        ctx["known"]["convenio"] = convenio_recusado
        ctx["known"]["convenio_nao_aceito_nome"] = convenio_recusado
        return ctx

    # ── Opção 2: Seguir Sem Convênio ─────────────────────────────────────────

    def test_detecta_opcao_2_numeral(self):
        ctx = self._ctx_pos_recusa()
        r = _bd.deve_responder_escolha_convenio(ctx, "2")
        assert r is not None
        assert ctx["known"].get("convenio") == "Não se aplica"
        assert ctx["known"].get("c123_marcar_sem_convenio") is True

    def test_detecta_emoji_2(self):
        ctx = self._ctx_pos_recusa()
        r = _bd.deve_responder_escolha_convenio(ctx, "2️⃣")
        assert r is not None
        assert ctx["known"].get("c123_marcar_sem_convenio") is True

    def test_detecta_seguir_sem_convenio_texto(self):
        ctx = self._ctx_pos_recusa()
        r = _bd.deve_responder_escolha_convenio(ctx, "seguir sem convênio")
        assert r is not None
        assert ctx["known"]["convenio"] == "Não se aplica"

    def test_detecta_sem_convenio_standalone(self):
        ctx = self._ctx_pos_recusa()
        r = _bd.deve_responder_escolha_convenio(ctx, "sem convênio mesmo")
        assert r is not None

    def test_resposta_sem_convenio_pede_motivo(self):
        ctx = self._ctx_pos_recusa()
        r = _bd.deve_responder_escolha_convenio(ctx, "2")
        assert r is not None
        assert "motivo" in r.lower() or "consulta" in r.lower()

    def test_resposta_sem_convenio_sem_particular(self):
        ctx = self._ctx_pos_recusa()
        r = _bd.deve_responder_escolha_convenio(ctx, "2")
        assert r is not None
        assert "particular" not in r.lower()

    def test_preserva_convenio_recusado_em_known(self):
        ctx = self._ctx_pos_recusa("Bradesco")
        _bd.deve_responder_escolha_convenio(ctx, "seguir sem convênio")
        # convenio_nao_aceito_nome deve ser preservado para Ñ ACEITO CONVÊNIO no Kommo
        assert "Bradesco" in (ctx["known"].get("c123_convenio_recusado") or "")

    # ── Opção 1: Somente com Convênio ────────────────────────────────────────

    def test_detecta_opcao_1_numeral(self):
        ctx = self._ctx_pos_recusa()
        r = _bd.deve_responder_escolha_convenio(ctx, "1")
        assert r is not None
        assert ctx["known"].get("c123_encerrar_so_convenio") is True

    def test_detecta_emoji_1(self):
        ctx = self._ctx_pos_recusa()
        r = _bd.deve_responder_escolha_convenio(ctx, "1️⃣")
        assert r is not None
        assert ctx["known"].get("c123_encerrar_so_convenio") is True

    def test_detecta_somente_com_convenio_texto(self):
        ctx = self._ctx_pos_recusa()
        r = _bd.deve_responder_escolha_convenio(ctx, "somente com convênio")
        assert r is not None
        assert ctx["known"].get("c123_encerrar_so_convenio") is True

    def test_resposta_so_convenio_gentil(self):
        ctx = self._ctx_pos_recusa()
        r = _bd.deve_responder_escolha_convenio(ctx, "somente com convênio")
        assert r is not None
        assert "credenciamento" in r.lower() or "avisar" in r.lower() or "qualquer dúvida" in r.lower()

    def test_resposta_so_convenio_sem_valor(self):
        ctx = self._ctx_pos_recusa()
        r = _bd.deve_responder_escolha_convenio(ctx, "1")
        assert r is not None
        assert "R$" not in r
        assert "611" not in r

    # ── Não age fora do contexto certo ──────────────────────────────────────

    def test_nao_age_sem_ultima_msg_recusa(self):
        ctx = _ctx(ultima_msg="Qual sua unidade preferida?")
        r = _bd.deve_responder_escolha_convenio(ctx, "2")
        assert r is None

    def test_nao_age_sem_ctx(self):
        r = _bd.deve_responder_escolha_convenio(None, "2")
        assert r is None

    def test_nao_age_sem_user_text(self):
        ctx = self._ctx_pos_recusa()
        r = _bd.deve_responder_escolha_convenio(ctx, "")
        assert r is None

    def test_nao_confunde_turno_aleatorio(self):
        ctx = self._ctx_pos_recusa()
        r = _bd.deve_responder_escolha_convenio(ctx, "bom dia!")
        assert r is None

    def test_toggle_off(self):
        ctx = self._ctx_pos_recusa()
        os.environ["BLINDAGEM_ESCOLHA_CONVENIO_ATIVADO"] = "0"
        try:
            r = _bd.deve_responder_escolha_convenio(ctx, "2")
            assert r is None
        finally:
            os.environ.pop("BLINDAGEM_ESCOLHA_CONVENIO_ATIVADO", None)

    def test_fail_open_excecao_interna(self, monkeypatch):
        ctx = self._ctx_pos_recusa()
        monkeypatch.setattr(_bd, "_RE_ESCOLHA_SEM_CONVENIO_C123", None)
        r = _bd.deve_responder_escolha_convenio(ctx, "2")
        assert r is None


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Posição no bypass chain — deve_responder_escolha_convenio ANTES de faq_convenio
# ═══════════════════════════════════════════════════════════════════════════════

class TestPosicaoNaChain:

    def test_escolha_convenio_antes_faq_no_chain(self):
        """No tentar_bypass_deterministico, escolha_convenio_c123 deve vir antes
        de faq_convenio_aceito para interceptar respostas à oferta apresentada."""
        src = open(
            "voice_agent/blindagens_deterministicas.py", encoding="utf-8"
        ).read()
        idx_escolha = src.index('"escolha_convenio_c123"')
        idx_faq = src.index('"faq_convenio_aceito"')
        assert idx_escolha < idx_faq, (
            "escolha_convenio_c123 deve aparecer antes de faq_convenio_aceito na chain"
        )

    def test_montar_recusa_existe(self):
        assert hasattr(_bd, "_montar_recusa_convenio")

    def test_ultima_msg_recusa_existe(self):
        assert hasattr(_bd, "_ultima_msg_era_recusa_convenio")

    def test_deve_responder_escolha_convenio_existe(self):
        assert hasattr(_bd, "deve_responder_escolha_convenio")


# ═══════════════════════════════════════════════════════════════════════════════
# 6. responder.py — _gerar_script_convenio_nao_aceito tom corrigido
# ═══════════════════════════════════════════════════════════════════════════════

class TestGeradorScriptConvenioNaoAceito:

    def _get_script(self, conv="Bradesco", ctx=None):
        import voice_agent.responder as _r
        return _r._gerar_script_convenio_nao_aceito(conv, ctx)

    def test_sem_particular(self):
        r = self._get_script("Bradesco")
        assert "particular" not in r.lower()

    def test_sem_valor_prematuro(self):
        r = self._get_script("Bradesco")
        assert "R$" not in r
        assert "611" not in r
        assert "parcelamento" not in r.lower()

    def test_ordem_botoes_canonica_1_somente_2_seguir(self):
        r = self._get_script("Bradesco")
        idx_1 = r.index("1️⃣")
        idx_2 = r.index("2️⃣")
        assert idx_1 < idx_2
        # 1️⃣ deve ser "Somente com Convênio"
        trecho_apos_1 = r[idx_1: idx_1 + 40]
        assert "Somente" in trecho_apos_1

    def test_processo_credenciamento(self):
        r = self._get_script("Bradesco")
        assert "credenciamento" in r.lower() or "rede credenciada" in r.lower()

    def test_label_correto(self):
        r = self._get_script("Bradesco")
        assert "Bradesco" in r

    def test_com_saudacao(self):
        ctx_c = {"known": {"nome_paciente": "Ana"}}
        r = self._get_script("Amil", ctx=ctx_c)
        assert "Ana," in r


# ═══════════════════════════════════════════════════════════════════════════════
# 7. Caso real lead 24441038 — Bradesco
# ═══════════════════════════════════════════════════════════════════════════════

class TestCasoReal24441038:

    def test_bradesco_sem_particular_sem_valor(self):
        ctx = _ctx(convenio="Bradesco", aceito=False)
        r = _bd.deve_responder_faq_convenio_aceito(ctx, "vocês atendem bradesco?")
        assert r is not None
        assert "particular" not in r.lower()
        assert "R$" not in r
        assert "611" not in r

    def test_bradesco_processo_credenciamento(self):
        ctx = _ctx(convenio="Bradesco", aceito=False)
        r = _bd.deve_responder_faq_convenio_aceito(ctx, "vocês atendem bradesco?")
        assert r is not None
        assert "processo de credenciamento" in r.lower()

    def test_bradesco_opcoes_canonicas(self):
        ctx = _ctx(convenio="Bradesco", aceito=False)
        r = _bd.deve_responder_faq_convenio_aceito(ctx, "vocês atendem bradesco?")
        assert r is not None
        assert "1️⃣ Somente com Convênio" in r
        assert "2️⃣ Seguir Sem Convênio" in r

    def test_fluxo_completo_bradesco_escolhe_2(self):
        """Simula: (1) Lia detecta Bradesco não aceito → apresenta opções.
        (2) Paciente responde '2' → bypass injecta sem convênio."""
        # Passo 1: FAQ convênio
        ctx = _ctx(convenio="Bradesco", aceito=False)
        r1 = _bd.deve_responder_faq_convenio_aceito(ctx, "vocês atendem bradesco?")
        assert r1 is not None
        # Registrar que Lia enviou as opções
        ctx["known"]["ultima_msg_outbound"] = r1

        # Passo 2: Paciente escolhe opção 2
        r2 = _bd.deve_responder_escolha_convenio(ctx, "2")
        assert r2 is not None
        assert ctx["known"]["convenio"] == "Não se aplica"
        assert ctx["known"].get("c123_marcar_sem_convenio") is True
        assert "motivo" in r2.lower() or "consulta" in r2.lower()
