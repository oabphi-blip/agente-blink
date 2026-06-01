"""Detector e enviador dos 7 áudios do Dr. Fabrício Freitas.

Catálogo completo + gatilhos: `lia-atendimento-blink/references/audios_dr_fabricio.md`.

Fluxo:
1. Lia escreve resposta com marcador `[AUDIO:audio_id]` no final.
2. `detectar_marcador(text)` extrai o ID.
3. `pode_enviar_audio(convo_key)` checa guardas (janela 24h, limite,
   preferência do paciente).
4. Se OK → envia texto SEM marcador + URL do áudio em sequência.
5. Se bloqueado → envia só o texto SEM marcador.

Hospedagem: `https://blink-agent.6prkfn.easypanel.host/static/audios/dr_fabricio/{filename}`.
Os arquivos físicos vão pra `voice_agent/static/audios/dr_fabricio/` no deploy.

Toggle: `AUDIOS_FABRICIO_ENABLED` (default `1` — quando catálogo upload OK).
"""
from __future__ import annotations

import logging
import os
import re
import time
from dataclasses import dataclass
from typing import Optional

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Catálogo — IDs válidos + arquivo + gatilho documentado
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AudioFabricio:
    id: str
    arquivo: str          # nome do mp3 hospedado
    gatilho_humano: str   # descrição pro KB
    etapa: str            # E1/E3/E7/etc


_CATALOGO: dict[str, AudioFabricio] = {
    a.id: a for a in [
        AudioFabricio(
            id="audio_1_dr_fabricio_freitas",
            arquivo="audio_1_dr_fabricio_freitas.mp3",
            gatilho_humano="Paciente novo mencionou Dr. Fabrício OU catarata",
            etapa="E3",
        ),
        AudioFabricio(
            id="audio_2_preciso_cuidar_disso_agora",
            arquivo="audio_2_preciso_cuidar_disso_agora.mp3",
            gatilho_humano="Paciente disse 'vou pensar', 'está caro' APÓS valor",
            etapa="E7",
        ),
        AudioFabricio(
            id="audio_3_retomada_parou_de_responder",
            arquivo="audio_3_retomada_parou_de_responder.mp3",
            gatilho_humano="NUNCA enviado pela Lia — só motor follow-up 12-23h",
            etapa="Follow-up",
        ),
        AudioFabricio(
            id="audio_4_convite_para_agendar",
            arquivo="audio_4_convite_para_agendar.mp3",
            gatilho_humano="Paciente superou objeção (respondeu OK ao audio 2)",
            etapa="E7",
        ),
        AudioFabricio(
            id="audio_5_interesse_nas_lentes",
            arquivo="audio_5_interesse_nas_lentes.mp3",
            gatilho_humano="Paciente mencionou LIO/lente premium/multifocal",
            etapa="E3",
        ),
        AudioFabricio(
            id="audio_6_medo_da_cirurgia",
            arquivo="audio_6_medo_da_cirurgia.mp3",
            gatilho_humano="Paciente disse 'tenho medo', 'fico com receio'",
            etapa="E3",
        ),
        AudioFabricio(
            id="audio_7_o_que_e_avaliacao",
            arquivo="audio_7_o_que_e_avaliacao.mp3",
            gatilho_humano="Paciente perguntou 'como funciona a avaliação?'",
            etapa="E3",
        ),
    ]
}


# IDs proibidos da Lia gerar livremente (só motor follow-up dispara)
_BLOQUEADOS_PARA_LIA: frozenset[str] = frozenset({
    "audio_3_retomada_parou_de_responder",
})


# ---------------------------------------------------------------------------
# Detecção e limpeza do marcador
# ---------------------------------------------------------------------------

_MARCADOR_REGEX = re.compile(
    r"\[AUDIO:\s*([a-z0-9_]+)\s*\]",
    re.IGNORECASE,
)


def detectar_marcador(texto: str) -> Optional[str]:
    """Devolve o audio_id se houver marcador válido NO catálogo E permitido."""
    if not texto:
        return None
    matches = _MARCADOR_REGEX.findall(texto)
    if not matches:
        return None
    # KB §60: NUNCA enviar 2 áudios na mesma mensagem
    if len(matches) > 1:
        log.warning(
            "[AUDIOS] Lia gerou %d marcadores na mesma msg — vou ignorar (KB §60)",
            len(matches),
        )
        return None
    audio_id = matches[0].lower()
    if audio_id not in _CATALOGO:
        log.warning(
            "[AUDIOS] marcador inventado: %r (não está no catálogo de 7)",
            audio_id,
        )
        return None
    if audio_id in _BLOQUEADOS_PARA_LIA:
        log.warning(
            "[AUDIOS] Lia tentou enviar %r — só motor follow-up pode",
            audio_id,
        )
        return None
    return audio_id


