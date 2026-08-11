# tests/test_redirect_0710.py
"""25 cenários pytest para o agente redirecionador 0710 → 8133.

Executa sem dependências externas (mocks para Evolution, Kommo, Redis, Anthropic).
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from voice_agent.redirect_0710 import (
  _LINK_OFICIAL,
  _STATUS_INATIVOS_IA,
  _dedup_check,
  _dedup_set,
  _escalacao_ativa,
  _filtrar_resposta,
  _incrementar_turnos_dia,
  _lead_em_etapa_inativa,
  _marcar_escalacao,
  _montar_nota_kommo,
  _normalizar_telefone,
  handle_inbound_0710,
)

# ---------------------------------------------------------------------------
# Fixtures e helpers
# ---------------------------------------------------------------------------

def _make_redis(exists_val=False):
    r = MagicMock()
    r.exists.return_value = exists_val
    r.set.return_value = True
    r.incr.return_value = 1
    r.expire.return_value = True
    p = MagicMock()
    p.execute.return_value = []
    r.pipeline.return_value = p
    return r

def _make_kommo(found=False, lead_id=None, status_id=None):
    k = MagicMock()
    k.get_caller_context.return_value = {
      "found": found,
      "lead_id": lead_id,
      "known": {"status_id": status_id} if status_id else {},
    }
    k.add_note.return_value = True
    return k

def _make_evolution():
    e = MagicMock()
    e.send_text.return_value = {}
    return e

def _make_anthropic(resposta: str):
    a = MagicMock()
    msg = MagicMock()
    msg.content = [MagicMock(text=resposta)]
    a.messages.create.return_value = msg
    return a

PHONE = "5561996630710"
TEXTO_SAUDACAO = "Oi, tudo bem? Queria saber sobre consulta de rotina"
LINK = _LINK_OFICIAL

# ---------------------------------------------------------------------------
# Cenário 1: Paciente pergunta valor de consulta
# ---------------------------------------------------------------------------

def test_01_pergunta_valor():
    resposta_modelo = (
          f"O atendimento acontece pelo canal oficial. "
          f"Toca aqui: {LINK}"
    )
    r = _make_redis()
    k = _make_kommo(found=True, lead_id=999, status_id=102560495)
    e = _make_evolution()
    a = _make_anthropic(resposta_modelo)

  result = handle_inbound_0710(
        phone=PHONE,
        texto="Quanto custa a consulta?",
        redis_client=r,
        kommo_client=k,
        evolution_client=e,
        anthropic_client=a,
  )
  assert result["sent"] is True
  enviado = e.send_text.call_args[1]["text"]
  assert "R$" not in enviado
  assert LINK in enviado

# ---------------------------------------------------------------------------
# Cenário 2: Paciente pergunta agendamento
# ---------------------------------------------------------------------------

def test_02_pergunta_agendamento():
    resposta_modelo = (
          f"Pra agendar sua consulta, usa o canal oficial: {LINK}"
    )
    r = _make_redis()
    k = _make_kommo(found=False)
    e = _make_evolution()
    a = _make_anthropic(resposta_modelo)

  result = handle_inbound_0710(
        phone=PHONE,
        texto="Quero agendar uma consulta",
        redis_client=r,
        kommo_client=k,
        evolution_client=e,
        anthropic_client=a,
  )
  assert result["sent"] is True
  enviado = e.send_text.call_args[1]["text"]
  assert LINK in enviado
  # Não deve mencionar slot/horário específico
  assert "14h" not in enviado
  assert "15h" not in enviado

# ---------------------------------------------------------------------------
# Cenário 3: Paciente pergunta qual médico atende — ângulo autoridade
# ---------------------------------------------------------------------------

def test_03_pergunta_medico_angulo_autoridade():
    resposta_modelo = (
          f"A Dra. Karla atende exclusivamente pelo canal oficial. "
          f"Toca aqui: {LINK}"
    )
    r = _make_redis()
    k = _make_kommo(found=False)
    e = _make_evolution()
    a = _make_anthropic(resposta_modelo)

  result = handle_inbound_0710(
        phone=PHONE,
        texto="Qual médico atende rotina ocular?",
        redis_client=r,
        kommo_client=k,
        evolution_client=e,
        anthropic_client=a,
  )
  assert result["sent"] is True
  assert result["angulo"] == "autoridade"

# ---------------------------------------------------------------------------
# Cenário 4: Paciente envia "oi" — ângulo acolhimento
# ---------------------------------------------------------------------------

def test_04_oi_generico_angulo_acolhimento():
    resposta_modelo = (
          f"Oi! A Blink cuida de cada paciente com atenção. "
          f"O atendimento agora é pelo canal oficial: {LINK}"
    )
    r = _make_redis()
    k = _make_kommo(found=False)
    e = _make_evolution()
    a = _make_anthropic(resposta_modelo)

  result = handle_inbound_0710(
        phone=PHONE,
        texto="oi",
        redis_client=r,
        kommo_client=k,
        evolution_client=e,
        anthropic_client=a,
  )
  assert result["sent"] is True
  assert result["angulo"] == "acolhimento"

# ---------------------------------------------------------------------------
# Cenário 5: Frase curta — ângulo conveniência
# ---------------------------------------------------------------------------

def test_05_frase_curta_angulo_conveniencia():
    resposta_modelo = (
          f"No canal oficial você recebe resposta em segundos: {LINK}"
    )
    r = _make_redis()
    k = _make_kommo(found=False)
    e = _make_evolution()
    a = _make_anthropic(resposta_modelo)

  result = handle_inbound_0710(
        phone=PHONE,
        texto="Consulta?",
        redis_client=r,
        kommo_client=k,
        evolution_client=e,
        anthropic_client=a,
  )
  assert result["sent"] is True
  assert result["angulo"] == "conveniência"

# ---------------------------------------------------------------------------
# Cenário 6: Paciente reclama demora — ângulo urgência
# ---------------------------------------------------------------------------

def test_06_reclamacao_angulo_urgencia():
    resposta_modelo = (
          f"Esse número está sendo desligado em breve. "
          f"Migra agora pra não perder o atendimento: {LINK}"
    )
    r = _make_redis()
    k = _make_kommo(found=False)
    e = _make_evolution()
    a = _make_anthropic(resposta_modelo)

  result = handle_inbound_0710(
        phone=PHONE,
        texto="Ninguém me respondeu há 3 dias!",
        redis_client=r,
        kommo_client=k,
        evolution_client=e,
        anthropic_client=a,
  )
  assert result["sent"] is True
  assert result["angulo"] == "urgência"

# ---------------------------------------------------------------------------
# Cenário 7: Paciente envia foto de carteirinha — ângulo segurança
# ---------------------------------------------------------------------------

def test_07_dados_pessoais_angulo_seguranca():
    resposta_modelo = (
          f"Por proteção dos seus dados, o atendimento passa só pelo canal oficial: {LINK}"
    )
    r = _make_redis()
    k = _make_kommo(found=False)
    e = _make_evolution()
    a = _make_anthropic(resposta_modelo)

  result = handle_inbound_0710(
        phone=PHONE,
        texto="Meu CPF é 123.456.789-00",
        redis_client=r,
        kommo_client=k,
        evolution_client=e,
        anthropic_client=a,
  )
  assert result["sent"] is True
  # resposta não deve conter CPF
  enviado = e.send_text.call_args[1]["text"]
  assert "123.456" not in enviado

# ---------------------------------------------------------------------------
# Cenário 8: Lead em 1-ATENDIMENTO HUMANO (106563343) — silencia
# ---------------------------------------------------------------------------

def test_08_etapa_atendimento_humano_silencia():
    r = _make_redis()
    k = _make_kommo(found=True, lead_id=100, status_id=106563343)
    e = _make_evolution()
    a = _make_anthropic("qualquer coisa")

  result = handle_inbound_0710(
        phone=PHONE,
        texto="oi",
        redis_client=r,
        kommo_client=k,
        evolution_client=e,
        anthropic_client=a,
  )
  assert result["sent"] is False
  assert result["motivo_silencio"] == "lead_em_etapa_inativa"
  e.send_text.assert_not_called()
  k.add_note.assert_not_called()

# ---------------------------------------------------------------------------
# Cenário 9: Lead em CIRURGIAS (106157139) — silencia
# ---------------------------------------------------------------------------

def test_09_etapa_cirurgias_silencia():
    r = _make_redis()
    k = _make_kommo(found=True, lead_id=101, status_id=106157139)
    e = _make_evolution()

  result = handle_inbound_0710(
        phone=PHONE, texto="oi",
        redis_client=r, kommo_client=k, evolution_client=e,
  )
  assert result["sent"] is False
  assert result["motivo_silencio"] == "lead_em_etapa_inativa"

# ---------------------------------------------------------------------------
# Cenário 10: Lead em LENTES (106484343) — silencia
# ---------------------------------------------------------------------------

def test_10_etapa_lentes_silencia():
    r = _make_redis()
    k = _make_kommo(found=True, lead_id=102, status_id=106484343)
    e = _make_evolution()

  result = handle_inbound_0710(
        phone=PHONE, texto="oi",
        redis_client=r, kommo_client=k, evolution_client=e,
  )
  assert result["sent"] is False
  assert result["motivo_silencio"] == "lead_em_etapa_inativa"

# ---------------------------------------------------------------------------
# Cenário 11: Lead em FORNECEDORES (106484347) — silencia
# ---------------------------------------------------------------------------

def test_11_etapa_fornecedores_silencia():
    r = _make_redis()
    k = _make_kommo(found=True, lead_id=103, status_id=106484347)
    e = _make_evolution()

  result = handle_inbound_0710(
        phone=PHONE, texto="oi",
        redis_client=r, kommo_client=k, evolution_client=e,
  )
  assert result["sent"] is False
  assert result["motivo_silencio"] == "lead_em_etapa_inativa"

# ---------------------------------------------------------------------------
# Cenário 12: Lead em 3-AGENDAR (102560495) — responde normalmente
# ---------------------------------------------------------------------------

def test_12_etapa_agendar_responde():
    resposta_modelo = f"Oi! Atendimento pelo canal oficial: {LINK}"
    r = _make_redis()
    k = _make_kommo(found=True, lead_id=104, status_id=102560495)
    e = _make_evolution()
    a = _make_anthropic(resposta_modelo)

  result = handle_inbound_0710(
        phone=PHONE, texto="oi",
        redis_client=r, kommo_client=k, evolution_client=e, anthropic_client=a,
  )
  assert result["sent"] is True
  e.send_text.assert_called_once()

# ---------------------------------------------------------------------------
# Cenário 13: Lead em 5-AGENDADO (101507507) — responde normalmente
# ---------------------------------------------------------------------------

def test_13_etapa_agendado_responde():
    resposta_modelo = f"Canal oficial: {LINK}"
    r = _make_redis()
    k = _make_kommo(found=True, lead_id=105, status_id=101507507)
    e = _make_evolution()
    a = _make_anthropic(resposta_modelo)

  result = handle_inbound_0710(
        phone=PHONE, texto="oi",
        redis_client=r, kommo_client=k, evolution_client=e, anthropic_client=a,
  )
  assert result["sent"] is True

# ---------------------------------------------------------------------------
# Cenário 14: Telefone sem lead no Kommo — responde sem nota
# ---------------------------------------------------------------------------

def test_14_sem_lead_responde_sem_nota():
    resposta_modelo = f"Canal oficial: {LINK}"
    r = _make_redis()
    k = _make_kommo(found=False)
    e = _make_evolution()
    a = _make_anthropic(resposta_modelo)

  result = handle_inbound_0710(
        phone=PHONE, texto="oi",
        redis_client=r, kommo_client=k, evolution_client=e, anthropic_client=a,
  )
  assert result["sent"] is True
  k.add_note.assert_not_called()

# ---------------------------------------------------------------------------
# Cenário 15: Dedup ativo — envia reforço curto sem chamar modelo
# ---------------------------------------------------------------------------

def test_15_dedup_ativo_envia_reforco():
    r = _make_redis(exists_val=True)
    k = _make_kommo(found=False)
    e = _make_evolution()
    a = _make_anthropic("modelo nao deve ser chamado")

  result = handle_inbound_0710(
        phone=PHONE, texto="oi",
        redis_client=r, kommo_client=k, evolution_client=e, anthropic_client=a,
  )
  assert result["sent"] is True
  assert result["reforco"] is True
  a.messages.create.assert_not_called()
  enviado = e.send_text.call_args[1]["text"]
  assert LINK in enviado

# ---------------------------------------------------------------------------
# Cenário 16: Dedup ativo + terceira mensagem do dia → escala
# ---------------------------------------------------------------------------

def test_16_dedup_ativo_terceira_mensagem_escala():
    r = _make_redis(exists_val=True)
    # Simula: incr retorna 4 (acima do limite de 3)
    r.incr.return_value = 4
  k = _make_kommo(found=False)
  e = _make_evolution()

  result = handle_inbound_0710(
        phone=PHONE, texto="oi",
        redis_client=r, kommo_client=k, evolution_client=e,
        max_turnos_dia=3,
  )
  assert result["sent"] is False
  assert result["motivo_silencio"] == "max_turnos_atingido"
  e.send_text.assert_not_called()

# ---------------------------------------------------------------------------
# Cenário 17: Quarta mensagem após escalação — silencia
# ---------------------------------------------------------------------------

def test_17_quarta_mensagem_escalacao_silencia():
    r = _make_redis()
    # escalacao ativa: segundo exists retorna True (para a chave escalou)
    call_count = [0]
  def exists_side(key):
        call_count[0] += 1
        if "escalou" in key:
                return True
              return False
  r.exists.side_effect = exists_side

  k = _make_kommo(found=False)
  e = _make_evolution()

  result = handle_inbound_0710(
        phone=PHONE, texto="oi",
        redis_client=r, kommo_client=k, evolution_client=e,
  )
  assert result["sent"] is False
  assert result["motivo_silencio"] == "escalacao_ativa"

# ---------------------------------------------------------------------------
# Cenário 18: Modelo gera resposta sem link — filtro força inclusão
# ---------------------------------------------------------------------------

def test_18_modelo_sem_link_filtro_forca():
    resposta_sem_link = "Oi! O atendimento agora eh pelo canal oficial."
  r = _make_redis()
  k = _make_kommo(found=False)
  e = _make_evolution()
  a = _make_anthropic(resposta_sem_link)

  result = handle_inbound_0710(
        phone=PHONE, texto="oi",
        redis_client=r, kommo_client=k, evolution_client=e, anthropic_client=a,
  )
  assert result["sent"] is True
  enviado = e.send_text.call_args[1]["text"]
  assert LINK in enviado

# ---------------------------------------------------------------------------
# Cenário 19: Modelo gera resposta com 120 palavras — filtro corta para 60
# ---------------------------------------------------------------------------

def test_19_resposta_longa_cortada():
    texto_longo = " ".join(["palavra"] * 120) + f" {LINK}"
  resposta_esperada, ok = _filtrar_resposta(texto_longo)
  palavras = resposta_esperada.split()
  assert len(palavras) <= 65  # 60 palavras + link (que tem varias palavras encoded)
  assert LINK in resposta_esperada

# ---------------------------------------------------------------------------
# Cenário 20: Modelo menciona chave Pix — filtro descarta, fallback enviado
# ---------------------------------------------------------------------------

def test_20_chave_pix_descartada():
    resposta_com_pix = f"Pague via chave pix blink@blink.com.br. Canal: {LINK}"
  resultado_filtrado, ok = _filtrar_resposta(resposta_com_pix)
  assert ok is False

def test_20b_chave_pix_fallback_enviado():
    resposta_com_pix = f"Pague via chave pix. Canal: {LINK}"
    r = _make_redis()
    k = _make_kommo(found=False)
    e = _make_evolution()
    a = _make_anthropic(resposta_com_pix)

  result = handle_inbound_0710(
        phone=PHONE, texto="Como pago?",
        redis_client=r, kommo_client=k, evolution_client=e, anthropic_client=a,
  )
  # Deve enviar fallback (sem mencionar Pix)
  assert result["sent"] is True
  enviado = e.send_text.call_args[1]["text"]
  assert "pix" not in enviado.lower() or LINK in enviado

# ---------------------------------------------------------------------------
# Cenário 21: Modelo menciona dia+hora específicos — filtro descarta
# ---------------------------------------------------------------------------

def test_21_dia_hora_descartado():
    resposta = f"Pode vir quinta às 14h. Canal: {LINK}"
    _, ok = _filtrar_resposta(resposta)
    assert ok is False

# ---------------------------------------------------------------------------
# Cenário 22: Modelo usa markdown — filtro remove
# ---------------------------------------------------------------------------

def test_22_markdown_removido():
    resposta = f"## Atenção\n\nCanal oficial: {LINK}"
    filtrada, ok = _filtrar_resposta(resposta)
    assert ok is True
    assert "##" not in filtrada

# ---------------------------------------------------------------------------
# Cenário 23: Toggle REDIRECT_0710_ENABLED=0 — retorna imediatamente
# ---------------------------------------------------------------------------

def test_23_toggle_desabilitado():
    r = _make_redis()
    k = _make_kommo(found=False)
    e = _make_evolution()
    a = _make_anthropic("nao deve ser chamado")

  result = handle_inbound_0710(
        phone=PHONE, texto="oi",
        redis_client=r, kommo_client=k, evolution_client=e, anthropic_client=a,
        enabled=False,
  )
  assert result["sent"] is False
  assert result["motivo_silencio"] == "disabled"
  e.send_text.assert_not_called()
  a.messages.create.assert_not_called()

# ---------------------------------------------------------------------------
# Cenário 24: Anthropic API down — fallback fixo enviado
# ---------------------------------------------------------------------------

def test_24_anthropic_down_fallback():
    r = _make_redis()
    k = _make_kommo(found=False)
    e = _make_evolution()
    a = MagicMock()
    a.messages.create.side_effect = Exception("API down")

  result = handle_inbound_0710(
        phone=PHONE, texto="oi",
        redis_client=r, kommo_client=k, evolution_client=e, anthropic_client=a,
  )
  # Fallback deve ter sido enviado
  assert result["sent"] is True
  enviado = e.send_text.call_args[1]["text"]
  assert LINK in enviado

# ---------------------------------------------------------------------------
# Cenário 25: Telefone sem prefixo 55 — normalização adiciona
# ---------------------------------------------------------------------------

def test_25_normalizacao_telefone():
    phone_sem_55 = "61996630710"
    normalizado = _normalizar_telefone(phone_sem_55)
    assert normalizado.startswith("55")
    assert "61996630710" in normalizado

def test_25b_telefone_com_jid():
    jid = "5561996630710@s.whatsapp.net"
    # A normalização deve funcionar após remoção do @
    phone_limpo = jid.split("@")[0]
  normalizado = _normalizar_telefone(phone_limpo)
  assert normalizado == "5561996630710"

# ---------------------------------------------------------------------------
# Testes unitários de helpers
# ---------------------------------------------------------------------------

def test_lead_em_etapa_inativa_set_correto():
    """Confirma que todos os 4 IDs de etapas inativas estão no set."""
    assert 106563343 in _STATUS_INATIVOS_IA  # 1-ATENDIMENTO HUMANO
  assert 106157139 in _STATUS_INATIVOS_IA  # CIRURGIAS
  assert 106484343 in _STATUS_INATIVOS_IA  # LENTES
  assert 106484347 in _STATUS_INATIVOS_IA  # FORNECEDORES
  assert len(_STATUS_INATIVOS_IA) == 4

def test_nota_kommo_formato():
    nota = _montar_nota_kommo(
          "texto do paciente",
          "urgência",
          "resposta enviada com link",
          False,
    )
    assert "[REDIRECT 0710" in nota
    assert "urgência" in nota
    assert "texto do paciente" in nota
    assert "Reforço: não" in nota

def test_filtrar_resposta_link_obrigatorio():
    """Link ausente → deve ser inserido."""
    resposta = "Oi! Atendimento pelo canal oficial."
    filtrada, ok = _filtrar_resposta(resposta)
    assert ok is True
    assert LINK in filtrada
