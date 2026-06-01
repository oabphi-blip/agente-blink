"""State machine da conversa Lia ↔ paciente — persistida em Redis.

Origem (31/05/2026): bug Juliene (lead 24053159). Lia "lembrava" o
estado pelo histórico de mensagens. Quando ctx[agenda] chegou vazio
ela escapou do fluxo porque NÃO HAVIA estado explícito a respeitar.

Esta FSM resolve isso: cada conversa tem 1 estado vivo em Redis. O
prompt diz pro Claude qual estado ele está + qual a NEXT_ACTION
exata. Saídas inválidas são detectadas pelo verificador.

ESTADOS:
  TRIAGEM       — paciente novo, descobrir motivo
  DADOS         — coletando nome completo + data nasc + CPF + convenio
  CONVENIO      — validando convênio aceito ou particular
  AGENDA        — Medware deu slots, oferta concreta
  CONFIRMACAO   — paciente escolheu slot, confirmando dados pra gravar
  GRAVACAO      — executor chama salvar_agendamento (status temporário)
  POS_GRAVACAO  — gravado, próximas mensagens são confirmação/dúvida

TRANSIÇÕES VÁLIDAS:
  TRIAGEM → DADOS → CONVENIO → AGENDA → CONFIRMACAO → GRAVACAO → POS_GRAVACAO

Atalhos PERMITIDOS (paciente bem informado):
  TRIAGEM → DADOS (sempre)
  DADOS → AGENDA (se convenio já ok no Kommo)
  AGENDA → CONFIRMACAO (paciente escolheu na 1ª oferta)
  POS_GRAVACAO → AGENDA (remarcação)

Atalhos PROIBIDOS:
  qualquer estado → AGENDA sem ter DADOS_MINIMOS_OK
  GRAVACAO → AGENDA (gravação não pode retroceder)
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Optional

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enum dos estados (string-based pra serializar fácil em Redis)
# ---------------------------------------------------------------------------

class EstadoConversa(str, Enum):
    TRIAGEM = "TRIAGEM"
    DADOS = "DADOS"
    CONVENIO = "CONVENIO"
    AGENDA = "AGENDA"
    CONFIRMACAO = "CONFIRMACAO"
    GRAVACAO = "GRAVACAO"
    POS_GRAVACAO = "POS_GRAVACAO"


# Transições válidas: chave = origem, valor = conjunto destinos OK
_TRANSICOES_VALIDAS: dict[EstadoConversa, frozenset] = {
    EstadoConversa.TRIAGEM: frozenset({
        EstadoConversa.TRIAGEM,  # repetir é OK (paciente ainda evasivo)
        EstadoConversa.DADOS,
    }),
    EstadoConversa.DADOS: frozenset({
        EstadoConversa.DADOS,
        EstadoConversa.CONVENIO,
        EstadoConversa.AGENDA,  # atalho se convenio ja ok
    }),
    EstadoConversa.CONVENIO: frozenset({
        EstadoConversa.CONVENIO,
        EstadoConversa.AGENDA,
        EstadoConversa.DADOS,  # voltar pra coletar dados que faltaram
    }),
    EstadoConversa.AGENDA: frozenset({
        EstadoConversa.AGENDA,  # paciente recusou os 2, ofereço outros
        EstadoConversa.CONFIRMACAO,
        EstadoConversa.DADOS,   # paciente quer mudar convênio/dados
    }),
    EstadoConversa.CONFIRMACAO: frozenset({
        EstadoConversa.CONFIRMACAO,
        EstadoConversa.GRAVACAO,
        EstadoConversa.AGENDA,  # paciente mudou de ideia sobre slot
    }),
    EstadoConversa.GRAVACAO: frozenset({
        EstadoConversa.GRAVACAO,    # processando
        EstadoConversa.POS_GRAVACAO,
    }),
    EstadoConversa.POS_GRAVACAO: frozenset({
        EstadoConversa.POS_GRAVACAO,
        EstadoConversa.AGENDA,  # remarcação
        EstadoConversa.CONFIRMACAO,
    }),
}


# ---------------------------------------------------------------------------
# Snapshot persistido em Redis
# ---------------------------------------------------------------------------

@dataclass
class SnapshotFSM:
    """Estado salvo no Redis por convo_key."""
    estado: EstadoConversa
    ultima_transicao_ts: float
    tentativas_no_estado: int = 0
    motivo_ultima_transicao: str = ""

    def como_dict(self) -> dict:
        return {
            "estado": self.estado.value,
            "ultima_transicao_ts": self.ultima_transicao_ts,
            "tentativas_no_estado": self.tentativas_no_estado,
            "motivo_ultima_transicao": self.motivo_ultima_transicao,
        }

    @classmethod
    def de_dict(cls, d: dict) -> "SnapshotFSM":
        return cls(
            estado=EstadoConversa(d.get("estado", EstadoConversa.TRIAGEM.value)),
            ultima_transicao_ts=float(d.get("ultima_transicao_ts", 0)),
            tentativas_no_estado=int(d.get("tentativas_no_estado", 0)),
            motivo_ultima_transicao=str(d.get("motivo_ultima_transicao", "")),
        )


# ---------------------------------------------------------------------------
# Validação de transição
# ---------------------------------------------------------------------------

def transicao_valida(origem: EstadoConversa, destino: EstadoConversa) -> bool:
    """True se origem → destino é permitido."""
    return destino in _TRANSICOES_VALIDAS.get(origem, frozenset())


# ---------------------------------------------------------------------------
# Inferência de estado a partir do contexto Kommo
# ---------------------------------------------------------------------------

def inferir_estado_inicial(
    caller_context: Optional[dict],
) -> EstadoConversa:
    """Quando convo é nova ou sem snapshot, infere o estado pelo Kommo.

    Heurística (alinhada com pipeline ATENDE):
      - ja_agendado=True → POS_GRAVACAO
      - status_id=AGENDADO/CONFIRMAR/CONFIRMADO → POS_GRAVACAO
      - status_id=AGENDAR/REAGENDAR → tenta ler dados:
        - dados completos + convenio ok → AGENDA
        - dados incompletos → DADOS
      - status_id=ENTRADA/0-CLASSIFICAR/FRIO → TRIAGEM
      - default → TRIAGEM
    """
    if not caller_context or not caller_context.get("found"):
        return EstadoConversa.TRIAGEM

    if caller_context.get("ja_agendado"):
        return EstadoConversa.POS_GRAVACAO

    status_id = caller_context.get("status_id")
    if status_id in {101507507, 101109455, 106653499}:  # AGENDADO/CONFIRMAR/CONFIRMADO
        return EstadoConversa.POS_GRAVACAO

    if status_id in {102560495, 106184631}:  # AGENDAR / REAGENDAR
        checklist = caller_context.get("checklist_dados_minimos") or {}
        if checklist.get("pronto_para_oferecer_slot"):
            return EstadoConversa.AGENDA
        return EstadoConversa.DADOS

    return EstadoConversa.TRIAGEM


# ---------------------------------------------------------------------------
# Manager — leitura/escrita em Redis
# ---------------------------------------------------------------------------

REDIS_KEY_FMT = "blink:fsm:{convo_key}"
REDIS_TTL_S = 86400 * 30  # 30 dias


class FSMManager:
    """Wrapper Redis pra ler/escrever snapshots FSM por convo_key.

    Falha silenciosa se Redis indisponível — FSM degrada pra
    "infere-do-zero a cada turno" (comportamento atual antes do task #125).
    """

    def __init__(self, redis_client=None):
        self.r = redis_client

    def _key(self, convo_key: str) -> str:
        return REDIS_KEY_FMT.format(convo_key=convo_key)

    def get(self, convo_key: str) -> Optional[SnapshotFSM]:
        if self.r is None:
            return None
        try:
            raw = self.r.get(self._key(convo_key))
            if not raw:
                return None
            data = raw.decode() if isinstance(raw, bytes) else raw
            return SnapshotFSM.de_dict(json.loads(data))
        except Exception as e:  # noqa: BLE001
            log.warning("[FSM get] %s falhou: %s", convo_key, e)
            return None

    def set(self, convo_key: str, snap: SnapshotFSM) -> None:
        if self.r is None:
            return
        try:
            self.r.setex(
                self._key(convo_key),
                REDIS_TTL_S,
                json.dumps(snap.como_dict()),
            )
        except Exception as e:  # noqa: BLE001
            log.warning("[FSM set] %s falhou: %s", convo_key, e)

    def transicionar(
        self,
        convo_key: str,
        novo_estado: EstadoConversa,
        motivo: str = "",
    ) -> tuple[SnapshotFSM, bool]:
        """Tenta mover pra novo_estado. Retorna (snapshot, ok).

        - Se snapshot não existe → cria com `novo_estado` (qualquer
          transição inicial é OK).
        - Se transição inválida → mantém estado antigo, ok=False.
        - Se válida → atualiza, ok=True.
        """
        atual = self.get(convo_key)
        agora = time.time()

        if atual is None:
            novo = SnapshotFSM(
                estado=novo_estado,
                ultima_transicao_ts=agora,
                tentativas_no_estado=1,
                motivo_ultima_transicao=motivo or "inicial",
            )
            self.set(convo_key, novo)
            return novo, True

        if atual.estado == novo_estado:
            # Repetiu estado → conta tentativa, sem registrar transição
            novo = SnapshotFSM(
                estado=atual.estado,
                ultima_transicao_ts=atual.ultima_transicao_ts,
                tentativas_no_estado=atual.tentativas_no_estado + 1,
                motivo_ultima_transicao=atual.motivo_ultima_transicao,
            )
            self.set(convo_key, novo)
            return novo, True

        if not transicao_valida(atual.estado, novo_estado):
            log.warning(
                "[FSM] transição inválida %s → %s convo=%s — mantém atual",
                atual.estado.value, novo_estado.value, convo_key,
            )
            return atual, False

        novo = SnapshotFSM(
            estado=novo_estado,
            ultima_transicao_ts=agora,
            tentativas_no_estado=1,
            motivo_ultima_transicao=motivo or "transição válida",
        )
        self.set(convo_key, novo)
        log.info(
            "[FSM] %s → %s convo=%s motivo=%s",
            atual.estado.value, novo_estado.value, convo_key, motivo,
        )
        return novo, True


# ---------------------------------------------------------------------------
# Bloco descritivo pro system prompt — Claude entende em qual estado está
# ---------------------------------------------------------------------------

_INSTRUCOES_POR_ESTADO: dict[EstadoConversa, str] = {
    EstadoConversa.TRIAGEM: (
        "Você está em TRIAGEM. Saúde o paciente, descubra o MOTIVO "
        "(rotina/sintoma/criança/etc) e a especialidade básica. NÃO "
        "ofereça slot, NÃO peça CPF ainda."
    ),
    EstadoConversa.DADOS: (
        "Você está em COLETA DE DADOS. PEÇA APENAS o que falta da "
        "checklist (nome completo, data nasc, CPF, convênio). Não "
        "ofereça slot AINDA — sem dados não há como gravar Medware."
    ),
    EstadoConversa.CONVENIO: (
        "Você está em CONVÊNIO. Confirme se o convênio do paciente "
        "está na nossa rede ou se segue particular. Use o KB de "
        "convênios pra decidir."
    ),
    EstadoConversa.AGENDA: (
        "Você está em AGENDA. Você tem slots reais no system prompt. "
        "OFEREÇA NO MÁXIMO 2 (escassez). Se paciente recusar, ofereça "
        "outros 2. NUNCA invente caminho 'humano' — sempre slots reais "
        "ou pedido honesto de 1 min."
    ),
    EstadoConversa.CONFIRMACAO: (
        "Você está em CONFIRMAÇÃO. Paciente escolheu um slot. Confirme "
        "EM UMA frase o slot exato (ex.: 'Combinado, terça 02/06 às "
        "09:00 com Doutora Karla'). Essa frase dispara a gravação "
        "Medware. PROIBIDO escrever 'vou verificar com a equipe'."
    ),
    EstadoConversa.GRAVACAO: (
        "Você está em GRAVAÇÃO. A gravação Medware está em execução "
        "em thread separada. Se paciente perguntar 'gravou?', responda "
        "honestamente baseado no STATUS GRAVAÇÃO MEDWARE que está no "
        "prompt. NUNCA invente 'sim, está gravado' sem o status confirmar."
    ),
    EstadoConversa.POS_GRAVACAO: (
        "Você está em PÓS-GRAVAÇÃO. O agendamento JÁ ESTÁ MARCADO. "
        "Responda APENAS à pergunta atual — confirmar presença, dúvida "
        "operacional ou remarcação. NÃO refaça triagem, NÃO ofereça "
        "slots novos, exceto se paciente pedir remarcação explicitamente."
    ),
}


def render_bloco_estado(snap: Optional[SnapshotFSM]) -> str:
    """Bloco injetado no system prompt — Claude sabe seu estado atual."""
    if snap is None:
        return ""
    estado = snap.estado
    instrucao = _INSTRUCOES_POR_ESTADO.get(estado, "")
    return (
        "\n\n----------------------------------------------------------------"
        f"\nESTADO DA CONVERSA — {estado.value}"
        "\n----------------------------------------------------------------"
        f"\n{instrucao}"
        f"\nTentativas neste estado: {snap.tentativas_no_estado}."
        "\n----------------------------------------------------------------"
    )
