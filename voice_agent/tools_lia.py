"""Tools estruturadas pro Claude da Lia — task #126 (otimizador #1).

Hoje a Lia escreve texto livre. Outras camadas (detector Haiku, kommo
auto-preenchimento, executor de agendamento) TENTAM interpretar a
intenção da mensagem em paralelo. Frágil.

Com tool calling, o modelo CHAMA uma ferramenta atômica e a resposta
humana é gerada DEPOIS, em cima do resultado real. Cada ação tem
schema definido e validação imediata. Origem: bug Juliene mostrou
que sem ação atômica, a Lia "improvisa" um caminho humano fictício.

3 tools desta fase:

1. `oferecer_slot` — modelo escolhe 2 slots da agenda real e os
   apresenta. Pipeline grava a oferta em Redis (rastreável).

2. `confirmar_dados_paciente` — quando paciente passou nome completo,
   data nasc e CPF. Pipeline valida formato + grava no Kommo.

3. `gravar_agendamento_medware` — gatilho explícito do `salvar_agendamento`.
   Antes era detector Haiku semântico — agora vira tool atômica.

Modo: OPT-IN via env `LIA_TOOLS_ENABLED=1`. Se desligado, responder
funciona exatamente como hoje. Permite rollout gradual.
"""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any, Optional

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Mapas Medware — codMedico/codUnidade por nome humano
# Fonte: mcp__medware__listar_medicos / listar_unidades em 04/06/2026.
# Chaves normalizadas (lowercase, sem acentos via simples replace).
# ---------------------------------------------------------------------------

COD_MEDICO_POR_NOME: dict[str, int] = {
    "karla": 12080,
    "karla delalibera": 12080,
    "dra. karla": 12080,
    "dra karla": 12080,
    "dra. karla delalibera": 12080,
    "fabricio": 12081,
    "fabrício": 12081,
    "fabricio freitas": 12081,
    "fabrício freitas": 12081,
    "dr. fabricio": 12081,
    "dr. fabrício": 12081,
    "dr. fabricio freitas": 12081,
    "dr. fabrício freitas": 12081,
}

COD_UNIDADE_POR_NOME: dict[str, int] = {
    "asa norte": 5,
    "asanorte": 5,
    "an": 5,
    "aguas claras": 3,
    "águas claras": 3,
    "aguasclaras": 3,
    "ac": 3,
}


def _normalize(s: str) -> str:
    """lowercase + strip + colapsa espaços. NÃO remove acentos."""
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def cod_medico_por_nome(nome: str) -> int:
    """Resolve codMedico a partir do nome humano. Default Karla=12080."""
    return COD_MEDICO_POR_NOME.get(_normalize(nome), 12080)


def cod_unidade_por_nome(nome: str) -> int:
    """Resolve codUnidade a partir do nome humano. Default Asa Norte=5."""
    return COD_UNIDADE_POR_NOME.get(_normalize(nome), 5)


# ---------------------------------------------------------------------------
# Schemas das 3 tools (formato Anthropic tool_use)
# ---------------------------------------------------------------------------

TOOL_OFERECER_SLOT = {
    "name": "oferecer_slot",
    "description": (
        "Oferece 1 ou 2 slots concretos de agenda ao paciente. Use SOMENTE "
        "slots que estão na lista 'AGENDA REAL' do system prompt. NUNCA "
        "invente. Use quando o paciente já deu preferência de dia/turno e "
        "você está em estado AGENDA."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "slots": {
                "type": "array",
                "minItems": 1,
                "maxItems": 2,
                "items": {
                    "type": "object",
                    "properties": {
                        "data_iso": {
                            "type": "string",
                            "description": "Data no formato YYYY-MM-DD",
                        },
                        "hora": {
                            "type": "string",
                            "description": "HH:MM (24h)",
                        },
                        "dia_semana": {
                            "type": "string",
                            "description": (
                                "ex: 'terça-feira'. Tem que casar com "
                                "data_iso (calendário Python valida)."
                            ),
                        },
                        "cod_agenda": {
                            "type": "integer",
                            "description": "cod_agenda do Medware (da lista)",
                        },
                    },
                    "required": ["data_iso", "hora", "dia_semana"],
                },
            },
            "mensagem_humana": {
                "type": "string",
                "description": (
                    "Frase curta e calorosa pro paciente, formato livre "
                    "(será exibida no WhatsApp). Mencione os slots."
                ),
            },
        },
        "required": ["slots", "mensagem_humana"],
    },
}

