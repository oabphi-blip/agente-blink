"""Motor de follow-up pós-valor.

Quando o agente apresenta o valor da consulta e o paciente fica em
silêncio por alguns minutos, dispara UM template de retomada pelo 8133,
para tirar o paciente da inércia. Uma vez por lead.

Marcação: o pipeline chama set_pending() quando a resposta do agente
apresenta o valor, e clear_pending() sempre que o paciente responde.
O motor (tick) varre os marcadores e dispara quando passam do tempo de
silêncio configurado.

SEGURANÇA — duas travas, igual à reativação/broadcast:
  - followup_enabled=False → o motor nem roda.
  - followup_dry_run=True  → monta tudo, mas NÃO envia.

CADÊNCIA: acionado por POST /followup/tick — um cron externo chama a
cada poucos minutos.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from zoneinfo import ZoneInfo

log = logging.getLogger(__name__)
_TZ = ZoneInfo("America/Sao_Paulo")

_PENDING_PREFIX = "blink:followup:pending:"
_DONE_PREFIX = "blink:followup:done:"
# Follow-up de PRIMEIRO CONTATO: a Lia mandou mensagem e o paciente ainda
# não respondeu. Armado em toda resposta da Lia que NÃO apresentou valor.
_FIRSTCONTACT_PREFIX = "blink:followup:firstcontact:"

# Fallback em memória — pipeline e motor rodam no MESMO processo, então
# um dict de módulo é compartilhado entre eles quando não há Redis.
_MEM_PENDING: dict[str, float] = {}
_MEM_DONE: set[str] = set()
# Marcador de primeiro contato guarda "toque:timestamp" (ex.: "2:17796...").
_MEM_FIRSTCONTACT: dict[str, str] = {}

# Cadência de primeiro contato — quantos toques e o intervalo entre eles.
# Toque 1: usa followup_firstcontact_min (settings). Toques 2 e 3: +24h cada.
_FC_MAX_TOUCH = 3
_FC_TTL = 6 * 86400  # TTL do marcador, longo o bastante p/ toda a cadência


def _parse_fc(v) -> tuple[int, float]:
    """Lê o marcador 'toque:timestamp'. Valor antigo (só timestamp, sem
    ':') é tratado como toque 1, para compatibilidade."""
    if v is None:
        return (1, 0.0)
    s = v.decode() if isinstance(v, bytes) else str(v)
    if ":" in s:
        a, _, b = s.partition(":")
        try:
            return (max(1, int(a)), float(b))
        except (TypeError, ValueError):
            return (1, 0.0)
    try:
        return (1, float(s))
    except (TypeError, ValueError):
        return (1, 0.0)

_SEM_CONVENIO = {
    "", "não se aplica", "nao se aplica", "particular",
    "sem convênio", "sem convenio",
}


def _first_name(full: str) -> str:
    if not full or not full.strip():
        return "paciente"
    return full.strip().split()[0].capitalize()


# Vídeo educacional de catarata (Dr. Fabrício) — catálogo do canal
# #atendimento-com-multimidia, item 0009 "Surgimento da Catarata".
_VIDEO_CATARATA = "https://youtube.com/shorts/zy41CUVhVD8"


def _firstcontact_msg(
    nome: str, especialidade: str = "", motivo: str = "",
) -> str:
    """Monta a mensagem de reengajamento de primeiro contato.

    Para leads de CATARATA, inclui o vídeo educacional do Dr. Fabrício
    junto com o convite — explica a doença para quem veio do anúncio.
    """
    contexto = f"{especialidade} {motivo}".lower()
    if "catarata" in contexto:
        return (
            f"Oi, {nome}! 😊 Vi que você nos chamou aqui na Blink "
            "Oftalmologia sobre catarata.\n\n"
            "Enquanto isso, o Dr. Fabrício Freitas preparou um vídeo "
            "rapidinho explicando como a catarata surge — vale muito a "
            f"pena assistir 👇\n🎥 {_VIDEO_CATARATA}\n\n"
            "Posso te ajudar a agendar a sua avaliação? É só me contar 💙"
        )
    return (
        f"Oi, {nome}! 😊 Vi que você nos chamou aqui na Blink "
        "Oftalmologia. Posso te ajudar a agendar a sua consulta? É só me "
        "contar o que você precisa que eu cuido de tudo por aqui 💙"
    )


def _firstcontact_audio_url(settings, especialidade: str, motivo: str):
    """Escolhe o áudio da Dra. Karla para o nudge de primeiro contato,
    conforme a especialidade do lead. Devolve a URL pública ou None.

    Mapa (roteiro de áudios da Dra. Karla):
      estrabismo                 → karla_07 (parou após a triagem)
      oftalmopediatria/infantil  → karla_14 (consulta da criança)
      catarata                   → None (catarata usa o vídeo do Dr. Fabrício)
      rotina/geral/demais        → karla_17 (não respondeu ao 1º contato)
    """
    if not getattr(settings, "followup_audio_enabled", False):
        return None
    base = (getattr(settings, "audio_base_url", "") or "").rstrip("/")
    if not base:
        return None
    ctx = f"{especialidade} {motivo}".lower()
    if "catarata" in ctx:
        return None
    if "estrabismo" in ctx:
        fn = "karla_07.ogg"
    elif any(k in ctx for k in (
        "pediatr", "infantil", "criança", "crianca", "filho", "filha",
    )):
        fn = "karla_14.ogg"
    else:
        fn = "karla_17.ogg"
    return f"{base}/{fn}"


def _firstcontact_touch_content(touch, nome, especialidade, motivo, settings):
    """(texto, url_de_áudio) do toque N da cadência de primeiro contato.

      Toque 1 — acolhimento + áudio por especialidade (roteiro 7/14/17).
      Toque 2 — reengajamento suave (~24h depois) + áudio 20 do roteiro.
      Toque 3 — última tentativa (~48h depois) + áudio 21 do roteiro.
    Catarata não recebe áudio (usa o vídeo do Dr. Fabrício no toque 1)."""
    base = (getattr(settings, "audio_base_url", "") or "").rstrip("/")
    audio_on = bool(getattr(settings, "followup_audio_enabled", False) and base)
    ctx = f"{especialidade} {motivo}".lower()
    if touch <= 1:
        return (
            _firstcontact_msg(nome, especialidade, motivo),
            _firstcontact_audio_url(settings, especialidade, motivo),
        )
    if touch == 2:
        txt = (
            f"Oi, {nome}! 😊 Passei aqui de novo — sei que o dia corre. "
            "Se ainda quiser cuidar da sua consulta na Blink, é só me "
            "responder que eu cuido de tudo por aqui 💙"
        )
        url = (f"{base}/karla_20.ogg"
               if audio_on and "catarata" not in ctx else None)
        return (txt, url)
    # toque 3 — última tentativa, acolhedora
    txt = (
        f"{nome}, esta é a minha última mensagenzinha para não te "
        "incomodar 💙 Quando quiser retomar a sua consulta, é só me "
        "chamar aqui — vai ser um prazer te atender."
    )
    url = (f"{base}/karla_21.ogg"
           if audio_on and "catarata" not in ctx else None)
    return (txt, url)


def _postvalue_audio_url(settings):
    """Áudio da Dra. Karla para o follow-up PÓS-VALOR — paciente sumiu
    depois de receber o preço da consulta. Usa o áudio 1 do roteiro
    ('vi que você se interessou... se ficou dúvida sobre os valores')."""
    if not getattr(settings, "followup_audio_enabled", False):
        return None
    base = (getattr(settings, "audio_base_url", "") or "").rstrip("/")
    if not base:
        return None
    return f"{base}/karla_01.ogg"


def answer_has_value(answer: str) -> bool:
    """True quando a resposta do agente apresentou o valor da consulta
    (bloco de formas de pagamento: R$ junto de Pix/Cartão)."""
    if not answer:
        return False
    a = answer.lower()
    return ("r$" in a) and ("pix" in a or "cartão" in a or "cartao" in a)


def set_pending(redis, ckey: str) -> None:
    """Arma o marcador de follow-up (o agente apresentou o valor)."""
    if not ckey:
        return
    now = time.time()
    if redis is not None:
        try:
            redis.set(_PENDING_PREFIX + ckey, str(now), ex=26 * 3600)
            return
        except Exception:  # noqa: BLE001
            pass
    _MEM_PENDING[ckey] = now


def set_firstcontact(redis, ckey: str) -> None:
    """Arma o marcador de follow-up de PRIMEIRO CONTATO no toque 1 — a Lia
    respondeu e está aguardando o paciente. Se o paciente não responder, a
    cadência de até 3 toques é disparada pelo motor."""
    if not ckey:
        return
    val = f"1:{time.time()}"
    if redis is not None:
        try:
            redis.set(_FIRSTCONTACT_PREFIX + ckey, val, ex=_FC_TTL)
            return
        except Exception:  # noqa: BLE001
            pass
    _MEM_FIRSTCONTACT[ckey] = val


def clear_pending(redis, ckey: str) -> None:
    """Remove os marcadores — o paciente respondeu, não precisa follow-up.
    Limpa tanto o follow-up pós-valor quanto o de primeiro contato."""
    if not ckey:
        return
    if redis is not None:
        try:
            redis.delete(_PENDING_PREFIX + ckey)
            redis.delete(_FIRSTCONTACT_PREFIX + ckey)
            return
        except Exception:  # noqa: BLE001
            pass
    _MEM_PENDING.pop(ckey, None)
    _MEM_FIRSTCONTACT.pop(ckey, None)


@dataclass
class FollowupReport:
    ran: bool
    action: str            # 'sent' | 'dry_run' | 'skipped'
    reason: str = ""
    sent: int = 0
    daily_count: int = 0
    details: list = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "ran": self.ran, "action": self.action, "reason": self.reason,
            "sent": self.sent, "daily_count": self.daily_count,
            "details": self.details,
        }


class FollowupEngine:
    """Motor de follow-up pós-valor. Um tick() processa um lote."""

    def __init__(self, settings, kommo, wa_cloud, store):
        self.s = settings
        self.kommo = kommo
        self.wa_cloud = wa_cloud
        self.store = store
        self._redis = getattr(store, "_redis", None)
        self._mem_count: dict[str, int] = {}

    def _today(self) -> str:
        return datetime.now(_TZ).strftime("%Y-%m-%d")

    def _mode(self) -> str:
        return "dry" if self.s.followup_dry_run else "live"

    def _done_key(self, ckey: str) -> str:
        return f"{_DONE_PREFIX}{self._mode()}:{ckey}"

    def _is_done(self, ckey: str) -> bool:
        if self._redis is not None:
            try:
                return bool(self._redis.exists(self._done_key(ckey)))
            except Exception:  # noqa: BLE001
                pass
        return f"{self._mode()}:{ckey}" in _MEM_DONE

    def _mark_done(self, ckey: str) -> None:
        if self._redis is not None:
            try:
                self._redis.set(self._done_key(ckey), "1", ex=7 * 86400)
                return
            except Exception:  # noqa: BLE001
                pass
        _MEM_DONE.add(f"{self._mode()}:{ckey}")

    def _daily_count(self) -> int:
        day = self._today()
        if self._redis is not None:
            try:
                v = self._redis.get(f"blink:followup:count:{self._mode()}:{day}")
                return int(v) if v else 0
            except Exception:  # noqa: BLE001
                pass
        return self._mem_count.get(f"{self._mode()}:{day}", 0)

    def _incr_daily(self) -> None:
        day = self._today()
        if self._redis is not None:
            try:
                k = f"blink:followup:count:{self._mode()}:{day}"
                self._redis.incr(k)
                self._redis.expire(k, 2 * 86400)
                return
            except Exception:  # noqa: BLE001
                pass
        key = f"{self._mode()}:{day}"
        self._mem_count[key] = self._mem_count.get(key, 0) + 1

    def _pending_items(self) -> list[tuple[str, float]]:
        """Lista (conversation_key, timestamp) dos marcadores pendentes."""
        if self._redis is not None:
            out: list[tuple[str, float]] = []
            try:
                for k in self._redis.scan_iter(match=_PENDING_PREFIX + "*"):
                    key = k.decode() if isinstance(k, bytes) else str(k)
                    ckey = key[len(_PENDING_PREFIX):]
                    v = self._redis.get(k)
                    try:
                        ts = float(v) if v else 0.0
                    except (TypeError, ValueError):
                        ts = 0.0
                    out.append((ckey, ts))
                return out
            except Exception as e:  # noqa: BLE001
                log.warning("followup scan falhou: %s", e)
                return []
        return list(_MEM_PENDING.items())

    # ----------------------- follow-up de primeiro contato

    def _firstcontact_items(self) -> list[tuple[str, int, float]]:
        """Lista (conversation_key, toque, timestamp) dos marcadores."""
        out: list[tuple[str, int, float]] = []
        if self._redis is not None:
            try:
                for k in self._redis.scan_iter(match=_FIRSTCONTACT_PREFIX + "*"):
                    key = k.decode() if isinstance(k, bytes) else str(k)
                    ckey = key[len(_FIRSTCONTACT_PREFIX):]
                    touch, ts = _parse_fc(self._redis.get(k))
                    out.append((ckey, touch, ts))
                return out
            except Exception as e:  # noqa: BLE001
                log.warning("followup firstcontact scan falhou: %s", e)
                return []
        for ck, v in list(_MEM_FIRSTCONTACT.items()):
            touch, ts = _parse_fc(v)
            out.append((ck, touch, ts))
        return out

    def _rearm_firstcontact(self, ckey: str, touch: int) -> None:
        """Reagenda o marcador para o próximo toque da cadência."""
        val = f"{touch}:{time.time()}"
        if self._redis is not None:
            try:
                self._redis.set(_FIRSTCONTACT_PREFIX + ckey, val, ex=_FC_TTL)
                return
            except Exception:  # noqa: BLE001
                pass
        _MEM_FIRSTCONTACT[ckey] = val

    def _fc_done_key(self, ckey: str) -> str:
        return f"{_DONE_PREFIX}fc:{self._mode()}:{ckey}"

    def _fc_is_done(self, ckey: str) -> bool:
        if self._redis is not None:
            try:
                return bool(self._redis.exists(self._fc_done_key(ckey)))
            except Exception:  # noqa: BLE001
                pass
        return f"fc:{self._mode()}:{ckey}" in _MEM_DONE

    def _fc_mark_done(self, ckey: str) -> None:
        if self._redis is not None:
            try:
                self._redis.set(self._fc_done_key(ckey), "1", ex=7 * 86400)
                return
            except Exception:  # noqa: BLE001
                pass
        _MEM_DONE.add(f"fc:{self._mode()}:{ckey}")

    def _clear_firstcontact(self, ckey: str) -> None:
        if self._redis is not None:
            try:
                self._redis.delete(_FIRSTCONTACT_PREFIX + ckey)
                return
            except Exception:  # noqa: BLE001
                pass
        _MEM_FIRSTCONTACT.pop(ckey, None)

    def _tick_firstcontact(self) -> int:
        """Cadência multi-toque de primeiro contato. Cada lead recebe até
        3 toques (≈5min, +24h, +48h), cada um com texto e áudio próprios.
        Quando o paciente responde, clear_pending apaga o marcador e a
        cadência para. Esgotada a cadência, o lead é marcado como done."""
        s = self.s
        if not getattr(s, "followup_firstcontact_enabled", False):
            return 0
        now = time.time()
        min_delay = getattr(s, "followup_firstcontact_min", 5) * 60
        dry = getattr(s, "followup_firstcontact_dry_run", True)
        sent = 0
        for ckey, touch, ts in self._firstcontact_items():
            # Cadência do dia 1, com o lead ainda quente e dentro da
            # janela de 24h: toque 1 ≈ 5 min, toque 2 ≈ 15 min,
            # toque 3 ≈ 30 min (todos ajustáveis por settings/env).
            if touch <= 1:
                delay = min_delay
            elif touch == 2:
                delay = getattr(s, "followup_fc_touch2_min", 15) * 60
            else:
                delay = getattr(s, "followup_fc_touch3_min", 30) * 60
            if (now - ts) < delay:
                continue
            if self._fc_is_done(ckey):
                self._clear_firstcontact(ckey)
                continue
            name, phone = "", ckey
            especialidade = ""
            motivo = ""
            try:
                lead_id = self.kommo.find_lead_id_by_phone(ckey)
                if lead_id:
                    ctx = self.kommo.get_caller_context_by_lead(lead_id)
                    name = ctx.get("name") or ""
                    known = ctx.get("known") or {}
                    especialidade = str(known.get("especialidade") or "")
                    motivo = str(known.get("motivo") or "")
                    p = self.kommo.get_lead_main_phone(lead_id)
                    if p:
                        phone = p
            except Exception as e:  # noqa: BLE001
                log.warning("followup-fc: contexto falhou (%s): %s", ckey, e)
            txt, audio_url = _firstcontact_touch_content(
                touch, _first_name(name), especialidade, motivo, s)

            def _avanca() -> None:
                # Esgotou a cadência → done; senão → reagenda o próximo toque.
                if touch >= _FC_MAX_TOUCH:
                    self._fc_mark_done(ckey)
                    self._clear_firstcontact(ckey)
                else:
                    self._rearm_firstcontact(ckey, touch + 1)

            if dry:
                _avanca()
                sent += 1
                continue
            try:
                self.wa_cloud.send_text(phone, txt)
            except Exception as e:  # noqa: BLE001
                log.warning("followup-fc: envio falhou (%s): %s", ckey, e)
                continue
            if audio_url:
                try:
                    self.wa_cloud.send_audio(phone, audio_url)
                except Exception as e:  # noqa: BLE001
                    log.warning("followup-fc: áudio falhou (%s): %s", ckey, e)
            _avanca()
            sent += 1
        if sent:
            log.info(
                "[FOLLOWUP-FC] %d toque(s) de cadência disparado(s) (dry=%s)",
                sent, dry,
            )
        return sent

    def status(self) -> dict:
        s = self.s
        return {
            "enabled": s.followup_enabled,
            "dry_run": s.followup_dry_run,
            "mode": self._mode(),
            "silence_min": s.followup_silence_min,
            "daily_cap": s.followup_daily_cap,
            "daily_count": self._daily_count(),
            "pending": len(self._pending_items()),
            "template_convenio": s.followup_template_convenio or None,
            "template_particular": s.followup_template_particular or None,
            "firstcontact_enabled": getattr(
                s, "followup_firstcontact_enabled", False),
            "firstcontact_dry_run": getattr(
                s, "followup_firstcontact_dry_run", True),
            "firstcontact_min": getattr(s, "followup_firstcontact_min", 5),
            "firstcontact_pending": len(self._firstcontact_items()),
            "audio_enabled": getattr(s, "followup_audio_enabled", False),
            "audio_base_url": getattr(s, "audio_base_url", "") or None,
            "wa_cloud_ready": self.wa_cloud is not None,
            "kommo_ready": self.kommo is not None,
        }

    def tick(self, force: bool = False) -> FollowupReport:
        s = self.s

        if self.wa_cloud is None:
            return FollowupReport(
                False, "skipped", "WhatsApp Cloud não configurado"
            )
        if self.kommo is None:
            return FollowupReport(False, "skipped", "Kommo não configurado")

        # Follow-up de primeiro contato — roda independente do pós-valor.
        fc_sent = 0
        try:
            fc_sent = self._tick_firstcontact()
        except Exception as e:  # noqa: BLE001
            log.warning("followup-fc tick falhou: %s", e)

        if not s.followup_enabled:
            return FollowupReport(
                True, "sent" if fc_sent else "skipped",
                f"primeiro-contato: {fc_sent} enviado(s); "
                "pós-valor desligado (followup_enabled=false)",
                sent=fc_sent,
            )

        count = self._daily_count()
        if count >= s.followup_daily_cap:
            return FollowupReport(
                False, "skipped",
                f"teto diário atingido ({count}/{s.followup_daily_cap})",
                sent=fc_sent, daily_count=count,
            )

        now = time.time()
        threshold = s.followup_silence_min * 60
        due = [
            (ck, ts) for ck, ts in self._pending_items()
            if (now - ts) >= threshold
        ]
        if not due:
            return FollowupReport(
                True, "sent" if fc_sent else "skipped",
                "nenhum lead no tempo de follow-up pós-valor",
                sent=fc_sent, daily_count=count,
            )

        sent = 0
        details: list = []
        for ckey, _ts in due:
            if count + sent >= s.followup_daily_cap:
                break
            if self._is_done(ckey):
                clear_pending(self._redis, ckey)
                continue

            # Encontra o lead e decide o template (convênio x particular)
            convenio, name, phone = None, "", ckey
            try:
                lead_id = self.kommo.find_lead_id_by_phone(ckey)
                if lead_id:
                    ctx = self.kommo.get_caller_context_by_lead(lead_id)
                    name = ctx.get("name") or ""
                    convenio = (ctx.get("known") or {}).get("convenio")
                    p = self.kommo.get_lead_main_phone(lead_id)
                    if p:
                        phone = p
            except Exception as e:  # noqa: BLE001
                log.warning("followup: contexto do lead falhou (%s): %s", ckey, e)

            tem_convenio = (
                bool(convenio)
                and str(convenio).strip().lower() not in _SEM_CONVENIO
            )
            template = (
                s.followup_template_convenio if tem_convenio
                else s.followup_template_particular
            )
            # Fallback: se o template do caso não está configurado, usa o outro.
            template = (
                template or s.followup_template_particular
                or s.followup_template_convenio
            )
            if not template:
                details.append({"ckey": ckey, "result": "sem template configurado"})
                continue

            # ---- DRY-RUN: registra mas NÃO envia
            if s.followup_dry_run:
                self._mark_done(ckey)
                clear_pending(self._redis, ckey)
                self._incr_daily()
                sent += 1
                details.append({
                    "ckey": ckey, "template": template,
                    "convenio": tem_convenio, "result": "dry_run",
                })
                continue

            # ---- LIVE: envia o template pelo 8133
            try:
                self.wa_cloud.send_template(
                    to=phone,
                    name=template,
                    language=s.followup_template_lang,
                    body_params=[_first_name(name)],
                )
            except Exception as e:  # noqa: BLE001
                details.append(
                    {"ckey": ckey, "result": f"falha: {str(e)[:140]}"}
                )
                continue
            # Follow-up multimídia — áudio da Dra. Karla logo após o
            # template (só envia dentro da janela de 24h; fora dela
            # a falha é silenciosa e o template já foi entregue).
            audio_url = _postvalue_audio_url(s)
            if audio_url:
                try:
                    self.wa_cloud.send_audio(phone, audio_url)
                except Exception as e:  # noqa: BLE001
                    log.warning(
                        "followup: áudio pós-valor falhou (%s): %s", ckey, e)
            self._mark_done(ckey)
            clear_pending(self._redis, ckey)
            self._incr_daily()
            sent += 1
            details.append({
                "ckey": ckey, "template": template,
                "convenio": tem_convenio, "result": "enviado",
            })

        action = "dry_run" if s.followup_dry_run else "sent"
        log.info(
            "[FOLLOWUP] tick (%s): %d pós-valor + %d primeiro-contato",
            action, sent, fc_sent,
        )
        return FollowupReport(
            True, action,
            f"{sent} follow-up(s) pós-valor + {fc_sent} primeiro-contato",
            sent=sent + fc_sent, daily_count=self._daily_count(),
            details=details,
        )
