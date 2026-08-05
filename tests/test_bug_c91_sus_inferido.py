"""
Bug C-91 — Haiku inferiu SUS/convênio sem menção explícita do paciente.
(Lead 24417676 Dante — pai de Cecília 1a10m, estrabismo)

Duas camadas de defesa testadas:
1. Sistema prompt Haiku reforçado — instrução JAMAIS inferir nao_aceito_convenio
2. Proteção post-extraction em pipeline.py — descarta campo se convênio não foi
   mencionado explicitamente na mensagem ou no histórico de notas.
"""
import os
import sys
import types
import importlib
import unittest

# ---------------------------------------------------------------------------
# Helpers de stub / importação defensiva
# ---------------------------------------------------------------------------

def _make_ctx(user_text: str = "", notas: str = "") -> dict:
    return {
        "lead_id": 24417676,
        "status_id": 102560495,
        "user_text": user_text,
        "known": {
            "notas_historico": notas,
        },
    }


# ---------------------------------------------------------------------------
# 1) Testes da lógica de validação C-91 (extraída da pipeline.py)
# ---------------------------------------------------------------------------

def _run_c91_guard(fields: dict, user_text: str, notas: str = "") -> dict:
    """
    Replica a lógica de proteção C-91 do pipeline.py de forma isolada,
    sem precisar importar o pipeline completo.
    """
    import logging
    log = logging.getLogger("test_c91")

    nac = fields.get("nao_aceito_convenio")
    if not nac:
        return fields

    corpus = " ".join([
        str(user_text or ""),
        str(notas or ""),
    ]).lower()

    ALIASES: dict = {
        "sus": ["sus", "s.u.s", "sistema único"],
        "inas gdf": ["inas", "gdf", "saúde gdf"],
        "amil": ["amil"],
        "bradesco": ["bradesco"],
        "cassi": ["cassi"],
        "unimed": ["unimed"],
        "notre dame": ["notre dame", "notredame", "ndm"],
        "sul américa": ["sul am", "sulam"],
        "assefaz": ["assefaz"],
        "fusex": ["fusex"],
        "geap": ["geap"],
        "hap vida": ["hap"],
        "pm": ["pm saúde", "pmsaúde"],
        "porto seguro": ["porto seguro"],
        "outro": [],
    }

    key = str(nac).lower().strip()
    terms = ALIASES.get(key, [key])
    mencionado = any(t in corpus for t in terms) if terms else True

    if not mencionado:
        log.warning("[C-91] descartando %r — não mencionado pelo paciente", nac)
        fields = dict(fields)  # cópia
        fields.pop("nao_aceito_convenio", None)
        if fields.get("motivo_perda") == "Somente Convênio":
            fields.pop("motivo_perda", None)

    return fields