TOOL_CONFIRMAR_DADOS_PACIENTE = {
    "name": "confirmar_dados_paciente",
    "description": (
        "Registra os dados do paciente quando ele(a) acabou de informar. "
        "Use quando paciente passou nome completo + data nasc (+ CPF, "
        "que só é obrigatório quando atendimento é PARTICULAR). Para "
        "qualquer convênio aceito o CPF é OPCIONAL. Pipeline valida "
        "formato e grava no Kommo."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "nome_completo_paciente": {
                "type": "string",
                "description": "Nome completo (mínimo 3 tokens fortes)",
            },
            "data_nascimento": {
                "type": "string",
                "description": "DD/MM/YYYY ou YYYY-MM-DD",
            },
            "cpf_paciente": {
                "type": "string",
                "description": (
                    "CPF do paciente (11 dígitos). Se menor de idade, "
                    "informe cpf_responsavel."
                ),
            },
            "cpf_responsavel": {
                "type": "string",
                "description": (
                    "CPF do responsável legal (quando paciente é menor)."
                ),
            },
            "mensagem_humana": {
                "type": "string",
                "description": "Frase de confirmação pro paciente",
            },
        },
        "required": ["mensagem_humana"],
    },
}

TOOL_GRAVAR_AGENDAMENTO_MEDWARE = {
    "name": "gravar_agendamento_medware",
    "description": (
        "Dispara gravação do agendamento no sistema Medware. Use SOMENTE "
        "quando paciente confirmou EXPLICITAMENTE 1 slot oferecido e "
        "os dados obrigatórios (nome, data nasc, convênio) estão "
        "presentes. CPF é obrigatório APENAS para Particular — para "
        "convênio aceito, CPF é opcional."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "cod_agenda": {
                "type": "integer",
                "description": "cod_agenda do slot escolhido (da lista AGENDA REAL)",
            },
            "data_iso": {
                "type": "string",
                "description": "YYYY-MM-DD do slot",
            },
            "hora": {
                "type": "string",
                "description": "HH:MM do slot",
            },
            "mensagem_humana": {
                "type": "string",
                "description": "Frase pro paciente confirmando o agendamento",
            },
        },
        "required": ["cod_agenda", "data_iso", "hora", "mensagem_humana"],
    },
}


ALL_TOOLS = [
    TOOL_OFERECER_SLOT,
    TOOL_CONFIRMAR_DADOS_PACIENTE,
    TOOL_GRAVAR_AGENDAMENTO_MEDWARE,
]


# ---------------------------------------------------------------------------
# Toggle global — default ON desde Bug C-32 (16/06/2026).
# ---------------------------------------------------------------------------
#
# Bug C-32: env esquecida = code completed mas inerte. Reincidente em C-29,
# C-30, C-31 — todas com a mesma causa raiz "código existe mas env não foi
# setada". Inverter padrão pra DEFAULT ON resolve estruturalmente.
#
# Pra desligar (rollback emergencial), setar LIA_TOOLS_ENABLED=0 explicitamente.

def tools_habilitadas() -> bool:
    """Default ON. Pra desligar: LIA_TOOLS_ENABLED=0 (ou "false"/"no")."""
    val = (os.environ.get("LIA_TOOLS_ENABLED") or "1").lower().strip()
    return val not in ("0", "false", "no", "off", "")


# ---------------------------------------------------------------------------
# Resultado de execução de 1 tool
# ---------------------------------------------------------------------------

@dataclass
class ResultadoTool:
    """Devolvido pelo Claude após executar 1 tool.

    `texto_para_paciente` = string final a enviar ao WhatsApp (vem do
       `mensagem_humana` da tool ou é construída pela função handler).
    `efeitos_colaterais` = log das ações realizadas (pra observability).
    `erro` = mensagem se falhou (caso paciente precise saber).
    """
    texto_para_paciente: str
    efeitos_colaterais: list[str] = field(default_factory=list)
    erro: Optional[str] = None
    tool_name: str = ""


# ---------------------------------------------------------------------------
# Handlers — recebem input da tool + contexto, fazem ação
# ---------------------------------------------------------------------------

