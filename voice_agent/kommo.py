"""Cliente Kommo CRM para auto-preenchimento de leads.

Usa Long-Lived JWT como Bearer. Endpoints v4:
- GET /api/v4/leads?query=<phone>   → busca lead por telefone do contato
- PATCH /api/v4/leads/{id}          → atualiza custom_fields_values

Mapeamento dos campos custom segue o ID/enum do Kommo univeja
(descobertos via list_custom_fields). Esse mapa é fixo no código —
se algum campo for renomeado no Kommo, atualizar aqui também.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

import httpx

log = logging.getLogger(__name__)


# ============================================================
# Mapa de campos (univeja.kommo.com)
# ============================================================

# Tipo SELECT (única opção) — id do campo + dict {valor → enum_id}
FIELD_CONVENIO = (853206, {
    "Pro ser STJ": 908265, "Pro Ser STJ": 908265, "STJ": 908265, "Pro Ser": 908265,
    "Bacen": 610306, "Casec": 610316, "Codevasf": 610316,
    "Casembrapa": 610318, "Embrapa": 610318,
    "Conab": 610324,
    "E-vida": 610326, "Luminar": 610326, "E-Vida": 610326,
    "Fascal": 610334,
    "Omint": 610348,
    "PF Saúde": 610356, "PF Saude": 610356, "Polícia Federal": 610356,
    "Plan Assiste": 610358, "MPF": 610358, "MPU": 610358, "MPT": 610358, "MPDFT": 610358,
    "ProSaúde": 610362, "Pro-Saúde": 610362, "Câmara dos Deputados": 610362,
    "Proasa": 610364,
    "Saúde Caixa": 610368, "Caixa": 610368,
    "Petrobrás": 610370, "Petrobras": 610370,
    "Serpro": 610372,
    "SIS Senado": 610374, "Senado": 610374,
    "STF-Med": 610376, "STF": 610376,
    "TRE": 610384, "TRE Saúde": 610384,
    "TRF": 610386, "Pro-social TRF": 610386,
    "TRT": 610388, "TRT Saúde": 610388,
    "TST": 610392, "TST Saúde": 610392,
    "TJDFT": 905132, "TJ DFT": 905132,
    "Care Plus": 908653, "CarePlus": 908653,
    "Anafe": 914499,
    "Plas/JMU": 924924, "STM": 924924, "STM Plas": 924924,
    "Inas GDF": 925312,
    "Não se aplica": 906979, "Particular": 906979, "Sem convênio": 906979,
})

FIELD_UNIDADE = (1245125, {
    "Asa Norte": 905963,
    "Águas Claras": 905961, "Aguas Claras": 905961,
    "Asa Sul": 925828,
})

FIELD_NUMERO_PACIENTES = (1259118, {
    "1": 923818, "2": 923820, "3": 923822, "4": 923824, "5": 923826,
    "6": 925218, "7": 925220, "8": 925222, "9": 925224, "10": 925226,
})

# Tipo MULTISELECT (lista) — mesma forma, ids
FIELD_MEDICOS = (1256257, {
    "Dra. Karla Delalibera": 919833, "Dra Karla": 919833, "Karla Delalibera": 919833,
    "Karla Delalíbera": 919833, "Dra Karla Delalíbera": 919833,
    "Dr. Fabrício Freitas": 919835, "Dr Fabricio": 919835, "Fabricio Freitas": 919835,
    "Fabrício Freitas": 919835, "Dr Fabrício": 919835, "Dr. Fabricio": 919835,
    "Dra. Kátia Delalibera": 919837, "Dra Katia": 919837, "Katia Delalibera": 919837,
    "Kátia Delalíbera": 919837, "Dra Kátia": 919837,
    "Dr. Marcelo Paraíba": 925166,
    "Dra. Isabela Nacarato": 925256,
})

FIELD_ESPECIALIDADE = (1259130, {
    "Oftalmopediatria": 923858, "Pediatria": 923858, "Oftalmopediatra": 923858,
    "Oftalmologia Geral": 923860, "Rotina": 923860, "Check-up": 923860,
    "SDP": 923862, "Síndrome Deficiência Postural": 923862, "Postural": 923862,
    "Estrabismo": 923864,
    "Retina": 923868, "Retina e vítreo": 923868, "Retina e Vítreo": 923868,
    "Uveíte": 923870,
    "Plástica": 923872,
    "Refrativa": 924832,
    "Catarata": 924930,
    "Lentes": 924934, "Lentes de contato": 924934,
    "Consulta Domiciliar": 925894, "Domiciliar": 925894,
})

# ⚠️ DESATIVADO — o campo "Tipo de agendamento" (id 1260438) NÃO existe na
# conta univeja.kommo.com. Enviá-lo fazia o Kommo rejeitar o PATCH inteiro
# com HTTP 400 (NotSupportedChoice em custom_fields_values.N.field_id).
# Mantido só como referência; não é mais usado em update_lead_fields.
FIELD_TIPO_AGENDAMENTO = (1260438, {
    "Fixo": 926254, "Fixo/Definido": 926254, "Definido": 926254,
    "Encaixe": 926140,
    "Domiciliar": 926202,
})

FIELD_PERFIL_PACIENTE_1 = (1257961, {
    "Bebê 0-2": 922309, "Bebê": 922309, "Bebe 0-2": 922309,
    "Criança 3-12": 922311, "Criança": 922311, "Crianca": 922311,
    "Adolescente 13-18": 923406, "Adolescente": 923406,
    "Adulto de 19 a 49": 922313, "Adulto 19-49": 922313, "Adulto": 922313,
    "Acima de 50": 922315, "Idoso": 922315,
})

# Textareas / textos livres
FIELD_NOME_PACIENTE_1 = 1255757
FIELD_MOTIVO_PACIENTE_1 = 1255727
FIELD_DIA_TURNO_PERIODO = 1259960  # "DIA/TURNO/PERÍODO ⚠️" — preferência textual

# Date (timestamp YYYY-MM-DDTHH:MM:SS-03:00)
FIELD_DATA_NASCIMENTO_PACIENTE_1 = 1259984


def _format_date_iso(iso_yyyymmdd: str) -> Optional[str]:
    """Converte 'YYYY-MM-DD' em 'YYYY-MM-DDT00:00:00-03:00' (BRT)."""
    if not iso_yyyymmdd or len(iso_yyyymmdd) < 10:
        return None
    return f"{iso_yyyymmdd[:10]}T00:00:00-03:00"


def _pick_enum(table: dict[str, int], value: str) -> Optional[int]:
    """Faz match case-insensitive + sem acento na tabela de enum."""
    if not value:
        return None
    import unicodedata
    def norm(s: str) -> str:
        s = unicodedata.normalize("NFD", s.strip())
        s = "".join(c for c in s if unicodedata.category(c) != "Mn")
        return s.lower()
    target = norm(value)
    for k, v in table.items():
        if norm(k) == target:
            return v
    # Fallback: prefixo
    for k, v in table.items():
        if target.startswith(norm(k)) or norm(k).startswith(target):
            return v
    return None


@dataclass
class KommoClient:
    subdomain: str
    token: str
    timeout: float = 8.0

    @property
    def _base(self) -> str:
        return f"https://{self.subdomain}.kommo.com/api/v4"

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    # ----------------------- busca lead por telefone

    def find_lead_id_by_phone(self, phone: str) -> Optional[int]:
        """Busca lead pelo telefone. Retorna o ID do mais recente.

        Tenta variações BR (com/sem o 9 extra) automaticamente.
        """
        candidates: list[str] = []
        normalized = (phone or "").replace("+", "").replace(" ", "").replace("-", "")
        if normalized:
            candidates.append(normalized)
            # Variantes BR
            if normalized.startswith("55") and len(normalized) in (12, 13):
                ddd = normalized[2:4]
                rest = normalized[4:]
                if len(normalized) == 13 and rest.startswith("9"):
                    candidates.append("55" + ddd + rest[1:])
                elif len(normalized) == 12:
                    candidates.append("55" + ddd + "9" + rest)
            # Last 8 digits (fallback robusto)
            if len(normalized) >= 8:
                candidates.append(normalized[-8:])

        seen: set[str] = set()
        for q in candidates:
            if q in seen:
                continue
            seen.add(q)
            try:
                with httpx.Client(timeout=self.timeout) as c:
                    r = c.get(
                        f"{self._base}/leads",
                        params={"query": q, "limit": 5, "order[updated_at]": "desc"},
                        headers=self._headers,
                    )
                if r.status_code == 204:
                    continue
                if r.status_code != 200:
                    log.warning("Kommo find_lead failed (q=%s): HTTP %d", q, r.status_code)
                    continue
                data = r.json() or {}
                leads = ((data.get("_embedded") or {}).get("leads") or [])
                if leads:
                    return int(leads[0]["id"])
            except Exception as e:  # noqa: BLE001
                log.warning("Kommo find_lead error (q=%s): %s", q, e)
        return None

    # ----------------------- update lead

    def update_lead_fields(self, lead_id: int, fields: dict) -> bool:
        """Atualiza custom_fields_values do lead.

        `fields` é um dict {nome_semântico: valor} com chaves:
          name, birth_date_iso (YYYY-MM-DD), reason,
          convenio, unidade, medico, especialidade, tipo_agendamento,
          perfil_paciente, num_pacientes, dia_turno_periodo
        """
        cfs: list[dict[str, Any]] = []

        def add_text(field_id: int, val: Optional[str]):
            if val:
                cfs.append({"field_id": field_id, "values": [{"value": val}]})

        def add_select(field_def: tuple[int, dict], val: Optional[str]):
            if not val:
                return
            field_id, table = field_def
            enum_id = _pick_enum(table, val)
            if enum_id is None:
                log.warning("Kommo: valor '%s' não casa com enum do campo %d", val, field_id)
                return
            cfs.append({"field_id": field_id, "values": [{"enum_id": enum_id}]})

        def add_date(field_id: int, val: Optional[str]):
            iso = _format_date_iso(val) if val else None
            if iso:
                cfs.append({"field_id": field_id, "values": [{"value": iso}]})

        add_text(FIELD_NOME_PACIENTE_1, fields.get("name"))
        add_text(FIELD_MOTIVO_PACIENTE_1, fields.get("reason"))
        add_text(FIELD_DIA_TURNO_PERIODO, fields.get("dia_turno_periodo"))
        add_date(FIELD_DATA_NASCIMENTO_PACIENTE_1, fields.get("birth_date_iso"))
        add_select(FIELD_CONVENIO, fields.get("convenio"))
        add_select(FIELD_UNIDADE, fields.get("unidade"))
        add_select(FIELD_MEDICOS, fields.get("medico"))
        add_select(FIELD_ESPECIALIDADE, fields.get("especialidade"))
        # FIELD_TIPO_AGENDAMENTO desativado — campo 1260438 não existe no Kommo
        # e derrubava o PATCH inteiro com HTTP 400.
        add_select(FIELD_PERFIL_PACIENTE_1, fields.get("perfil_paciente"))
        add_select(FIELD_NUMERO_PACIENTES, fields.get("num_pacientes"))

        if not cfs:
            return True

        payload = {"custom_fields_values": cfs}
        try:
            with httpx.Client(timeout=self.timeout) as c:
                r = c.patch(
                    f"{self._base}/leads/{lead_id}",
                    json=payload,
                    headers=self._headers,
                )
            if r.status_code // 100 == 2:
                log.info("Kommo lead %d atualizado: %d campos", lead_id, len(cfs))
                return True
            log.warning(
                "Kommo update lead %d falhou: HTTP %d — %s",
                lead_id, r.status_code, (r.text or "")[:300],
            )
        except Exception as e:  # noqa: BLE001
            log.warning("Kommo update error: %s", e)
        return False

    # ----------------------- nota (registro da conversa)

    def add_note(self, lead_id: int, text: str) -> bool:
        """Adiciona uma nota de texto ('common') na linha do tempo do lead.

        Usado para registrar as trocas de mensagem do agente — assim a
        equipe acompanha o andamento no Kommo, mesmo nos canais que não
        passam pelo chat nativo (8133 via API oficial, 0710 via Evolution).
        """
        if not text:
            return False
        payload = [{"note_type": "common", "params": {"text": text[:5000]}}]
        try:
            with httpx.Client(timeout=self.timeout) as c:
                r = c.post(
                    f"{self._base}/leads/{lead_id}/notes",
                    json=payload,
                    headers=self._headers,
                )
            if r.status_code // 100 == 2:
                log.info("Kommo nota gravada no lead %d", lead_id)
                return True
            log.warning(
                "Kommo add_note lead %d falhou: HTTP %d — %s",
                lead_id, r.status_code, (r.text or "")[:300],
            )
        except Exception as e:  # noqa: BLE001
            log.warning("Kommo add_note error: %s", e)
        return False

    # ----------------------- enriquecimento de contexto (onboarding)

    def get_caller_context(self, phone: str) -> dict:
        """Onboarding por telefone: busca o lead e o que o CRM já sabe.

        Usado no caminho Evolution (0710). Retorna:
        {found, lead_id, name, known:{campo:valor}}
        """
        lead_id = self.find_lead_id_by_phone(phone)
        if not lead_id:
            return {"found": False, "lead_id": None, "name": None, "known": {}}
        return self.get_caller_context_by_lead(lead_id)

    # ----------------------- reativação de leads frios

    def list_leads_by_status(
        self, pipeline_id: int, status_ids: list[int], limit: int = 200,
    ) -> list[dict]:
        """Lista leads de um pipeline que estejam em qualquer uma das etapas
        informadas. Ordenado por updated_at asc (mais parados primeiro).

        Usa a API REST direta do Kommo (filter[statuses]) — diferente da
        busca textual, aqui o filtro por etapa funciona de fato.
        """
        params: dict[str, Any] = {
            "limit": min(int(limit), 250),
            "order[updated_at]": "asc",
        }
        for i, sid in enumerate(status_ids):
            params[f"filter[statuses][{i}][pipeline_id]"] = pipeline_id
            params[f"filter[statuses][{i}][status_id]"] = sid
        try:
            with httpx.Client(timeout=self.timeout) as c:
                r = c.get(f"{self._base}/leads", params=params, headers=self._headers)
            if r.status_code == 204:
                return []
            if r.status_code != 200:
                log.warning("Kommo list_leads_by_status: HTTP %d", r.status_code)
                return []
            data = r.json() or {}
            return [
                {"id": ld["id"], "name": ld.get("name"),
                 "status_id": ld.get("status_id")}
                for ld in ((data.get("_embedded") or {}).get("leads") or [])
            ]
        except Exception as e:  # noqa: BLE001
            log.warning("Kommo list_leads_by_status erro: %s", e)
            return []

    def get_lead_main_phone(self, lead_id: int | str) -> Optional[str]:
        """Retorna o telefone (só dígitos) do contato principal do lead."""
        try:
            with httpx.Client(timeout=self.timeout) as c:
                r = c.get(
                    f"{self._base}/leads/{lead_id}",
                    params={"with": "contacts"}, headers=self._headers,
                )
                if r.status_code != 200:
                    return None
                contacts = (
                    ((r.json() or {}).get("_embedded") or {}).get("contacts") or []
                )
                if not contacts:
                    return None
                main = next(
                    (ct for ct in contacts if ct.get("is_main")), contacts[0]
                )
                cid = main.get("id")
                if not cid:
                    return None
                r2 = c.get(f"{self._base}/contacts/{cid}", headers=self._headers)
                if r2.status_code != 200:
                    return None
                for cf in ((r2.json() or {}).get("custom_fields_values") or []):
                    if cf.get("field_code") == "PHONE":
                        vals = cf.get("values") or []
                        if vals and vals[0].get("value"):
                            digits = "".join(
                                ch for ch in str(vals[0]["value"]) if ch.isdigit()
                            )
                            return digits or None
        except Exception as e:  # noqa: BLE001
            log.warning("Kommo get_lead_main_phone erro (lead %s): %s", lead_id, e)
        return None

    def update_lead_status(
        self, lead_id: int, status_id: int, pipeline_id: Optional[int] = None,
    ) -> bool:
        """Move o lead para outra etapa do funil."""
        payload: dict[str, Any] = {"status_id": status_id}
        if pipeline_id:
            payload["pipeline_id"] = pipeline_id
        try:
            with httpx.Client(timeout=self.timeout) as c:
                r = c.patch(
                    f"{self._base}/leads/{lead_id}",
                    json=payload, headers=self._headers,
                )
            if r.status_code // 100 == 2:
                return True
            log.warning(
                "Kommo update_lead_status lead %s falhou: HTTP %d",
                lead_id, r.status_code,
            )
        except Exception as e:  # noqa: BLE001
            log.warning("Kommo update_lead_status erro: %s", e)
        return False

    # ----------------------- enriquecimento de contexto (onboarding)

    def get_caller_context_by_lead(self, lead_id: int | str) -> dict:
        """Onboarding por lead_id direto — usado no caminho Kommo (8133),
        onde o widget_request já entrega o lead_id."""
        out: dict = {
            "found": True, "lead_id": int(lead_id), "name": None, "known": {},
        }
        try:
            with httpx.Client(timeout=self.timeout) as c:
                r = c.get(
                    f"{self._base}/leads/{lead_id}",
                    params={"with": "contacts"},
                    headers=self._headers,
                )
            if r.status_code != 200:
                return out
            data = r.json() or {}
            id_to_label = {
                FIELD_NOME_PACIENTE_1: "nome_paciente",
                FIELD_MOTIVO_PACIENTE_1: "motivo",
                FIELD_CONVENIO[0]: "convenio",
                FIELD_UNIDADE[0]: "unidade",
                FIELD_MEDICOS[0]: "medico",
                FIELD_ESPECIALIDADE[0]: "especialidade",
                FIELD_DIA_TURNO_PERIODO: "dia_turno",
            }
            for cf in (data.get("custom_fields_values") or []):
                fid = cf.get("field_id")
                label = id_to_label.get(fid)
                if not label:
                    continue
                vals = cf.get("values") or []
                if vals:
                    v = vals[0].get("value")
                    if v:
                        out["known"][label] = v
                        if label == "nome_paciente":
                            out["name"] = v
        except Exception as e:  # noqa: BLE001
            log.warning("Kommo get_caller_context_by_lead erro: %s", e)
        return out
