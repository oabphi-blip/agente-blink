"""Pytest dos geradores do ciclo de comunicação pós-agendamento (task #89).

Cobre:
  - formatação de data (PT-BR sem locale)
  - geradores D-3 / D-1 / D-0 / no-show
  - personalização (nome paciente, médico, unidade, data, hora)
  - instruções específicas por médico
  - pendências de documentos / sinal
  - vocabulário vetado ausente
  - link Maps presente
  - sequencia completa devolve as 4 chaves
"""
from __future__ import annotations

from datetime import date, datetime

import pytest

from voice_agent.mensagens_ciclo import (
    DURACAO_SLOT_MIN_POR_MEDICO,
    DURACAO_SLOT_PADRAO_MIN,
    ENDERECO_AGUAS_CLARAS,
    ENDERECO_ASA_NORTE,
    MAPS_AGUAS_CLARAS,
    MAPS_ASA_NORTE,
    UNIDADES,
    duracao_slot_min,
    formatar_data_completa,
    formatar_data_curta,
    formatar_intervalo_consulta,
    gerar_sequencia_completa,
    hora_termino_estimada,
    render_d0_lembrete,
    render_d1_localizacao,
    render_d3_confirmacao,
    render_noshow_check,
    validar_todas,
)
from voice_agent.mensagens_janela import _PALAVRAS_VETADAS


# ---------------------------------------------------------------------------
# Formatação de data
# ---------------------------------------------------------------------------

class TestFormatarData:

    def test_sexta_feira_06_06_2026(self):
        # 06/06/2026 é um sábado — vamos validar dia correto.
        # Verificação: datetime.date(2026, 6, 5).weekday() == 4 (sexta).
        assert formatar_data_completa("2026-06-05") == "sexta-feira, 05/06/2026"

    def test_aceita_date_object(self):
        assert formatar_data_completa(date(2026, 6, 5)) == "sexta-feira, 05/06/2026"

    def test_aceita_formato_br(self):
        assert formatar_data_completa("05/06/2026") == "sexta-feira, 05/06/2026"

    def test_data_invalida_devolve_fallback(self):
        assert formatar_data_completa("abc") == "abc"
        assert formatar_data_completa("") == ""
        assert formatar_data_completa(None) == ""

    def test_curto_inclui_dia_e_data(self):
        out = formatar_data_curta("2026-06-05")
        assert "sexta" in out
        assert "05/06" in out


# ---------------------------------------------------------------------------
# Unidades
# ---------------------------------------------------------------------------

class TestUnidades:

    def test_asa_norte_tem_endereco_e_maps(self):
        info = UNIDADES["asa norte"]
        assert "Medical Center" in info["endereco"]
        assert "google.com/maps" in info["maps"]

    def test_aguas_claras_tem_endereco_e_maps(self):
        info = UNIDADES["águas claras"]
        assert "Felicittá" in info["endereco"]
        assert "google.com/maps" in info["maps"]


# ---------------------------------------------------------------------------
# D-3 (confirmação prévia)
# ---------------------------------------------------------------------------

class TestD3:

    def _base(self, **over):
        kwargs = dict(
            primeiro_nome_contato="marcela", nome_paciente="Marcela Almeida Souza",
            medico="Dra. Karla Delalíbera", unidade="Asa Norte",
            data="2026-06-05", hora="14:30",
        )
        kwargs.update(over)
        return render_d3_confirmacao(**kwargs)

    def test_inclui_nome_paciente_e_medico(self):
        msg = self._base()
        assert "Marcela Almeida Souza" in msg
        assert "Dra. Karla Delalíbera" in msg
        assert "Asa Norte" in msg

    def test_personaliza_primeiro_nome_contato(self):
        msg = self._base(primeiro_nome_contato="marcela")
        assert "Olá, Marcela!" in msg

    def test_inclui_data_completa_e_hora(self):
        msg = self._base()
        assert "sexta-feira, 05/06/2026" in msg
        assert "14:30" in msg

    def test_convenio_mostrado_quando_existe(self):
        msg = self._base(convenio="Saúde Caixa")
        assert "Saúde Caixa" in msg

    def test_convenio_nao_se_aplica_omitido(self):
        msg = self._base(convenio="Sem convênio")
        assert "Convênio" not in msg or "🏥" not in msg

    def test_documentos_pendentes_listados(self):
        msg = self._base(
            convenio="Saúde Caixa", convenio_documentos_pendentes=True
        )
        assert "carteirinha" in msg.lower()
        assert "documento de identidade" in msg.lower()

    def test_sinal_pendente_com_valor(self):
        msg = self._base(sinal_pendente=True, valor_sinal="305,50")
        assert "305,50" in msg
        assert "Reserva Imediata" in msg
        assert "Fila de Encaixe" in msg

    def test_sinal_pendente_sem_valor(self):
        msg = self._base(sinal_pendente=True)
        assert "sinal" in msg.lower()

    def test_sem_pendencias_nao_mostra_secao(self):
        msg = self._base()
        assert "Para manter sua reserva confirmada" not in msg


