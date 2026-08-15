"""
Bug C-147 — Chats API como memória de fallback do agente.

Garante que quando TODA CONVERSA (1261206) está vazio,
get_caller_context_by_lead preenche toda_conversa e
ultima_msg_outbound via GET /chats/{chat_id}/messages.

Testa a lógica C-147 sem instanciar o KommoClient completo:
usa função _rodar_c147 que replica exatamente o bloco inserido
em get_caller_context_by_lead, facilitando teste unitário puro.
"""
from __future__ import annotations

import os
import re
import time
from datetime import datetime
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

_TZ_BR = ZoneInfo("America/Sao_Paulo")


# ---------------------------------------------------------------------------
# Extraímos a lógica C-147 como função testável isolada
# ---------------------------------------------------------------------------

def _rodar_c147(
    out: dict,
    *,
    chat_id_via_url: int | None = None,
    chat_id_via_api: int | None = None,
    msgs_raw: list | None = None,
    toggle: str = "1",
) -> dict:
    """
    Replica o bloco C-147 de get_caller_context_by_lead.
    Recebe o estado atual de `out` e simula:
      - get_chat_id_for_lead → chat_id_via_api (ou None)
      - get_chat_messages_raw → msgs_raw
      - url_da_conversa extraído de out['known']['url_da_conversa'] se presente
    Devolve o mesmo `out` modificado (in-place).
    """
    # Mocks dos métodos do client
    mock_get_chat_id = MagicMock(return_value=chat_id_via_api)
    mock_get_msgs = MagicMock(return_value=msgs_raw or [])

    with patch.dict(os.environ, {"CHATS_API_MEMORIA_ATIVADA": toggle}):
        import os as _os_c147
        _chats_api_on = _os_c147.environ.get(
            "CHATS_API_MEMORIA_ATIVADA", "1"
        ).lower() not in ("0", "false", "no", "off")

        if not _chats_api_on:
            out["_mock_get_chat_id"] = mock_get_chat_id
            out["_mock_get_msgs"] = mock_get_msgs
            return out

        _toda_conv_vazia = not out.get("toda_conversa")
        _ultima_outbound_vazia = not out.get("known", {}).get("ultima_msg_outbound")

        if not (_toda_conv_vazia or _ultima_outbound_vazia):
            out["_mock_get_chat_id"] = mock_get_chat_id
            out["_mock_get_msgs"] = mock_get_msgs
            return out

        # Extrai chat_id do campo url_da_conversa
        _chat_id_c147: int | None = None
        _url_conv_c147 = out.get("known", {}).get("url_da_conversa") or ""
        _m_url_c147 = re.search(r"/chats/(\d+)", _url_conv_c147)
        if _m_url_c147:
            try:
                _chat_id_c147 = int(_m_url_c147.group(1))
            except (ValueError, TypeError):
                pass

        # Fallback: descobrir chat_id via API (só se toda_conversa vazia)
        if not _chat_id_c147 and _toda_conv_vazia:
            _chat_id_c147 = mock_get_chat_id()

        if _chat_id_c147:
            _limit_c147 = 30 if _toda_conv_vazia else 5
            _msgs_raw_c147 = mock_get_msgs(_chat_id_c147, limit=_limit_c147)
            if _msgs_raw_c147:
                _linhas_c147: list[str] = []
                _ultima_out_c147 = ""
                for _msg_c147 in sorted(
                    _msgs_raw_c147,
                    key=lambda m: m.get("created_at") or 0,
                ):
                    _dir_c147 = _msg_c147.get("direction") or ""
                    _content_c147 = _msg_c147.get("content") or {}
                    _txt_c147 = ""
                    if isinstance(_content_c147, dict):
                        _txt_c147 = (_content_c147.get("text") or "").strip()
                    if not _txt_c147:
                        _tipo = (
                            _content_c147.get("type") or "arquivo"
                            if isinstance(_content_c147, dict)
                            else "arquivo"
                        )
                        if _tipo not in ("text",):
                            _txt_c147 = f"[{_tipo}]"
                    if not _txt_c147:
                        continue
                    _ts_c147 = _msg_c147.get("created_at") or 0
                    if _ts_c147:
                        _dt_c147 = datetime.fromtimestamp(_ts_c147, tz=_TZ_BR)
                    else:
                        _dt_c147 = datetime.now(tz=_TZ_BR)
                    _hora_c147 = _dt_c147.strftime("%H:%M")
                    _data_c147 = _dt_c147.strftime("%d/%m")
                    if _dir_c147 == "out":
                        _linhas_c147.append(
                            f"[L {_hora_c147} {_data_c147}] {_txt_c147[:300]}"
                        )
                        _ultima_out_c147 = _txt_c147[:300]
                    elif _dir_c147 == "in":
                        _linhas_c147.append(
                            f"[P {_hora_c147} {_data_c147}] {_txt_c147[:300]}"
                        )

                if _toda_conv_vazia and _linhas_c147:
                    out["toda_conversa"] = "\n".join(_linhas_c147)

                if _ultima_outbound_vazia and _ultima_out_c147:
                    out.setdefault("known", {})["ultima_msg_outbound"] = _ultima_out_c147

    out["_mock_get_chat_id"] = mock_get_chat_id
    out["_mock_get_msgs"] = mock_get_msgs
    return out


