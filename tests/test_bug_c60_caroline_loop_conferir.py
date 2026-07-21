"""Bug C-60 (21/07/2026) — Lia repetiu 4x a MESMA frase em 20 min
no lead 22949500 Caroline Varella Barca Amaral:

  'Deixa eu conferir os dias direito antes de gravar. A Dra. Karla Delalíbera
   atende **seg/qua/sex em Asa Norte** e **ter/qui em Águas Claras**.'

Causa raiz:
1. Filtro `_viola_oferta_agenda` exige palavra 'agenda/horário/disponibilidade'
   perto de 'conferir/reconferir'. Variação nova ('conferir os dias direito
   antes de gravar') escapou do regex.
2. Dedup outbound (Task C-62) estava no repo LOCAL mas nunca commited.

Fix (este arquivo blinda):
- Adicionar 3 padrões novos em `_FAKE_AGENDA_LOOKUP` que pegam a variação
- Blindar contra regressão futura.
"""

from __future__ import annotations

from voice_agent.responder import (
    _texto_contem_hesitacao_stall,
    _viola_oferta_agenda,
)


FRASE_CAROLINE_EXATA = (
    "Deixa eu conferir os dias direito antes de gravar. "
    "A Dra. Karla Delalíbera atende **seg/qua/sex em Asa Norte** "
    "e **ter/qui em Águas Claras**. Me diz de novo qual dia funciona "
    "melhor e eu já confirmo a unidade certa pra esse dia."
)


def test_frase_exata_caroline_detectada_como_stall():
    """Frase exata do bug C-60 tem que virar stall."""
    assert _texto_contem_hesitacao_stall(FRASE_CAROLINE_EXATA), (
        "Frase Caroline não foi detectada — regex escapou de novo"
    )


def test_com_agenda_frase_caroline_bloqueada():
    """Se ctx tem agenda + Lia diz frase Caroline → bloqueia."""
    assert _viola_oferta_agenda(FRASE_CAROLINE_EXATA, has_agenda=True)


def test_variantes_conferir_dias():
    """Variações de 'conferir os dias' — todas viram stall."""
    for frase in (
        "Deixa eu conferir os dias antes de gravar",
        "Vou conferir os dias da semana rápido",
        "Deixa eu reconferir o dia certo",
        "Vou verificar os dias e volto",
        "Deixa eu checar os dias antes de agendar",
    ):
        assert _texto_contem_hesitacao_stall(frase), f"não pegou: {frase[:40]}"


def test_variante_conferir_antes_de_gravar():
    """Padrão 'conferir/reconferir ... antes de gravar/marcar/agendar'."""
    for frase in (
        "Deixa eu conferir antes de gravar",
        "Vou reconferir antes de marcar",
        "Preciso verificar antes de agendar",
        "Deixa eu checar antes de confirmar",
    ):
        assert _texto_contem_hesitacao_stall(frase), f"não pegou: {frase[:40]}"


def test_tabela_seg_qua_sex_ter_qui():
    """Padrão 'seg/qua/sex ... ter/qui' — Lia listando dias como stall."""
    for frase in (
        "Atende seg/qua/sex em Asa Norte e ter/qui em Águas Claras",
        "**seg/qua/sex** em Asa Norte e **ter/qui** em Águas Claras",
        "Karla atende seg/qua/sex Asa Norte, ter/qui Águas Claras",
    ):
        assert _texto_contem_hesitacao_stall(frase), f"não pegou: {frase[:60]}"


def test_frases_legitimas_nao_disparam_falso_positivo():
    """Confirmação real ou saudação NÃO pode virar stall."""
    for frase in (
        "Perfeito! Tenho 2 horários abertos: quinta 10:30 ou 17:00.",
        "Sua consulta está confirmada quarta-feira às 09:00 na Asa Norte.",
        "Olá! Aqui é a Lia da Blink. Como posso ajudar?",
        "Vou verificar seu convênio no sistema.",  # sem 'dias'
    ):
        assert not _texto_contem_hesitacao_stall(frase), (
            f"falso positivo: {frase[:60]}"
        )
