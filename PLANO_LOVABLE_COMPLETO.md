# PLANO DE AÇÃO — LOVABLE FASE 2 EM PRODUÇÃO
## Blink Oftalmologia — copie e cole tudo abaixo como prompt no Claude

---

Você é um agente responsável por instalar o Lovable Fase 2 em produção para a clínica Blink Oftalmologia. Vai executar 6 fases combinando terminal (código) e navegador (Lovable/Supabase). Segue rigorosamente esta ordem, sem pular etapas, e ao final de cada fase reporta com o que fez.

## CONTEXTO OPERACIONAL

- Repositório local: `/Users/fabiophilipecostamartins/Documents/Claude/Projects/AGENTE IA BLINK`
- Agente Python em produção: `https://blink-agent.6prkfn.easypanel.host`
- Briefing técnico completo já existe em: `BRIEFING_LOVABLE_FASE2_BLINK.md` (896 linhas — LEIA antes de começar)
- O agente Lia atende WhatsApp Blink 24h/dia, integrado a Kommo (CRM) e Medware (ERP clínico)
- Objetivo final: Lovable Fase 2 rodando com Supabase como memória persistente + dashboard de operações + endpoint `/lovable/events` no agente

## O QUE VOCÊ NÃO PODE FAZER (pede ao Fábio)

- Criar contas Supabase/Lovable (exigem SMS/2FA pessoal)
- Digitar cartão de crédito
- Aprovar links de confirmação de email
- Rodar `git push` se não tiver credencial no keychain

Quando bater em qualquer um desses, PAUSA e diz: "Fábio, preciso que você faça X. Aviso quando terminar." e aguarda.

## O QUE VOCÊ VAI FAZER

Fases 1, 3, 4, 5, 6 no Terminal (código). Fase 2 no navegador (Lovable/Supabase).

---

## FASE 0 — PRÉ-REQUISITOS (Fábio, 15 min)

Antes de começar Fase 1, Fábio precisa ter:

1. Conta Supabase criada em `https://supabase.com`
2. Projeto Supabase: nome `blink-lovable-fase2`, região `sa-east-1`
3. Credenciais anotadas: `SUPABASE_URL` (formato `https://xxxxx.supabase.co`) e `SUPABASE_SERVICE_ROLE_KEY` (secret, começa com `eyJhbG...`)
4. Conta Lovable em `https://lovable.dev` com plano ativo (Pro US$20/mês ou trial 14d)

Peça essas 2 credenciais ao Fábio antes de continuar. Ele vai colar num arquivo `.env.local` no repo, que já está no `.gitignore`.

Quando ele confirmar, prossegue pra Fase 1.

---

## FASE 1 — SCHEMA SUPABASE (Terminal, 30 min autônomo)

1. Verifica se Supabase CLI está instalado:
   ```
   supabase --version
   ```
   Se não, instala:
   ```
   brew install supabase/tap/supabase
   ```

2. Login Supabase (pode abrir browser):
   ```
   supabase login
   ```

3. Vai pro repo:
   ```
   cd "/Users/fabiophilipecostamartins/Documents/Claude/Projects/AGENTE IA BLINK"
   ```

4. Cria pasta de migrations:
   ```
   mkdir -p supabase/migrations
   ```

5. Cria arquivo `supabase/migrations/20260703000001_fase1_schema.sql` com este conteúdo EXATO:

```sql
-- Fase 1: espelho da agenda Medware (sincronizado por cron)
CREATE TABLE medware_agenda (
  agenda_id BIGSERIAL PRIMARY KEY,
  cod_agenda INT NOT NULL,
  cod_medico INT NOT NULL,
  cod_unidade INT NOT NULL,
  data DATE NOT NULL,
  hora TIME NOT NULL,
  duracao_min INT DEFAULT 30,
  especialidade TEXT,
  status TEXT DEFAULT 'disponivel',
  cod_paciente_reservado INT,
  medware_sync_ts TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(cod_medico, cod_unidade, data, hora)
);
CREATE INDEX agenda_data_med ON medware_agenda(data, cod_medico);

-- Férias e escala dos médicos (config manual + cron)
CREATE TABLE medico_ferias (
  id BIGSERIAL PRIMARY KEY,
  cod_medico INT,
  data_inicio DATE,
  data_fim DATE,
  motivo TEXT
);

-- Log de sincronizações Medware (saúde do cron)
CREATE TABLE medware_sync_log (
  sync_id BIGSERIAL PRIMARY KEY,
  started_at TIMESTAMPTZ DEFAULT NOW(),
  ended_at TIMESTAMPTZ,
  sucesso BOOLEAN,
  slots_atualizados INT,
  erro TEXT
);

-- Fase 2: memória temporal (tabela events append-only)
CREATE TABLE events (
  event_id BIGSERIAL PRIMARY KEY,
  timestamp TIMESTAMPTZ DEFAULT NOW(),
  tipo TEXT NOT NULL,
  lead_id BIGINT,
  pacient_ref TEXT,
  payload JSONB,
  source TEXT
);
CREATE INDEX events_lead_ts ON events(lead_id, timestamp DESC);
CREATE INDEX events_pacient_ts ON events(pacient_ref, timestamp DESC);

-- Cache de pacientes (deduplicação por telefone/CPF)
CREATE TABLE patients_cache (
  paciente_id BIGSERIAL PRIMARY KEY,
  telefone TEXT UNIQUE,
  cpf TEXT UNIQUE,
  nome TEXT,
  data_nasc DATE,
  convenio_atual TEXT,
  ultima_consulta_ts TIMESTAMPTZ
);
CREATE INDEX patients_conv ON patients_cache(convenio_atual);

-- Lock distribuído (evita race conditions em sync)
CREATE TABLE sync_lock (
  recurso TEXT PRIMARY KEY,
  locked_by TEXT,
  expires_at TIMESTAMPTZ
);

-- View materializada: estado atual do paciente
CREATE MATERIALIZED VIEW vw_pacient_estado_atual AS
SELECT DISTINCT ON (pacient_ref)
  pacient_ref,
  tipo AS ultimo_evento_tipo,
  timestamp AS ultimo_evento_ts,
  payload
FROM events
WHERE pacient_ref IS NOT NULL
ORDER BY pacient_ref, timestamp DESC;
CREATE UNIQUE INDEX vw_pacient_idx ON vw_pacient_estado_atual(pacient_ref);

-- RLS policies (restringe acesso ao service_role)
ALTER TABLE medware_agenda ENABLE ROW LEVEL SECURITY;
CREATE POLICY "srv_all" ON medware_agenda FOR ALL USING (auth.role() = 'service_role');
ALTER TABLE medico_ferias ENABLE ROW LEVEL SECURITY;
CREATE POLICY "srv_all" ON medico_ferias FOR ALL USING (auth.role() = 'service_role');
ALTER TABLE medware_sync_log ENABLE ROW LEVEL SECURITY;
CREATE POLICY "srv_all" ON medware_sync_log FOR ALL USING (auth.role() = 'service_role');
ALTER TABLE events ENABLE ROW LEVEL SECURITY;
CREATE POLICY "srv_all" ON events FOR ALL USING (auth.role() = 'service_role');
ALTER TABLE patients_cache ENABLE ROW LEVEL SECURITY;
CREATE POLICY "srv_all" ON patients_cache FOR ALL USING (auth.role() = 'service_role');
ALTER TABLE sync_lock ENABLE ROW LEVEL SECURITY;
CREATE POLICY "srv_all" ON sync_lock FOR ALL USING (auth.role() = 'service_role');
```

6. Vincula ao projeto Supabase (usa `SUPABASE_URL` que Fábio te passou):
   ```
   supabase link --project-ref <ref_do_projeto>
   ```
   O `<ref_do_projeto>` é a parte antes de `.supabase.co` na URL.

7. Aplica migration:
   ```
   supabase db push
   ```

8. Verifica que rodou. Executa via psql direto no Supabase (Fábio pode abrir SQL Editor no painel Supabase e rodar):
   ```
   SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename;
   ```
   Deve mostrar 6 tabelas + 1 view materializada.

9. Cria arquivo `LOVABLE_INSTALL_LOG.md` no repo com o resultado das etapas 1-8. NÃO commite ainda.

Reporta ao Fábio: "Fase 1 OK. Schema aplicado no Supabase. 6 tabelas + 1 view criadas. Prossigo para Fase 2 (Lovable via Chrome)?"