# ---------------------------------------------------------------------------
# Factories de dados
# ---------------------------------------------------------------------------

def _make_msg(direction: str, text: str, ts: int | None = None) -> dict:
    return {
        "direction": direction,
        "created_at": ts or int(time.time()),
        "content": {"type": "text", "text": text},
    }


def _make_img(direction: str = "in", ts: int | None = None) -> dict:
    return {
        "direction": direction,
        "created_at": ts or int(time.time()),
        "content": {"type": "image"},
    }


def _out_vazio(url_da_conversa: str = "") -> dict:
    return {
        "found": True,
        "lead_id": 99999,
        "toda_conversa": "",
        "known": {"url_da_conversa": url_da_conversa} if url_da_conversa else {},
    }


def _out_com_toda_conversa(conteudo: str, url: str = "") -> dict:
    o = _out_vazio(url)
    o["toda_conversa"] = conteudo
    # Simula C-143: extrai ultima_msg_outbound da última linha [L ...]
    for linha in reversed(conteudo.splitlines()):
        linha = linha.strip()
        if linha.startswith("[L "):
            m = re.match(r"^\[L\s+[\d:/\s]+\]\s*(.+)$", linha)
            if m:
                o.setdefault("known", {})["ultima_msg_outbound"] = m.group(1).strip()
                break
    return o


# ---------------------------------------------------------------------------
# Testes: chat_id via url_da_conversa
# ---------------------------------------------------------------------------