def limpar_marcador(texto: str) -> str:
    """Remove TODOS os marcadores `[AUDIO:...]` do texto, deixando pronto pra envio."""
    if not texto:
        return texto
    return _MARCADOR_REGEX.sub("", texto).strip()


# ---------------------------------------------------------------------------
# Guardas — janela 24h, limite por conversa, paciente prefere texto
# ---------------------------------------------------------------------------

# Constantes (overridable via env)
_MAX_AUDIOS_POR_CONVERSA = int(os.environ.get("AUDIOS_MAX_POR_CONVERSA") or "3")
_MIN_MENSAGENS_ENTRE_AUDIOS = int(os.environ.get("AUDIOS_MIN_MSGS_ENTRE") or "2")
_JANELA_META_SEG = 23 * 3600  # 23h pra ter margem da janela 24h Meta


@dataclass
class GuardaResultado:
    pode_enviar: bool
    motivo: str
    contador_atual: int = 0


def pode_enviar_audio(
    convo_key: str,
    *,
    redis_client=None,
    last_inbound_ts: Optional[float] = None,
    paciente_prefere_texto: bool = False,
) -> GuardaResultado:
    """Verifica TODAS as guardas. Retorna GuardaResultado.

    Args:
      convo_key: chave da conversa (telefone E.164 normalizado)
      redis_client: pra ler contador `blink:audios_fabricio:<convo>`
      last_inbound_ts: timestamp epoch da última msg DO paciente
      paciente_prefere_texto: bool do E1 ("escolheu texto")
    """
    if paciente_prefere_texto:
        return GuardaResultado(False, "paciente prefere texto (E1)")

    # Janela Meta 24h
    if last_inbound_ts is not None:
        idle = time.time() - last_inbound_ts
        if idle > _JANELA_META_SEG:
            return GuardaResultado(
                False,
                f"janela Meta expirou (idle={int(idle)}s > {_JANELA_META_SEG}s)",
            )

    # Limite por conversa (contador em Redis)
    contador = 0
    if redis_client is not None:
        try:
            key = f"blink:audios_fabricio:{convo_key}"
            raw = redis_client.get(key)
            if raw:
                contador = int(raw.decode() if isinstance(raw, bytes) else raw)
        except Exception as e:  # noqa: BLE001
            log.warning("[AUDIOS] redis ler contador falhou: %s", e)

    if contador >= _MAX_AUDIOS_POR_CONVERSA:
        return GuardaResultado(
            False,
            f"limite por conversa atingido ({contador}/{_MAX_AUDIOS_POR_CONVERSA})",
            contador_atual=contador,
        )

    return GuardaResultado(True, "ok", contador_atual=contador)


def incrementar_contador(convo_key: str, redis_client=None) -> int:
    """Incrementa o contador em Redis (TTL 7 dias). Retorna novo valor."""
    if redis_client is None:
        return 0
    try:
        key = f"blink:audios_fabricio:{convo_key}"
        novo = redis_client.incr(key)
        redis_client.expire(key, 7 * 24 * 3600)
        return int(novo)
    except Exception as e:  # noqa: BLE001
        log.warning("[AUDIOS] redis incrementar falhou: %s", e)
        return 0


# ---------------------------------------------------------------------------
# URL pública do áudio
# ---------------------------------------------------------------------------

def url_audio(audio_id: str) -> Optional[str]:
    """URL pública pra `wa_cloud.send_audio(url)`."""
    a = _CATALOGO.get(audio_id)
    if not a:
        return None
    base = (
        os.environ.get("AUDIO_BASE_URL")
        or "https://blink-agent.6prkfn.easypanel.host/static/audios/dr_fabricio"
    ).rstrip("/")
    return f"{base}/{a.arquivo}"


def info_audio(audio_id: str) -> Optional[AudioFabricio]:
    """Retorna metadado do áudio ou None."""
    return _CATALOGO.get(audio_id)


def listar_catalogo() -> list[AudioFabricio]:
    """Devolve os 7 áudios disponíveis (pra logging / health check)."""
    return list(_CATALOGO.values())


# ---------------------------------------------------------------------------
# Toggle global
# ---------------------------------------------------------------------------

def audios_habilitados() -> bool:
    """Default ON. Pra desabilitar antes dos arquivos físicos subirem:
    `AUDIOS_FABRICIO_ENABLED=0`.
    """
    valor = (os.environ.get("AUDIOS_FABRICIO_ENABLED") or "1").lower()
    return valor in ("1", "true", "yes")
