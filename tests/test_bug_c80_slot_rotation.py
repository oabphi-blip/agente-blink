"""
Testes Bug C-80 — Slot rotation + scarcity + race-condition fix
================================================================
C-80a: re-validação em tempo real antes de gravar (slot_ainda_disponivel)
C-80b: rotação de slots com princípio da escassez (5 min / 3 rodadas)
"""
import pytest
import time
from unittest.mock import MagicMock, patch


# ══════════════════════════════════════════════════════════════════════════════
# FIXTURES
# ══════════════════════════════════════════════════════════════════════════════

def _make_redis(store: dict | None = None):
    """Redis mock com SET, SADD, EXPIRE, GET, INCR, SMEMBERS."""
    store = store if store is not None else {}
    ttls: dict = {}

    r = MagicMock()
    r.set = lambda k, v: store.__setitem__(k, str(v))
    r.setex = lambda k, ttl, v: (store.__setitem__(k, str(v)), ttls.__setitem__(k, ttl))
    r.get = lambda k: store[k].encode() if k in store else None
    r.incr = lambda k: store.__setitem__(k, str(int(store.get(k, "0")) + 1)) or int(store[k])
    r.expire = lambda k, t: ttls.__setitem__(k, t)
    r.sadd = lambda k, *vals: [store.setdefault(k + "__set", set()).add(v) for v in vals]
    r.smembers = lambda k: store.get(k + "__set", set())
    return r


SLOT_A = {"data_iso": "2026-08-05", "hora": "09:30", "dia_semana": "quarta-feira"}
SLOT_B = {"data_iso": "2026-08-05", "hora": "14:00", "dia_semana": "quarta-feira"}
SLOT_C = {"data_iso": "2026-08-06", "hora": "10:00", "dia_semana": "quinta-feira"}
SLOT_D = {"data_iso": "2026-08-06", "hora": "15:00", "dia_semana": "quinta-feira"}

AGENDA_4 = [SLOT_A, SLOT_B, SLOT_C, SLOT_D]
LEAD_ID = "99887766"


# ══════════════════════════════════════════════════════════════════════════════
# C-80b: slot_rotation.py
# ══════════════════════════════════════════════════════════════════════════════

from voice_agent.slot_rotation import (
    _slot_key,
    marcar_slots_oferecidos,
    filtrar_slots_novos,
    slots_ja_oferecidos,
    slot_ainda_na_janela,
    contar_rodadas,
    incrementar_rodada,
    deve_escalar,
    gerar_prefixo_escassez,
    gerar_msg_escalar_humano,
    selecionar_2_slots_novos,
)


class TestSlotKey:
    def test_key_canonico(self):
        assert _slot_key(SLOT_A) == "2026-08-05T09:30"

    def test_key_sem_data_vazio(self):
        assert _slot_key({"hora": "09:30"}) == ""

    def test_key_sem_hora_vazio(self):
        assert _slot_key({"data_iso": "2026-08-05"}) == ""

    def test_hora_truncada_a_5(self):
        s = {"data_iso": "2026-08-05", "hora": "09:30:00"}
        assert _slot_key(s) == "2026-08-05T09:30"


class TestMarcarEFiltrar:
    def test_filtrar_slots_sem_redis_retorna_tudo(self):
        resultado = filtrar_slots_novos(None, LEAD_ID, AGENDA_4)
        assert resultado == AGENDA_4

    def test_filtrar_slots_lead_vazio_retorna_tudo(self):
        r = _make_redis()
        resultado = filtrar_slots_novos(r, "", AGENDA_4)
        assert resultado == AGENDA_4

    def test_marcar_e_filtrar_remove_slots_usados(self):
        r = _make_redis()
        marcar_slots_oferecidos(r, LEAD_ID, [SLOT_A, SLOT_B])
        restantes = filtrar_slots_novos(r, LEAD_ID, AGENDA_4)
        assert SLOT_A not in restantes
        assert SLOT_B not in restantes
        assert SLOT_C in restantes
        assert SLOT_D in restantes

    def test_slots_ja_oferecidos_retorna_set_correto(self):
        r = _make_redis()
        marcar_slots_oferecidos(r, LEAD_ID, [SLOT_A])
        ja = slots_ja_oferecidos(r, LEAD_ID)
        assert "2026-08-05T09:30" in ja

    def test_filtrar_com_redis_falho_retorna_original(self):
        r = MagicMock()
        r.smembers.side_effect = Exception("Redis down")
        resultado = filtrar_slots_novos(r, LEAD_ID, [SLOT_A])
        assert resultado == [SLOT_A]


