"""Pytest — C-118 / C-119 / C-120 (11/08/2026).

C-118: deve_gerar_confirmacao_aceite agora lê ctx["known"]["slots_selecionados"]
       (antes lia ctx["slots_ofertados"] que nunca era populado → bypass nunca disparava).

C-119: Quando paciente diz "1, pode marcar", bypass injeta ctx["known"]["c119_slot_para_gravar"]
       → pipeline hook grava Medware sem pedir confirmação extra (salva 1 turno).

C-120: deve_perguntar_dados_pendentes gera a pergunta de dados faltantes sem LLM,
       com todos os campos pendentes em 1 mensagem.
"""
from __future__ import annotations

import re
import pytest

# ---------------------------------------------------------------------------
# Importações dos módulos sob teste
# ---------------------------------------------------------------------------
from voice_agent.blindagens_deterministicas import (
    deve_gerar_confirmacao_aceite,
    deve_perguntar_dados_pendentes,
    _PADRAO_PODE_MARCAR_INLINE,
    _SAUDACAO_PURA_C120,
    _INTENT_AGENDAR_C120,
)


# ═══════════════════════════════════════════════════════════════════════════
# FIXTURES
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture
def slot_karla_quarta():
    """Slot pré-selecionado por C-105 (enriquecimento_ctx step 11)."""
    return {
        "data_iso": "2026-08-12",
        "hora": "09:30",
        "dia_semana": "quarta-feira",
        "data_br": "12/08",
    }


@pytest.fixture
def slot_karla_quinta():
    return {
        "data_iso": "2026-08-13",
        "hora": "14:00",
        "dia_semana": "quinta-feira",
        "data_br": "13/08",
    }


@pytest.fixture
def ctx_karla_asa_norte_completo(slot_karla_quarta, slot_karla_quinta):
    """ctx com checklist completo e slots_selecionados (escrito por C-105)."""
    return {
        "fsm": {"estado": "AGENDA"},
        "lead_id": 99999,
        "known": {
            "nome_paciente": "Maria Clara Souza",
            "data_nasc_iso": "2015-04-10",
            "convenio": "Bacen",
            "medico": "Dra. Karla Delalíbera",
            "unidade": "Asa Norte",
            # C-105 escreve aqui — C-118 passa a ler daqui
            "slots_selecionados": [slot_karla_quarta, slot_karla_quinta],
        },
    }


@pytest.fixture
def ctx_dados_incompletos():
    """ctx sem nome, sem data_nasc — FSM TRIAGEM."""
    return {
        "fsm": {"estado": "TRIAGEM"},
        "lead_id": 11111,
        "known": {
            "motivo": "estrabismo",
            "medico": "Dra. Karla Delalíbera",
            "unidade": "Asa Norte",
        },
    }


@pytest.fixture
def ctx_sem_convenio():
    """ctx com nome + data_nasc mas sem convênio — FSM DADOS."""
    return {
        "fsm": {"estado": "DADOS"},
        "lead_id": 22222,
        "known": {
            "nome_paciente": "João Pedro Alves Costa",
            "data_nasc_iso": "2010-07-15",
            "motivo": "routine",
        },
    }


@pytest.fixture
def ctx_apenas_cpf_faltando():
    """ctx completo exceto CPF — particular."""
    return {
        "fsm": {"estado": "CONVENIO"},
        "lead_id": 33333,
        "known": {
            "nome_paciente": "Ana Luiza Ferreira Nunes",
            "data_nasc_iso": "1990-03-22",
            "convenio": "Não se aplica",
            "medico": "Dra. Karla Delalíbera",
            "unidade": "Águas Claras",
        },
    }


# ═══════════════════════════════════════════════════════════════════════════
# C-118 — Slot lookup fallback
# ═══════════════════════════════════════════════════════════════════════════

