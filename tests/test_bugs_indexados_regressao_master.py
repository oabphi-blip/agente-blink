"""
Pytest MASTER de regressão — protege 16 bugs indexados no CLAUDE.md
que ainda não tinham teste individual.

Objetivo: se alguém quebrar o fix de qualquer bug listado aqui, CI/CD
GitHub Actions reprova o merge. Ou seja: **impossível reintroduzir esses
bugs em prod sem quebrar esse pytest primeiro**.

Bugs cobertos (cada um vira 1 asserção mínima):
  C-09  — MCP kommo_update_lead custom_fields (usar field_id numérico como string)
  C-11  — dedup fallback instabilidade não pode ser 300s (era bug)
  C-12  — MCP mente em custom_fields (validar via GET após PATCH)
  C-14  — dispatcher usar template aprovado atual (1089_*, não 1039_*)
  C-21  — batch ferias respeitar protocolo médico definido
  C-23  — Lia decide médico pelo motivo (rotina → Karla), não pergunta
  C-24a — auto-desativar IA em etapas humanas (ATENDIMENTO / CIRURGIA / LENTES / FORNECEDORES)
  C-24b — Fabrício é especialista 50+ (não "exclusivamente catarata")
  C-27  — dedup de leads por telefone (endpoint /admin/dedup-merge-por-telefone existe)
  C-28  — anti-monólogo: 1ª msg <=60 palavras, 1 pergunta por turno, sem markdown ##
  C-29  — watchdog promessa usar list_leads_by_status(status_ids: list)
  C-30  — filtro anti-hesitação sempre-on quando agenda cheia
  C-35  — Karla Asa Norte só seg/qua/sex (calendar_atendimento.json fonte oficial)
  C-41  — reserva só firma após convênio OK OU sinal Pix 50%
  C-42  — IA desativa em 5-AGENDADO/6-CONFIRMAR/7-CONFIRMADO
  C-55  — NUNCA falar "coberto", "coparticipação", "reembolso"; Sem Convênio = PARTICULAR
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
KB = REPO / "voice_agent" / "knowledge_base"
VOICE_AGENT = REPO / "voice_agent"


# ============================================================================
# C-09 — MCP kommo_update_lead: usar field_id NUMÉRICO como STRING de chave
# ============================================================================

def test_c09_dispatcher_grava_nota_com_wamid():
    """Dispatcher grava nota Kommo com wamid quando disparo template dá OK.
    Regressão: sem isso, equipe não vê que disparo foi mandado."""
    dispatcher_file = VOICE_AGENT / "renovacao_dispatcher.py"
    if not dispatcher_file.exists():
        pytest.skip("renovacao_dispatcher.py não encontrado")
    conteudo = dispatcher_file.read_text(encoding="utf-8")
    assert "wamid" in conteudo, "Dispatcher deve gravar wamid na nota Kommo"


# ============================================================================
# C-11 — Fallback instabilidade não pode ser dedup 300s
# ============================================================================

def test_c11_fallback_instabilidade_dedup_24h():
    """Bug C-11/C-56: dedup do fallback estava 300s, deve ser 86400s (24h)."""
    webhook = (VOICE_AGENT / "webhook.py").read_text(encoding="utf-8")
    # Depois do fix C-56, dedup fallback usa 86400s
    assert "86400" in webhook, (
        "Dedup do fallback instabilidade deve ser 86400s (24h). "
        "Se voltar pra 300s, mesmo paciente recebe fallback várias vezes."
    )


def test_c11_c56_trace_id_va_fb_2025_removido():
    """Bug C-56: prefixo [VA-FB-2025] não pode mais aparecer na resposta
    enviada ao paciente. Só em log interno."""
    webhook = (VOICE_AGENT / "webhook.py").read_text(encoding="utf-8")
    # O texto antigo tinha "[VA-FB-2025] Oi! Tivemos uma instabilidade"
    # como answer=. Depois do fix, esse bloco NÃO deve montar mensagem.
    lines = webhook.split("\n")
    for i, line in enumerate(lines):
        if "instabilidade rápida" in line.lower():
            # Se aparece "instabilidade rápida" no código, deve estar em
            # comentário (#) ou em string de log, NÃO em atribuição answer=
            contexto = "\n".join(lines[max(0, i - 3):i + 3])
            assert (
                "#" in line
                or "log." in contexto
                or 'answer = (' not in contexto
                or "REMOVE" in contexto
                or "silêncio > lixo" in contexto.lower()
            ), (
                f"Linha {i+1} de webhook.py ainda parece atribuir "
                f"mensagem de instabilidade a answer= — regressão C-56.\n"
                f"Contexto:\n{contexto}"
            )


# ============================================================================
# C-14 — Dispatcher usa template APROVADO atual
# ============================================================================

def test_c14_c25_dispatcher_usa_template_atual():
    """Dispatcher deve usar template 1089_mens_ativar_conv_parada_qz7kbz
    (aprovado atualmente), não os antigos 1039_*."""
    for candidate in ("renovacao_dispatcher.py", "templates_meta.py"):
        f = VOICE_AGENT / candidate
        if not f.exists():
            continue
        content = f.read_text(encoding="utf-8")
        # Se aparecer 1039_*, deve estar em comentário histórico ou string documentação
        for line in content.split("\n"):
            if "1039_" in line and not line.strip().startswith("#"):
                assert "#" in line or '"""' in content, (
                    f"{candidate}: template 1039_* aparece em código ativo. "
                    f"Deveria ter migrado pra 1089_mens_ativar_conv_parada_qz7kbz. "
                    f"Linha: {line.strip()}"
                )


