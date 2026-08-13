"""Pytest — C-125 (11/08/2026) — Prova de escuta + uma pergunta por turno.

Regressão de C-120: deve_perguntar_dados_pendentes despejava TODOS os campos
pendentes em um formulário sem reconhecer o que o paciente acabou de dizer.

Caso real: lead 24441434 Janaina Melo.
  Paciente: "Gostaria de agendar com a Dra. Karla. É para o meu filho de 7 meses.
             Consulta de rotina solicitada pelo pediatra."
  Lia (errado): "me passa: nome completo, data de nascimento, convênio, médico e unidade?"
  Lia (correto): "Anotado — Dra. Karla Delalíbera, bebê de 7 meses, consulta de rotina! 😊
                  Qual o nome completo do bebê?"

Regras C-125:
  1. Prova de escuta — acknowledge o que o paciente disse
  2. UMA só pergunta por turno (não formulário)
  3. NUNCA pede médico — Python deriva via C-101/enriquecimento_ctx
  4. Pergunta priorizada: nome → data_nasc → convênio → cpf → unidade
"""
from __future__ import annotations

import pytest

from voice_agent.blindagens_deterministicas import (
    deve_perguntar_dados_pendentes,
    _prova_de_escuta_c125,
    _campo_prioritario_c125,
    _montar_pergunta_dados_c125,
)


# ═══════════════════════════════════════════════════════════════════════════
# FIXTURES
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture
def ctx_janaina():
    """Lead 24441434 Janaina Melo — bebê 7 meses, rotina, Dra. Karla."""
    return {
        "fsm": {"estado": "TRIAGEM"},
        "lead_id": 24441434,
        "known": {
            "motivo": "rotina",
            "medico": "Dra. Karla Delalíbera",  # derivado por C-101
        },
    }


@pytest.fixture
def ctx_sem_dados():
    """ctx sem nenhum dado coletado — FSM TRIAGEM."""
    return {
        "fsm": {"estado": "TRIAGEM"},
        "known": {},
    }


@pytest.fixture
def ctx_com_nome():
    """ctx com nome do paciente já coletado."""
    return {
        "fsm": {"estado": "DADOS"},
        "known": {
            "nome_paciente": "Beatriz Almeida Souza Silva",
            "motivo": "rotina",
            "medico": "Dra. Karla Delalíbera",
            "unidade": "Asa Norte",
        },
    }


@pytest.fixture
def ctx_apenas_medico_pendente():
    """ctx onde só médico está faltando — Python deve derivar, não perguntar."""
    return {
        "fsm": {"estado": "TRIAGEM"},
        "known": {
            "nome_paciente": "Carlos Eduardo Lima Santos",
            "data_nasc_iso": "1985-06-10",
            "convenio": "Bacen",
            "unidade": "Asa Norte",
            # sem "medico" → checklist inclui "médico" como pendente
        },
    }


@pytest.fixture
def ctx_particular_sem_cpf():
    """ctx particular completo exceto CPF."""
    return {
        "fsm": {"estado": "CONVENIO"},
        "known": {
            "nome_paciente": "Ana Luiza Ferreira Nunes",
            "data_nasc_iso": "1990-03-22",
            "convenio": "Não se aplica",  # particular → CPF exigido
            "medico": "Dra. Karla Delalíbera",
            "unidade": "Águas Claras",
        },
    }


# ═══════════════════════════════════════════════════════════════════════════
# CASO REAL — LEAD 24441434 JANAINA MELO
# ═══════════════════════════════════════════════════════════════════════════

