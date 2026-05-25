"""Cliente da API Medware (sistema de agenda da clínica).

API: https://medware.blinkoftalmologia.com.br/api
Auth: POST /Acesso/login {identificacao, senha} → {token, refreshToken}
      Token JWT válido ~13h. Bearer em todas as requisições.

Endpoints usados:
- POST /Acesso/login
- GET  /Medware/Agendamento/Listar
- GET  /Medware/Horarios/Listar     (vagas livres)
- GET  /Medware/Medico/Listar
- POST /Medware/Agendamento/Salvar  (gravação — Fase B)

NOTA SOBRE HORÁRIOS LIVRES (resolvido 05/2026): a "Versão Light" do Medware
REJEITA parâmetros zerados (codProcedimento=0, codPlano=0, codEspecialidade=0,
codPaciente=0) e devolvia [] quando eles eram enviados. A correção foi enviar
apenas os parâmetros com valor real — ver `listar_horarios_livres`.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Optional
from zoneinfo import ZoneInfo

import httpx

log = logging.getLogger(__name__)

MEDWARE_BASE = "https://medware.blinkoftalmologia.com.br/api"
_TZ = ZoneInfo("America/Sao_Paulo")
_DIAS_SEMANA = [
    "segunda-feira", "terça-feira", "quarta-feira", "quinta-feira",
    "sexta-feira", "sábado", "domingo",
]

# Mapa médico/unidade → códigos do Medware. Por ora só os dois confirmados;
# os demais médicos entram quando os códigos forem validados.
MEDICO_CODES = {
    "dra. karla delalibera": 12080, "dra karla": 12080,
    "karla delalibera": 12080, "karla delalíbera": 12080,
    "dra karla delalíbera": 12080, "dra. karla delalíbera": 12080,
    "dr. fabrício freitas": 12081, "dr fabricio": 12081,
    "fabricio freitas": 12081, "fabrício freitas": 12081,
    "dr fabrício": 12081, "dr. fabricio": 12081,
}
UNIDADE_CODES = {
    "asa norte": 5,
    "águas claras": 3, "aguas claras": 3,
}

# --- Procedimentos de CONSULTA -------------------------------------------
# Particular tem procedimento próprio por médico; convênio usa o genérico 13.
PROC_CONSULTA_CONVENIO = 13          # "Consulta em consultório (horário normal)"
PROC_CONSULTA_PARTICULAR = {
    12080: 303,                       # Consulta Particular Dra. Karla
}
PROC_CONSULTA_PARTICULAR_DEFAULT = 303

# --- Planos --------------------------------------------------------------
# codPlano 1 = .PARTICULAR. Demais = convênios mapeados a partir do histórico
# real de agendamentos. Convênio que NÃO estiver aqui → o agente cai no
# fluxo de atendimento humano (nunca agenda com plano errado).
PLANO_PARTICULAR = 1
PLANO_CODES = {
    "particular": 1, "sem convenio": 1, "sem convênio": 1, "particular ": 1,
    "serpro": 31,
    "sis senado": 32, "sis-senado": 32, "senado": 32,
    "tjdft": 2, "t.j.d.f.t": 2, "tjdft direto": 2, "tribunal de justica": 2,
    "policia federal": 26, "polícia federal": 26, "pf": 26,
    "plan-assist": 4, "plan assist": 4, "planassist": 4, "plan-assit": 4,
    "bacen": 9, "banco central": 9,
    "stj": 3, "superior tribunal de justica": 3,
    "camara dos deputados": 39, "câmara dos deputados": 39, "camara": 39,
}


def _code_lookup(table: dict, name: Optional[str]) -> int:
    if not name:
        return 0
    return table.get(str(name).strip().lower(), 0)


def resolver_plano(convenio: Optional[str]) -> int:
    """Nome do convênio → codPlano. 0 = desconhecido (→ atendimento humano).

    'Particular'/'sem convênio'/vazio resolve para o plano particular (1).
    """
    if not convenio or not str(convenio).strip():
        return 0
    chave = str(convenio).strip().lower()
    if chave in PLANO_CODES:
        return PLANO_CODES[chave]
    # match parcial — "uso o plano da policia federal" etc.
    for nome, cod in PLANO_CODES.items():
        if len(nome) >= 4 and nome in chave:
            return cod
    return 0


@dataclass
class MedwareClient:
    identificacao: str
    senha: str
    base_url: str = MEDWARE_BASE
    timeout: float = 12.0

    _token: Optional[str] = field(default=None, init=False)
    _token_exp: float = field(default=0.0, init=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False)

    # ---------------------------------------------------- auth

    def _ensure_token(self) -> Optional[str]:
        """Garante um token válido (renova se faltam <5 min)."""
        with self._lock:
            if self._token and time.time() < self._token_exp - 300:
                return self._token
            try:
                with httpx.Client(timeout=self.timeout) as c:
                    r = c.post(
                        f"{self.base_url}/Acesso/login",
                        json={"identificacao": self.identificacao, "senha": self.senha},
                    )
                if r.status_code != 200:
                    log.warning("Medware login falhou: HTTP %d", r.status_code)
                    return None
                data = r.json()
                self._token = data.get("token")
                # JWT exp — decodifica payload sem verificar assinatura
                self._token_exp = _jwt_exp(self._token) or (time.time() + 3600)
                log.info("Medware: token renovado")
                return self._token
            except Exception as e:  # noqa: BLE001
                log.warning("Medware login erro: %s", e)
                return None

    def _headers(self) -> Optional[dict]:
        tok = self._ensure_token()
        if not tok:
            return None
        return {"Authorization": f"Bearer {tok}", "Accept": "application/json"}

    # ---------------------------------------------------- status

    def status(self) -> dict:
        """Verifica conectividade — usado pelo /health."""
        try:
            with httpx.Client(timeout=self.timeout) as c:
                r = c.post(
                    f"{self.base_url}/Acesso/login",
                    json={"identificacao": self.identificacao, "senha": self.senha},
                )
            if r.status_code == 200 and r.json().get("token"):
                return {"ok": True, "detail": "login ok"}
            return {"ok": False, "detail": f"HTTP {r.status_code}"}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "detail": str(e)[:120]}

    # ---------------------------------------------------- consultas

    def _get(self, path: str, params: dict) -> Any:
        headers = self._headers()
        if headers is None:
            return None
        try:
            with httpx.Client(timeout=self.timeout) as c:
                r = c.get(f"{self.base_url}/{path}", params=params, headers=headers)
            if r.status_code != 200:
                log.warning("Medware GET %s falhou: HTTP %d", path, r.status_code)
                return None
            return r.json()
        except Exception as e:  # noqa: BLE001
            log.warning("Medware GET %s erro: %s", path, e)
            return None

    def _post(self, path: str, body: dict) -> tuple[bool, Any]:
        """POST autenticado. Devolve (ok, payload|erro)."""
        headers = self._headers()
        if headers is None:
            return False, "sem token Medware"
        headers["Content-Type"] = "application/json"
        try:
            with httpx.Client(timeout=self.timeout) as c:
                r = c.post(f"{self.base_url}/{path}", json=body, headers=headers)
            ok = 200 <= r.status_code < 300
            try:
                payload = r.json()
            except Exception:  # noqa: BLE001
                payload = r.text
            if not ok:
                log.warning("Medware POST %s falhou: HTTP %d %s",
                            path, r.status_code, str(payload)[:200])
            return ok, payload
        except Exception as e:  # noqa: BLE001
            log.warning("Medware POST %s erro: %s", path, e)
            return False, str(e)[:160]

    def buscar_paciente_por_cpf(self, cpf: str) -> Optional[dict]:
        """Busca um paciente pelo CPF. Devolve o 1º registro ou None.

        Usado antes de gravar agendamento: se o paciente JÁ existe no
        Medware, o agendamento usa o codPaciente dele (evita o erro
        CPF_JA_CADASTRADO_OUTRA_PESSOA).
        """
        digits = "".join(ch for ch in str(cpf or "") if ch.isdigit())
        if not digits:
            return None
        for path in ("Medware/Paciente/Listar", "Medware/Pacientes/Listar"):
            data = self._get(path, {"cpfPaciente": digits})
            if isinstance(data, list) and data:
                return data[0]
            if isinstance(data, dict) and data.get("codPaciente"):
                return data
        return None

    # ---------------------------------------------------- escrita (Fase B)

    def criar_agendamento(
        self,
        *,
        cod_medico: int,
        cod_unidade: int,
        cod_agenda: int,
        data_hora: str,
        nome: str,
        cpf: str = "",
        data_nascimento: str = "",
        celular: str = "",
        convenio: Optional[str] = None,
        cod_paciente: int = 0,
        encaixe: bool = False,
        obs: str = "",
    ) -> dict:
        """Grava um agendamento de CONSULTA no Medware.

        `convenio` None/"particular" → plano particular (1) + procedimento
        particular do médico. Convênio nomeado → resolve o codPlano; se não
        estiver mapeado devolve {ok:False, motivo:"convenio_desconhecido"}
        para o agente cair no fluxo humano.

        `data_hora` aceita 'YYYY-MM-DDTHH:MM' ou 'DD/MM/YYYY HH:MM'.
        Retorna {ok, cod_agendamento?, plano, procedimento, motivo?, detalhe?}.
        """
        cod_plano = (
            PLANO_PARTICULAR
            if (not convenio or str(convenio).strip().lower()
                in ("particular", "sem convenio", "sem convênio"))
            else resolver_plano(convenio)
        )
        if not cod_plano:
            return {"ok": False, "motivo": "convenio_desconhecido",
                    "convenio": convenio}
        if cod_plano == PLANO_PARTICULAR:
            cod_proc = PROC_CONSULTA_PARTICULAR.get(
                cod_medico, PROC_CONSULTA_PARTICULAR_DEFAULT)
        else:
            cod_proc = PROC_CONSULTA_CONVENIO

        body: dict[str, Any] = {
            "codMedico": cod_medico,
            "codUnidade": cod_unidade,
            "codAgenda": cod_agenda,
            "codProcedimento": cod_proc,
            "codPlano": cod_plano,
            "dataHoraAgendada": data_hora,
            "encaixe": -1 if encaixe else 0,
            "obs": obs or None,
        }
        # Celular: o Medware exige DDD e número SEPARADOS.
        cel = "".join(ch for ch in (celular or "") if ch.isdigit())
        if len(cel) > 11 and cel.startswith("55"):
            cel = cel[2:]                       # remove DDI 55, se vier
        cel_ddd = cel[:2] if len(cel) >= 10 else ""
        cel_num = cel[2:] if len(cel) >= 10 else cel

        # Se o paciente já existe no Medware (CPF cadastrado), usa o
        # codPaciente dele — senão o Medware recusa com
        # CPF_JA_CADASTRADO_OUTRA_PESSOA.
        if not cod_paciente and cpf:
            try:
                existente = self.buscar_paciente_por_cpf(cpf)
                if existente and existente.get("codPaciente"):
                    cod_paciente = int(existente["codPaciente"])
            except Exception as e:  # noqa: BLE001
                log.warning("Medware busca paciente por CPF falhou: %s", e)

        if cod_paciente:
            body["codPaciente"] = cod_paciente
        else:
            body["paciente"] = {
                "nome": (nome or "").strip().upper(),
                "cpf": "".join(ch for ch in (cpf or "") if ch.isdigit()),
                "dataNascimento": data_nascimento or "",
                "numeroCelular": cel_num,
                "numeroCelularDdd": cel_ddd,
            }

        ok, payload = self._post("Medware/Agendamento/Salvar", body)
        if not ok:
            return {"ok": False, "motivo": "erro_medware",
                    "detalhe": str(payload)[:200],
                    "plano": cod_plano, "procedimento": cod_proc}
        cod_ag = 0
        if isinstance(payload, dict):
            cod_ag = (payload.get("codAgendamento")
                      or payload.get("cod") or 0)
        return {"ok": True, "cod_agendamento": cod_ag,
                "plano": cod_plano, "procedimento": cod_proc,
                "detalhe": payload if not isinstance(payload, (dict, list))
                else None}

    def listar_agendamentos(
        self, data_inicio: str, data_fim: str,
        cod_medico: int = 0, cod_unidade: int = 0,
    ) -> list[dict]:
        """Lista agendamentos de um período (datas em DD/MM/YYYY)."""
        params = {"dataInicio": data_inicio, "dataFim": data_fim}
        if cod_medico:
            params["codMedico"] = cod_medico
        if cod_unidade:
            params["codUnidade"] = cod_unidade
        data = self._get("Medware/Agendamento/Listar", params)
        if isinstance(data, list):
            return data
        return []

    def listar_horarios_livres(
        self,
        data_inicio: str, data_fim: str,
        hora_inicio: str = "07:00", hora_fim: str = "19:00",
        cod_medico: int = 12080, cod_unidade: int = 0,
        cod_procedimento: int = 0, cod_plano: int = 0,
        data_nasc: str = "",
    ) -> list[dict]:
        """Lista vagas livres no período (datas DD/MM/YYYY, horas HH:MM).

        IMPORTANTE: a "Versão Light" do Medware REJEITA parâmetros zerados
        (codProcedimento=0, codPlano=0, codEspecialidade=0, codPaciente=0) e
        devolve [] quando eles são enviados. A correção é só mandar o que
        realmente tem valor — médico + período + janela de horário bastam.
        """
        params: dict[str, Any] = {
            "dataInicio": data_inicio, "dataFim": data_fim,
            "horaInicio": hora_inicio, "horaFim": hora_fim,
        }
        if cod_medico:
            params["codMedico"] = cod_medico
        if cod_unidade:
            params["codUnidade"] = cod_unidade
        if cod_procedimento:
            params["codProcedimento"] = cod_procedimento
        if cod_plano:
            params["codPlano"] = cod_plano
        if data_nasc:
            params["dataNasc"] = data_nasc
        data = self._get("Medware/Horarios/Listar", params)
        if isinstance(data, list):
            return data
        return []

    def horarios_para_agente(
        self, medico_nome: str, unidade_nome: Optional[str] = None,
        dias: int = 21,
    ) -> list[dict]:
        """Vagas livres reais para o agente OFERECER ao paciente.

        Mapeia o nome do médico/unidade para os códigos do Medware,
        consulta as vagas dos próximos `dias` e devolve uma lista limpa:
          {data_iso, data_br, dia_semana, hora}
        Devolve [] se o médico não estiver mapeado ou não houver vaga.
        """
        cod_medico = _code_lookup(MEDICO_CODES, medico_nome)
        if not cod_medico:
            return []
        cod_unidade = _code_lookup(UNIDADE_CODES, unidade_nome)
        hoje = datetime.now(_TZ)
        ini = (hoje + timedelta(days=1)).strftime("%d/%m/%Y")
        fim = (hoje + timedelta(days=dias)).strftime("%d/%m/%Y")
        raw = self.listar_horarios_livres(
            data_inicio=ini, data_fim=fim,
            cod_medico=cod_medico, cod_unidade=cod_unidade,
        )
        out: list[dict] = []
        for s in raw:
            d = str(s.get("data") or "")[:10]   # YYYY-MM-DD
            h = str(s.get("horario") or "")[:5]  # HH:MM
            if not d or not h:
                continue
            try:
                dt = datetime.strptime(d, "%Y-%m-%d")
            except ValueError:
                continue
            out.append({
                "data_iso": d,
                "data_br": dt.strftime("%d/%m"),
                "dia_semana": _DIAS_SEMANA[dt.weekday()],
                "hora": h,
                "cod_agenda": s.get("codAgenda") or 0,
                "cod_unidade": s.get("codUnidade") or 0,
                "cod_medico": s.get("codMedico") or cod_medico,
            })
        return out


def _jwt_exp(token: Optional[str]) -> Optional[float]:
    """Extrai o campo 'exp' (epoch) do payload de um JWT, sem verificar assinatura."""
    if not token:
        return None
    try:
        import base64
        import json as _json
        payload_b64 = token.split(".")[1]
        payload_b64 += "=" * (-len(payload_b64) % 4)
        payload = _json.loads(base64.urlsafe_b64decode(payload_b64))
        return float(payload.get("exp", 0)) or None
    except Exception:  # noqa: BLE001
        return None
