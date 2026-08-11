-- ============================================================
-- FONTE B DE AGENDA — cache de horários livres do Medware
-- Projeto Blink Oftalmologia · esboço 02/07/2026
-- ------------------------------------------------------------
-- Objetivo: quando o Medware AO VIVO cai (timeout/instabilidade),
-- a Lia lê os horários do último snapshot bom gravado aqui, em vez
-- de entrar no loop "deixa eu reconsultar... volto em 1 minuto".
-- Roda no Supabase (Postgres) do projeto Lovable.
-- ============================================================

create table if not exists public.slots_disponiveis (
    id            bigint generated always as identity primary key,
    cod_agenda    bigint  not null,              -- id do slot no Medware (grava agendamento)
    cod_medico    integer not null,              -- 12080 Karla · 12081 Fabrício
    medico_nome   text,
    cod_unidade   integer not null,              -- 3 Águas Claras · 5 Asa Norte
    unidade_nome  text,
    data          date    not null,              -- YYYY-MM-DD
    hora          time    not null,              -- HH:MM
    dia_semana    text    not null,              -- derivado da data (nunca digitado — anti Bug C-35)
    disponivel    boolean not null default true,
    capturado_em  timestamptz not null default now(),
    -- 1 linha por vaga física
    unique (cod_medico, cod_unidade, data, hora)
);

-- Leitura da Lia: filtra por médico+unidade, datas futuras, disponível.
create index if not exists idx_slots_lookup
    on public.slots_disponiveis (cod_medico, cod_unidade, data)
    where disponivel;

-- Guard de frescor: a Lia só confia no cache se o snapshot é recente.
create index if not exists idx_slots_capturado
    on public.slots_disponiveis (capturado_em);

-- ------------------------------------------------------------
-- RLS: só o service_role (edge function + backend da Lia) mexe.
-- ------------------------------------------------------------
alter table public.slots_disponiveis enable row level security;

drop policy if exists slots_service_all on public.slots_disponiveis;
create policy slots_service_all
    on public.slots_disponiveis
    for all
    to service_role
    using (true)
    with check (true);

-- ------------------------------------------------------------
-- Higiene: apaga vagas que já passaram (roda no fim de cada sync).
-- ------------------------------------------------------------
-- delete from public.slots_disponiveis where data < current_date;
