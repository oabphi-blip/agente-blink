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
