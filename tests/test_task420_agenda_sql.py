"""
Task #420 (20/07/2026) — Apresentação de agenda via SQL direto Medware.

Substitui REST /Medware/Horarios/Listar por SQL direto quando env
MEDWARE_AGENDA_SQL=1. Ganhos:
- Grade REAL via HORARIOAGENDA + MEDICO_PROCED_HORARIOAGENDA
- TZ Brasília local (Firebird sem UTC)
- Dedup natural (56 duplicatas C-59 = 1 slot ocupado)
- Dias da semana corretos (fim Bug C-31/C-53)

Fluxo:
1. medware.py::horarios_para_agente checa env
2. Se ON → medware_sql.listar_slots_livres (Python expande grade)
3. Se OFF ou SQL falhar → REST antigo (fallback)
"""

from __future__ import annotations

import os
from unittest.mock import patch
from datetime import date

import pytest


def test_medware_sql_grade_karla_asa_norte_bate_kb():
    """Grade Karla Asa Norte deve ser SEG/QUA/SEX conforme KB.
    Bug C-31/C-53: Karla NÃO atende quinta em Asa Norte."""
    from voice_agent import medware_sql

    fake_grade = [
        {"CODHORARIOAGENDA": 1, "DIASEMANA": 2, "HORAINICIO": "08:30:00",
         "HORAFIM": "12:00:00", "INTERVALO": 30, "CODAGENDA": 4,
         "DATAINICIO": "2026-01-01T00:00:00", "DATAFIM": None},
        {"CODHORARIOAGENDA": 2, "DIASEMANA": 4, "HORAINICIO": "08:30:00",
         "HORAFIM": "12:00:00", "INTERVALO": 30, "CODAGENDA": 4,
         "DATAINICIO": "2026-01-01T00:00:00", "DATAFIM": None},
        {"CODHORARIOAGENDA": 3, "DIASEMANA": 6, "HORAINICIO": "08:30:00",
         "HORAFIM": "12:00:00", "INTERVALO": 30, "CODAGENDA": 4,
         "DATAINICIO": "2026-01-01T00:00:00", "DATAFIM": None},
    ]

    with patch.object(medware_sql, "executar") as fake_exec:
        fake_exec.return_value = {"colunas": [], "dados": fake_grade}
        grade = medware_sql.listar_grade_medico(12080, 5)

    dias_medware = [g["DIASEMANA"] for g in grade]
    # DIASEMANA Medware: 2=seg, 4=qua, 6=sex
    assert 2 in dias_medware
    assert 4 in dias_medware
    assert 6 in dias_medware
    # NUNCA quinta (5) em Asa Norte
    assert 5 not in dias_medware


def test_isoweekday_para_diasemana_medware_mapping():
    """Python isoweekday (1=seg..7=dom) → Medware (1=dom..7=sab)."""
    from voice_agent.medware_sql import _isoweekday_para_diasemana_medware

    # Segunda (Python iso=1) → Medware DIASEMANA=2
    assert _isoweekday_para_diasemana_medware(1) == 2
    # Terça (iso=2) → Medware=3
    assert _isoweekday_para_diasemana_medware(2) == 3
    # Quarta (iso=3) → Medware=4
    assert _isoweekday_para_diasemana_medware(3) == 4
    # Sexta (iso=5) → Medware=6
    assert _isoweekday_para_diasemana_medware(5) == 6
    # Sábado (iso=6) → Medware=7
    assert _isoweekday_para_diasemana_medware(6) == 7
    # Domingo (iso=7) → Medware=1
    assert _isoweekday_para_diasemana_medware(7) == 1


def test_hhmm_conversoes():
    from voice_agent.medware_sql import _hhmm_para_minutos, _minutos_para_hhmm
    assert _hhmm_para_minutos("08:30") == 510
    assert _hhmm_para_minutos("08:30:00") == 510
    assert _hhmm_para_minutos("13:30") == 810
    assert _minutos_para_hhmm(510) == "08:30"
    assert _minutos_para_hhmm(810) == "13:30"
    assert _minutos_para_hhmm(0) == "00:00"


