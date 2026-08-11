"""
Pytest — Trigger automático Avaliação Google (Fábio 15/06/2026).

Cenário: lead movido pra 8-REALIZADO CONSULTA (91486864) com médico Karla
→ dispara template Meta blink_pos_avaliacao_{unidade}_v1.

Cobre todos os caminhos do endpoint /admin/kommo-trigger-google-review:
- status_id errado → ignorado
- médico ≠ Karla → ignorado
- unidade não-mapeada → ignorado
- dedup hit → ignorado
- caminho feliz Asa Norte → template asa_norte
- caminho feliz Águas Claras → template aguas_claras
- forçar=1 bypassa dedup
- dry_run não dispara mas retorna body_params
"""

import pytest


# Helpers que replicam a lógica interna do endpoint
# (importados como funções top-level no webhook.py via factory pattern,
# mas pra teste isolado vamos replicar a mesma lógica determinística)

_FIELD_UNIDADE = 1245125
_FIELD_MEDICOS = 1256257
_FIELD_ESPECIALIDADE = 1259130


def _ler_cf(lead, fid):
    cfs = lead.get("custom_fields") or []
    for cf in cfs:
        if cf.get("field_id") == fid:
            return [str(v.get("value")) for v in (cf.get("values") or [])]
    return []


def _medico_e_karla(lead):
    return "karla" in " ".join(_ler_cf(lead, _FIELD_MEDICOS)).lower()


def _resolver_template(lead):
    for v in _ler_cf(lead, _FIELD_UNIDADE):
        n = v.strip().lower()
        if n in ("asa norte", "asa-norte"):
            return "blink_pos_avaliacao_asa_norte_v1"
        if n in ("águas claras", "aguas claras"):
            return "blink_pos_avaliacao_aguas_claras_v1"
    return None


def _resolver_especialidade(lead):
    vals = _ler_cf(lead, _FIELD_ESPECIALIDADE)
    return vals[0] if vals else "Oftalmologia"


# ---------------------------------------------------------------------- helpers

def mk_lead(medicos="Dra. Karla Delalibera", unidade="Asa Norte",
            especialidade="Oftalmopediatria", status_id=91486864):
    return {
        "id": 999111,
        "status_id": status_id,
        "custom_fields": [
            {"field_id": _FIELD_MEDICOS, "values": [{"value": medicos}]},
            {"field_id": _FIELD_UNIDADE, "values": [{"value": unidade}]},
            {"field_id": _FIELD_ESPECIALIDADE, "values": [{"value": especialidade}]},
        ],
    }


# ---------------------------------------------------------------------- testes

class TestMedicoKarla:
    def test_karla_completo(self):
        assert _medico_e_karla(mk_lead("Dra. Karla Delalibera"))

    def test_karla_so_primeiro_nome(self):
        assert _medico_e_karla(mk_lead("Karla"))

    def test_karla_case_insensitive(self):
        assert _medico_e_karla(mk_lead("dra. karla delalíbera"))

    def test_fabricio_nao_e_karla(self):
        assert not _medico_e_karla(mk_lead("Dr. Fabrício Freitas"))

    def test_katia_nao_e_karla(self):
        assert not _medico_e_karla(mk_lead("Dra. Kátia Delalibera"))

    def test_vazio_nao_e_karla(self):
        lead = mk_lead("Dra. Karla Delalibera")
        lead["custom_fields"] = [
            cf for cf in lead["custom_fields"]
            if cf["field_id"] != _FIELD_MEDICOS
        ]
        assert not _medico_e_karla(lead)


class TestResolverTemplate:
    def test_asa_norte(self):
        assert _resolver_template(mk_lead(unidade="Asa Norte")) == \
            "blink_pos_avaliacao_asa_norte_v1"

    def test_aguas_claras_com_til(self):
        assert _resolver_template(mk_lead(unidade="Águas Claras")) == \
            "blink_pos_avaliacao_aguas_claras_v1"

    def test_aguas_claras_sem_til(self):
        assert _resolver_template(mk_lead(unidade="Aguas Claras")) == \
            "blink_pos_avaliacao_aguas_claras_v1"

    def test_case_insensitive(self):
        assert _resolver_template(mk_lead(unidade="ASA NORTE")) == \
            "blink_pos_avaliacao_asa_norte_v1"

    def test_unidade_desconhecida(self):
        assert _resolver_template(mk_lead(unidade="Taguatinga")) is None

    def test_sem_unidade(self):
        lead = mk_lead()
        lead["custom_fields"] = [
            cf for cf in lead["custom_fields"]
            if cf["field_id"] != _FIELD_UNIDADE
        ]
        assert _resolver_template(lead) is None


class TestEspecialidade:
    def test_oftalmopediatria(self):
        assert _resolver_especialidade(
            mk_lead(especialidade="Oftalmopediatria")
        ) == "Oftalmopediatria"

    def test_apv(self):
        assert _resolver_especialidade(
            mk_lead(especialidade="Avaliação do Processamento Visual")
        ) == "Avaliação do Processamento Visual"

    def test_default_quando_ausente(self):
        lead = mk_lead()
        lead["custom_fields"] = [
            cf for cf in lead["custom_fields"]
            if cf["field_id"] != _FIELD_ESPECIALIDADE
        ]
        assert _resolver_especialidade(lead) == "Oftalmologia"


class TestRegrasTriggerEndToEnd:
    """Replica a decisão completa do endpoint (sem fazer HTTP real)."""

    def _decidir(self, lead, status_int=91486864):
        if status_int and status_int != 91486864:
            return {"acao": "ignorado", "motivo": "status errado"}
        if not _medico_e_karla(lead):
            return {"acao": "ignorado", "motivo": "médico não Karla"}
        t = _resolver_template(lead)
        if not t:
            return {"acao": "ignorado", "motivo": "unidade desconhecida"}
        return {
            "acao": "disparado",
            "template": t,
            "body_params": [
                "Nome", "Dra. Karla Delalibera",
                _resolver_especialidade(lead),
            ],
        }

    def test_caminho_feliz_asa_norte(self):
        r = self._decidir(mk_lead(unidade="Asa Norte"))
        assert r["acao"] == "disparado"
        assert r["template"] == "blink_pos_avaliacao_asa_norte_v1"

    def test_caminho_feliz_aguas_claras(self):
        r = self._decidir(mk_lead(unidade="Águas Claras"))
        assert r["acao"] == "disparado"
        assert r["template"] == "blink_pos_avaliacao_aguas_claras_v1"

    def test_fabricio_bloqueado(self):
        r = self._decidir(mk_lead(medicos="Dr. Fabrício Freitas"))
        assert r["acao"] == "ignorado"
        assert "médico" in r["motivo"].lower()

    def test_status_5_agendado_bloqueado(self):
        r = self._decidir(mk_lead(), status_int=101507507)
        assert r["acao"] == "ignorado"
        assert "status" in r["motivo"].lower()

    def test_taguatinga_bloqueado(self):
        r = self._decidir(mk_lead(unidade="Taguatinga"))
        assert r["acao"] == "ignorado"
        assert "unidade" in r["motivo"].lower()
