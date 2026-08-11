"""
Pytest — Bug C-110: Validação CPF por dígitos verificadores.

Cobre:
  - CPFs matematicamente válidos (aceitos)
  - CPFs com dígito verificador errado (rejeitados)
  - Sequências homogêneas (000...0, 111...1, etc.) → inválido
  - Extração do texto: com pontuação, sem, espaços
  - Nenhum CPF no texto → None (não interfere)
  - ctx=None → None (fail-open)
  - Toggle OFF → None
  - enriquecimento_ctx step 16: injeta cpf_validado em known
  - Formatação XXX.XXX.XXX-XX
  - CPF já válido em known → step 16 não sobrescreve
  - CPF inválido → known["cpf_invalido_detectado"]=True
"""
from __future__ import annotations

import os
import sys

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _importar(ativado="1"):
    env = os.environ.get("VALIDACAO_CPF_ATIVADO")
    os.environ["VALIDACAO_CPF_ATIVADO"] = ativado
    for k in list(sys.modules):
        if "validacao_cpf" in k:
            del sys.modules[k]
    try:
        from voice_agent import validacao_cpf as m
        return m
    finally:
        if env is None:
            os.environ.pop("VALIDACAO_CPF_ATIVADO", None)
        else:
            os.environ["VALIDACAO_CPF_ATIVADO"] = env


def _ctx(lead_id=1001):
    return {"lead_id": lead_id, "known": {}}


# ---------------------------------------------------------------------------
# CPFs de teste (matematicamente válidos — gerados com algoritmo oficial)
# ---------------------------------------------------------------------------
# CPFs válidos reais de teste (usados em documentação oficial brasileira):
_CPF_VALIDOS = [
    "52998224725",   # 529.982.247-25
    "11144477735",   # 111.444.777-35
    "00000000191",   # 000.000.001-91
    "12345678909",   # 123.456.789-09
]

_CPF_INVALIDOS = [
    "12345678900",   # dígito errado
    "11111111111",   # sequência homogênea
    "00000000000",   # zeros
    "99999999999",   # noves
    "52998224726",   # último dígito errado
    "52998224715",   # penúltimo errado
]


# ---------------------------------------------------------------------------
# 1. cpf_matematicamente_valido
# ---------------------------------------------------------------------------

class TestCpfMatematicoValido:
    @pytest.mark.parametrize("cpf", _CPF_VALIDOS)
    def test_cpf_valido_aceito(self, cpf):
        from voice_agent.validacao_cpf import cpf_matematicamente_valido
        assert cpf_matematicamente_valido(cpf) is True

    @pytest.mark.parametrize("cpf", _CPF_INVALIDOS)
    def test_cpf_invalido_rejeitado(self, cpf):
        from voice_agent.validacao_cpf import cpf_matematicamente_valido
        assert cpf_matematicamente_valido(cpf) is False

    def test_tamanho_errado(self):
        from voice_agent.validacao_cpf import cpf_matematicamente_valido
        assert cpf_matematicamente_valido("1234567890") is False   # 10 dígitos
        assert cpf_matematicamente_valido("123456789012") is False  # 12 dígitos

    def test_com_letras(self):
        from voice_agent.validacao_cpf import cpf_matematicamente_valido
        assert cpf_matematicamente_valido("1234567890a") is False

    @pytest.mark.parametrize("d", range(10))
    def test_sequencia_homogenea(self, d):
        from voice_agent.validacao_cpf import cpf_matematicamente_valido
        assert cpf_matematicamente_valido(str(d) * 11) is False


# ---------------------------------------------------------------------------
# 2. extrair_cpf_do_texto
# ---------------------------------------------------------------------------

class TestExtrairCpf:
    def test_com_pontuacao(self):
        from voice_agent.validacao_cpf import extrair_cpf_do_texto
        assert extrair_cpf_do_texto("meu cpf é 529.982.247-25") == "52998224725"

    def test_sem_pontuacao(self):
        from voice_agent.validacao_cpf import extrair_cpf_do_texto
        assert extrair_cpf_do_texto("52998224725") == "52998224725"

    def test_com_espacos(self):
        from voice_agent.validacao_cpf import extrair_cpf_do_texto
        assert extrair_cpf_do_texto("529 982 247 25") == "52998224725"

    def test_sem_cpf_no_texto(self):
        from voice_agent.validacao_cpf import extrair_cpf_do_texto
        assert extrair_cpf_do_texto("olá, quero agendar") is None

    def test_texto_vazio(self):
        from voice_agent.validacao_cpf import extrair_cpf_do_texto
        assert extrair_cpf_do_texto("") is None

    def test_none(self):
        from voice_agent.validacao_cpf import extrair_cpf_do_texto
        assert extrair_cpf_do_texto(None) is None

    def test_texto_com_cpf_pontuado_extraido(self):
        from voice_agent.validacao_cpf import extrair_cpf_do_texto
        # CPF com pontuação — regex captura claramente
        result = extrair_cpf_do_texto("meu cpf: 529.982.247-25, obrigado")
        assert result == "52998224725"


# ---------------------------------------------------------------------------
# 3. formatar_cpf
# ---------------------------------------------------------------------------

class TestFormatarCpf:
    def test_formatacao(self):
        from voice_agent.validacao_cpf import formatar_cpf
        assert formatar_cpf("52998224725") == "529.982.247-25"

    def test_formatacao_zeros(self):
        from voice_agent.validacao_cpf import formatar_cpf
        assert formatar_cpf("00000000191") == "000.000.001-91"


# ---------------------------------------------------------------------------
# 4. deve_validar_cpf — função principal do bypass
# ---------------------------------------------------------------------------

