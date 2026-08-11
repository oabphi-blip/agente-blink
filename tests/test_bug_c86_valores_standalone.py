"""
Pytest Bug C-86 / C-86b — FAQ valor: regex ampliado + nunca ignorar pergunta de preço

C-86  (04/08/2026): "Valores" standalone não era capturado pelo bypass.
C-86b (05/08/2026): sinonimos amplos + sem médico → tabela geral (nunca None).

Lead 24413976 Cecília/Cristina.
"""
import sys, types

# --- stubs mínimos ---
for mod in [
    "redis", "anthropic", "httpx", "pydantic", "pydantic_settings",
    "zep_cloud", "zep_cloud.client", "zep_cloud.types",
    "openai", "openai.embeddings",
    "voice_agent.medware", "voice_agent.kommo", "voice_agent.zep_adapter",
    "voice_agent.store", "voice_agent.settings",
]:
    if mod not in sys.modules:
        sys.modules[mod] = types.ModuleType(mod)

settings_mod = sys.modules["voice_agent.settings"]
class _S:
    webhook_secret = "x"
    anthropic_api_key = "x"
    kommo_base_url = "x"
    kommo_api_token = "x"
    redis_url = "redis://localhost"
settings_mod.settings = _S()

import os
os.environ.setdefault("BLINDAGEM_VALOR_ATIVADO", "1")

from voice_agent.blindagens_deterministicas import (
    _PADROES_PERGUNTA_VALOR,
    _inferir_medico_por_motivo,
    _resposta_tabela_geral_valores,
    deve_responder_valor,
)


# ════════════════════════════════════════════════════════════════
# 1. Regex — padrões originais continuam funcionando
# ════════════════════════════════════════════════════════════════

def test_captura_quanto_custa():
    assert _PADROES_PERGUNTA_VALOR.search("quanto custa a consulta?")

def test_captura_qual_o_valor():
    assert _PADROES_PERGUNTA_VALOR.search("qual o valor da consulta?")

def test_captura_quanto_vou_pagar():
    assert _PADROES_PERGUNTA_VALOR.search("quanto vou pagar?")

def test_captura_quanto_pago():
    assert _PADROES_PERGUNTA_VALOR.search("quanto pago?")

def test_captura_tem_desconto():
    assert _PADROES_PERGUNTA_VALOR.search("tem desconto?")


# ════════════════════════════════════════════════════════════════
# 2. Regex — Bug C-86: standalone que não era capturado
# ════════════════════════════════════════════════════════════════

def test_captura_valores_standalone():
    """'Valores' sozinho — era o bug C-86."""
    assert _PADROES_PERGUNTA_VALOR.search("Valores"), "Bug C-86: 'Valores' não capturado"

def test_captura_valor_minusculo():
    assert _PADROES_PERGUNTA_VALOR.search("valor"), "'valor' deve casar"

def test_captura_valores_maiusculo():
    assert _PADROES_PERGUNTA_VALOR.search("VALORES"), "case insensitive"

def test_captura_preco_standalone():
    assert _PADROES_PERGUNTA_VALOR.search("Preço")

def test_captura_preco_sem_cedilha():
    assert _PADROES_PERGUNTA_VALOR.search("Preco")

def test_captura_precos_plural():
    assert _PADROES_PERGUNTA_VALOR.search("Preços")

def test_captura_pagamento():
    assert _PADROES_PERGUNTA_VALOR.search("formas de pagamento")

def test_captura_quero_saber_valores():
    """Terceira mensagem do paciente no caso real C-86."""
    assert _PADROES_PERGUNTA_VALOR.search("Quero saber valores")


# ════════════════════════════════════════════════════════════════
# 3. Regex — Bug C-86b: sinônimos PT-BR informal
# ════════════════════════════════════════════════════════════════

def test_captura_custo():
    assert _PADROES_PERGUNTA_VALOR.search("custo"), "'custo' standalone"

def test_captura_custos():
    assert _PADROES_PERGUNTA_VALOR.search("quais os custos?")

def test_captura_investimento():
    assert _PADROES_PERGUNTA_VALOR.search("qual o investimento?")

def test_captura_cobram():
    assert _PADROES_PERGUNTA_VALOR.search("quanto cobram?")

def test_captura_cobra():
    assert _PADROES_PERGUNTA_VALOR.search("quanto cobra?")

def test_captura_tabela():
    assert _PADROES_PERGUNTA_VALOR.search("Tabela"), "'Tabela' standalone"

def test_captura_qual_tabela():
    assert _PADROES_PERGUNTA_VALOR.search("qual a tabela de preços?")

def test_captura_promocao():
    assert _PADROES_PERGUNTA_VALOR.search("tem promoção?")

def test_captura_promocao_sem_acento():
    assert _PADROES_PERGUNTA_VALOR.search("tem promocao?")

def test_captura_parcelado():
    assert _PADROES_PERGUNTA_VALOR.search("parcelado?")

def test_captura_parcelas():
    assert _PADROES_PERGUNTA_VALOR.search("quantas parcelas?")

def test_captura_a_vista():
    assert _PADROES_PERGUNTA_VALOR.search("à vista tem desconto?")

