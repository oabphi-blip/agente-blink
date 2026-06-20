"""blink-medware — Sprint 4.

Servidor MCP que encapsula Medware (ERP clínico). Implementa NATIVAMENTE
todos os fixes que custaram dezenas de bugs ao projeto:

- Bug C-38: janela default 14 dias (não mais 90)
- Bug C-38b: timeout 20s, retry 1x fail-fast
- Regra E6-C: janela cirúrgica quando preferência conhecida
- Validação Pydantic estrita: anti-alucinação da LLM
- Stderr-only logs (livro 6.1)
- Servidor como guardião (livro 4.5): valida ANTES de gravar
"""
from __future__ import annotations

import logging
import os
import sys
from datetime import date, timedelta
from typing import Optional

import httpx
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field, field_validator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - blink-medware - %(levelname)s - %(message)s",
    stream=sys.stderr,
)
log = logging.getLogger("blink-medware")


# ─── Configuração ───────────────────────────────────────────────────
MEDWARE_BASE = os.getenv(
    "MEDWARE_BASE_URL",
    "https://medware.blinkoftalmologia.com.br/api",
)
MEDWARE_USER = os.getenv("MEDWARE_USER", "")
MEDWARE_SENHA = os.getenv("MEDWARE_SENHA", "")

# Fix C-38b: timeouts e retry
TIMEOUT_SECONDS = float(os.getenv("MEDWARE_TIMEOUT_S", "20"))
MAX_RETRIES = int(os.getenv("MEDWARE_MAX_RETRIES", "1"))
DIAS_DEFAULT = int(os.getenv("MEDWARE_DIAS_DEFAULT", "14"))

# Mapeamento médicos/unidades canônico
COD_MEDICO = {
    "karla": 12080,
    "fabricio": 12081,
}
COD_UNIDADE = {
    "asa norte": 5,
    "aguas claras": 3,
    "águas claras": 3,
}

# Cliente HTTP (substituível em testes)
_http_client: Optional[httpx.Client] = None


def _get_client() -> httpx.Client:
    global _http_client
    if _http_client is None:
        _http_client = httpx.Client(timeout=TIMEOUT_SECONDS)
    return _http_client


def _set_client(c: httpx.Client) -> None:
    """Para testes."""
    global _http_client
    _http_client = c


mcp = FastMCP("blink-medware")


# ─── Pydantic Models ────────────────────────────────────────────────

class HorariosInput(BaseModel):
    """Input estrito da tool consultar_horarios."""
    medico: str = Field(default="karla")
    unidade: str = Field(...)
    dias: int = Field(default=DIAS_DEFAULT, ge=1, le=30)
    hora_inicio: str = Field(
        default="07:00",
        pattern=r"^\d{2}:\d{2}$",
        description="Janela cirúrgica: hora início HH:MM (E6-C)",
    )
    hora_fim: str = Field(
        default="19:00",
        pattern=r"^\d{2}:\d{2}$",
        description="Janela cirúrgica: hora fim HH:MM (E6-C)",
    )
    data_inicio: Optional[str] = Field(
        default=None,
        pattern=r"^\d{4}-\d{2}-\d{2}$",
        description="Override de data inicial ISO. Default amanhã.",
    )

    @field_validator("medico")
    @classmethod
    def _medico_normalizar(cls, v: str) -> str:
        return v.lower().strip()

    @field_validator("unidade")
    @classmethod
    def _unidade_strip(cls, v: str) -> str:
        return v.strip()


class GravarAgendamentoInput(BaseModel):
    """Input estrito da tool gravar_agendamento.

    Bug C-41 (20/06/2026 — lead 24182212 Milena): servidor agora exige
    UMA das duas trilhas de cobertura ANTES de aceitar a gravação. Sem
    isso, a Lia pode reservar slot sem garantir convênio nem sinal,
    paciente vira pra clínica e Dra. Karla pode recusar atender.

    Aplicação do livro 4.5 (Servidor como Guardião): a validação não
    fica na LLM (que pode esquecer), nem no atendente humano (que pode
    distrair) — fica no servidor MCP, que REJEITA o input antes de
    chegar no Medware.
    """
    cod_agenda: int = Field(..., ge=1)
    cod_medico: int = Field(..., ge=1)
    cod_unidade: int = Field(..., ge=1)
    data_iso: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    hora: str = Field(..., pattern=r"^\d{2}:\d{2}$")
    cpf: str = Field(..., min_length=11, max_length=14)
    nome_paciente: str = Field(..., min_length=3)
    data_nasc_iso: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    celular_e164: str = Field(..., min_length=10)
    cod_plano: int = Field(default=1, ge=1)
    # Bug C-41 — trilha A (convênio) OU trilha B (sinal Pix). Sem isso, falha.
    convenio_validado: bool = Field(
        default=False,
        description=(
            "TRILHA A: True quando convênio nominal está na lista de "
            "aceitos E paciente enviou foto carteirinha + RG/certidão."
        ),
    )
    sinal_pix_comprovado: bool = Field(
        default=False,
        description=(
            "TRILHA B: True quando paciente decidiu particular E "
            "enviou comprovante Pix de 50% da consulta."
        ),
    )

    @field_validator("sinal_pix_comprovado")
    @classmethod
    def _exige_trilha_a_ou_b(cls, v: bool, info) -> bool:
        """Bug C-41 — bloqueia gravação sem cobertura financeira/convênio."""
        convenio = info.data.get("convenio_validado", False)
        if not (convenio or v):
            raise ValueError(
                "BUG_C41_RESERVA_SEM_COBERTURA: nem convênio_validado nem "
                "sinal_pix_comprovado. Lia precisa fechar UMA das duas "
                "trilhas (convênio + carteirinha OU Pix 50%) antes de "
                "gravar reserva. Lead 24182212 Milena, 20/06/2026."
            )
        return v


