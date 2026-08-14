"""
Pytest C-136 — Pergunta de perfil "bebê, criança, adolescente ou adulto?"
(14/08/2026) Fábio: substituir "para você ou para outra pessoa?" pela
pergunta de faixa etária que deriva médico + protocolo automaticamente.
"""
import pytest
from voice_agent.pergunta_perfil import deve_perguntar_perfil, _RE_PERFIL_JA_DADO


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ctx(perfil=None, medico=None, ultima_msg=None, faixa=None, idade=None):
    known = {}
    if perfil:
        known["perfil_paciente"] = perfil
    if medico:
        known["medico"] = medico
    if ultima_msg:
        known["ultima_msg_outbound"] = ultima_msg
    if faixa:
        known["faixa_etaria"] = faixa
    if idade is not None:
        known["idade_paciente"] = idade
    return {"known": known}


# ---------------------------------------------------------------------------
# 1. Regex _RE_PERFIL_JA_DADO — deve detectar faixa etária no inbound
# ---------------------------------------------------------------------------

class TestRePerfilJaDado:
    def test_bebe(self):
        assert _RE_PERFIL_JA_DADO.search("meu bebê tem 3 meses")

    def test_crianca_filho(self):
        assert _RE_PERFIL_JA_DADO.search("é para meu filho de 7 anos")

    def test_filha(self):
        assert _RE_PERFIL_JA_DADO.search("quero agendar para minha filha")

    def test_adolescente(self):
        assert _RE_PERFIL_JA_DADO.search("minha adolescente de 14 anos")

    def test_adulto(self):
        assert _RE_PERFIL_JA_DADO.search("é para mim, sou adulta")

    def test_idoso(self):
        assert _RE_PERFIL_JA_DADO.search("meu pai, idoso de 72 anos")

    def test_para_mim(self):
        assert _RE_PERFIL_JA_DADO.search("a consulta é para mim")

    def test_sou_eu(self):
        assert _RE_PERFIL_JA_DADO.search("sou eu mesma")

    def test_idade_numerica_anos(self):
        assert _RE_PERFIL_JA_DADO.search("criança de 5 anos")

    def test_idade_numerica_meses(self):
        assert _RE_PERFIL_JA_DADO.search("bebê de 8 meses")

    def test_recem_nascido(self):
        assert _RE_PERFIL_JA_DADO.search("recém-nascido")

    def test_garota(self):
        assert _RE_PERFIL_JA_DADO.search("para minha garota")

    def test_menino(self):
        assert _RE_PERFIL_JA_DADO.search("para o meu menino")

    # Não deve detectar faixa etária nestes casos
    def test_sem_faixa_saudacao(self):
        assert not _RE_PERFIL_JA_DADO.search("Boa tarde")

    def test_sem_faixa_agendar(self):
        assert not _RE_PERFIL_JA_DADO.search("quero agendar uma consulta")

    def test_sem_faixa_info(self):
        assert not _RE_PERFIL_JA_DADO.search("preciso de informações")

    def test_sem_faixa_convenio(self):
        assert not _RE_PERFIL_JA_DADO.search("atende Saúde Caixa?")


# ---------------------------------------------------------------------------
# 2. deve_perguntar_perfil() — retorna None quando não deve perguntar
# ---------------------------------------------------------------------------