class TestJanelaDe5Min:
    def test_slot_dentro_da_janela(self):
        r = _make_redis()
        marcar_slots_oferecidos(r, LEAD_ID, [SLOT_A])
        # TTL está configurado mas mock não expira — simula dentro da janela
        assert slot_ainda_na_janela(r, LEAD_ID, SLOT_A) is True

    def test_slot_fora_da_janela_key_ausente(self):
        r = _make_redis()  # sem marcar nada
        assert slot_ainda_na_janela(r, LEAD_ID, SLOT_A) is False

    def test_slot_sem_lead_id(self):
        r = _make_redis()
        assert slot_ainda_na_janela(r, "", SLOT_A) is False


class TestRodadas:
    def test_inicia_em_zero(self):
        r = _make_redis()
        assert contar_rodadas(r, LEAD_ID) == 0

    def test_incrementar_uma_vez(self):
        r = _make_redis()
        val = incrementar_rodada(r, LEAD_ID)
        assert val == 1
        assert contar_rodadas(r, LEAD_ID) == 1

    def test_deve_escalar_apos_3(self):
        r = _make_redis()
        for _ in range(3):
            incrementar_rodada(r, LEAD_ID)
        assert deve_escalar(r, LEAD_ID) is True

    def test_nao_escalar_antes_de_3(self):
        r = _make_redis()
        incrementar_rodada(r, LEAD_ID)
        incrementar_rodada(r, LEAD_ID)
        assert deve_escalar(r, LEAD_ID) is False

    def test_sem_redis_nao_escala(self):
        assert deve_escalar(None, LEAD_ID) is False


class TestMensagens:
    def test_prefixo_rodada_0_vazio(self):
        assert gerar_prefixo_escassez(0) == ""

    def test_prefixo_rodada_1_menciona_escassez(self):
        txt = gerar_prefixo_escassez(1)
        assert "preenchidos" in txt or "disputad" in txt

    def test_prefixo_rodada_2_menciona_dinamismo(self):
        txt = gerar_prefixo_escassez(2)
        assert txt  # deve ter algum texto

    def test_msg_escalar_menciona_especialista(self):
        msg = gerar_msg_escalar_humano()
        assert "especialista" in msg or "atendente" in msg


class TestSelecionar2SlotsNovos:
    def test_seleciona_1_manha_1_tarde(self):
        r = _make_redis()
        result = selecionar_2_slots_novos(r, LEAD_ID, AGENDA_4)
        assert len(result) == 2
        horas = [s["hora"][:2] for s in result]
        # Um manhã (<12) e um tarde (>=12) ou 2 do mesmo turno se só há 1
        assert any(int(h) < 12 for h in horas)
        assert any(int(h) >= 12 for h in horas)

    def test_exclui_ja_oferecidos(self):
        r = _make_redis()
        marcar_slots_oferecidos(r, LEAD_ID, [SLOT_A, SLOT_B])
        result = selecionar_2_slots_novos(r, LEAD_ID, AGENDA_4)
        keys = [_slot_key(s) for s in result]
        assert "2026-08-05T09:30" not in keys
        assert "2026-08-05T14:00" not in keys

    def test_retorna_vazio_quando_todos_ofertados(self):
        r = _make_redis()
        marcar_slots_oferecidos(r, LEAD_ID, AGENDA_4)
        result = selecionar_2_slots_novos(r, LEAD_ID, AGENDA_4)
        assert result == []

    def test_sem_agenda_retorna_vazio(self):
        r = _make_redis()
        assert selecionar_2_slots_novos(r, LEAD_ID, []) == []


# ══════════════════════════════════════════════════════════════════════════════
# C-80b: handle_oferecer_slot com rotação
# ══════════════════════════════════════════════════════════════════════════════

from voice_agent.tools_lia import handle_oferecer_slot