# ---------------------------------------------------------------------------
# D-1 (localização)
# ---------------------------------------------------------------------------

class TestD1:

    def _base(self, **over):
        kwargs = dict(
            primeiro_nome_contato="marcela", nome_paciente="Marcela Almeida Souza",
            medico="Dra. Karla Delalíbera", unidade="Asa Norte",
            data="2026-06-05", hora="14:30",
        )
        kwargs.update(over)
        return render_d1_localizacao(**kwargs)

    def test_inclui_endereco_asa_norte(self):
        msg = self._base()
        assert "Medical Center" in msg
        assert "Asa Norte" in msg

    def test_inclui_link_maps(self):
        msg = self._base()
        assert "google.com/maps" in msg

    def test_aguas_claras_usa_endereco_correto(self):
        msg = self._base(unidade="Águas Claras")
        assert "Felicittá" in msg

    def test_call_to_action_confirmar_reagendar(self):
        msg = self._base()
        assert "confirmo" in msg.lower()
        assert "reagendar" in msg.lower()

    def test_NAO_inventa_orientacao_catarata_fabricio(self):
        # Task #92: removidas todas as orientações chutadas pela IA.
        msg = self._base(
            medico="Dr. Fabrício Freitas",
            motivo="Pré-operatório catarata",
        )
        baixo = msg.lower()
        for proibido in ("acompanhada", "acompanhado", "jejum",
                          "pausa de", "medicamento"):
            assert proibido not in baixo, (
                f"orientação não-verificada vazou: {proibido!r}"
            )

    def test_NAO_inventa_orientacao_pediatria_karla(self):
        msg = self._base(
            medico="Dra. Karla Delalíbera",
            motivo="primeira consulta da criança",
        )
        baixo = msg.lower()
        for proibido in ("brinquedo", "lanche"):
            assert proibido not in baixo, (
                f"orientação não-verificada vazou: {proibido!r}"
            )

    def test_NAO_inventa_duracao_em_orientacao_karla(self):
        # Reforço: duração só no header, nunca como orientação.
        msg = self._base(
            medico="Dra. Karla Delalíbera",
            motivo="primeira consulta da criança",
        )
        for fraseado in ("1h", "1h30", "1 hora", "2 horas", "duas horas",
                          "1 hora e 30"):
            assert fraseado not in msg.lower(), (
                f"orientação não pode citar duração inventada: {fraseado!r}"
            )

    def test_NAO_inventa_duracao_em_orientacao_sdp(self):
        msg = self._base(
            medico="Dra. Karla Delalíbera",
            motivo="SDP avaliação",
        )
        for fraseado in ("2 horas", "duas horas", "1h30"):
            assert fraseado not in msg.lower()

    def test_NAO_inventa_orientacao_retina_katia(self):
        msg = self._base(
            medico="Dra. Kátia Delalíbera",
            motivo="mapeamento retina",
        )
        baixo = msg.lower()
        for proibido in ("dilatação", "dilataçao", "embaçada", "embacada"):
            assert proibido not in baixo, (
                f"orientação não-verificada vazou: {proibido!r}"
            )

    def test_lembrete_documentos_quando_pendente(self):
        msg = self._base(convenio_documentos_pendentes=True)
        assert "carteirinha" in msg.lower()


# ---------------------------------------------------------------------------
# D-0 (lembrete matinal)
# ---------------------------------------------------------------------------

class TestD0:

    def test_bom_dia_com_nome(self):
        msg = render_d0_lembrete(
            primeiro_nome_contato="marcela",
            nome_paciente="Marcela Souza",
            medico="Dra. Karla Delalíbera", unidade="Asa Norte",
            hora="14:30",
        )
        assert msg.startswith("Bom dia, Marcela!")

    def test_inclui_paciente_medico_hora_unidade(self):
        msg = render_d0_lembrete(
            primeiro_nome_contato="ana",
            nome_paciente="João Costa", medico="Dr. Fabrício Freitas",
            unidade="Águas Claras", hora="09:00",
        )
        assert "João Costa" in msg
        assert "Dr. Fabrício Freitas" in msg
        assert "09:00" in msg
        assert "Águas Claras" in msg

    def test_sem_nome_usa_bom_dia_neutro(self):
        msg = render_d0_lembrete(
            primeiro_nome_contato="",
            nome_paciente="X", medico="Y", unidade="Asa Norte", hora="10:00",
        )
        assert msg.startswith("Bom dia!")

    def test_orienta_chegar_antes(self):
        msg = render_d0_lembrete(
            primeiro_nome_contato="ana", nome_paciente="X", medico="Y",
            unidade="Asa Norte", hora="10:00",
        )
        assert "antes" in msg.lower()