def handle_oferecer_slot(
    inputs: dict,
    caller_context: Optional[dict],
    redis_client=None,
) -> ResultadoTool:
    """Valida slots oferecidos contra AGENDA REAL + grava oferta em Redis."""
    slots = inputs.get("slots") or []
    msg = (inputs.get("mensagem_humana") or "").strip()
    if not slots:
        return ResultadoTool(
            texto_para_paciente="",
            erro="oferecer_slot chamada sem slots",
            tool_name="oferecer_slot",
        )

    # Validar slots contra agenda real no ctx
    agenda_real = (caller_context or {}).get("agenda") or []
    if agenda_real:
        agenda_set = {(s.get("data_iso"), s.get("hora")) for s in agenda_real}
        invalidos = [
            (s.get("data_iso"), s.get("hora")) for s in slots
            if (s.get("data_iso"), s.get("hora")) not in agenda_set
        ]
        if invalidos:
            return ResultadoTool(
                texto_para_paciente="",
                erro=f"slots fora da AGENDA REAL: {invalidos}",
                tool_name="oferecer_slot",
            )

    # Grava oferta em Redis pra rastreio
    efeitos = [f"ofertou {len(slots)} slots"]
    if redis_client is not None and caller_context:
        try:
            convo_key = caller_context.get("conversation_key", "")
            if convo_key:
                redis_client.setex(
                    f"blink:oferta:{convo_key}",
                    7200,
                    json.dumps({"slots": slots, "ts": __import__("time").time()}),
                )
                efeitos.append("oferta gravada em Redis (TTL 2h)")
        except Exception as e:  # noqa: BLE001
            efeitos.append(f"redis falhou: {e}")

    # Métricas live (task #260)
    try:
        from . import metricas_funcionamento as _mf
        _mf.incrementar(redis_client, "tool:oferecer_slot:ok")
    except Exception:  # noqa: BLE001
        pass

    return ResultadoTool(
        texto_para_paciente=msg,
        efeitos_colaterais=efeitos,
        tool_name="oferecer_slot",
    )


def handle_confirmar_dados_paciente(
    inputs: dict,
    caller_context: Optional[dict],
    kommo_client=None,
) -> ResultadoTool:
    """Valida formato dos dados + grava no Kommo via update_lead_fields."""
    nome = (inputs.get("nome_completo_paciente") or "").strip()
    data = (inputs.get("data_nascimento") or "").strip()
    cpf_p = (inputs.get("cpf_paciente") or "").strip()
    cpf_r = (inputs.get("cpf_responsavel") or "").strip()
    msg = (inputs.get("mensagem_humana") or "").strip()

    # Valida (mesma lib do checklist)
    from voice_agent.checklist_dados_minimos import (
        cpf_ok,
        data_nascimento_ok,
        nome_completo_ok,
    )
    erros = []
    if nome and not nome_completo_ok(nome):
        erros.append(f"nome '{nome}' não tem 3 tokens fortes")
    if data and not data_nascimento_ok(data):
        erros.append(f"data_nascimento '{data}' formato inválido")
    if cpf_p and not cpf_ok(cpf_p):
        erros.append(f"cpf_paciente '{cpf_p}' inválido")
    if cpf_r and not cpf_ok(cpf_r):
        erros.append(f"cpf_responsavel '{cpf_r}' inválido")
    if erros:
        return ResultadoTool(
            texto_para_paciente="",
            erro="; ".join(erros),
            tool_name="confirmar_dados_paciente",
        )

    efeitos = []
    # Grava no Kommo
    if kommo_client is not None and caller_context:
        try:
            lead_id = caller_context.get("lead_id")
            if lead_id:
                campos = {}
                if nome:
                    campos["nome_paciente"] = nome
                if data:
                    campos["data_nascimento"] = data
                if cpf_p:
                    campos["cpf_paciente"] = cpf_p
                if cpf_r:
                    campos["cpf_responsavel"] = cpf_r
                if campos:
                    kommo_client.update_lead_fields(lead_id, campos)
                    efeitos.append(f"gravou {len(campos)} campos Kommo lead {lead_id}")
        except Exception as e:  # noqa: BLE001
            efeitos.append(f"kommo falhou: {e}")

    return ResultadoTool(
        texto_para_paciente=msg,
        efeitos_colaterais=efeitos,
        tool_name="confirmar_dados_paciente",
    )


