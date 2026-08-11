"""
Bug C-59 (20/07/2026) — Dedup de agendamentos por slot.

Descoberto via SQL Medware direto: 18 slots com >1 agendamento em 20/07:
  - Slot 20/07 11:30 → 56 agendamentos duplicados
  - Slot 20/07 10:40 → 28
  - Slot 20/07 17:00 → 28
  - Slot 20/07 09:00 → 18
  - Slot 20/07 08:30 → 11 (Eloah Bender)

Causa raiz: `criar_agendamento` do medware.py NÃO checa se slot já foi
gravado antes de POST. Cada retry do agente OU race condition duplica.

Fix (medware.py::criar_agendamento):
1. ANTES do POST /Medware/Agendamento/Salvar, chama
   `medware_sql.existe_agendamento(cod_medico, cod_unidade, data_hora, cod_paciente)`
2. Se retorna CODAGENDAMENTO existente, devolve o mesmo cod sem duplicar
3. Log estruturado `[MEDWARE DEDUP C-59]` pra observabilidade
4. Fail-open: se SQL Medware está fora, deixa gravar (evita bloquear tudo)

Toggle env: `MEDWARE_DEDUP_SLOT=0` desativa (rollback emergência).
Default: ON.
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch


def test_medware_dedup_slot_ligado_por_default():
    """Env vazia = dedup ligado. Só desliga com valor explícito 0/false/no."""
    import importlib
    import voice_agent.medware as mw
    importlib.reload(mw)  # garante estado limpo

    # Sem env definida
    if "MEDWARE_DEDUP_SLOT" in os.environ:
        del os.environ["MEDWARE_DEDUP_SLOT"]
    valor = os.environ.get("MEDWARE_DEDUP_SLOT", "1")
    assert valor not in ("0", "false", "no")


def test_medware_dedup_slot_desligado_por_env():
    os.environ["MEDWARE_DEDUP_SLOT"] = "0"
    valor = os.environ.get("MEDWARE_DEDUP_SLOT", "1")
    assert valor in ("0", "false", "no")
    del os.environ["MEDWARE_DEDUP_SLOT"]


def test_medware_sql_existe_agendamento_query_format():
    """A query gerada por existe_agendamento deve usar CAST + EXTRACT
    em vez de comparar DATETIME como string (Firebird rejeita HTTP 400)."""
    from voice_agent import medware_sql

    # Mock executar pra capturar a query enviada
    query_captured = []

    def fake_executar(q):
        query_captured.append(q)
        return {"colunas": [], "dados": []}

    with patch.object(medware_sql, "executar", side_effect=fake_executar):
        medware_sql.existe_agendamento(12080, 5, "2026-07-20T08:30:00", 4982)

    assert len(query_captured) == 1
    q = query_captured[0]
    assert "CAST(DATAHORAAGENDADA AS DATE)='2026-07-20'" in q
    assert "EXTRACT(HOUR FROM DATAHORAAGENDADA)=8" in q
    assert "EXTRACT(MINUTE FROM DATAHORAAGENDADA)=30" in q
    assert "CODMEDICO=12080" in q
    assert "CODUNIDADE=5" in q
    assert "CODPACIENTE=4982" in q


def test_medware_sql_existe_agendamento_sem_paciente():
    """cod_paciente=0 → NÃO filtra por paciente (checa slot compartilhado)."""
    from voice_agent import medware_sql

    query_captured = []
    with patch.object(
        medware_sql, "executar",
        side_effect=lambda q: (query_captured.append(q), {"colunas": [], "dados": []})[1],
    ):
        medware_sql.existe_agendamento(12080, 5, "2026-07-20T08:30:00", 0)

    assert "CODPACIENTE" not in query_captured[0]


def test_medware_sql_contar_duplicatas_slot_query():
    from voice_agent import medware_sql

    query_captured = []
    with patch.object(
        medware_sql, "executar",
        side_effect=lambda q: (
            query_captured.append(q),
            {"colunas": [], "dados": [{"QTD": 56}]},
        )[1],
    ):
        n = medware_sql.contar_duplicatas_slot(12080, 5, "2026-07-20T11:30:00")

    assert n == 56
    q = query_captured[0]
    # Fix 20/07/2026: usar COUNT(DISTINCT CODPACIENTE) em vez de COUNT(*).
    # 1 consulta Medware = N registros (um por procedimento/exame). COUNT(*)
    # conta exames; COUNT DISTINCT paciente conta consultas reais.
    assert "COUNT(DISTINCT CODPACIENTE)" in q
    assert "EXTRACT(HOUR FROM DATAHORAAGENDADA)=11" in q
    assert "EXTRACT(MINUTE FROM DATAHORAAGENDADA)=30" in q


def test_medware_sql_apenas_select_permitido():
    """Segurança: bloqueia qualquer coisa que não seja SELECT/WITH."""
    from voice_agent import medware_sql

    for q in (
        "DELETE FROM AGENDAMENTO WHERE 1=1",
        "UPDATE PACIENTE SET NOME='X'",
        "INSERT INTO AGENDAMENTO VALUES (1,2,3)",
        "DROP TABLE AGENDAMENTO",
        "",
        "   ",
    ):
        try:
            medware_sql.executar(q)
            raise AssertionError(f"query permitida indevidamente: {q!r}")
        except medware_sql.MedwareSQLError as e:
            assert "SELECT/WITH" in str(e) or "vazia" in str(e)


def test_medware_sql_with_permitido():
    """WITH (CTE) também é read-only, deve passar a validação."""
    from voice_agent import medware_sql

    query_captured = []
    with patch.object(
        medware_sql, "obter_token", return_value="fake_token",
    ), patch.object(
        medware_sql, "_http_post",
        side_effect=lambda url, h, b: (
            query_captured.append(b.get("query", "")),
            (200, {"colunas": [], "dados": []}),
        )[1],
    ):
        medware_sql.executar(
            "WITH X AS (SELECT 1 FROM PACIENTE) SELECT * FROM X"
        )

    assert len(query_captured) == 1
    assert "WITH" in query_captured[0]


def test_medware_criar_agendamento_dedup_reintroduz_import():
    """Regressão: medware.py deve ter `import os` no topo (fix C-59)."""
    from pathlib import Path
    src = (
        Path(__file__).resolve().parent.parent
        / "voice_agent" / "medware.py"
    ).read_text(encoding="utf-8")
    # Import os na área dos imports (não em função)
    top = src.split("def ", 1)[0]
    assert "\nimport os\n" in top, (
        "medware.py precisa `import os` no topo pra ler MEDWARE_DEDUP_SLOT"
    )


def test_medware_criar_agendamento_chama_existe_agendamento():
    """medware.py deve importar existe_agendamento de medware_sql."""
    from pathlib import Path
    src = (
        Path(__file__).resolve().parent.parent
        / "voice_agent" / "medware.py"
    ).read_text(encoding="utf-8")
    assert "existe_agendamento" in src, (
        "medware.py deve usar existe_agendamento pra dedup"
    )
    assert "MEDWARE_DEDUP_SLOT" in src, (
        "medware.py deve ler env MEDWARE_DEDUP_SLOT"
    )
    assert "dedup_slot_existente" in src, (
        "medware.py deve retornar motivo='dedup_slot_existente' quando pega dup"
    )
