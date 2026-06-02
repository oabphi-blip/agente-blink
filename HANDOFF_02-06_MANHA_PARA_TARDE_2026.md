# Handoff — 02/06/2026 manhã → tarde

## TL;DR

Sessão prática da manhã expôs limite real do trabalho noturno: implementei
muita defesa sem validação com dado real. Juiz Haiku 4.5 vetou em série
respostas legítimas (Larissa/Lis/Samuel + Adriana). Causa: pytest passou,
mas LIMIAR=70 deu falso positivo em casos borderline normais.

**Estado atual prod (12h BRT):**
- `JUIZ_HAIKU_ENABLED=0` e `MEMORIA_BUGS_ENABLED=0` desligados via Easypanel
- Lia voltou a responder normalmente (lead Adriana 24063769 fechou em
  R$ 611 às 11:21 com formato direto)
- Larissa 10513560 sendo atendida por humano (paciente da clínica
  reportou bug Blink)
- 3 commits locais aguardam token GitHub novo do Fábio pra subir

## Princípio nascido nessa sessão — "shadow mode"

Antes de qualquer camada nova substituir resposta da Lia, ela roda em
modo silencioso por 24h+: só LOGA o que substituiria. Métrica de
aprovação: < 2% dos turnos teriam sido substituídos. Só depois disso,
revisão dos textos e aprovação explícita do Fábio liberam o ENABLED=1.

Registrado em CLAUDE.md seção 11-E.

## 3 commits aguardando push

| Commit | Significado |
|---|---|
| `96cb3a3` | Camada 5 (histórico conversa) + canary #15 Graziela/Enzo |
| `76da4b7` | Fallback Larissa: troca "se preferir me diga sua dúvida" por "vou reconsultar agenda" |
| `24e12ad` | Filtro Adriana (`_viola_pergunta_redundante_convenio`) + KB 39 valores oficiais + `.github/workflows/test.yml` (CI) |

**Por que não estão em prod:** push falhou com `Invalid username or
token. Password authentication is not supported`. Token GitHub salvo
no Keychain do Mac do Fábio está expirado/revogado.

**Próxima ação do Fábio:**

1. `github.com/settings/tokens` → Generate new token (classic) →
   `repo` scope → copiar `ghp_...`
2. Terminal: `printf "host=github.com\nprotocol=https\n\n" |
   git credential-osxkeychain erase && cd "$HOME/Documents/Claude/Projects/AGENTE IA BLINK" && git push origin main`
3. Username: `oabphi-blip` + senha = o token novo

Quando push subir, auto-deploy pega em 2-5min. Os 3 commits são
**corretivos**, sem camadas novas que ativem por default.

## Bugs reais resolvidos hoje (com correção em código)

### Bug Larissa/Lis/Samuel (10513560) — Juiz substituiu respostas legítimas

Conversa travou em "Anotei aqui! Em instantes confirmo os detalhes...
me diga sua dúvida específica que eu agilizo" — duas vezes seguidas.
Essa frase é o `FALLBACK_SUBSTITUICAO` do juiz Haiku.

Fix `76da4b7`: frase trocada para "Deixa eu reconsultar a agenda real
aqui pra você. Me responde 'oi' em 1 minuto que eu volto com 2 opções
concretas". Action-oriented em vez de "tira dúvida". Aplicada também
em `memoria_bugs.FALLBACK_SIMILAR_BUG`.

**Causa raiz:** juiz semântico LLM com LIMIAR=70 catalogou como "alto
risco" várias respostas normais de coleta de dados. Solução não foi
ajustar o juiz, foi **desligá-lo** até validação real. Aplica `shadow
mode` (seção 11-E).

### Bug Adriana (24063769) — Pergunta redundante de convênio

Paciente pediu valor. Lia fez 4 turnos pedindo "com ou sem convênio?",
"quem?", "convênio de novo?", "motivo?". Convênio JÁ estava no Kommo
("Não se aplica" = particular).

Fix `24e12ad`:
- Artigo KB `voice_agent/knowledge_base/39_valores_consulta.md` com
  tabela oficial: Karla R$ 611 (rotina/oftalmopediatria/estrabismo),
  Fabrício R$ 297 (catarata aval/pós-op), SDP R$ 800.
- Filtro `_viola_pergunta_redundante_convenio(text, ctx)` em
  `responder.py`: detecta "com ou sem convênio" + ctx tem convenio →
  substitui pela resposta direta baseada no ctx.
- `_gerar_resposta_valor_sem_repergunta(ctx)`: usa
  médico+especialidade+convênio do ctx pra montar resposta com R$
  certo. Convênio aceito → "coberta pelo plano". Particular → R$ + Pix.
- 13 testes em `tests/test_pergunta_redundante_convenio.py`.

Validação real: Adriana 11:21 respondeu com "R$ 611,00 via Pix ou 2x
R$ 335,00 sem juros" — formato exato do KB 39. Lia já entendeu o
template assim que o juiz parou de vetar.

### Bug estrutural — Regressão recorrente

Fábio: "passo a noite inteira informa que corrigiu quando começa o
dia para trabalhar acontece estes erros".

Fix `24e12ad` (`.github/workflows/test.yml`):
- GitHub Actions roda pytest + lint a cada push em main + PR.
- Status check do GitHub fica vermelho se algum cenário antigo quebrar.
- Easypanel respeita check (auto-deploy só dispara em verde).
- Memória ativa **preventiva**, não reativa.

Próxima vez: bug Aurora não pode voltar mesmo se eu acidentalmente
mexer no `_viola_oferta_apos_agendado`, porque o pytest E2E vai pegar.

## Estado consolidado do sistema (02/06 12h)

| Componente | Estado |
|---|---|
| Health prod | OK · Redis/Medware/Kommo/WA Cloud verdes |
| Pytest local | 937/937 verde (+14 hoje) |
| Filtros regex em `responder.py` | 13 ativos (juiz e memória bugs OFF) |
| `ja_agendado` camadas 1-5 | Ativas (status, 1.DIA CONSULTA, nota humana, template Blink, histórico) |
| Smoke contínuo cron 1h | ON |
| Watchdog Lia muda cron 5min | ON |
| Detector leads-fantasma cron 5min | ON |
| Canary lead diário 7h BRT | ON (CANARY_PHONE 5561996830710) |
| Auto-deploy GitHub→Easypanel | ON |
| GitHub Actions CI | **vai ativar quando push subir** |

## Próximas ações da tarde

1. **Fábio destrava token GitHub** e dá push dos 3 commits
2. Auto-deploy puxa, CI GitHub Actions roda pela 1ª vez
3. Eu valido `/health` + `/admin/smoke-tick` + GitHub Actions verde
4. Sistema entra na rotina nova: cada push novo passa por pytest no CI
   antes de auto-deploy do Easypanel

## Lições

1. Pytest unitário não substitui validação com dado real (precisa do
   shadow mode).
2. LLM julgando LLM (juiz Haiku) tem falso positivo em casos borderline.
   Não bota em prod sem ver 100+ turnos reais.
3. CI/CD foi o que faltava pra fechar o loop. Sem ele, pytest só
   protege se você lembrar de rodar.
4. Quando paciente reclama do bug, a Lia geralmente já passou por 3-4
   filtros de defesa. Adicionar mais camada não resolve — refinar o
   que tem e medir é melhor.

— Sessão 02/06/2026 manhã encerrada às ~12h BRT com sistema operando
em modo "defesa mínima viável" (13 regex + retry Medware + circuit
breaker + state machine + checklist).
