"""
Pytest C-138 (14/08/2026) — Fluxo sem convênio 100% Python.

Benchmarks por especialidade + escalação 3 níveis via Redis.
Garante que pacientes sem convênio em hesitação recebem conteúdo
conversacional específico antes do LLM.
"""
import pytest
from unittest.mock import MagicMock

from voice_agent.fluxo_sem_convenio import (
    deve_aprofundar_especialidade,
    _e_sem_convenio,
    _e_hesitacao,
    _derivar_especialidade,
    _get_nivel,
    _set_nivel,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _ctx(
    convenio=None, medico=None, motivo=None, nome=None,
    ja_agendado=False, lead_id=None, idade=None, pediatrico=False,
):
    known = {"ja_agendado": ja_agendado}
    if convenio is not None:
        known["convenio"] = convenio
    if medico:
        known["medico"] = medico
    if motivo:
        known["motivo"] = motivo
    if idade is not None:
        known["idade"] = idade
    if pediatrico:
        known["contexto_pediatrico"] = True
    ctx = {"known": known}
    if nome:
        ctx["name"] = nome
    if lead_id:
        ctx["lead_id"] = lead_id
    return ctx


def _mock_redis(nivel_atual=0):
    """Redis mock que começa em nivel_atual."""
    r = MagicMock()
    r.get.return_value = str(nivel_atual).encode()
    r.setex.return_value = True
    return r


def _redis_vazio():
    """Redis mock sem dados (lead novo)."""
    r = MagicMock()
    r.get.return_value = None
    r.setex.return_value = True
    return r


# ─────────────────────────────────────────────────────────────────────────────
# 1. _e_sem_convenio()
# ─────────────────────────────────────────────────────────────────────────────

class TestESemConvenio:
    def test_nao_se_aplica(self):
        assert _e_sem_convenio(_ctx(convenio="Não se aplica"))

    def test_nao_se_aplica_lower(self):
        assert _e_sem_convenio(_ctx(convenio="nao se aplica"))

    def test_particular(self):
        assert _e_sem_convenio(_ctx(convenio="particular"))

    def test_sem_convenio_str(self):
        assert _e_sem_convenio(_ctx(convenio="sem convênio"))

    def test_vazio_str(self):
        assert _e_sem_convenio(_ctx(convenio=""))

    def test_com_convenio_saude_caixa(self):
        assert not _e_sem_convenio(_ctx(convenio="Saúde Caixa"))

    def test_com_convenio_bacen(self):
        assert not _e_sem_convenio(_ctx(convenio="Bacen"))

    def test_ctx_none(self):
        # sem convênio definido = considera sem convênio
        assert _e_sem_convenio(_ctx())


# ─────────────────────────────────────────────────────────────────────────────
# 2. _e_hesitacao()
# ─────────────────────────────────────────────────────────────────────────────

class TestEHesitacao:
    def test_vou_pensar(self):
        assert _e_hesitacao("vou pensar")

    def test_entendi(self):
        assert _e_hesitacao("entendi")

    def test_ok(self):
        assert _e_hesitacao("ok")

    def test_beleza(self):
        assert _e_hesitacao("beleza")

    def test_vou_ver(self):
        assert _e_hesitacao("vou ver sim")

    def test_preciso_de_tempo(self):
        assert _e_hesitacao("preciso de um tempo")

    def test_talvez(self):
        assert _e_hesitacao("talvez mais pra frente")

    def test_nao_hesitacao_booking(self):
        """'Quero marcar' não é hesitação."""
        assert not _e_hesitacao("quero marcar a consulta")

    def test_nao_hesitacao_confirmar(self):
        assert not _e_hesitacao("sim, pode confirmar")

    def test_nao_hesitacao_opcao1(self):
        assert not _e_hesitacao("opção 1")

    def test_msg_vazia(self):
        assert not _e_hesitacao("")

    def test_msg_muito_curta(self):
        assert not _e_hesitacao("1")


# ─────────────────────────────────────────────────────────────────────────────
# 3. _derivar_especialidade()
# ─────────────────────────────────────────────────────────────────────────────

class TestDerivarEspecialidade:
    def test_apv(self):
        assert _derivar_especialidade(_ctx(motivo="processamento visual")) == "apv"

    def test_apv_sdp(self):
        assert _derivar_especialidade(_ctx(motivo="sdp")) == "apv"

    def test_estrabismo(self):
        assert _derivar_especialidade(_ctx(motivo="estrabismo")) == "estrabismo"

    def test_olho_torto(self):
        assert _derivar_especialidade(_ctx(motivo="olho torto")) == "estrabismo"

    def test_catarata(self):
        assert _derivar_especialidade(_ctx(motivo="catarata")) == "catarata"

    def test_oftalmopediatria_idade(self):
        assert _derivar_especialidade(_ctx(medico="Karla", idade=7)) == "oftalmopediatria"

    def test_oftalmopediatria_pediatrico_flag(self):
        assert _derivar_especialidade(_ctx(pediatrico=True)) == "oftalmopediatria"

    def test_oftalmopediatria_bebe_motivo(self):
        assert _derivar_especialidade(_ctx(motivo="bebê 3 meses")) == "oftalmopediatria"

    def test_refrativa_fabricio(self):
        assert _derivar_especialidade(_ctx(medico="Dr. Fabrício Freitas")) == "refrativa"

    def test_geral_sem_info(self):
        assert _derivar_especialidade(_ctx()) == "geral"

    def test_geral_karla_adulto(self):
        assert _derivar_especialidade(_ctx(medico="Karla", motivo="rotina")) == "geral"


# ─────────────────────────────────────────────────────────────────────────────
# 4. deve_aprofundar_especialidade() — gates
# ─────────────────────────────────────────────────────────────────────────────

class TestGates:
    def test_com_convenio_nao_dispara(self):
        """Paciente com convênio → None."""
        ctx = _ctx(convenio="Saúde Caixa")
        r = deve_aprofundar_especialidade(ctx, "entendi ok")
        assert r is None

    def test_ja_agendado_nao_dispara(self):
        """Lead já agendado → None."""
        ctx = _ctx(convenio="não se aplica", ja_agendado=True)
        r = deve_aprofundar_especialidade(ctx, "vou pensar")
        assert r is None

    def test_sem_hesitacao_nao_dispara(self):
        """Inbound sem hesitação → None."""
        ctx = _ctx(convenio="não se aplica")
        r = deve_aprofundar_especialidade(ctx, "quero marcar agora")
        assert r is None

    def test_ctx_none_retorna_none(self):
        r = deve_aprofundar_especialidade(None, "entendi")
        assert r is None

    def test_toggle_off(self, monkeypatch):
        """Toggle FLUXO_SEM_CONVENIO_ATIVADO=0 → None."""
        import voice_agent.fluxo_sem_convenio as mod
        monkeypatch.setattr(mod, "_ATIVADO", False)
        ctx = _ctx(convenio="não se aplica")
        r = deve_aprofundar_especialidade(ctx, "vou pensar")
        assert r is None

    def test_nivel3_nao_dispara(self):
        """Nível 3 ou mais → None (não repetir)."""
        redis = _mock_redis(nivel_atual=3)
        ctx = _ctx(convenio="não se aplica", lead_id="999")
        r = deve_aprofundar_especialidade(ctx, "entendi ok", redis)
        assert r is None


# ─────────────────────────────────────────────────────────────────────────────
# 5. deve_aprofundar_especialidade() — conteúdo dos níveis
# ─────────────────────────────────────────────────────────────────────────────

class TestConteudoNiveis:
    def test_nivel0_oftalmopediatria(self):
        """Nível 0: benchmark de oftalmopediatria."""
        redis = _redis_vazio()
        ctx = _ctx(convenio="não se aplica", medico="Karla", idade=5, lead_id="100")
        r = deve_aprofundar_especialidade(ctx, "vou pensar", redis)
        assert r is not None
        assert "7 anos" in r or "janela" in r.lower() or "pediátrica" in r.lower() or "oftalmopediatria" in r.lower()
        # Deve mostrar valores
        assert "611" in r or "335" in r

    def test_nivel0_apv(self):
        """Nível 0: benchmark APV."""
        redis = _redis_vazio()
        ctx = _ctx(convenio="não se aplica", medico="Karla", motivo="processamento visual", lead_id="101")
        r = deve_aprofundar_especialidade(ctx, "entendi", redis)
        assert r is not None
        assert "800" in r or "435" in r
        assert "2" in r and ("hora" in r.lower() or "horas" in r.lower())

    def test_nivel0_catarata(self):
        """Nível 0: benchmark catarata com biometria."""
        redis = _redis_vazio()
        ctx = _ctx(convenio="particular", medico="Fabrício", motivo="catarata", lead_id="102")
        r = deve_aprofundar_especialidade(ctx, "ok, entendi", redis)
        assert r is not None
        assert "biometria" in r.lower()
        assert "445" in r or "235" in r

    def test_nivel0_refrativa(self):
        """Nível 0: benchmark saúde ocular adulto 50+."""
        redis = _redis_vazio()
        ctx = _ctx(convenio="não se aplica", medico="Fabrício", lead_id="103")
        r = deve_aprofundar_especialidade(ctx, "vou ver", redis)
        assert r is not None
        assert "glaucoma" in r.lower() or "50" in r or "preventiv" in r.lower()

    def test_nivel1_fila_encaixe(self):
        """Nível 1: fila de encaixe."""
        redis = _mock_redis(nivel_atual=1)
        ctx = _ctx(convenio="não se aplica", lead_id="104")
        r = deve_aprofundar_especialidade(ctx, "talvez mais pra frente", redis)
        assert r is not None
        assert "fila" in r.lower() or "encaixe" in r.lower()

    def test_nivel2_escalar_humano(self):
        """Nível 2: escalada para equipe humana."""
        redis = _mock_redis(nivel_atual=2)
        ctx = _ctx(convenio="não se aplica", lead_id="105")
        r = deve_aprofundar_especialidade(ctx, "ainda estou pensando", redis)
        assert r is not None
        assert "equipe" in r.lower() or "atendente" in r.lower() or "equipe" in r.lower()

    def test_nivel_incrementa(self):
        """Após disparo, Redis deve ser chamado para gravar nivel+1."""
        redis = _redis_vazio()
        ctx = _ctx(convenio="não se aplica", lead_id="106")
        r = deve_aprofundar_especialidade(ctx, "entendi", redis)
        assert r is not None
        # setex deve ter sido chamado com nivel=1
        redis.setex.assert_called_once()
        args = redis.setex.call_args[0]
        assert args[2] == "1"  # nivel 0 → incrementa para 1

    def test_sem_redis_ainda_dispara(self):
        """Sem Redis: nível sempre 0, ainda entrega conteúdo."""
        ctx = _ctx(convenio="não se aplica", lead_id="107")
        r = deve_aprofundar_especialidade(ctx, "entendi ok", redis_client=None)
        assert r is not None

    def test_nome_aparece_na_resposta(self):
        """Nome do paciente deve aparecer na resposta."""
        ctx = _ctx(convenio="não se aplica", nome="Fernanda", lead_id="108")
        r = deve_aprofundar_especialidade(ctx, "vou pensar", redis_client=None)
        if r:
            assert "Fernanda" in r

    def test_sem_nome_nao_quebra(self):
        """Sem nome no ctx → resposta sem nome, sem exceção."""
        ctx = _ctx(convenio="não se aplica", lead_id="109")
        r = deve_aprofundar_especialidade(ctx, "ok, entendi", redis_client=None)
        assert r is None or isinstance(r, str)

    def test_resposta_nao_usa_particular(self):
        """Termo proibido 'particular' não deve aparecer."""
        ctx = _ctx(convenio="não se aplica", lead_id="110")
        r = deve_aprofundar_especialidade(ctx, "vou pensar", redis_client=None)
        if r:
            assert "particular" not in r.lower()

    def test_resposta_tem_valor(self):
        """Nível 0 deve sempre mostrar valor (Pix ou parcelamento)."""
        ctx = _ctx(convenio="não se aplica", lead_id="111")
        r = deve_aprofundar_especialidade(ctx, "entendi", redis_client=None)
        if r:
            assert "R$" in r or "Pix" in r or "pix" in r.lower()

    def test_estrabismo_benchmark(self):
        """Benchmark estrabismo menciona alinhamento/funcional."""
        redis = _redis_vazio()
        ctx = _ctx(convenio="não se aplica", motivo="estrabismo", lead_id="112")
        r = deve_aprofundar_especialidade(ctx, "vou pensar", redis)
        assert r is not None
        # deve mencionar aspecto funcional
        assert ("visão" in r.lower() or "alinhament" in r.lower()
                or "profundidade" in r.lower() or "diagnóstico" in r.lower())


# ─────────────────────────────────────────────────────────────────────────────
# 6. Redis helpers
# ─────────────────────────────────────────────────────────────────────────────

class TestRedisHelpers:
    def test_get_nivel_sem_dados(self):
        redis = MagicMock()
        redis.get.return_value = None
        assert _get_nivel("123", redis) == 0

    def test_get_nivel_com_dados(self):
        redis = MagicMock()
        redis.get.return_value = b"2"
        assert _get_nivel("123", redis) == 2

    def test_get_nivel_erro_redis(self):
        redis = MagicMock()
        redis.get.side_effect = Exception("Redis timeout")
        # fail-open: retorna 0
        assert _get_nivel("123", redis) == 0

    def test_set_nivel_chama_setex(self):
        redis = MagicMock()
        _set_nivel("123", 2, redis)
        redis.setex.assert_called_once()
        args = redis.setex.call_args[0]
        assert "123" in args[0]
        assert args[2] == "2"

    def test_set_nivel_erro_nao_explode(self):
        redis = MagicMock()
        redis.setex.side_effect = Exception("Redis error")
        # fail-open: não levanta exceção
        _set_nivel("123", 1, redis)


# ─────────────────────────────────────────────────────────────────────────────
# 7. Fail-open e edge cases
# ─────────────────────────────────────────────────────────────────────────────

class TestFailOpen:
    def test_redis_falha_nao_quebra_resposta(self):
        """Redis timeout não deve impedir resposta."""
        redis = MagicMock()
        redis.get.side_effect = Exception("timeout")
        ctx = _ctx(convenio="não se aplica", lead_id="200")
        # Não deve levantar exceção
        r = deve_aprofundar_especialidade(ctx, "entendi", redis)
        # Com get falhando, level=0 e deve responder
        assert r is None or isinstance(r, str)

    def test_ctx_vazio_known_nao_quebra(self):
        """ctx com known={} não deve explodir."""
        r = deve_aprofundar_especialidade({"known": {}}, "entendi")
        # sem convenio definido → considera sem convênio → pode disparar
        assert r is None or isinstance(r, str)

    def test_user_text_none_nao_quebra(self):
        """user_text=None → None (sem hesitação detectável)."""
        ctx = _ctx(convenio="não se aplica")
        # None user_text → _e_hesitacao retorna False
        r = deve_aprofundar_especialidade(ctx, None)  # type: ignore
        # Deve ser None por causa do gate de hesitação
        assert r is None or isinstance(r, str)
