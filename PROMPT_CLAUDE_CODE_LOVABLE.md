# Prompt pronto pra Claude Code — Lovable Fase 2

**Como usar:** abre Claude Code no Terminal, cola o bloco abaixo, Enter. Ele executa autônomo.

---

```
Você vai me ajudar a instalar Lovable Fase 2 no projeto Blink Oftalmologia. Vou dar contexto e depois executar em etapas.

CONTEXTO:
- Repo local: /Users/fabiophilipecostamartins/Documents/Claude/Projects/AGENTE IA BLINK
- Este é o agente Python (voice_agent/) que responde WhatsApp Blink 24/7
- Deploy em Easypanel: https://blink-agent.6prkfn.easypanel.host
- Briefing técnico completo em: BRIEFING_LOVABLE_FASE2_BLINK.md (896 linhas)
- Plano master em: LOVABLE_PLANO_MASTER.md

CREDENCIAIS SUPABASE (Fábio já criou):
Vou colar em .env.local antes de você começar:
- SUPABASE_URL=<vou colar>
- SUPABASE_SERVICE_ROLE_KEY=<vou colar>

FASE 1 — SCHEMA SUPABASE (você executa TUDO agora):

1. Verifica se Supabase CLI está instalado: `supabase --version`
   Se não tiver, instala: `brew install supabase/tap/supabase`

2. Login: `supabase login` (pode abrir browser, aprovo se abrir)

3. Cria pasta migrations local:
   `mkdir -p supabase/migrations`

4. Cria arquivo `supabase/migrations/20260703000001_fase1_schema.sql` com o schema EXATO do briefing seção 4.4 e seção 5.2:
   - Tabela `medware_agenda` (agenda_id, cod_agenda, cod_medico, cod_unidade, data, hora, duracao_min, especialidade, status, cod_paciente_reservado, medware_sync_ts, UNIQUE)
   - Tabela `medico_ferias` (id, cod_medico, data_inicio, data_fim, motivo)
   - Tabela `medware_sync_log` (sync_id, started_at, ended_at, sucesso, slots_atualizados, erro)
   - Tabela `events` (event_id, timestamp, tipo, lead_id, pacient_ref, payload jsonb, source)
   - Tabela `patients_cache` (paciente_id, nome, data_nasc, convenio_atual, ultima_consulta_ts)
   - Tabela `sync_lock` (recurso, locked_by, expires_at)

5. Adiciona RLS policies restringindo acesso ao service_role:
   ```sql
   ALTER TABLE medware_agenda ENABLE ROW LEVEL SECURITY;
   CREATE POLICY "service_role_all" ON medware_agenda FOR ALL USING (auth.role() = 'service_role');
   -- repete pra cada tabela
   ```

6. Cria índices:
   ```sql
   CREATE INDEX agenda_data_med ON medware_agenda(data, cod_medico);
   CREATE INDEX events_lead_ts ON events(lead_id, timestamp DESC);
   CREATE INDEX patients_conv ON patients_cache(convenio_atual);
   ```

7. Aplica: `supabase db push --linked` (se linkou antes) OU `supabase migration up`

8. Cria view materializada `vw_pacient_estado_atual`:
   ```sql
   CREATE MATERIALIZED VIEW vw_pacient_estado_atual AS
   SELECT DISTINCT ON (pacient_ref)
     pacient_ref,
     tipo AS ultimo_evento_tipo,
     timestamp AS ultimo_evento_ts,
     payload
   FROM events
   ORDER BY pacient_ref, timestamp DESC;
   CREATE UNIQUE INDEX vw_pacient_idx ON vw_pacient_estado_atual(pacient_ref);
   ```

9. Verifica com psql:
   `psql <SUPABASE_URL> -c "\dt"` → deve mostrar 6 tabelas + 1 view

10. Salva output de cada passo num arquivo `LOVABLE_INSTALL_LOG.md` no repo.

ENTREGA ESPERADA:
- Migrations aplicadas
- 6 tabelas + 1 view materializada existem no Supabase
- LOVABLE_INSTALL_LOG.md commitado com resultado de cada etapa
- Responde: "Fase 1 OK. Prossigo pra Fase 3 (endpoint agent)?"

REGRAS:
- Se qualquer comando falhar, NÃO ignora — para e explica erro
- NÃO commita SUPABASE_SERVICE_ROLE_KEY em lugar nenhum (só .env.local que está no gitignore)
- NÃO faz git push até você confirmar que Fase 1 rodou
- Se schema já existir, avisa antes de dropar
```

---

## Depois da Fase 1, cola isto pra Fase 3:

```
Fase 1 OK. Agora Fase 3 — endpoint /lovable/events no agent.

1. Lê seção 6 do BRIEFING_LOVABLE_FASE2_BLINK.md
2. Adiciona no voice_agent/webhook.py:
   - POST /lovable/events com validação HMAC-SHA256
   - Header X-Lovable-Signature = hmac_sha256(LOVABLE_SIGNING_KEY, body)
3. Adiciona envs no voice_agent/settings.py:
   - LOVABLE_ENDPOINT_URL
   - LOVABLE_SIGNING_KEY (default: string vazia = feature off)
4. Em voice_agent/pipeline.py, após cada turn:
   - Se LOVABLE_ENDPOINT_URL setado, POST evento {tipo: "turn_complete", lead_id, timestamp, ctx.known, resposta_lia_snippet}
   - Não bloqueia se falhar (fire-and-forget com timeout 2s)
5. Cria pytest tests/test_lovable_events_endpoint.py com 5 cenários:
   - HMAC válido → 200
   - HMAC inválido → 401
   - Body sem tipo → 400
   - Evento aceito grava em fila Redis
   - Feature-flag off → skip

6. Commit e push:
   git add voice_agent/webhook.py voice_agent/settings.py voice_agent/pipeline.py tests/test_lovable_events_endpoint.py
   git commit -m "feat(lovable-fase2): endpoint /lovable/events + emissão de eventos por turn"
   git push origin main

7. Fábio adiciona no Easypanel:
   LOVABLE_ENDPOINT_URL=<vou colar depois do Claude Chrome publicar>
   LOVABLE_SIGNING_KEY=<gera 64 chars hex agora com openssl rand -hex 32>

ENTREGA:
- Código commitado + pushed
- Pytest verde
- Responde: "Fase 3 OK. Pronto pra Fase 4 (sync Medware→Supabase)?"
```

---

## Depois disso, Fase 4:

```
Fase 4 — cron sync Medware→Supabase a cada 5min.

1. Cria voice_agent/lovable_sync.py:
   - Cliente Supabase (usa supabase-py)
   - Função sync_medware_agenda(dias=30):
     * Chama Medware Agenda/Listar janela 30d
     * Upsert em medware_agenda por (cod_medico, cod_unidade, data, hora)
     * Grava resultado em medware_sync_log
     * Retorna {ok, slots_atualizados, duracao_ms}
2. Adiciona no cron_interno.py:
   - Se LOVABLE_SYNC_ENABLED=1, roda sync_medware_agenda() a cada 5min
   - Se 3 falhas seguidas, POST no Slack via SLACK_WEBHOOK_BUGS_URL
3. Pytest tests/test_lovable_sync.py com mocks
4. Commit e push

ENTREGA:
- Sync roda a cada 5min em prod
- Alerta Slack funcionando
- Responde: "Fase 4 OK."
```