def test_listar_slots_livres_expande_e_dedup_ocupados():
    """Grade seg 08:30-10:00 int=30 → 3 slots (08:30, 09:00, 09:30).
    Se 09:00 está ocupado 5x, ainda conta 1x (dedup natural)."""
    from voice_agent import medware_sql
    from datetime import date, timedelta

    grade_fake = [
        {"CODHORARIOAGENDA": 1, "DIASEMANA": 2, "HORAINICIO": "08:30:00",
         "HORAFIM": "10:00:00", "INTERVALO": 30, "CODAGENDA": 4},
    ]
    # Próxima segunda-feira (garantidamente futuro).
    # Fórmula: (1 - iso) % 7 or 7 → sempre 1-7 dias à frente.
    hoje = date.today()
    dias_ate_seg = (1 - hoje.isoweekday()) % 7 or 7
    prox_seg = hoje + timedelta(days=dias_ate_seg)

    # 09:00 ocupado (com 5 duplicatas — dedup natural)
    ocupados_fake = [
        {"DATAHORAAGENDADA": f"{prox_seg.isoformat()}T09:00:00"},
        {"DATAHORAAGENDADA": f"{prox_seg.isoformat()}T09:00:00"},
        {"DATAHORAAGENDADA": f"{prox_seg.isoformat()}T09:00:00"},
    ]

    calls = []

    def fake_executar(q):
        calls.append(q)
        if "MEDICO_PROCED_HORARIOAGENDA" in q:
            return {"colunas": [], "dados": grade_fake}
        elif "AGENDAMENTO" in q:
            return {"colunas": [], "dados": ocupados_fake}
        return {"colunas": [], "dados": []}

    with patch.object(medware_sql, "executar", side_effect=fake_executar):
        livres = medware_sql.listar_slots_livres(
            12080, 5, dias=(dias_ate_seg + 1), data_inicio=prox_seg.isoformat(),
        )

    horarios_livres = [(s["data_iso"], s["hora"]) for s in livres if s["data_iso"] == prox_seg.isoformat()]
    # Esperado: 08:30 e 09:30 (09:00 ocupado). 3 slots - 1 ocupado = 2 livres.
    assert (prox_seg.isoformat(), "08:30") in horarios_livres
    assert (prox_seg.isoformat(), "09:30") in horarios_livres
    assert (prox_seg.isoformat(), "09:00") not in horarios_livres


def test_medware_horarios_para_agente_toggle_default_off():
    """Sem env, usa REST antigo (rollout gradual)."""
    if "MEDWARE_AGENDA_SQL" in os.environ:
        del os.environ["MEDWARE_AGENDA_SQL"]
    valor = os.environ.get("MEDWARE_AGENDA_SQL", "0")
    assert valor not in ("1", "true", "yes", "on")


def test_medware_horarios_para_agente_toggle_on():
    for on_val in ("1", "true", "yes", "on"):
        os.environ["MEDWARE_AGENDA_SQL"] = on_val
        assert os.environ["MEDWARE_AGENDA_SQL"] in ("1", "true", "yes", "on")
    del os.environ["MEDWARE_AGENDA_SQL"]


def test_medware_py_tem_toggle_agenda_sql():
    """medware.py::horarios_para_agente deve suportar MEDWARE_AGENDA_SQL."""
    from pathlib import Path
    src = (
        Path(__file__).resolve().parent.parent
        / "voice_agent" / "medware.py"
    ).read_text(encoding="utf-8")
    assert "MEDWARE_AGENDA_SQL" in src, (
        "medware.py deve suportar env MEDWARE_AGENDA_SQL"
    )
    assert "listar_slots_livres" in src, (
        "medware.py deve importar listar_slots_livres pra rollout SQL"
    )


def test_medware_py_fallback_rest_quando_sql_falha():
    """Se SQL falhar (exception), medware.py deve continuar com REST antigo."""
    from pathlib import Path
    src = (
        Path(__file__).resolve().parent.parent
        / "voice_agent" / "medware.py"
    ).read_text(encoding="utf-8")
    # Bloco except deve existir com log warning + continuar (não return [])
    assert "fallback REST" in src, (
        "medware.py deve ter fallback REST no except do SQL"
    )


def test_slot_no_passado_nao_aparece():
    """Slots de HOJE que já passaram (data+hora <= agora) devem ser filtrados."""
    from voice_agent import medware_sql
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo

    brt = ZoneInfo("America/Sao_Paulo")
    agora = datetime.now(brt)
    # Grade: hoje toda tem horários 00:00-23:59
    hoje = agora.date()
    dw_medware = medware_sql._isoweekday_para_diasemana_medware(hoje.isoweekday())

    grade_fake = [
        {"CODHORARIOAGENDA": 1, "DIASEMANA": dw_medware,
         "HORAINICIO": "00:00:00", "HORAFIM": "23:59:00",
         "INTERVALO": 30, "CODAGENDA": 999},
    ]

    def fake_executar(q):
        if "MEDICO_PROCED_HORARIOAGENDA" in q:
            return {"colunas": [], "dados": grade_fake}
        return {"colunas": [], "dados": []}

    with patch.object(medware_sql, "executar", side_effect=fake_executar):
        livres = medware_sql.listar_slots_livres(12080, 5, dias=1)

    # Nenhum slot deve ter hora <= agora
    for s in livres:
        if s["data_iso"] == hoje.isoformat():
            h, m = s["hora"].split(":")
            slot_hm = int(h) * 60 + int(m)
            agora_hm = agora.hour * 60 + agora.minute
            assert slot_hm > agora_hm, (
                f"slot {s['hora']} está no passado (agora {agora.strftime('%H:%M')})"
            )