class TestC118SlotLookup:
    """C-118: deve_gerar_confirmacao_aceite agora lê ctx.known.slots_selecionados."""

    def test_bug_original_slots_ofertados_vazio_retornava_none(self):
        """Sem a fix, ctx sem 'slots_ofertados' → bypass retornava None (bug)."""
        ctx = {
            "fsm": {"estado": "AGENDA"},
            "known": {
                "slots_selecionados": [
                    {"data_iso": "2026-08-12", "hora": "09:30",
                     "dia_semana": "quarta-feira", "data_br": "12/08"},
                ]
            },
            # NÃO tem "slots_ofertados" — era o bug
        }
        # Com a fix, deve achar os slots via ctx.known.slots_selecionados
        resultado = deve_gerar_confirmacao_aceite(ctx, "1")
        # Não deve ser None
        assert resultado is not None

    def test_fix_c118_le_slots_selecionados(self, ctx_karla_asa_norte_completo):
        """Fix C-118: bypass encontra slots via ctx['known']['slots_selecionados']."""
        resultado = deve_gerar_confirmacao_aceite(ctx_karla_asa_norte_completo, "1")
        assert resultado is not None
        # Deve conter data do primeiro slot
        assert "12/08" in resultado or "09:30" in resultado

    def test_emoji_1_seleciona_primeiro_slot(self, ctx_karla_asa_norte_completo):
        resultado = deve_gerar_confirmacao_aceite(ctx_karla_asa_norte_completo, "1️⃣")
        assert resultado is not None
        assert "12/08" in resultado

    def test_segunda_opcao_seleciona_segundo_slot(self, ctx_karla_asa_norte_completo):
        resultado = deve_gerar_confirmacao_aceite(ctx_karla_asa_norte_completo, "2️⃣")
        assert resultado is not None
        assert "13/08" in resultado

    def test_sem_slots_retorna_none(self):
        ctx = {"fsm": {"estado": "AGENDA"}, "known": {}}
        assert deve_gerar_confirmacao_aceite(ctx, "1") is None

    def test_ctx_none_retorna_none(self):
        assert deve_gerar_confirmacao_aceite(None, "1") is None

    def test_user_text_vazio_retorna_none(self, ctx_karla_asa_norte_completo):
        assert deve_gerar_confirmacao_aceite(ctx_karla_asa_norte_completo, "") is None

    def test_texto_nao_aceite_retorna_none(self, ctx_karla_asa_norte_completo):
        assert deve_gerar_confirmacao_aceite(ctx_karla_asa_norte_completo, "não quero") is None


class TestC118TextoConfirmacao:
    """C-118 fix: _montar_texto_confirmacao agora pede CONFIRMAÇÃO, não diz 'estou registrando'."""

    def test_texto_nao_diz_registrando(self, ctx_karla_asa_norte_completo):
        resultado = deve_gerar_confirmacao_aceite(ctx_karla_asa_norte_completo, "1")
        assert resultado is not None
        # Antes dizia "Já estou registrando no sistema" — ERRADO (não gravava no Medware)
        assert "registrando" not in resultado.lower()
        assert "em instantes te envio" not in resultado.lower()

    def test_texto_pede_confirmacao(self, ctx_karla_asa_norte_completo):
        resultado = deve_gerar_confirmacao_aceite(ctx_karla_asa_norte_completo, "1")
        assert resultado is not None
        # Deve perguntar se está certo
        assert any(kw in resultado.lower() for kw in [
            "tudo certo", "está certo", "confirma", "certo pra você"
        ])

    def test_texto_contem_data_e_hora(self, ctx_karla_asa_norte_completo):
        resultado = deve_gerar_confirmacao_aceite(ctx_karla_asa_norte_completo, "1")
        assert "12/08" in resultado
        assert "09:30" in resultado or "09h" in resultado

    def test_texto_contem_medico(self, ctx_karla_asa_norte_completo):
        resultado = deve_gerar_confirmacao_aceite(ctx_karla_asa_norte_completo, "1")
        assert "karla" in resultado.lower() or "dra." in resultado.lower()


# ═══════════════════════════════════════════════════════════════════════════
# C-119 — Aceite + "pode marcar" inline
# ═══════════════════════════════════════════════════════════════════════════