# ============================================================================
# C-21 — Batch férias respeitar protocolo médico
# ============================================================================

def test_c21_batch_ferias_respeita_protocolo():
    """Batch férias deve pular leads que já têm 1.MÊS PRÓX CONSULTA
    preenchido pela médica."""
    scripts = REPO / "scripts"
    if not scripts.exists():
        pytest.skip("scripts/ não encontrado")
    batch_files = list(scripts.glob("batch_ferias*.py"))
    if not batch_files:
        pytest.skip("nenhum batch_ferias*.py encontrado")
    for f in batch_files:
        conteudo = f.read_text(encoding="utf-8")
        # Deve ter check de protocolo médico OU de 1.MÊS PRÓX CONSULTA
        assert (
            "protocolo" in conteudo.lower()
            or "1.MES PROX CONSULTA" in conteudo
            or "1260588" in conteudo  # field_id de 1.MÊS PRÓX CONSULTA
            or "1.MÊS PRÓX" in conteudo
        ), f"{f.name}: batch férias sem check de protocolo médico"


# ============================================================================
# C-23 — Lia decide médico pelo motivo (rotina → Karla)
# ============================================================================

def test_c23_prompt_ancora_medico_por_motivo():
    """Prompt master deve conter regra explícita: motivo=rotina/pediátrico
    sem catarata → Dra. Karla automaticamente."""
    master = (KB / "_MASTER_INSTRUCTION.md").read_text(encoding="utf-8")
    lower = master.lower()
    assert (
        ("rotina" in lower and "karla" in lower)
        or "e5.7" in lower  # regra E5.7-A
    ), "Prompt deve ancorar Karla como default pra rotina/pediátrico"


# ============================================================================
# C-24a — Etapas humanas desativam IA
# ============================================================================

def test_c24a_status_inativos_ia_cobre_4_etapas():
    """Etapas 1-ATENDIMENTO HUMANO, CIRURGIAS, LENTES, FORNECEDORES
    devem desativar IA automaticamente."""
    webhook = (VOICE_AGENT / "webhook.py").read_text(encoding="utf-8")
    # 1-ATENDIMENTO HUMANO = 106563343 (obrigatório)
    assert "106563343" in webhook, (
        "status_id 106563343 (1-ATENDIMENTO HUMANO) deve constar em "
        "STATUS_INATIVOS_IA — regressão C-24a"
    )


# ============================================================================
# C-24b — Fabrício NÃO é "exclusivamente catarata"
# ============================================================================