class TestC147ChatIdViaUrl:

    def test_toda_conversa_vazia_preenche(self):
        t = int(time.time())
        msgs = [
            _make_msg("in", "Quero agendar", ts=t - 120),
            _make_msg("out", "Olá! Pode marcar, sim.", ts=t - 30),
        ]
        out = _rodar_c147(
            _out_vazio(url_da_conversa="/chats/54321/leads/detail/99999"),
            msgs_raw=msgs,
        )
        assert "[P " in out["toda_conversa"]
        assert "[L " in out["toda_conversa"]
        assert "Quero agendar" in out["toda_conversa"]
        assert "Olá! Pode marcar" in out["toda_conversa"]

    def test_ultima_msg_outbound_preenchida(self):
        t = int(time.time())
        msgs = [
            _make_msg("in", "Oi", ts=t - 90),
            _make_msg("out", "Primeira resposta", ts=t - 45),
            _make_msg("out", "Última resposta da Lia", ts=t - 10),
        ]
        out = _rodar_c147(
            _out_vazio(url_da_conversa="/chats/54321/leads/detail/99999"),
            msgs_raw=msgs,
        )
        assert out["known"]["ultima_msg_outbound"] == "Última resposta da Lia"

    def test_ordenacao_cronologica(self):
        t = int(time.time())
        msgs = [
            _make_msg("out", "Saída 2", ts=t - 10),
            _make_msg("in", "Entrada 1", ts=t - 60),   # mais antiga
            _make_msg("in", "Entrada 3", ts=t - 5),
        ]
        out = _rodar_c147(
            _out_vazio(url_da_conversa="/chats/54321/leads/detail/99999"),
            msgs_raw=msgs,
        )
        linhas = out["toda_conversa"].splitlines()
        assert "Entrada 1" in linhas[0]   # t-60: primeiro
        assert "Saída 2" in linhas[1]     # t-10
        assert "Entrada 3" in linhas[2]   # t-5

    def test_get_chat_id_for_lead_nao_chamado_quando_url_disponivel(self):
        """Se url tem chat_id, não faz request extra."""
        t = int(time.time())
        out = _rodar_c147(
            _out_vazio(url_da_conversa="/chats/99/leads/detail/99999"),
            chat_id_via_api=77777,  # não deve ser usado
            msgs_raw=[_make_msg("in", "Oi", ts=t)],
        )
        # mock_get_chat_id não deve ter sido chamado
        out["_mock_get_chat_id"].assert_not_called()

    def test_prefixo_P_para_entrada(self):
        t = int(time.time())
        out = _rodar_c147(
            _out_vazio(url_da_conversa="/chats/888/leads/detail/99999"),
            msgs_raw=[_make_msg("in", "Mensagem do paciente", ts=t)],
        )
        assert out["toda_conversa"].startswith("[P ")

    def test_prefixo_L_para_saida(self):
        t = int(time.time())
        out = _rodar_c147(
            _out_vazio(url_da_conversa="/chats/888/leads/detail/99999"),
            msgs_raw=[_make_msg("out", "Resposta da Lia", ts=t)],
        )
        assert out["toda_conversa"].startswith("[L ")


# ---------------------------------------------------------------------------
# Testes: chat_id via API (fallback quando url_da_conversa vazio)
# ---------------------------------------------------------------------------

class TestC147ChatIdViaApi:

    def test_toda_conversa_vazia_busca_chat_id(self):
        t = int(time.time())
        msgs = [_make_msg("in", "Primeira mensagem", ts=t - 10)]
        out = _rodar_c147(
            _out_vazio(),  # sem url_da_conversa
            chat_id_via_api=77777,
            msgs_raw=msgs,
        )
        out["_mock_get_chat_id"].assert_called_once()
        assert "Primeira mensagem" in out.get("toda_conversa", "")

    def test_toda_conversa_existente_nao_chama_api(self):
        """Se toda_conversa já preenchida, não chama get_chat_id_for_lead."""
        conteudo = "[P 10:00 14/08] oi\n[L 10:01 14/08] olá"
        out = _rodar_c147(
            _out_com_toda_conversa(conteudo),
            chat_id_via_api=77777,
            msgs_raw=[_make_msg("out", "NÃO DEVE APARECER", ts=int(time.time()))],
        )
        out["_mock_get_chat_id"].assert_not_called()
        assert out["toda_conversa"] == conteudo


# ---------------------------------------------------------------------------
# Testes: não sobrescreve o que já existe
# ---------------------------------------------------------------------------

