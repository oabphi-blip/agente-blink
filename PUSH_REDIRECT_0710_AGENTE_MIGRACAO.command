#!/bin/bash
  # PUSH_REDIRECT_0710_AGENTE_MIGRACAO.command
  # Script de implantação do agente redirecionador 0710 → 8133
  # Executa: patch nos arquivos existentes + pytest + commit + push
  # Fábio — 18/06/2026

  set -e
  cd "$(dirname "$0")"

REPO_DIR="/Users/fabiophilipecostamartins/Documents/Claude/Projects/AGENTE IA BLINK"
  cd "$REPO_DIR"

  echo "=== REDIRECT 0710 → 8133: Deploy ==="
  echo "Diretório: $(pwd)"
  echo ""

  # -------------------------------------------------------
  # 1. Aplicar patches nos arquivos existentes via Python
# -------------------------------------------------------
  echo "[1/5] Aplicando patches em settings.py e webhook.py..."

python3 - <<'PYEOF'
  import re, sys

# -------------------------------------------------------
  # PATCH settings.py — adicionar 4 novas envs
  # -------------------------------------------------------
  settings_path = "voice_agent/settings.py"
  with open(settings_path, encoding="utf-8") as f:
    content = f.read()

  NEW_FIELDS = '''
    # Agente redirecionador 0710 → 8133
    redirect_0710_enabled: bool = True
  redirect_0710_max_turnos_dia: int = 3
    redirect_0710_dedup_ttl_dias: int = 7
    redirect_0710_modelo: str = "claude-haiku-4-5-20251001"
  '''

  # Insere antes da linha @classmethod def load(
  if "redirect_0710_enabled" not in content:
    content = content.replace(
              "  @classmethod\n  def load(cls)",
              NEW_FIELDS + "\n  @classmethod\n  def load(cls)"
          )
          # Também adiciona no método load():
          LOAD_ADD = '''
      redirect_0710_enabled = os.getenv("REDIRECT_0710_ENABLED", "1").strip() in ("1", "true", "yes")
      redirect_0710_max_turnos_dia = int(os.getenv("REDIRECT_0710_MAX_TURNOS_DIA", "3") or "3")
      redirect_0710_dedup_ttl_dias = int(os.getenv("REDIRECT_0710_DEDUP_TTL_DIAS", "7") or "7")
      redirect_0710_modelo = os.getenv("REDIRECT_0710_MODELO") or "claude-haiku-4-5-20251001"
  '''
      # Insere antes do return cls(
      content = content.replace(
          "\n    return cls(",
          LOAD_ADD + "\n    return cls(",
          1  # apenas primeira ocorrência
      )
      # Adiciona nos kwargs do return cls(
      RETURN_ADD = '''        redirect_0710_enabled=redirect_0710_enabled,
          redirect_0710_max_turnos_dia=redirect_0710_max_turnos_dia,
          redirect_0710_dedup_ttl_dias=redirect_0710_dedup_ttl_dias,
          redirect_0710_modelo=redirect_0710_modelo,'''
      # Insere antes do fechamento do return cls(
      content = content.replace(
          "        asaas_env=asaas_env,\n    )",
          "        asaas_env=asaas_env,\n" + RETURN_ADD + "\n    )"
      )
      with open(settings_path, "w", encoding="utf-8") as f:
        f.write(content)
              print(f"  ✓ settings.py atualizado com 4 novas envs")
  else:
      print(f"  ✓ settings.py já tem redirect_0710_enabled — skip")

# -------------------------------------------------------
  # PATCH webhook.py — adicionar import + dispatcher 0710
  #   e endpoints admin
  # -------------------------------------------------------
  webhook_path = "voice_agent/webhook.py"
  with open(webhook_path, encoding="utf-8") as f:
    wh = f.read()

  # 1. Adicionar import do redirect_0710
  IMPORT_LINE = "from .redirect_0710 import handle_inbound_0710\n"
  if "from .redirect_0710" not in wh:
    wh = wh.replace(
              "from . import followup\n",
              "from . import followup\n" + IMPORT_LINE
          )
          print("  ✓ webhook.py: import adicionado")

  # 2. Detectar instância 0710 no endpoint /webhook — ANTES do pipeline normal