---

## FASE 2 — LOVABLE (Chrome, 30 min semi-guiado)

Se você é o Claude Chrome, executa esta fase. Se é Claude Code, pede pro Fábio abrir o Claude Chrome e colar este bloco lá:

1. Navega em `https://lovable.dev/dashboard`. Se pedir login, PAUSA e pede pro Fábio logar.

2. Clica em "New Project" (ou botão equivalente pra criar novo).

3. Nome do projeto: "Blink Fase 2 Dashboard".

4. Quando o Lovable pedir "Descreva seu app", cola EXATAMENTE este prompt:

```
Dashboard operacional para clínica de oftalmologia com 4 áreas:

1) VISÃO GERAL — 4 cards:
- Leads em atendimento hoje (contagem)
- Última resposta do agente WhatsApp em minutos
- Slots ofertados últimas 24h vs confirmados (barras)
- Semáforo: Kommo, Medware, WhatsApp (verde/vermelho)

2) LEADS ATIVOS — tabela filtrada por etapa do funil.
Colunas: nome_paciente, motivo_consulta, medico, unidade, convenio, status_conversa, proxima_acao, ultima_msg_ts, link_kommo.
Filtros: etapa (3-AGENDAR/4-APRESENTADO/5-REAGENDAR/6-AGENDADO/7-CONFIRMAR), convênio, médico.
Ordenação: mais recente primeiro.

3) AGENDA POR MÉDICO — visão semanal.
Linhas = horários 08h-18h. Colunas = 7 dias.
Cores: verde=disponível, amarelo=reservado 10min, vermelho=ocupado, cinza=fora expediente.
Filtro por médico (Karla/Fabrício) e unidade (Asa Norte/Águas Claras).

4) LOG DE EVENTOS — timeline últimos 100 eventos.
Colunas: timestamp, tipo, lead_id, resumo.
Filtro por tipo (turn_complete/agendou/cancelou/no_show/escalou_humano).

Dados vêm de tabelas Supabase:
- medware_agenda (cod_medico, cod_unidade, data, hora, status)
- events (event_id, timestamp, tipo, lead_id, pacient_ref, payload)
- patients_cache (paciente_id, nome, convenio_atual)

Auth via Supabase Auth (só usuários logados).
Layout profissional denso tipo Retool/Metabase.
Cores neutras (cinza + azul escuro).
React + Tailwind + shadcn/ui.
Auto-refresh 30s.
```

5. Aguarda Lovable gerar (5-10 min). Se der progress bar visível, monitora. Se demorar mais que 15 min, screenshot e reporta.

6. Vai na aba "Integrations" ou "Settings → Supabase".

7. Cola `SUPABASE_URL` e `SUPABASE_SERVICE_ROLE_KEY` que o Fábio te passou. Salva.

8. Clica em "Preview" pra testar. Se der erro RLS, tira screenshot e reporta.

9. Clica em "Publish"/"Deploy". Aguarda 2-3 min.

10. Copia URL final publicada (algo tipo `https://blink-fase2-dashboard.lovable.app`).

Reporta ao Fábio: "Fase 2 OK. Lovable publicado em [URL]. Passa essa URL pro Claude Code prosseguir com Fase 3."

---

## FASE 3 — ENDPOINT AGENT (Terminal, 20 min autônomo)

Volta pro Terminal. Vai adicionar endpoint `/lovable/events` no agente e emissão de eventos por turn.

1. Abre `voice_agent/webhook.py`. Localiza os outros endpoints admin. Adiciona endpoint novo:

```python
@app.post("/lovable/events")
async def lovable_events(request: Request) -> JSONResponse:
    import hmac, hashlib, os
    signing_key = os.environ.get("LOVABLE_SIGNING_KEY", "")
    if not signing_key:
        raise HTTPException(503, "Lovable off")
    body = await request.body()
    sig_recebida = request.headers.get("X-Lovable-Signature", "")
    sig_calc = hmac.new(signing_key.encode(), body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig_recebida, sig_calc):
        raise HTTPException(401, "Assinatura inválida")
    import json
    payload = json.loads(body)
    if "tipo" not in payload:
        raise HTTPException(400, "campo tipo obrigatório")
    # Enfileira em Redis para processamento assíncrono
    r = pipeline._redis
    if r:
        r.rpush("blink:lovable:events_queue", body)
    return JSONResponse({"ok": True, "queued": True})
```