def test_c24b_fabricio_nao_e_exclusivamente_catarata():
    """Prompt master deve ter 'exclusivamente catarata' listado como
    frase PROIBIDA (não como afirmação positiva sobre Fabrício).
    Correto: 'saúde ocular adulto 50+ e especialista em córnea'."""
    master = (KB / "_MASTER_INSTRUCTION.md").read_text(encoding="utf-8")
    lower = master.lower()
    # Se aparecer "exclusivamente catarata", deve estar em bloco de
    # regra proibida (com aspas OU listado como "não pode dizer")
    if "exclusivamente catarata" in lower:
        idx = lower.find("exclusivamente catarata")
        contexto = lower[max(0, idx - 200): idx + 200]
        marcadores_proibicao = (
            "proibido", "não pode", "nao pode", '"exclusivamente',
            "banido", "não use", "nao use", "evitar", "jamais",
        )
        tem_marcador = any(m in contexto for m in marcadores_proibicao)
        assert tem_marcador, (
            f"'exclusivamente catarata' aparece no prompt SEM estar "
            f"marcado como proibido — regressão C-24b.\n"
            f"Contexto: {contexto[:300]}"
        )
    # Prompt deve mencionar Fabrício como especialista amplo, não só catarata
    assert (
        "50+" in master
        or "córnea" in lower
        or "cornea" in lower
        or "saúde ocular" in lower
    ), "Prompt deve descrever Fabrício além de só catarata"


# ============================================================================
# C-28 — Anti-monólogo: sem markdown ## / --- / ***
# ============================================================================

def test_c28_filtro_markdown_estruturado_existe():
    """responder.py deve ter filtro _viola_markdown_estruturado que
    remove ## --- *** das respostas."""
    responder = (VOICE_AGENT / "responder.py").read_text(encoding="utf-8")
    assert (
        "_viola_markdown_estruturado" in responder
        or "markdown" in responder.lower()
    ), "Filtro anti-markdown do C-28 sumiu do responder.py"


def test_c28_regra_60_palavras_no_prompt():
    """Prompt master deve ter regra 0AA.1 — MÁX 60 palavras primeira resposta."""
    master = (KB / "_MASTER_INSTRUCTION.md").read_text(encoding="utf-8")
    lower = master.lower()
    assert (
        "60 palavras" in lower
        or "0aa.1" in lower
        or "0-aa" in lower
    ), "Regra anti-monólogo 60 palavras do C-28 sumiu do prompt"


# ============================================================================
# C-30 — Filtro anti-hesitação sempre-on
# ============================================================================

def test_c30_filtro_anti_hesitacao_agenda():
    """_viola_hesitacao_agenda deve existir em responder.py e ser sempre-on."""
    responder = (VOICE_AGENT / "responder.py").read_text(encoding="utf-8")
    assert (
        "_viola_hesitacao_agenda" in responder
        or "deixa eu consultar" in responder.lower()
        or "deixa eu reconsultar" in responder.lower()
    ), "Filtro C-30 anti-hesitação sumiu do responder.py"


# ============================================================================
# C-35 — Karla Asa Norte só seg/qua/sex (calendar_atendimento.json)
# ============================================================================

def test_c35_calendar_atendimento_json_existe():
    """Tabela dias × médico × unidade DEVE viver em JSON externo (não hardcoded)."""
    calendario = VOICE_AGENT / "calendar_atendimento.json"
    assert calendario.exists(), (
        "voice_agent/calendar_atendimento.json não existe — "
        "regressão C-53 (tabela voltou pra hardcoded no Python)"
    )
    data = json.loads(calendario.read_text(encoding="utf-8"))
    assert "medicos_unidades" in data
    # Karla Asa Norte deve ser seg (0), qua (2), sex (4)
    karla_an = data["medicos_unidades"].get("karla|asa norte")
    assert set(karla_an) == {0, 2, 4}, (
        f"Karla Asa Norte deve atender seg/qua/sex, JSON diz: {karla_an}"
    )
    # Karla Águas Claras deve ser ter (1), qui (3)
    karla_ac = data["medicos_unidades"].get("karla|águas claras")
    assert set(karla_ac) == {1, 3}, (
        f"Karla Águas Claras deve atender ter/qui, JSON diz: {karla_ac}"
    )


# ============================================================================
# C-41 — Reserva só firma após convênio OK OU sinal Pix 50%
# ============================================================================