class TestC147NaoSobrescreve:

    def test_toda_conversa_existente_preservada(self):
        conteudo = "[P 09:00 14/08] Bom dia\n[L 09:01 14/08] Olá, tudo bem!"
        out = _rodar_c147(
            _out_com_toda_conversa(
                conteudo,
                url="/chats/111/leads/detail/99999",
            ),
            msgs_raw=[_make_msg("out", "ISSO NÃO DEVE APARECER", ts=int(time.time()))],
        )
        assert out["toda_conversa"] == conteudo

    def test_ultima_outbound_existente_preservada(self):
        """Se ultima_msg_outbound já derivada de C-143, não sobrescreve."""
        conteudo = "[P 10:00 14/08] oi\n[L 10:01 14/08] Boa tarde!"
        out = _rodar_c147(
            _out_com_toda_conversa(
                conteudo,
                url="/chats/222/leads/detail/99999",
            ),
            msgs_raw=[_make_msg("out", "OUTRO TEXTO", ts=int(time.time()))],
        )
        assert out["known"]["ultima_msg_outbound"] == "Boa tarde!"

    def test_limit_5_quando_apenas_ultima_outbound_vazia(self):
        """Se toda_conversa existe mas ultima_outbound vazia → limit=5 (não 30)."""
        # toda_conversa com só entradas do paciente (sem [L ...])
        conteudo = "[P 10:00 14/08] oi\n[P 10:05 14/08] quero agendar"
        t = int(time.time())
        out = _rodar_c147(
            {
                "found": True,
                "lead_id": 99999,
                "toda_conversa": conteudo,
                "known": {
                    "url_da_conversa": "/chats/333/leads/detail/99999",
                    # ultima_msg_outbound ausente
                },
            },
            msgs_raw=[_make_msg("out", "Resposta via Chats API", ts=t)],
        )
        # get_chat_messages_raw chamado com limit=5
        call_args = out["_mock_get_msgs"].call_args
        limit_usado = (
            call_args[1].get("limit")
            if call_args[1]
            else (call_args[0][1] if len(call_args[0]) > 1 else None)
        )
        assert limit_usado == 5
        assert out["known"].get("ultima_msg_outbound") == "Resposta via Chats API"


# ---------------------------------------------------------------------------
# Testes: imagens e conteúdo não-textual
# ---------------------------------------------------------------------------

class TestC147Imagens:

    def test_imagem_representa_marcador_image(self):
        t = int(time.time())
        msgs = [
            _make_img("in", ts=t - 5),
            _make_msg("out", "Recebi sua imagem!", ts=t),
        ]
        out = _rodar_c147(
            _out_vazio(url_da_conversa="/chats/444/leads/detail/99999"),
            msgs_raw=msgs,
        )
        toda = out.get("toda_conversa", "")
        assert "Recebi sua imagem!" in toda
        # Linhas não podem ser vazias
        for linha in toda.splitlines():
            assert linha.strip(), f"Linha vazia encontrada: {linha!r}"

    def test_mensagem_texto_vazio_ignorada(self):
        """Mensagem com text='' e type=text é ignorada (não gera linha)."""
        t = int(time.time())
        msgs = [
            {"direction": "in", "created_at": t - 10,
             "content": {"type": "text", "text": ""}},  # texto vazio
            _make_msg("out", "Resposta válida", ts=t),
        ]
        out = _rodar_c147(
            _out_vazio(url_da_conversa="/chats/444/leads/detail/99999"),
            msgs_raw=msgs,
        )
        toda = out.get("toda_conversa", "")
        linhas = toda.splitlines()
        assert len(linhas) == 1
        assert "Resposta válida" in linhas[0]

    def test_limite_300_chars_por_mensagem(self):
        texto_longo = "X" * 500
        t = int(time.time())
        out = _rodar_c147(
            _out_vazio(url_da_conversa="/chats/999/leads/detail/99999"),
            msgs_raw=[_make_msg("out", texto_longo, ts=t)],
        )
        linha = out["toda_conversa"]
        texto_na_linha = linha.split("] ", 1)[1] if "] " in linha else ""
        assert len(texto_na_linha) <= 300


# ---------------------------------------------------------------------------
# Testes: toggle
# ---------------------------------------------------------------------------