class TestC119PadraoPoderMarcar:
    """Regex _PADRAO_PODE_MARCAR_INLINE cobre frases de confirmação inline."""

    @pytest.mark.parametrize("texto", [
        "1, pode marcar",
        "1️⃣ pode agendar",
        "2, confirma",
        "pode marcar o primeiro",
        "quero marcar esse",
        "sim, pode confirmar",
        "tá bom, pode marcar",
        "tá ok, pode agendar",
        "fecha esse",
        "pega esse",
        "vai marcar",
        "marca aí",
        "fica marcado",
    ])
    def test_deve_casar(self, texto):
        assert _PADRAO_PODE_MARCAR_INLINE.search(texto), f"Não casou: {texto!r}"

    @pytest.mark.parametrize("texto", [
        "1",               # só aceite posicional, sem confirmação
        "1️⃣",             # só emoji
        "segunda opção",   # seleção sem confirmação
        "pode ser",        # ambíguo — não é confirmação de slot
        "não quero",
        "deixa eu pensar",
    ])
    def test_nao_deve_casar_falsos_positivos(self, texto):
        # Esses não devem disparar C-119
        assert not _PADRAO_PODE_MARCAR_INLINE.search(texto), f"Falso positivo: {texto!r}"


class TestC119InjecaoCtxKnown:
    """C-119: quando inline, injeta c119_slot_para_gravar em ctx.known."""

    def test_injeta_slot_quando_pode_marcar_inline(self, ctx_karla_asa_norte_completo):
        ctx = ctx_karla_asa_norte_completo
        resultado = deve_gerar_confirmacao_aceite(ctx, "1, pode marcar")
        assert resultado is not None
        # Flag deve ter sido injetado
        assert "c119_slot_para_gravar" in ctx["known"]
        slot_injetado = ctx["known"]["c119_slot_para_gravar"]
        assert slot_injetado["data_iso"] == "2026-08-12"
        assert slot_injetado["hora"] == "09:30"

    def test_nao_injeta_sem_pode_marcar(self, ctx_karla_asa_norte_completo):
        ctx = ctx_karla_asa_norte_completo
        # "1" sem "pode marcar" → confirmação normal, não injeta flag
        deve_gerar_confirmacao_aceite(ctx, "1")
        assert "c119_slot_para_gravar" not in ctx.get("known", {})

    def test_texto_c119_anuncia_reserva_imediata(self, ctx_karla_asa_norte_completo):
        ctx = ctx_karla_asa_norte_completo
        resultado = deve_gerar_confirmacao_aceite(ctx, "pode marcar a primeira opção")
        assert resultado is not None
        # Texto C-119 deve anunciar que está RESERVANDO (não pedindo confirmação)
        assert any(kw in resultado.lower() for kw in [
            "reservando", "perfeito", "✅"
        ])
        # E NÃO deve pedir "tudo certo?" (isso é texto C-118 normal)
        assert "tudo certo pra você" not in resultado.lower()

    def test_ctx_known_none_nao_explode(self):
        """Se ctx.known for None, C-119 não explode — fail-open."""
        ctx = {"fsm": {"estado": "AGENDA"}, "known": None}
        # Não tem slots_selecionados, deve retornar None
        resultado = deve_gerar_confirmacao_aceite(ctx, "pode marcar")
        assert resultado is None  # sem slots → None, sem exceção

    def test_toggle_off_retorna_none(self, ctx_karla_asa_norte_completo, monkeypatch):
        monkeypatch.setenv("BLINDAGEM_ACEITE_ATIVADO", "0")
        resultado = deve_gerar_confirmacao_aceite(ctx_karla_asa_norte_completo, "1, pode marcar")
        assert resultado is None


# ═══════════════════════════════════════════════════════════════════════════
# C-120 — deve_perguntar_dados_pendentes
# ═══════════════════════════════════════════════════════════════════════════

class TestC120SaudacaoPura:
    """C-120 não dispara para saudações puras."""

    @pytest.mark.parametrize("texto", [
        "oi", "Oi!", "Olá", "olá", "ola",
        "bom dia", "boa tarde", "boa noite",
        "hey", "hi",
    ])
    def test_saudacao_nao_dispara(self, texto, ctx_dados_incompletos):
        resultado = deve_perguntar_dados_pendentes(ctx_dados_incompletos, texto)
        assert resultado is None, f"Disparou pra saudação: {texto!r}"


class TestC120IntentAgendar:
    """Regex _INTENT_AGENDAR_C120 cobre formas comuns de intenção de agendar."""

    @pytest.mark.parametrize("texto", [
        "quero agendar",
        "queria marcar uma consulta",
        "preciso de uma consulta",
        "gostaria de agendar",
        "poderia marcar um horário",
        "quero consultar",
        "quero uma avaliação",
    ])
    def test_deve_detectar_intent(self, texto):
        assert _INTENT_AGENDAR_C120.search(texto), f"Não detectou intent: {texto!r}"

    @pytest.mark.parametrize("texto", [
        "quanto custa",
        "tudo bem",
        "quero saber sobre a clínica",
        "me fale sobre os serviços",
    ])
    def test_nao_deve_detectar_false_positives(self, texto):
        assert not _INTENT_AGENDAR_C120.search(texto), f"Falso positivo: {texto!r}"


