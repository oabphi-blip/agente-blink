"""Orquestrador: junta Whisper (OpenAI) + Claude (Anthropic) + Evolution.

Whitelist é aplicada ANTES de enviar — em modo soft launch, só os números
autorizados em settings recebem resposta. Demais ficam apenas logados.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Optional

from . import followup
from .evolution import EvolutionClient, EvolutionError
from .kommo import KommoClient
from .responder import Responder
from .settings import Settings
from .transcribe import Transcriber

log = logging.getLogger(__name__)


# === AGENDA SUSPENSA (kill-switch operacional — Fábio 22/07/2026) ===
_AGENDA_SUSPENSA_TERMOS = (
    "horário", "horario", "horarios", "horários", "vaga", "vagas",
    "disponibilidade", "disponível", "disponivel", "agendar", "marcar",
    "que dia", "quais dias", "tem para", "tem pra",
)


def _agenda_suspensa_ativa() -> bool:
    """True se o kill-switch operacional AGENDA_SUSPENSA está ligado."""
    import os
    return os.getenv("AGENDA_SUSPENSA", "0").lower() in ("1", "true", "yes", "on")


def _texto_pede_agendamento(user_text: Optional[str]) -> bool:
    """Paciente pediu horário/agendamento (gatilho de handoff c/ agenda suspensa)."""
    if not user_text:
        return False
    baixo = user_text.lower()
    return any(t in baixo for t in _AGENDA_SUSPENSA_TERMOS)


@dataclass
class PipelineResult:
    transcript: str
    answer: str
    sent: bool
    model_used: str
    articles_used: list[str]
    blocked_by_whitelist: bool = False
    error: Optional[str] = None


class VoicePipeline:
    def __init__(
        self,
        transcriber: Transcriber,
        responder: Responder,
        evolution: EvolutionClient,
        settings: Settings,
        conversation_store=None,
        medware=None,
    ):
        self.transcriber = transcriber
        self.responder = responder
        self.evolution = evolution
        self.settings = settings
        self.store = conversation_store
        self.medware = medware
        self._redis = getattr(conversation_store, "_redis", None)
        self.kommo: Optional[KommoClient] = (
            KommoClient(subdomain=settings.kommo_subdomain, token=settings.kommo_token)
            if settings.kommo_enabled
            else None
        )

    def process_audio_bytes(
        self,
        audio_bytes: bytes,
        mime_type: str,
        conversation_key: str,
        reply_to_number: Optional[str] = None,
        quoted_message_id: Optional[str] = None,
        send_typing: bool = True,
    ) -> PipelineResult:
        return self._process_inner(
            user_input_factory=lambda: self.transcriber.transcribe(
                audio_bytes, mime_type=mime_type
            ),
            input_kind="audio",
            conversation_key=conversation_key,
            reply_to_number=reply_to_number,
            quoted_message_id=quoted_message_id,
            send_typing=send_typing,
        )

    def process_text(
        self,
        text: str,
        conversation_key: str,
        reply_to_number: Optional[str] = None,
        quoted_message_id: Optional[str] = None,
        send_typing: bool = True,
    ) -> PipelineResult:
        return self._process_inner(
            user_input_factory=lambda: text,
            input_kind="text",
            conversation_key=conversation_key,
            reply_to_number=reply_to_number,
            quoted_message_id=quoted_message_id,
            send_typing=send_typing,
        )

    # ----------------------------------------------------- internal

    def _process_inner(
        self,
        user_input_factory,
        input_kind: str,
        conversation_key: str,
        reply_to_number: Optional[str],
        quoted_message_id: Optional[str],
        send_typing: bool,
    ) -> PipelineResult:
        # 0) Whitelist DESATIVADA — atendimento público geral. O agente
        # responde a TODOS os números (soft launch encerrado). O bloco de
        # bloqueio por whitelist foi removido de propósito.

        # 0-B) LOCK CROSS-RAJADA (Bug #183, casos Kamila/Iara/Janeide 02/06/2026)
        # Pacientes mandam 5 mensagens em 3s. Sem lock, cada inbound dispara
        # um turn paralelo gerando rajadas redundantes ("ainda buscando..." 2x).
        # Estratégia: lock NX 30s por conversation_key. Se já existe lock,
        # descarta o request (a thread em andamento já processa o estado
        # mais recente quando completar). Bypass via PIPELINE_LOCK_ENABLED=0.
        import os as _os
        if _os.environ.get("PIPELINE_LOCK_ENABLED", "1") == "1" and self._redis:
            try:
                lock_key = f"blink:lock_pipeline:{conversation_key}"
                # TTL 8s = cobre processamento típico (3-5s) + margem. Patient
                # legítimo que digita > 8s entre mensagens não é bloqueado.
                lock_ttl = int(_os.environ.get("PIPELINE_LOCK_TTL", "8"))
                lock_set = self._redis.set(
                    lock_key, "1", nx=True, ex=lock_ttl,
                )
                if not lock_set:
                    log.warning(
                        "[pipeline-lock] convo=%s já travado — descartando "
                        "inbound rajada", conversation_key,
                    )
                    return PipelineResult(
                        transcript="", answer="", sent=False,
                        model_used="", articles_used=[],
                        error="conversation_locked",
                    )
            except Exception as e:  # noqa: BLE001
                # Redis fora — log e segue sem lock (degradação segura).
                log.warning("[pipeline-lock] falha redis: %s", e)

        # 1) Presença "digitando" (best-effort)
        if send_typing and reply_to_number:
            self.evolution.send_typing(reply_to_number)

        # 2) Extrai input do usuário (transcrição ou texto bruto)
        try:
            user_text = user_input_factory()
        except Exception as e:  # noqa: BLE001
            log.exception("falha ao obter input do usuário (%s)", input_kind)
            return PipelineResult(
                transcript="", answer="", sent=False,
                model_used="", articles_used=[],
                error=f"input_{input_kind}: {e}",
            )

        if not user_text or not user_text.strip():
            return PipelineResult(
                transcript="", answer="", sent=False,
                model_used="", articles_used=[],
                error="entrada vazia",
            )

        # Follow-up pós-valor: o paciente acabou de interagir → limpa
        # qualquer marcador de follow-up pendente desta conversa.
        try:
            followup.clear_pending(self._redis, conversation_key)
        except Exception:  # noqa: BLE001
            pass

        # 2b) Onboarding orquestrado — busca no Kommo o que já se sabe deste
        # contato. Feito em TODA mensagem (não só na primeira): assim o agente
        # nunca "esquece" os dados do lead no meio da conversa, e enxerga
        # também o que ele mesmo já preencheu (convênio, médico, unidade...).
        caller_context = None
        if self.kommo is not None and reply_to_number:
            try:
                caller_context = self.kommo.get_caller_context(reply_to_number)
                if caller_context and caller_context.get("found"):
                    log.info(
                        "Onboarding: contato conhecido (lead %s, campos=%s)",
                        caller_context.get("lead_id"),
                        list((caller_context.get("known") or {}).keys()),
                    )
            except Exception as e:  # noqa: BLE001
                log.warning("Onboarding lookup falhou: %s", e)
                caller_context = None

        # REMOVIDO Bug C-49 (05/08/2026 — Bug C-90 P0).
        # C-49 auto-resetava ATIVADO IA=Desativado → Ativado a cada mensagem,
        # tornando impossível desativar a IA manualmente. O webhook
        # /admin/kommo-trigger-status-change já cuida de reativar quando o lead
        # muda de etapa legitimamente. Desativação manual DEVE ser respeitada.

        # Bug C-102 (11/08/2026) — Layer 2: Derivação determinística de ctx.known.
        # Transforma dados Kommo em fatos derivados (data_nasc→idade→medico,
        # motivo→medico, normalização) ANTES de qualquer LLM ou Medware lookup.
        # Roda APÓS get_caller_context() e ANTES de injetar_pre_slots() (C-81).
        # Idempotente e fail-safe: exceção aqui NÃO bloqueia o pipeline.
        if caller_context:
            try:
                from voice_agent.enriquecimento_ctx import enriquecer_known as _enriquecer_c102  # noqa: PLC0415
                _enriquecer_c102(caller_context)
            except Exception as _e_c102:  # noqa: BLE001
                log.warning("[C-102] enriquecer_known falhou: %s", _e_c102)

        # 2c) Convivência humano × agente: fica em silêncio se o lead está
        # em cirurgias ou se um humano assumiu o chat há pouco (handoff).
        if self.kommo is not None and caller_context:
            try:
                motivo = self.kommo.agent_paused_for_lead(
                    caller_context, self.settings.agent_handoff_window_min,
                )
            except Exception as e:  # noqa: BLE001
                log.warning("Verificação de pausa falhou: %s", e)
                motivo = None
            if motivo:
                log.info("Agente em silêncio (%s) para %s", motivo, reply_to_number)
                # Handoff humano detectado → carimba a IA como DESATIVADA
                # E move pra etapa 1-ATENDIMENTO HUMANO (106563343) pra
                # equipe enxergar pelo card a fila de leads a finalizar.
                # Quando humano mover pra outra etapa ativa, webhook
                # /admin/kommo-trigger-status-change reativa IA automático.
                # (task #233 — sugestão Fábio 05/06/2026)
                lid = caller_context.get("lead_id")
                if lid:
                    try:
                        self.kommo.update_lead_fields(
                            lid, {"ativado_ia": "DESATIVADO"}
                        )
                    except Exception as e:  # noqa: BLE001
                        log.warning("Carimbo ATIVADO IA? (off) falhou: %s", e)
                    # Move pra 1-ATENDIMENTO HUMANO (apenas se não estiver lá
                    # ou em etapa final). Status 106563343 = 1-ATENDIMENTO HUMANO.
                    try:
                        status_atual = caller_context.get("status_id")
                        # Etapas finais não devem ser mexidas
                        _ETAPAS_FINAIS_HANDOFF = {142, 143, 91486864}
                        if (
                            status_atual
                            and status_atual != 106563343
                            and status_atual not in _ETAPAS_FINAIS_HANDOFF
                        ):
                            self.kommo.update_lead_status(lid, 106563343)
                            log.info(
                                "[HANDOFF] lead %s movido pra 1-ATENDIMENTO "
                                "HUMANO (origem etapa %s)",
                                lid, status_atual,
                            )
                    except Exception as e:  # noqa: BLE001
                        log.warning(
                            "[HANDOFF] mover pra ATENDIMENTO HUMANO falhou "
                            "lead=%s: %s", lid, e,
                        )
                return PipelineResult(
                    transcript=user_text, answer="", sent=False,
                    model_used="", articles_used=[],
                )

        # 2c-bis) Bug C-68 (22/07/2026, lead 21513059 Natacha/Eduardo).
        # Paciente em 5-AGENDADO/6-CONFIRMAR/7.CONFIRMADO pediu REMARCAR ou
        # CANCELAR → Lia ofereceu novos slots em vez de escalar pra humano.
        # Causa raiz: filtro C-47 apenas substituía o TEXTO; não movia o lead
        # nem desativava a IA. Agora detectamos cedo no pipeline (antes do
        # Medware e do LLM) e executamos as 3 ações obrigatórias:
        #   (1) Enviar mensagem canônica de handoff
        #   (2) Mover lead → 1-ATENDIMENTO HUMANO (106563343)
        #   (3) Desativar IA (ATIVADO IA = Desativado)
        _STATUS_POS_AGENDADO = {101507507, 101109455, 106653499}
        if (
            self.kommo is not None
            and caller_context
            and caller_context.get("status_id") in _STATUS_POS_AGENDADO
        ):
            _user_text_baixo = user_text.lower().strip()
            _TERMOS_REMARCAR_AGENDADO = (
                "remarcar", "remarcação", "remarcacao", "reagendar",
                "cancelar", "cancela", "cancelamento", "desmarcar",
                "mudar horário", "mudar horario", "trocar horário",
                "trocar horario", "trocar o horário", "trocar o horario",
                "mudar data", "trocar data", "trocar dia", "trocar o dia",
                "mudar o dia", "mudar o horário", "mudar o horario",
                "não vou conseguir", "nao vou conseguir",
                "não consigo mais", "nao consigo mais",
                "queria mudar", "quero mudar",
            )
            _pediu_remarcar_pos = any(
                t in _user_text_baixo for t in _TERMOS_REMARCAR_AGENDADO
            )
            if _pediu_remarcar_pos:
                _lid_pos = caller_context.get("lead_id")
                _known_pos = caller_context.get("known") or {}
                _nome_pos = (
                    (_known_pos.get("nome_contato") or "").split()[0]
                    if _known_pos.get("nome_contato")
                    else ""
                )
                _msg_handoff = (
                    f"{_nome_pos + ', p' if _nome_pos else 'P'}"
                    "asso seu atendimento para nossa equipe agora mesmo — "
                    "eles vão cuidar da remarcação com você. Um instante! 🙏"
                )
                log.error(
                    "[BUG C-68] REMARCAÇÃO em lead PÓS-AGENDADO. "
                    "lead=%s status=%s user=%r — forçando handoff.",
                    _lid_pos, caller_context.get("status_id"), user_text[:100],
                )
                # Envia mensagem canônica antes de retornar
                if reply_to_number:
                    try:
                        self.evolution.send_text(
                            number=reply_to_number,
                            text=_msg_handoff,
                            quoted_message_id=quoted_message_id,
                        )
                    except Exception as _e_ev:  # noqa: BLE001
                        log.warning("[C-68] envio evolution falhou: %s", _e_ev)
                if _lid_pos:
                    # (3) Desativar IA
                    try:
                        self.kommo.update_lead_fields(
                            _lid_pos, {"ativado_ia": "DESATIVADO"}
                        )
                    except Exception as _e_ia:  # noqa: BLE001
                        log.warning("[C-68] desativar IA falhou: %s", _e_ia)
                    # (2) Mover pra 1-ATENDIMENTO HUMANO
                    _status_atual_pos = caller_context.get("status_id")
                    _ETAPAS_FINAIS_C68 = {142, 143, 91486864, 106563343}
                    if (
                        _status_atual_pos
                        and _status_atual_pos not in _ETAPAS_FINAIS_C68
                    ):
                        try:
                            self.kommo.update_lead_status(_lid_pos, 106563343)
                            log.info(
                                "[C-68] lead %s movido → 1-ATENDIMENTO HUMANO",
                                _lid_pos,
                            )
                        except Exception as _e_st:  # noqa: BLE001
                            log.warning(
                                "[C-68] mover status falhou lead=%s: %s",
                                _lid_pos, _e_st,
                            )
                    # Nota Kommo registrando o handoff
                    try:
                        _nota_c68 = (
                            f"🔀 [LIA C-68 {__import__('datetime').datetime.now().strftime('%H:%M %d/%m')}] "
                            f"Paciente pediu remarcação/cancelamento em lead pós-agendado. "
                            f"IA desativada + lead movido para ATENDIMENTO HUMANO. "
                            f"Mensagem do paciente: \"{user_text[:200]}\""
                        )
                        self.kommo.add_note(_lid_pos, _nota_c68)
                    except Exception:  # noqa: BLE001
                        pass
                return PipelineResult(
                    transcript=user_text,
                    answer=_msg_handoff,
                    sent=bool(reply_to_number),
                    model_used="c68-handoff",
                    articles_used=[],
                )

        # === AGENDA SUSPENSA (kill-switch operacional — Fábio 22/07/2026) ===
        # Enquanto AGENDA_SUSPENSA=1, a Lia NÃO apresenta disponibilidade de
        # horários (estava com muitos erros). Quando o paciente chega no
        # momento de agendar (qualificado: unidade+convênio, OU pediu horários,
        # OU lead em 3-AGENDAR), faz handoff pra equipe humana confirmar o
        # horário — mesmo mecanismo do C-68. Reversível: basta remover o env.
        if (
            _agenda_suspensa_ativa()
            and self.kommo is not None
            and caller_context
        ):
            _known_ags = caller_context.get("known") or {}
            _status_ags = caller_context.get("status_id")
            _pediu_horarios = _texto_pede_agendamento(user_text)
            _qualificado = bool(_known_ags.get("unidade")) and bool(_known_ags.get("convenio"))
            _em_agendar = _status_ags == 102560495
            _ETAPAS_FINAIS_AGS = {142, 143, 91486864, 106563343}
            if (
                (_pediu_horarios or _qualificado or _em_agendar)
                and _status_ags not in _ETAPAS_FINAIS_AGS
            ):
                _lid_ags = caller_context.get("lead_id")
                _nome_ags = (
                    (_known_ags.get("nome_contato") or "").split()[0]
                    if _known_ags.get("nome_contato") else ""
                )
                _msg_ags = (
                    f"{_nome_ags + ', p' if _nome_ags else 'P'}"
                    "ara garantir o melhor horário pra você, vou passar seu "
                    "atendimento agora para nossa equipe — eles confirmam a "
                    "disponibilidade e finalizam o seu agendamento. Um instante! 🙏"
                )
                log.warning(
                    "[AGENDA_SUSPENSA] handoff agendamento. lead=%s status=%s user=%r",
                    _lid_ags, _status_ags, (user_text or "")[:100],
                )
                if reply_to_number:
                    try:
                        self.evolution.send_text(
                            number=reply_to_number,
                            text=_msg_ags,
                            quoted_message_id=quoted_message_id,
                        )
                    except Exception as _e_ev_ags:  # noqa: BLE001
                        log.warning("[AGENDA_SUSPENSA] envio evolution falhou: %s", _e_ev_ags)
                if _lid_ags:
                    try:
                        self.kommo.update_lead_fields(_lid_ags, {"ativado_ia": "DESATIVADO"})
                    except Exception as _e_ia_ags:  # noqa: BLE001
                        log.warning("[AGENDA_SUSPENSA] desativar IA falhou: %s", _e_ia_ags)
                    try:
                        self.kommo.update_lead_status(_lid_ags, 106563343)
                    except Exception as _e_st_ags:  # noqa: BLE001
                        log.warning("[AGENDA_SUSPENSA] mover status falhou lead=%s: %s", _lid_ags, _e_st_ags)
                    try:
                        _nota_ags = (
                            f"⏸️ [LIA AGENDA_SUSPENSA {__import__('datetime').datetime.now().strftime('%H:%M %d/%m')}] "
                            f"Apresentação de agenda suspensa. Lead encaminhado para ATENDIMENTO HUMANO "
                            f"confirmar o horário. Mensagem do paciente: \"{(user_text or '')[:200]}\""
                        )
                        self.kommo.add_note(_lid_ags, _nota_ags)
                    except Exception:  # noqa: BLE001
                        pass
                return PipelineResult(
                    transcript=user_text,
                    answer=_msg_ags,
                    sent=bool(reply_to_number),
                    model_used="agenda-suspensa-handoff",
                    articles_used=[],
                )

        # === BUG C-81 — Classificador de intenção pré-LLM (02/08/2026) ===
        # Caso Isabella (lead 22335902): "olhos inchados e remelando" →
        # Lia fez triagem normal de convênio em vez de oferecer encaixe urgente.
        # Causa raiz: pipeline monolítico não distinguia urgência antes do LLM.
        # Fix: classificação determinística por regex ANTES do Medware lookup.
        # Benefícios:
        #   1. Urgência: oferta de encaixe + alerta humano sem esperar LLM
        #   2. Pré-extração: unidade/n_patients/day_pref/turno injetados em
        #      ctx.known → Medware já recebe parâmetros corretos → menos perguntas
        #   3. Zero custo de API (apenas regex, sem Haiku/Sonnet)
        # Toggle: INTENT_CLASSIFIER_ENABLED=0 desliga (default ON).
        _intent_result = None
        import os as _os_c81  # noqa: PLC0415
        if (
            _os_c81.environ.get("INTENT_CLASSIFIER_ENABLED", "1") not in ("0", "false", "no", "off")
            and caller_context
            and user_text
        ):
            try:
                from voice_agent.intent_classifier import (
                    classify_intent as _classify_intent,
                    gerar_msg_urgencia as _gerar_msg_urgencia,
                    injetar_pre_slots as _injetar_pre_slots,
                )
                _intent_result = _classify_intent(
                    user_text,
                    caller_context=caller_context,
                )
                # Injeta pré-slots em ctx.known ANTES do Medware lookup
                _injetar_pre_slots(caller_context, _intent_result)

                # Urgência CRÍTICA → resposta canônica + escalar + sem LLM
                if _intent_result.escalate_human:
                    _lid_c81 = caller_context.get("lead_id")
                    _known_c81 = caller_context.get("known") or {}
                    _nome_c81 = (
                        (_known_c81.get("nome_contato") or "").split()[0]
                        if _known_c81.get("nome_contato") else ""
                    )
                    _msg_c81 = _gerar_msg_urgencia(_intent_result, _nome_c81)
                    log.error(
                        "[C-81 CRITICAL] urgência crítica detectada. lead=%s user=%r",
                        _lid_c81, user_text[:100],
                    )
                    if reply_to_number and _msg_c81:
                        try:
                            self.evolution.send_text(
                                number=reply_to_number,
                                text=_msg_c81,
                                quoted_message_id=quoted_message_id,
                            )
                        except Exception as _e_c81:  # noqa: BLE001
                            log.warning("[C-81] envio evolution falhou: %s", _e_c81)
                    if _lid_c81:
                        try:
                            _nota_c81 = (
                                f"🚨 [LIA C-81 CRÍTICO {__import__('datetime').datetime.now().strftime('%H:%M %d/%m')}] "
                                f"Emergência ocular detectada. Lead encaminhado URGENTE. "
                                f"Razão: {_intent_result.reasoning[:200]}. "
                                f"Mensagem: \"{user_text[:200]}\""
                            )
                            self.kommo.add_note(_lid_c81, _nota_c81)
                        except Exception:  # noqa: BLE001
                            pass
                        try:
                            self.kommo.update_lead_status(_lid_c81, 106563343)
                        except Exception:  # noqa: BLE001
                            pass
                    return PipelineResult(
                        transcript=user_text,
                        answer=_msg_c81,
                        sent=bool(reply_to_number and _msg_c81),
                        model_used="c81-critical-urgency",
                        articles_used=[],
                    )

                # Urgência PRIORITÁRIA → flag em ctx para responder adaptar o prompt
                # (não retorna ainda — deixa LLM ofertar encaixe com contexto certo)
                # Task #436: alerta humano paralelo via nota Kommo (C-85)
                if _intent_result.urgency_level == "priority":
                    _lid_c81_pr = caller_context.get("lead_id")
                    log.warning(
                        "[C-81 PRIORITY] urgência prioritária. lead=%s reason=%r",
                        _lid_c81_pr, _intent_result.reasoning,
                    )
                    # Alerta visível na timeline Kommo — equipe pode intervir se Lia travar
                    if _lid_c81_pr and self.kommo is not None:
                        try:
                            import datetime as _dt_pr
                            _nota_pr = (
                                f"🟡 [LIA C-81 PRIORITY {_dt_pr.datetime.now().strftime('%H:%M %d/%m')}] "
                                f"Urgência oftálmica detectada — Lia está tentando encaixe imediato. "
                                f"Verificar se precisa intervenção humana. "
                                f"Razão: {str(_intent_result.reasoning)[:200]}. "
                                f"Msg: \"{user_text[:150]}\""
                            )
                            self.kommo.add_note(_lid_c81_pr, _nota_pr)
                            log.info("[C-81 PRIORITY] nota Kommo gravada. lead=%s", _lid_c81_pr)
                        except Exception as _e_pr:  # noqa: BLE001
                            log.warning("[C-81 PRIORITY] falha ao gravar nota: %s", _e_pr)

            except Exception as _e_c81_outer:  # noqa: BLE001
                log.warning("[C-81] classificador falhou (fail-open): %s", _e_c81_outer)

        # -------------------------------------------------------------------
        # Bug C-94 (05/08/2026) — Auto-inferência de especialidade + médico
        # Roda APÓS injetar_pre_slots (C-81) e ANTES do Medware lookup para
        # que medico_param já esteja preenchido corretamente em known.
        # -------------------------------------------------------------------
        try:
            from voice_agent.intent_classifier import (
                calcular_idade_anos as _calc_idade_c94,
                inferir_especialidade as _inf_esp_c94,
                inferir_medico as _inf_med_c94,
            )
            _known_c94 = caller_context.get("known", {}) if caller_context else {}
            _age_c94 = _calc_idade_c94(
                _known_c94.get("data_nascimento") or _known_c94.get("data_nasc")
            )
            _motivo_c94 = _known_c94.get("motivo") or _known_c94.get("reason") or ""

            # Inferir médico se não definido
            if not _known_c94.get("medico"):
                _esp_para_medico = _known_c94.get("especialidade")
                _med_c94 = _inf_med_c94(_age_c94, _motivo_c94, _esp_para_medico)
                if _med_c94:
                    _known_c94["medico"] = _med_c94
                    log.info(
                        "[C-94] medico inferido: %s (idade=%s motivo=%r)",
                        _med_c94, _age_c94, _motivo_c94[:40],
                    )

            # Inferir especialidade se não definida
            if not _known_c94.get("especialidade"):
                _esp_c94 = _inf_esp_c94(_age_c94, _motivo_c94, _known_c94.get("medico"))
                if _esp_c94:
                    _known_c94["especialidade"] = _esp_c94
                    log.info("[C-94] especialidade inferida: %s", _esp_c94)
                    # Atualizar Kommo (async, fail-open)
                    _lid_c94 = caller_context.get("lead_id") if caller_context else None
                    if _lid_c94 and self.kommo is not None:
                        try:
                            self.kommo.update_lead_fields(_lid_c94, {"especialidade": _esp_c94})
                        except Exception as _e_c94_kommo:  # noqa: BLE001
                            log.warning("[C-94] falha ao atualizar especialidade no Kommo: %s", _e_c94_kommo)

            # Preencher motivo da consulta no Kommo se disponível
            _lid_c94_mot = caller_context.get("lead_id") if caller_context else None
            if _motivo_c94 and not _known_c94.get("motivo_gravado_kommo") and _lid_c94_mot and self.kommo is not None:
                try:
                    self.kommo.update_lead_fields(_lid_c94_mot, {"reason": _motivo_c94})
                    _known_c94["motivo_gravado_kommo"] = True
                except Exception:  # noqa: BLE001
                    pass  # fail-open

            if caller_context:
                caller_context["known"] = _known_c94
        except Exception as _exc_c94:  # noqa: BLE001
            log.warning("[C-94] inferência falhou (fail-open): %s", _exc_c94)
        # -------------------------------------------------------------------

        # 2d) Agenda Medware: busca horários reais para o agente OFERECER.
        # ANTES: só consultava se caller_context.known.medico estava
        # preenchido. Resultado: lead novo (paciente recém-chegado, médico
        # ainda não definido no Kommo) → caller_context.agenda vazia →
        # Lia INVENTAVA slots no KB E7. Origem: lead 24038029 (29/05/2026).
        # AGORA: se ctx.medico vazio, default = Dra. Karla Delalibera
        # (médica principal Blink — oftalmologia geral) para já injetar
        # agenda real e a Lia poder oferecer slots concretos com cod_agenda.
        if self.medware is not None and caller_context:
            try:
                import json as _json
                import os
                import time as _time
                known = caller_context.get("known") or {}
                medico_param = known.get("medico") or "Dra. Karla Delalibera"
                unidade_param = known.get("unidade")  # pode ser None
                # Bug C-30 (Sofia 24158652): transformar a preferência textual
                # do paciente (campo DIA/TURNO/PERÍODO → known["dia_turno"]) num
                # request ESPECÍFICO ao Medware. Ex.: "entre 7 e 15 de julho"
                # → consulta SÓ essa janela em vez do default fixo de 90 dias.
                # Toggle de rollback: MEDWARE_JANELA_PREFERENCIA=0 desliga.
                _janela = None
                _janela_fonte = "default_10d"
                if os.getenv("MEDWARE_JANELA_PREFERENCIA", "1") != "0":
                    try:
                        from voice_agent.janela_preferencia import (
                            parse_janela_preferencia,
                        )
                        # Bug C-65 (26/07/2026 — lead 21397921 Renata/Augusto):
                        # O parser só lia known["dia_turno"] (campo Kommo,
                        # gravado no turno ANTERIOR). Quando paciente diz
                        # "outubro" na mensagem ATUAL, dia_turno ainda estava
                        # vazio → fallback hoje+10d → slots de julho ofertados
                        # 3x em loop ignorando completamente o mês pedido.
                        # Fix: combinar dia_turno + user_text para capturar
                        # preferência do turno atual imediatamente.
                        _pref_texto = " ".join(filter(None, [
                            known.get("dia_turno") or "",
                            user_text or "",
                        ]))
                        _janela = parse_janela_preferencia(_pref_texto)
                    except Exception:  # noqa: BLE001
                        _janela = None

                # Bug C-71 (26/07/2026 — lead 22557778 Adriana):
                # ctx.unidade pode estar defasado de sessão anterior (ex:
                # paciente escolheu Águas Claras meses atrás, mas agora pede
                # "03/08" = segunda = Karla Asa Norte). Se a janela é um único
                # dia cujo dia-da-semana implica unidade diferente, atualizar
                # unidade_param + known["unidade"] ANTES de bater o Medware.
                # Assim C-31b não vê conflito e o LLM recebe slots corretos.
                if _janela and _janela[0] == _janela[1]:
                    try:
                        from voice_agent.responder import (
                            _inferir_unidade_por_dia as _iupd,
                        )
                        _weekday_pedido = _janela[0].weekday()
                        _unidade_c71 = _iupd(medico_param, _weekday_pedido)
                        _unidade_atual = (unidade_param or "").lower()
                        if (
                            _unidade_c71 and
                            _unidade_c71.lower() != _unidade_atual
                        ):
                            import logging as _log_c71
                            _log_c71.getLogger(__name__).info(
                                "[C-71] unidade corrigida %r→%r pela data pedida "
                                "%s (weekday=%d medico=%r)",
                                unidade_param, _unidade_c71,
                                _janela[0].strftime("%d/%m/%Y"),
                                _weekday_pedido, medico_param,
                            )
                            unidade_param = _unidade_c71
                            known["unidade"] = _unidade_c71
                    except Exception:  # noqa: BLE001
                        pass  # não quebra o fluxo principal

                # Bug C-73 (26/07/2026): quando paciente pede 1 data específica,
                # usar SQL canônico (WITH RECURSIVE + CONTAINING) que é mais
                # preciso que o REST de agendamentos. Requisito mínimo pra mostrar
                # agenda: médico + unidade + 1 data. Nome/data_nasc/convênio são
                # coletados DEPOIS que paciente escolher o slot.
                slots = None
                if _janela and _janela[0] == _janela[1]:
                    try:
                        from voice_agent.medware_sql import (
                            horarios_livres_dia as _hld,
                        )
                        _DIAS_BR_C73 = [
                            "Segunda-feira", "Terça-feira", "Quarta-feira",
                            "Quinta-feira", "Sexta-feira", "Sábado", "Domingo",
                        ]
                        _d_sql = _janela[0]
                        _horarios_sql = _hld(
                            medico_param or "",
                            unidade_param or "",
                            _d_sql.isoformat(),
                        )
                        if _horarios_sql:
                            _ds_c73 = _DIAS_BR_C73[_d_sql.weekday()]
                            _dbr_c73 = _d_sql.strftime("%d/%m/%Y")
                            slots = [
                                {"dia_semana": _ds_c73, "data_br": _dbr_c73, "hora": h}
                                for h in _horarios_sql
                            ]
                            _janela_fonte = "sql_single_date"
                            log.info(
                                "[C-73] SQL single-date: %d slots medico=%r unidade=%r data=%s",
                                len(slots), medico_param, unidade_param,
                                _d_sql.isoformat(),
                            )
                    except Exception as _e_sql:  # noqa: BLE001
                        log.warning(
                            "[C-73] SQL single-date falhou, fallback REST: %s", _e_sql
                        )
                        slots = None  # força fallback REST abaixo

                if _janela and slots is None:
                    slots = self.medware.horarios_para_agente(
                        medico_param, unidade_param,
                        data_inicio=_janela[0], data_fim=_janela[1],
                    )
                    _janela_fonte = "preferencia"
                    # Bug C-65b: quando a janela é um único dia (ex: paciente
                    # pede "09/10/2026 às 16:00") e não há slot nesse dia
                    # exato, expandir para o mês INTEIRO antes de cair no
                    # default hoje+10d. Evita oferecer slots de julho quando
                    # paciente quer outubro.
                    if not slots:
                        import calendar as _cal
                        _d = _janela[0]
                        _ultimo = _cal.monthrange(_d.year, _d.month)[1]
                        from datetime import date as _date_cls
                        _di_mes = _date_cls(_d.year, _d.month, 1)
                        _df_mes = _date_cls(_d.year, _d.month, _ultimo)
                        # Só tenta expansão se a janela original não era já
                        # o mês inteiro (evita chamada dupla redundante).
                        if _di_mes != _janela[0] or _df_mes != _janela[1]:
                            slots = self.medware.horarios_para_agente(
                                medico_param, unidade_param,
                                data_inicio=_di_mes, data_fim=_df_mes,
                            )
                            _janela_fonte = "fallback_mes_inteiro"
                    if not slots:
                        slots = self.medware.horarios_para_agente(
                            medico_param, unidade_param,
                        )
                        _janela_fonte = "fallback_default_apos_pref_vazia"
                elif slots is None:
                    slots = self.medware.horarios_para_agente(
                        medico_param, unidade_param,
                    )
                # Persiste o req/resp do Medware em Redis pra auditoria
                # (blink:medware_req:{lead_id}, TTL 30d). Resolve a lacuna do
                # tracing, que só guardava agenda_disponivel=bool.
                try:
                    _redis = getattr(self, "_redis", None)
                    _lead = caller_context.get("lead_id")
                    if _redis is not None and _lead:
                        _audit = dict(
                            getattr(self.medware, "ultimo_req_horarios", {}) or {}
                        )
                        _audit["pref_texto"] = known.get("dia_turno") or ""
                        _audit["janela_fonte"] = _janela_fonte
                        _audit["ts_epoch"] = int(_time.time())
                        _key = f"blink:medware_req:{_lead}"
                        _redis.lpush(_key, _json.dumps(_audit, ensure_ascii=False))
                        _redis.ltrim(_key, 0, 49)
                        _redis.expire(_key, 30 * 24 * 3600)
                except Exception:  # noqa: BLE001
                    pass
                if slots:
                    caller_context["agenda"] = slots
                    caller_context["agenda_medico_inferido"] = (
                        "default_karla" if not known.get("medico") else "ctx"
                    )
                    log.info(
                        "Medware: %d horários para %s (fonte_medico=%s "
                        "janela=%s)",
                        len(slots), medico_param,
                        "ctx" if known.get("medico") else "default_karla",
                        _janela_fonte,
                    )
                    # Sucesso: zera contador do circuit breaker
                    try:
                        _redis = getattr(self, "_redis", None)
                        if _redis is not None:
                            _redis.delete(
                                f"blink:agenda_vazia_seq:{conversation_key}"
                            )
                    except Exception:  # noqa: BLE001
                        pass
                else:
                    # Lead em status AGENDAR/REAGENDAR com agenda vazia é
                    # SINTOMA: Medware silenciou, JWT vencido, ou médico/unidade
                    # erradamente mapeados. Origem: lead 24053159 Juliene
                    # (31/05/2026) — Lia acabou inventando "vou registrar pra
                    # equipe finalizar". ERROR pra Easypanel/Slack pegar.
                    _status_id = (caller_context.get("status_id")
                                  if isinstance(caller_context, dict) else None)
                    _STATUS_AGENDAR_REAGENDAR = {
                        102560495,  # 3-AGENDAR
                        106184631,  # 4.REAGENDAR
                    }
                    if _status_id in _STATUS_AGENDAR_REAGENDAR:
                        log.error(
                            "[AGENDA VAZIA EM AGENDAR] lead=%s status=%s "
                            "medico=%r unidade=%r → Lia vai cair no fallback "
                            "AGENDA INDISPONÍVEL. Investigar Medware/cache.",
                            caller_context.get("lead_id"), _status_id,
                            medico_param, unidade_param,
                        )
                        # Circuit breaker (task #141, origem bug Adelia)
                        # Conta falhas consecutivas POR conversa em Redis.
                        # Após 3 falhas → escalona pra humano.
                        try:
                            _redis = getattr(self, "_redis", None)
                            if _redis is not None:
                                _key = (
                                    f"blink:agenda_vazia_seq:"
                                    f"{conversation_key}"
                                )
                                seq = int(_redis.incr(_key))
                                _redis.expire(_key, 1800)  # 30 min de janela
                                caller_context["agenda_vazia_seq"] = seq
                                if seq >= 3:
                                    caller_context[
                                        "escalonar_humano_medware_off"
                                    ] = True
                                    log.error(
                                        "[CIRCUIT BREAKER MEDWARE] %d falhas "
                                        "seguidas conv=%s lead=%s — "
                                        "escalonar humano",
                                        seq, conversation_key,
                                        caller_context.get("lead_id"),
                                    )
                        except Exception as _e_cb:  # noqa: BLE001
                            log.warning(
                                "circuit breaker contador falhou: %s", _e_cb,
                            )
                    else:
                        log.info(
                            "Medware: 0 horários para %s/%s (status=%s)",
                            medico_param, unidade_param, _status_id,
                        )
            except Exception as e:  # noqa: BLE001
                # WARNING não basta — origem do bug Juliene foi silêncio
                # silencioso. Subir pra ERROR.
                log.error("Medware horários falhou: %s", e)

        # 2d-bis-2) Pré-popular 1.MOTIVO + 1.EXAMES em conversas vivas
        # (task #140, origem bug Adelia 24056883 — 01/06/2026).
        # Antes selecionar_agrupador só era chamado em agendamento.salvar,
        # então leads "em conversa" (sem agendamento gravado) ficavam com
        # 1.EXAMES vazio. Agora calculamos cedo: assim que perfil + motivo
        # estão no caller_context. Grava no Kommo via thread separada
        # (best-effort, não bloqueia resposta da Lia).
        if caller_context and caller_context.get("lead_id"):
            try:
                _known = caller_context.get("known") or {}
                _perfil = _known.get("perfil") or ""
                _motivo = _known.get("motivo") or ""
                _nasc_iso = _known.get("data_nasc_iso") or None
                if _perfil and _motivo:
                    from voice_agent.procedimentos import (
                        agrupador_label_kommo,
                        classificar_motivo_tipo_kommo,
                        selecionar_agrupador,
                    )
                    _nome_agr, _ = selecionar_agrupador(
                        perfil_kommo=_perfil,
                        birth_date_iso=_nasc_iso,
                        motivo=_motivo,
                    )
                    _agrupa_label = agrupador_label_kommo(_nome_agr)
                    _motivo_tipo = classificar_motivo_tipo_kommo(_motivo)
                    # Disponibiliza pro caller_context (pra responder usar)
                    caller_context["agrupador_calculado"] = _agrupa_label
                    caller_context["motivo_tipo_calculado"] = _motivo_tipo
                    # Grava no Kommo em background pra não bloquear
                    if self.kommo is not None:
                        _lead_id = caller_context["lead_id"]
                        _campos = {
                            "motivo_tipo_paciente_1": _motivo_tipo,
                            "agrupador_exames_paciente_1": _agrupa_label,
                        }
                        threading.Thread(
                            target=self._gravar_agrupador_silencioso,
                            args=(_lead_id, _campos),
                            daemon=True,
                        ).start()
                        log.info(
                            "[AGRUPADOR EARLY] lead=%s motivo_tipo=%s "
                            "agrupador=%s",
                            _lead_id, _motivo_tipo, _agrupa_label,
                        )
            except Exception as e:  # noqa: BLE001
                log.warning("[AGRUPADOR EARLY] falhou: %s", e)

        # 2d-bis) Checklist dados mínimos pra gravar Medware (task #123 / 31-05-2026)
        # Origem: lead Juliene 24053159 — Lia ofereceu slot sem ter nome
        # completo do Daniel nem CPF. Sem checklist, ela "sente" que não
        # dá pra fechar e improvisa frase humana. Aqui validamos os 4
        # dados mínimos (nome, data nasc, CPF, convenio) E:
        # - se TODOS OK → ctx["checklist_ok"]=True, agenda fica livre pra ser oferecida
        # - se falta algum → ctx["dados_pendentes"]=lista → responder injeta bloco
        #   PRÉ-AGENDA proibindo oferta e listando campos a coletar
        if caller_context:
            try:
                from voice_agent.checklist_dados_minimos import (
                    verificar_dados_minimos,
                )
                _check = verificar_dados_minimos(
                    caller_context.get("known") or {}
                )
                caller_context["checklist_dados_minimos"] = {
                    "pronto_para_oferecer_slot": _check.pronto_para_oferecer_slot,
                    "campos_pendentes": list(_check.campos_pendentes),
                    "nome_completo_ok": _check.nome_completo_ok,
                    "data_nascimento_ok": _check.data_nascimento_ok,
                    "cpf_ok": _check.cpf_ok,
                    "convenio_definido_ok": _check.convenio_definido_ok,
                }
                if not _check.pronto_para_oferecer_slot:
                    log.info(
                        "[CHECKLIST] lead=%s pendentes=%s — slot NAO sera oferecido",
                        caller_context.get("lead_id"),
                        _check.campos_pendentes,
                    )
            except Exception as e:  # noqa: BLE001
                log.warning("[CHECKLIST] falhou: %s", e)

        # 2d-ter) FSM da conversa (task #125, otimizador #2 / 31-05-2026)
        # Lê snapshot do Redis e ENRIQUECE caller_context com:
        # - fsm.estado (TRIAGEM/DADOS/.../POS_GRAVACAO)
        # - fsm.tentativas_no_estado (>3 indica loop preso)
        # Se snapshot vazio, infere a partir do caller_context (status_id,
        # ja_agendado, checklist). Persiste no Redis pra próximo turno.
        try:
            from voice_agent.fsm_conversa import (
                EstadoConversa,
                FSMManager,
                inferir_estado_inicial,
            )
            _redis = getattr(self, "_redis", None)
            _fsm_mgr = FSMManager(_redis)
            _snap = _fsm_mgr.get(conversation_key)
            if _snap is None and caller_context:
                _estado_inferido = inferir_estado_inicial(caller_context)
                _snap, _ok = _fsm_mgr.transicionar(
                    conversation_key, _estado_inferido,
                    motivo="boot pelo caller_context",
                )
            if _snap and caller_context is not None:
                caller_context["fsm"] = {
                    "estado": _snap.estado.value,
                    "tentativas_no_estado": _snap.tentativas_no_estado,
                    "motivo_ultima_transicao": _snap.motivo_ultima_transicao,
                }
                # Métricas live (task #260): conta ENTRADA no estado pra calcular
                # taxa de "AGENDA→oferecer_slot OK" e tendência por dia.
                try:
                    from . import metricas_funcionamento as _mf
                    _mf.incrementar(
                        _redis, f"fsm:{_snap.estado.value}:enter",
                    )
                except Exception:  # noqa: BLE001
                    pass
                # C-98 (08/08/2026): Auto-advance FSM pra AGENDA quando checklist
                # completo + agenda disponível mas FSM ainda em TRIAGEM/DADOS/CONVENIO.
                # Origem: paciente envia "asa norte" como última peça (C-81 injeta
                # unidade em known), checklist vira pronto=True, Medware retorna slots,
                # MAS a FSM Redis ainda guarda snapshot do turno anterior (ex: CONVENIO).
                # deve_ofertar_agora() exige fsm.estado==AGENDA → retorna False →
                # LLM é chamado → gera stall "Vou verificar..." em vez de oferta real.
                # Fix: detectar essa condição e disparar transição CONVENIO→AGENDA
                # (transição já era válida em _TRANSICOES_VALIDAS; faltava o trigger).
                _fsm_estado_c98 = (
                    caller_context.get("fsm") or {}
                ).get("estado", "")
                _chk_c98 = caller_context.get("checklist_dados_minimos") or {}
                if (
                    _fsm_estado_c98 in {"TRIAGEM", "DADOS", "CONVENIO"}
                    and _chk_c98.get("pronto_para_oferecer_slot")
                    and caller_context.get("agenda")
                    and not caller_context.get("ja_agendado")
                ):
                    try:
                        _snap_c98, _ok_c98 = _fsm_mgr.transicionar(
                            conversation_key,
                            EstadoConversa.AGENDA,
                            motivo="C-98 auto-advance: checklist completo + agenda disponível",
                        )
                        if _ok_c98:
                            caller_context["fsm"] = {
                                "estado": _snap_c98.estado.value,
                                "tentativas_no_estado": _snap_c98.tentativas_no_estado,
                                "motivo_ultima_transicao": _snap_c98.motivo_ultima_transicao,
                            }
                            log.info(
                                "[C-98] FSM %s→AGENDA lead=%s — deve_ofertar_agora será True",
                                _fsm_estado_c98,
                                caller_context.get("lead_id"),
                            )
                    except Exception as _e_c98:  # noqa: BLE001
                        log.warning("[C-98] auto-advance falhou: %s", _e_c98)
        except Exception as e:  # noqa: BLE001
            log.warning("[FSM] inicialização falhou: %s", e)

        # 2e) Gap 5: status real da gravação Medware (se houver) — pra Lia
        # poder responder com VERDADE quando paciente perguntar "gravou?".
        # Origem: lead 24038029 — Lia mentiu sem saber.
        if caller_context and caller_context.get("lead_id"):
            try:
                _redis = getattr(self, "_redis", None)
                if _redis is not None:
                    import json as _json
                    _raw = _redis.get(f"blink:gravacao:lead:{int(caller_context['lead_id'])}")
                    if _raw:
                        _val = _raw.decode() if isinstance(_raw, bytes) else _raw
                        caller_context["gravacao_status"] = _json.loads(_val)
            except Exception as _e:  # noqa: BLE001
                log.debug("consulta status gravacao Redis ignorada: %s", _e)

        # 2f) Bug C-72 Etapa 2 (26/07/2026) — pré-carga do histórico completo
        # via Chats API Kommo. Quando caller_context.known.url_da_conversa está
        # preenchido (campo 1260160), extrai chat_id e carrega até 50 mensagens
        # sem janela de tempo. Injeta como caller_context["historico_chat_msgs"]
        # pra responder.py usar via montar_bloco_historico_chat().
        # Cobre paciente respondendo dias depois a campanha/template (o C-58
        # janela 6h não alcança esse cenário).
        if caller_context and self.kommo is not None:
            try:
                from voice_agent.historico_conversa import extrair_chat_id_da_url
                _url_conv = (caller_context.get("known") or {}).get("url_da_conversa") or ""
                _chat_id_etapa2: Optional[int] = None
                if _url_conv:
                    _chat_id_etapa2 = extrair_chat_id_da_url(_url_conv)
                # Fallback: URL sem /chats/ → descobre via API (1 chamada extra)
                if _chat_id_etapa2 is None and caller_context.get("lead_id"):
                    _chat_id_etapa2 = self.kommo.get_chat_id_for_lead(
                        caller_context["lead_id"]
                    )
                if _chat_id_etapa2:
                    # Bug C-76c (29/07/2026): limit=50 carregava 50 msgs completas
                    # em memória — responder.py ainda passava max_msgs=30 ao
                    # formatar (o call site que C-76b esqueceu de corrigir).
                    # Alinhado com o cap de 15 msgs do historico_conversa.py.
                    _msgs_etapa2 = self.kommo.get_chat_messages_raw(
                        _chat_id_etapa2, limit=15
                    )
                    if _msgs_etapa2:
                        caller_context["historico_chat_msgs"] = _msgs_etapa2
                        log.debug(
                            "[C-72-E2] lead=%s chat=%s msgs=%d",
                            caller_context.get("lead_id"),
                            _chat_id_etapa2,
                            len(_msgs_etapa2),
                        )
            except Exception as _e72:  # noqa: BLE001
                log.debug("[C-72-E2] falha ao carregar historico chat: %s", _e72)

        # 3) Resposta com Claude
        try:
            result = self.responder.reply(
                conversation_key, user_text, caller_context=caller_context
            )
            answer = result["answer"]
            model_used = result["model_used"]
            articles_used = result["articles_used"]
        except Exception as e:  # noqa: BLE001
            log.exception("Claude falhou")
            return PipelineResult(
                transcript=user_text, answer="", sent=False,
                model_used="", articles_used=[],
                error=f"claude: {e}",
            )

        # 3a-bis) Bug C-84b (04/08/2026 Juliana 24413852) — paciente pediu atendente.
        # Filtro C-84b em responder.py já substituiu o texto e gravou flag Redis.
        # Aqui: mover lead pra 1-ATENDIMENTO HUMANO + desativar IA.
        try:
            _redis_c84 = getattr(self, "_redis", None)
            _lid_c84_pipe = (
                caller_context.get("lead_id") if isinstance(caller_context, dict) else None
            )
            if _redis_c84 and _lid_c84_pipe:
                _flag_c84 = _redis_c84.get(f"blink:c84_pede_atendente:{_lid_c84_pipe}")
                if _flag_c84:
                    log.error(
                        "[C-84b PIPELINE] paciente pediu atendente lead=%s — "
                        "movendo pra ATENDIMENTO HUMANO + desativando IA",
                        _lid_c84_pipe,
                    )
                    # Limpa o flag imediatamente (evita re-trigger)
                    _redis_c84.delete(f"blink:c84_pede_atendente:{_lid_c84_pipe}")
                    if self.kommo is not None:
                        _status_c84 = (
                            caller_context.get("status_id")
                            if isinstance(caller_context, dict) else None
                        )
                        _ETAPAS_FINAIS_C84 = {142, 143, 91486864, 106563343}
                        # (1) Desativar IA
                        try:
                            self.kommo.update_lead_fields(
                                _lid_c84_pipe, {"ativado_ia": "DESATIVADO"}
                            )
                        except Exception as _e_c84_ia:  # noqa: BLE001
                            log.warning("[C-84b] desativar IA falhou: %s", _e_c84_ia)
                        # (2) Mover pra 1-ATENDIMENTO HUMANO
                        if _status_c84 and _status_c84 not in _ETAPAS_FINAIS_C84:
                            try:
                                self.kommo.update_lead_status(_lid_c84_pipe, 106563343)
                                log.info(
                                    "[C-84b] lead %s movido → 1-ATENDIMENTO HUMANO",
                                    _lid_c84_pipe,
                                )
                            except Exception as _e_c84_st:  # noqa: BLE001
                                log.warning(
                                    "[C-84b] mover status falhou lead=%s: %s",
                                    _lid_c84_pipe, _e_c84_st,
                                )
                        # (3) Nota Kommo
                        try:
                            import datetime as _dt_c84
                            _nota_c84 = (
                                f"🤝 [LIA C-84b {_dt_c84.datetime.now().strftime('%H:%M %d/%m')}] "
                                "Paciente pediu falar com atendente. IA desativada + "
                                f"lead movido pra ATENDIMENTO HUMANO. Msg: \"{user_text[:200]}\""
                            )
                            self.kommo.add_note(_lid_c84_pipe, _nota_c84)
                        except Exception:  # noqa: BLE001
                            pass
        except Exception as _e_c84_pipe:  # noqa: BLE001
            log.warning("[C-84b PIPELINE] check falhou (fail-open): %s", _e_c84_pipe)

        # 3a-C108) Bug C-108 (11/08/2026) — paciente desistiu explicitamente.
        # Bypass em blindagens_deterministicas.py já substituiu o texto e
        # enriquecimento_ctx step 14 gravou known["desistencia_explicita"]=True.
        # Aqui: desativar IA + mover pra 2.LEADS FRIO (não Closed-lost — pode voltar).
        try:
            _redis_c108 = getattr(self, "_redis", None)
            _lid_c108 = (
                caller_context.get("lead_id") if isinstance(caller_context, dict) else None
            )
            if _redis_c108 and _lid_c108:
                _flag_c108 = _redis_c108.get(f"blink:c108_desistencia:{_lid_c108}")
                if _flag_c108:
                    log.info(
                        "[C-108 PIPELINE] desistencia explicita lead=%s — "
                        "desativando IA + movendo pra 2.LEADS FRIO",
                        _lid_c108,
                    )
                    _redis_c108.delete(f"blink:c108_desistencia:{_lid_c108}")
                    if self.kommo is not None:
                        _status_c108 = (
                            caller_context.get("status_id")
                            if isinstance(caller_context, dict) else None
                        )
                        _ETAPAS_FINAIS_C108 = {142, 143, 91486864}
                        # (1) Desativar IA
                        try:
                            self.kommo.update_lead_fields(
                                _lid_c108, {"ativado_ia": "DESATIVADO"}
                            )
                        except Exception as _e_c108_ia:  # noqa: BLE001
                            log.warning("[C-108] desativar IA falhou: %s", _e_c108_ia)
                        # (2) Mover pra 2.LEADS FRIO (101508307) — não Closed-lost
                        if _status_c108 and _status_c108 not in _ETAPAS_FINAIS_C108:
                            try:
                                self.kommo.update_lead_status(_lid_c108, 101508307)
                                log.info(
                                    "[C-108] lead %s movido → 2.LEADS FRIO", _lid_c108
                                )
                            except Exception as _e_c108_st:  # noqa: BLE001
                                log.warning(
                                    "[C-108] mover status falhou lead=%s: %s",
                                    _lid_c108, _e_c108_st,
                                )
                        # (3) Nota Kommo
                        try:
                            import datetime as _dt_c108
                            _nota_c108 = (
                                f"🚪 [LIA C-108 {_dt_c108.datetime.now().strftime('%H:%M %d/%m')}] "
                                "Paciente desistiu explicitamente. IA desativada + "
                                f"lead movido pra 2.LEADS FRIO. Msg: \"{user_text[:200]}\""
                            )
                            self.kommo.add_note(_lid_c108, _nota_c108)
                        except Exception:  # noqa: BLE001
                            pass
        except Exception as _e_c108_pipe:  # noqa: BLE001
            log.warning("[C-108 PIPELINE] check falhou (fail-open): %s", _e_c108_pipe)

        # 3a-C109) Bug C-109 (11/08/2026) — NO-SHOW COUNT >= 3 → mover pra ATENDIMENTO HUMANO.
        # Bypass em blindagens_deterministicas.py já substituiu o texto e
        # sinal_noshow.py gravou flag blink:c109_move_humano:{lead_id} (TTL 24h).
        # Aqui: desativar IA + mover pra 1-ATENDIMENTO HUMANO + nota Kommo.
        try:
            _redis_c109 = getattr(self, "_redis", None)
            _lid_c109 = (
                caller_context.get("lead_id") if isinstance(caller_context, dict) else None
            )
            if _redis_c109 and _lid_c109:
                _flag_c109 = _redis_c109.get(f"blink:c109_move_humano:{_lid_c109}")
                if _flag_c109:
                    log.info(
                        "[C-109 PIPELINE] noshow>=3 lead=%s — "
                        "desativando IA + movendo pra 1-ATENDIMENTO HUMANO",
                        _lid_c109,
                    )
                    _redis_c109.delete(f"blink:c109_move_humano:{_lid_c109}")
                    if self.kommo is not None:
                        _status_c109 = (
                            caller_context.get("status_id")
                            if isinstance(caller_context, dict) else None
                        )
                        _ETAPAS_FINAIS_C109 = {142, 143, 91486864}
                        # (1) Desativar IA
                        try:
                            self.kommo.update_lead_fields(
                                _lid_c109, {"ativado_ia": "DESATIVADO"}
                            )
                        except Exception as _e_c109_ia:  # noqa: BLE001
                            log.warning("[C-109] desativar IA falhou: %s", _e_c109_ia)
                        # (2) Mover pra 1-ATENDIMENTO HUMANO (106563343)
                        if _status_c109 and _status_c109 not in _ETAPAS_FINAIS_C109:
                            try:
                                self.kommo.update_lead_status(_lid_c109, 106563343)
                                log.info(
                                    "[C-109] lead %s movido → 1-ATENDIMENTO HUMANO", _lid_c109
                                )
                            except Exception as _e_c109_st:  # noqa: BLE001
                                log.warning(
                                    "[C-109] mover status falhou lead=%s: %s",
                                    _lid_c109, _e_c109_st,
                                )
                        # (3) Nota Kommo
                        try:
                            import datetime as _dt_c109
                            _ns_count_c109 = (
                                (caller_context.get("known") or {}).get("noshow_count_val")
                                or "≥3"
                            )
                            _nota_c109 = (
                                f"⚠️ [LIA C-109 {_dt_c109.datetime.now().strftime('%H:%M %d/%m')}] "
                                f"Paciente com {_ns_count_c109} no-shows — sinal integral necessário. "
                                "IA desativada. Equipe humana deve negociar pagamento antes de agendar."
                            )
                            self.kommo.add_note(_lid_c109, _nota_c109)
                        except Exception:  # noqa: BLE001
                            pass
        except Exception as _e_c109_pipe:  # noqa: BLE001
            log.warning("[C-109 PIPELINE] check falhou (fail-open): %s", _e_c109_pipe)

        # 3a-C129 (12/08/2026) — Pós-consulta → escalar para 1-ATENDIMENTO HUMANO.
        # pos_consulta.py gravou flag blink:c129_pos_consulta:{lead_id} (TTL 24h)
        # quando paciente pediu recibo/reembolso/laudo/etc OU a_fazer_pos_consulta=True.
        # Aqui: desativar IA + mover pra 1-ATENDIMENTO HUMANO + nota Kommo.
        try:
            _redis_c129 = getattr(self, "_redis", None)
            _lid_c129 = (
                caller_context.get("lead_id") if isinstance(caller_context, dict) else None
            )
            if _redis_c129 and _lid_c129:
                _flag_c129 = _redis_c129.get(f"blink:c129_pos_consulta:{_lid_c129}")
                if _flag_c129:
                    log.info(
                        "[C-129 PIPELINE] pos-consulta lead=%s — "
                        "desativando IA + movendo pra 1-ATENDIMENTO HUMANO",
                        _lid_c129,
                    )
                    _redis_c129.delete(f"blink:c129_pos_consulta:{_lid_c129}")
                    if self.kommo is not None:
                        _status_c129 = (
                            caller_context.get("status_id")
                            if isinstance(caller_context, dict) else None
                        )
                        _ETAPAS_FINAIS_C129 = {142, 143, 91486864}
                        # (1) Desativar IA
                        try:
                            self.kommo.update_lead_fields(
                                _lid_c129, {"ativado_ia": "DESATIVADO"}
                            )
                        except Exception as _e_c129_ia:  # noqa: BLE001
                            log.warning("[C-129] desativar IA falhou: %s", _e_c129_ia)
                        # (2) Mover pra 1-ATENDIMENTO HUMANO (106563343)
                        if _status_c129 and _status_c129 not in _ETAPAS_FINAIS_C129:
                            try:
                                self.kommo.update_lead_status(_lid_c129, 106563343)
                                log.info(
                                    "[C-129] lead %s movido → 1-ATENDIMENTO HUMANO",
                                    _lid_c129,
                                )
                            except Exception as _e_c129_st:  # noqa: BLE001
                                log.warning(
                                    "[C-129] mover status falhou lead=%s: %s",
                                    _lid_c129, _e_c129_st,
                                )
                        # (3) Nota Kommo
                        try:
                            import datetime as _dt_c129
                            _nota_c129 = (
                                f"📋 [LIA C-129 {_dt_c129.datetime.now().strftime('%H:%M %d/%m')}] "
                                "Mensagem pós-consulta detectada — paciente pode estar pedindo "
                                "recibo/resultado/atestado ou tem a_fazer=Pós Consulta. "
                                "IA desativada. Equipe humana responde. "
                                f"Msg paciente: \"{user_text[:200]}\""
                            )
                            self.kommo.add_note(_lid_c129, _nota_c129)
                        except Exception:  # noqa: BLE001
                            pass
        except Exception as _e_c129_pipe:  # noqa: BLE001
            log.warning("[C-129 PIPELINE] check falhou (fail-open): %s", _e_c129_pipe)

        # 3a-C119 (11/08/2026) — Aceite slot + "pode marcar" inline.
        # deve_gerar_confirmacao_aceite (blindagens_deterministicas.py) injetou
        # ctx["known"]["c119_slot_para_gravar"] = slot. Aqui: gravar Medware e
        # avançar FSM para POS_GRAVACAO — salta o turno de CONFIRMACAO.
        try:
            _slot_c119 = (
                caller_context.get("known") or {}
            ).get("c119_slot_para_gravar")
            _lid_c119 = (
                caller_context.get("lead_id")
                if isinstance(caller_context, dict) else None
            )
            if _slot_c119 and _lid_c119:
                # Limpa flag imediatamente (evita re-trigger no próximo turno)
                if isinstance(caller_context.get("known"), dict):
                    caller_context["known"].pop("c119_slot_para_gravar", None)
                _known_c119 = caller_context.get("known") or {}
                _decision_c119 = {
                    "medico": _known_c119.get("medico") or "",
                    "unidade": _known_c119.get("unidade") or "",
                    "data_iso": _slot_c119.get("data_iso") or "",
                    "hora": _slot_c119.get("hora") or "",
                }
                if _decision_c119["data_iso"] and _decision_c119["hora"]:
                    log.info(
                        "[C-119 PIPELINE] gravando Medware lead=%s %s %s",
                        _lid_c119,
                        _decision_c119["data_iso"],
                        _decision_c119["hora"],
                    )
                    from voice_agent.agendamento import (  # noqa: PLC0415
                        executar_agendamento as _exec_ag_c119,
                    )
                    _res_c119 = _exec_ag_c119(
                        _decision_c119,
                        caller_context,
                        self.medware if hasattr(self, "medware") else None,
                        self.kommo if hasattr(self, "kommo") else None,
                        getattr(self, "_redis", None),
                    )
                    if (_res_c119 or {}).get("ok"):
                        log.info("[C-119 PIPELINE] OK lead=%s", _lid_c119)
                        try:
                            from voice_agent.fsm_conversa import (  # noqa: PLC0415
                                EstadoConversa as _EC_c119,
                                FSMManager as _FSMMgr_c119,
                            )
                            _FSMMgr_c119(getattr(self, "_redis", None)).transicionar(
                                conversation_key,
                                _EC_c119.POS_GRAVACAO,
                                motivo="C-119 aceite+pode_marcar inline",
                            )
                        except Exception as _e_fsm_c119:  # noqa: BLE001
                            log.warning("[C-119 FSM] transicionar falhou: %s", _e_fsm_c119)
                    else:
                        log.warning(
                            "[C-119 PIPELINE] agendamento falhou lead=%s motivo=%s",
                            _lid_c119,
                            (_res_c119 or {}).get("motivo"),
                        )
        except Exception as _e_c119_pipe:  # noqa: BLE001
            log.warning("[C-119 PIPELINE] check falhou (fail-open): %s", _e_c119_pipe)

        # 3a-ter) Bug C-92 (05/08/2026 Beatriz 16843614) — paciente AGENDADO pediu
        # remarcar, corrigir dados ou fila de espera.
        # Filtro C-92 em responder.py já substituiu o texto e gravou flag Redis.
        # Aqui: desativar IA + mover pra 1-ATENDIMENTO HUMANO + nota Kommo.
        try:
            _redis_c92 = getattr(self, "_redis", None)
            _lid_c92_pipe = (
                caller_context.get("lead_id") if isinstance(caller_context, dict) else None
            )
            if _redis_c92 and _lid_c92_pipe:
                _flag_c92 = _redis_c92.get(f"blink:c92_reagendamento_agendado:{_lid_c92_pipe}")
                if _flag_c92:
                    log.error(
                        "[C-92 PIPELINE] paciente AGENDADO pediu remarcar lead=%s — "
                        "movendo pra ATENDIMENTO HUMANO + desativando IA",
                        _lid_c92_pipe,
                    )
                    _redis_c92.delete(f"blink:c92_reagendamento_agendado:{_lid_c92_pipe}")
                    if self.kommo is not None:
                        _status_c92_pipe = (
                            caller_context.get("status_id")
                            if isinstance(caller_context, dict) else None
                        )
                        _ETAPAS_FINAIS_C92 = {142, 143, 91486864, 106563343}
                        # (1) Desativar IA
                        try:
                            self.kommo.update_lead_fields(
                                _lid_c92_pipe, {"ativado_ia": "DESATIVADO"}
                            )
                        except Exception as _e_c92_ia:  # noqa: BLE001
                            log.warning("[C-92] desativar IA falhou: %s", _e_c92_ia)
                        # (2) Mover pra 1-ATENDIMENTO HUMANO
                        if _status_c92_pipe and _status_c92_pipe not in _ETAPAS_FINAIS_C92:
                            try:
                                self.kommo.update_lead_status(_lid_c92_pipe, 106563343)
                                log.info(
                                    "[C-92] lead %s movido → 1-ATENDIMENTO HUMANO",
                                    _lid_c92_pipe,
                                )
                            except Exception as _e_c92_st:  # noqa: BLE001
                                log.warning(
                                    "[C-92] mover status falhou lead=%s: %s",
                                    _lid_c92_pipe, _e_c92_st,
                                )
                        # (3) Nota Kommo
                        try:
                            import datetime as _dt_c92
                            _nota_c92 = (
                                f"🔄 [LIA C-92 {_dt_c92.datetime.now().strftime('%H:%M %d/%m')}] "
                                "Paciente AGENDADO pediu remarcar/corrigir dados/fila de espera. "
                                "IA desativada + lead movido pra ATENDIMENTO HUMANO. "
                                f"Msg: \"{user_text[:200]}\""
                            )
                            self.kommo.add_note(_lid_c92_pipe, _nota_c92)
                        except Exception:  # noqa: BLE001
                            pass
        except Exception as _e_c92_pipe:  # noqa: BLE001
            log.warning("[C-92 PIPELINE] check falhou (fail-open): %s", _e_c92_pipe)

        # 3a-qua) Bug C-114 (11/08/2026) — resposta à oferta "poltrona de avião".
        # politica_comparecimento.py gravou flag blink:c114_sinal_solicitado:{lead_id}
        # quando enviou as 2 opções ao paciente PARTICULAR.
        # Aqui: detectar escolha ("fila" ou "reserva") e agir:
        #   fila    → A FAZER = Fila Encaixe (enum 927866) + move → 4.REAGENDAR
        #   reserva → A FAZER = Encaixe (enum 927023) + nota "aguardando comprovante"
        try:
            _redis_c114_pipe = getattr(self, "_redis", None)
            _lid_c114_pipe = (
                caller_context.get("lead_id") if isinstance(caller_context, dict) else None
            )
            if _redis_c114_pipe and _lid_c114_pipe:
                # Só age se C-114 foi previamente disparado para este lead
                _flag_c114_pipe = _redis_c114_pipe.get(
                    f"blink:c114_sinal_solicitado:{_lid_c114_pipe}"
                )
                if _flag_c114_pipe:
                    from voice_agent.politica_comparecimento import detectar_escolha_c114 as _det_c114
                    _escolha_c114 = _det_c114(user_text, _lid_c114_pipe, _redis_c114_pipe)
                    if _escolha_c114 in ("fila", "reserva"):
                        # Limpar flag de solicitação (evita reprocessar)
                        _redis_c114_pipe.delete(f"blink:c114_sinal_solicitado:{_lid_c114_pipe}")
                        import datetime as _dt_c114
                        _ts_c114 = _dt_c114.datetime.now().strftime("%H:%M %d/%m")
                        if self.kommo is not None:
                            # Atualizar campo "A FAZER" (field 1259312) via patch_custom_fields_raw
                            # Bug C-12: update_lead_fields não grava multiselect corretamente.
                            # Usando patch_custom_fields_raw que faz PATCH + GET de validação.
                            _a_fazer_enum_c114 = (
                                927866 if _escolha_c114 == "fila" else 927023
                            )
                            try:
                                self.kommo.patch_custom_fields_raw(
                                    _lid_c114_pipe,
                                    [{"field_id": 1259312, "values": [{"enum_id": _a_fazer_enum_c114}]}],
                                )
                                log.info(
                                    "[C-114 PIPELINE] A FAZER → %s (enum %d) lead=%s",
                                    _escolha_c114, _a_fazer_enum_c114, _lid_c114_pipe,
                                )
                            except Exception as _e_c114_cf:  # noqa: BLE001
                                log.warning("[C-114] patch A FAZER falhou: %s", _e_c114_cf)

                            if _escolha_c114 == "fila":
                                # Mover para 4.REAGENDAR — aguarda slot alternativo
                                _status_c114 = (
                                    caller_context.get("status_id")
                                    if isinstance(caller_context, dict) else None
                                )
                                _ETAPAS_FINAIS_C114 = {142, 143, 91486864}
                                if _status_c114 and _status_c114 not in _ETAPAS_FINAIS_C114:
                                    try:
                                        self.kommo.update_lead_status(_lid_c114_pipe, 106184631)
                                        log.info(
                                            "[C-114 PIPELINE] lead %s movido → 4.REAGENDAR",
                                            _lid_c114_pipe,
                                        )
                                    except Exception as _e_c114_st:  # noqa: BLE001
                                        log.warning(
                                            "[C-114] mover status falhou lead=%s: %s",
                                            _lid_c114_pipe, _e_c114_st,
                                        )
                                # Nota Kommo
                                try:
                                    _nota_c114_fila = (
                                        f"🗓️ [LIA C-114 {_ts_c114}] "
                                        "Paciente PARTICULAR escolheu FILA DE ENCAIXE "
                                        "(sem pagamento, sem exclusividade no horário). "
                                        "A FAZER = Fila Encaixe. Lead movido → 4.REAGENDAR. "
                                        f"Msg: \"{user_text[:200]}\""
                                    )
                                    self.kommo.add_note(_lid_c114_pipe, _nota_c114_fila)
                                except Exception:  # noqa: BLE001
                                    pass

                            else:  # reserva
                                # Grava flag Redis para C-116 detectar comprovante Pix.
                                # TTL 7d — paciente pode demorar pra pagar.
                                try:
                                    _redis_c114_pipe.setex(
                                        f"blink:c114_aguardando_comprovante:{_lid_c114_pipe}",
                                        7 * 24 * 3600,
                                        "1",
                                    )
                                    log.info(
                                        "[C-114 PIPELINE] flag aguardando_comprovante set lead=%s",
                                        _lid_c114_pipe,
                                    )
                                except Exception as _e_c114_flag:  # noqa: BLE001
                                    log.warning(
                                        "[C-114] setex aguardando_comprovante falhou: %s",
                                        _e_c114_flag,
                                    )
                                # Nota Kommo — aguardando comprovante Pix
                                try:
                                    _nota_c114_res = (
                                        f"💳 [LIA C-114 {_ts_c114}] "
                                        "Paciente PARTICULAR escolheu RESERVA GARANTIDA "
                                        "(Pix 50% do valor). Aguardando comprovante. "
                                        "A FAZER = Encaixe. "
                                        f"Msg: \"{user_text[:200]}\""
                                    )
                                    self.kommo.add_note(_lid_c114_pipe, _nota_c114_res)
                                except Exception:  # noqa: BLE001
                                    pass
        except Exception as _e_c114_pipe:  # noqa: BLE001
            log.warning("[C-114 PIPELINE] check falhou (fail-open): %s", _e_c114_pipe)

        # 3a-cin) Bug C-116 (11/08/2026) — Comprovante Pix detectado.
        # bypass comprovante_pix (blindagens_deterministicas) já intercepetou
        # o user_text de imagem, respondeu ao paciente e gravou
        # blink:c116_comprovante_detectado:{lead_id}.
        # Aqui: lemos o flag e fazemos os side effects Kommo:
        #   1. Nota "comprovante recebido"
        #   2. Deletar blink:c114_aguardando_comprovante:{lead_id}
        #   3. Deletar blink:c116_comprovante_detectado:{lead_id}
        try:
            _redis_c116 = getattr(self, "_redis", None)
            _lid_c116 = (
                caller_context.get("lead_id") if isinstance(caller_context, dict) else None
            )
            if _redis_c116 and _lid_c116:
                _flag_c116 = _redis_c116.get(f"blink:c116_comprovante_detectado:{_lid_c116}")
                if _flag_c116:
                    import datetime as _dt_c116
                    _ts_c116 = _dt_c116.datetime.now().strftime("%H:%M %d/%m")
                    # Nota Kommo
                    if self.kommo is not None:
                        try:
                            _nota_c116 = (
                                f"📲 [LIA C-116 {_ts_c116}] "
                                "Comprovante Pix recebido via WhatsApp. "
                                "Aguardando confirmação da equipe para validar pagamento "
                                "e garantir o horário."
                            )
                            self.kommo.add_note(_lid_c116, _nota_c116)
                        except Exception as _e_c116_note:  # noqa: BLE001
                            log.warning("[C-116] add_note falhou: %s", _e_c116_note)
                    # Limpeza dos flags Redis
                    try:
                        _redis_c116.delete(f"blink:c114_aguardando_comprovante:{_lid_c116}")
                        _redis_c116.delete(f"blink:c116_comprovante_detectado:{_lid_c116}")
                        log.info(
                            "[C-116 PIPELINE] flags limpos lead=%s", _lid_c116
                        )
                    except Exception as _e_c116_del:  # noqa: BLE001
                        log.warning("[C-116] delete flags falhou: %s", _e_c116_del)
        except Exception as _e_c116_pipe:  # noqa: BLE001
            log.warning("[C-116 PIPELINE] check falhou (fail-open): %s", _e_c116_pipe)

        # 3a-sex) Bug C-123 (11/08/2026) — Escolha pós-recusa de convênio.
        # bypass deve_responder_escolha_convenio() injetou em ctx.known:
        #   c123_marcar_sem_convenio = True  →  paciente escolheu Seguir Sem Convênio
        #   c123_encerrar_so_convenio = True →  paciente insiste em Somente com Convênio
        # Aqui: gravar campo CONVÊNIO = "Não se aplica" (field 853206) no Kommo
        # + gravar Ñ ACEITO CONVÊNIO com o plano recusado (field 1175268)
        # + mover lead → 2.LEADS FRIO se insistiu em só com convênio.
        try:
            _known_c123 = (
                caller_context.get("known") if isinstance(caller_context, dict) else {}
            ) or {}
            _lid_c123 = (
                caller_context.get("lead_id") if isinstance(caller_context, dict) else None
            )
            _marcar_sem_c123 = _known_c123.get("c123_marcar_sem_convenio")
            _encerrar_so_c123 = _known_c123.get("c123_encerrar_so_convenio")

            if _lid_c123 and self.kommo is not None and (_marcar_sem_c123 or _encerrar_so_c123):
                import datetime as _dt_c123
                _ts_c123 = _dt_c123.datetime.now().strftime("%H:%M %d/%m")

                if _marcar_sem_c123:
                    # Limpar flag (idempotência)
                    _known_c123.pop("c123_marcar_sem_convenio", None)

                    # Gravar CONVÊNIO = "Não se aplica" (enum_id 906979, field 853206)
                    # Usar patch_custom_fields_raw — Bug C-12: update_lead_fields não grava select
                    try:
                        self.kommo.patch_custom_fields_raw(
                            _lid_c123,
                            [{"field_id": 853206, "values": [{"enum_id": 906979}]}],
                        )
                        log.info(
                            "[C-123 PIPELINE] CONVÊNIO = Não se aplica gravado lead=%s",
                            _lid_c123,
                        )
                    except Exception as _e_c123_conv:  # noqa: BLE001
                        log.warning("[C-123] gravar CONVÊNIO falhou: %s", _e_c123_conv)

                    # Gravar Ñ ACEITO CONVÊNIO com o plano recusado (field 1175268)
                    # se o nome foi preservado em ctx.known.c123_convenio_recusado
                    _conv_recusado_c123 = _known_c123.get("c123_convenio_recusado", "")
                    if _conv_recusado_c123:
                        try:
                            # update_lead_fields lida com o mapeamento nome→enum_id
                            self.kommo.update_lead_fields(
                                _lid_c123,
                                {"nao_aceito_convenio": _conv_recusado_c123},
                            )
                            log.info(
                                "[C-123] Ñ ACEITO CONVÊNIO = %s lead=%s",
                                _conv_recusado_c123, _lid_c123,
                            )
                        except Exception as _e_c123_nao:  # noqa: BLE001
                            log.warning("[C-123] gravar Ñ ACEITO CONVÊNIO falhou: %s", _e_c123_nao)

                    # Nota Kommo
                    try:
                        _conv_disp_c123 = _conv_recusado_c123 or "convênio recusado"
                        self.kommo.add_note(
                            _lid_c123,
                            f"✅ [LIA C-123 {_ts_c123}] Paciente escolheu SEGUIR SEM CONVÊNIO. "
                            f"Plano: {_conv_disp_c123}. "
                            f"CONVÊNIO → Não se aplica. Coleta de motivo em andamento.",
                        )
                    except Exception:  # noqa: BLE001
                        pass

                if _encerrar_so_c123:
                    # Limpar flag
                    _known_c123.pop("c123_encerrar_so_convenio", None)

                    # Mover lead → 2.LEADS FRIO e desativar IA
                    _status_c123 = (
                        caller_context.get("status_id") if isinstance(caller_context, dict) else None
                    )
                    _ETAPAS_FINAIS_C123 = {142, 143, 91486864, 106563343}
                    if _status_c123 and _status_c123 not in _ETAPAS_FINAIS_C123:
                        try:
                            self.kommo.update_lead_status(_lid_c123, 101508307)  # 2.LEADS FRIO
                            log.info("[C-123] lead %s movido → 2.LEADS FRIO", _lid_c123)
                        except Exception as _e_c123_st:  # noqa: BLE001
                            log.warning("[C-123] mover status falhou: %s", _e_c123_st)
                    try:
                        self.kommo.update_lead_fields(_lid_c123, {"ativado_ia": "DESATIVADO"})
                    except Exception as _e_c123_ia:  # noqa: BLE001
                        log.warning("[C-123] desativar IA falhou: %s", _e_c123_ia)
                    try:
                        self.kommo.add_note(
                            _lid_c123,
                            f"🔕 [LIA C-123 {_ts_c123}] Paciente insistiu em SOMENTE com convênio. "
                            "IA desativada. Lead movido → 2.LEADS FRIO. "
                            "Avisar quando credenciamento concluído.",
                        )
                    except Exception:  # noqa: BLE001
                        pass

        except Exception as _e_c123_pipe:  # noqa: BLE001
            log.warning("[C-123 PIPELINE] check falhou (fail-open): %s", _e_c123_pipe)

        # 4) Envio (se houver destino)
        if not reply_to_number:
            return PipelineResult(
                transcript=user_text, answer=answer, sent=False,
                model_used=model_used, articles_used=articles_used,
            )

        # 4a) Áudios Fabricio (task #68) — detecta marcador [AUDIO:audio_id]
        # na resposta, valida guardas (janela 24h, limite, preferência texto),
        # envia texto SEM marcador + áudio em sequência. Falha silenciosa
        # mantém só o texto. Toggle: AUDIOS_FABRICIO_ENABLED.
        audio_id_pra_enviar: Optional[str] = None
        try:
            from voice_agent import audios_fabricio as _af
            if _af.audios_habilitados():
                _id = _af.detectar_marcador(answer)
                if _id:
                    # Pega last_inbound_ts do Redis ou caller_context
                    _last_in = None
                    try:
                        if isinstance(caller_context, dict):
                            _last_in = caller_context.get("last_inbound_ts")
                    except Exception:  # noqa: BLE001
                        pass
                    _prefere_texto = bool(
                        (caller_context or {}).get(
                            "paciente_prefere_texto", False
                        )
                    )
                    _guarda = _af.pode_enviar_audio(
                        conversation_key,
                        redis_client=getattr(self, "_redis", None),
                        last_inbound_ts=_last_in,
                        paciente_prefere_texto=_prefere_texto,
                    )
                    if _guarda.pode_enviar:
                        audio_id_pra_enviar = _id
                    else:
                        log.info(
                            "[AUDIO FABRICIO] %s bloqueado: %s",
                            _id, _guarda.motivo,
                        )
                    # Sempre limpa o marcador antes do envio textual
                    answer = _af.limpar_marcador(answer)
        except Exception as exc:  # noqa: BLE001
            log.warning("[AUDIO FABRICIO] detecção falhou: %s", exc)

        # DEDUP FORTE pré-envio (bug Kamila 24064723, 02/06/2026 11:24 BRT):
        # Lia enviou DUAS mensagens IDÊNTICAS em <1s. Causa: 2 webhooks
        # próximos disparam 2 turnos, ambos geram mesma resposta. Hash
        # SHA1(conversation_key + answer) + Redis SETEX 10s bloqueia o 2º.
        try:
            _redis_dedup = getattr(self, "_redis", None)
            if _redis_dedup is not None and answer:
                import hashlib as _h
                _hash = _h.sha1(
                    (str(conversation_key) + "|" + answer).encode("utf-8")
                ).hexdigest()[:16]
                _key = f"blink:dedup_outbound:{_hash}"
                # set if not exists, com TTL 10s
                _ok = _redis_dedup.set(_key, "1", nx=True, ex=10)
                if not _ok:
                    log.warning(
                        "[DEDUP OUTBOUND] mensagem duplicada bloqueada "
                        "convo=%s preview=%r", conversation_key, answer[:80],
                    )
                    return PipelineResult(
                        transcript=user_text, answer=answer, sent=False,
                        model_used=model_used, articles_used=articles_used,
                        error="dedup: mensagem idêntica enviada recentemente",
                    )
        except Exception as _dedup_err:  # noqa: BLE001
            log.warning("[DEDUP OUTBOUND] check falhou (ignora): %s", _dedup_err)

        # Bug C-127 Fix 1 (12/08/2026) — Tom conversacional: enviar em chunks.
        # Mensagens longas são quebradas em 2-3 partes com delay de ~1.2s.
        # Toggle: MESSAGE_SPLIT_ENABLED=0 em Easypanel → desliga splitting.
        try:
            from voice_agent.message_splitter import send_split as _send_split
            _send_split(
                lambda _t: self.evolution.send_text(
                    number=reply_to_number,
                    text=_t,
                    quoted_message_id=quoted_message_id,
                ),
                answer,
            )
        except EvolutionError as e:
            log.exception("envio Evolution falhou")
            return PipelineResult(
                transcript=user_text, answer=answer, sent=False,
                model_used=model_used, articles_used=articles_used,
                error=f"evolution: {e}",
            )

        # 4a-bis) Envia áudio em sequência (depois do texto pra paciente
        # ler primeiro a explicação). Se método send_audio não existir
        # no client, degrada silenciosa.
        if audio_id_pra_enviar:
            try:
                from voice_agent import audios_fabricio as _af2
                url = _af2.url_audio(audio_id_pra_enviar)
                send_audio = getattr(self.evolution, "send_audio", None)
                if url and callable(send_audio):
                    send_audio(number=reply_to_number, url=url)
                    _af2.incrementar_contador(
                        conversation_key,
                        redis_client=getattr(self, "_redis", None),
                    )
                    log.info(
                        "[AUDIO FABRICIO] %s enviado pra %s",
                        audio_id_pra_enviar, reply_to_number,
                    )
                else:
                    log.warning(
                        "[AUDIO FABRICIO] send_audio indisponível ou url=%r",
                        url,
                    )
            except Exception as e:  # noqa: BLE001
                log.warning("[AUDIO FABRICIO] envio áudio falhou: %s", e)

        # 4b) Follow-up: se a resposta apresentou o VALOR, arma o marcador
        # pós-valor (template). Caso contrário, arma o de PRIMEIRO CONTATO
        # — se o paciente não responder, a Lia manda um nudge de retomada.
        try:
            if followup.answer_has_value(answer):
                followup.set_pending(self._redis, conversation_key)
            else:
                followup.set_firstcontact(self._redis, conversation_key)
        except Exception:  # noqa: BLE001
            pass

        # 5) Auto-preenchimento do Kommo CRM (best-effort, em background)
        # — não bloqueia a resposta do WhatsApp se Kommo demorar/falhar.
        if self.kommo is not None and reply_to_number:
            threading.Thread(
                target=self._sync_kommo_safely,
                args=(reply_to_number, conversation_key, user_text, answer,
                      "96630710"),
                daemon=True,
            ).start()

        # 6) Gap 2: detectar se a Lia confirmou agendamento e gravar Medware.
        # Passa redis_client pra thread escrever status real (Gap 5) — assim
        # a Lia consegue saber no próximo turno se o agendamento foi gravado
        # de verdade, evitando mentir pra o paciente (origem: lead 24038029).
        if self.medware is not None and self.kommo is not None and caller_context:
            from . import agendamento as _ag
            _redis = getattr(self, "_redis", None)
            threading.Thread(
                target=_ag.detectar_e_executar_safely,
                args=(answer, caller_context, self.medware, self.kommo,
                      self.settings.anthropic_api_key,
                      self.settings.claude_haiku_model, _redis),
                daemon=True,
            ).start()

        return PipelineResult(
            transcript=user_text, answer=answer, sent=True,
            model_used=model_used, articles_used=articles_used,
        )

    def _gravar_agrupador_silencioso(
        self, lead_id: int, campos: dict,
    ) -> None:
        """Grava motivo_tipo + agrupador no Kommo em thread background.

        Task #140. Origem: bug Adelia 24056883 — 01/06/2026. Conversas
        progrediam (perfil + motivo coletados) mas 1.EXAMES/Grupo ficava
        vazio porque selecionar_agrupador só era chamado em
        agendamento.salvar (que muitas vezes não chega).
        """
        if self.kommo is None or not lead_id:
            return
        try:
            self.kommo.update_lead_fields(lead_id, campos)
            log.info(
                "[AGRUPADOR EARLY] gravado no Kommo lead=%s campos=%s",
                lead_id, list(campos.keys()),
            )
        except Exception as e:  # noqa: BLE001
            log.warning(
                "[AGRUPADOR EARLY] gravação falhou lead=%s: %s", lead_id, e,
            )

    def _sync_kommo_safely(
        self,
        phone: str,
        conversation_key: str,
        user_text: str | None = None,
        answer: str | None = None,
        channel: str = "",
        lead_id_hint: int | None = None,
    ) -> None:
        """Sincroniza o lead do Kommo: grava a nota da conversa e atualiza
        os campos extraídos.

        Roda em thread separada — qualquer erro é logado, não propaga.

        Bug C-36 #1 (17/06/2026): leads recém-criados (segundos atrás) não
        aparecem em /leads?query=PHONE — Kommo demora pra indexar. Resultado:
        find_lead_id_by_phone retorna None → pipeline ABORTAVA gravação
        silenciosamente. Lead 24168922 Manuela: chat ativo mas zero notas.

        Fix 3 camadas:
          1) lead_id_hint — caller (webhook) passa direto se já souber
          2) Cache Redis blink:chat_to_lead:{conversation_key} — TTL 24h
          3) Retry 3x com backoff 1s/2s/4s pra dar tempo da indexação
          4) Quando achar via busca, persiste no cache pros próximos turns
          5) Log WARNING (não INFO) quando falha total — visibilidade pra
             monitorar taxa de race condition em prod
        """
        import time as _time
        if self.kommo is None:
            return
        try:
            lead_id: int | None = None

            # Camada 1: caller passou direto (webhook Kommo tem no payload)
            if lead_id_hint:
                lead_id = int(lead_id_hint)
                log.debug("[KOMMO SYNC] lead_id via hint=%s", lead_id)

            # Camada 2: cache Redis (turn-by-turn da mesma conversa)
            cache_key = f"blink:chat_to_lead:{conversation_key}"
            if lead_id is None and self._redis is not None:
                try:
                    cached = self._redis.get(cache_key)
                    if cached:
                        lead_id = int(
                            cached.decode() if isinstance(cached, bytes) else cached
                        )
                        log.debug(
                            "[KOMMO SYNC] lead_id via cache=%s convo=%s",
                            lead_id, conversation_key,
                        )
                except Exception as e:  # noqa: BLE001
                    log.debug("[KOMMO SYNC] cache read falhou: %s", e)

            # Camada 3: busca por telefone com retry (race condition de
            # indexação Kommo pra leads recém-criados)
            if lead_id is None:
                for tentativa in (0, 1, 2):
                    lead_id = self.kommo.find_lead_id_by_phone(phone)
                    if lead_id:
                        if tentativa > 0:
                            log.info(
                                "[KOMMO SYNC] lead achado na retry %d phone=%s",
                                tentativa, phone,
                            )
                        break
                    if tentativa < 2:
                        _time.sleep(2 ** tentativa)  # 1s, 2s, 4s
                if not lead_id:
                    log.warning(
                        "[KOMMO SYNC] lead NÃO encontrado após 3 tentativas "
                        "phone=%s convo=%s — nota Lia será DESCARTADA. "
                        "Possível causa: telefone não casa formato Kommo, "
                        "ou lead criado há >60s sem indexar ainda.",
                        phone, conversation_key,
                    )
                    return

            # Persistir no cache pros próximos turns (TTL 24h)
            if self._redis is not None and lead_id:
                try:
                    self._redis.setex(cache_key, 86400, str(lead_id))
                except Exception as e:  # noqa: BLE001
                    log.debug("[KOMMO SYNC] cache write falhou: %s", e)
            # Nota da conversa — grava AMBOS os lados (paciente + Lia).
            #
            # Histórico de mudanças:
            # 01/06/2026 17:39 (Fábio): removida gravação INBOUND, "chat
            #   nativo já mostra a msg". Feed ficou "limpo" mas contexto
            #   quebrou pra visibilidade humana E pra debug de sessões
            #   quebradas (ver bug 12/07 lead 24290902: caiu em fallback
            #   "instabilidade" e não dava pra saber o que o paciente
            #   respondeu). Task #154, #264, #378.
            # 12/07/2026 (Fábio): reverter. Voltar a gravar INBOUND.
            #   "Este é um retrocesso. Estava funcionando."
            #
            # Inbound do paciente (grava ANTES da Lia pra ordem cronológica correta)
            if user_text:
                nota_in = f"💬 Paciente (WhatsApp):\n{user_text.strip()}"
                try:
                    self.kommo.add_note(lead_id, nota_in)
                except Exception as e:  # noqa: BLE001
                    log.warning(
                        "Kommo nota INBOUND falhou (%s): %s", phone, e
                    )
            # Outbound da Lia
            if answer:
                note = f"🤖 Lia (WhatsApp):\n{answer.strip()}"
                try:
                    self.kommo.add_note(lead_id, note)
                except Exception as e:  # noqa: BLE001
                    log.warning("Kommo nota falhou (%s): %s", phone, e)
            # Contexto atual do lead (etapa + estado da IA) — uma leitura só.
            try:
                ctx = self.kommo.get_caller_context_by_lead(lead_id)
            except Exception as e:  # noqa: BLE001
                log.warning("Kommo ctx falhou (%s): %s", phone, e)
                ctx = {}
            # Campos extraídos da conversa.
            fields = self.responder.extract_lead_fields(conversation_key) or {}

            # === PROTEÇÃO C-91 (05/08/2026 — Haiku inferiu SUS sem menção do paciente) ===
            # Haiku às vezes infere nao_aceito_convenio="SUS" para bebês/crianças
            # sem que o paciente tenha mencionado o convênio. Aqui, validamos que
            # o nome do convênio aparece EXPLICITAMENTE no texto da mensagem ou
            # no histórico de notas antes de gravar no Kommo.
            try:
                _nac_c91 = fields.get("nao_aceito_convenio")
                if _nac_c91:
                    # Monta corpus de textos do paciente neste turn
                    _ctx_c91 = ctx if isinstance(ctx, dict) else {}
                    _corpus_c91 = " ".join([
                        str(user_text or ""),
                        str((_ctx_c91.get("known") or {}).get("notas_historico") or ""),
                    ]).lower()
                    # Aliases dos convênios que o Haiku pode inferir indevidamente
                    _ALIASES_C91: dict = {
                        "sus": ["sus", "s.u.s", "sistema único"],
                        "inas gdf": ["inas", "gdf", "saúde gdf"],
                        "amil": ["amil"],
                        "bradesco": ["bradesco"],
                        "cassi": ["cassi"],
                        "unimed": ["unimed"],
                        "notre dame": ["notre dame", "notredame", "ndm"],
                        "sul américa": ["sul am", "sulam"],
                        "assefaz": ["assefaz"],
                        "fusex": ["fusex"],
                        "geap": ["geap"],
                        "hap vida": ["hap"],
                        "pm": ["pm saúde", "pmsaúde"],
                        "porto seguro": ["porto seguro"],
                        "outro": [],  # "Outro" genérico não precisa de validação
                    }
                    _key_c91 = str(_nac_c91).lower().strip()
                    _terms_c91 = _ALIASES_C91.get(_key_c91, [_key_c91])
                    _mencionado_c91 = any(t in _corpus_c91 for t in _terms_c91) if _terms_c91 else True
                    if not _mencionado_c91:
                        log.warning(
                            "[C-91] nao_aceito_convenio=%r NÃO foi mencionado pelo "
                            "paciente — descartando para evitar invenção de SUS/convênio. "
                            "lead=%s user_text=%r",
                            _nac_c91, lead_id, str(user_text or "")[:80],
                        )
                        fields.pop("nao_aceito_convenio", None)
                        # Remover motivo_perda inferido junto (pode ter sido injetado também)
                        if fields.get("motivo_perda") == "Somente Convênio":
                            fields.pop("motivo_perda", None)
            except Exception as _e_c91:  # noqa: BLE001
                log.warning("[C-91] validação fail-open: %s", _e_c91)

            # Carimba o canal de entrada (8133 ou 0710) no campo do lead.
            if channel:
                fields["numero_telefone"] = channel
            # Se a Lia processou esta mensagem, a IA está ATIVADA neste lead.
            fields["ativado_ia"] = "ATIVADO"
            # ATENDENTE: a IA conduziu o atendimento → carimba "Lia".
            fields["atendente"] = "Lia"
            # HORA ATIVAÇÃO: se a IA estava DESATIVADA e voltou a atuar agora,
            # carimba o momento da reativação (não mexe se já estava ATIVADA).
            estado_anterior = str(
                (ctx.get("known") or {}).get("ativado_ia") or ""
            ).upper()
            if estado_anterior == "DESATIVADO":
                fields["hora_ativacao_ts"] = int(time.time())

            # PROTEÇÃO ANTI-ENVENENAMENTO (task #145, origem bug Diones 23742328)
            # Bug: Lia alucinou "Dr. Fabrício" quando ctx tinha "Dra. Karla";
            # extract_lead_fields detectou "Fabrício" no histórico; pipeline
            # gravou MÉDICOS=Fabrício no Kommo, sobrescrevendo Karla.
            # Próximo turn: ctx vem com medico=Fabrício, TRAVA defende o errado.
            #
            # Fix: MÉDICO/UNIDADE/CONVÊNIO só são gravados se o lead ainda
            # NÃO tem valor. Atendente humano segue podendo alterar manualmente
            # pelo Kommo (esse fluxo nem passa por aqui).
            known_atual = ctx.get("known") or {}
            for campo_critico in ("medico", "unidade", "convenio"):
                if (
                    fields.get(campo_critico)
                    and known_atual.get(campo_critico)
                    and str(fields[campo_critico]).strip().lower()
                    != str(known_atual[campo_critico]).strip().lower()
                ):
                    log.warning(
                        "[ANTI-ENVENENAMENTO] lead=%s campo=%s já é %r, "
                        "NÃO sobrescrevendo com %r (provável alucinação Lia)",
                        lead_id, campo_critico,
                        known_atual[campo_critico], fields[campo_critico],
                    )
                    fields.pop(campo_critico)

            # ── Campos de acompanhamento (task #231, 05/06/2026) ──────
            # Carimba a cada turn 4 campos visíveis na lista do funil:
            # STATUS CONVERSA, ULTIMA MSG OUTBOUND, PROXIMA ACAO,
            # TS ULTIMA MSG ENVIADA. Equipe humana enxerga o estado
            # de cada lead sem abrir o card.
            try:
                from voice_agent import campos_acompanhamento as _ca
                # Resolve estado FSM atual (best-effort).
                estado_fsm = None
                try:
                    from voice_agent.fsm_conversa import FSMManager as _FM
                    _r = getattr(self, "_redis", None)
                    if _r is not None:
                        _mgr_fsm = _FM(_r)
                        _snap_fsm = _mgr_fsm.get(conversation_key)
                        if _snap_fsm is not None:
                            estado_fsm = _snap_fsm.estado.value
                except Exception:  # noqa: BLE001
                    pass
                _ja_agendado = bool(ctx.get("ja_agendado"))
                _conv_negado = bool(
                    (ctx.get("known") or {}).get("nao_aceito_convenio")
                ) or (fields.get("motivo_perda") == "Somente Convênio")
                campos_acomp = _ca.montar_dict_campos(
                    answer=answer or "",
                    estado_fsm=estado_fsm,
                    autor="LIA",
                    ja_agendado=_ja_agendado,
                    convenio_nao_aceito=_conv_negado,
                )
                # Timestamp da última msg enviada — sempre Lia neste fluxo.
                campos_acomp["ts_ultima_msg_lia"] = int(time.time())
                fields.update(campos_acomp)
            except Exception as e:  # noqa: BLE001
                log.warning(
                    "[ACOMPANHAMENTO] fail (%s): %s — segue sem 4 campos",
                    phone, e,
                )

            # ── JANELA 24H (05/07/2026) ───────────────────────────────
            # Este sync roda logo após o inbound do paciente, então agora
            # ≈ timestamp do último inbound = quando a janela de 24h
            # (re)abre. Carimba ÚLTIMA MENS PACIENTE + JANELA 24H no Kommo
            # e grava o epoch no Redis (blink:janela:ultima_msg_paciente:*)
            # — chave que o cron de renovação já lê mas que ninguém escrevia.
            # A transição aberta→expirando→fechada durante o silêncio é
            # recalculada pelo cron (janela_24h_tick), não aqui.
            try:
                from voice_agent import campos_acompanhamento as _caj
                _in_ts = int(_time.time())
                _r_j = getattr(self, "_redis", None)
                if _r_j is not None:
                    try:
                        _r_j.set(
                            f"blink:janela:ultima_msg_paciente:{lead_id}",
                            _in_ts,
                        )
                    except Exception:  # noqa: BLE001
                        pass
                fields.update(_caj.campos_janela_24h(_in_ts))
            except Exception as e:  # noqa: BLE001
                log.warning("[JANELA24H] sync fail (%s): %s", phone, e)

            if fields:
                self.kommo.update_lead_fields(lead_id, fields)
                # Lead perdido por convênio não credenciado → fecha o card
                # como "Closed - lost" (status 143, válido em qualquer funil).
                if fields.get("motivo_perda"):
                    try:
                        self.kommo.update_lead_status(lead_id, 143)
                        log.info("Kommo lead %s fechado como perdido", lead_id)
                    except Exception as e:  # noqa: BLE001
                        log.warning("Kommo close-lost falhou (%s): %s", phone, e)
                else:
                    # Lead interagiu (e não foi perdido): se está numa etapa
                    # inicial do funil, move para 2-AGENDAR; e dá uma
                    # denominação ao card refletindo a última mensagem, para
                    # visibilidade da equipe humana.
                    try:
                        st = ctx.get("status_id")
                        # 0-ENTRADA, 1-FRIO, 2-AGENDAR, 3-REAGENDAR, 5.1-NO-SHOW
                        if st in (96441724, 101508307, 102560495,
                                  106184631, 106184983):
                            if st != 102560495:
                                self.kommo.update_lead_status(lead_id, 102560495)
                                log.info(
                                    "Kommo lead %s movido para 2-AGENDAR",
                                    lead_id,
                                )
                            denom = fields.get("denominacao")
                            if denom:
                                self.kommo.rename_lead(
                                    lead_id, f"AGENDAR_ {denom}"
                                )
                    except Exception as e:  # noqa: BLE001
                        log.warning(
                            "Kommo etapa/denominação falhou (%s): %s", phone, e
                        )
        except Exception as e:  # noqa: BLE001
            log.warning("Kommo sync falhou (%s): %s", phone, e)
