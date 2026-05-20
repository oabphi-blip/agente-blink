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
from typing import Any, Optional

import httpx

log = logging.getLogger(__name__)

MEDWARE_BASE = "https://medware.blinkoftalmologia.com.br/api"


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
