"""Carrega configuração do agente a partir de env vars, .env e config.json."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    # OpenAI (Whisper)
    openai_api_key: str
    whisper_model: str

    # Anthropic (Claude — atendimento)
    anthropic_api_key: str
    claude_sonnet_model: str
    claude_haiku_model: str

    # Evolution API
    evolution_base_url: str
    evolution_api_key: str
    evolution_default_instance: str

    # Webhook
    webhook_secret: Optional[str]

    # Agente
    response_language: str
    max_response_chars: int

    # Whitelist de segurança (modo soft launch)
    whitelist_numbers: tuple[str, ...]
    whitelist_strict: bool

    # Kommo CRM (auto-preenchimento de leads)
    kommo_subdomain: str
    kommo_token: str
    kommo_enabled: bool

    # Redis (persistência de histórico de conversa + dedup)
    redis_url: str

    # Medware (sistema de agenda da clínica)
    medware_user: str
    medware_password: str
    medware_enabled: bool

    # Reativação de leads frios (motor — DESLIGADO por padrão)
    # Duas travas: 'enabled' liga o motor; 'dry_run' impede o envio real.
    # Mensagem real só sai com enabled=True E dry_run=False.
    reactivation_enabled: bool = False
    reactivation_dry_run: bool = True
    reactivation_daily_cap: int = 30
    reactivation_min_interval_min: int = 8
    reactivation_hour_start: int = 8
    reactivation_hour_end: int = 18
    reactivation_pipeline_id: int = 8601819
    reactivation_cold_status_ids: tuple[int, ...] = (
        96441724,   # 0-ETAPA ENTRADA
        101508307,  # 1.LEADS FRIO
        102560495,  # 2-AGENDAR
        106184631,  # 3.REAGENDAR
        106184983,  # 5.1-NO-SHOW (ATIVAR)
    )
    reactivation_target_status_id: int = 102560495  # 2-AGENDAR
    # Canal da reativação: se reactivation_template_name estiver preenchido
    # E o WhatsApp Cloud estiver ativo, a reativação sai via TEMPLATE pelo
    # 8133 (oficial). Sem template configurado, cai no Evolution (0710).
    reactivation_template_name: str = ""
    reactivation_template_lang: str = "pt_BR"
    slack_webhook_url: str = ""
    # Disparo de unificação (broadcast do aviso de número único 8133).
    # Duas travas: enabled liga o motor; dry_run impede o envio real.
    broadcast_enabled: bool = False
    broadcast_dry_run: bool = True
    broadcast_daily_cap: int = 200
    broadcast_batch_size: int = 25
    broadcast_hour_start: int = 8
    broadcast_hour_end: int = 20
    broadcast_template_name: str = "atendimento_unificado_oficial"
    broadcast_template_lang: str = "pt_BR"
    # Follow-up pós-valor — dispara um template quando o paciente some
    # depois de o agente apresentar o valor. Duas travas: enabled e dry_run.
    followup_enabled: bool = False
    followup_dry_run: bool = True
    followup_silence_min: int = 15
    followup_daily_cap: int = 100
    followup_template_convenio: str = ""
    followup_template_particular: str = "1078_sem_resposta_valor_consulta_xs9jqe"
    followup_template_lang: str = "pt_BR"

    # Reconciliação de etapas (Medware × Kommo) — duas travas, igual reativação.
    reconciliation_enabled: bool = False
    reconciliation_dry_run: bool = True

    # Carimbo do campo "ATIVADO IA?" no Kommo — duas travas, igual reativação.
    ia_status_enabled: bool = False
    ia_status_dry_run: bool = True
    # Quando true, roda o backfill do campo "ATIVADO IA?" automaticamente
    # na inicialização do app (cada réplica roda; é idempotente).
    ia_status_backfill_on_boot: bool = False

    # Convivência humano × agente: minutos de silêncio do agente após um
    # humano enviar mensagem no chat do Kommo. Janela curta (1 min) — só um
    # respiro para não colidir no mesmo instante; depois o agente retoma.
    # Para manter o atendimento humano de propósito, mover o lead para a
    # etapa "0-ATENDIMENTO HUMANO" (ver kommo.ST_AGENT_OFF).
    agent_handoff_window_min: int = 1

    # WhatsApp Cloud API (Meta) — canal do número OFICIAL, direto (sem Kommo)
    whatsapp_cloud_token: str = ""
    whatsapp_cloud_phone_number_id: str = ""
    whatsapp_cloud_waba_id: str = ""
    whatsapp_cloud_verify_token: str = ""
    whatsapp_cloud_api_version: str = "v21.0"
    whatsapp_cloud_enabled: bool = False

    # Asaas — geração de links de pagamento da consulta.
    asaas_enabled: bool = False
    asaas_api_key: str = ""
    asaas_env: str = "production"  # "production" ou "sandbox"

    @classmethod
    def load(cls) -> "Settings":
        load_dotenv()
        cfg = _load_config_json()
        oai = cfg.get("openai", {}) if isinstance(cfg, dict) else {}
        anthropic = cfg.get("anthropic", {}) if isinstance(cfg, dict) else {}
        ev = cfg.get("evolution_api", {}) if isinstance(cfg, dict) else {}
        kommo_cfg = cfg.get("kommo", {}) if isinstance(cfg, dict) else {}
        agent = cfg.get("agent", {}) if isinstance(cfg, dict) else {}

        openai_api_key = os.getenv("OPENAI_API_KEY") or oai.get("api_key", "")
        anthropic_api_key = os.getenv("ANTHROPIC_API_KEY") or anthropic.get("api_key", "")
        evolution_base = os.getenv("EVOLUTION_BASE_URL") or ev.get("base_url", "")
        evolution_key = os.getenv("EVOLUTION_API_KEY") or ev.get("api_key", "")
        evolution_inst = os.getenv("EVOLUTION_INSTANCE") or ev.get("instance", "")

        # Whitelist via env var (CSV) ou config.json
        env_wl = os.getenv("WHITELIST_NUMBERS", "")
        if env_wl:
            wl = tuple(n.strip() for n in env_wl.split(",") if n.strip())
        else:
            wl = tuple(agent.get("whitelist_numbers", []))

        missing = []
        if not openai_api_key:
            missing.append("OPENAI_API_KEY (Whisper)")
        if not anthropic_api_key:
            missing.append("ANTHROPIC_API_KEY (Claude)")
        if not evolution_base:
            missing.append("EVOLUTION_BASE_URL")
        if not evolution_key:
            missing.append("EVOLUTION_API_KEY")
        if not evolution_inst:
            missing.append("EVOLUTION_INSTANCE")

        if missing:
            raise RuntimeError(
                "Configuração ausente:\n  - " + "\n  - ".join(missing)
            )

        # Kommo (opcional — desabilitado se não houver token)
        kommo_subdomain = os.getenv("KOMMO_SUBDOMAIN") or kommo_cfg.get("subdomain", "")
        kommo_token = os.getenv("KOMMO_TOKEN") or kommo_cfg.get("token", "")
        kommo_enabled = bool(kommo_subdomain and kommo_token)

        # Redis (opcional — fallback em memória se ausente)
        redis_url = os.getenv("REDIS_URL") or cfg.get("redis", {}).get("url", "")

        # Medware (opcional)
        mw_cfg = cfg.get("medware", {}) if isinstance(cfg, dict) else {}
        medware_user = os.getenv("MEDWARE_USER") or mw_cfg.get("user", "")
        medware_password = os.getenv("MEDWARE_PASSWORD") or mw_cfg.get("password", "")
        medware_enabled = bool(medware_user and medware_password)

        # Reativação de leads frios (opcional — tudo via env var)
        rc = cfg.get("reactivation", {}) if isinstance(cfg, dict) else {}

        def _flag(env_name: str, cfg_key: str, default: bool) -> bool:
            raw = os.getenv(env_name)
            if raw is not None:
                return raw.strip().lower() in ("1", "true", "yes", "sim")
            return bool(rc.get(cfg_key, default))

        def _intval(env_name: str, cfg_key: str, default: int) -> int:
            raw = os.getenv(env_name) or rc.get(cfg_key)
            try:
                return int(raw) if raw not in (None, "") else default
            except (TypeError, ValueError):
                return default

        cold_default = (96441724, 101508307, 102560495, 106184631, 106184983)
        cold_raw = os.getenv("REACTIVATION_COLD_STATUS_IDS") or rc.get("cold_status_ids")
        if isinstance(cold_raw, str) and cold_raw.strip():
            cold_ids = tuple(int(x) for x in cold_raw.split(",") if x.strip().isdigit())
        elif isinstance(cold_raw, (list, tuple)) and cold_raw:
            cold_ids = tuple(int(x) for x in cold_raw)
        else:
            cold_ids = cold_default

        reactivation_enabled = _flag("REACTIVATION_ENABLED", "enabled", False)
        reactivation_dry_run = _flag("REACTIVATION_DRY_RUN", "dry_run", True)
        reconciliation_enabled = _flag(
            "RECONCILIATION_ENABLED", "reconciliation_enabled", False)
        reconciliation_dry_run = _flag(
            "RECONCILIATION_DRY_RUN", "reconciliation_dry_run", True)
        ia_status_enabled = _flag(
            "IA_STATUS_ENABLED", "ia_status_enabled", False)
        ia_status_dry_run = _flag(
            "IA_STATUS_DRY_RUN", "ia_status_dry_run", True)
        ia_status_backfill_on_boot = _flag(
            "IA_STATUS_BACKFILL_ON_BOOT", "ia_status_backfill_on_boot", False)
        agent_handoff_window_min = _intval(
            "AGENT_HANDOFF_WINDOW_MIN", "agent_handoff_window_min", 1)
        reactivation_daily_cap = _intval("REACTIVATION_DAILY_CAP", "daily_cap", 30)
        reactivation_min_interval = _intval("REACTIVATION_MIN_INTERVAL_MIN", "min_interval_min", 8)
        reactivation_hour_start = _intval("REACTIVATION_HOUR_START", "hour_start", 8)
        reactivation_hour_end = _intval("REACTIVATION_HOUR_END", "hour_end", 18)
        reactivation_pipeline_id = _intval("REACTIVATION_PIPELINE_ID", "pipeline_id", 8601819)
        reactivation_target_status = _intval("REACTIVATION_TARGET_STATUS_ID", "target_status_id", 102560495)
        slack_webhook_url = os.getenv("SLACK_WEBHOOK_URL") or rc.get("slack_webhook_url", "") or ""
        reactivation_template_name = (
            os.getenv("REACTIVATION_TEMPLATE_NAME") or rc.get("template_name", "") or ""
        )
        reactivation_template_lang = (
            os.getenv("REACTIVATION_TEMPLATE_LANG") or rc.get("template_lang", "pt_BR") or "pt_BR"
        )
        broadcast_enabled = _flag("BROADCAST_ENABLED", "broadcast_enabled", False)
        broadcast_dry_run = _flag("BROADCAST_DRY_RUN", "broadcast_dry_run", True)
        broadcast_daily_cap = _intval("BROADCAST_DAILY_CAP", "broadcast_daily_cap", 200)
        broadcast_batch_size = _intval("BROADCAST_BATCH_SIZE", "broadcast_batch_size", 25)
        broadcast_hour_start = _intval("BROADCAST_HOUR_START", "broadcast_hour_start", 8)
        broadcast_hour_end = _intval("BROADCAST_HOUR_END", "broadcast_hour_end", 20)
        broadcast_template_name = (
            os.getenv("BROADCAST_TEMPLATE_NAME") or "atendimento_unificado_oficial"
        )
        broadcast_template_lang = os.getenv("BROADCAST_TEMPLATE_LANG") or "pt_BR"
        followup_enabled = _flag("FOLLOWUP_ENABLED", "followup_enabled", False)
        followup_dry_run = _flag("FOLLOWUP_DRY_RUN", "followup_dry_run", True)
        followup_silence_min = _intval("FOLLOWUP_SILENCE_MIN", "followup_silence_min", 15)
        followup_daily_cap = _intval("FOLLOWUP_DAILY_CAP", "followup_daily_cap", 100)
        followup_template_convenio = os.getenv("FOLLOWUP_TEMPLATE_CONVENIO") or ""
        followup_template_particular = (
            os.getenv("FOLLOWUP_TEMPLATE_PARTICULAR")
            or "1078_sem_resposta_valor_consulta_xs9jqe"
        )
        followup_template_lang = os.getenv("FOLLOWUP_TEMPLATE_LANG") or "pt_BR"

        # Asaas — links de pagamento da consulta.
        asaas_enabled = _flag("ASAAS_ENABLED", "asaas_enabled", False)
        asaas_api_key = os.getenv("ASAAS_API_KEY") or rc.get("asaas_api_key", "") or ""
        asaas_env = os.getenv("ASAAS_ENV") or rc.get("asaas_env", "production") or "production"

        # WhatsApp Cloud API (Meta) — canal do número oficial
        wac = cfg.get("whatsapp_cloud", {}) if isinstance(cfg, dict) else {}
        whatsapp_cloud_token = os.getenv("WHATSAPP_CLOUD_TOKEN") or wac.get("token", "")
        whatsapp_cloud_phone_number_id = (
            os.getenv("WHATSAPP_CLOUD_PHONE_NUMBER_ID") or wac.get("phone_number_id", "")
        )
        whatsapp_cloud_waba_id = (
            os.getenv("WHATSAPP_CLOUD_WABA_ID") or wac.get("waba_id", "")
        )
        whatsapp_cloud_verify_token = (
            os.getenv("WHATSAPP_CLOUD_VERIFY_TOKEN") or wac.get("verify_token", "")
        )
        whatsapp_cloud_api_version = (
            os.getenv("WHATSAPP_CLOUD_API_VERSION") or wac.get("api_version", "v21.0")
        )
        whatsapp_cloud_enabled = bool(
            whatsapp_cloud_token and whatsapp_cloud_phone_number_id
        )

        return cls(
            openai_api_key=openai_api_key,
            whisper_model=os.getenv("WHISPER_MODEL") or agent.get("whisper_model", "whisper-1"),
            anthropic_api_key=anthropic_api_key,
            claude_sonnet_model=os.getenv("CLAUDE_SONNET_MODEL") or agent.get("claude_sonnet_model", "claude-sonnet-4-5"),
            claude_haiku_model=os.getenv("CLAUDE_HAIKU_MODEL") or agent.get("claude_haiku_model", "claude-haiku-4-5-20251001"),
            evolution_base_url=evolution_base.rstrip("/"),
            evolution_api_key=evolution_key,
            evolution_default_instance=evolution_inst,
            webhook_secret=os.getenv("WEBHOOK_SECRET") or None,
            response_language=os.getenv("RESPONSE_LANGUAGE", "pt"),
            max_response_chars=int(os.getenv("MAX_RESPONSE_CHARS", "1200")),
            whitelist_numbers=wl,
            whitelist_strict=(os.getenv("WHITELIST_STRICT", str(agent.get("whitelist_strict", True))).lower() == "true"),
            kommo_subdomain=kommo_subdomain,
            kommo_token=kommo_token,
            kommo_enabled=kommo_enabled,
            redis_url=redis_url,
            medware_user=medware_user,
            medware_password=medware_password,
            medware_enabled=medware_enabled,
            reactivation_enabled=reactivation_enabled,
            reactivation_dry_run=reactivation_dry_run,
            reconciliation_enabled=reconciliation_enabled,
            reconciliation_dry_run=reconciliation_dry_run,
            ia_status_enabled=ia_status_enabled,
            ia_status_dry_run=ia_status_dry_run,
            ia_status_backfill_on_boot=ia_status_backfill_on_boot,
            agent_handoff_window_min=agent_handoff_window_min,
            reactivation_daily_cap=reactivation_daily_cap,
            reactivation_min_interval_min=reactivation_min_interval,
            reactivation_hour_start=reactivation_hour_start,
            reactivation_hour_end=reactivation_hour_end,
            reactivation_pipeline_id=reactivation_pipeline_id,
            reactivation_cold_status_ids=cold_ids,
            reactivation_target_status_id=reactivation_target_status,
            reactivation_template_name=reactivation_template_name,
            reactivation_template_lang=reactivation_template_lang,
            slack_webhook_url=slack_webhook_url,
            broadcast_enabled=broadcast_enabled,
            broadcast_dry_run=broadcast_dry_run,
            broadcast_daily_cap=broadcast_daily_cap,
            broadcast_batch_size=broadcast_batch_size,
            broadcast_hour_start=broadcast_hour_start,
            broadcast_hour_end=broadcast_hour_end,
            broadcast_template_name=broadcast_template_name,
            broadcast_template_lang=broadcast_template_lang,
            followup_enabled=followup_enabled,
            followup_dry_run=followup_dry_run,
            followup_silence_min=followup_silence_min,
            followup_daily_cap=followup_daily_cap,
            followup_template_convenio=followup_template_convenio,
            followup_template_particular=followup_template_particular,
            followup_template_lang=followup_template_lang,
            whatsapp_cloud_token=whatsapp_cloud_token,
            whatsapp_cloud_phone_number_id=whatsapp_cloud_phone_number_id,
            whatsapp_cloud_waba_id=whatsapp_cloud_waba_id,
            whatsapp_cloud_verify_token=whatsapp_cloud_verify_token,
            whatsapp_cloud_api_version=whatsapp_cloud_api_version,
            whatsapp_cloud_enabled=whatsapp_cloud_enabled,
            asaas_enabled=asaas_enabled,
            asaas_api_key=asaas_api_key,
            asaas_env=asaas_env,
        )

    def is_whitelisted(self, number: str) -> bool:
        """Verifica se um número está na whitelist (modo soft launch).

        Se whitelist_strict=False ou whitelist vazia, todos são permitidos.
        Compara variantes BR (com/sem o 9 extra de celular), porque a Evolution
        às vezes entrega 12 dígitos e às vezes 13.
        """
        if not self.whitelist_strict or not self.whitelist_numbers:
            return True
        candidate = _br_variants(number)
        allowed: set[str] = set()
        for wl in self.whitelist_numbers:
            allowed.update(_br_variants(wl))
        return bool(candidate & allowed)


def _normalize_number(number: str) -> str:
    if not number:
        return number
    if "@" in number:
        number = number.split("@", 1)[0]
    return number.lstrip("+").replace(" ", "").replace("-", "").strip()


def _br_variants(number: str) -> set[str]:
    """Gera variantes BR (com e sem o 9 extra) para um número.

    No Brasil, celulares modernos têm o 9 após o DDD:
      - 5561996830710 (13 dígitos, com 9)
      - 556196830710  (12 dígitos, sem 9)
    A Evolution às vezes entrega um, às vezes outro. Retornamos AMBAS.
    """
    n = _normalize_number(number)
    if not n:
        return set()
    out = {n}
    if n.startswith("55") and len(n) in (12, 13):
        ddd = n[2:4]
        rest = n[4:]
        if len(n) == 13 and rest.startswith("9"):
            out.add("55" + ddd + rest[1:])
        elif len(n) == 12:
            out.add("55" + ddd + "9" + rest)
    return out


def _load_config_json() -> dict:
    for path in (
        Path.cwd() / "config.json",
        Path(__file__).resolve().parent.parent / "config.json",
    ):
        if path.is_file():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                pass
    return {}
