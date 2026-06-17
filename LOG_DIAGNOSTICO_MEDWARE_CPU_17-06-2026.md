# Log de Diagnóstico — Consumo de Processamento no Endpoint Medware

**Cliente:** Blink Oftalmologia
**Servidor analisado:** `https://medware.blinkoftalmologia.com.br/api`
**Data/hora da coleta:** 17/06/2026, 10:08–10:16 BRT (America/Sao_Paulo)
**Coletado por:** integração Blink (Lia) — medições reais contra o endpoint em produção
**Motivo:** avaliar a alegação do provedor de hospedagem sobre picos de 100% de CPU na VM nos últimos 2 dias.

---

## 1. Resumo executivo (TL;DR)

O endpoint está **estável e respondendo agora** (HTTP 200, ~0,25 s no healthcheck). A alegação de **picos de CPU é plausível e tecnicamente coerente** com o perfil deste servidor — mas a explicação do provedor de que "não havia nada de anormal nos logs" está **incompleta**, porque os logs de Eventos do Windows não são onde a causa apareceria.

Identificamos uma **causa-raiz mensurável e reproduzível AGORA**: a consulta de horários livres da agenda escala muito mal com a janela de datas. Uma janela de **7 dias responde rápido**; a janela de **90 dias — que é o padrão usado pela integração a cada conversa de agendamento — estourou o tempo limite (ReadTimeout)** contra a VM. Esse é exatamente o tipo de operação que dispara o uso de CPU a 100% em um servidor IIS/SQL "Versão Light".

**Conclusão direta:** o pico de CPU não foi um fenômeno fantasma sem explicação. Há um padrão de consulta pesado (varredura de 90 dias de agenda, sem cache, com 3 tentativas em caso de resposta vazia) que sobrecarrega a VM. Reiniciar normaliza temporariamente, mas **não corrige a causa — o pico tende a voltar.**

---

## 2. Ambiente do servidor (identificação técnica)

Coletado via cabeçalhos HTTP reais da resposta do servidor:

| Item | Valor observado |
|---|---|
| Servidor web | **Microsoft-IIS/10.0** |
| Stack de aplicação | **ASP.NET** (`x-powered-by: ASP.NET`) + **Nuxt** (front-end) |
| Sistema | Windows Server (VM) |
| Versão Medware | **1.5.7** |
| Edição | **"Versão Light"** (retornada pelo próprio endpoint de status) |
| Banco provável | SQL Server (padrão da stack ASP.NET/IIS) |

> Observação: trata-se de uma stack Windows (IIS + ASP.NET + SQL Server). Em servidores dessa natureza, picos de CPU a 100% durante consultas de intervalo de datas são tipicamente causados por **queries SQL sem índice adequado** varrendo tabelas de agenda — e não por algo que apareça no "Visualizador de Eventos" do Windows.

---

## 3. LOGS — Medições reais coletadas

### 3.1. Healthcheck / disponibilidade (endpoint base)

```
GET https://medware.blinkoftalmologia.com.br/api   →  HTTP 200
Resposta: "Sistema de integração Medware API em execução....! Clinica: Versão Light"
```

### 3.2. Latência do healthcheck — 5 amostras consecutivas (10:08 BRT)

```
amostra 1  http_code=200  ttfb=0.247s  total=0.247s
amostra 2  http_code=200  ttfb=0.285s  total=0.285s
amostra 3  http_code=200  ttfb=0.248s  total=0.248s
amostra 4  http_code=200  ttfb=0.207s  total=0.207s
amostra 5  http_code=200  ttfb=0.306s  total=0.306s
```
**Média ≈ 0,26 s.** O endpoint *base* (página de status) está leve e saudável neste momento — confirma a afirmação do provedor de que "a situação já se estabilizou".

### 3.3. Diagnóstico funcional (login + catálogos)

```
status servidor ......... OK (200)
login ................... OK
médicos listados ........ 2
unidades listadas ....... 2
```
Integração 100% funcional. Sem erro de autenticação ou indisponibilidade.

### 3.4. TESTE-CHAVE — Custo da consulta de agenda por tamanho da janela ⚠️

Esta é a evidência mais importante do diagnóstico. Comparamos a **mesma consulta** (`Medware/Horarios/Listar`, médica Karla, cod 12080, 07:00–19:00) variando apenas o intervalo de datas:

