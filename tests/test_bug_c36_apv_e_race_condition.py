"""Pytest blindando Bug C-36 — APV só com sintomas + race condition gravação notas.

Origem: lead 24168922 Manuela (17/06/2026 23:30 BRT).
Fábio percebeu 3 bugs simultâneos:
  #1 — pipeline._sync_kommo_safely descarta nota se find_lead_id_by_phone
       retorna vazio (race condition de indexação Kommo)
  #2 — Lia chuta "especialista Avaliação do Processamento Visual" pra TODO
       paciente Karla, sem evidência clínica (deveria exigir sintomas)
  #36c — janela agenda Medware muito ampla (já corrigido pra 10d)
"""
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
MASTER_INSTRUCTION = (
    ROOT / "voice_agent" / "knowledge_base" / "_MASTER_INSTRUCTION.md"
)


class TestAPVSoComSintomas:
    """Bug C-36 #2: apresentação Karla deve ser branching por motivo/sintoma."""

    @pytest.fixture(scope="class")
    def prompt(self) -> str:
        return MASTER_INSTRUCTION.read_text(encoding="utf-8")

    def test_versao_prompt_bumpada_c36(self, prompt: str):
        """Cache Anthropic precisa re-carregar — VERSAO_PROMPT bumped."""
        assert "2026-06-17-c36-apv-so-com-sintomas" in prompt

    def test_sintomas_apv_listados_explicitamente(self, prompt: str):
        """Sintomas característicos APV/SDP devem estar listados no prompt."""
        sintomas = [
            "cefaleia",
            "cansaço visual",
            "tontura",
            "postura",
            "concentração escolar",
            "sensibilidade à luz",
        ]
        for sintoma in sintomas:
            assert sintoma.lower() in prompt.lower(), (
                f"Sintoma APV '{sintoma}' deveria estar listado no prompt"
            )

    def test_apresentacao_oftalmopediatria_permitida(self, prompt: str):
        """Bebê/criança rotina → 'especialista em oftalmopediatria' (não APV)."""
        assert "especialista em oftalmopediatria" in prompt

    def test_apresentacao_estrabismo_permitida(self, prompt: str):
        """Estrabismo declarado → 'especialista em estrabismo' (não APV)."""
        assert "especialista em estrabismo" in prompt

    def test_chute_clinico_proibido(self, prompt: str):
        """O prompt deve mencionar 'chute clínico' como PROIBIDO."""
        assert "chute" in prompt.lower()

    def test_regra_antiga_nao_existe_mais(self, prompt: str):
        """Regra antiga 'PROIBIDO especialista em oftalmopediatria' deve
        ter sido REMOVIDA (era a causa raiz do bug)."""
        # A regra antiga proibia o termo "especialista em oftalmopediatria"
        # como apresentação. Verificar que NÃO há mais essa proibição.
        # Se existe a linha "PROIBIDO escrever ... 'especialista em oftalmopediatria'"
        # com texto que sugira proibição genérica, falha.
        linhas_proibido = [
            l for l in prompt.split("\n")
            if "PROIBIDO" in l and "oftalmopediatria" in l.lower()
        ]
        # Aceita linhas técnicas, mas não a antiga regra genérica
        for linha in linhas_proibido:
            assert "como apresentação principal" not in linha, (
                "Regra antiga 'PROIBIDO especialista em oftalmopediatria' "
                "ainda está no prompt — fix C-36 #2 não foi aplicado."
            )


class TestRaceConditionFix:
    """Bug C-36 #1: pipeline._sync_kommo_safely tem 3 camadas de defesa."""

    @pytest.fixture(scope="class")
    def pipeline_src(self) -> str:
        return (ROOT / "voice_agent" / "pipeline.py").read_text(encoding="utf-8")

    def test_aceita_lead_id_hint(self, pipeline_src: str):
        """Caller (webhook) pode passar lead_id direto."""
        assert "lead_id_hint" in pipeline_src

    def test_cache_redis_chat_to_lead(self, pipeline_src: str):
        """Cache Redis blink:chat_to_lead:{convo} pra evitar busca repetida."""
        assert "blink:chat_to_lead:" in pipeline_src

    def test_retry_com_backoff(self, pipeline_src: str):
        """3 tentativas com backoff 1s/2s/4s pra race condition Kommo."""
        # Confirma que tem loop com tentativas e sleep
        assert "for tentativa in" in pipeline_src
        assert "2 ** tentativa" in pipeline_src

    def test_warning_quando_falha_total(self, pipeline_src: str):
        """Log WARNING (não INFO) quando lead não encontrado após retries."""
        # Antes: log.info(...) — silencioso demais
        # Agora: log.warning(...) — visível em produção
        assert "log.warning" in pipeline_src
        assert "lead NÃO encontrado após 3 tentativas" in pipeline_src

    def test_persiste_lead_id_no_cache_apos_achar(self, pipeline_src: str):
        """Quando acha via busca, salva no cache (próximo turn é instantâneo)."""
        assert "setex(cache_key" in pipeline_src
        assert "86400" in pipeline_src  # TTL 24h


class TestJanelaAgenda10d:
    """Bug C-36c: janela Medware reduzida pra 10 dias (Fábio)."""

    @pytest.fixture(scope="class")
    def medware_src(self) -> str:
        return (ROOT / "voice_agent" / "medware.py").read_text(encoding="utf-8")

    def test_dias_default_10(self, medware_src: str):
        """dias=10 default em horarios_para_agente."""
        assert "dias: int = 10," in medware_src

    def test_historico_documentado_no_docstring(self, medware_src: str):
        """Docstring documenta 90d → 21d → 10d."""
        assert "C-36c" in medware_src
        assert "10d" in medware_src

    def test_env_override_continua_valido(self, medware_src: str):
        """MEDWARE_DIAS_DEFAULT continua funcionando."""
        assert "MEDWARE_DIAS_DEFAULT" in medware_src