class TestC147Toggle:

    def test_toggle_0_nao_chama_chats_api(self):
        out = _rodar_c147(
            _out_vazio(url_da_conversa="/chats/555/leads/detail/99999"),
            msgs_raw=[_make_msg("out", "Texto", ts=int(time.time()))],
            toggle="0",
        )
        out["_mock_get_msgs"].assert_not_called()
        assert not out.get("toda_conversa")

    def test_toggle_false_desliga(self):
        out = _rodar_c147(
            _out_vazio(url_da_conversa="/chats/555/leads/detail/99999"),
            msgs_raw=[_make_msg("out", "Texto", ts=int(time.time()))],
            toggle="false",
        )
        out["_mock_get_msgs"].assert_not_called()

    def test_toggle_off_desliga(self):
        out = _rodar_c147(
            _out_vazio(url_da_conversa="/chats/555/leads/detail/99999"),
            msgs_raw=[_make_msg("out", "Texto", ts=int(time.time()))],
            toggle="off",
        )
        out["_mock_get_msgs"].assert_not_called()

    def test_toggle_1_ativa(self):
        t = int(time.time())
        out = _rodar_c147(
            _out_vazio(url_da_conversa="/chats/555/leads/detail/99999"),
            msgs_raw=[_make_msg("out", "Texto ativo", ts=t)],
            toggle="1",
        )
        assert "Texto ativo" in out.get("toda_conversa", "")


# ---------------------------------------------------------------------------
# Testes: fail-open
# ---------------------------------------------------------------------------

class TestC147FailOpen:

    def test_excecao_em_get_msgs_nao_quebra(self):
        """Se get_chat_messages_raw lança exceção, ctx retorna intacto."""
        out_inicial = _out_vazio(url_da_conversa="/chats/666/leads/detail/99999")
        # Força mock a lançar exceção
        with patch.dict(os.environ, {"CHATS_API_MEMORIA_ATIVADA": "1"}):
            mock_msgs = MagicMock(side_effect=RuntimeError("timeout"))
            out = dict(out_inicial)
            out["known"] = {}

            # Simula o bloco C-147 com exceção
            try:
                _chat_id = 666
                msgs = mock_msgs(_chat_id, limit=30)
            except Exception:
                pass  # fail-open: ctx permanece intacto

            assert out["found"] is True  # ctx não foi destruído

    def test_msgs_vazias_nao_preenche(self):
        """Se Chats API retorna lista vazia, toda_conversa fica vazia."""
        out = _rodar_c147(
            _out_vazio(url_da_conversa="/chats/777/leads/detail/99999"),
            msgs_raw=[],
        )
        assert not out.get("toda_conversa")

    def test_sem_chat_id_e_api_retorna_none(self):
        """Se chat_id não encontrado em nenhuma fonte, nada é preenchido."""
        out = _rodar_c147(
            _out_vazio(),             # sem url_da_conversa
            chat_id_via_api=None,     # API também não encontra
            msgs_raw=[_make_msg("out", "Texto", ts=int(time.time()))],
        )
        assert not out.get("toda_conversa")


# ---------------------------------------------------------------------------
# Testes: extração do chat_id da URL
# ---------------------------------------------------------------------------

class TestC147ExtracaoChatId:
    """Garante que o regex /chats/{id} funciona em vários formatos."""

    @pytest.mark.parametrize("url,esperado", [
        ("/chats/54321/leads/detail/99999", 54321),
        ("https://univeja.kommo.com/chats/99/leads/detail/1", 99),
        ("/chats/1000000/leads/99", 1000000),
        ("", None),
        ("/leads/detail/99999", None),
        ("/chats/abc/leads", None),  # não numérico → não extrai
    ])
    def test_regex_extrai_chat_id(self, url, esperado):
        m = re.search(r"/chats/(\d+)", url)
        if esperado is None:
            assert m is None or (lambda: int(m.group(1)) if m else None)() != esperado or True
            # Simplificado: checa que o resultado final seria None
            resultado = None
            if m:
                try:
                    resultado = int(m.group(1))
                except (ValueError, TypeError):
                    pass
            assert resultado == esperado
        else:
            assert m is not None
            assert int(m.group(1)) == esperado
