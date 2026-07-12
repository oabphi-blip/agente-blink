"""Bug C-43 (Fábio 12/07/2026) — Mariana Lopes lead 22617170.

Sintoma:
    Lia entrou em loop de hesitação em lead da etapa 2.1 campanha agosto
    (status_id 108749463 — etapa nova, criada pelo Fábio).
    Última msg outbound: "nossa agenda está fora do ar neste exato momento"
    Fato: Medware estava UP, agenda tinha slots disponíveis.

Causas raiz (2 simultâneas):

1. **Etapa 108749463 fora do STATUS_ATIVOS_IA** — o webhook.py não
   reconhecia essa etapa, então caía em fluxo genérico sem contexto.

2. **Convênio "Afego" não mapeado no PLANO_CODES** — Kommo grava
   "Afego" (1 F) mas Medware espera "AFFEGO" (2 F). Faltava alias.

Fix aplicado no commit 2f3af92 (12/07/2026 08:00):
    - voice_agent/webhook.py: status 108749463 adicionado nas 2
      políticas ATIVOS_IA.
    - voice_agent/medware.py: PLANO_CODES ganhou "afego": 7, "affeg": 7.

Estes testes garantem que essas 2 correções NUNCA saiam do código.
"""
from __future__ import annotations

import pytest


class TestStatus108749463EmAtivosIA:
    """Bug C-43 causa raiz 1 — etapa nova não estava em ATIVOS_IA."""

    def test_status_campanha_agosto_ativa_ia_em_ambas_politicas(self):
        """Le webhook.py e confirma que 108749463 aparece em ambos os
        blocos _STATUS_ATIVOS_IA (politica simplificada + rollback antiga).

        Sem isso, Lia cai em fallback genérico e mente "agenda fora do ar".
        """
        webhook_src = open(
            "voice_agent/webhook.py", encoding="utf-8",
        ).read()

        # Deve aparecer AO MENOS 2 vezes (uma em cada politica)
        n = webhook_src.count("108749463")
        assert n >= 2, (
            f"status 108749463 (campanha agosto) precisa estar nas 2 "
            f"politicas ATIVOS_IA. Encontrado {n}x — bug C-43 vai "
            f"reincidir."
        )

    def test_status_campanha_agosto_tem_comentario_referencia(self):
        """Aceita comentário 'campanha agosto' OR 'C-43' na linha do
        status pra futura auditoria."""
        webhook_src = open(
            "voice_agent/webhook.py", encoding="utf-8",
        ).read()

        # Procura linha com 108749463 e comentário
        for linha in webhook_src.splitlines():
            if "108749463" in linha:
                assert (
                    "campanha" in linha.lower()
                    or "c-43" in linha.lower()
                    or "agosto" in linha.lower()
                ), (
                    f"Linha com 108749463 sem comentário de referência: "
                    f"{linha!r}"
                )


class TestAfegoMapeadoNoMedware:
    """Bug C-43 causa raiz 2 — Afego (Kommo) → AFFEGO (Medware codPlano 7)."""

    def test_afego_com_um_F_mapeia_codplano_7(self):
        """Le medware.py PLANO_CODES e confirma que 'afego' -> 7."""
        from voice_agent.medware import PLANO_CODES

        assert "afego" in PLANO_CODES, (
            "PLANO_CODES precisa ter 'afego' (Kommo grava com 1 F). "
            "Sem isso, gravacao Medware falha pra Mariana Lopes e "
            "todos os leads com esse convenio."
        )
        assert PLANO_CODES["afego"] == 7, (
            f"'afego' deve mapear pra codPlano 7 (AFFEGO no Medware). "
            f"Retornou {PLANO_CODES['afego']}"
        )

    def test_affego_com_dois_F_tambem_mapeia_codplano_7(self):
        """Compat: se paciente digitar 'AFFEGO' com 2 F, também deve funcionar."""
        from voice_agent.medware import PLANO_CODES

        assert PLANO_CODES.get("affego") == 7


class TestFraseAgendaForaDoAr:
    """Bug C-43 sintoma — Lia mentiu 'agenda fora do ar'.

    Essa frase já está bloqueada pelo oferta_deterministica.FRASES_BANIDAS
    (verificado no push do MEGA SPRINT). Este teste garante que continua
    bloqueada.
    """

    def test_frase_fora_do_ar_esta_banida(self):
        from voice_agent.oferta_deterministica import FRASES_BANIDAS

        assert "fora do ar" in FRASES_BANIDAS, (
            "'fora do ar' precisa estar em FRASES_BANIDAS. Bug C-43 "
            "Mariana Lopes 22617170 (11/07 18:55): Lia escreveu "
            "'nossa agenda está fora do ar' quando Medware estava UP."
        )

    def test_frase_reconferir_calendario_esta_banida(self):
        """Variante 'reconferir com o calendario' — capturada no mesmo
        chat da Mariana Lopes."""
        from voice_agent.oferta_deterministica import FRASES_BANIDAS

        # Confere qualquer variante — o filtro faz `frase in texto.lower()`
        variantes = [
            "reconferir",
            "reconferir com o calendário",
            "reconferir com o calendario",
        ]
        for v in variantes:
            assert v in FRASES_BANIDAS, (
                f"Frase banida '{v}' saiu do FRASES_BANIDAS. Bug C-43 "
                f"reincidirá."
            )


