"""
Rotação de Slots com Princípio da Escassez (Bug C-80b)
=======================================================
Regra de negócio (Fábio 02/08/2026):
  - Slot ofertado fica "exclusivo" para o lead por 5 minutos.
  - Após 5 min sem confirmação, o slot não é re-ofertado — Lia sempre
    apresenta um slot DIFERENTE, comunicando que a agenda é dinâmica.
  - Após 3 rodadas sem confirmação do paciente → transferência humana.

Chaves Redis:
  blink:slots_oferecidos:{lead_id}          SET com slot_keys já ofertados (TTL 24h)
  blink:slot_ts:{lead_id}:{slot_key}        Timestamp Unix da oferta (TTL 300s = 5 min)
  blink:slot_rodadas:{lead_id}              Contador de rodadas de oferta (TTL 24h)
  blink:slot_escalar:{lead_id}             Flag "escalar humano por slots" (TTL 24h)
"""
import logging
import time

log = logging.getLogger(__name__)

_TTL_SLOT_OFERTA_SEG = 300       # 5 minutos — janela de exclusividade
_TTL_OFERECIDOS_SET_SEG = 86_400  # 24h — memória de slots já ofertados
_TTL_RODADAS_SEG = 86_400         # 24h
_TTL_ESCALAR_SEG = 86_400         # 24h
_MAX_RODADAS = 3                  # após 3 rodadas → humano


def _slot_key(slot: dict) -> str:
    """Chave canônica de um slot: 'YYYY-MM-DDTHH:MM'."""
    data = (slot.get("data_iso") or "").strip()
    hora = (slot.get("hora") or "")[:5].strip()
    if data and hora:
        return f"{data}T{hora}"
    return ""


# ──────────────────────────────────────────────────────────────────────────────
# Escrita
# ──────────────────────────────────────────────────────────────────────────────

def marcar_slots_oferecidos(redis, lead_id: str, slots: list[dict]) -> None:
    """Registra slots como 'já ofertados' nesse lead."""
    if not redis or not lead_id:
        return
    set_key = f"blink:slots_oferecidos:{lead_id}"
    ts_now = str(time.time())
    for s in slots:
        sk = _slot_key(s)
        if not sk:
            continue
        try:
            redis.sadd(set_key, sk)
            redis.expire(set_key, _TTL_OFERECIDOS_SET_SEG)
            # Timestamp da oferta — expira em 5 min (janela de escassez)
            redis.setex(f"blink:slot_ts:{lead_id}:{sk}", _TTL_SLOT_OFERTA_SEG, ts_now)
        except Exception as e:
            log.warning("[SLOT-ROT] marcar_slots_oferecidos falhou: %s", e)


def incrementar_rodada(redis, lead_id: str) -> int:
    """Incrementa contador de rodadas. Retorna novo valor."""
    if not redis or not lead_id:
        return 0
    try:
        key = f"blink:slot_rodadas:{lead_id}"
        val = redis.incr(key)
        redis.expire(key, _TTL_RODADAS_SEG)
        return int(val)
    except Exception as e:
        log.warning("[SLOT-ROT] incrementar_rodada falhou: %s", e)
        return 0


def marcar_escalar(redis, lead_id: str) -> None:
    """Sinaliza que este lead deve ser escalado para humano por esgotamento de slots."""
    if not redis or not lead_id:
        return
    try:
        redis.setex(f"blink:slot_escalar:{lead_id}", _TTL_ESCALAR_SEG, "1")
    except Exception as e:
        log.warning("[SLOT-ROT] marcar_escalar falhou: %s", e)


# ──────────────────────────────────────────────────────────────────────────────
# Leitura / Consulta
# ──────────────────────────────────────────────────────────────────────────────

def slots_ja_oferecidos(redis, lead_id: str) -> set[str]:
    """Retorna SET de slot_keys já ofertados para esse lead."""
    if not redis or not lead_id:
        return set()
    try:
        members = redis.smembers(f"blink:slots_oferecidos:{lead_id}") or set()
        return {(m.decode() if isinstance(m, bytes) else m) for m in members}
    except Exception as e:
        log.warning("[SLOT-ROT] slots_ja_oferecidos falhou: %s", e)
        return set()