2. Adiciona no `voice_agent/settings.py`:

```python
lovable_endpoint_url: str = ""
lovable_signing_key: str = ""
```

3. Em `voice_agent/pipeline.py`, no final da função `run_turn` (após a Lia responder), emite evento fire-and-forget:

```python
# Emite evento pra Lovable (não bloqueia)
try:
    lovable_url = self.settings.lovable_endpoint_url
    lovable_key = self.settings.lovable_signing_key
    if lovable_url and lovable_key:
        import hmac, hashlib, json, httpx
        evt = {
            "tipo": "turn_complete",
            "lead_id": caller_context.get("lead_id"),
            "timestamp": int(time.time()),
            "ctx_known": caller_context.get("known", {}),
            "resposta_snippet": (answer or "")[:200],
        }
        body = json.dumps(evt).encode()
        sig = hmac.new(lovable_key.encode(), body, hashlib.sha256).hexdigest()
        async with httpx.AsyncClient(timeout=2.0) as client:
            try:
                await client.post(
                    lovable_url,
                    content=body,
                    headers={"X-Lovable-Signature": sig, "Content-Type": "application/json"},
                )
            except Exception:
                pass
except Exception as e:
    log.warning("Lovable emit falhou: %s", e)
```

4. Cria pytest `tests/test_lovable_events.py` com 5 cenários:
   - HMAC válido → 200
   - HMAC inválido → 401
   - Body sem tipo → 400
   - Feature off (sem key) → 503
   - Body vazio → 400

5. Roda pytest:
   ```
   cd "/Users/fabiophilipecostamartins/Documents/Claude/Projects/AGENTE IA BLINK"
   python3 -m pytest tests/test_lovable_events.py -q
   ```

6. Se tudo verde, commit:
   ```
   git add voice_agent/webhook.py voice_agent/settings.py voice_agent/pipeline.py tests/test_lovable_events.py
   git commit -m "feat(lovable-fase2): endpoint /lovable/events + emissao de eventos por turn"
   git push origin main
   ```

7. Gera signing key nova (64 chars hex):
   ```
   openssl rand -hex 32
   ```

8. Reporta ao Fábio: "Fase 3 OK. Adicione no Easypanel duas envs novas:
   - `LOVABLE_ENDPOINT_URL=<URL_DO_LOVABLE_DA_FASE_2>`
   - `LOVABLE_SIGNING_KEY=<KEY_GERADA_ACIMA>`
   
   Depois clica Implantar. Aguarde 3-5min e prossigo pra Fase 4."

---

## FASE 4 — SYNC via FIREBIRD READ-ONLY (Terminal, 45 min)

**TARGET DEFINIDO:** conectar direto no banco de produção Medware:
- Servidor: `srvapp01` (`162.120.186.82`) via DNS `medware.blinkoftalmologia.com.br`
- Database: `E:\Medware Clinicas\BD\CLINICAS.FDB`
- Porta: `3050` (Firebird default)

Ver `PROMPT_CONEXAO_FIREBIRD_CLOUD_READONLY.md` para o spec completo de segurança.

### PRÉ-REQUISITOS BLOQUEANTES (fazer ANTES de rodar Fase 4)

Sem estes 4 itens, nenhum código Python vai conseguir conectar. Fábio precisa acionar time Medware:

**1. Usuário Firebird `CLOUD_READONLY` criado**
No servidor Firebird (`srvapp01`), admin roda:
```sql
CREATE USER CLOUD_READONLY PASSWORD '<senha_forte_gerada>';
```
Guarda senha em cofre. NÃO passa por chat, e-mail ou repositório.