def handle_gravar_agendamento_medware(
    inputs: dict,
    caller_context: Optional[dict],
    medware_client=None,
    redis_client=None,
) -> ResultadoTool:
    """Dispara salvar_agendamento Medware. Pré-condição: checklist OK
    + slot tem que estar na AGENDA REAL.
    """
    cod_agenda = inputs.get("cod_agenda")
    data_iso = (inputs.get("data_iso") or "").strip()
    hora = (inputs.get("hora") or "").strip()
    msg = (inputs.get("mensagem_humana") or "").strip()

    # Pré-validação dura
    if caller_context:
        checklist = caller_context.get("checklist_dados_minimos") or {}
        if not checklist.get("pronto_para_oferecer_slot"):
            return ResultadoTool(
                texto_para_paciente="",
                erro=(
                    "checklist incompleto: "
                    f"{checklist.get('campos_pendentes')}"
                ),
                tool_name="gravar_agendamento_medware",
            )
        agenda_real = caller_context.get("agenda") or []
        if agenda_real:
            agenda_set = {(s.get("data_iso"), s.get("hora")) for s in agenda_real}
            if (data_iso, hora) not in agenda_set:
                return ResultadoTool(
                    texto_para_paciente="",
                    erro=f"slot ({data_iso} {hora}) NÃO está na AGENDA REAL",
                    tool_name="gravar_agendamento_medware",
                )

    efeitos = []
    convo_key = (caller_context or {}).get("conversation_key", "")

    # DEDUP: se já gravamos pra essa conversa nas últimas 24h, retorna OK
    # sem chamar Medware de novo (evita duplicação por re-tool-call).
    if redis_client is not None and convo_key:
        try:
            ja = redis_client.get(f"blink:agendamento_gravado:{convo_key}")
            if ja:
                payload = ja.decode() if isinstance(ja, bytes) else ja
                efeitos.append(f"dedup: já gravado antes ({payload[:80]})")
                return ResultadoTool(
                    texto_para_paciente=msg,
                    efeitos_colaterais=efeitos,
                    tool_name="gravar_agendamento_medware",
                )
        except Exception as e:  # noqa: BLE001
            log.warning("dedup redis falhou: %s", e)

    # CHAMADA REAL ao Medware (era stub Redis até 04/06/2026 — task #208).
    if medware_client is not None and caller_context:
        known = (caller_context.get("known") or {})
        try:
            medico_nome = known.get("medico") or caller_context.get("medico") or ""
            unidade_nome = known.get("unidade") or ""
            cod_med = cod_medico_por_nome(medico_nome)
            cod_uni = cod_unidade_por_nome(unidade_nome)

            # data_hora "YYYY-MM-DDTHH:MM" — medware.criar_agendamento já aceita esse formato
            data_hora = f"{data_iso}T{hora}" if "T" not in data_iso else data_iso

            # MODO DRY-RUN (ambiente de teste, 06/06/2026 — task #183 follow-up)
            # Quando LIA_GRAVACAO_DRY_RUN=1, faz TODAS validações + log estruturado
            # MAS NÃO chama medware_client.criar_agendamento. Resposta humana sai
            # normalmente. Marca dedup Redis com prefixo "dryrun:" pra diferenciar
            # de gravação real. Operador valida fluxo completo sem efeito Medware.
            import os as _os_dry
            if _os_dry.environ.get("LIA_GRAVACAO_DRY_RUN", "0") == "1":
                log.info(
                    "[GRAVAR-MEDWARE][DRY-RUN] convo=%s cod_med=%s cod_uni=%s "
                    "slot=%s %s nome=%r cpf=%r convenio=%r",
                    convo_key, cod_med, cod_uni, data_iso, hora,
                    known.get("nome_paciente", ""), known.get("cpf", ""),
                    known.get("convenio"),
                )
                efeitos.append(
                    f"DRY-RUN: validações OK, NÃO chamado Medware. "
                    f"med={cod_med} uni={cod_uni} slot={data_iso} {hora}"
                )
                if redis_client is not None and convo_key:
                    try:
                        redis_client.setex(
                            f"blink:agendamento_gravado:{convo_key}",
                            86400,
                            json.dumps({
                                "dry_run": True,
                                "data_iso": data_iso, "hora": hora,
                                "cod_medico": cod_med, "cod_unidade": cod_uni,
                            }),
                        )
                    except Exception as e:  # noqa: BLE001
                        efeitos.append(f"redis dry-run dedup falhou: {e}")
                return ResultadoTool(
                    texto_para_paciente=msg,
                    efeitos_colaterais=efeitos,
                    tool_name="gravar_agendamento_medware",
                )

            resultado = medware_client.criar_agendamento(
                cod_medico=cod_med,
                cod_unidade=cod_uni,
                cod_agenda=int(cod_agenda) if cod_agenda else 0,
                data_hora=data_hora,
                nome=known.get("nome_paciente", ""),
                cpf=known.get("cpf", ""),
                data_nascimento=known.get("data_nasc", "") or known.get("data_nascimento", ""),
                celular=known.get("celular", "") or known.get("telefone", ""),
                convenio=known.get("convenio"),
                obs=f"Agendado via Lia (Cowork) — conv {convo_key}",
            )

            if resultado.get("ok"):
                cod_ag = resultado.get("cod_agendamento") or resultado.get("codAgendamento") or 0
                efeitos.append(
                    f"MEDWARE OK: codAgendamento={cod_ag} med={cod_med} uni={cod_uni}"
                )
                log.info(
                    "[GRAVAR-MEDWARE] OK convo=%s cod_ag=%s med=%s uni=%s slot=%s %s",
                    convo_key, cod_ag, cod_med, cod_uni, data_iso, hora,
                )
                # Métricas live (task #260)
                try:
                    from . import metricas_funcionamento as _mf
                    _mf.incrementar(redis_client, "tool:gravar_agendamento_medware:ok")
                except Exception:  # noqa: BLE001
                    pass
                # Marca Redis pra dedup de 24h (futuras tool calls não re-gravam)
                if redis_client is not None and convo_key:
                    try:
                        redis_client.setex(
                            f"blink:agendamento_gravado:{convo_key}",
                            86400,
                            json.dumps({
                                "cod_agendamento": cod_ag,
                                "cod_agenda": cod_agenda,
                                "data_iso": data_iso,
                                "hora": hora,
                                "cod_medico": cod_med,
                                "cod_unidade": cod_uni,
                            }),
                        )
                    except Exception as e:  # noqa: BLE001
                        efeitos.append(f"redis dedup falhou: {e}")
            else:
                # Erro Medware (convênio desconhecido, conflito, etc.) — escalar
                motivo = resultado.get("motivo") or "desconhecido"
                detalhe = resultado.get("detalhe", "")[:120]
                efeitos.append(f"MEDWARE ERRO motivo={motivo} {detalhe}")
                log.error(
                    "[GRAVAR-MEDWARE] FAIL convo=%s motivo=%s detalhe=%s",
                    convo_key, motivo, detalhe,
                )
                # Métricas live (task #260)
                try:
                    from . import metricas_funcionamento as _mf
                    _mf.incrementar(redis_client, "tool:gravar_agendamento_medware:fail")
                except Exception:  # noqa: BLE001
                    pass
                return ResultadoTool(
                    texto_para_paciente="",
                    erro=f"medware_falhou: {motivo}",
                    efeitos_colaterais=efeitos,
                    tool_name="gravar_agendamento_medware",
                )
        except Exception as e:  # noqa: BLE001
            log.exception("[GRAVAR-MEDWARE] EXCEPTION convo=%s", convo_key)
            efeitos.append(f"exception: {e}")
            return ResultadoTool(
                texto_para_paciente="",
                erro=f"medware_exception: {e}",
                efeitos_colaterais=efeitos,
                tool_name="gravar_agendamento_medware",
            )
    else:
        # Sem medware_client (modo teste/unit) — registra flag Redis legado
        if redis_client is not None and convo_key:
            try:
                redis_client.setex(
                    f"blink:tool_gravacao_solicitada:{convo_key}",
                    600,
                    json.dumps({"cod_agenda": cod_agenda, "data_iso": data_iso, "hora": hora}),
                )
                efeitos.append("solicitação gravada em Redis (sem medware_client)")
            except Exception as e:  # noqa: BLE001
                efeitos.append(f"redis falhou: {e}")

    return ResultadoTool(
        texto_para_paciente=msg,
        efeitos_colaterais=efeitos,
        tool_name="gravar_agendamento_medware",
    )


