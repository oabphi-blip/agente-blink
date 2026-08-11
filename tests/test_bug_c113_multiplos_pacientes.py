"""
Pytest — Bug C-113: Múltiplos pacientes — bifurcar para 2 agendamentos.

Cobre:
  - Detecção: "2 filhos", "nós dois", "para mim e minha filha", etc.
  - ctx.known.n_patients (injetado por C-81) também dispara
  - Negação: "segunda-feira", "2 horas" → não dispara
  - ctx=None → None (fail-open)
  - Toggle OFF → None
  - Redis flag impede repetição
  - Mensagem orienta bifurcação e pede dados do 1° paciente
  - already_coletado flag → silencia
  - Posição na chain: antes de C-112 e urgência
  - step 18 em enriquecimento_ctx
"""
from __future__ import annotations

import pathlib
from unittest.mock import MagicMock


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ctx(n_patients: int | None = None, lead_id: int = 8801, **known_extra) -> dict:
    known: dict = {}
    if n_patients is not None:
        known["n_patients"] = n_patients
    known.update(known_extra)
    return {"lead_id": lead_id, "known": known}


def _redis_sem_flag():
    r = MagicMock()
    r.get.return_value = None
    return r


def _redis_com_flag():
    r = MagicMock()
    r.get.return_value = b"1"
    return r


def _orientar(ctx, user_text="", redis=None):
    from voice_agent.multiplos_pacientes import deve_orientar_multiplos_pacientes
    return deve_orientar_multiplos_pacientes(ctx, user_text, redis)


def _detectar(user_text, ctx=None):
    from voice_agent.multiplos_pacientes import detectar_multiplos_pacientes
    return detectar_multiplos_pacientes(user_text, ctx)


# ---------------------------------------------------------------------------
# 1. Detecção de padrões
# ---------------------------------------------------------------------------

class TestDeteccaoPadroes:
    @staticmethod
    def _checa(texto):
        return _detectar(texto) >= 2

    def test_dois_filhos_numeral(self):
        assert self._checa("para meus 2 filhos")

    def test_dois_filhos_extenso(self):
        assert self._checa("tenho dois filhos")

    def test_para_mim_e_minha_filha(self):
        assert self._checa("quero agendar para mim e minha filha")

    def test_nos_dois(self):
        assert self._checa("nós dois precisamos consultar")

    def test_a_gente_dois(self):
        assert self._checa("a gente vai agendar para os dois")

    def test_minha_filha_e_eu(self):
        assert self._checa("minha filha e eu")

    def test_para_nos(self):
        assert self._checa("consulta para nós e minha filha")

    def test_agendar_para_dois(self):
        assert self._checa("quero agendar para os dois")

    def test_minhas_duas_filhas(self):
        assert self._checa("para minhas duas filhas")


# ---------------------------------------------------------------------------
# 2. Falsos positivos — NÃO deve disparar
# ---------------------------------------------------------------------------

class TestFalsoPositivo:
    def test_segunda_feira(self):
        """'segunda-feira' não é 2 pacientes."""
        assert _detectar("quero agendar segunda-feira") == 0

    def test_dois_minutos(self):
        assert _detectar("aguarda 2 minutos") == 0

    def test_texto_vazio(self):
        assert _detectar("") == 0

    def test_um_paciente(self):
        assert _detectar("quero agendar para minha filha") == 0

    def test_texto_generico(self):
        assert _detectar("bom dia, quero consultar") == 0


# ---------------------------------------------------------------------------
# 3. ctx.known.n_patients (injetado por C-81)
# ---------------------------------------------------------------------------

class TestNPatientsDoCtx:
    def test_n_patients_2_dispara(self):
        ctx = _ctx(n_patients=2)
        assert _detectar("qualquer texto", ctx) == 2

    def test_n_patients_3_dispara(self):
        ctx = _ctx(n_patients=3)
        assert _detectar("quero agendar", ctx) == 3

    def test_n_patients_1_nao_dispara(self):
        ctx = _ctx(n_patients=1)
        assert _detectar("qualquer texto", ctx) < 2

    def test_n_patients_0_usa_regex(self):
        ctx = _ctx(n_patients=0)
        # sem n_patients ≥2, usa regex
        assert _detectar("meus 2 filhos", ctx) == 2