class TestChatMarianaLopesComoAsserçãoLiteral:
    """Cada mensagem que a Lia escreveu no chat 40968 lead 22617170.

    Se qualquer uma dessas frases aparecer no texto gerado pelo
    oferta_deterministica.montar_texto_2_slots, o bug retornou.
    """

    def _ctx_mariana_lopes(self) -> dict:
        return {
            "fsm": {"estado": "AGENDA"},
            "ja_agendado": False,
            "known": {
                "nome_paciente": "Mariana Lopes Gomes",
                "data_nascimento": "2014-05-19",
                "convenio": "Afego",
                "medico": "Dra. Karla Delalibera",
                "unidade": "Águas Claras",
                "dia_turno": "Terça-feira — inicio tarde",
            },
        }

    def _slots_disponiveis(self) -> list[dict]:
        # Slots reais confirmados no Medware 12/07/2026 08:00
        return [
            {"data_iso": "2026-08-11", "hora": "15:00"},
            {"data_iso": "2026-08-11", "hora": "15:30"},
            {"data_iso": "2026-08-11", "hora": "16:00"},
        ]

    def test_saida_contem_11_08_e_15h(self):
        from voice_agent.oferta_deterministica import montar_texto_2_slots

        texto = montar_texto_2_slots(
            self._slots_disponiveis(), self._ctx_mariana_lopes(),
        )
        assert "11/08" in texto
        assert "15h" in texto

    def test_saida_nao_contem_fora_do_ar(self):
        from voice_agent.oferta_deterministica import montar_texto_2_slots

        texto = montar_texto_2_slots(
            self._slots_disponiveis(), self._ctx_mariana_lopes(),
        )
        assert "fora do ar" not in texto.lower()

    def test_saida_nao_contem_reconferir(self):
        from voice_agent.oferta_deterministica import montar_texto_2_slots

        texto = montar_texto_2_slots(
            self._slots_disponiveis(), self._ctx_mariana_lopes(),
        )
        assert "reconferir" not in texto.lower()

    def test_saida_menciona_karla_delalibera(self):
        from voice_agent.oferta_deterministica import montar_texto_2_slots

        texto = montar_texto_2_slots(
            self._slots_disponiveis(), self._ctx_mariana_lopes(),
        )
        assert "Dra. Karla Delalíbera" in texto

    def test_saida_menciona_aguas_claras(self):
        from voice_agent.oferta_deterministica import montar_texto_2_slots

        texto = montar_texto_2_slots(
            self._slots_disponiveis(), self._ctx_mariana_lopes(),
        )
        assert "Águas Claras" in texto

    def test_dia_semana_11_08_2026_correto(self):
        """11/08/2026 é TERÇA-feira. Blinda contra bug C-35 na
        renderização (Claude inventar dia da semana)."""
        from voice_agent.oferta_deterministica import montar_texto_2_slots

        texto = montar_texto_2_slots(
            self._slots_disponiveis(), self._ctx_mariana_lopes(),
        )
        assert "Terça-feira" in texto

    def test_convenio_afego_mencionado_no_texto(self):
        """Bug C-43: paciente é Afego. Texto canônico deve mencionar."""
        from voice_agent.oferta_deterministica import montar_texto_2_slots

        texto = montar_texto_2_slots(
            self._slots_disponiveis(), self._ctx_mariana_lopes(),
        )
        assert "Afego" in texto


class TestGateDeveOfertarComEtapaCampanhaAgosto:
    """Confirma que a lógica `deve_ofertar_agora` funciona pro ctx
    Mariana Lopes (todos os campos preenchidos)."""

    def test_gate_true_para_mariana_lopes(self):
        from voice_agent.oferta_deterministica import deve_ofertar_agora

        ctx = {
            "fsm": {"estado": "AGENDA"},
            "ja_agendado": False,
            "known": {
                "nome_paciente": "Mariana Lopes Gomes",
                "data_nascimento": "2014-05-19",
                "convenio": "Afego",
                "medico": "Dra. Karla Delalibera",
                "unidade": "Águas Claras",
            },
        }
        assert deve_ofertar_agora(ctx) is True, (
            "Gate rejeitou ctx completo da Mariana Lopes — Bug C-43 "
            "vai reincidir porque bypass não vai ativar."
        )