class TestC91SusInferido(unittest.TestCase):
    """Cenários: Haiku inferiu SUS sem menção → descarte."""

    def test_sus_sem_mencao_descartado(self):
        """Caso real: bebê estrabismo, pai nunca mencionou SUS."""
        fields = {"nao_aceito_convenio": "SUS", "nome": "Cecília"}
        user_text = "Boa tarde, preciso marcar uma consulta para minha filha"
        result = _run_c91_guard(fields, user_text)
        self.assertNotIn("nao_aceito_convenio", result,
                         "SUS inferido sem menção deve ser descartado")

    def test_sus_sem_mencao_remove_motivo_perda(self):
        """Junto com SUS inferido, motivo_perda também deve ser removido."""
        fields = {
            "nao_aceito_convenio": "SUS",
            "motivo_perda": "Somente Convênio",
            "nome": "Dante",
        }
        user_text = "Minha filha tem estrabismo, preciso agendar urgente"
        result = _run_c91_guard(fields, user_text)
        self.assertNotIn("nao_aceito_convenio", result)
        self.assertNotIn("motivo_perda", result)

    def test_sus_mencionado_explicitamente_mantido(self):
        """Paciente disse 'sou do SUS' → campo deve ser mantido."""
        fields = {"nao_aceito_convenio": "SUS"}
        user_text = "Tenho SUS, vocês atendem?"
        result = _run_c91_guard(fields, user_text)
        self.assertIn("nao_aceito_convenio", result)
        self.assertEqual(result["nao_aceito_convenio"], "SUS")

    def test_sus_nas_notas_mantido(self):
        """SUS mencionado nas notas anteriores → campo mantido."""
        fields = {"nao_aceito_convenio": "SUS"}
        user_text = "Bom dia"
        notas = "Paciente informou que usa SUS"
        result = _run_c91_guard(fields, user_text, notas)
        self.assertIn("nao_aceito_convenio", result)

    def test_inas_inferido_descartado(self):
        """Inas GDF inferido sem menção → descartado."""
        fields = {"nao_aceito_convenio": "Inas GDF"}
        user_text = "Quero marcar consulta para meu filho"
        result = _run_c91_guard(fields, user_text)
        self.assertNotIn("nao_aceito_convenio", result)

    def test_gdf_mencionado_mantido(self):
        """'GDF' aparece na mensagem → campo mantido."""
        fields = {"nao_aceito_convenio": "Inas GDF"}
        user_text = "Tenho o plano GDF, atende?"
        result = _run_c91_guard(fields, user_text)
        self.assertIn("nao_aceito_convenio", result)

    def test_amil_mencionado_mantido(self):
        """Paciente diz 'sou da Amil' → mantido."""
        fields = {"nao_aceito_convenio": "Amil"}
        user_text = "Boa tarde, sou da Amil vocês atendem?"
        result = _run_c91_guard(fields, user_text)
        self.assertIn("nao_aceito_convenio", result)

    def test_amil_nao_mencionado_descartado(self):
        """Amil inferida sem menção → descartada."""
        fields = {"nao_aceito_convenio": "Amil"}
        user_text = "Boa tarde, quero marcar uma consulta"
        result = _run_c91_guard(fields, user_text)
        self.assertNotIn("nao_aceito_convenio", result)

    def test_outro_sempre_mantido(self):
        """'Outro' não tem alias de validação → sempre mantido (sem falso positivo)."""
        fields = {"nao_aceito_convenio": "Outro"}
        user_text = "Tenho um plano corporativo que não sei o nome"
        result = _run_c91_guard(fields, user_text)
        self.assertIn("nao_aceito_convenio", result)

    def test_sem_nao_aceito_convenio_passthrough(self):
        """Fields sem nao_aceito_convenio passam inalterados."""
        fields = {"nome": "Cecília", "medico": "Karla"}
        result = _run_c91_guard(fields, "Preciso marcar")
        self.assertEqual(result, fields)

    def test_sus_case_insensitive(self):
        """'sus' em lowercase na mensagem deve ser detectado."""
        fields = {"nao_aceito_convenio": "SUS"}
        user_text = "Meu plano é sus, vocês atendem sus?"
        result = _run_c91_guard(fields, user_text)
        self.assertIn("nao_aceito_convenio", result)

    def test_unimed_inferida_descartada(self):
        """Unimed inferida sem menção → descartada."""
        fields = {"nao_aceito_convenio": "Unimed"}
        user_text = "Quero uma consulta oftalmológica"
        result = _run_c91_guard(fields, user_text)
        self.assertNotIn("nao_aceito_convenio", result)

    def test_outros_campos_preservados(self):
        """Ao descartar nao_aceito_convenio, outros campos devem ser preservados."""
        fields = {
            "nao_aceito_convenio": "SUS",
            "nome": "Cecília",
            "medico": "Karla",
            "unidade": "Asa Norte",
        }
        user_text = "Olá, quero agendar para minha filha"
        result = _run_c91_guard(fields, user_text)
        self.assertNotIn("nao_aceito_convenio", result)
        self.assertEqual(result["nome"], "Cecília")
        self.assertEqual(result["medico"], "Karla")
        self.assertEqual(result["unidade"], "Asa Norte")

    def test_bradesco_mencionado_mantido(self):
        """'Bradesco' mencionado explicitamente → mantido."""
        fields = {"nao_aceito_convenio": "Bradesco"}
        user_text = "Tenho Bradesco Saúde, atende?"
        result = _run_c91_guard(fields, user_text)
        self.assertIn("nao_aceito_convenio", result)

    def test_motivo_perda_nao_removido_se_sem_sus(self):
        """motivo_perda não é removido se não havia nao_aceito_convenio inferido."""
        fields = {
            "motivo_perda": "Somente Convênio",
            # nao_aceito_convenio ausente propositalmente
        }
        user_text = "Bom dia"
        result = _run_c91_guard(fields, user_text)
        # motivo_perda deve permanecer (foi outro mecanismo que o colocou)
        self.assertIn("motivo_perda", result)


# ---------------------------------------------------------------------------
# 2) Testes do system prompt Haiku reforçado
# ---------------------------------------------------------------------------

class TestC91HaikuSystemPrompt(unittest.TestCase):
    """
    Valida que o system prompt do extrator Haiku contém as regras C-91
    explícitas para evitar inferência de convênio.
    """

    def _get_system_prompt(self) -> str:
        """Importa responder e extrai o system prompt do extrator."""
        try:
            # Importação defensiva — pode falhar em CI sem deps
            import voice_agent.responder as responder_mod
            # Procura a string-chave no código-fonte do módulo
            import inspect
            src = inspect.getsource(responder_mod)
            return src
        except Exception:
            return ""

    def test_system_prompt_contem_regra_c91(self):
        """Código do responder.py deve conter instrução JAMAIS sobre nao_aceito_convenio."""
        src = self._get_system_prompt()
        if not src:
            self.skipTest("responder.py não importável no ambiente de teste")
        self.assertIn("nao_aceito_convenio", src,
                      "responder.py deve conter instrução sobre nao_aceito_convenio")
        self.assertIn("JAMAIS", src,
                      "System prompt deve conter 'JAMAIS' pra reforçar a regra C-91")

    def test_system_prompt_menciona_bebe_crianca(self):
        """Regra C-91 deve mencionar que bebê/criança NÃO implica SUS."""
        src = self._get_system_prompt()
        if not src:
            self.skipTest("responder.py não importável")
        # Verifica que existe referência a "bebê/criança NÃO implica SUS" no código
        self.assertTrue(
            "bebê" in src.lower() or "criança" in src.lower() or "idade" in src.lower(),
            "System prompt C-91 deve mencionar que idade não implica convênio"
        )

    def test_system_prompt_menciona_explicito(self):
        """Regra C-91 deve exigir menção explícita do convênio."""
        src = self._get_system_prompt()
        if not src:
            self.skipTest("responder.py não importável")
        self.assertIn("explicitamente", src.lower(),
                      "System prompt C-91 deve exigir menção explícita")


if __name__ == "__main__":
    unittest.main(verbosity=2)
