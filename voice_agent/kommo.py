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
import time
from dataclasses import dataclass
from datetime import datetime
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

# Tipo MULTISELECT — campo AÇÕES (workflow interno da equipe)
FIELD_ACOES = (1259312, {
    "Agendar Encaixe": 925134, "Encaixe": 925134,
    "Agendar Domiciliar": 925336, "Domiciliar": 925336,
})

# "Ñ ACEITO CONVÊNIO" — convênio que o paciente queria usar mas a clínica
# NÃO credencia. Preenchido quando o lead insiste no convênio não aceito.
FIELD_NAO_ACEITO_CONVENIO = (1175268, {
    "Afeb": 897198,
    "Amil": 843464,
    "Assefaz": 843504,
    "Bradesco": 902366, "Bradesco Saúde": 902366,
    "Bradesco Top Nacional": 902366, "Bradesco Saude": 902366,
    "BRB": 902824, "BRB Saúde": 902824, "BRB Saude": 902824,
    "Cassi": 841860,
    "Fusex": 919143,
    "GEAP": 898162,
    "HAP VIDA": 898284, "Hapvida": 898284, "Hap Vida": 898284, "HapVida": 898284,
    "Inas GDF": 923352, "Inas": 923352,
    "Notre Dame": 921367, "NotreDame": 921367, "Notredame": 921367,
    "PM": 921427, "Polícia Militar": 921427, "Policia Militar": 921427,
    "Porto Seguro": 895650,
    "SUS": 921395,
    "Sul América": 843502, "Sul America": 843502, "SulAmérica": 843502,
    "Unimed": 898838,
    "Outro": 926611,
})

# "MOTIVOS PERDA" (multiselect) — motivo do lead perdido.
FIELD_MOTIVOS_PERDA = (1260434, {
    "Somente Convênio": 926086, "Somente Convenio": 926086,
    "Só Convênio": 926086, "Só com Convênio": 926086,
})

# "NUMERO TELEFONE" (multiselect) — canal por onde o lead fala com a
# clínica. Carimbado pelo agente conforme a porta de entrada da mensagem.
FIELD_NUMERO_TELEFONE = (1260633, {
    "81331005": 926673, "8133": 926673, "8133-1005": 926673,
    "96630710": 926675, "0710": 926675, "9663-0710": 926675,
})

# "ATIVADO IA?" (multiselect) — indica se a IA está conduzindo o lead.
# ATIVADO: a Lia acabou de processar uma mensagem neste lead.
# DESATIVADO: handoff humano detectado (mensagem manual / pausa de handoff).
FIELD_ATIVADO_IA = (1260635, {
    "ATIVADO": 926677, "ATIVA": 926677, "ATIVO": 926677, "ON": 926677,
    "DESATIVADO": 926679, "DESATIVADA": 926679, "OFF": 926679,
})

# "HORA ATIVAÇÃO" (date_time) — momento em que a IA foi REATIVADA, ou seja,
# voltou a atuar depois de ter estado DESATIVADA (após atendimento humano).
FIELD_HORA_ATIVACAO = 1260639

# "ATENDENTE (s)" (multiselect) — quem está conduzindo o atendimento.
# A Lia carimba "Lia" sempre que a IA processa uma mensagem do lead.
FIELD_ATENDENTE = (1246419, {
    "LIA": 926681, "IA": 926681, "AGENTE": 926681,
})

# Status "Closed - lost" (Venda perdida) — id reservado, vale em qualquer funil.
STATUS_CLOSED_LOST = 143

# Textareas / textos livres
FIELD_NOME_PACIENTE_1 = 1255757
FIELD_MOTIVO_PACIENTE_1 = 1255727
FIELD_DIA_TURNO_PERIODO = 1259960  # "DIA/TURNO/PERÍODO ⚠️" — preferência textual
FIELD_DIA_CONSULTA_1 = 1255723     # "1.DIA CONSULTA" (date_time) — data/hora confirmada

# Date (timestamp YYYY-MM-DDTHH:MM:SS-03:00)
FIELD_DATA_NASCIMENTO_PACIENTE_1 = 1259984