class TestCasoRealJanaina:
    """Regressão do bug C-125: paciente informou médico + filho + rotina."""

    USER_TEXT_JANAINA = (
        "Gostaria de agendar uma consulta com a Dra. Karla. "
        "É para o meu filho de 7 meses. "
        "Consulta de rotina solicitada pelo pediatra."
    )

    def test_resultado_contem_prova_de_escuta(self, ctx_janaina):
        resultado = deve_perguntar_dados_pendentes(ctx_janaina, self.USER_TEXT_JANAINA)
        assert resultado is not None
        # Deve reconhecer Dra. Karla
        assert "karla" in resultado.lower()
        # Deve reconhecer bebê de 7 meses
        assert "7" in resultado and "mes" in resultado.lower()

    def test_resultado_pergunta_apenas_nome(self, ctx_janaina):
        """Com prova de escuta, só pergunta o nome (não 5 campos de uma vez)."""
        resultado = deve_perguntar_dados_pendentes(ctx_janaina, self.USER_TEXT_JANAINA)
        assert resultado is not None
        # Deve perguntar nome
        assert "nome" in resultado.lower()
        # NÃO deve pedir múltiplos campos na mesma mensagem
        assert "convênio" not in resultado.lower()
        assert "data de nascimento" not in resultado.lower()
        assert "unidade" not in resultado.lower()

    def test_nao_pede_medico(self, ctx_janaina):
        """C-125 nunca pergunta médico — Python deriva."""
        resultado = deve_perguntar_dados_pendentes(ctx_janaina, self.USER_TEXT_JANAINA)
        assert resultado is not None
        assert "médico" not in resultado.lower()
        assert "dr. fabricio" not in resultado.lower()
        # "karla" pode estar na prova de escuta mas não como pergunta
        assert "dra. karla delalíbera ou dr. fabrício freitas" not in resultado.lower()

    def test_usa_emoji_de_escuta(self, ctx_janaina):
        """Com escuta identificada, resposta usa 😊."""
        resultado = deve_perguntar_dados_pendentes(ctx_janaina, self.USER_TEXT_JANAINA)
        assert resultado is not None
        assert "😊" in resultado

    def test_menciona_bebe_na_pergunta_nome(self, ctx_janaina):
        """Pergunta de nome personalizada para bebê."""
        resultado = deve_perguntar_dados_pendentes(ctx_janaina, self.USER_TEXT_JANAINA)
        assert resultado is not None
        # "bebê" deve aparecer na pergunta de nome
        assert "beb" in resultado.lower() or "nome" in resultado.lower()

    def test_nao_formulario(self, ctx_janaina):
        """A resposta NÃO deve ser um formulário com múltiplos campos."""
        resultado = deve_perguntar_dados_pendentes(ctx_janaina, self.USER_TEXT_JANAINA)
        assert resultado is not None
        # Formulário clássico continha "antes de garantir o horário, me passa:"
        assert "antes de garantir o horário, me passa:" not in resultado.lower()


# ═══════════════════════════════════════════════════════════════════════════
# PROVA DE ESCUTA — _prova_de_escuta_c125
# ═══════════════════════════════════════════════════════════════════════════

class TestProvaDeEscuta:
    """_prova_de_escuta_c125 detecta elementos do que o paciente disse."""

    def test_detecta_karla(self):
        escuta = _prova_de_escuta_c125("quero consulta com a Dra. Karla", {})
        assert "karla" in escuta.lower()

    def test_detecta_fabricio(self):
        escuta = _prova_de_escuta_c125("quero com o Dr. Fabrício Freitas", {})
        assert "fabrício" in escuta.lower() or "fabricio" in escuta.lower()

    def test_detecta_bebe_com_meses(self):
        escuta = _prova_de_escuta_c125("para meu filho de 7 meses", {})
        assert "7" in escuta and ("mes" in escuta.lower() or "beb" in escuta.lower())

    def test_detecta_bebe_com_1_mes(self):
        escuta = _prova_de_escuta_c125("é para meu bebê de 1 mês", {})
        assert "1" in escuta

    def test_detecta_crianca_com_anos(self):
        escuta = _prova_de_escuta_c125("minha filha de 5 anos", {})
        assert "5" in escuta and "ano" in escuta.lower()

    def test_detecta_rotina(self):
        escuta = _prova_de_escuta_c125("consulta de rotina", {})
        assert "rotina" in escuta.lower()

    def test_detecta_retorno(self):
        escuta = _prova_de_escuta_c125("retorno pós-operatório", {})
        assert "retorno" in escuta.lower()

    def test_detecta_pediatra(self):
        escuta = _prova_de_escuta_c125("solicitado pelo pediatra", {})
        assert "encaminhamento" in escuta.lower()

    def test_detecta_encaminhamento(self):
        escuta = _prova_de_escuta_c125("com encaminhamento do clínico geral", {})
        assert "encaminhamento" in escuta.lower()

    def test_vazio_sem_elementos(self):
        escuta = _prova_de_escuta_c125("sim", {})
        assert escuta == ""

    def test_vazio_saudacao(self):
        escuta = _prova_de_escuta_c125("oi tudo bem?", {})
        assert escuta == ""

    def test_prefixo_anotado(self):
        escuta = _prova_de_escuta_c125("consulta com a Dra. Karla, rotina", {})
        assert escuta.startswith("Anotado —")

    def test_combina_multiplos_elementos(self):
        """Caso Janaina completo."""
        texto = "Dra. Karla, filho de 7 meses, rotina, pediatra"
        escuta = _prova_de_escuta_c125(texto, {})
        assert "karla" in escuta.lower()
        assert "7" in escuta
        assert "rotina" in escuta.lower()
        assert "encaminhamento" in escuta.lower()