# A lógica do 0710 precisa rodar ANTES de _aviso_unificacao_se_novo
# Vamos inserir após a linha que seta evolution.instance = instance
DISPATCH_BLOCK = '''
          # ─── CANAL 0710 (legado Evolution) → agente redirecionador ───────
          # Se a instância é o canal antigo (0710), desvia para o handler
          # de migração — NÃO entra no pipeline completo da Lia.
          _inst_name = (instance or settings.evolution_default_instance or "").lower()
          if "0710" in _inst_name or "9663" in _inst_name:
            if msg_type in (
                "audioMessage", "pttMessage", "conversation",
                "extendedTextMessage", "imageMessage", "documentMessage",
            ):
                import anthropic as _anthropic
                _anth = _anthropic.Anthropic(api_key=settings.anthropic_api_key)
                  _redis_0710 = getattr(pipeline, "_redis", None) or getattr(conversation_store, "_redis", None)
                threading.Thread(
                      target=handle_inbound_0710,
                      kwargs=dict(
                          phone=remote_jid,
                          texto=_extract_text(message) or f"[{msg_type}]",
                          redis_client=_redis_0710,
                          kommo_client=pipeline.kommo if hasattr(pipeline, "kommo") else None,
                          evolution_client=evolution,
                          anthropic_client=_anth,
                          enabled=settings.redirect_0710_enabled,
                          max_turnos_dia=settings.redirect_0710_max_turnos_dia,
                          dedup_ttl_dias=settings.redirect_0710_dedup_ttl_dias,
                          modelo=settings.redirect_0710_modelo,
                      ),
                      daemon=True,
                  ).start()
              return JSONResponse({"ok": True, "canal": "0710_redirect"})
          # ──────────────────────────────────────────────────────────────────
'''

  if "CANAL 0710" not in wh:
    # Insere após "if instance:\n        evolution.instance = instance\n"
    wh = wh.replace(
              "    if instance:\n        evolution.instance = instance\n\n",
              "    if instance:\n        evolution.instance = instance\n" + DISPATCH_BLOCK + "\n",
              1
          )
          print("  ✓ webhook.py: dispatcher 0710 adicionado")

  # 3. Adicionar endpoints admin para o 0710
  ADMIN_ENDPOINTS = '''

  # ================================================================
  # ENDPOINTS ADMIN — Agente Redirecionador 0710 → 8133
  # ================================================================

  @app.get("/admin/redirect-0710-status")
  def redirect_0710_status(secret: str = "") -> JSONResponse:
    """Status e métricas do agente redirecionador 0710."""
      if settings.webhook_secret and secret != settings.webhook_secret:
        raise HTTPException(401, "Unauthorized")
    import os as _os
    from datetime import datetime, timezone
      _redis = getattr(pipeline, "_redis", None) or getattr(conversation_store, "_redis", None)
    hoje = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
    result = {
          "enabled": settings.redirect_0710_enabled,
          "modelo": settings.redirect_0710_modelo,
          "dedup_ttl_dias": settings.redirect_0710_dedup_ttl_dias,
          "max_turnos_dia": settings.redirect_0710_max_turnos_dia,
          "today": hoje,
          "total_dia": 0,
          "top_angulos": {},
        "silenciados_etapa_inativa": 0,
  }
      if _redis is not None:
        try:
            result["total_dia"] = int(_redis.get(f"blink:redirect_0710:total_dia:{hoje}") or 0)
            for ang in ("acolhimento", "conveniencia", "autoridade", "urgencia", "seguranca", "fallback"):
                v = _redis.get(f"blink:redirect_0710:angulo:{ang}:{hoje}")
                if v:
                    result["top_angulos"][ang] = int(v)
        except Exception as e:
            result["redis_error"] = str(e)[:120]
    return JSONResponse(result)

@app.get("/admin/redirect-0710-metrics")
def redirect_0710_metrics(secret: str = "") -> JSONResponse:
    """Métricas históricas do agente redirecionador 0710."""
    if settings.webhook_secret and secret != settings.webhook_secret:
        raise HTTPException(401, "Unauthorized")
    from datetime import datetime, timezone
    _redis = getattr(pipeline, "_redis", None) or getattr(conversation_store, "_redis", None)
    hoje = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
    result = {"today": hoje, "enabled": settings.redirect_0710_enabled}
    if _redis is not None:
        try:
            keys = list(_redis.scan_iter("blink:redirect_0710:total_dia:*"))
            historico = {}
            for k in keys:
                day = k.decode() if isinstance(k, bytes) else k
                day = day.split(":")[-1]
                v = _redis.get(k)
                historico[day] = int(v or 0)
            result["historico_total"] = historico
        except Exception as e:
            result["redis_error"] = str(e)[:120]
    return JSONResponse(result)
'''