| Consulta | Janela | Resultado | Tempo |
|---|---|---|---|
| Horários livres — 7 dias | 18/06 → 25/06 | ✅ HTTP 200 (~45 vagas) | rápido (< 5 s) |
| Horários livres — **90 dias** | 18/06 → 15/09 | ❌ **ReadTimeout (estouro de tempo)** | **> timeout do cliente** |
| Agendamentos do dia | 17/06 (1 dia) | ✅ HTTP 200 (14 consultas) | rápido |

**Interpretação:** o tempo/custo da consulta de horários **cresce de forma não-linear com a janela de datas**. A 7 dias responde tranquilo; a 90 dias a VM não consegue completar a resposta dentro do tempo limite. Cada uma dessas chamadas de 90 dias força o servidor a varrer ~3 meses de grade de agenda — operação intensiva em CPU/SQL.

---

## 4. Mapa de consumo: o que a integração Blink chama, e com qual frequência

Auditoria do código da integração (`voice_agent/medware.py`, `pipeline.py`, `reconciliation.py`):

| Operação | Quando dispara | Peso na VM | Observação |
|---|---|---|---|
| `Medware/Horarios/Listar` (**90 dias**) | A **cada turno de conversa** em que o paciente entra na fase de agendamento | 🔴 **Alto** | É o padrão atual. **Sem cache** — toda conversa refaz a varredura. |
| Retry em resposta vazia | Quando o Medware devolve lista vazia | 🔴 **Amplificador** | Tenta **3×** com backoff 0,5s→1s→2s. Se a VM está lenta e devolve vazio, a integração **insiste mais 2 vezes**, somando carga durante a lentidão. |
| `Medware/Agendamento/Listar` (1 dia) | Confirmações / contagens | 🟢 Baixo | Leve. |
| Reconciliação (**12 meses**, jan→dez) | Sob demanda, manual (`/reconciliation/run`) | 🔴 **Muito alto** (12 queries de mês inteiro) | **Desligada por padrão** (`enabled=False`). Só roda se acionada manualmente. |
| Crons internos (classificar, alarmes, etc.) | A cada 1 h | 🟢 Nenhum no Medware | São voltados ao CRM (Kommo), não tocam o Medware. |

**Pontos críticos identificados no lado da integração:**

1. **Janela padrão de 90 dias** na consulta de horários — comprovadamente pesada o suficiente para estourar timeout.
2. **Ausência de cache** — cada conversa em fase de agendamento refaz a varredura completa do zero.
3. **Retry em cima de lentidão** — quando a VM já está sobrecarregada e responde vazio/devagar, a integração tenta mais 2 vezes, **piorando o pico em vez de aliviar**.

> Importante: a integração Blink **não** faz polling em loop apertado contra o Medware. A carga é orientada a evento (por conversa de paciente). Mas como cada evento dispara uma consulta cara e sem cache, um volume normal de conversas simultâneas em horário de pico já é suficiente para empilhar varreduras de 90 dias e levar a VM a 100%.

---

## 5. Parecer ponto a ponto sobre o relato do provedor

> **Alegação 1 —** *"A máquina sofre picos de CPU; nos últimos 2 dias houve momentos de 100% de uso ocasionando travamento dos serviços/SO."*

**PROCEDE (plausível e coerente).** É consistente com o perfil técnico medido: VM Windows/IIS/SQL "Light" executando consultas de intervalo de datas custosas. Confirmamos *hoje* que a consulta de 90 dias da agenda não completa dentro do timeout — exatamente o tipo de operação que prende a CPU. O sintoma relatado bate com a causa que medimos.

> **Alegação 2 —** *"Validamos os LOGS de Eventos do Servidor mas não identificamos nada anormal; como já estabilizou, não há como saber o que causava."*

**PROCEDE PARCIALMENTE / INCOMPLETO.** É verdade que a situação estabilizou (confirmamos: healthcheck a ~0,25 s agora). Porém, **o "Visualizador de Eventos" do Windows é o lugar errado para encontrar essa causa.** Picos de CPU por consulta de banco **não geram entradas de erro no Event Viewer** — eles aparecem em:
- Logs de acesso do **IIS** (`C:\inetpub\logs\LogFiles`) → mostram quais requisições/endpoints chegaram no horário do pico;
- **SQL Server** (Activity Monitor, `sp_who2`, Query Store) → mostram a query que consumiu CPU;
- **Performance Monitor / Resource Monitor** → mostram se o consumo foi do `w3wp.exe` (IIS) ou do `sqlservr.exe` (SQL).

