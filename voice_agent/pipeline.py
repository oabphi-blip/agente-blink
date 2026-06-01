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
                # no lead, para a equipe enxergar pelo campo "ATIVADO IA?".
                lid = caller_context.get("lead_id")
                if lid:
                    try:
                        self.kommo.update_lead_fields(
                            lid, {"ativado_ia": "DESATIVADO"}
                        )
                    except Exception as e:  # noqa: BLE001
                        log.warning("Carimbo ATIVADO IA? (off) falhou: %s", e)
                return PipelineResult(
                    transcript=user_text, answer="", sent=False,
                    model_used="", articles_used=[],
                )

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
                known = caller_context.get("known") or {}
                medico_param = known.get("medico") or "Dra. Karla Delalibera"
                unidade_param = known.get("unidade")  # pode ser None
                slots = self.medware.horarios_para_agente(
                    medico_param, unidade_param,
                )
                if slots:
                    caller_context["agenda"] = slots
                    caller_context["agenda_medico_inferido"] = (
                        "default_karla" if not known.get("medico") else "ctx"
                    )
                    log.info(
                        "Medware: %d horários para %s (fonte_medico=%s)",
                        len(slots), medico_param,
                        "ctx" if known.get("medico") else "default_karla",
                    )
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
                    else:
                        log.info(
                            "Medware: 0 horários para %s/%s (status=%s)",
                            medico_param, unidade_param, _status_id,
                        )
            except Exception as e:  # noqa: BLE001
                # WARNING não basta — origem do bug Juliene foi silêncio
                # silencioso. Subir pra ERROR.
                log.error("Medware horários falhou: %s", e)

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

        # 4) Envio (se houver destino)
        if not reply_to_number:
            return PipelineResult(
                transcript=user_text, answer=answer, sent=False,
                model_used=model_used, articles_used=articles_used,
            )

        try:
            self.evolution.send_text(
                number=reply_to_number,
                text=answer,
                quoted_message_id=quoted_message_id,
            )
        except EvolutionError as e:
            log.exception("envio Evolution falhou")
            return PipelineResult(
                transcript=user_text, answer=answer, sent=False,
                model_used=model_used, articles_used=articles_used,
                error=f"evolution: {e}",
            )

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

    def _sync_kommo_safely(
        self,
        phone: str,
        conversation_key: str,
        user_text: str | None = None,
        answer: str | None = None,
        channel: str = "",
    ) -> None:
        """Sincroniza o lead do Kommo: grava a nota da conversa e atualiza
        os campos extraídos.

        Roda em thread separada — qualquer erro é logado, não propaga.
        """
        if self.kommo is None:
            return
        try:
            lead_id = self.kommo.find_lead_id_by_phone(phone)
            if not lead_id:
                log.info("Kommo sync: lead não encontrado pra %s", phone)
                return
            # Nota da conversa — só a resposta da Lia, para a equipe
            # acompanhar o andamento no Kommo (os canais não passam
            # pelo chat nativo).
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