class TestC120PerguntaDados:
    """C-120 gera a pergunta de dados pendentes corretamente."""

    def test_dispara_com_intent_e_dados_faltando(self):
        """Paciente diz 'quero agendar' + ctx sem dados → C-120 pergunta tudo."""
        ctx = {
            "fsm": {"estado": "TRIAGEM"},
            "known": {},  # Completamente vazio
        }
        resultado = deve_perguntar_dados_pendentes(ctx, "quero agendar minha filha")
        assert resultado is not None
        # Deve pedir dados — nome e data de nascimento são obrigatórios
        assert any(kw in resultado.lower() for kw in [
            "nome", "nascimento", "convênio", "plano"
        ])

    def test_dispara_com_dados_parciais(self, ctx_dados_incompletos):
        """Paciente responde com algo, tem motivo mas falta nome e DOB → C-120."""
        resultado = deve_perguntar_dados_pendentes(
            ctx_dados_incompletos, "tenho 6 anos"
        )
        assert resultado is not None
        # Deve perguntar nome e data de nascimento
        assert "nome" in resultado.lower()

    def test_dispara_apenas_convenio_faltando(self, ctx_sem_convenio):
        """Só convenio faltando (tem nome e DOB) → C-120 pergunta especificamente."""
        resultado = deve_perguntar_dados_pendentes(ctx_sem_convenio, "sim")
        assert resultado is not None
        assert "convênio" in resultado.lower() or "plano" in resultado.lower()

    def test_dispara_cpf_faltando_particular(self, ctx_apenas_cpf_faltando):
        """Particular sem CPF → C-120 pergunta CPF com nome do paciente."""
        resultado = deve_perguntar_dados_pendentes(ctx_apenas_cpf_faltando, "sim")
        assert resultado is not None
        assert "cpf" in resultado.lower()
        # Deve incluir o nome do paciente (personalização)
        assert "ana" in resultado.lower() or "ana luiza" in resultado.lower()

    def test_nao_dispara_checklist_completo(self):
        """Checklist completo → C-120 não dispara."""
        ctx = {
            "fsm": {"estado": "DADOS"},
            "known": {
                "nome_paciente": "Carlos Eduardo Lima Santos",
                "data_nasc_iso": "1985-06-10",
                "convenio": "Bacen",
                "medico": "Dra. Karla Delalíbera",
                "unidade": "Asa Norte",
            },
        }
        resultado = deve_perguntar_dados_pendentes(ctx, "sim")
        assert resultado is None

    def test_nao_dispara_em_agenda(self, ctx_karla_asa_norte_completo):
        """FSM=AGENDA (paciente escolhendo slot) → C-120 não deve interferir."""
        ctx = ctx_karla_asa_norte_completo
        # Mesmo que dados faltassem (não é o caso aqui), AGENDA não deve disparar C-120
        resultado = deve_perguntar_dados_pendentes(ctx, "1")
        assert resultado is None

    def test_nao_dispara_em_confirmacao(self):
        """FSM=CONFIRMACAO → C-120 não dispara."""
        ctx = {
            "fsm": {"estado": "CONFIRMACAO"},
            "known": {"motivo": "estrabismo"},  # dados incompletos mas irrelevante
        }
        resultado = deve_perguntar_dados_pendentes(ctx, "sim")
        assert resultado is None

    def test_nao_dispara_em_gravacao(self):
        """FSM=GRAVACAO → C-120 não dispara."""
        ctx = {"fsm": {"estado": "GRAVACAO"}, "known": {}}
        resultado = deve_perguntar_dados_pendentes(ctx, "ok")
        assert resultado is None

    def test_nao_dispara_ja_agendado(self):
        """Paciente já agendado → C-120 não dispara."""
        ctx = {
            "fsm": {"estado": "TRIAGEM"},
            "ja_agendado": True,
            "known": {"motivo": "retorno"},
        }
        resultado = deve_perguntar_dados_pendentes(ctx, "quero agendar")
        assert resultado is None

    def test_nao_dispara_sem_intent_e_sem_dados(self):
        """Sem intent de agendamento E sem dados coletados → C-120 não dispara (deixa LLM)."""
        ctx = {
            "fsm": {"estado": "TRIAGEM"},
            "known": {},
        }
        # Pergunta de serviço sem intent de agendar
        resultado = deve_perguntar_dados_pendentes(ctx, "quanto custa a consulta?")
        assert resultado is None

    def test_ctx_none_retorna_none(self):
        assert deve_perguntar_dados_pendentes(None, "quero agendar") is None

    def test_user_text_vazio_retorna_none(self, ctx_dados_incompletos):
        assert deve_perguntar_dados_pendentes(ctx_dados_incompletos, "") is None

    def test_toggle_off_retorna_none(self, ctx_dados_incompletos, monkeypatch):
        monkeypatch.setenv("BLINDAGEM_DADOS_PENDENTES_ATIVADO", "0")
        resultado = deve_perguntar_dados_pendentes(
            ctx_dados_incompletos, "quero agendar"
        )
        assert resultado is None

    def test_multiplos_campos_em_uma_mensagem(self):
        """Quando há 3 campos pendentes, todos ficam na mesma mensagem (não separados)."""
        ctx = {
            "fsm": {"estado": "TRIAGEM"},
            "known": {"motivo": "estrabismo"},  # nome, DOB e convenio faltando
        }
        resultado = deve_perguntar_dados_pendentes(ctx, "quero agendar")
        assert resultado is not None
        # Uma só mensagem com múltiplos campos
        assert "e" in resultado  # "nome... e data... e convênio"

    def test_pergunta_contem_saudacao_com_nome(self):
        """Quando nome já coletado, pergunta começa com ele."""
        ctx = {
            "fsm": {"estado": "DADOS"},
            "known": {
                "nome_paciente": "Beatriz Almeida Souza Silva",
                "motivo": "rotina",
                "medico": "Dra. Karla Delalíbera",
                "unidade": "Asa Norte",
            },
        }
        resultado = deve_perguntar_dados_pendentes(ctx, "sim")
        assert resultado is not None
        # Deve incluir nome (Beatriz) na saudação
        assert "beatriz" in resultado.lower() or "Beatriz" in resultado


