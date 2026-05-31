"""Pytest blindando o auto-skip de field_ids órfãos no Kommo.

Cenário 30/05/2026: 3 campos foram deletados no painel Kommo
(ATIVADO_IA=1260635, HORA_ATIVACAO=1260639, e indiretamente ATENDENTE
em situações com lista 'pacientes'). Toda PATCH derrubava com HTTP 400
NotSupportedChoice e nenhum campo válido era salvo. Lia conversava
perfeitamente mas custom_fields=[] no painel.

Solução implementada: o builder kommo.update_lead_fields agora detecta
NotSupportedChoice no response, identifica qual field_id falhou, marca
como dead em _KOMMO_DEAD_FIELD_IDS, e tenta de novo SEM ele. Self-healing.

Esses testes garantem que:
  - O retry funciona pra 1 campo órfão
  - O retry escala pra múltiplos órfãos em sequência
  - A blacklist persiste entre chamadas (não esquece)
  - O builder pula automaticamente nas próximas chamadas
"""
from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest

import voice_agent.kommo as kommo_mod
from voice_agent.kommo import KommoClient, _KOMMO_DEAD_FIELD_IDS


@pytest.fixture(autouse=True)
def _clear_blacklist():
    """Cada teste começa com a blacklist limpa."""
    _KOMMO_DEAD_FIELD_IDS.clear()
    yield
    _KOMMO_DEAD_FIELD_IDS.clear()


def _make_client() -> KommoClient:
    return KommoClient(subdomain="test", token="test-token", timeout=1.0)


def _resp(status: int, body: dict | None = None):
    """Constrói um mock httpx.Response."""
    m = MagicMock()
    m.status_code = status
    m.text = "test"
    m.json = MagicMock(return_value=body or {})
    return m


def _not_supported_error(position: int) -> dict:
    """Constrói body de erro 400 do Kommo no formato real."""
    return {
        "validation-errors": [{
            "request_id": "0",
            "errors": [{
                "code": "NotSupportedChoice",
                "path": f"custom_fields_values.{position}.field_id",
                "detail": "The value you selected is not a valid choice.",
            }],
        }],
        "title": "Bad Request",
        "status": 400,
    }


class TestAutoSkipUmCampo:

    def test_um_campo_orfao_e_blacklisted_e_retry_sucede(self):
        client = _make_client()
        # Primeira tentativa: rejeita position 11 (ATENDENTE 1246419)
        # Segunda tentativa: 200 OK
        mock_patch = MagicMock(side_effect=[
            _resp(400, _not_supported_error(11)),
            _resp(200, {"id": 999}),
        ])
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.patch = mock_patch
        with patch.object(kommo_mod, "httpx") as mock_httpx:
            mock_httpx.Client = MagicMock(return_value=mock_client)
            # Fields que produzem 12 cfs incluindo ATENDENTE em position 11
            fields = {
                "name": "João Carlos",
                "convenio": "Não se aplica",
                "unidade": "Águas Claras",
                "medico": "Dr. Fabrício Freitas",
                "especialidade": "Catarata",
                "perfil_paciente": "Acima de 50 anos",
                "num_pacientes": "1",
                "numero_telefone": "81331005",
                "atendente": "Lia",
                "pacientes": [{
                    "nome": "João Carlos Silva",
                    "birth_date_iso": "1973-05-14",
                    "reason": "Catarata",
                    "cpf": "12345678900",
                }],
            }
            ok = client.update_lead_fields(24045059, fields)
        assert ok is True
        assert mock_patch.call_count == 2, "Deveria fazer 1 retry após NotSupportedChoice"
        assert 1246419 in _KOMMO_DEAD_FIELD_IDS, "ATENDENTE blacklisted"

    def test_blacklist_persiste_chamada_seguinte_pula_campo(self):
        client = _make_client()
        # Pre-blacklist o ATENDENTE
        _KOMMO_DEAD_FIELD_IDS.add(1246419)
        mock_patch = MagicMock(return_value=_resp(200, {"id": 999}))
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.patch = mock_patch
        with patch.object(kommo_mod, "httpx") as mock_httpx:
            mock_httpx.Client = MagicMock(return_value=mock_client)
            fields = {
                "name": "Joao Silva Souza",
                "unidade": "Águas Claras",
                "atendente": "Lia",  # vai ser filtrado
            }
            ok = client.update_lead_fields(11111, fields)
        assert ok is True
        # Patch chamado UMA vez (sem retry) — ATENDENTE foi pulado antes
        assert mock_patch.call_count == 1
        # Verifica que o payload enviado NÃO inclui 1246419
        call_kwargs = mock_patch.call_args.kwargs or {}
        cfs = (call_kwargs.get("json") or {}).get("custom_fields_values", [])
        sent_ids = [c.get("field_id") for c in cfs]
        assert 1246419 not in sent_ids, "Campo morto não pode entrar no payload"


class TestAutoSkipMultiplosCampos:

    def test_dois_campos_orfaos_em_sequencia(self):
        client = _make_client()
        # Tentativa 1: rejeita position 11. Tentativa 2: rejeita position 0.
        # Tentativa 3: 200 OK.
        mock_patch = MagicMock(side_effect=[
            _resp(400, _not_supported_error(11)),
            _resp(400, _not_supported_error(0)),
            _resp(200, {"id": 999}),
        ])
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.patch = mock_patch
        with patch.object(kommo_mod, "httpx") as mock_httpx:
            mock_httpx.Client = MagicMock(return_value=mock_client)
            fields = {
                "name": "Joao Silva Souza",
                "convenio": "Não se aplica",
                "unidade": "Águas Claras",
                "medico": "Dr. Fabrício Freitas",
                "especialidade": "Catarata",
                "perfil_paciente": "Acima de 50 anos",
                "num_pacientes": "1",
                "numero_telefone": "81331005",
                "atendente": "Lia",
                "pacientes": [{
                    "nome": "Paciente Auto Teste",
                    "birth_date_iso": "1973-05-14",
                    "reason": "Catarata",
                    "cpf": "12345678900",
                }],
            }
            ok = client.update_lead_fields(99999, fields)
        assert ok is True
        assert mock_patch.call_count == 3
        assert len(_KOMMO_DEAD_FIELD_IDS) >= 2


class TestRetryGracefulFailure:

    def test_erro_400_sem_validation_errors_nao_loopa(self):
        client = _make_client()
        # Body sem `validation-errors` — retry detecta que não há campo a
        # remover e desiste limpo.
        mock_patch = MagicMock(return_value=_resp(400, {"detail": "outro erro"}))
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.patch = mock_patch
        with patch.object(kommo_mod, "httpx") as mock_httpx:
            mock_httpx.Client = MagicMock(return_value=mock_client)
            fields = {"name": "Joao Silva Souza"}
            ok = client.update_lead_fields(11111, fields)
        assert ok is False
        # Só 1 tentativa porque não conseguiu identificar campo pra remover
        assert mock_patch.call_count == 1

    def test_cfs_vazio_apos_skip_total_retorna_true_sem_patch(self):
        client = _make_client()
        # Pre-blacklist TODOS os campos que viriam
        _KOMMO_DEAD_FIELD_IDS.add(1255757)  # NOME_PACIENTE_1
        mock_patch = MagicMock()
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.patch = mock_patch
        with patch.object(kommo_mod, "httpx") as mock_httpx:
            mock_httpx.Client = MagicMock(return_value=mock_client)
            fields = {"name": "Solo"}
            ok = client.update_lead_fields(11111, fields)
        # Sem campos pra enviar — sucesso vazio
        assert ok is True
        assert mock_patch.call_count == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