# ---------------------------------------------------------------------------
# Check no-show
# ---------------------------------------------------------------------------

class TestNoShow:

    def test_menciona_paciente_medico_hora(self):
        msg = render_noshow_check(
            primeiro_nome_contato="marcela",
            nome_paciente="Marcela Souza",
            medico="Dra. Karla Delalíbera", hora="14:30",
        )
        assert "Marcela Souza" in msg
        assert "Dra. Karla Delalíbera" in msg
        assert "14:30" in msg

    def test_oferece_3_opcoes(self):
        msg = render_noshow_check(
            primeiro_nome_contato="x", nome_paciente="X", medico="Y", hora="10:00",
        )
        assert "1" in msg
        assert "2" in msg
        assert "3" in msg
        assert "chegando" in msg.lower()
        assert "reagendar" in msg.lower()


# ---------------------------------------------------------------------------
# Vocabulário Blink em TODAS as mensagens
# ---------------------------------------------------------------------------

class TestVocabularioCiclo:

    @pytest.fixture
    def todas_as_mensagens(self):
        return gerar_sequencia_completa(
            primeiro_nome_contato="marcela",
            nome_paciente="Marcela Almeida Souza",
            medico="Dra. Karla Delalíbera",
            unidade="Asa Norte",
            data="2026-06-05", hora="14:30",
            convenio="Saúde Caixa",
            motivo="rotina pediátrica",
            convenio_documentos_pendentes=True,
            sinal_pendente=False,
        )

    def test_nenhuma_mensagem_tem_palavra_vetada(self, todas_as_mensagens):
        for chave, msg in todas_as_mensagens.items():
            baixo = msg.lower()
            for palavra in _PALAVRAS_VETADAS:
                # "particular" precisa de match palavra inteira
                # (evita falso positivo em "particularmente")
                import re as _re
                if _re.search(rf"\b{_re.escape(palavra)}\b", baixo):
                    pytest.fail(
                        f"{chave}: palavra vetada {palavra!r} encontrada"
                    )

    def test_validador_aprova_todas(self, todas_as_mensagens):
        resultado = validar_todas(todas_as_mensagens)
        for chave, v in resultado.items():
            assert v["ok"], f"{chave} falhou: {v['violacoes']}"


# ---------------------------------------------------------------------------
# Sequência completa
# ---------------------------------------------------------------------------

class TestDuracaoSlot:
    """Fábio definiu em 31/05/2026 (task #90):
       - Karla    → 30 min
       - Fabrício → 40 min
       - Kátia    → 30 min (default)
    """

    def test_karla_30min(self):
        assert duracao_slot_min("Dra. Karla Delalíbera") == 30
        assert duracao_slot_min("dra karla") == 30
        assert duracao_slot_min("KARLA") == 30

    def test_fabricio_40min(self):
        assert duracao_slot_min("Dr. Fabrício Freitas") == 40
        assert duracao_slot_min("dr fabricio freitas") == 40
        assert duracao_slot_min("Fabricio") == 40
        assert duracao_slot_min("Fabrício") == 40

    def test_katia_30min(self):
        assert duracao_slot_min("Dra. Kátia Delalíbera") == 30
        assert duracao_slot_min("dra. katia") == 30

    def test_desconhecido_usa_padrao(self):
        assert duracao_slot_min("Dr. Aleatório") == DURACAO_SLOT_PADRAO_MIN

    def test_none_e_vazio_usam_padrao(self):
        assert duracao_slot_min(None) == DURACAO_SLOT_PADRAO_MIN
        assert duracao_slot_min("") == DURACAO_SLOT_PADRAO_MIN

    def test_dict_tem_pelo_menos_3_medicos(self):
        # Sentinela contra remoção acidental.
        assert "karla" in DURACAO_SLOT_MIN_POR_MEDICO
        assert "fabricio" in DURACAO_SLOT_MIN_POR_MEDICO
        assert "katia" in DURACAO_SLOT_MIN_POR_MEDICO

    def test_decisao_oficial_fabio_31_05_2026(self):
        """SENTINELA: estes valores foram confirmados pelo Fábio em 31/05/2026
        baseados na configuração ATUAL do Medware. Se algum deles mudar:

          1. Confirmar nova duração no Medware (fonte de verdade).
          2. Atualizar DURACAO_SLOT_MIN_POR_MEDICO no mensagens_ciclo.py.
          3. Atualizar a decisão neste teste com a nova data.
          4. Atualizar handoff e CLAUDE.md.

        Quem mexer só em um lugar e tentar passar build, falha aqui."""
        assert duracao_slot_min("Dra. Karla Delalíbera") == 30, (
            "Karla 30min — não cobre só rotina, cobre TAMBÉM SDP/Prisma "
            "e oftalmopediatria. Slot único Medware."
        )
        assert duracao_slot_min("Dr. Fabrício Freitas") == 40, (
            "Fabrício 40min — vale para avaliação E pós-op de catarata "
            "(mesmo slot Medware)."
        )
        assert duracao_slot_min("Dra. Kátia Delalíbera") == 30, (
            "Kátia em pausa em 31/05/2026 — 30min é placeholder; "
            "revisar quando voltar a atender."
        )


