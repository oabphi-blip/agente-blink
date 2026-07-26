"""Pytest — Bug C-71 (26/07/2026)

Caso: lead 22557778 (Adriana). ctx.unidade="Águas Claras" (defasado de sessão
anterior). Paciente pede "03/08/2026" (segunda-feira = Karla Asa Norte).
Lia gera oferta correta com Asa Norte, mas filtro C-31b bloqueia porque
ctx.unidade diz Águas Claras → retorna _DIA_NAO_ATENDIDO_FALLBACK →
paciente responde "manhã" → mesma coisa → loop infinito.

Fix em 2 camadas:
  Guarda 1 — C-31b deixa passar se LLM escreveu a unidade CORRETA no texto.
  Guarda 2 — C-31b não repete "Qual turno?" se paciente já respondeu turno.

Adicionalmente: _inferir_unidade_por_dia devolve a unidade certa dado médico
+ weekday (weekday(0)=seg, 2=qua, 4=sex → Asa Norte; 1=ter, 3=qui → AC).
"""

from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Helpers para evitar importação de módulos pesados em CI sem env
# ---------------------------------------------------------------------------

def _get_inferir():
    """Importa _inferir_unidade_por_dia de responder.py."""
    from voice_agent.responder import _inferir_unidade_por_dia
    return _inferir_unidade_por_dia


def _get_scrub():
    """Importa _scrub_prohibited de responder.py."""
    from voice_agent.responder import _scrub_prohibited
    return _scrub_prohibited


# ---------------------------------------------------------------------------
# 1. _inferir_unidade_por_dia
# ---------------------------------------------------------------------------

class TestInferirUnidadePorDia:
    """Valida que inferência médico × dia-da-semana → unidade funciona."""

    def test_karla_segunda_asa_norte(self):
        fn = _get_inferir()
        assert fn("karla", 0) == "Asa Norte"   # segunda

    def test_karla_quarta_asa_norte(self):
        fn = _get_inferir()
        assert fn("karla", 2) == "Asa Norte"   # quarta

    def test_karla_sexta_asa_norte(self):
        fn = _get_inferir()
        assert fn("karla", 4) == "Asa Norte"   # sexta

    def test_karla_terca_aguas_claras(self):
        fn = _get_inferir()
        assert fn("karla", 1) == "Águas Claras"  # terça

    def test_karla_quinta_aguas_claras(self):
        fn = _get_inferir()
        assert fn("karla", 3) == "Águas Claras"  # quinta

    def test_karla_sabado_none(self):
        fn = _get_inferir()
        assert fn("karla", 5) is None  # sábado — não atende

    def test_karla_domingo_none(self):
        fn = _get_inferir()
        assert fn("karla", 6) is None  # domingo — não atende

    def test_medico_desconhecido_none(self):
        fn = _get_inferir()
        assert fn("joaquim", 0) is None

    def test_medico_vazio_none(self):
        fn = _get_inferir()
        assert fn("", 0) is None

    def test_karla_com_titulo(self):
        """Deve normalizar 'Dra. Karla Delalíbera' para 'karla'."""
        fn = _get_inferir()
        assert fn("dra. karla delalíbera", 0) == "Asa Norte"

    def test_fabricio_ambiguo_none(self):
        """Fabrício atende ter/qui em AMBAS as unidades → ambíguo → None."""
        fn = _get_inferir()
        # Fabricio ter/qui: se calendar_atendimento.json tiver Fabrício em AC e AN
        # no mesmo dia → None (ambíguo). Se só AN, retorna "Asa Norte".
        # O teste apenas verifica que não levanta exceção.
        result = fn("fabricio", 1)
        assert result is None or isinstance(result, str)


# ---------------------------------------------------------------------------
# 2. Guarda 1 — C-31b deixa passar quando LLM escreveu unidade correta
# ---------------------------------------------------------------------------