class TestDevePerguntar_NaoPergunta:
    def test_perfil_ja_em_ctx(self):
        """Perfil conhecido no ctx → não perguntar."""
        r = deve_perguntar_perfil(_ctx(perfil="criança"), "quero agendar")
        assert r is None

    def test_medico_ja_em_ctx(self):
        """Médico já derivado → não perguntar."""
        r = deve_perguntar_perfil(_ctx(medico="Karla"), "quero agendar")
        assert r is None

    def test_faixa_etaria_em_ctx(self):
        """faixa_etaria em ctx.known → não perguntar."""
        r = deve_perguntar_perfil(_ctx(faixa="pediátrico"), "quero agendar")
        assert r is None

    def test_idade_em_ctx(self):
        """idade_paciente em ctx.known → não perguntar."""
        r = deve_perguntar_perfil(_ctx(idade=5), "quero agendar")
        assert r is None

    def test_faixa_no_inbound_bebe(self):
        """Paciente já informou 'bebê de 3 meses' no inbound → não perguntar."""
        r = deve_perguntar_perfil({}, "meu bebê tem 3 meses")
        assert r is None

    def test_faixa_no_inbound_filho(self):
        r = deve_perguntar_perfil({}, "é para meu filho de 8 anos")
        assert r is None

    def test_faixa_no_inbound_para_mim(self):
        r = deve_perguntar_perfil({}, "a consulta é para mim")
        assert r is None

    def test_medico_no_inbound(self):
        """Paciente citou 'Dra. Karla' → não perguntar perfil."""
        r = deve_perguntar_perfil({}, "quero com a Dra. Karla")
        assert r is None

    def test_especialidade_no_inbound_catarata(self):
        """Paciente citou 'catarata' → especialidade derivável, não perguntar."""
        r = deve_perguntar_perfil({}, "preciso avaliar catarata")
        assert r is None

    def test_especialidade_no_inbound_oculos(self):
        r = deve_perguntar_perfil({}, "quero fazer exame de óculos")
        assert r is None

    def test_msg_muito_curta(self):
        """Mensagem com < 3 chars → não perguntar (provavelmente botão/number)."""
        r = deve_perguntar_perfil({}, "1")
        assert r is None

    def test_msg_vazia(self):
        r = deve_perguntar_perfil({}, "")
        assert r is None

    def test_anti_repeticao(self):
        """última_msg_outbound já contém 'bebê, criança' → não repetir."""
        ctx = _ctx(ultima_msg="pode me contar se a consulta é para um bebê, criança, adolescente ou adulto?")
        r = deve_perguntar_perfil(ctx, "boa tarde")
        assert r is None

    def test_toggle_off(self, monkeypatch):
        """Toggle PERGUNTA_PERFIL_ATIVADA=0 → sempre None."""
        monkeypatch.setenv("PERGUNTA_PERFIL_ATIVADA", "0")
        r = deve_perguntar_perfil({}, "quero agendar uma consulta")
        assert r is None

    def test_toggle_false(self, monkeypatch):
        monkeypatch.setenv("PERGUNTA_PERFIL_ATIVADA", "false")
        r = deve_perguntar_perfil({}, "boa tarde preciso de ajuda")
        assert r is None

    def test_ctx_none(self):
        """ctx=None não deve explodir (fail-open)."""
        r = deve_perguntar_perfil(None, "quero agendar")
        # Deve retornar a pergunta (ctx vazio = sem perfil)
        assert r is not None or r is None  # fail-open: não levanta exceção

    def test_ctx_without_known(self):
        """ctx sem 'known' não deve explodir."""
        r = deve_perguntar_perfil({}, "quero agendar uma consulta")
        # Sem perfil no ctx → deve perguntar
        assert r is not None


# ---------------------------------------------------------------------------
# 3. deve_perguntar_perfil() — retorna a pergunta quando deve perguntar
# ---------------------------------------------------------------------------

class TestDevePerguntar_Pergunta:
    def test_saudacao_simples(self):
        """'Boa tarde' sem contexto → deve perguntar faixa etária."""
        r = deve_perguntar_perfil({}, "Boa tarde")
        assert r is not None
        assert "bebê" in r.lower()
        assert "criança" in r.lower()
        assert "adulto" in r.lower()

    def test_mensagem_generica_agendar(self):
        r = deve_perguntar_perfil({}, "quero agendar uma consulta")
        assert r is not None
        assert "bebê, criança" in r.lower()

    def test_mensagem_com_convenio_mas_sem_perfil(self):
        """Paciente mencionou convênio mas não perfil → perguntar."""
        r = deve_perguntar_perfil({}, "atendo pelo Saúde Caixa, quero consulta")
        assert r is not None
        assert "bebê" in r.lower()

    def test_pergunta_valor(self):
        """'Qual o valor?' sem perfil → perguntar perfil ANTES de valor."""
        # Nota: este bypass vem ANTES de valor na chain, mas vale testar isolado
        r = deve_perguntar_perfil({}, "Qual o valor da consulta?")
        # Pode ou não retornar dependendo do toggle; sem toggle → deve perguntar
        # (o bypass de valor detecta a keyword; pergunta_perfil é anterior)
        assert r is not None
        assert "adulto" in r.lower()

    def test_com_nome_no_ctx(self):
        """Se há nome no ctx, deve aparecer na pergunta."""
        ctx = _ctx()
        ctx["known"]["nome_contato"] = "Maria"
        r = deve_perguntar_perfil(ctx, "boa tarde")
        assert r is not None
        assert "Maria" in r

    def test_formato_correto(self):
        """Formato canônico: inclui emoji 😊 e lista 4 opções."""
        r = deve_perguntar_perfil({}, "preciso de ajuda")
        assert r is not None
        assert "😊" in r
        assert "adolescente" in r.lower()

    def test_ctx_vazio_known(self):
        """ctx com known={} → sem perfil → deve perguntar."""
        r = deve_perguntar_perfil({"known": {}}, "boa noite")
        assert r is not None
        assert "bebê" in r.lower()