def slot_ainda_na_janela(redis, lead_id: str, slot: dict) -> bool:
    """True se o slot foi ofertado há < 5 min (ainda dentro da janela de escassez)."""
    if not redis or not lead_id:
        return False
    sk = _slot_key(slot)
    if not sk:
        return False
    try:
        val = redis.get(f"blink:slot_ts:{lead_id}:{sk}")
        return val is not None  # TTL 300s — se key existe, está dentro da janela
    except Exception as e:
        log.warning("[SLOT-ROT] slot_ainda_na_janela falhou: %s", e)
        return False


def filtrar_slots_novos(redis, lead_id: str, slots: list[dict]) -> list[dict]:
    """Retorna apenas slots NÃO ofertados previamente a este lead."""
    ja = slots_ja_oferecidos(redis, lead_id)
    if not ja:
        return slots
    return [s for s in slots if _slot_key(s) not in ja]


def contar_rodadas(redis, lead_id: str) -> int:
    """Quantas rodadas de oferta já foram feitas a este lead."""
    if not redis or not lead_id:
        return 0
    try:
        val = redis.get(f"blink:slot_rodadas:{lead_id}")
        if val is None:
            return 0
        return int(val.decode() if isinstance(val, bytes) else val)
    except Exception as e:
        log.warning("[SLOT-ROT] contar_rodadas falhou: %s", e)
        return 0


def deve_escalar(redis, lead_id: str) -> bool:
    """True se já foram feitas >= 3 rodadas de oferta sem confirmação."""
    return contar_rodadas(redis, lead_id) >= _MAX_RODADAS


# ──────────────────────────────────────────────────────────────────────────────
# Geração de mensagem
# ──────────────────────────────────────────────────────────────────────────────

def gerar_prefixo_escassez(rodada: int) -> str:
    """Texto de abertura para 2ª+ rodada de oferta, comunicando escassez."""
    if rodada <= 0:
        return ""
    if rodada == 1:
        return (
            "Os horários anteriores já foram preenchidos — nossa agenda é bastante "
            "disputada! 🏃 Separei novas opções pra você agora:\n\n"
        )
    return (
        "A agenda muda rápido e os horários anteriores já não estão mais "
        "disponíveis. Ainda tenho estas opções:\n\n"
    )


def gerar_msg_escalar_humano() -> str:
    """Mensagem ao paciente quando slots se esgotam após 3 rodadas."""
    return (
        "Nossa agenda está muito movimentada agora 😊 "
        "Vou chamar um de nossos especialistas pra te ajudar a encontrar "
        "o melhor horário pessoalmente. Um momento!"
    )


# ──────────────────────────────────────────────────────────────────────────────
# Seleção inteligente de 2 slots (1 manhã + 1 tarde)
# ──────────────────────────────────────────────────────────────────────────────

def selecionar_2_slots_novos(
    redis,
    lead_id: str,
    agenda: list[dict],
) -> list[dict]:
    """Seleciona até 2 slots (1 manhã + 1 tarde) não ofertados anteriormente.

    Ordem de prioridade: mais próximos no tempo primeiro.
    """
    candidatos = filtrar_slots_novos(redis, lead_id, agenda)
    if not candidatos:
        return []

    manha = [s for s in candidatos if _e_manha(s)]
    tarde = [s for s in candidatos if not _e_manha(s)]

    resultado: list[dict] = []
    if manha:
        resultado.append(manha[0])
    if tarde:
        resultado.append(tarde[0])
    if len(resultado) < 2 and len(candidatos) >= 2:
        # Só tem de um turno — pega 2 desse turno
        for s in candidatos:
            if s not in resultado:
                resultado.append(s)
                if len(resultado) == 2:
                    break
    elif len(resultado) < 2 and candidatos:
        pass  # só 1 disponível — OK

    return resultado[:2]


def _e_manha(slot: dict) -> bool:
    hora = (slot.get("hora") or "")[:5]
    try:
        h = int(hora.split(":")[0])
        return h < 12
    except Exception:
        return False
