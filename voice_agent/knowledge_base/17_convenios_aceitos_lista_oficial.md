# CONVÊNIOS ACEITOS — LISTA OFICIAL TAXATIVA

⚠️ **REGRA DE SEGURANÇA OPERACIONAL — LEITURA RESTRITIVA**

Esta lista é **FECHADA E TAXATIVA**. Somente os convênios expressamente listados abaixo (com suas respectivas variações de nomenclatura) possuem atendimento na clínica.

O agente está programado com **"Tolerância Zero" para presunção de cobertura**. Caso o paciente informe um plano que não se encontre nesta lista oficial — a comparação é feita de forma flexível, **ignorando maiúsculas/minúsculas, acentos e espaços** (ex.: "Pró-Saúde", "Pro Saude" e "ProSaúde" são o MESMO convênio) — o agente deve informar taxativamente que não atendemos a rede credenciada solicitada, acionando o script de transição para atendimento sem convênio (ver artigo 14).

A política é **única para toda a clínica e para todos os profissionais**. Sem diferenciação por médico. Sem exceção.

---

## ⚠️ EXCEÇÕES CRÍTICAS — Procedimentos SEM convênio

**Os seguintes atendimentos NÃO aceitam convênio**, mesmo para pacientes com plano listado acima:

1. **SDP (Síndrome da Deficiência Postural)**
2. **Consultas relacionadas a Lentes de Prisma**

Esses procedimentos são exclusivamente **sem convênio** (pagamento direto).

### 🚨 Regra de comportamento sobre as exceções

1. **SEMPRE perguntar o motivo da consulta primeiro.**
2. É **ESTRITAMENTE PROIBIDO** mencionar que SDP ou Prisma não aceitam convênio ANTES de o paciente declarar explicitamente o motivo da busca.
3. **Só ativar a exceção** se a resposta do paciente contiver termos como:
   - "SDP"
   - "Síndrome de Deficiência Postural"
   - "Postural"
   - "Prisma" / "Lente de prisma" / "Óculos com prisma"
   - "Dores posturais" relacionadas à visão

4. Quando a exceção for ativada, usar o script:
> [Nome], esse tipo de atendimento (SDP / lentes de prisma) é exclusivamente sem convênio — não passa por nenhum convênio, inclusive os que normalmente aceitamos. Posso te passar o valor e disponibilidade?

---

## 🏥 LISTA OFICIAL DE CONVÊNIOS ACEITOS

Ordem alfabética. Cada item lista o nome OFICIAL e todas as variações que o paciente pode usar.

### A
- **Anafe** — também: ANAFE

### B
- **Bacen** — também: BACEN, Banco Central

### C
- **Care Plus** — também: CARE PLUS, CarePlus
- **Casec** — também: CASEC, CODEVASF
- **Casembrapa** — também: CASEMBRAPA, EMBRAPA
- **Conab** — também: CONAB

### E
- **E-Vida** — também: E VIDA, Luminar, LUMINAR

### F
- **Fascal** — também: FASCAL

### G
- **Gravia** — também: GRAVIA

### O
- **Omint** — também: OMINT

### P
- **PF Saúde** — também: PF, Polícia Federal
- **Plan Assiste-MPF** — também: MPU, MPF, MPT, MPDFT
- **Petrobrás** — também: PETROBRAS, Petrobras
- **Plas/JMU** — também: STM, Plas JMU
- **ProSaúde / Câmara dos Deputados** — também: Pro Saúde, Pró-Saúde, Pró Saúde, Pro-Saúde, Pró-Saude, Câmara dos Deputados, Câmara, Pró-Saúde da Câmara, ProSaude
- **Proasa** — também: PROASA
- **Pro Ser STJ** — também: ProSer, Proser, Pro-Ser, STJ, STJ Pro Ser, STJ Proser, STJ Pro-Ser, Proser STJ
- **Pro-social TRF** — também: TRF

