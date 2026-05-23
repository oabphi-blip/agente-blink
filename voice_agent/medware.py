"""Cliente da API Medware (sistema de agenda da clínica).

API: https://medware.blinkoftalmologia.com.br/api
Auth: POST /Acesso/login {identificacao, senha} → {token, refreshToken}
      Token JWT válido ~13h. Bearer em todas as requisições.

Endpoints usados:
- POST /Acesso/login
- GET  /Medware/Agendamento/Listar
- GET  /Medware/Horarios/Listar     (vagas livres — ver nota abaixo)
- GET  /Medware/Medico/Listar

NOTA SOBRE HORÁRIOS LIVRES: na "Versão Light" da Medware desta clínica o
endpoint Horarios/Listar tem retornado lista vazia para todas as combinações
testadas de procedimento/unidade. Enquanto isso não for calibrado junto à
Medware, `listar_horarios_livres` devolve [] e o agente cai no fluxo de
coleta de preferência + transferência humana (fallback gracioso).
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


def _code_lookup(table: dict, name: Optional[str]) -> int:
    if not name:
        return 0
    return table.get(str(name).strip().lower(), 0)


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
        data_nasc: str = "01/01/1990",
    ) -> list[dict]:
        """Lista vagas livres no período (datas DD/MM/YYYY, horas HH:MM).

        Ver NOTA no topo do arquivo: hoje pode devolver [] (Versão Light).
        """
        params = {
            "codProcedimento": cod_procedimento,
            "dataInicio": data_inicio, "dataFim": data_fim,
            "horaInicio": hora_inicio, "horaFim": hora_fim,
            "dataNasc": data_nasc,
            "codMedico": cod_medico, "codUnidade": cod_unidade,
            "codPlano": cod_plano, "codEspecialidade": 0, "codPaciente": 0,
        }
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
