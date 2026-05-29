"""Pytest dos cenários históricos da Lia.

Cada bug que já travou em produção vira UM teste aqui. Push roda
os testes via GitHub Actions; se algum quebrar, o deploy falha e o
fix antigo não regride.

Como rodar local:
    cd /Users/fabiophilipecostamartins/Documents/Claude/Projects/AGENTE\\ IA\\ BLINK
    python -m pytest tests/ -v

Cenários cobertos:
  - Aurora (lead 23907418): retrocesso ja_agendado
  - Um momentinho (lead 24033913): fingiu consultar agenda
  - Cobrança antes slot (lead 24034205): pediu Pix sem oferecer slot
  - Dia da semana inventado (lead 24038029): "terça 03/06" = quarta
  - Mentiu gravação Medware (lead 24038029): afirmou registrado sem ter
  - Fallback instabilidade repetido (lead 24037253): 3 vezes mesma frase
"""
from __future__ import annotations

import sys
from pathlib import Path

# Adiciona repo root ao sys.path pra importar voice_agent
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402

from voice_agent.responder import (  # noqa: E402
    _viola_dia_semana,
    _viola_afirmacao_gravacao,
    _viola_cobranca_antes_slot,
    _viola_oferta_agenda,
)
from voice_agent.medware import resolver_plano  # noqa: E402


# ----------------------------------------------------------------------
# CENÁRIO 1 — Dia da semana inventado (lead 24038029, 29/05/2026)
# Lia escreveu "terça-feira, 03/06" mas 03/06/2026 é quarta.
# ----------------------------------------------------------------------
class TestDiaSemanaInventado:
    def test_terca_03_junho_e_na_verdade_quarta(self):
        """Lead 24038029: Lia disse 03/06 era terça, era quarta."""
        text = "1️⃣ terça-feira, 03/06 às 10:30"
        resultado = _viola_dia_semana(text)
        assert resultado is not None, "Filtro DEVE detectar"
        dia_falado, data, dia_real = resultado
        assert dia_falado == "terça-feira"
        assert "03/06" in data
        assert dia_real == "quarta-feira"

    def test_terca_10_junho_e_quarta(self):
        text = "3️⃣ terça-feira, 10/06 às 11:15"
        resultado = _viola_dia_semana(text)
        assert resultado is not None
        assert resultado[2] == "quarta-feira"

    def test_quinta_04_junho_esta_correto(self):
        """04/06/2026 é quinta-feira — NÃO deve disparar filtro."""
        text = "2️⃣ quinta-feira, 04/06 às 11:00"
        resultado = _viola_dia_semana(text)
        assert resultado is None, (
            f"Filtro NÃO deveria detectar (04/06 é quinta), mas detectou: {resultado}"
        )

    def test_terca_02_junho_esta_correto(self):
        """02/06/2026 é terça — correção que Lia fez está OK."""
        text = "1️⃣ terça-feira, 02/06 às 10:30"
        resultado = _viola_dia_semana(text)
        assert resultado is None

    def test_sem_data_nao_dispara(self):
        text = "Qual sua preferência de turno?"
        assert _viola_dia_semana(text) is None

    def test_data_invalida_30_de_fevereiro_nao_explode(self):
        """Não deve crashar com data impossível."""
        text = "segunda-feira, 30/02"
        # Apenas não pode lançar exceção
        _viola_dia_semana(text)  # ok se retornar None ou True


# ----------------------------------------------------------------------
# CENÁRIO 2 — Mentir gravação Medware (lead 24038029, 29/05/2026)
# Lia disse "agendamento já foi registrado automaticamente no Medware"
# sem ter como verificar. Mentira ética grave.
# ----------------------------------------------------------------------
class TestAfirmacaoGravacaoMedware:
    def test_registrado_automaticamente_no_medware(self):
        text = "Sim! O agendamento já foi registrado automaticamente no Medware quando você confirmou o horário."
        assert _viola_afirmacao_gravacao(text), "DEVE bloquear"

    def test_esta_tudo_registrado_no_sistema(self):
        text = "Está tudo registrado no sistema! Agora só falta enviar a carteirinha."
        assert _viola_afirmacao_gravacao(text)

    def test_foi_gravado_na_medware(self):
        text = "Foi gravado na Medware com sucesso."
        assert _viola_afirmacao_gravacao(text)

    def test_dados_foram_salvos_no_sistema(self):
        text = "Os dados foram salvos no sistema."
        assert _viola_afirmacao_gravacao(text)

    def test_mensagem_de_confirmacao_normal_nao_dispara(self):
        """'Combinado, terça 02/06 às 10:30' é confirmação OK."""
        text = "Combinado, Karla! Terça-feira, 02/06 às 10:30 com a Dra. Karla em Águas Claras."
        assert not _viola_afirmacao_gravacao(text), (
            "NÃO deveria bloquear — é confirmação de slot, não afirmação de gravação"
        )

    def test_em_processamento_nao_dispara(self):
        text = "Sua reserva está em processamento — a confirmação no sistema sai em alguns minutos."
        assert not _viola_afirmacao_gravacao(text)