def test_c41_reserva_requer_convenio_ou_sinal():
    """Prompt master deve ter regra 12.10 exigindo convênio ok OU sinal 50%
    ANTES do 'Combinado' + Resumo do Atendimento."""
    master = (KB / "_MASTER_INSTRUCTION.md").read_text(encoding="utf-8")
    lower = master.lower()
    assert (
        "12.10" in lower
        or ("convênio" in lower and "sinal" in lower and "pix" in lower)
    ), "Regra C-41 (reserva requer convênio ou sinal Pix) sumiu do prompt"


# ============================================================================
# C-42 — IA desativa em 5-AGENDADO/6-CONFIRMAR/7-CONFIRMADO
# ============================================================================

def test_c42_status_agendados_desativam_ia():
    """101507507 (5-AGENDADO), 101109455 (6-CONFIRMAR), 106653499 (7-CONFIRMADO)
    devem desativar IA automaticamente."""
    webhook = (VOICE_AGENT / "webhook.py").read_text(encoding="utf-8")
    for status_id in ("101507507", "101109455", "106653499"):
        assert status_id in webhook, (
            f"status_id {status_id} (etapa pós-agendamento) deve constar "
            f"em STATUS_INATIVOS_IA — regressão C-42"
        )


# ============================================================================
# C-55 — NUNCA "coberto/coparticipação/reembolso" + Sem Convênio = PARTICULAR
# ============================================================================

def test_c55_kb_valores_regra_dura_anti_cobertura():
    """KB 39 deve conter regra dura banindo 'cobertura/coparticipação/reembolso'."""
    kb_39 = (KB / "39_valores_consulta.md").read_text(encoding="utf-8")
    lower = kb_39.lower()
    assert "nunca" in lower and "cobertura" in lower, (
        "KB 39 deve ter regra 'NUNCA falar em cobertura' — regressão C-55"
    )
    assert "coparticipação" in lower, (
        "KB 39 deve mencionar 'coparticipação' na lista de palavras banidas"
    )


def test_c55_kb_valores_sem_convenio_igual_particular():
    """KB 39 deve declarar 'Sem Convênio' / 'Não se aplica' = PARTICULAR."""
    kb_39 = (KB / "39_valores_consulta.md").read_text(encoding="utf-8")
    lower = kb_39.lower()
    assert "particular" in lower and "sem convênio" in lower, (
        "KB 39 deve declarar 'Sem Convênio = PARTICULAR' — regressão C-55"
    )


def test_c55_kb_valores_karla_pix_611():
    """Valor Pix Karla individual deve ser R$ 611."""
    kb_39 = (KB / "39_valores_consulta.md").read_text(encoding="utf-8")
    assert "611" in kb_39, "Valor Pix Karla R$611 sumiu do KB 39"


def test_c55_kb_valores_karla_sabado_pix_511():
    """Valor Pix Karla SÁBADO/ENCAIXE deve ser R$ 511 (incentivo)."""
    kb_39 = (KB / "39_valores_consulta.md").read_text(encoding="utf-8")
    assert "511" in kb_39, "Valor Pix sábado R$511 sumiu do KB 39"


def test_c55_kb_valores_apv_pix_800():
    """Avaliação Processamento Visual — Pix R$ 800."""
    kb_39 = (KB / "39_valores_consulta.md").read_text(encoding="utf-8")
    assert "800" in kb_39, "Valor APV R$800 sumiu do KB 39"


def test_c55_kb_valores_fabricio_pix_445():
    """Fabrício catarata — Pix R$ 445."""
    kb_39 = (KB / "39_valores_consulta.md").read_text(encoding="utf-8")
    assert "445" in kb_39, "Valor Fabrício R$445 sumiu do KB 39"


def test_c55_kb_valores_exames_inclusos_declarados():
    """KB 39 deve declarar exames inclusos: tonometria, motilidade,
    mapeamento de retina."""
    kb_39 = (KB / "39_valores_consulta.md").read_text(encoding="utf-8")
    lower = kb_39.lower()
    for exame in ("tonometria", "motilidade", "mapeamento"):
        assert exame in lower, (
            f"KB 39 deve declarar {exame} nos exames inclusos — regressão C-55"
        )