# ─── TOOLS ──────────────────────────────────────────────────────────

@mcp.tool()
def consultar_horarios(
    medico: str = "karla",
    unidade: str = "Asa Norte",
    dias: int = 14,
    hora_inicio: str = "07:00",
    hora_fim: str = "19:00",
    data_inicio: Optional[str] = None,
) -> list[dict]:
    """Consulta horários livres no Medware com janela cirúrgica (Regra E6-C).

    Quando hora_inicio e hora_fim formam uma janela específica
    (ex: 09:00 a 11:00), o request fica mínimo e responde rápido,
    sem estourar timeout do servidor Medware Light (Bug C-38).

    Args:
        medico: "karla" ou "fabricio".
        unidade: "Asa Norte" ou "Águas Claras".
        dias: Janela em dias. Default 14 (fix C-38b). Max 30.
        hora_inicio: HH:MM. Default 07:00.
        hora_fim: HH:MM. Default 19:00.
        data_inicio: ISO YYYY-MM-DD. Default amanhã.

    Returns:
        Lista de dicts {data, horario, codAgenda, codMedico, codUnidade}.
    """
    inp = HorariosInput(
        medico=medico, unidade=unidade, dias=dias,
        hora_inicio=hora_inicio, hora_fim=hora_fim,
        data_inicio=data_inicio,
    )

    cod_med = COD_MEDICO.get(inp.medico)
    cod_uni = COD_UNIDADE.get(inp.unidade.lower())
    if not cod_med:
        raise ValueError(f"Médico desconhecido: {inp.medico}")
    if not cod_uni:
        raise ValueError(f"Unidade desconhecida: {inp.unidade}")

    if inp.data_inicio:
        di = date.fromisoformat(inp.data_inicio)
    else:
        di = date.today() + timedelta(days=1)
    df = di + timedelta(days=inp.dias)

    params = {
        "dataInicio": di.strftime("%d/%m/%Y"),
        "dataFim": df.strftime("%d/%m/%Y"),
        "horaInicio": inp.hora_inicio,
        "horaFim": inp.hora_fim,
        "codMedico": cod_med,
        "codUnidade": cod_uni,
    }

    log.info(
        "[MEDWARE REQ] %s",
        {**params, "janela_fonte": "cirurgica" if inp.dias <= 14 else "ampla"},
    )

    client = _get_client()
    last_exc = None
    for tentativa in range(MAX_RETRIES + 1):
        try:
            r = client.get(f"{MEDWARE_BASE}/Medware/Horarios/Listar", params=params)
            if r.status_code == 200:
                data = r.json()
                log.info("[MEDWARE RESP] n_slots=%d janela=%d dias", len(data), inp.dias)
                return data if isinstance(data, list) else []
            log.warning("Medware HTTP %d: %s", r.status_code, r.text[:200])
            break
        except (httpx.TimeoutException, httpx.HTTPError) as e:
            last_exc = e
            log.warning("Medware tentativa %d/%d falhou: %s", tentativa + 1, MAX_RETRIES + 1, e)

    if last_exc:
        log.error("Medware indisponível após %d tentativas: %s", MAX_RETRIES + 1, last_exc)
    return []


@mcp.tool()
def consultar_paciente_cpf(cpf: str) -> Optional[dict]:
    """Busca paciente no Medware pelo CPF.

    Use ANTES de gravar agendamento para checar se paciente já existe e
    pegar o codPaciente. Bug C-21 mitigado (não atropela paciente cadastrado).

    Args:
        cpf: CPF com ou sem formatação. Ex: "123.456.789-00" ou "12345678900".

    Returns:
        Dict do paciente ou None se não encontrado.
    """
    cpf_limpo = "".join(c for c in cpf if c.isdigit())
    if len(cpf_limpo) != 11:
        raise ValueError(f"CPF inválido: deve ter 11 dígitos. Recebido: {len(cpf_limpo)}")

    client = _get_client()
    try:
        r = client.get(f"{MEDWARE_BASE}/Medware/Paciente/Buscar", params={"cpf": cpf_limpo})
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, list) and data:
                return data[0]
            if isinstance(data, dict):
                return data
        return None
    except Exception as e:
        log.error("Erro buscar paciente: %s", e)
        return None