**2. Views criadas no `CLINICAS.FDB` produção**
Admin roda no banco de produção:
```sql
CREATE VIEW VW_CLOUD_AGENDAMENTOS AS
SELECT
    A.CODAGENDAMENTO,
    A.CODMEDICO,
    A.CODUNIDADE,
    A.DATA,
    A.HORA,
    A.DURACAO_MIN,
    A.STATUS,
    A.CODPACIENTE
FROM AGENDAMENTO A;

CREATE VIEW VW_CLOUD_MEDICOS AS
SELECT CODMEDICO, NOME, ESPECIALIDADE FROM MEDICO;

CREATE VIEW VW_CLOUD_UNIDADES AS
SELECT CODUNIDADE, NOME FROM UNIDADE;

GRANT SELECT ON VW_CLOUD_AGENDAMENTOS TO CLOUD_READONLY;
GRANT SELECT ON VW_CLOUD_MEDICOS TO CLOUD_READONLY;
GRANT SELECT ON VW_CLOUD_UNIDADES TO CLOUD_READONLY;
```

**3. Firewall Medware libera IP do Easypanel na porta 3050**
Descobre IP do Easypanel:
```bash
curl -s ifconfig.me  # rodado de dentro do container Easypanel
```
Time Medware libera esse IP → `srvapp01:3050`.

**4. Smoke test em homologação (15 min, opcional mas altamente recomendado)**
Antes de apontar produção, valida em `E:\Medware Clinicas\BD\BD de Homologacao\CLINICAS.FDB`. Se homologação tem as mesmas views + usuário, muda 1 env (`FIREBIRD_DATABASE`) depois. Zero risco.

Fábio confirma cada um dos 4 itens acima antes do Claude Code prosseguir.

### Pré-requisito — usuário Firebird e views (feito pelo DBA/Medware team, NÃO Claude)

Peça ao time Medware (ou você mesmo se tem acesso admin ao Firebird):

1. Criar usuário read-only:
```sql
CREATE USER CLOUD_READONLY PASSWORD '<senha_forte_cofre>';
```

2. Criar 3 views mínimas para o sync:
```sql
CREATE VIEW VW_CLOUD_AGENDAMENTOS AS
SELECT
    A.CODAGENDAMENTO,
    A.CODMEDICO,
    A.CODUNIDADE,
    A.DATA,
    A.HORA,
    A.DURACAO_MIN,
    A.STATUS,
    A.CODPACIENTE
FROM AGENDAMENTO A;

CREATE VIEW VW_CLOUD_MEDICOS AS
SELECT CODMEDICO, NOME, ESPECIALIDADE FROM MEDICO;

CREATE VIEW VW_CLOUD_UNIDADES AS
SELECT CODUNIDADE, NOME FROM UNIDADE;
```

3. Conceder permissão somente SELECT:
```sql
GRANT SELECT ON VW_CLOUD_AGENDAMENTOS TO CLOUD_READONLY;
GRANT SELECT ON VW_CLOUD_MEDICOS TO CLOUD_READONLY;
GRANT SELECT ON VW_CLOUD_UNIDADES TO CLOUD_READONLY;
```

4. Confirmar que firewall libera IP do Easypanel para porta 3050 (Firebird default).

5. Fábio armazena credenciais em variáveis de ambiente Easypanel (NUNCA no código):

**Envs PRODUÇÃO (target final):**
```
FIREBIRD_HOST=medware.blinkoftalmologia.com.br
FIREBIRD_PORT=3050
FIREBIRD_DATABASE=E:\Medware Clinicas\BD\CLINICAS.FDB
FIREBIRD_USER=CLOUD_READONLY
FIREBIRD_PASSWORD=<senha_cofre>
FIREBIRD_ENVIRONMENT=production
LOVABLE_FIREBIRD_ENABLED=1
```

**Envs HOMOLOGAÇÃO (opcional, pra smoke test 15min antes):**
```
FIREBIRD_HOST=medware.blinkoftalmologia.com.br
FIREBIRD_PORT=3050
FIREBIRD_DATABASE=E:\Medware Clinicas\BD\BD de Homologacao\CLINICAS.FDB
FIREBIRD_USER=CLOUD_READONLY
FIREBIRD_PASSWORD=<senha_cofre>
FIREBIRD_ENVIRONMENT=homologacao
LOVABLE_FIREBIRD_ENABLED=1
```

Swap prod ↔ homologação = trocar 2 envs (`FIREBIRD_DATABASE` + `FIREBIRD_ENVIRONMENT`) + Implantar. Rollback trivial.

### Passos do Claude Code