if "/admin/redirect-0710-status" not in wh:
    # Insere antes do último comentário de fim de arquivo ou no final
    if "# ================================================================" in wh:
        # Adiciona antes do último endpoint de saúde ou no final
        wh = wh.rstrip() + "\n" + ADMIN_ENDPOINTS
    else:
        wh = wh.rstrip() + "\n" + ADMIN_ENDPOINTS
    print("  ✓ webhook.py: endpoints admin adicionados")

with open(webhook_path, "w", encoding="utf-8") as f:
    f.write(wh)

print("  ✓ webhook.py salvo")
print("")
print("Patches aplicados com sucesso!")
PYEOF

echo ""
echo "[2/5] Rodando pytest..."
python3 -m pytest tests/test_redirect_0710.py -v --tb=short 2>&1 | tail -50

echo ""
echo "[3/5] Rodando sanity check de import..."
python3 -c "from voice_agent.redirect_0710 import handle_inbound_0710; print('  ✓ import OK')"

echo ""
echo "[4/5] Fazendo git add + commit..."
git add voice_agent/redirect_0710.py
git add voice_agent/knowledge_base/_PROMPT_REDIRECT_0710.md
git add tests/test_redirect_0710.py
git add voice_agent/settings.py
git add voice_agent/webhook.py
git add PUSH_REDIRECT_0710_AGENTE_MIGRACAO.command

git diff --staged --stat

git commit -m "feat: PUSH_REDIRECT_0710_AGENTE_MIGRACAO — agente redirecionador 0710→8133

- voice_agent/redirect_0710.py: handler principal com dedup, filtros, 5 ângulos
- voice_agent/knowledge_base/_PROMPT_REDIRECT_0710.md: prompt v1 (800 palavras)
- tests/test_redirect_0710.py: 25 cenários pytest
- voice_agent/settings.py: 4 novas envs (REDIRECT_0710_*)
- voice_agent/webhook.py: dispatcher 0710 + endpoints admin
- PUSH_REDIRECT_0710_AGENTE_MIGRACAO.command: este script

Etapas inativas: 106563343,106157139,106484343,106484347
Link oficial: https://wa.me/556181331005?text=...(-0710)
Toggle: REDIRECT_0710_ENABLED=0 no Easypanel para rollback sem deploy"

echo ""
echo "[5/5] Fazendo git push..."
git push origin main

echo ""
echo "=== Deploy concluído! ==="
echo "Aguarde 3 minutos para auto-deploy no Easypanel."
echo "Smoke test: enviar mensagem ao 0710 (61 9 9663-0710)"
echo ""
echo "Entrada em produção: $(date '+%d/%m/%Y %H:%M') BRT"