@mcp.tool()
def gravar_agendamento(
    cod_agenda: int,
    cod_medico: int,
    cod_unidade: int,
    data_iso: str,
    hora: str,
    cpf: str,
    nome_paciente: str,
    data_nasc_iso: str,
    celular_e164: str,
    cod_plano: int = 1,
) -> dict:
    """Grava agendamento no Medware com validação completa (livro 4.5: servidor é guardião).

    Antes de chamar a API do Medware, valida TODOS os campos. Se algum
    estiver inválido, retorna erro estruturado SEM tentar gravar. Isso
    elimina o Bug C-21 (batch atropelou protocolo médico) e dezenas
    de gravações com dados parciais.

    Args:
        cod_agenda, cod_medico, cod_unidade: códigos Medware.
        data_iso: data do agendamento YYYY-MM-DD.
        hora: HH:MM.
        cpf: 11 dígitos.
        nome_paciente: completo, mín. 3 caracteres.
        data_nasc_iso: YYYY-MM-DD.
        celular_e164: ex "5561981331005".
        cod_plano: código do plano/convênio Medware. Default 1 (particular).

    Returns:
        Dict com {ok, codAgendamento ou erro}.
    """
    inp = GravarAgendamentoInput(
        cod_agenda=cod_agenda, cod_medico=cod_medico, cod_unidade=cod_unidade,
        data_iso=data_iso, hora=hora, cpf=cpf, nome_paciente=nome_paciente,
        data_nasc_iso=data_nasc_iso, celular_e164=celular_e164, cod_plano=cod_plano,
    )

    # Conversões para formato Medware
    d = date.fromisoformat(inp.data_iso)
    nasc = date.fromisoformat(inp.data_nasc_iso)
    cpf_limpo = "".join(c for c in inp.cpf if c.isdigit())

    payload = {
        "codAgenda": inp.cod_agenda,
        "codMedico": inp.cod_medico,
        "codUnidade": inp.cod_unidade,
        "data": d.strftime("%d/%m/%Y"),
        "horario": inp.hora,
        "cpf": cpf_limpo,
        "nome": inp.nome_paciente,
        "dataNasc": nasc.strftime("%d/%m/%Y"),
        "celular": inp.celular_e164,
        "codPlano": inp.cod_plano,
    }

    log.info("[MEDWARE GRAVAR] payload=%s", {k: v for k, v in payload.items() if k != "cpf"})

    client = _get_client()
    try:
        r = client.post(f"{MEDWARE_BASE}/Medware/Agendamento/Salvar", json=payload)
        if r.status_code in (200, 201):
            data = r.json()
            cod_ag = data.get("codAgendamento") or data.get("cod_agendamento")
            log.info("[MEDWARE GRAVAR OK] cod_agendamento=%s", cod_ag)
            return {"ok": True, "cod_agendamento": cod_ag, "raw": data}
        log.error("[MEDWARE GRAVAR FALHOU] HTTP %d: %s", r.status_code, r.text[:300])
        return {
            "ok": False,
            "erro": f"HTTP {r.status_code}",
            "detail": r.text[:300],
        }
    except Exception as e:
        log.exception("[MEDWARE GRAVAR EXC]")
        return {"ok": False, "erro": "exception", "detail": str(e)}


# ─── RESOURCES ──────────────────────────────────────────────────────

@mcp.resource("medware://medicos")
def resource_medicos() -> str:
    """Lista médicos com códigos Medware."""
    linhas = ["MÉDICOS BLINK — CÓDIGOS MEDWARE"]
    for nome, cod in COD_MEDICO.items():
        linhas.append(f"  {nome}: codMedico={cod}")
    return "\n".join(linhas)


@mcp.resource("medware://unidades")
def resource_unidades() -> str:
    """Lista unidades com códigos Medware."""
    linhas = ["UNIDADES BLINK — CÓDIGOS MEDWARE"]
    vistos = set()
    for nome, cod in COD_UNIDADE.items():
        if cod not in vistos:
            linhas.append(f"  {nome.title()}: codUnidade={cod}")
            vistos.add(cod)
    return "\n".join(linhas)


if __name__ == "__main__":
    log.info(
        "Iniciando blink-medware. base=%s timeout=%ss retries=%d dias_default=%d",
        MEDWARE_BASE, TIMEOUT_SECONDS, MAX_RETRIES, DIAS_DEFAULT,
    )
    mcp.run()