def test_captura_a_vista_sem_acento():
    assert _PADROES_PERGUNTA_VALOR.search("a vista")

def test_captura_pix_standalone():
    assert _PADROES_PERGUNTA_VALOR.search("Pix"), "'Pix' standalone"

def test_captura_tem_pix():
    assert _PADROES_PERGUNTA_VALOR.search("tem pix?")

def test_captura_cartao():
    assert _PADROES_PERGUNTA_VALOR.search("aceita cartão?")

def test_captura_cartao_sem_acento():
    assert _PADROES_PERGUNTA_VALOR.search("cartao de credito")

def test_captura_boleto():
    assert _PADROES_PERGUNTA_VALOR.search("tem boleto?")

def test_captura_gratuito():
    assert _PADROES_PERGUNTA_VALOR.search("é gratuito?")

def test_captura_gratis():
    assert _PADROES_PERGUNTA_VALOR.search("é grátis?")

def test_captura_gratis_sem_acento():
    assert _PADROES_PERGUNTA_VALOR.search("e gratis?")

def test_captura_barato():
    assert _PADROES_PERGUNTA_VALOR.search("é barato?")

def test_captura_caro():
    assert _PADROES_PERGUNTA_VALOR.search("é caro?")

def test_captura_forma_de_pagamento():
    assert _PADROES_PERGUNTA_VALOR.search("forma de pagamento")

def test_captura_formas_de_pagamento():
    assert _PADROES_PERGUNTA_VALOR.search("quais as formas de pagamento?")

def test_captura_meio_de_pagamento():
    assert _PADROES_PERGUNTA_VALOR.search("qual o meio de pagamento?")

def test_captura_aceita_todas_bandeiras():
    assert _PADROES_PERGUNTA_VALOR.search("aceita todas as bandeiras?")

def test_captura_me_passa_o_valor():
    assert _PADROES_PERGUNTA_VALOR.search("me passa o valor")


# ════════════════════════════════════════════════════════════════
# 4. _inferir_medico_por_motivo
# ════════════════════════════════════════════════════════════════

def test_inferir_estrabismo_karla():
    assert _inferir_medico_por_motivo({"motivo": "estrabismo"}) == "karla"

def test_inferir_pediatria_karla():
    assert _inferir_medico_por_motivo({"motivo": "oftalmopediatria"}) == "karla"

def test_inferir_crianca_karla():
    assert _inferir_medico_por_motivo({"motivo": "consulta para meu filho"}) == "karla"

def test_inferir_apv_karla():
    assert _inferir_medico_por_motivo({"motivo": "apv"}) == "karla"

def test_inferir_rotina_karla():
    assert _inferir_medico_por_motivo({"motivo": "rotina"}) == "karla"

def test_inferir_oculos_karla():
    assert _inferir_medico_por_motivo({"motivo": "óculos"}) == "karla"

def test_inferir_catarata_fabricio():
    assert _inferir_medico_por_motivo({"motivo": "catarata"}) == "fabricio"

def test_inferir_cornea_fabricio():
    assert _inferir_medico_por_motivo({"motivo": "córnea"}) == "fabricio"

def test_inferir_pterigio_fabricio():
    assert _inferir_medico_por_motivo({"motivo": "pterígio"}) == "fabricio"

def test_inferir_cirurgia_fabricio():
    assert _inferir_medico_por_motivo({"motivo": "cirurgia ocular"}) == "fabricio"

def test_inferir_idade_menor_karla():
    assert _inferir_medico_por_motivo({"motivo": "", "idade": 10}) == "karla"

def test_inferir_idade_50_fabricio():
    assert _inferir_medico_por_motivo({"motivo": "", "idade": 55}) == "fabricio"

def test_inferir_sem_info_retorna_vazio():
    assert _inferir_medico_por_motivo({}) == ""

def test_inferir_motivo_vazio_retorna_vazio():
    assert _inferir_medico_por_motivo({"motivo": ""}) == ""


# ════════════════════════════════════════════════════════════════
# 5. _resposta_tabela_geral_valores
# ════════════════════════════════════════════════════════════════

def test_tabela_geral_tem_dois_medicos():
    tabela = _resposta_tabela_geral_valores("")
    assert "Karla" in tabela
    assert "Freitas" in tabela or "Fabrício" in tabela

def test_tabela_geral_tem_valores():
    tabela = _resposta_tabela_geral_valores("")
    assert "R$ 611" in tabela
    assert "R$ 445" in tabela

def test_tabela_geral_com_nome():
    tabela = _resposta_tabela_geral_valores("Cristina")
    assert "Cristina" in tabela

def test_tabela_geral_nunca_none():
    assert _resposta_tabela_geral_valores("") is not None
    assert _resposta_tabela_geral_valores("X") is not None


# ════════════════════════════════════════════════════════════════
# 6. deve_responder_valor — comportamento completo
# ════════════════════════════════════════════════════════════════

def _ctx_karla_particular(nome="Cristina"):
    return {"known": {"medico": "Karla", "convenio": "Não se aplica", "nome": nome}}

def _ctx_karla_convenio():
    return {"known": {"medico": "Karla", "convenio": "Saúde Caixa"}}

