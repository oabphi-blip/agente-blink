# Fonte B de agenda — cache Supabase (esboço 02/07/2026)

Rede de segurança para o descompasso do lead **Carolina 21225483**: Medware ao
vivo caiu → Lia entrou em loop "volto em 1 minuto" 4x. O cache resolve os casos
em que **nenhum** slot foi pré-calculado no lead (onde o fallback Kommo já
tampou), porque mantém sempre o **último snapshot bom** da agenda inteira.

## Como as duas camadas se encaixam

```
Lia precisa da agenda
        │
        ▼
1. Medware AO VIVO  ──ok──▶  usa slots reais (comportamento normal)
        │ timeout/vazio
        ▼
2. Fallback Kommo   ──tem 1./2. DIA COM CONVÊNIO?──▶  oferta com esses slots
        │ (JÁ IMPLEMENTADO hoje em responder.py)          (caso Carolina)
        ▼
3. Cache Supabase   ──snapshot recente?──▶  oferta com o último bom da agenda
        │ (ESTE esboço)                        (casos sem slot no lead)
        ▼
4. Frase honesta + escala humana  (só se as 3 fontes falharem)
```

## Query que a Lia roda (camada 3)

```sql
-- Fonte B: últimos horários bons capturados, ainda no futuro.
select data, hora, dia_semana, cod_agenda, cod_medico, cod_unidade
from public.slots_disponiveis
where cod_medico = :cod_medico
  and cod_unidade = :cod_unidade
  and disponivel
  and data >= current_date
order by data, hora
limit 20;
```

**Guard de frescor** — só confiar no cache se o snapshot é recente
(senão, é melhor a frase honesta do que oferecer vaga que já sumiu):

```sql
select max(capturado_em) as ultimo_sync
from public.slots_disponiveis
where cod_medico = :cod_medico and cod_unidade = :cod_unidade;
-- Lia usa o cache só se now() - ultimo_sync < 60 min.
```

## Integração no backend da Lia (próximo passo, fora deste esboço)

Em `voice_agent/medware.py::horarios_para_agente`, quando as tentativas ao vivo
voltam vazias, consultar o Supabase (REST ou client PG) com a query acima e
devolver os slots no mesmo formato `{data_br, dia_semana, hora, cod_agenda}`.
Como o formato é idêntico ao do Medware, o resto do pipeline (C-30, oferta de 2
slots, tool calling) funciona sem mudança.

Um `MEDWARE_CACHE_ENABLED=1` controla o rollout; `disponivel=false` some da
oferta automaticamente.

## Passos no Lovable / Supabase

1. Criar projeto Lovable com Supabase habilitado (ou usar o Supabase existente).
2. Rodar `01_tabela_slots_disponiveis.sql` no SQL Editor.
3. Publicar `02_edge_function_sync_medware.ts` como Edge Function `sync-medware-slots`.
4. Cadastrar os secrets (MEDWARE_BASE_URL/USER/PASS + SUPABASE_URL/SERVICE_ROLE_KEY).
5. Agendar cron de 10 min (pg_cron ou scheduled function do Supabase).
6. Bônus — painel "gap de amanhã": `select data, count(*) ... group by data`
   mostra os dias com poucas vagas → campanha de ativação focada.

## Decisões do esboço

- **Chave sem `codPlano`.** A "versão light" do Medware devolve `[]` se receber
  `codPlano=0`, então os horários livres são plano-agnósticos; o plano é
  validado só na gravação. A tabela reflete isso.
- **`dia_semana` derivado da data** (nunca digitado) — imune ao Bug C-35.
- **Falha por par não apaga snapshot.** Se o Medware oscila só pra um
  médico/unidade, mantém-se o último bom em vez de zerar a agenda.