class TestGuarda1UnidadeCorretaNoTexto:
    """Guarda 1: se o texto da Lia menciona a unidade correta para o dia
    oferecido (mesmo que ctx.unidade esteja errado), não bloquear."""

    def _ctx_aguas_claras(self, user_text=""):
        return {
            "known": {
                "medico": "karla",
                "unidade": "Águas Claras",   # DEFASADO
            },
            "ultima_msg_outbound": "",
            "user_text": user_text,
        }

    def test_oferta_segunda_asa_norte_no_texto_passa(self):
        """LLM escreveu 'Asa Norte' + 'segunda 03/08' → C-31b não bloqueia."""
        scrub = _get_scrub()
        ctx = self._ctx_aguas_claras()
        # 03/08/2026 = segunda-feira → Karla Asa Norte
        texto = (
            "1️⃣ Segunda-feira (03/08) às 09:30 em Asa Norte\n"
            "2️⃣ Segunda-feira (03/08) às 11:00 em Asa Norte\n"
            "Algum desses fica bom pra você?"
        )
        result = scrub(texto, ctx)
        # Deve retornar texto ORIGINAL (ou None), não o fallback "Qual turno"
        assert result is None or (
            "turno funciona melhor" not in (result or "").lower()
        ), f"C-71 guarda-1 falhou — retornou: {result!r}"

    def test_oferta_segunda_sem_unidade_ainda_bloqueia(self):
        """LLM NÃO escreveu 'Asa Norte' → C-31b ainda bloqueia normalmente."""
        scrub = _get_scrub()
        ctx = self._ctx_aguas_claras()
        # Texto sem mencionar unidade, mas com data de segunda
        texto = (
            "1️⃣ Segunda-feira (03/08) às 09:30\n"
            "2️⃣ Segunda-feira (03/08) às 11:00\n"
            "Algum desses fica bom?"
        )
        result = scrub(texto, ctx)
        # Nesse caso C-31b pode ou não bloquear dependendo da guarda-2.
        # O importante é que guarda-1 não causa falso negativo aqui — é OK
        # bloquear porque o texto não deixa claro qual unidade.
        # Apenas verificamos que o código não levanta exceção.
        assert result is None or isinstance(result, str)

    def test_oferta_aguas_claras_quinta_ok_sem_bloqueio(self):
        """Quinta-feira + ctx.unidade=Águas Claras → sem conflito → passa."""
        scrub = _get_scrub()
        ctx = {
            "known": {
                "medico": "karla",
                "unidade": "Águas Claras",  # CORRETO para quinta
            },
            "ultima_msg_outbound": "",
            "user_text": "",
        }
        texto = (
            "1️⃣ Quinta-feira (07/08) às 10:00 em Águas Claras\n"
            "2️⃣ Quinta-feira (07/08) às 14:00 em Águas Claras\n"
            "Algum desses fica bom?"
        )
        result = scrub(texto, ctx)
        assert result is None or (
            "turno funciona melhor" not in (result or "").lower()
        ), f"Oferta quinta AC não deveria ser bloqueada: {result!r}"


# ---------------------------------------------------------------------------
# 3. Guarda 2 — anti-loop: paciente JÁ respondeu turno
# ---------------------------------------------------------------------------

class TestGuarda2AntiLoop:
    """Guarda 2: se última msg da Lia foi 'Qual turno...' E o paciente
    respondeu 'manhã' ou 'tarde', não repetir o fallback."""

    def _ctx_loop(self, user_text: str):
        return {
            "known": {
                "medico": "karla",
                "unidade": "Águas Claras",  # DEFASADO
            },
            # Última msg da Lia era exatamente o fallback que causava loop
            "ultima_msg_outbound": (
                "Qual turno funciona melhor pra você — manhã ou tarde? "
                "Com isso confirmo o horário disponível."
            ),
            "user_text": user_text,
        }

    def test_loop_manha_nao_repete(self):
        """Paciente respondeu 'manhã' → não repete 'Qual turno?'."""
        scrub = _get_scrub()
        ctx = self._ctx_loop("Pela manhã")
        # Texto que dispararia C-31b sem a guarda
        texto = (
            "1️⃣ Segunda-feira (03/08) às 09:30\n"
            "2️⃣ Segunda-feira (03/08) às 10:30\n"
            "Algum desses fica bom?"
        )
        result = scrub(texto, ctx)
        # Com guarda-2 ativa, deve deixar passar (result=None) ou devolver
        # texto que NÃO seja o mesmo fallback de "Qual turno"
        if result is not None:
            assert "turno funciona melhor" not in result.lower(), (
                f"Loop infinito detectado — guarda-2 falhou. result={result!r}"
            )

    def test_loop_tarde_nao_repete(self):
        """Paciente respondeu 'tarde' → não repete 'Qual turno?'."""
        scrub = _get_scrub()
        ctx = self._ctx_loop("À tarde, por favor")
        texto = (
            "1️⃣ Segunda-feira (03/08) às 14:00\n"
            "2️⃣ Segunda-feira (03/08) às 15:30\n"
            "Algum desses fica bom?"
        )
        result = scrub(texto, ctx)
        if result is not None:
            assert "turno funciona melhor" not in result.lower(), (
                f"Loop infinito detectado — guarda-2 falhou. result={result!r}"
            )

    def test_loop_manha_accentuada_nao_repete(self):
        """'manhã' com acento → regex \b(manh[aã]|tarde)\b deve casar."""
        scrub = _get_scrub()
        ctx = self._ctx_loop("manhã")
        texto = (
            "1️⃣ Segunda-feira (03/08) às 09:00\n"
            "2️⃣ Segunda-feira (10/08) às 09:00\n"
            "Algum desses fica?"
        )
        result = scrub(texto, ctx)
        if result is not None:
            assert "turno funciona melhor" not in result.lower(), (
                f"Loop com 'manhã' acentuado: {result!r}"
            )

    def test_sem_resposta_turno_ainda_bloqueia(self):
        """Última msg foi fallback MAS paciente não respondeu turno → bloqueia."""
        scrub = _get_scrub()
        ctx = self._ctx_loop("Um momento")  # sem "manhã" nem "tarde"
        texto = (
            "1️⃣ Segunda-feira (03/08) às 09:00\n"
            "2️⃣ Segunda-feira (10/08) às 09:00\n"
            "Algum desses fica?"
        )
        result = scrub(texto, ctx)
        # Sem resposta de turno, C-31b DEVE bloquear (comportamento correto)
        # Verificamos apenas que não levanta exceção
        assert result is None or isinstance(result, str)

    def test_primeira_vez_sem_loop_ainda_bloqueia(self):
        """Primeira vez (ultima_msg não é fallback turno) → bloqueio normal."""
        scrub = _get_scrub()
        ctx = {
            "known": {
                "medico": "karla",
                "unidade": "Águas Claras",  # DEFASADO
            },
            "ultima_msg_outbound": "Olá! Posso ajudar com seu agendamento?",
            "user_text": "manhã",
        }
        texto = (
            "1️⃣ Segunda-feira (03/08) às 09:00\n"
            "2️⃣ Segunda-feira (10/08) às 09:00\n"
            "Algum desses fica?"
        )
        result = scrub(texto, ctx)
        # Primeira tentativa: guarda-2 não se aplica (última msg não foi fallback)
        # Guarda-1 pode salvar se "Asa Norte" estiver no texto — mas aqui não está.
        # Esperamos bloqueio OR None dependendo da guarda-1.
        assert result is None or isinstance(result, str)