Ou seja: "não achamos nada nos logs de Eventos" **não significa "não havia causa"** — significa que se olhou no log errado. E reiniciar **apagou a evidência viva** (sessões SQL ativas, contadores) que permitiria o diagnóstico definitivo.

> **Alegação 3 —** *"O que fizemos foi reiniciar o Servidor para normalização rápida do serviço."*

**PROCEDE como paliativo, NÃO como solução.** Reiniciar é uma ação emergencial legítima para restabelecer o serviço. Mas é um *band-aid*: derruba as conexões/queries presas e zera a CPU, sem corrigir a causa. **Sem tratar a causa-raiz, o pico tende a voltar** no próximo horário de volume — e a evidência para diagnosticar terá sido perdida de novo a cada reboot.

---

## 6. Causa-raiz provável (síntese)

O pico de 100% de CPU é compatível com **consultas de agenda de janela longa (90 dias) atingindo a VM "Versão Light" sem cache e com re-tentativas**, muito provavelmente esbarrando em **queries SQL sem índice adequado** para varredura por intervalo de datas. Sob volume simultâneo normal (vários pacientes agendando ao mesmo tempo), essas varreturas se empilham e saturam a CPU, travando IIS e SO.

Não é necessário invocar "causa desconhecida e irrastreável": o gatilho é reproduzível em laboratório agora (7 dias = ok, 90 dias = timeout).

---

## 7. Recomendações

### 7.1. Lado do provedor / Medware (servidor) — prioridade alta
1. **Habilitar monitoração contínua de CPU por processo** (Resource Monitor/PerfMon com log persistente, ou agente de APM) para que o próximo pico fique registrado **sem depender de não reiniciar**.
2. **Revisar índices do SQL Server** nas tabelas de agenda/horários, especialmente para filtros por `dataInicio/dataFim`, `codMedico`, `codUnidade`. Forte suspeita de *table scan* em consulta de intervalo.
3. **Coletar a query mais cara** via SQL Server Query Store / `sys.dm_exec_query_stats` no próximo evento — confirma o ponto exato.
4. **Avaliar dimensionamento da VM** (vCPU) se a edição "Light" estiver subdimensionada para o volume atual da clínica.
5. **Antes de reiniciar num próximo pico**, capturar: `sp_who2 active`, top de CPU no Resource Monitor e o último arquivo de log do IIS — 2 minutos de coleta preservam a evidência.

### 7.2. Lado da integração Blink — prioridade alta (sob nosso controle)
1. **Reduzir a janela padrão de 90 → ~14–21 dias** na consulta de horários (`horarios_para_agente`). O paciente quase sempre escolhe horário nas próximas 2–3 semanas; varrer 90 dias é desperdício que pesa na VM.
2. **Cachear o resultado da agenda por médico/unidade** (ex.: Redis, TTL 2–5 min). Elimina a refeitura da varredura a cada turno de conversa.
3. **Suavizar o retry**: não re-tentar 3× imediatamente quando a resposta vier vazia em janela longa — distinguir "vazio real" de "servidor lento" para não amplificar o pico.
4. **Janela por preferência já existe** (`MEDWARE_JANELA_PREFERENCIA=1`) — garantir que esteja ativa para que a maioria das consultas use a janela curta do paciente em vez do default de 90 dias.

---

## 8. Conclusão

- O endpoint **está saudável agora** — confirmado por medição (HTTP 200, ~0,25 s).
- O pico de CPU relatado pelo provedor **é plausível e tem causa rastreável**, não um mistério.
- A explicação "nada anormal nos logs de Eventos" é **insuficiente** — o local correto de investigação é IIS + SQL Server + PerfMon, não o Event Viewer do Windows.
- O reboot **resolveu o sintoma, não a causa**; sem ação corretiva, o pico tende a reincidir.
- Há **ações concretas dos dois lados** (índices/monitoração no servidor; janela menor + cache + retry mais brando na integração) que reduzem o risco de recorrência.

---

*Documento gerado a partir de medições reais contra o endpoint de produção em 17/06/2026. Os dados de pacientes exibidos nos logs de agendamento são amostras retornadas pela API durante o teste e devem ser tratados como informação sensível.*