class TestHoraTermino:

    def test_14_30_mais_30_e_15_00(self):
        assert hora_termino_estimada("14:30", 30) == "15:00"

    def test_14_30_mais_40_e_15_10(self):
        assert hora_termino_estimada("14:30", 40) == "15:10"

    def test_aceita_formato_com_h(self):
        assert hora_termino_estimada("09h00", 40) == "09:40"

    def test_meia_noite_rollover(self):
        assert hora_termino_estimada("23:50", 30) == "00:20"

    def test_hora_invalida_devolve_none(self):
        assert hora_termino_estimada("25:00", 30) is None
        assert hora_termino_estimada("abc", 30) is None
        assert hora_termino_estimada("", 30) is None

    def test_duracao_zero_ou_negativa_devolve_none(self):
        assert hora_termino_estimada("14:00", 0) is None
        assert hora_termino_estimada("14:00", -5) is None


class TestFormatarIntervaloConsulta:

    def test_karla_14_30_renderiza_15_00_30min(self):
        out = formatar_intervalo_consulta("14:30", "Dra. Karla Delalíbera")
        assert "14:30" in out
        assert "15:00" in out
        assert "30 min" in out

    def test_fabricio_09_00_renderiza_09_40_40min(self):
        out = formatar_intervalo_consulta("09:00", "Dr. Fabrício Freitas")
        assert "09:00" in out
        assert "09:40" in out
        assert "40 min" in out

    def test_hora_invalida_devolve_so_inicio_e_duracao(self):
        out = formatar_intervalo_consulta("abc", "Dra. Karla")
        assert "abc" in out
        assert "30 min" in out


class TestDuracaoNasMensagens:
    """Garante que a duração real aparece no header das 3 mensagens
    (D-3, D-1, D-0) e foi calculada pelo médico — não inventada."""

    def test_d3_karla_mostra_30min(self):
        msg = render_d3_confirmacao(
            primeiro_nome_contato="x", nome_paciente="X",
            medico="Dra. Karla Delalíbera", unidade="Asa Norte",
            data="2026-06-05", hora="14:30",
        )
        assert "14:30 às 15:00" in msg
        assert "30 min" in msg

    def test_d3_fabricio_mostra_40min(self):
        msg = render_d3_confirmacao(
            primeiro_nome_contato="x", nome_paciente="X",
            medico="Dr. Fabrício Freitas", unidade="Águas Claras",
            data="2026-06-12", hora="09:00",
        )
        assert "09:00 às 09:40" in msg
        assert "40 min" in msg

    def test_d1_fabricio_mostra_40min(self):
        msg = render_d1_localizacao(
            primeiro_nome_contato="x", nome_paciente="X",
            medico="Dr. Fabrício Freitas", unidade="Águas Claras",
            data="2026-06-12", hora="09:00",
        )
        assert "09:40" in msg
        assert "40 min" in msg

    def test_d0_karla_mostra_30min(self):
        msg = render_d0_lembrete(
            primeiro_nome_contato="x", nome_paciente="X",
            medico="Dra. Karla Delalíbera", unidade="Asa Norte",
            hora="14:30",
        )
        assert "15:00" in msg
        assert "30 min" in msg


class TestSequenciaCompleta:

    def test_devolve_4_chaves(self):
        seq = gerar_sequencia_completa(
            primeiro_nome_contato="x", nome_paciente="X", medico="Y",
            unidade="Asa Norte", data="2026-06-05", hora="10:00",
        )
        assert set(seq.keys()) == {"D-3", "D-1", "D-0", "no-show"}

    def test_cada_mensagem_eh_string_nao_vazia(self):
        seq = gerar_sequencia_completa(
            primeiro_nome_contato="x", nome_paciente="X", medico="Y",
            unidade="Asa Norte", data="2026-06-05", hora="10:00",
        )
        for chave, msg in seq.items():
            assert isinstance(msg, str), f"{chave} não é string"
            assert msg.strip(), f"{chave} está vazia"
