"""Pydantic models — validação estrita ANTES de a LLM chamar tools.

Livro 6.5: defesa contra "Argument Hallucination" da LLM.
"""
from __future__ import annotations
from datetime import date
from typing import Optional
from pydantic import BaseModel, Field, field_validator


class ValidarDataInput(BaseModel):
    """Input estrito da tool validar_data_unidade."""
    data: date = Field(
        ...,
        description="Data no formato ISO YYYY-MM-DD. Ex: 2026-06-29",
    )
    medico: str = Field(
        default="karla",
        description="Nome curto do médico: 'karla' ou 'fabricio'. Case-insensitive.",
    )
    unidade_pretendida: Optional[str] = Field(
        default=None,
        description=(
            "Unidade que o atendente quer oferecer. "
            "Valores aceitos: 'Asa Norte' ou 'Águas Claras'. "
            "Se ausente, valida apenas se médico atende naquele dia."
        ),
    )

    @field_validator("medico")
    @classmethod
    def _medico_lower(cls, v: str) -> str:
        return v.lower().strip()


class DataInfoOutput(BaseModel):
    """Saída tipada da tool validar_data_unidade."""
    data_iso: str = Field(description="Data ISO YYYY-MM-DD")
    data_br: str = Field(description="Data formato brasileiro DD/MM/YYYY")
    dia: str = Field(description="Dia da semana por extenso. Ex: Quinta-feira")
    dia_idx: int = Field(description="Índice 0-6 (0=segunda, 6=domingo)")
    unidade_atende: Optional[str] = Field(
        description="Unidade onde o médico atende NESSE dia. None se não atende."
    )
    valido_para_oferta: bool = Field(
        description=(
            "True se a data é válida para ofertar slot ao paciente. "
            "False quando: dia não é de atendimento, OU unidade_pretendida "
            "não bate com a unidade real daquele dia."
        )
    )
    texto_pronto: str = Field(
        description=(
            "Texto pronto para colar em nota Kommo ou WhatsApp. "
            "Ex: 'Quinta-feira (18/06) — Águas Claras'"
        )
    )
    motivo_invalido: Optional[str] = Field(
        default=None,
        description="Quando valido_para_oferta=False, explica o motivo.",
    )


class ProximasDatasInput(BaseModel):
    """Input da tool proximas_datas_disponiveis."""
    medico: str = Field(default="karla")
    unidade: str = Field(
        ...,
        description="Unidade alvo: 'Asa Norte' ou 'Águas Claras' (case-insensitive)",
    )
    n: int = Field(
        default=4,
        ge=1,
        le=20,
        description="Quantas próximas datas retornar. Mínimo 1, máximo 20.",
    )

    @field_validator("medico", "unidade")
    @classmethod
    def _strip(cls, v: str) -> str:
        return v.strip()


class GerarOfertaInput(BaseModel):
    """Input da tool gerar_oferta_pronta."""
    medico: str = Field(default="karla")
    unidade: str = Field(...)
    hora1: str = Field(
        ...,
        pattern=r"^\d{2}:\d{2}$",
        description="Hora do primeiro slot no formato HH:MM. Ex: 09:30",
    )
    hora2: str = Field(
        ...,
        pattern=r"^\d{2}:\d{2}$",
        description="Hora do segundo slot no formato HH:MM. Ex: 14:30",
    )
    nome_paciente: Optional[str] = Field(
        default=None,
        description="Primeiro nome do paciente, opcional. Personaliza a saudação.",
    )


class OfertaProntaOutput(BaseModel):
    """Mensagem pronta para colar no WhatsApp."""
    mensagem: str = Field(description="Texto formatado canônico 1️⃣/2️⃣")
    data1_iso: str
    data2_iso: str
    data1_br: str
    data2_br: str
    dia1: str
    dia2: str