### S
- **Saúde Caixa** — também: Caixa, CAIXA, Saude Caixa
- **Serpro** — também: SERPRO
- **SIS Senado** — também: SIS, Senado
- **STF-Med** — também: STF Med, STF, STFMed
- **STM Plas** — também: STM, Jmu, STM-Plas

### T
- **TJ DFT** — também: TJ, TJDFT, TJ-DFT, TJDFT Pró-Saúde, Pró-Saúde do TJDFT, Pró-Saúde TJDFT, Pró-Saúde do Tribunal, Tribunal de Justiça do DF
- **TRE Saúde** — também: TRE SAÚDE, TRE
- **TRT Saúde** — também: TRT SAÚDE, TRT
- **TST** — também: tst

---

## ⚠️ Atenção — "Pró-Saúde" é nome compartilhado

"Pró-Saúde" é o nome do plano usado por **DUAS instituições diferentes**: a **Câmara dos Deputados** e o **TJDFT**. **As duas são ACEITAS.**

Portanto: se o paciente disser "Pró-Saúde" (de qualquer forma — com ou sem acento, com ou sem hífen), o convênio é **ACEITO**. Nunca negue "Pró-Saúde". Se quiser, confirme de qual instituição é (Câmara ou TJDFT) para o registro — mas em nenhuma hipótese diga que não atende.

## 📋 Fluxo operacional padrão

```
1. Paciente menciona convênio (qualquer nome)
   ↓
2. Agente PERGUNTA o motivo da consulta (se não souber ainda)
   ↓
3. SE motivo = SDP / Prisma:
     → Aplicar exceção: "esse tipo é só sem convênio"
     → Ir para artigo 14 (funil sem convênio)
   SENÃO:
   ↓
4. Comparar nome do convênio (case-insensitive, normalizando acentos)
   com a lista oficial + variações
   ↓
5. SE encontrado claramente:
     → "Sim, atendemos [nome oficial]! Vamos seguir..."
     → Ir para artigo 13 (funil com convênio)

   SE HOUVER DÚVIDA (nome parecido com um da lista, incompleto,
   abreviado, com possível erro de digitação, ou nome de instituição
   que pode ter plano próprio) → NÃO NEGAR DE IMEDIATO. Primeiro
   CONFIRMAR com o paciente:
     → "Só para eu confirmar certinho — o seu convênio é o
       [nome mais próximo da lista]? Ou pode me dizer o nome completo
       do plano, por favor?"
     → Com a resposta, voltar ao passo 4. Negar é o ÚLTIMO recurso,
       nunca a primeira reação à dúvida.

   SE CLARAMENTE NÃO encontrado (nome conhecido, que de fato não está
   na lista e não há dúvida):
     → "[Nome], ainda não estamos credenciados ao [convênio]. Mas
       oferecemos incentivos especiais para pacientes com convênios
       que ainda não atendemos. Como prefere seguir?
       1️⃣ Seguir sem convênio
       2️⃣ Somente com convênio"
     → Se insistir: "Nossa política de convênios é única para toda
       a clínica. Sem exceção."
```

## ⚠️ Proibições absolutas

- ❌ NUNCA dizer "vou verificar com a recepção se atendemos esse convênio" — a lista é definitiva e o agente conhece todas as opções.
- ❌ NUNCA aceitar variação de nomenclatura que NÃO esteja explicitamente listada acima.
- ❌ NUNCA prometer atendimento sob convênio para SDP ou Prisma.
- ❌ NUNCA inferir similaridade ("Petrobrás Saúde" não é a mesma coisa que "Petrobrás" — só aceitar nome exato). Mas em caso de DÚVIDA, antes de negar, CONFIRME o nome com o paciente ou sugira o nome próximo da lista — negar é o último recurso, nunca a reação imediata.
- ❌ NUNCA mencionar que SDP/Prisma não aceitam convênio ANTES de saber o motivo da consulta.
