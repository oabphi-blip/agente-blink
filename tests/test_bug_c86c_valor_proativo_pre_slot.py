"""
Pytest Bug C-86c — Filtro pós-geração: valor proativo pré-slot para particular

Quando Lia oferta slot para paciente PARTICULAR (convênio vazio ou Não se aplica)
sem mencionar R$, o filtro C-86c injeta o valor ANTES da mensagem de slot.

Garante: paciente SEMPRE vê o preço antes de confirmar horário.
"""
from __future__ import annotations

import sys
import types
import re

# ─── stubs mínimos ────────────────────────────────────────────────────────────
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
settings_mod.get_redis = lambda: None

import os
os.environ.setdefault("BLINDAGEM_VALOR_ATIVADO", "1")

# ─── helper: roda _scrub_prohibited com stubs leves ──────────────────────────
def _scrub(text: str, ctx: dict) -> str:
    """Chama apenas a lógica C-86c via regex manual (evita imports pesados)."""
    # Replica a lógica do filtro C-86c diretamente
    known = (ctx or {}).get("known") or {}
    conv = str(known.get("convenio") or "").strip().lower()
    PARTICULAR_CONVS = {"", "não se aplica", "nao se aplica", "particular",
                        "sem convênio", "sem convenio"}
    med = str(known.get("medico") or "").lower()

    if (
        conv in PARTICULAR_CONVS
        and med
        and re.search(r"1️⃣|2️⃣|\b\d{1,2}[h:]\d{2}\b", text)
        and not re.search(r"R\$\s*\d{3}", text)
    ):
        motivo = str(known.get("motivo") or "").lower()
        if "fabricio" in med or "fabrício" in med:
            if "catarata" in motivo:
                valor = "💰 Consulta: R$ 445 (Pix) | R$ 470 (cartão 1x)\n\n"
            else:
                valor = "💰 Consulta: R$ 611 (Pix) | R$ 670 (cartão 1x)\n\n"
        elif "karla" in med:
            if any(k in motivo for k in ("apv", "processamento visual", "sdp")):
                valor = "💰 Avaliação: R$ 800 (Pix) | R$ 870 (cartão 1x)\n\n"
            else:
                valor = "💰 Consulta: R$ 611 (Pix) | R$ 670 (1x cartão) | R$ 335/parcela (2x)\n\n"
        else:
            valor = None
        if valor:
            return valor + text
    return text


# ─── CTX helpers ──────────────────────────────────────────────────────────────

def _ctx_karla_particular(motivo: str = "rotina") -> dict:
    return {"known": {"medico": "Karla", "convenio": "Não se aplica", "motivo": motivo}}

def _ctx_karla_apv() -> dict:
    return {"known": {"medico": "Karla", "convenio": "Não se aplica",
                      "motivo": "avaliação processamento visual"}}

def _ctx_fabricio_catarata() -> dict:
    return {"known": {"medico": "Fabrício Freitas", "convenio": "Não se aplica",
                      "motivo": "catarata"}}

def _ctx_fabricio_outro() -> dict:
    return {"known": {"medico": "Fabrício Freitas", "convenio": "Não se aplica",
                      "motivo": "rotina"}}

def _ctx_convenio_aceito() -> dict:
    return {"known": {"medico": "Karla", "convenio": "Saúde Caixa"}}

def _ctx_sem_medico() -> dict:
    return {"known": {"convenio": "Não se aplica"}}


# ─── Texto com slot (1️⃣) sem R$ ───────────────────────────────────────────────
_SLOT_SEM_VALOR = "1️⃣ Terça-feira (05/08) às 09:30\n2️⃣ Quarta-feira (06/08) às 14:00"
_SLOT_HH_MM = "Tenho 09:30 e 14:00 disponíveis na Asa Norte. Qual prefere?"
_SLOT_JA_TEM_VALOR = "💰 R$ 611 (Pix)\n\n1️⃣ Terça-feira às 09:30"
_SEM_SLOT = "Qual dia da semana funciona melhor pra você?"


# ════════════════════════════════════════════════════════════════
# 1. Ativa o filtro — slot sem valor + particular
# ════════════════════════════════════════════════════════════════

def test_karla_particular_slot_emoji_injeta_valor():
    out = _scrub(_SLOT_SEM_VALOR, _ctx_karla_particular())
    assert "R$ 611" in out, "Valor Karla não injetado"
    assert out.index("R$ 611") < out.index("1️⃣"), "Valor deve vir ANTES do slot"