class TestDeveValidarCpf:
    def test_cpf_valido_retorna_none(self):
        from voice_agent.validacao_cpf import deve_validar_cpf
        ctx = _ctx()
        result = deve_validar_cpf(ctx, "meu cpf é 529.982.247-25")
        assert result is None  # CPF válido → não bloqueia

    def test_cpf_invalido_retorna_mensagem(self):
        from voice_agent.validacao_cpf import deve_validar_cpf
        ctx = _ctx()
        result = deve_validar_cpf(ctx, "cpf: 123.456.789-00")
        assert result is not None
        assert "CPF" in result or "cpf" in result.lower()

    def test_sem_cpf_retorna_none(self):
        from voice_agent.validacao_cpf import deve_validar_cpf
        ctx = _ctx()
        assert deve_validar_cpf(ctx, "quero agendar para segunda") is None

    def test_ctx_none_retorna_none(self):
        from voice_agent.validacao_cpf import deve_validar_cpf
        assert deve_validar_cpf(None, "cpf 529.982.247-25") is None

    def test_texto_vazio_retorna_none(self):
        from voice_agent.validacao_cpf import deve_validar_cpf
        assert deve_validar_cpf(_ctx(), "") is None

    def test_toggle_off_retorna_none(self):
        from voice_agent import validacao_cpf as mod
        original = mod._ATIVADO
        mod._ATIVADO = False
        try:
            assert mod.deve_validar_cpf(_ctx(), "cpf: 123.456.789-00") is None
        finally:
            mod._ATIVADO = original

    def test_sequencia_homogenea_retorna_mensagem(self):
        from voice_agent.validacao_cpf import deve_validar_cpf
        ctx = _ctx()
        result = deve_validar_cpf(ctx, "111.111.111-11")
        assert result is not None

    def test_mensagem_tem_exemplo_de_formato(self):
        from voice_agent.validacao_cpf import deve_validar_cpf
        ctx = _ctx()
        result = deve_validar_cpf(ctx, "meu CPF: 12345678900")
        assert result is not None
        # Mensagem deve guiar o paciente
        assert "11" in result or "dígito" in result.lower() or "exemplo" in result.lower() or "pontuação" in result.lower()


# ---------------------------------------------------------------------------
# 5. Step 16 em enriquecimento_ctx — injeção em known
# ---------------------------------------------------------------------------

class TestStep16Enriquecimento:
    """Simula o step 16 e verifica injeção correta em known."""

    def _rodar_step16(self, user_text: str, known: dict | None = None) -> dict:
        if known is None:
            known = {}
        ctx = {"lead_id": 1001, "known": known}

        try:
            from voice_agent.validacao_cpf import (
                extrair_cpf_do_texto as _extrair_cpf,
                cpf_matematicamente_valido as _cpf_valido,
            )
            if user_text and not known.get("cpf_validado"):
                _cpf_raw = _extrair_cpf(user_text)
                if _cpf_raw is not None:
                    if _cpf_valido(_cpf_raw):
                        known["cpf_validado"] = _cpf_raw
                        known.pop("cpf_invalido_detectado", None)
                    else:
                        known["cpf_invalido_detectado"] = True
        except Exception:
            pass

        return known

    def test_cpf_valido_injeta_em_known(self):
        known = self._rodar_step16("meu cpf 529.982.247-25")
        assert known.get("cpf_validado") == "52998224725"
        assert not known.get("cpf_invalido_detectado")

    def test_cpf_invalido_marca_flag(self):
        known = self._rodar_step16("cpf 123.456.789-00")
        assert known.get("cpf_invalido_detectado") is True
        assert not known.get("cpf_validado")

    def test_sem_cpf_nao_altera_known(self):
        known = self._rodar_step16("quero marcar para segunda")
        assert not known.get("cpf_validado")
        assert not known.get("cpf_invalido_detectado")

    def test_cpf_ja_em_known_nao_sobrescreve(self):
        """Se cpf_validado já existe (de turno anterior), step 16 não reprocessa."""
        known_antes = {"cpf_validado": "52998224725"}
        known = self._rodar_step16("cpf novo: 12345678900", known=dict(known_antes))
        # Não deve ter sobrescrito com o CPF inválido novo
        assert known.get("cpf_validado") == "52998224725"

    def test_cpf_valido_limpa_flag_invalido(self):
        """Paciente corrige CPF na 2ª tentativa — flag deve ser limpo."""
        known = {"cpf_invalido_detectado": True}
        known = self._rodar_step16("cpf correto: 529.982.247-25", known=known)
        assert known.get("cpf_validado") == "52998224725"
        assert not known.get("cpf_invalido_detectado")


# ---------------------------------------------------------------------------
# 6. Posição na chain (C-110 depois de C-109, antes de urgência)
# ---------------------------------------------------------------------------

class TestPosicaoNaChain:
    def test_c110_depois_de_c109_antes_urgencia(self):
        import pathlib
        base = pathlib.Path(__file__).parent.parent
        conteudo = (base / "voice_agent/blindagens_deterministicas.py").read_text(encoding="utf-8")

        inicio = conteudo.find("def tentar_bypass_deterministico")
        assert inicio >= 0
        corpo = conteudo[inicio:]

        pos_c109 = corpo.find("C-109")
        pos_c110 = corpo.find("C-110")
        pos_urgencia = corpo.find("deve_orientar_urgencia(ctx")

        assert pos_c109 >= 0, "C-109 não encontrado"
        assert pos_c110 >= 0, "C-110 não encontrado"
        assert pos_urgencia >= 0, "deve_orientar_urgencia não encontrado"

        assert pos_c109 < pos_c110, "C-109 deve vir antes de C-110"
        assert pos_c110 < pos_urgencia, "C-110 deve vir antes de urgência"