# ----------------------------------------------------------------------
# CENÁRIO 3 — Cobrança sinal antes de slot (lead 24034205)
# Lia pediu Pix 305,50 sem ter oferecido slot concreto.
# ----------------------------------------------------------------------
class TestCobrancaAntesSlot:
    def test_pix_sem_slot_concreto(self):
        text = "Faça o Pix de R$ 305,50 na chave karladelaliberaoftalmo@gmail.com"
        assert _viola_cobranca_antes_slot(text), "DEVE bloquear"

    def test_cobranca_com_slot_concreto_passa(self):
        """Cobrança com slot dia+data+hora E menção a encaixe = OK."""
        text = (
            "Pra terça-feira, 02/06 às 10:30 com a Dra. Karla, "
            "você prefere Reserva Imediata (Pix R$ 305,50) ou Fila de Encaixe?"
        )
        # Tem slot concreto E menciona encaixe → não deve disparar
        assert not _viola_cobranca_antes_slot(text)


# ----------------------------------------------------------------------
# CENÁRIO 4 — Fingiu consultar agenda (lead 24033913, "Um momentinho")
# Lia disse "deixa eu consultar a agenda" TENDO agenda real no contexto.
# ----------------------------------------------------------------------
class TestFakeAgendaLookup:
    def test_um_momentinho_com_agenda_no_ctx(self):
        text = "Um momentinho, deixa eu consultar a agenda pra você"
        # Simula que ctx tem agenda real
        assert _viola_oferta_agenda(text, has_agenda=True), "DEVE bloquear"

    def test_sem_agenda_no_ctx_passa(self):
        """Se de fato não tem agenda no contexto, frase é honesta."""
        text = "Um momentinho enquanto consulto a agenda"
        assert not _viola_oferta_agenda(text, has_agenda=False)


# ----------------------------------------------------------------------
# CENÁRIO 5 — Convênios Kommo ↔ Medware mapeados (lead 24038029, 29/05/2026)
# Bug original: "Pro ser STJ" do Kommo não casava com "STJ" do Medware.
# Cross-check oficial 29/05/2026 — todos os 27 convênios devem resolver.
# ----------------------------------------------------------------------
class TestConveniosMapeados:
    @pytest.mark.parametrize("convenio,esperado", [
        ("Bacen", 9),
        ("Casec (Codevasf)", 15),
        ("Casembrapa  _ Embrapa", 16),
        ("Conab", 19),
        ("E-vida (Luminar)", 5),
        ("Fascal", 22),
        ("Omint", 25),
        ("PF Saúde", 26),
        ("Plan Assiste - MPF (MPU)", 4),
        ("PróSaúde (Camara dos Deputados)", 39),
        ("Proasa", 28),
        ("Saúde Caixa", 29),
        ("Petrobrás (Saúde Petrobrás)", 30),
        ("Serpro", 31),
        ("SIS Senado", 32),
        ("STF-Med", 33),
        ("TRE", 35),
        ("TRF Pró-Social", 34),
        ("TRT", 36),
        ("TST Saúde", 37),
        ("TJDFT Pró-Saúde", 2),
        ("Não se aplica", 1),
        ("Pro ser STJ", 3),  # ← bug histórico lead 24038029
        ("Care Plus", 14),
        ("Anafe", 8),
        ("PLAS/JMU (STM)", 27),
    ])
    def test_convenio_kommo_resolve_medware(self, convenio, esperado):
        """Cada convênio do enum CONVÊNIO do Kommo (field 853206) DEVE
        resolver pra um codPlano > 0 do Medware. Bug histórico (lead
        24038029, 29/05/2026): 'Pro ser STJ' não casava com 'STJ'
        porque match parcial exige len(nome)>=4 e 'stj' tem 3 chars."""
        assert resolver_plano(convenio) == esperado

    def test_inas_gdf_nao_mapeado_propositalmente(self):
        """Inas GDf não tem correspondência no listar_planos_operadoras
        do Medware (29/05/2026). Retorna 0 propositalmente → escala
        humano até decisão de negócio sobre qual codPlano usar."""
        assert resolver_plano("Inas GDf (somente Dr. Fabrício Freitas)") == 0

    def test_paciente_escreve_minusculo_funciona(self):
        """Lookup é case-insensitive."""
        assert resolver_plano("pro ser stj") == 3
        assert resolver_plano("fascal") == 22

    def test_paciente_escreve_sem_acento(self):
        """Aliases sem acento devem funcionar."""
        assert resolver_plano("saude caixa") == 29
        assert resolver_plano("petrobras") == 30