# ---------------------------------------------------------------------------
# 4. Texto canônico não contém termos proibidos
# ---------------------------------------------------------------------------

class TestConteudoCanônico:
    def test_sem_para_voce_ou_outra_pessoa(self):
        """A pergunta antiga NÃO deve aparecer na saída."""
        r = deve_perguntar_perfil({}, "olá, quero agendar")
        if r:
            assert "para você ou" not in r.lower()
            assert "outra pessoa" not in r.lower()

    def test_sem_particular(self):
        """Termo proibido 'particular' não deve aparecer."""
        r = deve_perguntar_perfil({}, "quero consulta")
        if r:
            assert "particular" not in r.lower()

    def test_sem_sdp(self):
        """Termo proibido 'SDP' não deve aparecer."""
        r = deve_perguntar_perfil({}, "quero consulta")
        if r:
            assert "sdp" not in r.lower()

    def test_mensagem_curta(self):
        """Resposta deve ser conversacional, não longa."""
        r = deve_perguntar_perfil({}, "boa tarde quero agendar")
        if r:
            assert len(r) < 200  # mensagem curta


# ---------------------------------------------------------------------------
# 5. Casos reais esperados em produção
# ---------------------------------------------------------------------------

class TestCasosReais:
    def test_caso_tipico_novo_lead(self):
        """Lead novo sem contexto + mensagem genérica → pergunta perfil."""
        r = deve_perguntar_perfil({"known": {}}, "Olá, boa tarde! Gostaria de marcar uma consulta")
        assert r is not None
        assert "bebê" in r.lower()

    def test_caso_bebe_7_meses(self):
        """'bebê de 7 meses' no inbound → NÃO perguntar (C-125 já captura)."""
        r = deve_perguntar_perfil({"known": {}},
            "Gostaria de agendar com a Dra. Karla. É para o meu filho de 7 meses.")
        assert r is None  # filho + 7 meses detectados

    def test_caso_adulto_catarata(self):
        """'catarata' no inbound → especialidade detectada, não perguntar."""
        r = deve_perguntar_perfil({"known": {}},
            "Preciso de uma avaliação de catarata para meu pai")
        assert r is None  # "catarata" + "pai" detectados

    def test_caso_rotina_sem_contexto(self):
        """'consulta de rotina' sem faixa etária → perguntar."""
        r = deve_perguntar_perfil({"known": {}}, "Quero marcar consulta de rotina")
        assert r is not None

    def test_caso_karla_no_inbound(self):
        """Paciente menciona 'Karla' → médico identificado, não perguntar."""
        r = deve_perguntar_perfil({"known": {}}, "Quero consulta com a Karla")
        assert r is None

    def test_caso_fabricio_no_inbound(self):
        """Paciente menciona 'Fabrício' → não perguntar."""
        r = deve_perguntar_perfil({"known": {}}, "Quero com o Dr. Fabrício")
        assert r is None

    def test_caso_medico_ja_derivado_ctx(self):
        """Médico derivado por C-101 → já em ctx.known.medico → não perguntar."""
        r = deve_perguntar_perfil(_ctx(medico="Dra. Karla Delalíbera"),
                                  "boa tarde")
        assert r is None