# ═══════════════════════════════════════════════════════════════════════════
# Posição na chain — C-120 deve estar NO FIM
# ═══════════════════════════════════════════════════════════════════════════

class TestC120PosicaoNaChain:
    """C-120 fica no fim da chain em tentar_bypass_deterministico."""

    def test_aceite_slot_tem_prioridade_sobre_c120(self, ctx_karla_asa_norte_completo):
        """Se aceite_slot disparar, C-120 não deve ser chamado."""
        from voice_agent.blindagens_deterministicas import tentar_bypass_deterministico
        resultado = tentar_bypass_deterministico(ctx_karla_asa_norte_completo, "1")
        assert resultado is not None
        nome, texto = resultado
        # Deve ser aceite_slot (C-118), não dados_pendentes (C-120)
        assert nome == "aceite_slot"

    def test_c120_dispara_quando_nenhum_bypass_especifico_quer(self):
        """Nenhum bypass específico → C-120 assume e pergunta dados."""
        from voice_agent.blindagens_deterministicas import tentar_bypass_deterministico
        ctx = {
            "fsm": {"estado": "TRIAGEM"},
            "known": {"motivo": "estrabismo"},
        }
        resultado = tentar_bypass_deterministico(ctx, "quero agendar minha filha")
        assert resultado is not None
        nome, _ = resultado
        assert nome == "dados_pendentes_c120"

    def test_arquivo_tem_c120_no_fim_da_chain(self):
        """Verificar que 'dados_pendentes_c120' está wired em tentar_bypass_deterministico."""
        import inspect
        from voice_agent import blindagens_deterministicas
        src = inspect.getsource(blindagens_deterministicas.tentar_bypass_deterministico)
        assert "dados_pendentes_c120" in src
        # C-120 deve aparecer DEPOIS de sinal_particular_c114 (último item anterior)
        pos_c114 = src.find("sinal_particular_c114")
        pos_c120 = src.find("dados_pendentes_c120")
        assert pos_c114 < pos_c120, "C-120 deve estar DEPOIS de C-114 na chain"