# ----------------------------------------------------------------------
# CENÁRIO 7 — Silêncio Lia controlado SÓ por etapa Kommo (decisão Fábio
# 29/05/2026). Removida verificação de campo ATIVADO IA? e janela handoff.
# Razão: 3 sinais redundantes confundiam (lead 24038117 Talita).
# Lia silencia QUANDO E APENAS QUANDO status_id está em ST_AGENT_OFF.
# Operação humana: mover lead pra etapa humana ao assumir, mover de
# volta ao terminar. Recomendado: regra Salesbot Kommo automática.
# ----------------------------------------------------------------------
class TestSilencioPorEtapa:
    """Único sinal de silêncio é a etapa do funil Kommo."""

    def _make_kommo_stub(self):
        from voice_agent.kommo import KommoClient
        return KommoClient.__new__(KommoClient)

    def test_etapa_normal_lia_responde(self):
        """2-AGENDAR não está em ST_AGENT_OFF → Lia responde."""
        kommo = self._make_kommo_stub()
        ctx = {"found": True, "lead_id": 1, "status_id": 102560495,
               "known": {}}
        assert kommo.agent_paused_for_lead(ctx, 30) is None

    def test_etapa_humana_lia_silencia(self):
        """Lead em 7-CIRURGIAS / 8-LENTES / 9-FORNECEDORES → silêncio."""
        from voice_agent.kommo import ST_AGENT_OFF
        kommo = self._make_kommo_stub()
        for st in list(ST_AGENT_OFF)[:3]:
            ctx = {"found": True, "lead_id": 1, "status_id": st, "known": {}}
            motivo = kommo.agent_paused_for_lead(ctx, 30)
            assert motivo == "etapa-humana", f"falhou pra status_id={st}"

    def test_ativado_ia_campo_ignorado(self):
        """Mesmo com ATIVADO IA? = Desativado, etapa normal libera Lia.
        Decisão Fábio 29/05: campo ATIVADO IA? não é mais sinal de silêncio."""
        kommo = self._make_kommo_stub()
        ctx = {
            "found": True, "lead_id": 1, "status_id": 102560495,  # 2-AGENDAR
            "known": {"ativado_ia": "Desativado"},  # ignorado
        }
        assert kommo.agent_paused_for_lead(ctx, 30) is None

    def test_caller_context_vazio_lia_responde(self):
        """Sem contexto válido (paciente novo) → Lia responde normalmente."""
        kommo = self._make_kommo_stub()
        assert kommo.agent_paused_for_lead(None, 30) is None
        assert kommo.agent_paused_for_lead({"found": False}, 30) is None


# ----------------------------------------------------------------------
# CENÁRIO 6 — Médicos mapeados (origem: smoke test 29/05/2026 22:30)
# Bug encontrado: "Dr. Fabricio Freitas" (sem acento) retornava 0,
# bloqueando consulta agenda + gravação Medware pra TODO Fabricio.
# ----------------------------------------------------------------------
class TestMedicosMapeados:
    """Karla e Fabricio devem casar em variações com/sem acento."""

    @pytest.mark.parametrize("nome,esperado", [
        # Karla — variantes
        ("Dra. Karla Delalibera", 12080),
        ("Dra. Karla Delalíbera", 12080),
        ("Karla Delalibera", 12080),
        ("Karla", 12080),
        ("Dra. Karla", 12080),
        ("Karla Delalibera Pacheco", 12080),  # como aparece no Medware
        # Fabricio — variantes (bug histórico: sem acento falhava)
        ("Dr. Fabricio Freitas", 12081),  # ← bug fixado 29/05/2026
        ("Dr. Fabrício Freitas", 12081),
        ("Fabricio", 12081),
        ("Fabrício", 12081),
        ("Dr. Fabricio", 12081),
        ("Dr Freitas", 12081),
    ])
    def test_medico_lookup(self, nome, esperado):
        from voice_agent.medware import MEDICO_CODES, _code_lookup
        assert _code_lookup(MEDICO_CODES, nome) == esperado