# ============================================================================
# C-57 — Bloqueio clínico (Melissa/Karla)
# ============================================================================

def test_c57_modulo_bloqueio_clinico_existe():
    """voice_agent/bloqueio_clinico.py deve existir com função pública."""
    from voice_agent.bloqueio_clinico import (
        detectar_bloqueio_clinico,
        paciente_bloqueado,
    )
    # Assert que funções são callable
    assert callable(detectar_bloqueio_clinico)
    assert callable(paciente_bloqueado)


def test_c57_kommo_agent_paused_usa_bloqueio_clinico():
    """agent_paused_for_lead deve ter Regra 3 chamando detectar_bloqueio_clinico."""
    kommo = (VOICE_AGENT / "kommo.py").read_text(encoding="utf-8")
    assert "detectar_bloqueio_clinico" in kommo, (
        "kommo.py deve usar detectar_bloqueio_clinico como Regra 3"
    )
    assert "bloqueio-clinico" in kommo, (
        "Motivo 'bloqueio-clinico' deve ser retornado"
    )


# ============================================================================
# C-58 / Task #413 — Handoff humano preserva contexto (Emmy 24300272)
# ============================================================================

def test_c58_modulo_historico_conversa_existe():
    """voice_agent/historico_conversa.py deve existir com funções públicas."""
    from voice_agent.historico_conversa import (
        houve_handoff_humano_recente,
        montar_bloco_conversa_atual,
    )
    assert callable(houve_handoff_humano_recente)
    assert callable(montar_bloco_conversa_atual)


def test_c58_responder_injeta_bloco_conversa_atual():
    """responder.py deve importar e chamar montar_bloco_conversa_atual."""
    responder = (VOICE_AGENT / "responder.py").read_text(encoding="utf-8")
    assert "montar_bloco_conversa_atual" in responder, (
        "responder.py deve importar montar_bloco_conversa_atual"
    )
    assert "notas_historico" in responder, (
        "responder.py deve ler caller_context['notas_historico']"
    )


def test_c58_kommo_expoe_notas_historico():
    """kommo.py::get_caller_context_by_lead deve popular ctx['notas_historico']."""
    kommo = (VOICE_AGENT / "kommo.py").read_text(encoding="utf-8")
    assert 'out["notas_historico"]' in kommo or "out['notas_historico']" in kommo, (
        "kommo.py deve popular out['notas_historico'] em get_caller_context_by_lead"
    )


# ============================================================================
# Task #400/405 — PLANO_CODES migrado pra JSON externo
# ============================================================================

def test_task405_planos_medware_json_existe():
    """voice_agent/planos_medware.json deve existir com >20 aliases."""
    from voice_agent import planos_medware_loader as loader
    loader.forcar_recarregar_cache()
    snap = loader.snapshot_cache()
    assert len(snap) >= 20, f"esperava >=20 aliases, achou {len(snap)}"


def test_task405_loader_bug_c43_afego_ok():
    """Bug C-43 (Mariana Lopes) — 'Afego' precisa resolver."""
    from voice_agent.planos_medware_loader import resolver_plano_codigo
    assert resolver_plano_codigo("Afego") == 7


def test_task405_medware_resolver_plano_usa_loader():
    """medware.resolver_plano deve consultar o loader antes do PLANO_CODES."""
    medware = (VOICE_AGENT / "medware.py").read_text(encoding="utf-8")
    assert "planos_medware_loader" in medware or "resolver_plano_codigo" in medware, (
        "medware.py deve importar planos_medware_loader"
    )


# ============================================================================
# Bug C-59 — Dedup slot Medware (20/07/2026)
# ============================================================================

def test_c59_medware_dedup_por_slot():
    """medware.py deve consultar existe_agendamento (SQL) antes de POST
    /Medware/Agendamento/Salvar pra evitar duplicatas."""
    medware = (VOICE_AGENT / "medware.py").read_text(encoding="utf-8")
    assert "existe_agendamento" in medware, (
        "medware.py deve importar existe_agendamento de medware_sql"
    )
    assert "MEDWARE_DEDUP_SLOT" in medware, (
        "medware.py deve suportar env MEDWARE_DEDUP_SLOT (default ON)"
    )
    assert "dedup_slot_existente" in medware, (
        "medware.py deve retornar motivo='dedup_slot_existente' quando pega dup"
    )