# ---------------------------------------------------------------------------
# Dispatcher genérico
# ---------------------------------------------------------------------------

HANDLERS = {
    "oferecer_slot": handle_oferecer_slot,
    "confirmar_dados_paciente": handle_confirmar_dados_paciente,
    "gravar_agendamento_medware": handle_gravar_agendamento_medware,
}


def executar_tool(
    nome_tool: str,
    inputs: dict,
    caller_context: Optional[dict],
    kommo_client=None,
    medware_client=None,
    redis_client=None,
) -> ResultadoTool:
    """Dispatcher genérico — encontra handler por nome e executa."""
    handler = HANDLERS.get(nome_tool)
    if not handler:
        return ResultadoTool(
            texto_para_paciente="",
            erro=f"tool desconhecida: {nome_tool}",
            tool_name=nome_tool,
        )
    # Cada handler tem assinatura específica — passa só o que precisa
    kwargs = {"caller_context": caller_context}
    if nome_tool == "oferecer_slot":
        kwargs["redis_client"] = redis_client
    elif nome_tool == "confirmar_dados_paciente":
        kwargs["kommo_client"] = kommo_client
    elif nome_tool == "gravar_agendamento_medware":
        kwargs["medware_client"] = medware_client
        kwargs["redis_client"] = redis_client
    try:
        return handler(inputs, **kwargs)
    except Exception as e:  # noqa: BLE001
        log.exception("[TOOL] %s falhou", nome_tool)
        return ResultadoTool(
            texto_para_paciente="",
            erro=f"exception: {e}",
            tool_name=nome_tool,
        )