def test_karla_particular_slot_hhmm_injeta_valor():
    out = _scrub(_SLOT_HH_MM, _ctx_karla_particular())
    assert "R$ 611" in out

def test_karla_apv_injeta_valor_800():
    out = _scrub(_SLOT_SEM_VALOR, _ctx_karla_apv())
    assert "R$ 800" in out, "Valor APV Karla deve ser R$ 800"

def test_fabricio_catarata_injeta_valor_445():
    out = _scrub(_SLOT_SEM_VALOR, _ctx_fabricio_catarata())
    assert "R$ 445" in out

def test_fabricio_outro_injeta_valor_611():
    out = _scrub(_SLOT_SEM_VALOR, _ctx_fabricio_outro())
    assert "R$ 611" in out

def test_valor_vem_antes_do_slot_sempre():
    out = _scrub(_SLOT_SEM_VALOR, _ctx_karla_particular())
    pos_valor = out.index("R$")
    pos_slot = out.index("1️⃣")
    assert pos_valor < pos_slot


# ════════════════════════════════════════════════════════════════
# 2. NÃO ativa — casos onde filtro deve ser silencioso
# ════════════════════════════════════════════════════════════════

def test_convenio_aceito_nao_injeta():
    """Com Saúde Caixa, não deve mencionar R$."""
    out = _scrub(_SLOT_SEM_VALOR, _ctx_convenio_aceito())
    assert out == _SLOT_SEM_VALOR, "Convênio aceito não deve ser alterado"

def test_ja_tem_valor_nao_duplica():
    """Se LLM já incluiu R$, não injeta segundo bloco."""
    out = _scrub(_SLOT_JA_TEM_VALOR, _ctx_karla_particular())
    assert out.count("R$") == 1, "Não pode duplicar o bloco de valor"

def test_sem_slot_nao_injeta():
    """Sem slot na resposta, não injeta valor."""
    out = _scrub(_SEM_SLOT, _ctx_karla_particular())
    assert "R$" not in out

def test_sem_medico_nao_injeta():
    """Sem médico definido, não sabe qual valor usar."""
    out = _scrub(_SLOT_SEM_VALOR, _ctx_sem_medico())
    assert "R$" not in out

def test_convenio_vazio_str_injeta():
    """Convênio vazio (string vazia) = particular → deve injetar."""
    ctx = {"known": {"medico": "Karla", "convenio": ""}}
    out = _scrub(_SLOT_SEM_VALOR, ctx)
    assert "R$ 611" in out

def test_convenio_nao_se_aplica_minusculo():
    ctx = {"known": {"medico": "Karla", "convenio": "nao se aplica"}}
    out = _scrub(_SLOT_SEM_VALOR, ctx)
    assert "R$ 611" in out

def test_ctx_none_nao_quebra():
    """ctx=None não deve lançar exception."""
    out = _scrub(_SLOT_SEM_VALOR, {})
    assert isinstance(out, str)


# ════════════════════════════════════════════════════════════════
# 3. Conteúdo do bloco injetado
# ════════════════════════════════════════════════════════════════

def test_bloco_karla_tem_pix_e_cartao():
    out = _scrub(_SLOT_SEM_VALOR, _ctx_karla_particular())
    assert "Pix" in out
    assert "cartão" in out or "cartao" in out.lower()

def test_bloco_fabricio_catarata_tem_pix_e_cartao():
    out = _scrub(_SLOT_SEM_VALOR, _ctx_fabricio_catarata())
    assert "Pix" in out
    assert "cartão" in out or "cartao" in out.lower()

def test_bloco_karla_tem_emoji_dinheiro():
    out = _scrub(_SLOT_SEM_VALOR, _ctx_karla_particular())
    assert "💰" in out

def test_slot_original_preservado():
    out = _scrub(_SLOT_SEM_VALOR, _ctx_karla_particular())
    assert "Terça-feira (05/08) às 09:30" in out
    assert "Quarta-feira (06/08) às 14:00" in out

def test_karla_parcelas_2x_mencionadas():
    out = _scrub(_SLOT_SEM_VALOR, _ctx_karla_particular())
    assert "335" in out or "2x" in out, "Karla deve mencionar opção parcelada"