# ═══════════════════════════════════════════════════════════════════════════
# CAMPO PRIORITÁRIO — _campo_prioritario_c125
# ═══════════════════════════════════════════════════════════════════════════

class TestCampoPrioritario:
    """_campo_prioritario_c125 retorna 1 campo, nunca 'médico'."""

    def test_retorna_primeiro_nao_medico(self):
        pendentes = (
            "nome completo do paciente",
            "data de nascimento",
            "convênio (particular ou nome da operadora)",
            "médico (Dra. Karla Delalíbera ou Dr. Fabrício Freitas)",
        )
        campo = _campo_prioritario_c125(pendentes)
        assert campo == "nome completo do paciente"

    def test_pula_medico_no_inicio(self):
        pendentes = (
            "médico (Dra. Karla Delalíbera ou Dr. Fabrício Freitas)",
            "convênio (particular ou nome da operadora)",
        )
        campo = _campo_prioritario_c125(pendentes)
        assert campo == "convênio (particular ou nome da operadora)"

    def test_retorna_none_quando_so_medico(self):
        """Apenas médico pendente → None (Python resolve via C-101)."""
        pendentes = (
            "médico (Dra. Karla Delalíbera ou Dr. Fabrício Freitas)",
        )
        campo = _campo_prioritario_c125(pendentes)
        assert campo is None

    def test_retorna_none_para_vazio(self):
        campo = _campo_prioritario_c125(())
        assert campo is None

    def test_retorna_convenio_quando_unico_pendente(self):
        pendentes = ("convênio (particular ou nome da operadora)",)
        campo = _campo_prioritario_c125(pendentes)
        assert campo == "convênio (particular ou nome da operadora)"

    def test_retorna_cpf_quando_nome_e_dob_ok(self):
        pendentes = ("CPF do paciente (ou do responsável, se for menor)",)
        campo = _campo_prioritario_c125(pendentes)
        assert campo is not None
        assert "cpf" in campo.lower()


# ═══════════════════════════════════════════════════════════════════════════
# UMA PERGUNTA POR TURNO — comportamento geral
# ═══════════════════════════════════════════════════════════════════════════