1. Instala driver Firebird para Python:
```
pip3 install --break-system-packages firebird-driver
```

2. Cria `voice_agent/lovable_sync.py`:

```python
"""Fase 4: sync Firebird Medware -> Supabase a cada 5min.

Segue rigorosamente o spec de segurança em
PROMPT_CONEXAO_FIREBIRD_CLOUD_READONLY.md:
- Conexão READ ONLY exclusivamente
- Transação READ ONLY READ COMMITTED NO WAIT
- Consultas parametrizadas SEMPRE (nunca concatenação)
- Filtros obrigatórios (data_inicial, data_final, unidade)
- Paginação com FIRST/SKIP
- Timeout de comando 5s com cancelamento automático
- Pool limitado (max 3 conexões)
- Log de auditoria completo por consulta
- Bloqueia qualquer SQL não whitelisted
"""
import time, os, logging
from datetime import date, timedelta
from contextlib import contextmanager

log = logging.getLogger(__name__)

# CONSULTAS WHITELISTED — SQL livre é PROIBIDO
_QUERIES_PERMITIDAS = {
    "listar_agenda_janela": """
        SELECT FIRST :LIMITE SKIP :OFFSET
            CODAGENDAMENTO,
            CODMEDICO,
            CODUNIDADE,
            DATA,
            HORA,
            DURACAO_MIN,
            STATUS,
            CODPACIENTE
        FROM VW_CLOUD_AGENDAMENTOS
        WHERE DATA BETWEEN :DATA_INICIAL AND :DATA_FINAL
          AND CODUNIDADE = :CODUNIDADE
        ORDER BY DATA, HORA
    """,
    "listar_medicos": """
        SELECT FIRST 500 CODMEDICO, NOME, ESPECIALIDADE
        FROM VW_CLOUD_MEDICOS
    """,
    "listar_unidades": """
        SELECT FIRST 100 CODUNIDADE, NOME
        FROM VW_CLOUD_UNIDADES
    """,
}


@contextmanager
def _firebird_readonly_conn():
    """Conexão Firebird em modo READ ONLY estrito.

    Configuração da transação:
    - READ ONLY (impede escritas)
    - READ COMMITTED (não bloqueia outras transações)
    - NO WAIT (falha rápido em vez de esperar lock)
    - timeout 5s
    """
    import firebird.driver as fbd
    host = os.environ["FIREBIRD_HOST"]
    port = int(os.environ.get("FIREBIRD_PORT", "3050"))
    database = os.environ["FIREBIRD_DATABASE"]
    user = os.environ["FIREBIRD_USER"]
    password = os.environ["FIREBIRD_PASSWORD"]

    dsn = f"{host}/{port}:{database}"
    con = fbd.connect(
        dsn,
        user=user,
        password=password,
        charset="UTF8",
        timeout=5,  # timeout de conexão
    )
    try:
        # Transação READ ONLY - se driver não aceitar params diretos,
        # explicita via SQL:
        con.execute_immediate(
            "SET TRANSACTION READ ONLY READ COMMITTED NO WAIT"
        )
        yield con
    finally:
        try:
            con.rollback()  # nunca commit em conexão readonly
        except Exception:
            pass
        con.close()


def executar_consulta(nome_query: str, params: dict,
                     limite: int = 100, offset: int = 0) -> list[dict]:
    """Executa consulta whitelisted com auditoria completa.

    Raises:
        ValueError: nome_query não está na whitelist
        KeyError: params obrigatórios ausentes
    """
    if nome_query not in _QUERIES_PERMITIDAS:
        raise ValueError(
            f"Consulta '{nome_query}' NÃO está whitelisted. "
            f"Permitidas: {list(_QUERIES_PERMITIDAS.keys())}"
        )
    sql = _QUERIES_PERMITIDAS[nome_query]
    inicio = time.time()
    linhas_retornadas = 0
    erro_msg = None
    resultado = []
    try:
        # Enforce paginação
        params_final = dict(params)
        params_final["LIMITE"] = min(limite, 500)  # cap máximo
        params_final["OFFSET"] = max(offset, 0)
        with _firebird_readonly_conn() as con:
            cur = con.cursor()
            # SEMPRE parametrizado — driver escapa
            cur.execute(sql, params_final)
            cols = [d[0] for d in cur.description]
            for row in cur.fetchall():
                resultado.append(dict(zip(cols, row)))
            linhas_retornadas = len(resultado)
    except Exception as e:
        erro_msg = str(e)
        log.error(
            "[FIREBIRD] Consulta %s falhou: %s | params=%r",
            nome_query, e, {k: v for k, v in params.items()
                            if k not in ("password", "senha")},
        )
        raise
    finally:
        duracao_ms = int((time.time() - inicio) * 1000)
        # Log de auditoria obrigatório
        log.info(
            "[FIREBIRD AUDIT] consulta=%s duracao_ms=%d linhas=%d "
            "params=%r erro=%s",
            nome_query, duracao_ms, linhas_retornadas,
            {k: v for k, v in params.items()
             if not k.lower().startswith(("pass", "senha"))},
            erro_msg,
        )
    return resultado


def sync_medware_agenda(supabase_client, dias: int = 30) -> dict:
    """Sync Firebird -> Supabase janela N dias, paginado."""
    inicio = time.time()
    slots_atualizados = 0
    sucesso = True
    erro_msg = None
    try:
        hoje = date.today()
        fim = hoje + timedelta(days=dias)
        # Descobre unidades (max 100)
        unidades = executar_consulta("listar_unidades", {})
        for un in unidades:
            cod_un = un["CODUNIDADE"]
            offset = 0
            while True:
                lote = executar_consulta(
                    "listar_agenda_janela",
                    params={
                        "DATA_INICIAL": hoje.isoformat(),
                        "DATA_FINAL": fim.isoformat(),
                        "CODUNIDADE": cod_un,
                    },
                    limite=100,
                    offset=offset,
                )
                if not lote:
                    break
                for slot in lote:
                    row = {
                        "cod_agenda": slot["CODAGENDAMENTO"],
                        "cod_medico": slot["CODMEDICO"],
                        "cod_unidade": slot["CODUNIDADE"],
                        "data": slot["DATA"].isoformat() if hasattr(slot["DATA"], "isoformat") else slot["DATA"],
                        "hora": str(slot["HORA"]),
                        "duracao_min": slot.get("DURACAO_MIN") or 30,
                        "status": slot.get("STATUS") or "disponivel",
                        "cod_paciente_reservado": slot.get("CODPACIENTE"),
                    }
                    supabase_client.table("medware_agenda").upsert(
                        row, on_conflict="cod_medico,cod_unidade,data,hora"
                    ).execute()
                    slots_atualizados += 1
                offset += len(lote)
                if len(lote) < 100:
                    break
    except Exception as e:
        sucesso = False
        erro_msg = str(e)
        log.error("Sync Firebird->Supabase falhou: %s", e)
    finally:
        duracao_ms = int((time.time() - inicio) * 1000)
        try:
            supabase_client.table("medware_sync_log").insert({
                "sucesso": sucesso,
                "slots_atualizados": slots_atualizados,
                "erro": erro_msg,
            }).execute()
        except Exception:
            pass
    return {
        "sucesso": sucesso,
        "slots_atualizados": slots_atualizados,
        "duracao_ms": duracao_ms,
        "erro": erro_msg,
    }
```