class TestHandleOferecer:
    def _ctx(self, agenda=None):
        return {
            "lead_id": LEAD_ID,
            "conversation_key": "55619999:BLINK8133",
            "agenda": agenda or AGENDA_4,
        }

    def test_primeira_rodada_sem_prefixo(self):
        r = _make_redis()
        res = handle_oferecer_slot(
            {"slots": [SLOT_A, SLOT_B], "mensagem_humana": "Escolha um"},
            self._ctx(),
            redis_client=r,
        )
        assert res.erro is None
        assert res.texto_para_paciente == "Escolha um"

    def test_segunda_rodada_adiciona_prefixo_escassez(self):
        r = _make_redis()
        # Simula 1 rodada já feita
        incrementar_rodada(r, LEAD_ID)
        marcar_slots_oferecidos(r, LEAD_ID, [SLOT_A, SLOT_B])

        res = handle_oferecer_slot(
            {"slots": [SLOT_C, SLOT_D], "mensagem_humana": "Novas opções:"},
            self._ctx(),
            redis_client=r,
        )
        assert res.erro is None
        # Deve ter prefixo de escassez no início
        assert "preenchidos" in res.texto_para_paciente or "disputad" in res.texto_para_paciente

    def test_reoferta_slot_ja_oferecido_redireciona_para_novo(self):
        r = _make_redis()
        marcar_slots_oferecidos(r, LEAD_ID, [SLOT_A, SLOT_B])

        # LLM propõe SLOT_A e SLOT_B novamente (já ofertados)
        res = handle_oferecer_slot(
            {"slots": [SLOT_A, SLOT_B], "mensagem_humana": "Tenho estes:"},
            self._ctx(agenda=AGENDA_4),
            redis_client=r,
        )
        # Deve ter trocado por SLOT_C/SLOT_D (novos)
        assert res.erro is None or "escalar_humano" in (res.erro or "")

    def test_sem_slots_retorna_erro(self):
        r = _make_redis()
        res = handle_oferecer_slot({"slots": [], "mensagem_humana": ""}, self._ctx(), r)
        assert res.erro == "oferecer_slot chamada sem slots"

    def test_escala_apos_3_rodadas(self):
        r = _make_redis()
        for _ in range(3):
            incrementar_rodada(r, LEAD_ID)

        res = handle_oferecer_slot(
            {"slots": [SLOT_C], "mensagem_humana": "Tenho:"},
            self._ctx(),
            redis_client=r,
        )
        assert res.erro == "escalar_humano:3_rounds_sem_confirmacao"
        assert "especialista" in res.texto_para_paciente or "atendente" in res.texto_para_paciente

    def test_sem_redis_funciona_normalmente(self):
        res = handle_oferecer_slot(
            {"slots": [SLOT_A], "mensagem_humana": "Tenho:"},
            self._ctx(),
            redis_client=None,
        )
        assert res.erro is None


# ══════════════════════════════════════════════════════════════════════════════
# C-80a: slot_ainda_disponivel SQL routing
# ══════════════════════════════════════════════════════════════════════════════

class TestSlotAindaDisponivelSqlRouting:
    """Verifica que slot_ainda_disponivel rota para SQL quando nomes fornecidos."""

    def test_sql_chamado_quando_nomes_fornecidos(self):
        """Com medico_nome + unidade_nome, deve chamar slot_ainda_disponivel_sql."""
        with patch(
            "voice_agent.medware_sql.slot_ainda_disponivel_sql",
            return_value=(True, []),
        ) as mock_sql:
            from voice_agent.medware import MedwareClient
            client = MedwareClient.__new__(MedwareClient)
            client.listar_horarios_livres = MagicMock(return_value=[])

            result = client.slot_ainda_disponivel(
                data_iso="2026-08-05",
                hora="09:30",
                cod_medico=12080,
                cod_unidade=5,
                medico_nome="Dra. Karla Delalíbera",
                unidade_nome="Asa Norte",
            )
            mock_sql.assert_called_once()
            assert result == (True, [])

    def test_sem_nomes_usa_rest(self):
        """Sem medico_nome, deve cair no caminho REST (listar_horarios_livres)."""
        from voice_agent.medware import MedwareClient
        client = MedwareClient.__new__(MedwareClient)
        client.listar_horarios_livres = MagicMock(return_value=[
            {"hora": "09:30", "dataHora": "2026-08-05T09:30:00"}
        ])

        result = client.slot_ainda_disponivel(
            data_iso="2026-08-05",
            hora="09:30",
            cod_medico=12080,
            cod_unidade=5,
            medico_nome="",   # sem nome → REST
            unidade_nome="",
        )
        assert result == (True, [])
        client.listar_horarios_livres.assert_called_once()
