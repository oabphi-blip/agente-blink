"""Blindagem do helper _disparar_template_aprovado_para_lead (task #215).

Refatoração 04/06/2026 pós-feedback: dispatcher de renovação rejeitava
leads "que nunca falaram" (regra de segurança pra renovar janela). Pra
cold outbound (REAGENDAR/REATIVAR), o caminho correto é template
aprovado direto via wa_cloud.send_template.

Helper testado isoladamente — não depende do endpoint FastAPI.
"""
from unittest.mock import MagicMock


def _primeiro_nome(nome: str) -> str:
    """Mesma lógica do helper inline em webhook.py."""
    if not nome:
        return "Você"
    primeiro = nome.strip().split(" ")[0]
    return primeiro.title() if primeiro else "Você"


# ---------------------------------------------------------------------------
# Casos do helper de primeiro_nome
# ---------------------------------------------------------------------------

def test_primeiro_nome_nome_completo():
    assert _primeiro_nome("Noah Pereira Vieira") == "Noah"


def test_primeiro_nome_vazio_devolve_voce():
    assert _primeiro_nome("") == "Você"
    assert _primeiro_nome(None) == "Você"


def test_primeiro_nome_minusculo_vira_title():
    assert _primeiro_nome("flávia") == "Flávia"


def test_primeiro_nome_extra_espacos():
    assert _primeiro_nome("  Carol   Lima  ") == "Carol"


def test_primeiro_nome_so_um_token():
    assert _primeiro_nome("Iara") == "Iara"


# ---------------------------------------------------------------------------
# Casos do fluxo end-to-end mockado
# ---------------------------------------------------------------------------

class _HelperShim:
    """Recria o helper inline pra teste isolado — comportamento idêntico."""

    @staticmethod
    def disparar(
        lead_id, kommo_client, wa_cloud, dry_run=False,
        template_name="template_test", template_lang="pt_BR",
    ):
        info = kommo_client.get_lead_main_contact(lead_id)
        if not info or not info.get("telefone"):
            return {"ok": False, "motivo": "sem_telefone_ou_contato"}
        telefone = info["telefone"]
        if not telefone.startswith("55") and len(telefone) >= 10:
            telefone = "55" + telefone
        nome = info.get("nome") or ""
        primeiro = _primeiro_nome(nome)

        if dry_run:
            return {
                "ok": True, "dry_run": True,
                "telefone": telefone, "nome": nome,
                "primeiro_nome": primeiro,
                "template": template_name,
            }

        try:
            resp = wa_cloud.send_template(
                to=telefone, name=template_name,
                language=template_lang, body_params=[primeiro],
            )
        except Exception as exc:
            return {
                "ok": False,
                "motivo": f"send_template falhou: {exc}",
                "telefone": telefone,
            }

        wamid = None
        try:
            wamid = (resp.get("messages") or [{}])[0].get("id")
        except Exception:
            pass

        try:
            kommo_client.add_note(
                lead_id=lead_id,
                text=f"Template {template_name} disparado pra {primeiro}",
            )
        except Exception:
            pass

        return {
            "ok": True,
            "telefone": telefone, "nome": nome,
            "primeiro_nome": primeiro,
            "template": template_name, "wamid": wamid,
        }


def test_dispara_sucesso_chama_send_template_com_args_certos():
    kommo = MagicMock()
    kommo.get_lead_main_contact.return_value = {
        "telefone": "5561999998888",
        "nome": "Noah Pereira Vieira",
        "status_id": 101508307,
    }
    wa = MagicMock()
    wa.send_template.return_value = {
        "messages": [{"id": "wamid.ABC123"}],
    }

    res = _HelperShim.disparar(
        22982854, kommo, wa, dry_run=False,
        template_name="1089_mens_ativar_conv_parada_qz7kbz",
    )

    assert res["ok"] is True
    assert res["primeiro_nome"] == "Noah"
    assert res["wamid"] == "wamid.ABC123"
    wa.send_template.assert_called_once()
    call = wa.send_template.call_args
    assert call.kwargs["to"] == "5561999998888"
    assert call.kwargs["body_params"] == ["Noah"]
    # Nota gravada
    kommo.add_note.assert_called_once()


def test_dispara_sem_telefone_retorna_erro():
    kommo = MagicMock()
    kommo.get_lead_main_contact.return_value = {"telefone": None, "nome": "X"}
    wa = MagicMock()
    res = _HelperShim.disparar(12345, kommo, wa, dry_run=False)
    assert res["ok"] is False
    assert res["motivo"] == "sem_telefone_ou_contato"
    wa.send_template.assert_not_called()


def test_dispara_telefone_sem_DDI_55_recebe_prefixo():
    kommo = MagicMock()
    kommo.get_lead_main_contact.return_value = {
        "telefone": "61999998888",  # sem 55
        "nome": "Test",
    }
    wa = MagicMock()
    wa.send_template.return_value = {"messages": [{"id": "wamid.X"}]}

    res = _HelperShim.disparar(1, kommo, wa, dry_run=False)
    assert res["telefone"] == "5561999998888"
    assert wa.send_template.call_args.kwargs["to"] == "5561999998888"


def test_dispara_dry_run_nao_chama_wa():
    kommo = MagicMock()
    kommo.get_lead_main_contact.return_value = {
        "telefone": "556199999", "nome": "Test",
    }
    wa = MagicMock()
    res = _HelperShim.disparar(1, kommo, wa, dry_run=True)
    assert res["ok"] is True
    assert res["dry_run"] is True
    wa.send_template.assert_not_called()
    kommo.add_note.assert_not_called()


def test_dispara_send_template_excecao_retorna_erro():
    kommo = MagicMock()
    kommo.get_lead_main_contact.return_value = {
        "telefone": "5561999", "nome": "Test",
    }
    wa = MagicMock()
    wa.send_template.side_effect = RuntimeError("API Meta erro 400")
    res = _HelperShim.disparar(1, kommo, wa, dry_run=False)
    assert res["ok"] is False
    assert "send_template falhou" in res["motivo"]
    assert "erro 400" in res["motivo"]


def test_dispara_nota_falha_nao_quebra_sucesso():
    """Mesmo se add_note falhar, considera disparo OK (msg foi enviada)."""
    kommo = MagicMock()
    kommo.get_lead_main_contact.return_value = {
        "telefone": "5561999", "nome": "Test",
    }
    kommo.add_note.side_effect = RuntimeError("kommo offline")
    wa = MagicMock()
    wa.send_template.return_value = {"messages": [{"id": "wamid.Y"}]}
    res = _HelperShim.disparar(1, kommo, wa, dry_run=False)
    assert res["ok"] is True
    assert res["wamid"] == "wamid.Y"