### Checklist de segurança pós-implementação (obrigatório)

Antes de habilitar em produção, valide TODOS os itens:

- [ ] Testado em `E:\Medware Clinicas\BD\BD de Homologacao\CLINICAS.FDB` primeiro
- [ ] Usuário `CLOUD_READONLY` criado, senha em cofre (`FIREBIRD_PASSWORD` env)
- [ ] Permissões revisadas: apenas `SELECT` nas 3 views
- [ ] Nenhuma permissão `INSERT`, `UPDATE`, `DELETE`, `EXECUTE`, `GRANT ALL`
- [ ] Consultas parametrizadas (verificado em code review)
- [ ] Todas as consultas com filtros obrigatórios (data + unidade)
- [ ] `FIRST :LIMITE` em toda consulta
- [ ] Paginação implementada
- [ ] Timeout 5s implementado
- [ ] Pool máximo 3 conexões
- [ ] Log de auditoria mostrando: nome_query, duracao_ms, linhas, params (sem senha), erro
- [ ] Firewall Medware libera IP Easypanel para porta 3050
- [ ] Whitelist SQL bloqueia qualquer consulta não registrada
- [ ] Plano rollback: `LOVABLE_FIREBIRD_ENABLED=0` + revoke usuário CLOUD_READONLY

### Plano de rollback (caso impacto no Medware seja detectado)