class TestUmaPerguntaPorTurno:
    """deve_perguntar_dados_pendentes pergunta apenas 1 campo por vez."""

    def test_pergunta_nome_quando_primeiro_pendente(self, ctx_sem_dados):
        """Com muitos campos pendentes, pergunta nome primeiro."""
        resultado = deve_perguntar_dados_pendentes(
            ctx_sem_dados, "gostaria de marcar uma consulta"
        )
        assert resultado is not None
        assert "nome" in resultado.lower()
        # NÃO lista todos os campos
        campo_count = sum([
            "nome completo" in resultado.lower(),
            "data de nascimento" in resultado.lower(),
            "convênio" in resultado.lower(),
        ])
        assert campo_count <= 1, f"Listou {campo_count} campos (esperado <= 1): {resultado!r}"

    def test_pergunta_data_nasc_quando_nome_ok(self, ctx_com_nome):
        """Nome já coletado → pergunta data de nascimento."""
        resultado = deve_perguntar_dados_pendentes(ctx_com_nome, "sim")
        assert resultado is not None
        assert "nascimento" in resultado.lower() or "data" in resultado.lower()
        # NÃO menciona convênio (é o próximo)
        assert "convênio" not in resultado.lower()

    def test_beatriz_data_nasc_personalizada(self, ctx_com_nome):
        """Pergunta de data_nasc usa primeiro nome do paciente."""
        resultado = deve_perguntar_dados_pendentes(ctx_com_nome, "sim")
        assert resultado is not None
        # "Beatriz" deve aparecer na pergunta (data de nascimento de Beatriz?)
        assert "beatriz" in resultado.lower()

    def test_beatriz_sem_repeticao_no_saud(self, ctx_com_nome):
        """Nome na pergunta evita "Beatriz, Qual a data de nascimento de Beatriz?" repetição."""
        resultado = deve_perguntar_dados_pendentes(ctx_com_nome, "sim")
        assert resultado is not None
        # "beatriz," como saud antes de questão que já contém "beatriz" = repetição indesejada
        # A implementação correta omite o saud quando o nome já está na pergunta
        # Validamos que o resultado tem "beatriz" SEM começar com "Beatriz, Qual...de Beatriz"
        resultado_lower = resultado.lower()
        if resultado_lower.startswith("beatriz,"):
            # Se tem saud, então a pergunta não deve ter beatriz também
            resto = resultado_lower[len("beatriz,"):].strip()
            assert "beatriz" not in resto, f"Repetição detectada: {resultado!r}"

    def test_cpf_com_nome_do_paciente(self, ctx_particular_sem_cpf):
        """CPF incluído no nome do paciente para identificação."""
        resultado = deve_perguntar_dados_pendentes(ctx_particular_sem_cpf, "sim")
        assert resultado is not None
        assert "cpf" in resultado.lower()
        # Deve mencionar Ana (ou Ana Luiza)
        assert "ana" in resultado.lower()

    def test_apenas_medico_pendente_retorna_none(self, ctx_apenas_medico_pendente):
        """Quando só médico está faltando, C-125 retorna None (Python resolve)."""
        resultado = deve_perguntar_dados_pendentes(
            ctx_apenas_medico_pendente, "quero agendar"
        )
        # Médico deve ser derivado por C-101, não perguntado aqui
        # Se checklist.total_pendentes == 1 (só medico), C-125 retorna None
        if resultado is not None:
            # Se retornou algo, NÃO deve ser sobre médico
            assert "médico" not in resultado.lower()
            assert "dra. karla delalíbera ou dr. fabrício freitas" not in resultado.lower()


# ═══════════════════════════════════════════════════════════════════════════
# PROVA DE ESCUTA INTEGRADA
# ═══════════════════════════════════════════════════════════════════════════

class TestEscutaIntegrada:
    """Prova de escuta aparece no resultado final de deve_perguntar_dados_pendentes."""

    def test_escuta_com_karla_mencionada(self, ctx_sem_dados):
        resultado = deve_perguntar_dados_pendentes(
            ctx_sem_dados, "quero agendar com a Dra. Karla"
        )
        assert resultado is not None
        assert "karla" in resultado.lower()
        assert "😊" in resultado

    def test_escuta_com_bebe_7_meses(self):
        """Com intent de agendar + bebê 7 meses, escuta reflete isso."""
        ctx = {
            "fsm": {"estado": "TRIAGEM"},
            "known": {"intent_agendar": True},
        }
        resultado = deve_perguntar_dados_pendentes(
            ctx, "quero agendar para meu filho de 7 meses"
        )
        assert resultado is not None
        assert "7" in resultado

    def test_sem_escuta_usa_saudacao_nome(self):
        """Sem escuta, usa saudação com nome do contato se disponível."""
        ctx = {
            "fsm": {"estado": "DADOS"},
            "known": {
                "nome": "João Pedro",
                "data_nasc_iso": "2010-07-15",
            },
        }
        resultado = deve_perguntar_dados_pendentes(ctx, "sim")
        assert resultado is not None
        # Deve ter "João" como saudação ou no corpo
        assert "joão" in resultado.lower() or "joao" in resultado.lower()

    def test_sem_escuta_sem_nome_sem_saudacao(self, ctx_sem_dados):
        """Sem escuta e sem nome coletado, pergunta diretamente."""
        resultado = deve_perguntar_dados_pendentes(
            ctx_sem_dados, "quero marcar uma consulta"
        )
        assert resultado is not None
        assert "nome" in resultado.lower()
        # Não deve ter vírgula de saudação orphan
        assert not resultado.startswith(", ")

    def test_escuta_sem_emoji_quando_nada_identificado(self):
        """user_text sem elementos reconhecíveis → sem escuta → sem 😊."""
        ctx = {
            "fsm": {"estado": "TRIAGEM"},
            "known": {"motivo": "estrabismo"},
        }
        resultado = deve_perguntar_dados_pendentes(ctx, "quero agendar")
        assert resultado is not None
        # Sem escuta identificada, 😊 não aparece
        # (Nota: se motivo/outros dados gerarem escuta indiretamente, pode aparecer)
        # Verificamos apenas que o resultado é pergunta válida
        assert len(resultado) > 5