# ----------------------- camada MULTIPACIENTE (fichas 1 a 6)
# Cada lead pode ter até 6 pacientes (ex.: mãe agendando vários filhos).
# Mapas numerados {n: field_id} para gravar a ficha de cada paciente.
FIELD_NOME_PACIENTES = {
    1: 1255757, 2: 1255761, 3: 1255779,
    4: 1255925, 5: 1257661, 6: 1260332,
}
FIELD_NASC_PACIENTES = {
    1: 1259984, 2: 1255729, 3: 1255787,
    4: 1255927, 5: 1257663, 6: 1260334,
}
FIELD_MOTIVO_PACIENTES = {
    1: 1255727, 2: 1255733, 3: 1255783,
    4: 1255929, 5: 1257665, 6: 1260338,
}
# CPF — necessário para o agendamento no Medware.
FIELD_CPF_PACIENTE_1 = 1260414
# COD-AGENDAMENTO (numeric) — id do agendamento criado no Medware via API.
FIELD_COD_AGENDAMENTO = 1260645
FIELD_CPF_PACIENTES = {
    1: 1260414, 2: 1260416, 3: 1260418,
    4: 1260548, 5: 1260422, 6: 1260424,
}

# Etapas do funil ATENDE em que o agente fica DESLIGADO — tratamento
# conduzido por humanos ou contato que não é paciente (fornecedor).
ST_AGENT_OFF = frozenset({
    106563343,  # 0-ATENDIMENTO HUMANO — atendente assumiu de propósito
    106157139,  # 7-CIRURGIAS ANDAMENTO
    106484343,  # 8-LENTES ANDAMENTO
    106484347,  # 9-FORNECEDORES
    101109455,  # 5-CONFIRMAR — paciente respondendo template de confirmação
    106653499,  # 6-CONFIRMADO — consulta já confirmada
})

# Nomes legíveis das etapas do funil ATENDE (status_id → nome).
ST_NAMES = {
    96441724: "0-ETAPA ENTRADA",
    106563343: "0-ATENDIMENTO HUMANO",
    101508307: "1.LEADS FRIO",
    102560495: "2-AGENDAR",
    106184631: "3.REAGENDAR",
    101507507: "4-AGENDADO",
    101109455: "5-CONFIRMAR OU CONFIRMADO",
    106184983: "5.1-NO-SHOW",
    91486864: "6-REALIZADO CONSULTA",
    106157139: "7-CIRURGIAS ANDAMENTO",
    106484343: "8-LENTES ANDAMENTO",
    106484347: "9-FORNECEDORES",
    106157327: "10-PRÓXIMA CONSULTA",
    142: "Closed - won",
    143: "Closed - lost",
}