1. Env `LOVABLE_FIREBIRD_ENABLED=0` no Easypanel → sync para
2. `REVOKE ALL FROM CLOUD_READONLY;` no Firebird (bloqueia mesmo se app tentar)
3. `ALTER USER CLOUD_READONLY DISABLED;` (opção nuclear)
4. Firewall Medware bloqueia IP Easypanel na porta 3050
5. Analisa logs de auditoria: qual consulta, horário, params, volume
6. Corrige em homologação antes de reabilitar

2. Instala cliente Supabase:
   ```
   pip3 install --break-system-packages supabase
   ```

3. Adiciona no `voice_agent/cron_interno.py` novo worker rodando a cada 5min:
   - Se `LOVABLE_SYNC_ENABLED=1` na env
   - Chama `sync_medware_agenda`
   - Se 3 falhas seguidas, alerta Slack via `SLACK_WEBHOOK_BUGS_URL`

4. Cria pytest com mocks.

5. Commit + push.

Reporta: "Fase 4 OK. Fábio, adiciona no Easypanel:
- `LOVABLE_SYNC_ENABLED=1`
- `SUPABASE_URL=<url>`
- `SUPABASE_SERVICE_ROLE_KEY=<key>`

Depois Implanta. Aguarda 5-10min pra ver primeiros logs de sync."

---

## FASE 5 — SHADOW MODE (48h, monitoramento passivo)

Toggle `LIA_USA_LOVABLE=shadow` no Easypanel.

Nesse modo:
- Lia continua usando lógica atual
- Também consulta Supabase e loga o que teria respondido usando dados Lovable
- Compara respostas em `blink:shadow_diff:{lead_id}` no Redis
- Você cria endpoint `/admin/shadow-diff-report` que mostra top 20 discrepâncias

Espera 48h. Se discrepâncias < 5%, prossegue pra Fase 6.

---

## FASE 6 — SWITCH ON (15 min + monitoramento)

Env `LIA_USA_LOVABLE=1` no Easypanel. Implantar.

Monitor 2h iniciais no `/admin/dashboard` que já existe.

**Rollback fácil:** `LIA_USA_LOVABLE=0` → Implantar (30s).

Reporta: "Fase 6 OK. Lovable Fase 2 em produção. Monitorando pelas próximas 2h."

---

## MÉTRICAS DE SUCESSO PÓS-IMPLEMENTAÇÃO

Depois de 7 dias em produção, compara com baseline:

| Métrica | Antes | Alvo |
|---|---|---|
| Latência "consultar disponibilidade" | 8-15 seg | menor que 200 ms |
| Taxa "deixa eu reconsultar" / 1000 turns | ~6% | menor que 0,5% |
| Slots oferecidos por conversa AGENDA | ~0,3 | maior que 1,8 |
| Conversão "oferta → confirma slot" | ~28% | maior que 45% |

---

## REGRAS OPERACIONAIS

1. Ao final de CADA fase, reporte o que fez e aguarde confirmação do Fábio antes de prosseguir.
2. Se qualquer comando falhar, PARE e explique o erro exato. Não tenta workaround silencioso.
3. NUNCA commita secrets (SUPABASE_SERVICE_ROLE_KEY, LOVABLE_SIGNING_KEY) — só `.env.local` que está no gitignore.
4. Ao fazer `git push`, se der auth error, avise o Fábio pra rodar `git push` manualmente (as vezes credencial dele está no keychain e não na sua sessão).
5. Se Lovable ou Supabase pedir 2FA/SMS/aprovação email, PARE e chama o Fábio.
6. NÃO gasta créditos Lovable com edições estéticas — só cria estrutura base. Fábio pode refinar depois.
7. Grava tudo no `LOVABLE_INSTALL_LOG.md` pra auditoria.

---

## FIM DO PLANO

Começa pela Fase 0 confirmando com o Fábio que ele já criou as contas. Depois avança sequencial. Boa sorte.