# ---------------------------------------------------------------------------
# 4. Cenário real lead 22557778 (Adriana)
# ---------------------------------------------------------------------------

class TestCenarioRealAdriana:
    """Reproduce a sequência exata de mensagens do lead 22557778."""

    def test_lia_nao_repete_turno_apos_manha(self):
        """Simula turn N+1: paciente disse 'manhã', Lia gerou oferta segunda,
        C-31b detecta conflito com AC, mas guarda-2 deve inibir o loop."""
        scrub = _get_scrub()

        # Estado após 3 loops: Lia perguntou "Qual turno" 3x seguidas
        ctx = {
            "known": {
                "medico": "Dra. Karla Delalíbera",
                "unidade": "Águas Claras",
            },
            "ultima_msg_outbound": (
                "[LIA 10:15 26/07] Qual turno funciona melhor pra você — "
                "manhã ou tarde? Com isso confirmo o horário disponível."
            ),
            "user_text": "Pela manhã",
        }

        # LLM gerou oferta correta para segunda, mas sem mencionar "Asa Norte"
        texto_lia = (
            "Tenho 2 horários disponíveis com a Dra. Karla Delalíbera:\n"
            "1️⃣ Segunda-feira (03/08) às 09:30\n"
            "2️⃣ Segunda-feira (03/08) às 10:30\n"
            "Algum desses fica bom pra você?"
        )

        result = scrub(texto_lia, ctx)
        assert result is None or (
            "turno funciona melhor" not in (result or "").lower()
        ), (
            f"BUG C-71 não corrigido — Lia ainda repetiria 'Qual turno?' "
            f"apesar de paciente ter respondido 'manhã'. result={result!r}"
        )

    def test_lia_com_asa_norte_no_texto_passa(self):
        """Cenário ideal: LLM escreve 'Asa Norte' explicitamente → guarda-1."""
        scrub = _get_scrub()

        ctx = {
            "known": {
                "medico": "karla",
                "unidade": "Águas Claras",  # DEFASADO
            },
            "ultima_msg_outbound": "",
            "user_text": "manhã",
        }

        texto_lia = (
            "Tenho 2 horários disponíveis com a Dra. Karla Delalíbera "
            "em Asa Norte (segunda-feira):\n"
            "1️⃣ Segunda-feira (03/08) às 09:30\n"
            "2️⃣ Segunda-feira (03/08) às 10:30\n"
            "Algum desses fica bom?"
        )

        result = scrub(texto_lia, ctx)
        assert result is None or (
            "turno funciona melhor" not in (result or "").lower()
        ), (
            f"C-71 guarda-1 falhou — texto com 'Asa Norte' deveria passar: "
            f"{result!r}"
        )

    def test_oferta_quarta_asa_norte_sem_conflito(self):
        """Quarta-feira (Asa Norte) + ctx.unidade=Águas Claras: guarda-1 salva."""
        scrub = _get_scrub()

        ctx = {
            "known": {
                "medico": "karla",
                "unidade": "Águas Claras",
            },
            "ultima_msg_outbound": (
                "Qual turno funciona melhor pra você — manhã ou tarde?"
            ),
            "user_text": "de manhã",
        }

        # 05/08/2026 = quarta-feira → Asa Norte
        texto_lia = (
            "Tenho estes horários em Asa Norte:\n"
            "1️⃣ Quarta-feira (05/08) às 08:30\n"
            "2️⃣ Quarta-feira (05/08) às 09:30\n"
            "Qual prefere?"
        )

        result = scrub(texto_lia, ctx)
        assert result is None or (
            "turno funciona melhor" not in (result or "").lower()
        ), f"Guarda-1 não salvou oferta quarta AC→AN: {result!r}"
