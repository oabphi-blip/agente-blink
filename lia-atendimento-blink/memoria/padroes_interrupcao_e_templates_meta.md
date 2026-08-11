# Padrões de interrupção × Templates Meta — análise pra campanhas ativas

> Origem: Fábio 05/06/2026 — analisar razões de interrupção e mapear pra templates
> Meta aprovados, distribuindo por estágio (LEAD FRIO / AGENDAR / ONBOARDING).
> Base: leads renomeados (task #227) + bugs históricos + padrões observados.

---

## Padrões de interrupção identificados em 368 leads de 2.LEADS FRIO + histórico

| # | Padrão de interrupção | Evidência (nome lead / bug histórico) | Volume aprox | Template aprovado existente | Status |
|---|---|---|---|---|---|
| 1 | Paciente pediu valor consulta e não respondeu | "[C] sem resposta após valor particular" | ~30 leads | `10pp_dia_disponivel_*` (3 variantes) | ✅ aprovado |
| 2 | Paciente desmarcou e não voltou | "[R] Faltou consulta", "[R] Desmarcou" | ~40 leads | `0780_50_p_remarcar_th9ptw` | ✅ aprovado |
| 3 | Paciente pediu remarcação, não respondeu data | "[R] REMARCAÇÃO aguardando responder" | ~50 leads | `0780_50_p_remarcar_th9ptw` | ✅ aprovado |
| 4 | Convênio Inas/GDF (não atendido) | "[X] Inas GDF", "[X] Sulamerica" | ~15 leads | `105c_proposta_inasgdf_t7oejl` | ✅ aprovado |
| 5 | Paciente parou no envio de documentos | "[R] aguardo documento" | ~25 leads | `10aa_re_solicitar_documentos_ufstoj` | ✅ aprovado |
| 6 | Lead pediátrico > 6 meses sem retorno | "[C] Bebê 0-2", "[C] Criança 3-12" | ~20 leads | `blink_lf_c_pediatrico_v1` | ✅ aprovado |
| 7 | Paciente em pausa pessoal ("vou tirar siso") | "[E] pausa paciente" | ~10 leads | `blink_lf_e_pausa_paciente_v1` | ✅ aprovado |
| 8 | Sem convênio aceito, virou particular | "[C] AGENDAR SEM CONVÊNIO" | ~80 leads | `blink_lf_b_particular_v1` | ✅ aprovado |
| 9 | Convênio aceito mas não respondeu agenda | "[E] AGENDAR COM CONVÊNIO sem resposta" | ~70 leads | `blink_lf_a_convenio_aceito_v1` | ✅ aprovado |
| 10 | Catarata Dr. Fabrício sem retorno | "[F] catarata" | ~15 leads | `blink_lf_f_catarata_v1` | ✅ aprovado |
| 11 | Cliente retorno anual (> 1 ano sem voltar) | "[V] Cliente conhecido" | ~25 leads | `blink_lf_g_cliente_conhecido_v1` | ✅ aprovado |
| 12 | Lead sem nome do paciente | "[H] sem nome" | ~20 leads | `blink_lf_h_sem_nome_v1` | ✅ aprovado |
| 13 | Paciente confundiu data com dia da semana | bug Priscila lead 24055629 | recorrente | **❌ FALTA** | criar |
| 14 | Paciente pediu pra ser ligado (preferiu voz) | "[A] paciente pediu ligação" | ~10 leads | **❌ FALTA** | criar |
| 15 | Paciente confirmou consulta mas não pagou sinal | "[E] AGENDADO_aguardo confirmação pagamento" | ~30 leads | **❌ FALTA** | criar |
| 16 | Pós no-show (não veio D+0) | "[R] Faltou hoje" | recorrente | **❌ FALTA** | criar |
| 17 | Onboarding — paciente parou na coleta CPF | bug Adelia 24056883 | recorrente | **❌ FALTA** | criar |
| 18 | Paciente reativou mas Lia entrou fora de contexto | bug Larissa 21392947 / Talita | recorrente | **❌ FALTA** | criar |

---

## Distribuição por estágio

### Estágio: ATIVAÇÃO DE LEAD FRIO (2.LEADS FRIO, status_id 101508307)

Volume: 368 leads. Cobertura por templates atuais:

| Categoria do lead | Template aprovado | Mensagem |
|---|---|---|
| [E] convênio aceito (cobertura cobre) | `blink_lf_a_convenio_aceito_v1` | Oferece Asa Norte / Águas Claras / ligar |
| [C] particular (sem cobertura) | `blink_lf_b_particular_v1` | Oferece essa semana / 2 semanas / link online |
| [C] pediátrico | `blink_lf_c_pediatrico_v1` | Reforça importância avaliação precoce |
| [D] família 2+ pacientes | `blink_lf_d_familia_v1` | Oferece encaixar no mesmo dia |
| [E] pausa pessoal | `blink_lf_e_pausa_paciente_v1` | Sem pressão, retoma quando estiver pronto |
| [F] catarata Fabrício | `blink_lf_f_catarata_v1` | R$ 297 avaliação, indicação cirúrgica |
| [V] cliente conhecido (anual) | `blink_lf_g_cliente_conhecido_v1` | Check-up anual reservado |
| [H] sem nome do paciente | `blink_lf_h_sem_nome_v1` | Pergunta nome + convênio + unidade |
| [X] convênio não aceito | `105c_proposta_inasgdf_t7oejl` | Oferta opções de particular |

### Estágio: AGENDAR (3-AGENDAR, status_id 102560495) — 267 leads

Padrões diferentes do frio. Lead em conversa ativa mas parou.

| Sub-padrão | Template recomendado | Status |
|---|---|---|
| Pediu valor, não respondeu | `1098_men_sem_respost_valor_consulta_3vu2qw` | ✅ aprovado |
| Pediu horário e não respondeu | `10pp_dia_disponivel_aczfbx` | ✅ aprovado |
| Confirmou interesse mas não fechou | `1079_ativar_conversa_de_imediato_odlmcy` | ✅ aprovado |
| Aguarda documento pra agendar | `10aa_re_solicitar_documentos_ufstoj` | ✅ aprovado |
| Sumiu após Lia ofertar slots | `1078_sem_resposta_cbbaji` | ✅ aprovado |

### Estágio: ONBOARDING / 1-ATENDIMENTO HUMANO (status_id 106563343)

| Sub-padrão | Template recomendado | Status |
|---|---|---|
| Aguarda envio docs após agendamento | `1033_agradecer_envio_documentos_f9at6f` (já enviou) | ✅ aprovado |
| Confirmação D-1 véspera | `1015_confirmar_com_1_dia_antecedencia_*` (várias variantes) | ✅ aprovado |
| Lembrete localização D-0 | `1010_link_localizacao_asa_norte_oy3704` | ✅ aprovado |
| Pós-consulta avaliação Google | `blink_pos_avaliacao_asa_norte_v1` / `blink_pos_avaliacao_aguas_claras_v1` | ✅ aprovado |

---

## Templates faltantes pra criar e submeter ao Meta

Prioridade alta (cobrir gaps mais comuns):

### Template 1: `blink_data_corrigida_v1`
**Razão:** bug Priscila — Lia ofereceu "sexta (06/06)" mas 06/06 era sábado.
**Uso:** quando filtro detecta erro de data + dia semana, manda correção.
**Body params:** `{{1}}=nome`, `{{2}}=data_correta_com_dia_semana` (ex: "segunda 08/06/2026 às 14:00")
**Categoria Meta:** UTILITY (correção)

### Template 2: `blink_te_ligamos_v1`
**Razão:** paciente prefere canal voz.
**Uso:** lead deixou claro que quer ligação. Atendente vai ligar em X horas.
**Body params:** `{{1}}=nome`, `{{2}}=hora_estimada` (ex: "amanhã entre 9h e 11h")
**Categoria Meta:** UTILITY

### Template 3: `blink_sinal_pendente_v1`
**Razão:** paciente confirmou data + médico, falta pagar sinal pra reservar.
**Uso:** lembrete educado de Pix + valor + chave + reserva.
**Body params:** `{{1}}=nome`, `{{2}}=valor_sinal_50pc`, `{{3}}=chave_pix_unidade`, `{{4}}=dia_hora`
**Categoria Meta:** UTILITY

### Template 4: `blink_noshow_d0_v1`
**Razão:** paciente não compareceu hoje. Mensagem +30min após hora marcada.
**Uso:** "Vimos que não pôde vir hoje. Quer remarcar? Tenho horário pra X / Y."
**Body params:** `{{1}}=nome`, `{{2}}=dia_marcado`, `{{3}}=slot_proximo_a`, `{{4}}=slot_proximo_b`
**Categoria Meta:** UTILITY (continuidade de serviço)

### Template 5: `blink_cpf_pendente_v1`
**Razão:** Lia conversou mas paciente parou na coleta CPF.
**Uso:** "Pra reservar o horário no sistema preciso só do CPF do paciente. Pode mandar?"
**Body params:** `{{1}}=nome_responsavel`, `{{2}}=nome_paciente`
**Categoria Meta:** UTILITY

### Template 6: `blink_proxima_consulta_data_v1`
**Razão:** check-up anual / retorno X meses.
**Uso:** "Aqui Blink. Próximo retorno previsto: data. Quer reservar agora?"
**Body params:** `{{1}}=nome_paciente`, `{{2}}=intervalo_legivel` (ex: "1 ano", "6 meses")
**Categoria Meta:** MARKETING

---

## Próximas ações pragmáticas

1. **Plugar 6 templates novos no `templates_meta.py`** com slugs default + builders. Mesma estrutura do task #236.

2. **Submeter os 6 ao Meta Business Manager** via Graph API ou painel. Aguardar aprovação (24-72h).

3. **Mapear cada template no roteador de campanha:**
   - `/admin/disparar-categoria?categoria=R&template_lf=R` (REMARCAR) → `0780_50_p_remarcar`
   - `/admin/disparar-categoria?categoria=A&template_lf=A` (convênio aceito) → `blink_lf_a`
   - `/admin/disparar-categoria?categoria=B&template_lf=B` (particular) → `blink_lf_b`
   - novos templates entram quando aprovados

4. **Criar cron por padrão:**
   - Cron diário 09h: detecta no-shows do dia anterior + dispara `blink_noshow_d0_v1`
   - Cron semanal segunda 09h: dispara `blink_lf_a/b/c/d/e/f/g/h` por categoria
   - Cron diário 18h: detecta sinal pendente > 24h + dispara `blink_sinal_pendente_v1`

5. **Adicionar campo Kommo `MOTIVO_INTERRUPCAO` (select)** com 18 opções correspondentes aos padrões. Lia preenche quando detecta motivo da parada. Permite analytics depois.
