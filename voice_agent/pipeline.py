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
            # Nota da conversa — APENAS resposta da Lia.
            # Decisão Fábio (01/06/2026 17:39): mensagens do paciente
            # NÃO precisam virar nota no Kommo (já aparecem no chat
            # nativo). Antes (commit do dia) gravávamos ambos lados,
            # mas o feed do Kommo ficou poluído. Mantemos só outbound
            # da Lia pra observabilidade do agente.
            #
            # NOTA: o `user_text` continua disponível pra debugging e
            # outros usos (extract_lead_fields, FSM, etc), só não vira
            # nota Kommo.
            #
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