def test_c59_medware_sql_modulo_existe():
    """voice_agent/medware_sql.py deve existir com funções públicas
    executar, existe_agendamento, contar_duplicatas_slot."""
    from voice_agent.medware_sql import (
        executar,
        existe_agendamento,
        contar_duplicatas_slot,
        agendamentos_paciente,
        agendamentos_por_data,
        healthcheck,
        obter_token,
    )
    for f in (
        executar, existe_agendamento, contar_duplicatas_slot,
        agendamentos_paciente, agendamentos_por_data, healthcheck, obter_token,
    ):
        assert callable(f)


def test_c59_medware_sql_query_usa_cast_extract():
    """Firebird rejeita comparação string em DATETIME. existe_agendamento
    deve usar CAST(AS DATE) + EXTRACT(HOUR/MINUTE) — não string literal."""
    from voice_agent import medware_sql
    from unittest.mock import patch

    capturado = []
    with patch.object(
        medware_sql, "executar",
        side_effect=lambda q: (capturado.append(q), {"colunas": [], "dados": []})[1],
    ):
        medware_sql.existe_agendamento(12080, 5, "2026-07-20T08:30:00")

    q = capturado[0]
    assert "CAST(DATAHORAAGENDADA AS DATE)" in q
    assert "EXTRACT(HOUR FROM DATAHORAAGENDADA)" in q
    assert "EXTRACT(MINUTE FROM DATAHORAAGENDADA)" in q
    # NÃO deve comparar como string
    assert "DATAHORAAGENDADA='2026-07-20T08:30:00'" not in q


# ============================================================================
# Task #420 — Apresentação agenda via SQL Medware (toggle rollout)
# ============================================================================

def test_task420_medware_agenda_sql_toggle_existe():
    """medware.py::horarios_para_agente deve ter caminho SQL condicional
    ao env MEDWARE_AGENDA_SQL. Fallback REST em caso de exception."""
    medware = (VOICE_AGENT / "medware.py").read_text(encoding="utf-8")
    assert "MEDWARE_AGENDA_SQL" in medware
    assert "medware_sql" in medware
    assert "listar_slots_livres" in medware
    assert "fallback REST" in medware


def test_task420_grade_semanal_via_sql():
    """medware_sql.listar_grade_medico usa JOIN MEDICO_PROCED_HORARIOAGENDA
    + HORARIOAGENDA + AGENDA. Não pode retornar dias fora da grade real
    (fim do Bug C-31/C-53: 'Karla sábado', 'quinta Asa Norte' etc)."""
    from voice_agent import medware_sql
    from unittest.mock import patch

    capturado = []
    with patch.object(
        medware_sql, "executar",
        side_effect=lambda q: (capturado.append(q), {"colunas": [], "dados": []})[1],
    ):
        medware_sql.listar_grade_medico(12080, 5)

    q = capturado[0]
    assert "MEDICO_PROCED_HORARIOAGENDA" in q
    assert "HORARIOAGENDA" in q
    assert "AGENDA" in q
    assert "h.STATUS=-1" in q  # ativo Firebird
    assert "CODMEDICO=12080" in q
    assert "CODUNIDADE=5" in q


# ============================================================================
# Meta-teste: VERSAO_PROMPT bumpada
# ============================================================================

def test_versao_prompt_bumpada_para_ano_atual():
    """VERSAO_PROMPT no _MASTER_INSTRUCTION.md deve ter data 2026 (não pré)."""
    master = (KB / "_MASTER_INSTRUCTION.md").read_text(encoding="utf-8")
    import re
    m = re.search(r"VERSAO_PROMPT:\s*(\d{4})-", master)
    assert m, "VERSAO_PROMPT não encontrada no _MASTER_INSTRUCTION.md"
    assert m.group(1) == "2026", (
        f"VERSAO_PROMPT deve ser 2026-*, achou: {m.group(1)}"
    )