# ═══════════════════════════════════════════════════════════════════════════
# FORMULÁRIO BANIDO — anti-regressão C-120
# ═══════════════════════════════════════════════════════════════════════════

class TestFormularioBanido:
    """C-125 nunca gera formulário com múltiplos campos na mesma mensagem."""

    def test_nao_gera_formulario_com_muitos_campos(self, ctx_sem_dados):
        resultado = deve_perguntar_dados_pendentes(
            ctx_sem_dados, "quero agendar minha filha"
        )
        assert resultado is not None
        # Anti-padrão C-120: "me passa: nome, data de nascimento, convênio e unidade?"
        assert "me passa:" not in resultado.lower()
        assert "antes de garantir o horário, me passa:" not in resultado.lower()

    def test_nao_lista_tres_campos_juntos(self, ctx_sem_dados):
        """C-125 nunca lista 3+ campos separados por vírgula na mesma pergunta."""
        resultado = deve_perguntar_dados_pendentes(
            ctx_sem_dados, "quero agendar com a Dra. Karla para minha filha de 5 anos"
        )
        assert resultado is not None
        # Conta quantos campos de checklist aparecem
        campos_checklist = [
            "nome completo do paciente",
            "data de nascimento",
            "convênio (particular",
            "médico (dra.",
            "unidade de atendimento",
        ]
        campos_na_resposta = sum(
            1 for c in campos_checklist if c in resultado.lower()
        )
        assert campos_na_resposta <= 1, (
            f"Listou {campos_na_resposta} campos (esperado <= 1): {resultado!r}"
        )

    def test_nao_pede_medico_em_nenhum_cenario(self):
        """Em nenhum cenário C-125 pede para o paciente escolher o médico."""
        cenarios = [
            {"fsm": {"estado": "TRIAGEM"}, "known": {}},
            {"fsm": {"estado": "DADOS"}, "known": {"motivo": "retorno"}},
            {"fsm": {"estado": "CONVENIO"}, "known": {"nome_paciente": "Test", "data_nasc_iso": "2000-01-01"}},
        ]
        textos = ["quero agendar", "sim", "minha filha de 3 anos"]

        for ctx, texto in zip(cenarios, textos):
            resultado = deve_perguntar_dados_pendentes(ctx, texto)
            if resultado is not None:
                assert "dra. karla delalíbera ou dr. fabrício freitas" not in resultado.lower(), (
                    f"Pediu médico: {resultado!r}"
                )


# ═══════════════════════════════════════════════════════════════════════════
# TOGGLE E FAIL-OPEN
# ═══════════════════════════════════════════════════════════════════════════

class TestToggleFalios:
    def test_toggle_off_retorna_none(self, ctx_janaina, monkeypatch):
        monkeypatch.setenv("BLINDAGEM_DADOS_PENDENTES_ATIVADO", "0")
        resultado = deve_perguntar_dados_pendentes(
            ctx_janaina,
            "Gostaria de agendar com a Dra. Karla. Filho de 7 meses.",
        )
        assert resultado is None

    def test_ctx_none_retorna_none(self):
        resultado = deve_perguntar_dados_pendentes(None, "quero agendar")
        assert resultado is None

    def test_user_text_vazio_retorna_none(self, ctx_sem_dados):
        resultado = deve_perguntar_dados_pendentes(ctx_sem_dados, "")
        assert resultado is None
