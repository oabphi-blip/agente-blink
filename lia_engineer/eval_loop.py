"""Eval Loop — mede e evolui o desempenho da Lia continuamente.

Diferente do detect_bugs (que pega ERROS individuais), o eval_loop mede
**conversão** e **qualidade percebida**. Detecta degradação sistêmica
mesmo quando nenhum bug individual aparece.

Rodado 1x/dia via cron. Compara janelas (hoje vs ontem vs semana passada).

Métricas-chave:

    1. Taxa de conversão por funil
       lead criado → lead ativo (paciente respondeu) → ofereceu slot →
       paciente aceitou → dados completos → gravado Medware → consulta realizada
       Cada etapa tem TAXA. Se taxa cai >15% em 24h → alarme + análise.

    2. Tempo médio por etapa
       Etapa lenta = fricção. Lia perdendo turnos = leak de conversão.

    3. No-show rate
       Pacientes agendados que não compareceram. Se subir, política sinal
       precisa endurecer ou comunicação D-1/D-0 precisa mudar.

    4. Distribuição de bugs por categoria
       Se Cat 1 (race condition) sobe, foco em pipeline lock.
       Se Cat 6 (formulário) sobe, foco em "1 pergunta/msg".

    5. NPS / satisfação pós-consulta
       Coletado via mensagem D+1. Se cair → revisar tom da Lia.

A/B test de prompts (próxima fase):

    - 50% conversas turn em variante A (prompt atual)
    - 50% conversas em variante B (prompt experimental)
    - Após 100 turnos cada → comparar taxa conversão
    - Variante vencedora vira default. Loop infinito de melhoria.

Cosmoética: tudo medido honestamente, sem cherry-pick. Métricas que
caíram aparecem no relatório com a mesma proeminência das que subiram.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional


# ────────────────────────────────────────────────────────────────────────
# Modelo de métricas
# ────────────────────────────────────────────────────────────────────────

@dataclass
class FunilMetricas:
    """Snapshot de uma janela de tempo."""

    janela_inicio: datetime
    janela_fim: datetime
    leads_criados: int = 0
    leads_responderam: int = 0  # paciente mandou ≥ 1 msg
    leads_dados_minimos: int = 0  # nome + nasc + convênio
    leads_oferecidos_slot: int = 0
    leads_aceitaram_slot: int = 0
    leads_gravados_medware: int = 0
    leads_compareceram: int = 0  # consulta realizada
    no_shows: int = 0

    def taxa(self, numerador: int, denominador: int) -> float:
        if denominador == 0:
            return 0.0
        return round(100 * numerador / denominador, 1)

    def funil_taxas(self) -> Dict[str, float]:
        """Taxa percentual de cada etapa do funil."""
        return {
            "responderam_de_criados": self.taxa(self.leads_responderam, self.leads_criados),
            "dados_de_responderam": self.taxa(self.leads_dados_minimos, self.leads_responderam),
            "oferta_de_dados": self.taxa(self.leads_oferecidos_slot, self.leads_dados_minimos),
            "aceite_de_oferta": self.taxa(self.leads_aceitaram_slot, self.leads_oferecidos_slot),
            "gravado_de_aceite": self.taxa(self.leads_gravados_medware, self.leads_aceitaram_slot),
            "comparecimento_de_gravado": self.taxa(self.leads_compareceram, self.leads_gravados_medware),
            "no_show_rate": self.taxa(self.no_shows, self.leads_gravados_medware),
            "conversao_total_criado_compareceu": self.taxa(self.leads_compareceram, self.leads_criados),
        }


@dataclass
class ComparacaoJanelas:
    """Comparação entre 2 janelas. Detecta DEGRADAÇÃO ou MELHORIA."""

    atual: FunilMetricas
    anterior: FunilMetricas
    limiar_degradacao_pct: float = 15.0  # >15% queda = alarme

    def degradacoes_detectadas(self) -> List[Dict]:
        """Lista das métricas que pioraram > limiar."""
        atual_taxas = self.atual.funil_taxas()
        ant_taxas = self.anterior.funil_taxas()
        degradacoes = []
        for chave, valor_atual in atual_taxas.items():
            valor_ant = ant_taxas.get(chave, 0)
            if valor_ant == 0:
                continue
            # "no_show_rate" é invertido — subir = degradar
            inverso = chave in ("no_show_rate",)
            queda_pct = (valor_atual - valor_ant) / valor_ant * 100
            piorou = (queda_pct < -self.limiar_degradacao_pct) if not inverso else (queda_pct > self.limiar_degradacao_pct)
            if piorou:
                degradacoes.append({
                    "metrica": chave,
                    "valor_atual": valor_atual,
                    "valor_anterior": valor_ant,
                    "variacao_pct": round(queda_pct, 1),
                })
        return degradacoes

    def melhorias_detectadas(self) -> List[Dict]:
        """Lista das métricas que melhoraram > limiar."""
        atual_taxas = self.atual.funil_taxas()
        ant_taxas = self.anterior.funil_taxas()
        melhorias = []
        for chave, valor_atual in atual_taxas.items():
            valor_ant = ant_taxas.get(chave, 0)
            if valor_ant == 0:
                continue
            inverso = chave in ("no_show_rate",)
            variacao_pct = (valor_atual - valor_ant) / valor_ant * 100
            melhorou = (variacao_pct > self.limiar_degradacao_pct) if not inverso else (variacao_pct < -self.limiar_degradacao_pct)
            if melhorou:
                melhorias.append({
                    "metrica": chave,
                    "valor_atual": valor_atual,
                    "valor_anterior": valor_ant,
                    "variacao_pct": round(variacao_pct, 1),
                })
        return melhorias


# ────────────────────────────────────────────────────────────────────────
# Coleta de métricas
# ────────────────────────────────────────────────────────────────────────

# Status IDs do funil ATENDE (Blink Oftalmologia) — fonte: CLAUDE.md seção 4
_STATUS_FUNIL = {
    "responderam": [
        96441724,    # 0-ETAPA ENTRADA
        106919911,   # 0-a classificar
        101508307,   # 2.LEADS FRIO
        102560495,   # 3-AGENDAR
        106184631,   # 4.REAGENDAR
        106184983,   # 7.1-NO-SHOW
        106563343,   # 1-ATENDIMENTO HUMANO
        101507507,   # 5-AGENDADO
        101109455,   # 6-CONFIRMAR
        106653499,   # 7.CONFIRMADO
        91486864,    # 8-REALIZADO
    ],
    "gravados_medware": [101507507, 101109455, 106653499, 91486864],
    "compareceram": [91486864],  # 8-REALIZADO CONSULTA
    "no_show": [106184983],       # 7.1-NO-SHOW (ATIVAR)
}

# Custom field IDs (CLAUDE.md seção 5)
_FIELD_NOME_PACIENTE = 1255723  # 1.NOME PACIENTE (proxy de dados mínimos)
_FIELD_CONVENIO = 853206
_FIELD_DIA_CONSULTA = 1255723  # 1.DIA CONSULTA


def coletar_metricas_janela(
    kommo_client,
    inicio: datetime,
    fim: datetime,
    pipeline_id: int = 8601819,  # funil ATENDE
) -> FunilMetricas:
    """Coleta métricas de uma janela de tempo via Kommo API REAL.

    Lê leads criados dentro da janela, classifica por status_id final
    pra inferir até onde o funil chegou. Pra "responderam" + "dados
    completos" usa proxies (status >= 0-classificar = respondeu;
    custom_field nome_paciente preenchido = dados mínimos).

    Args:
        kommo_client: instância de KommoClient (precisa ter método
            `search_leads(filter_query, with_=...)`).
        inicio: timestamp UTC da janela.
        fim: timestamp UTC.
        pipeline_id: padrão funil ATENDE Blink.

    Returns:
        FunilMetricas preenchido. Em caso de erro, retorna métricas
        zeradas (não None) pra eval_loop continuar funcionando.
    """
    metricas = FunilMetricas(janela_inicio=inicio, janela_fim=fim)

    try:
        ts_from = int(inicio.timestamp())
        ts_to = int(fim.timestamp())
        # Busca leads criados na janela via método list_leads_by_status_range
        # ou search com filter custom. Aqui usamos abordagem genérica.
        leads = []
        if hasattr(kommo_client, "search_leads_by_window"):
            leads = kommo_client.search_leads_by_window(
                pipeline_id=pipeline_id, ts_from=ts_from, ts_to=ts_to,
            )
        elif hasattr(kommo_client, "search_leads"):
            leads = kommo_client.search_leads(
                filter_query={
                    "filter[pipeline_id]": pipeline_id,
                    "filter[created_at][from]": ts_from,
                    "filter[created_at][to]": ts_to,
                },
                limit=500,
            )
        # Se KommoClient não tem nenhum método compatível, retorna zerado
        metricas.leads_criados = len(leads)
        for lead in leads:
            status_id = lead.get("status_id")
            cfs = {
                f.get("field_id"): (f.get("values") or [{}])[0].get("value")
                for f in (lead.get("custom_fields_values") or [])
            }
            # Respondeu = saiu de 0-ETAPA ENTRADA
            if status_id and status_id != 96441724:
                metricas.leads_responderam += 1
            # Dados mínimos: nome_paciente preenchido E convenio preenchido
            if cfs.get(_FIELD_NOME_PACIENTE) and cfs.get(_FIELD_CONVENIO):
                metricas.leads_dados_minimos += 1
            # Ofertou slot: passou por 3-AGENDAR (102560495) ou ZÁ etapas posteriores
            if status_id in (102560495, 106184631, 101507507, 101109455,
                             106653499, 91486864):
                metricas.leads_oferecidos_slot += 1
            # Aceitou: chegou em 5-AGENDADO (101507507) ou posterior
            if status_id in (101507507, 101109455, 106653499, 91486864):
                metricas.leads_aceitaram_slot += 1
            # Gravado Medware = mesmo critério
            if status_id in _STATUS_FUNIL["gravados_medware"]:
                metricas.leads_gravados_medware += 1
            # Compareceu = 8-REALIZADO
            if status_id in _STATUS_FUNIL["compareceram"]:
                metricas.leads_compareceram += 1
            # No-show
            if status_id in _STATUS_FUNIL["no_show"]:
                metricas.no_shows += 1
    except Exception as e:
        # Não vamos quebrar o eval_loop por erro de API.
        import logging
        logging.warning("[eval_loop] coletar_metricas_janela erro: %s", e)

    return metricas


def comparar_24h(kommo_client) -> ComparacaoJanelas:
    """Comparação rápida: últimas 24h vs 24h anteriores."""
    agora = datetime.now(timezone.utc)
    atual = coletar_metricas_janela(kommo_client, agora - timedelta(hours=24), agora)
    anterior = coletar_metricas_janela(kommo_client, agora - timedelta(hours=48), agora - timedelta(hours=24))
    return ComparacaoJanelas(atual=atual, anterior=anterior)


def comparar_7d(kommo_client) -> ComparacaoJanelas:
    """Comparação semanal: 7d × 7d anterior. Usa pra detectar trend."""
    agora = datetime.now(timezone.utc)
    atual = coletar_metricas_janela(kommo_client, agora - timedelta(days=7), agora)
    anterior = coletar_metricas_janela(kommo_client, agora - timedelta(days=14), agora - timedelta(days=7))
    return ComparacaoJanelas(atual=atual, anterior=anterior)


# ────────────────────────────────────────────────────────────────────────
# Relatório
# ────────────────────────────────────────────────────────────────────────

def gerar_relatorio_eval(comparacao: ComparacaoJanelas) -> Dict:
    """Relatório completo pra Slack #lia-engineer.

    Inclui taxas atuais, variações, degradações, melhorias, e recomendações.
    """
    degradacoes = comparacao.degradacoes_detectadas()
    melhorias = comparacao.melhorias_detectadas()
    return {
        "janela_atual": {
            "de": comparacao.atual.janela_inicio.isoformat(),
            "ate": comparacao.atual.janela_fim.isoformat(),
        },
        "funil_atual": comparacao.atual.funil_taxas(),
        "degradacoes_alerta": degradacoes,
        "melhorias": melhorias,
        "alerta_geral": len(degradacoes) > 0,
        "recomendacao": _gerar_recomendacao(degradacoes),
    }


def _gerar_recomendacao(degradacoes: List[Dict]) -> str:
    """Heurística simples: tradução de métrica degradada em ação."""
    if not degradacoes:
        return "Sem degradação significativa. Continuar monitorando."
    acoes = []
    for d in degradacoes:
        m = d["metrica"]
        if "responderam_de_criados" in m:
            acoes.append("Lead não responde — revisar mensagem inicial (template ou primeiro turno Lia).")
        elif "dados_de_responderam" in m:
            acoes.append("Paciente abandona durante coleta de dados — revisar # perguntas/turno (Cat 6).")
        elif "oferta_de_dados" in m:
            acoes.append("Lia coleta dados mas não oferece slot — checar tool_choice Medware (Cat 1).")
        elif "aceite_de_oferta" in m:
            acoes.append("Slots oferecidos não convertem — revisar formato 2 slots imediatos, conferir horários.")
        elif "gravado_de_aceite" in m:
            acoes.append("Paciente aceita mas não grava Medware — bug handle_gravar_agendamento.")
        elif "comparecimento" in m:
            acoes.append("Comparecimento caiu — revisar política sinal + lembretes D-1/D-0.")
        elif "no_show_rate" in m:
            acoes.append("No-show subiu — endurecer política sinal ou ajustar lembretes D-1/D-0.")
    return " | ".join(acoes)


# ────────────────────────────────────────────────────────────────────────
# A/B test de prompt (próxima fase — esqueleto)
# ────────────────────────────────────────────────────────────────────────

@dataclass
class VariantePrompt:
    """Variante de prompt em A/B test."""
    nome: str
    prompt_diff: str  # diff vs prompt baseline
    leads_atendidos: int = 0
    leads_convertidos: int = 0

    def taxa_conversao(self) -> float:
        if self.leads_atendidos == 0:
            return 0.0
        return round(100 * self.leads_convertidos / self.leads_atendidos, 1)


@dataclass
class ABTest:
    """A/B test rodando em produção."""
    nome: str
    iniciado_em: datetime
    variantes: List[VariantePrompt]
    min_leads_por_variante: int = 100

    def vencedora(self) -> Optional[VariantePrompt]:
        if any(v.leads_atendidos < self.min_leads_por_variante for v in self.variantes):
            return None  # ainda não tem dados suficientes
        return max(self.variantes, key=lambda v: v.taxa_conversao())

    def significancia_estatistica(self) -> float:
        """Z-test 2 proporções. Retorna p-value. <0.05 = significativo."""
        # Implementação simplificada — em prod, usar scipy.stats
        if len(self.variantes) != 2:
            return 1.0
        v1, v2 = self.variantes
        if v1.leads_atendidos < 30 or v2.leads_atendidos < 30:
            return 1.0
        p1 = v1.leads_convertidos / v1.leads_atendidos
        p2 = v2.leads_convertidos / v2.leads_atendidos
        p_pool = (v1.leads_convertidos + v2.leads_convertidos) / (v1.leads_atendidos + v2.leads_atendidos)
        if p_pool == 0 or p_pool == 1:
            return 1.0
        import math
        se = math.sqrt(p_pool * (1 - p_pool) * (1/v1.leads_atendidos + 1/v2.leads_atendidos))
        if se == 0:
            return 1.0
        z = abs(p1 - p2) / se
        # P-value aprox (2-tailed) — sem scipy
        return max(0.0, 1.0 - _normal_cdf(z))


def _normal_cdf(z: float) -> float:
    """Aprox CDF normal padrão (sem scipy). Erro <0.001 pra |z|<5."""
    import math
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))
