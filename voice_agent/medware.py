"""Cliente da API Medware (sistema de agenda da clínica).

API: https://medware.blinkoftalmologia.com.br/api
Auth: POST /Acesso/login {identificacao, senha} → {token, refreshToken}
      Token JWT válido ~24h. Bearer em todas as requisições.

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
    # Dra. Karla Delalibera (cod 12080) — todas as variantes que pacientes escrevem
    "dra. karla delalibera": 12080, "dra karla": 12080,
    "karla delalibera": 12080, "karla delalíbera": 12080,
    "karla delalibera pacheco": 12080,  # como aparece no Medware
    "dra. karla delalibera pacheco": 12080,
    "dra karla delalíbera": 12080, "dra. karla delalíbera": 12080,
    "karla": 12080, "dra. karla": 12080, "doutora karla": 12080,
    "dra delalibera": 12080, "dra. delalibera": 12080,
    # Dr. Fabrício Freitas (cod 12081) — todas as variantes (com/sem acento, sigla)
    "dr. fabrício freitas": 12081, "dr. fabricio freitas": 12081,
    "dr fabricio": 12081, "dr fabrício": 12081,
    "dr. fabricio": 12081, "dr. fabrício": 12081,
    "fabricio freitas": 12081, "fabrício freitas": 12081,
    "fabricio": 12081, "fabrício": 12081,
    "doutor fabricio": 12081, "doutor fabrício": 12081,
    "dr freitas": 12081, "dr. freitas": 12081,
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
# codPlano 1 = .PARTICULAR. Demais = convênios mapeados via cross-check
# entre lista oficial Medware (listar_planos_operadoras) e enum CONVÊNIO
# do Kommo (field_id=853206). Cada convênio tem múltiplos aliases para
# tolerar variações do paciente. Convênio NÃO mapeado → cai em humano.
#
# Cross-check oficial 29/05/2026 — todos os 27 convênios do Kommo mapeados:
PLANO_PARTICULAR = 1
PLANO_CODES = {
    # PARTICULAR (codPlano 1)
    "particular": 1, "sem convenio": 1, "sem convênio": 1,
    "particular ": 1, "nao se aplica": 1, "não se aplica": 1,
    "n/a": 1,

    # T.J.D.F.T - DIRETO (codPlano 2) — Kommo: "TJDFT Pró-Saúde"
    "tjdft": 2, "t.j.d.f.t": 2, "t.j.d.f.t - direto": 2, "tjdft direto": 2,
    "tribunal de justica": 2, "tjdft pró-saúde": 2, "tjdft pro-saude": 2,
    "tjdft pro saude": 2, "pro saude tjdft": 2, "pró-saúde tjdft": 2,

    # STJ (codPlano 3) — Kommo: "Pro ser STJ"
    "stj": 3, "superior tribunal de justica": 3,
    "pro ser stj": 3, "pro-ser stj": 3, "proser stj": 3,
    "pro ser": 3, "pro-ser": 3, "pro ser do stj": 3, "pro-ser do stj": 3,

    # PLAN-ASSIT (codPlano 4) — Kommo: "Plan Assiste - MPF (MPU)"
    # NOTA: existe "MPU- PLAN ASSISTE AGUAS CLARAS (DIRETO)" cod 74,
    # decidir caso a caso. Padrão = 4 (mais comum historicamente).
    "plan-assist": 4, "plan assist": 4, "planassist": 4, "plan-assit": 4,
    "plan assiste": 4, "plan-assiste": 4, "planassiste": 4,
    "plan assiste mpf": 4, "plan assiste - mpf (mpu)": 4,
    "mpf": 4, "mpu": 4,

    # E-VIDA (codPlano 5) — Kommo: "E-vida (Luminar)"
    "e-vida": 5, "evida": 5, "e vida": 5, "luminar": 5,
    "e-vida (luminar)": 5, "evida luminar": 5,

    # AFFEGO (codPlano 7) — sem correspondência Kommo, mantido pra compatibilidade
    "affego": 7,

    # ANAFE (codPlano 8) — Kommo: "Anafe"
    "anafe": 8,

    # BACEN (codPlano 9) — Kommo: "Bacen"
    "bacen": 9, "banco central": 9,

    # CARE PLUS (codPlano 14) — Kommo: "Care Plus"
    "care plus": 14, "careplus": 14, "care-plus": 14,

    # CASEC (codPlano 15) — Kommo: "Casec (Codevasf)"
    "casec": 15, "casec (codevasf)": 15, "codevasf": 15,

    # CASEMBRAPA (codPlano 16) — Kommo: "Casembrapa  _ Embrapa"
    "casembrapa": 16, "embrapa": 16, "casembrapa _ embrapa": 16,
    "casembrapa  _ embrapa": 16, "casembrapa embrapa": 16,

    # CNTI (codPlano 18) — sem correspondência Kommo
    "cnti": 18,

    # FASCAL (codPlano 22) — Kommo: "Fascal"
    "fascal": 22,

    # CONAB (codPlano 19) — Kommo: "Conab"
    "conab": 19,

    # OMINT (codPlano 25) — Kommo: "Omint"
    "omint": 25,

    # POLICIA FEDERAL (codPlano 26) — Kommo: "PF Saúde"
    "policia federal": 26, "polícia federal": 26, "pf": 26,
    "pf saude": 26, "pf saúde": 26, "pfsaude": 26,
    "policia": 26, "polícia": 26,

    # STM (codPlano 27) — Kommo: "PLAS/JMU (STM)"
    "stm": 27, "plas/jmu": 27, "plas jmu": 27, "plas/jmu (stm)": 27,
    "jmu": 27,

    # PROASA (codPlano 28) — Kommo: "Proasa"
    "proasa": 28, "pro-asa": 28, "pro asa": 28,

    # SAÚDE CAIXA (codPlano 29) — Kommo: "Saúde Caixa"
    "saude caixa": 29, "saúde caixa": 29, "caixa": 29, "saúde-caixa": 29,
    "saude-caixa": 29,

    # SAÚDE PETROBRAS (codPlano 30) — Kommo: "Petrobrás (Saúde Petrobrás)"
    "saude petrobras": 30, "saúde petrobras": 30, "saúde petrobrás": 30,
    "petrobras": 30, "petrobrás": 30,
    "petrobrás (saúde petrobrás)": 30, "petrobras (saude petrobras)": 30,

    # SERPRO (codPlano 31) — Kommo: "Serpro"
    "serpro": 31,

    # SIS SENADO (codPlano 32) — Kommo: "SIS Senado"
    "sis senado": 32, "sis-senado": 32, "senado": 32, "sis": 32,

    # STF-MED (codPlano 33) — Kommo: "STF-Med"
    "stf-med": 33, "stf med": 33, "stfmed": 33, "stf": 33,

    # TRF (codPlano 34) — Kommo: "TRF Pró-Social"
    "trf": 34, "trf pro-social": 34, "trf pró-social": 34,
    "pro social trf": 34, "pró-social trf": 34,

    # TRE (codPlano 35) — Kommo: "TRE"
    "tre": 35,

    # TRT (codPlano 36) — Kommo: "TRT"
    "trt": 36,

    # TST (codPlano 37) — Kommo: "TST Saúde"
    "tst": 37, "tst saude": 37, "tst saúde": 37, "tstsaude": 37,

    # UNAFISCO SAÚDE (codPlano 38) — sem correspondência Kommo
    "unafisco": 38, "unafisco saude": 38, "unafisco saúde": 38,

    # CAMARA DOS DEPUTADOS (codPlano 39) — Kommo: "PróSaúde (Camara dos Deputados)"
    "camara dos deputados": 39, "câmara dos deputados": 39, "camara": 39,
    "câmara": 39, "prosaude camara": 39, "prósaúde câmara": 39,
    "prósaúde (camara dos deputados)": 39,
    "prosaude (camara dos deputados)": 39,
    "pró-saúde câmara": 39, "pró-saúde camara dos deputados": 39,

    # BACEN AMHPDF (codPlano 45) — sem correspondência Kommo direta
    "bacen amhpdf": 45, "amhpdf": 45,

    # MPU- PLAN ASSISTE AGUAS CLARAS (DIRETO) (codPlano 74)
    # alternativa pra MPU em vez de PLAN-ASSIT (4)
    "mpu plan assiste aguas claras": 74,
    "mpu- plan assiste aguas claras (direto)": 74,
    "plan assiste aguas claras": 74,

    # INAS (Kommo: "Inas GDf (somente Dr. Fabrício Freitas)")
    # NOTA: NÃO existe operadora INAS na listar_planos_operadoras do Medware.
    # Provavelmente é um plano interno / particular especial. Mantém código 0
    # pra escalar humano até esclarecer com a equipe. Listar aliases pra
    # detectar e marcar no log.
    # "inas": 0, "inas gdf": 0,  # deixar SEM mapeamento → humano

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


def _data_nasc_iso(value: Optional[str]) -> str:
    """Normaliza a data de nascimento para yyyy-MM-dd (PacienteExternoDto)."""
    if not value:
        return ""
    v = str(value).strip()[:10]
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(v, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return v


def _extrair_codigos_procedimento(data: Any) -> list[int]:
    """Normaliza qualquer formato de resposta Medware num set de codProcedimento.

    Tolera: lista direta, dict com chave de coleção, ou dict único.
    Procura os nomes de campo de código conhecidos. Não levanta exceção —
    devolve sempre uma lista (vazia se nada reconhecível).
    """
    if not data:
        return []
    registros: list[Any] = []
    if isinstance(data, list):
        registros = data
    elif isinstance(data, dict):
        for key in ("procedimentos", "itens", "items", "data", "lista", "registros"):
            v = data.get(key)
            if isinstance(v, list):
                registros = v
                break
        else:
            registros = [data]
    out: list[int] = []
    for r in registros:
        if isinstance(r, dict):
            for key in ("codProcedimento", "codigoProcedimento",
                        "codProc", "codigo", "cod"):
                val = r.get(key)
                if val is not None:
                    try:
                        out.append(int(val))
                    except (TypeError, ValueError):
                        pass
                    break
        else:
            try:
                out.append(int(r))
            except (TypeError, ValueError):
                pass
    return sorted(set(out))


def _data_hora_iso(value: Optional[str]) -> str:
    """Normaliza data/hora do agendamento para yyyy-MM-ddTHH:mm.

    Aceita ISO ('yyyy-MM-ddTHH:mm[:ss]') ou formato BR ('dd/MM/yyyy HH:mm').
    """
    if not value:
        return ""
    v = str(value).strip()
    for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%d %H:%M", "%d/%m/%Y %H:%M",
                "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %Hh%M"):
        try:
            return datetime.strptime(v, fmt).strftime("%Y-%m-%dT%H:%M")
        except ValueError:
            continue
    return v

# Thresholds para alertar sobre lentidão do servidor Medware
# (servidor Windows local da clínica — sob pressão de memória/cpu).
_LATENCY_WARN_S = 3.0   # acima disso, aviso (servidor sob estresse)
_LATENCY_ERROR_S = 8.0  # acima disso, erro crítico (timeout iminente)


def _log_latencia(method: str, path: str, elapsed: float, status: int) -> None:
    """Log estruturado de latência das chamadas Medware.

    Permite cruzar logs do Easypanel com momentos de instabilidade do
    servidor Windows local. Use grep '[MEDWARE LATENCY]' nos logs.
    """
    if elapsed >= _LATENCY_ERROR_S:
        log.error(
            "[MEDWARE LATENCY] %s %s %.2fs HTTP=%d — CRÍTICO (servidor sobrecarregado)",
            method, path, elapsed, status,
        )
    elif elapsed >= _LATENCY_WARN_S:
        log.warning(
            "[MEDWARE LATENCY] %s %s %.2fs HTTP=%d — lento (servidor sob estresse)",
            method, path, elapsed, status,
        )
    else:
        log.info("[MEDWARE LATENCY] %s %s %.2fs HTTP=%d", method, path, elapsed, status)


@dataclass
class MedwareClient:
    identificacao: str
    senha: str
    base_url: str = MEDWARE_BASE
    # Bug C-38b (17/06/2026): VM Medware Light com SQL sem índice estoura
    # com timeout curto. 20s dá margem pra a query completar antes do retry
    # amplificar carga. Override via env MEDWARE_TIMEOUT_S (5-60).
    timeout: float = 20.0

    _token: Optional[str] = field(default=None, init=False)
    _refresh_token: Optional[str] = field(default=None, init=False)
    _token_exp: float = field(default=0.0, init=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False)

    # ---------------------------------------------------- auth

    def _ensure_token(self) -> Optional[str]:
        """Garante um token válido (renova se faltam <5 min)."""
        with self._lock:
            if self._token and time.time() < self._token_exp - 300:
                return self._token
            t0 = time.perf_counter()
            try:
                with httpx.Client(timeout=self.timeout) as c:
                    r = c.post(
                        f"{self.base_url}/Acesso/login",
                        json={"identificacao": self.identificacao, "senha": self.senha},
                    )
                elapsed = time.perf_counter() - t0
                _log_latencia("POST", "Acesso/login", elapsed, r.status_code)
                if r.status_code != 200:
                    log.warning("Medware login falhou: HTTP %d", r.status_code)
                    return None
                data = r.json()
                self._token = data.get("token")
                self._refresh_token = data.get("refreshToken")
                # JWT exp — decodifica payload sem verificar assinatura
                self._token_exp = _jwt_exp(self._token) or (time.time() + 86400)
                log.info("Medware: token renovado (%.2fs)", elapsed)
                return self._token
            except httpx.TimeoutException as e:
                elapsed = time.perf_counter() - t0
                log.error(
                    "[MEDWARE LATENCY] TIMEOUT no login após %.2fs — servidor "
                    "Windows local pode estar sobrecarregado. Erro: %s",
                    elapsed, e,
                )
                return None
            except Exception as e:  # noqa: BLE001
                elapsed = time.perf_counter() - t0
                log.warning("Medware login erro após %.2fs: %s", elapsed, e)
                return None

    def _headers(self) -> Optional[dict]:
        tok = self._ensure_token()
        if not tok:
            return None
        return {"Authorization": f"Bearer {tok}", "Accept": "application/json"}

    # ---------------------------------------------------- status

    def status(self) -> dict:
        """Verifica conectividade — usado pelo /health."""
        t0 = time.perf_counter()
        try:
            with httpx.Client(timeout=self.timeout) as c:
                r = c.get(f"{self.base_url}/health/health")
            elapsed = time.perf_counter() - t0
            _log_latencia("GET", "health/health", elapsed, r.status_code)
            if r.status_code == 200 and "API Ativa" in r.text:
                return {"ok": True, "detail": "API Ativa", "elapsed_s": round(elapsed, 2)}
            return {"ok": False, "detail": f"HTTP {r.status_code}", "elapsed_s": round(elapsed, 2)}
        except Exception as e:  # noqa: BLE001
            elapsed = time.perf_counter() - t0
            return {"ok": False, "detail": str(e)[:120], "elapsed_s": round(elapsed, 2)}

    # ---------------------------------------------------- consultas

    def _get(self, path: str, params: dict) -> Any:
        headers = self._headers()
        if headers is None:
            return None
        t0 = time.perf_counter()
        try:
            with httpx.Client(timeout=self.timeout) as c:
                r = c.get(f"{self.base_url}/{path}", params=params, headers=headers)
            elapsed = time.perf_counter() - t0
            _log_latencia("GET", path, elapsed, r.status_code)
            if r.status_code != 200:
                log.warning("Medware GET %s falhou: HTTP %d", path, r.status_code)
                return None
            return r.json()
        except httpx.TimeoutException as e:
            elapsed = time.perf_counter() - t0
            log.error(
                "[MEDWARE LATENCY] TIMEOUT em GET %s após %.2fs (timeout=%.1fs) "
                "— servidor pode estar sobrecarregado. Erro: %s",
                path, elapsed, self.timeout, e,
            )
            return None
        except Exception as e:  # noqa: BLE001
            elapsed = time.perf_counter() - t0
            log.warning(
                "Medware GET %s erro após %.2fs: %s", path, elapsed, e,
            )
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

        # Body conforme AgendamentoExternoDto (spec OpenAPI v1.5.0):
        # campos da raiz são SÓ estes — additionalProperties=false.
        body: dict[str, Any] = {
            "codAgenda": cod_agenda,
            "codMedico": cod_medico,
            "codProcedimento": cod_proc,
            "codPlano": cod_plano,
            "dataHoraAgendada": _data_hora_iso(data_hora),  # yyyy-MM-ddTHH:mm
        }
        # Celular: DDD e número SEPARADOS.
        cel = "".join(ch for ch in (celular or "") if ch.isdigit())
        if len(cel) > 11 and cel.startswith("55"):
            cel = cel[2:]                       # remove DDI 55, se vier
        cel_ddd = cel[:2] if len(cel) >= 10 else ""
        cel_num = cel[2:] if len(cel) >= 10 else cel

        # Resolução do paciente (spec Medware):
        #  • Paciente JÁ cadastrado → codPaciente na RAIZ do JSON; o objeto
        #    `paciente` é OPCIONAL e NÃO é enviado (dispensa dataNascimento).
        #  • Paciente NOVO → omite codPaciente e envia o objeto `paciente`
        #    com nome, dataNascimento (yyyy-MM-dd), cpf e celular.
        cpf_digits = "".join(ch for ch in str(cpf or "") if ch.isdigit())
        if not cod_paciente and cpf_digits:
            try:
                existente = self.buscar_paciente_por_cpf(cpf_digits)
                if existente and existente.get("codPaciente"):
                    cod_paciente = int(existente["codPaciente"])
            except Exception as e:  # noqa: BLE001
                log.warning("Medware busca paciente por CPF falhou: %s", e)

        if cod_paciente:
            body["codPaciente"] = cod_paciente
        else:
            body["paciente"] = {
                "nome": (nome or "").strip().upper(),
                "dataNascimento": _data_nasc_iso(data_nascimento),
                "cpf": cpf_digits,
                "numeroCelularddd": cel_ddd,
                "numeroCelular": cel_num,
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

    def listar_procedimentos_realizados(self, agendamento_id: int) -> list[int]:
        """Lista os códigos de procedimentos REALIZADOS num agendamento.

        Usado pela auditoria pós-consulta (task #82): compara o PLANEJADO
        (N.EXAMES do Kommo, via selecionar_agrupador) com o que foi de fato
        executado no Medware. A diferença vira `N.AGRUPAMENTO ALTERADO=true`
        + reabertura da autorização do convênio.

        ATENÇÃO — endpoint A CONFIRMAR contra a API real do Medware. A spec
        OpenAPI v1.5.0 não documenta explicitamente "procedimentos
        realizados"; tentamos os caminhos candidatos conhecidos e
        normalizamos a resposta. Se nenhum responder, devolve [] e a
        auditoria trata como `fonte_vazia` (não inventa nada — segue a
        lição "nunca codifico mapeamento sem listar a fonte").

        Devolve lista de codProcedimento (int), deduplicada e ordenada.
        """
        if not agendamento_id:
            return []
        candidatos = (
            ("Medware/Agendamento/Procedimentos",
             {"codAgendamento": int(agendamento_id)}),
            ("Medware/Procedimento/Realizados",
             {"codAgendamento": int(agendamento_id)}),
            ("Medware/Worklist/Listar",
             {"codAgendamento": int(agendamento_id)}),
        )
        for path, params in candidatos:
            data = self._get(path, params)
            codigos = _extrair_codigos_procedimento(data)
            if codigos:
                return codigos
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
        dias: int = 14, max_retries: int = 1,
        data_inicio: Optional[Any] = None,
        data_fim: Optional[Any] = None,
    ) -> list[dict]:
        """Vagas livres reais para o agente OFERECER ao paciente.

        Mapeia o nome do médico/unidade para os códigos do Medware,
        consulta as vagas e devolve uma lista limpa:
          {data_iso, data_br, dia_semana, hora}
        Devolve [] se o médico não estiver mapeado ou não houver vaga.

        JANELA DE DATAS (Bug C-38, 17/06/2026 — diagnóstico Medware 90d
        causa ReadTimeout na VM Light + diagnóstico_consumo_medware_17_06):
        - default reduzido de 90 → 21 dias (servidor Medware Light SQL sem
          índice adequado estoura timeout com janela longa; 7d = ok, 90d =
          timeout). Override via env MEDWARE_DIAS_DEFAULT (1-90, default 21).
        - `data_inicio`/`data_fim` (objetos date) sobrescrevem dias para
          request ESPECÍFICO (preferência do paciente vinda do C-30, ex.:
          "entre 7 e 15 de julho").

        OBSERVABILIDADE: cada chamada loga [MEDWARE REQ] e [MEDWARE RESP] em
        JSON, pra auditar no Easypanel "o que foi pedido vs. o que voltou".

        RETRY (task #139, origem bug Adelia 24056883 — 01/06/2026):
        Medware é silencioso intermitente — uma chamada pode retornar
        [] mesmo quando há slots. Hoje tentamos 3 vezes com backoff
        0.5s → 1s → 2s antes de devolver vazio. Só tenta de novo se
        o cod_medico foi resolvido (médico mapeado) — caso contrário
        retorno [] é definitivo.
        """
        import json as _json
        import os as _os
        import time as _time
        cod_medico = _code_lookup(MEDICO_CODES, medico_nome)
        if not cod_medico:
            return []
        cod_unidade = _code_lookup(UNIDADE_CODES, unidade_nome)
        hoje = datetime.now(_TZ)
        # Bug C-38: env override pro default. Permite voltar pra 90d se
        # provedor consertar SQL/índices, sem precisar de novo deploy.
        try:
            _env_dias = int(_os.getenv("MEDWARE_DIAS_DEFAULT") or "0")
            if 1 <= _env_dias <= 90:
                dias_default = _env_dias
            else:
                dias_default = dias
        except (TypeError, ValueError):
            dias_default = dias
        # Bug C-38b: env override pro max_retries. Default fail-fast (1
        # tentativa) evita amplificar congestionamento quando VM Medware
        # está lenta. Pra voltar pro retry agressivo, set MEDWARE_MAX_RETRIES=3.
        try:
            _env_retries = int(_os.getenv("MEDWARE_MAX_RETRIES") or "0")
            if 1 <= _env_retries <= 5:
                max_retries = _env_retries
        except (TypeError, ValueError):
            pass
        # Bug C-38b: env override pro timeout httpx (5-60s).
        try:
            _env_to = float(_os.getenv("MEDWARE_TIMEOUT_S") or "0")
            if 5.0 <= _env_to <= 60.0:
                # patch in-place do timeout do client pra essa instância
                self.timeout = _env_to
        except (TypeError, ValueError):
            pass
        if data_inicio is not None and data_fim is not None:
            ini = data_inicio.strftime("%d/%m/%Y")
            fim = data_fim.strftime("%d/%m/%Y")
            janela_fonte = "preferencia"
        else:
            ini = (hoje + timedelta(days=1)).strftime("%d/%m/%Y")
            fim = (hoje + timedelta(days=dias_default)).strftime("%d/%m/%Y")
            janela_fonte = f"default_{dias_default}d"
        # Log estruturado do REQUEST (grep '[MEDWARE REQ]' no Easypanel).
        _req_log = {
            "evento": "medware_horarios_req",
            "medico": medico_nome, "cod_medico": cod_medico,
            "unidade": unidade_nome, "cod_unidade": cod_unidade,
            "dataInicio": ini, "dataFim": fim,
            "horaInicio": "07:00", "horaFim": "19:00",
            "janela_fonte": janela_fonte,
        }
        log.info("[MEDWARE REQ] %s", _json.dumps(_req_log, ensure_ascii=False))
        # Stash do último req/resp na instância — o pipeline persiste em Redis.
        self.ultimo_req_horarios = dict(_req_log)
        raw: list[dict] = []
        delay = 0.5
        for tentativa in range(1, max_retries + 1):
            try:
                raw = self.listar_horarios_livres(
                    data_inicio=ini, data_fim=fim,
                    cod_medico=cod_medico, cod_unidade=cod_unidade,
                )
            except Exception as e:  # noqa: BLE001
                log.warning(
                    "[MEDWARE horarios_para_agente tentativa %d] exception: %s",
                    tentativa, e,
                )
                raw = []
            if raw:
                if tentativa > 1:
                    log.info(
                        "[MEDWARE horarios_para_agente] sucesso na tentativa %d "
                        "(medico=%s unidade=%s)",
                        tentativa, medico_nome, unidade_nome,
                    )
                break
            if tentativa < max_retries:
                log.warning(
                    "[MEDWARE horarios_para_agente tentativa %d/%d VAZIA] "
                    "medico=%s unidade=%s — backoff %ss",
                    tentativa, max_retries, medico_nome, unidade_nome, delay,
                )
                _time.sleep(delay)
                delay *= 2
        if not raw:
            log.error(
                "[MEDWARE horarios_para_agente] %d tentativas TODAS VAZIAS — "
                "medico=%s unidade=%s — escalonar humano se status AGENDAR",
                max_retries, medico_nome, unidade_nome,
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
        # Log estruturado da RESPOSTA (grep '[MEDWARE RESP]' no Easypanel).
        _resp_log = {
            "evento": "medware_horarios_resp",
            "n_slots": len(out),
            "janela_fonte": janela_fonte,
            "dataInicio": ini, "dataFim": fim,
            "amostra": [
                f"{s['dia_semana']} {s['data_br']} {s['hora']}" for s in out[:3]
            ],
        }
        log.info("[MEDWARE RESP] %s", _json.dumps(_resp_log, ensure_ascii=False))
        try:
            self.ultimo_req_horarios["n_slots"] = len(out)
            self.ultimo_req_horarios["amostra"] = _resp_log["amostra"]
        except Exception:  # noqa: BLE001
            pass
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