# Etapas que significam que o lead JÁ TEM consulta marcada ou realizada —
# a conversa é confirmação/dúvida, NUNCA um novo agendamento do zero.
ST_JA_AGENDADO = frozenset({
    101507507,  # 4-AGENDADO
    101109455,  # 5-CONFIRMAR OU CONFIRMADO
    91486864,   # 6-REALIZADO CONSULTA
    106157327,  # 10-PRÓXIMA CONSULTA
})


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

        def add_datetime(field_id: int, ts: Optional[int]):
            """Campo date_time do Kommo — valor é timestamp Unix (segundos)."""
            if ts:
                cfs.append(
                    {"field_id": field_id, "values": [{"value": int(ts)}]}
                )

        # ── Fichas dos pacientes (camada multipaciente) ──────────────
        # Se a extração trouxe a lista `pacientes`, grava a ficha de cada
        # um nos campos numerados 1..6 (nome, nascimento, motivo, CPF).
        # Senão, usa os campos simples (compatibilidade — paciente único).
        def _digits(v: Any) -> str:
            return "".join(ch for ch in str(v or "") if ch.isdigit())

        pacientes = fields.get("pacientes")
        if isinstance(pacientes, list) and pacientes:
            for idx, p in enumerate(pacientes[:6], start=1):
                if not isinstance(p, dict):
                    continue
                add_text(FIELD_NOME_PACIENTES[idx],
                         p.get("nome") or p.get("name"))
                add_date(FIELD_NASC_PACIENTES[idx], p.get("birth_date_iso"))
                add_text(FIELD_MOTIVO_PACIENTES[idx],
                         p.get("reason") or p.get("motivo"))
                add_text(FIELD_CPF_PACIENTES[idx],
                         _digits(p.get("cpf")) or None)
            # nº de pacientes — rede de segurança se a extração não trouxe
            fields.setdefault("num_pacientes", str(min(len(pacientes), 10)))
        else:
            add_text(FIELD_NOME_PACIENTE_1, fields.get("name"))
            add_text(FIELD_MOTIVO_PACIENTE_1, fields.get("reason"))
            add_text(FIELD_CPF_PACIENTE_1, _digits(fields.get("cpf")) or None)
            add_date(FIELD_DATA_NASCIMENTO_PACIENTE_1,
                     fields.get("birth_date_iso"))
        add_text(FIELD_DIA_TURNO_PERIODO, fields.get("dia_turno_periodo"))
        add_select(FIELD_CONVENIO, fields.get("convenio"))
        add_select(FIELD_UNIDADE, fields.get("unidade"))
        add_select(FIELD_MEDICOS, fields.get("medico"))
        add_select(FIELD_ESPECIALIDADE, fields.get("especialidade"))
        # FIELD_TIPO_AGENDAMENTO desativado — campo 1260438 não existe no Kommo
        # e derrubava o PATCH inteiro com HTTP 400.
        add_select(FIELD_PERFIL_PACIENTE_1, fields.get("perfil_paciente"))
        add_select(FIELD_NUMERO_PACIENTES, fields.get("num_pacientes"))
        # AÇÕES — só é gravado quando o atendimento virou encaixe/domiciliar.
        add_select(FIELD_ACOES, fields.get("acoes"))
        # Ñ ACEITO CONVÊNIO — convênio que o paciente queria e a clínica
        # não credencia (preenchido quando o lead insiste nesse convênio).
        add_select(FIELD_NAO_ACEITO_CONVENIO, fields.get("nao_aceito_convenio"))
        # MOTIVOS PERDA — motivo do lead perdido (ex.: "Somente Convênio").
        add_select(FIELD_MOTIVOS_PERDA, fields.get("motivo_perda"))
        # NUMERO TELEFONE — canal de entrada do lead (8133 ou 0710).
        add_select(FIELD_NUMERO_TELEFONE, fields.get("numero_telefone"))
        # ATIVADO IA? — estado da IA no lead (ATIVADO / DESATIVADO).
        add_select(FIELD_ATIVADO_IA, fields.get("ativado_ia"))
        # HORA ATIVAÇÃO — timestamp de quando a IA voltou a atuar (reativação).
        add_datetime(FIELD_HORA_ATIVACAO, fields.get("hora_ativacao_ts"))
        # ATENDENTE — carimba "Lia" quando a IA conduz o atendimento.
        add_select(FIELD_ATENDENTE, fields.get("atendente"))
        # COD-AGENDAMENTO — preenchido apos gravar consulta no Medware via API.
        cod_ag = fields.get("cod_agendamento")
        if cod_ag:
            try:
                cfs.append({"field_id": FIELD_COD_AGENDAMENTO, "values": [{"value": int(cod_ag)}]})
            except (TypeError, ValueError):
                log.warning("cod_agendamento nao numerico: %s", cod_ag)

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

    def update_leads_field_batch(
        self, field_def: tuple[int, dict], pairs: list[tuple[int, str]],
    ) -> dict:
        """Atualiza UM campo select em vários leads de uma vez (PATCH em lote).

        O Kommo aceita PATCH /leads com um array de leads (até 250 por
        requisição) — muito mais rápido que um PATCH por lead.

        `pairs` = lista de (lead_id, valor_textual). Retorna
        {ok, fail} com a contagem de leads atualizados.
        """
        field_id, table = field_def
        ok = 0
        fail = 0
        chunk = 250
        for i in range(0, len(pairs), chunk):
            bloco = pairs[i:i + chunk]
            body: list[dict] = []
            for lead_id, val in bloco:
                enum_id = _pick_enum(table, val)
                if enum_id is None:
                    fail += 1
                    continue
                body.append({
                    "id": int(lead_id),
                    "custom_fields_values": [
                        {"field_id": field_id, "values": [{"enum_id": enum_id}]},
                    ],
                })
            if not body:
                continue
            try:
                with httpx.Client(timeout=self.timeout) as c:
                    r = c.patch(
                        f"{self._base}/leads", json=body, headers=self._headers,
                    )
                if r.status_code // 100 == 2:
                    ok += len(body)
                else:
                    fail += len(body)
                    log.warning(
                        "Kommo batch update falhou: HTTP %d — %s",
                        r.status_code, (r.text or "")[:300],
                    )
            except Exception as e:  # noqa: BLE001
                fail += len(body)
                log.warning("Kommo batch update error: %s", e)
            # Controle de ritmo — respeita o rate limit do Kommo.
            time.sleep(0.5)
        return {"ok": ok, "fail": fail}

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
        page: int = 1,
    ) -> list[dict]:
        """Lista leads de um pipeline que estejam em qualquer uma das etapas
        informadas. Ordenado por updated_at asc (mais parados primeiro).

        Usa a API REST direta do Kommo (filter[statuses]) — diferente da
        busca textual, aqui o filtro por etapa funciona de fato.
        `page` permite paginar (Kommo entrega no máximo 250 por página).
        """
        params: dict[str, Any] = {
            "limit": min(int(limit), 250),
            "page": max(int(page), 1),
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

    def list_leads_recent(self, limit: int = 250, page: int = 1) -> list[dict]:
        """Lista leads ordenados pela atividade MAIS RECENTE primeiro
        (updated_at desc), com paginação.

        Usado pelo disparo de unificação: avisa primeiro quem teve
        contato mais recente (hoje, ontem) e vai descendo na base.
        """
        params: dict[str, Any] = {
            "limit": min(int(limit), 250),
            "page": max(int(page), 1),
            "order[updated_at]": "desc",
        }
        try:
            with httpx.Client(timeout=self.timeout) as c:
                r = c.get(f"{self._base}/leads", params=params, headers=self._headers)
            if r.status_code == 204:
                return []
            if r.status_code != 200:
                log.warning("Kommo list_leads_recent: HTTP %d", r.status_code)
                return []
            data = r.json() or {}
            return [
                {"id": ld["id"], "name": ld.get("name"),
                 "status_id": ld.get("status_id"),
                 "updated_at": ld.get("updated_at")}
                for ld in ((data.get("_embedded") or {}).get("leads") or [])
            ]
        except Exception as e:  # noqa: BLE001
            log.warning("Kommo list_leads_recent erro: %s", e)
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

    def rename_lead(self, lead_id: int, name: str) -> bool:
        """Atualiza a denominação (nome/título) do card do lead.

        Usado para dar visibilidade rápida à equipe humana — o título do
        card passa a refletir a situação atual do atendimento.
        """
        if not name or not str(name).strip():
            return False
        try:
            with httpx.Client(timeout=self.timeout) as c:
                r = c.patch(
                    f"{self._base}/leads/{lead_id}",
                    json={"name": str(name).strip()[:250]},
                    headers=self._headers,
                )
            if r.status_code // 100 == 2:
                return True
            log.warning(
                "Kommo rename_lead %s falhou: HTTP %d", lead_id, r.status_code
            )
        except Exception as e:  # noqa: BLE001
            log.warning("Kommo rename_lead erro: %s", e)
        return False

    # ----------------------- enriquecimento de contexto (onboarding)

    def get_caller_context_by_lead(self, lead_id: int | str) -> dict:
        """Onboarding por lead_id direto — usado no caminho Kommo (8133),
        onde o widget_request já entrega o lead_id."""
        out: dict = {
            "found": True, "lead_id": int(lead_id), "name": None,
            "status_id": None, "etapa": None, "ja_agendado": False,
            "known": {},
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
            sid = data.get("status_id")
            out["status_id"] = sid
            out["etapa"] = ST_NAMES.get(sid)
            # ja_agendado baseado em status_id (camada 1).
            # Camada 2 (1.DIA CONSULTA preenchido) é avaliada abaixo.
            ja_agendado_by_status = sid in ST_JA_AGENDADO
            id_to_label = {
                FIELD_NOME_PACIENTE_1: "nome_paciente",
                FIELD_MOTIVO_PACIENTE_1: "motivo",
                FIELD_CONVENIO[0]: "convenio",
                FIELD_UNIDADE[0]: "unidade",
                FIELD_MEDICOS[0]: "medico",
                FIELD_ESPECIALIDADE[0]: "especialidade",
                FIELD_DIA_TURNO_PERIODO: "dia_turno",
                FIELD_ATIVADO_IA[0]: "ativado_ia",
            }
            # 1.DIA CONSULTA é tratado separadamente porque é date_time (epoch)
            # e dispara a flag ja_agendado quando aponta para futuro/hoje.
            ja_agendado_by_consulta = False
            dia_consulta_ts: Optional[int] = None
            for cf in (data.get("custom_fields_values") or []):
                fid = cf.get("field_id")
                # 1.DIA CONSULTA (date_time) → ja_agendado se >= ontem
                if fid == FIELD_DIA_CONSULTA_1:
                    vals = cf.get("values") or []
                    if vals and vals[0].get("value"):
                        try:
                            ts = int(vals[0]["value"])
                            # Aceita "consulta hoje OU futura" como sinal de já agendado
                            # (consulta de ontem já passou, não conta)
                            if ts > time.time() - 86400:
                                ja_agendado_by_consulta = True
                                dia_consulta_ts = ts
                                out["known"]["dia_consulta_ts"] = ts
                                # Para o agente saber a data legível
                                out["known"]["dia_consulta_iso"] = (
                                    datetime.fromtimestamp(ts).isoformat()
                                )
                        except (ValueError, TypeError):
                            pass
                    continue
                label = id_to_label.get(fid)
                if not label:
                    continue
                vals = cf.get("values") or []
                if vals:
                    v = vals[0].get("value")
                    if v:
                        out["known"][label] = v
            # ja_agendado = OR das duas camadas (status_id OR consulta futura)
            out["ja_agendado"] = ja_agendado_by_status or ja_agendado_by_consulta
            if ja_agendado_by_consulta and not ja_agendado_by_status:
                # Caso típico do bug "Aurora": lead com 1.DIA CONSULTA preenchido
                # mas status ainda 2-AGENDAR (não foi movido). Loga aviso.
                log.info(
                    "Kommo: lead %s tem dia_consulta_ts=%s (futuro) mas status "
                    "%s não está em ST_JA_AGENDADO. ja_agendado=True por camada 2.",
                    lead_id, dia_consulta_ts, sid,
                )

            # 'name' = nome do CONTATO (quem escreve no WhatsApp) — é esse
            # que o agente usa para CUMPRIMENTAR. NUNCA usar o nome do
            # paciente aqui: o paciente pode ser outra pessoa (ex.: a mãe
            # escreve, a consulta é do filho). O nome do paciente fica
            # separado, em known['nome_paciente'].
            contatos = (data.get("_embedded") or {}).get("contacts") or []
            main = next(
                (ct for ct in contatos if ct.get("is_main")),
                contatos[0] if contatos else None,
            )
            cid = (main or {}).get("id")
            if cid:
                with httpx.Client(timeout=self.timeout) as cc:
                    rc = cc.get(
                        f"{self._base}/contacts/{cid}",
                        headers=self._headers,
                    )
                if rc.status_code == 200:
                    cname = (rc.json() or {}).get("name")
                    if cname and str(cname).strip():
                        out["name"] = str(cname).strip()
        except Exception as e:  # noqa: BLE001
            log.warning("Kommo get_caller_context_by_lead erro: %s", e)
        return out

    # ----------------------- convivência humano × agente

    def recent_human_handoff(self, lead_id: int | str, window_min: int) -> bool:
        """True se um humano enviou mensagem manual no chat há < window_min.

        O Kommo registra uma nota 'service_message' quando detecta uma
        mensagem manual de saída ("Agentes de IA foram desativados neste
        chat..."). Essa nota é o sinal de que um atendente assumiu a conversa.
        """
        if not lead_id or window_min <= 0:
            return False
        try:
            with httpx.Client(timeout=self.timeout) as c:
                r = c.get(
                    f"{self._base}/leads/{lead_id}/notes",
                    params={"limit": 50, "order[created_at]": "desc"},
                    headers=self._headers,
                )
            if r.status_code != 200:
                return False
            notes = ((r.json() or {}).get("_embedded") or {}).get("notes") or []
            agora = time.time()
            for nt in notes:
                if nt.get("note_type") != "service_message":
                    continue
                txt = (
                    (nt.get("params") or {}).get("text")
                    or nt.get("text") or ""
                ).lower()
                if "desativ" not in txt:
                    continue
                created = float(nt.get("created_at") or 0)
                if created and (agora - created) < window_min * 60:
                    return True
        except Exception as e:  # noqa: BLE001
            log.warning(
                "Kommo recent_human_handoff erro (lead %s): %s", lead_id, e
            )
        return False

    def ia_status_from_notes(self, lead_id: int | str) -> Optional[str]:
        """Lê as notas do lead e deduz o estado da IA: 'ATIVADO' / 'DESATIVADO'.

        Sinal de DESATIVADO: nota service_message do Kommo com 'desativ'
        ('Agentes de IA foram desativados neste chat...').
        Sinal de ATIVADO: nota da própria Lia ('🤖 Lia (WhatsApp)') ou uma
        service_message de reativação — mais recente que o último desativar.
        Retorna None quando não há nenhum sinal nas notas.
        """
        if not lead_id:
            return None
        try:
            with httpx.Client(timeout=self.timeout) as c:
                r = c.get(
                    f"{self._base}/leads/{lead_id}/notes",
                    params={"limit": 100, "order[created_at]": "desc"},
                    headers=self._headers,
                )
            if r.status_code != 200:
                return None
            notes = ((r.json() or {}).get("_embedded") or {}).get("notes") or []
        except Exception as e:  # noqa: BLE001
            log.warning("Kommo ia_status_from_notes erro (lead %s): %s", lead_id, e)
            return None
        ts_off = 0.0   # último 'IA desativada'
        ts_on = 0.0    # última atividade da Lia / reativação
        for nt in notes:
            created = float(nt.get("created_at") or 0)
            txt = (
                (nt.get("params") or {}).get("text")
                or nt.get("text") or ""
            ).lower()
            if nt.get("note_type") == "service_message":
                if "desativ" in txt:
                    ts_off = max(ts_off, created)
                elif "ativ" in txt:  # 'agentes de IA foram ativados'
                    ts_on = max(ts_on, created)
            elif "lia (whatsapp)" in txt:
                ts_on = max(ts_on, created)
        if ts_off == 0.0 and ts_on == 0.0:
            return None
        return "DESATIVADO" if ts_off > ts_on else "ATIVADO"

    def agent_paused_for_lead(
        self, caller_context: Optional[dict], window_min: int,
    ) -> Optional[str]:
        """Decide se o agente deve ficar em SILÊNCIO para este lead.

        Retorna o motivo ou None se pode responder.
          - 'etapa-humana': lead em 7-CIRURGIAS, 8-LENTES ou 9-FORNECEDORES
            → agente desligado (atendimento humano ou contato fornecedor).
          - 'ia-desativada-manual': campo ATIVADO IA? do Kommo = DESATIVADO
            → silêncio PERMANENTE até equipe humana reativar manualmente.
            Origem do fix: lead 24038117 (Talita, 29/05/2026) — Kommo
            marcou IA desativada 11:16, mas Lia voltou a responder 16:24
            porque agent_paused_for_lead só checava janela de tempo
            (recent_human_handoff). O campo ATIVADO IA? do Kommo é a
            fonte de verdade permanente do estado da IA.
          - 'handoff': humano assumiu o chat há < window_min minutos
            (proteção temporária além do campo ATIVADO IA?).
        """
        if not caller_context or not caller_context.get("found"):
            return None
        if caller_context.get("status_id") in ST_AGENT_OFF:
            return "etapa-humana"
        # Fonte de verdade PERMANENTE: campo ATIVADO IA? do Kommo.
        # Se foi desativado (manual ou por handoff), NUNCA responde até
        # alguém marcar como ATIVADO de novo manualmente.
        known = (caller_context or {}).get("known") or {}
        ativado_ia_raw = (known.get("ativado_ia") or "")
        ativado_ia = str(ativado_ia_raw).strip().upper()
        if ativado_ia in (
            "DESATIVADO", "DESATIVADA", "DESATIVAR", "DESATIVAD",
            "OFF", "INATIVO", "INATIVA", "NAO", "NÃO",
        ):
            return "ia-desativada-manual"
        # Janela temporária extra (handoff recente sem campo Kommo ainda
        # populado pelo carimbo).
        lead_id = caller_context.get("lead_id")
        if lead_id and self.recent_human_handoff(lead_id, window_min):
            return "handoff"
        return None