def _ctx_fabricio_catarata():
    return {"known": {"medico": "Fabrício Freitas", "motivo": "catarata",
                      "convenio": "Não se aplica"}}

def _ctx_sem_medico_estrabismo():
    return {"known": {"motivo": "estrabismo", "convenio": "Não se aplica"}}

def _ctx_sem_medico_sem_motivo():
    return {"known": {"convenio": "Não se aplica"}}


# ── 6a. Com médico definido ───────────────────────────────────

def test_standalone_valores_com_karla_responde():
    """Caso C-86 exato: 'Valores' + médico definido → resposta canônica."""
    resp = deve_responder_valor(_ctx_karla_particular(), "Valores")
    assert resp is not None, "deve_responder_valor retornou None para 'Valores'"
    assert "R$ 611" in resp or "R$ 800" in resp

def test_quero_saber_valores_com_karla():
    resp = deve_responder_valor(_ctx_karla_particular(), "Quero saber valores")
    assert resp is not None
    assert "R$" in resp

def test_convenio_aceito_menciona_convenio():
    resp = deve_responder_valor(_ctx_karla_convenio(), "Valores")
    assert resp is not None
    assert "Saúde Caixa" in resp or "saúde caixa" in resp.lower()

def test_fabricio_catarata_valor_correto():
    resp = deve_responder_valor(_ctx_fabricio_catarata(), "quanto custa?")
    assert resp is not None
    assert "R$ 445" in resp  # valor catarata Fabrício

def test_preco_com_karla():
    resp = deve_responder_valor(_ctx_karla_particular(), "Preço")
    assert resp is not None
    assert "R$" in resp

def test_pix_com_karla_responde():
    resp = deve_responder_valor(_ctx_karla_particular(), "pix?")
    assert resp is not None

def test_cartao_com_karla_responde():
    resp = deve_responder_valor(_ctx_karla_particular(), "aceita cartão?")
    assert resp is not None

def test_custo_com_karla_responde():
    resp = deve_responder_valor(_ctx_karla_particular(), "custo")
    assert resp is not None
    assert "R$" in resp

# ── 6b. Sem médico → inferência por motivo ───────────────────

def test_sem_medico_estrabismo_infere_karla():
    """Sem médico + motivo=estrabismo → infere Karla → responde com valor Karla."""
    resp = deve_responder_valor(_ctx_sem_medico_estrabismo(), "Valores")
    assert resp is not None, "Com motivo inferível não deve retornar None"
    assert "R$ 611" in resp or "Karla" in resp

def test_sem_medico_catarata_infere_fabricio():
    ctx = {"known": {"motivo": "catarata", "convenio": "Não se aplica"}}
    resp = deve_responder_valor(ctx, "qual o valor?")
    assert resp is not None
    assert "R$ 445" in resp or "Fabrício" in resp or "Fabricio" in resp

def test_sem_medico_bebe_infere_karla():
    ctx = {"known": {"motivo": "consulta para meu bebê", "convenio": "Não se aplica"}}
    resp = deve_responder_valor(ctx, "Valores")
    assert resp is not None
    assert "R$ 611" in resp or "Karla" in resp

# ── 6c. Sem médico sem motivo → tabela geral (NUNCA None) ────

def test_sem_medico_sem_motivo_retorna_tabela_geral():
    """Bug C-86b principal: sem ctx → retorna tabela geral, NUNCA None."""
    resp = deve_responder_valor(_ctx_sem_medico_sem_motivo(), "Valores")
    assert resp is not None, "Sem médico/motivo deve retornar tabela geral, não None"
    assert "Karla" in resp
    assert "R$ 611" in resp

def test_ctx_none_retorna_tabela_geral():
    """ctx=None → tabela geral (NUNCA None)."""
    resp = deve_responder_valor(None, "Valores")
    assert resp is not None, "ctx=None deve retornar tabela geral"
    assert "R$" in resp

def test_ctx_vazio_retorna_tabela_geral():
    resp = deve_responder_valor({}, "Preço")
    assert resp is not None
    assert "R$" in resp

# ── 6d. Toggle desligado ─────────────────────────────────────

def test_toggle_off_retorna_none(monkeypatch):
    monkeypatch.setenv("BLINDAGEM_VALOR_ATIVADO", "0")
    resp = deve_responder_valor(_ctx_karla_particular(), "Valores")
    assert resp is None, "Toggle OFF deve retornar None"
    monkeypatch.setenv("BLINDAGEM_VALOR_ATIVADO", "1")

# ── 6e. Pergunta não é sobre valor → retorna None ────────────

def test_nao_dispara_texto_irrelevante():
    resp = deve_responder_valor(_ctx_karla_particular(), "Boa tarde, quero agendar")
    assert resp is None, "Texto sem pergunta de valor não deve disparar bypass"

def test_nao_dispara_nome_paciente():
    resp = deve_responder_valor(_ctx_karla_particular(), "Meu nome é Ana")
    assert resp is None

def test_nao_dispara_string_vazia():
    resp = deve_responder_valor(_ctx_karla_particular(), "")
    assert resp is None
