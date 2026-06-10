"""Lia Engineer Autônomo — agente 24/7 que detecta bugs em produção,
propõe fix via Opus, testa, aplica, monitora deploy e faz rollback se falhar.

Componentes principais:
    - detect_bugs : padrões observáveis em notas Kommo
    - propose_fix : Opus 4.6 gera diff + pytest
    - apply_fix   : git commit + push + monitora deploy
    - verify      : smoke test pós-deploy
    - engineer_loop : orquestra tudo (rodado por cron 5min)

Toggle: LIA_ENGINEER_ENABLED=1 no Easypanel
"""
from .detect_bugs import (
    BugReport,
    detectar_bugs_em_lead,
    detectar_padroes_em_texto,
    detectar_padroes_sliding_window,
    PADROES_BUG,
)
from .propose_fix import FixProposal, propor_fix, confianca_suficiente
from .engineer_loop import EngineerState, engineer_tick, processar_bug

__all__ = [
    "BugReport", "detectar_bugs_em_lead", "detectar_padroes_em_texto",
    "detectar_padroes_sliding_window", "PADROES_BUG",
    "FixProposal", "propor_fix", "confianca_suficiente",
    "EngineerState", "engineer_tick", "processar_bug",
]