# ---------------------------------------------------------------------------
# 4. deve_orientar_multiplos_pacientes — comportamento
# ---------------------------------------------------------------------------

class TestOrientarMultiplosPacientes:
    def test_dispara_com_dois_filhos(self):
        ctx = _ctx()
        result = _orientar(ctx, "quero agendar meus 2 filhos")
        assert result is not None

    def test_mensagem_menciona_agendamento_separado(self):
        ctx = _ctx()
        result = _orientar(ctx, "para mim e minha filha")
        assert result is not None
        assert "separado" in result.lower() or "um agendamento" in result.lower() or "cada vez" in result.lower()

    def test_mensagem_pede_dados_primeiro_paciente(self):
        ctx = _ctx()
        result = _orientar(ctx, "nós dois")
        assert result is not None
        assert "primeiro" in result.lower() or "nome" in result.lower()

    def test_ctx_none_retorna_none(self):
        assert _orientar(None, "meus 2 filhos") is None

    def test_texto_sem_multiplos_retorna_none(self):
        ctx = _ctx()
        assert _orientar(ctx, "bom dia") is None

    def test_toggle_off_retorna_none(self):
        from voice_agent import multiplos_pacientes as mod
        original = mod._ATIVADO
        mod._ATIVADO = False
        try:
            ctx = _ctx()
            assert mod.deve_orientar_multiplos_pacientes(ctx, "meus 2 filhos") is None
        finally:
            mod._ATIVADO = original

    def test_redis_flag_impede_repeticao(self):
        """Se Redis flag ativo → não repetir orientação."""
        ctx = _ctx()
        result = _orientar(ctx, "meus 2 filhos", redis=_redis_com_flag())
        assert result is None

    def test_redis_sem_flag_dispara(self):
        ctx = _ctx()
        result = _orientar(ctx, "meus 2 filhos", redis=_redis_sem_flag())
        assert result is not None

    def test_ja_coletado_silencia(self):
        """Segundo agendamento já coletado → não orientar mais."""
        ctx = _ctx(segundo_agendamento_coletado=True)
        result = _orientar(ctx, "meus 2 filhos")
        assert result is None

    def test_injecta_multiplos_pacientes_em_known(self):
        """Após detecção, known deve ter multiplos_pacientes."""
        ctx = _ctx()
        _orientar(ctx, "nós dois")
        assert ctx["known"].get("multiplos_pacientes", 0) >= 2

    def test_injecta_aguardando_primeiro_paciente(self):
        ctx = _ctx()
        _orientar(ctx, "meus 2 filhos")
        assert ctx["known"].get("aguardando_primeiro_paciente") is True

    def test_n_patients_no_ctx_dispara(self):
        ctx = _ctx(n_patients=2)
        result = _orientar(ctx, "quero agendar")  # sem texto explícito
        assert result is not None


# ---------------------------------------------------------------------------
# 5. Posição na chain e estrutura
# ---------------------------------------------------------------------------

class TestPosicaoNaChain:
    def test_c113_antes_de_c112_na_chain(self):
        base = pathlib.Path(__file__).parent.parent
        conteudo = (base / "voice_agent/blindagens_deterministicas.py").read_text(encoding="utf-8")

        inicio = conteudo.find("def tentar_bypass_deterministico")
        assert inicio >= 0
        corpo = conteudo[inicio:]

        pos_c113 = corpo.find("C-113")
        pos_c112 = corpo.find("C-112")

        assert pos_c113 >= 0, "C-113 não encontrado"
        assert pos_c112 >= 0, "C-112 não encontrado"
        assert pos_c113 < pos_c112, "C-113 deve vir antes de C-112"

    def test_step18_em_enriquecimento_ctx(self):
        base = pathlib.Path(__file__).parent.parent
        conteudo = (base / "voice_agent/enriquecimento_ctx.py").read_text(encoding="utf-8")
        assert "C-113-18" in conteudo, "Step 18 C-113 não encontrado em enriquecimento_ctx.py"
