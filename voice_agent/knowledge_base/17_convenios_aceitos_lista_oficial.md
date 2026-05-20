# CONVÊNIOS ACEITOS — LISTA OFICIAL TAXATIVA

⚠️ **REGRA DE SEGURANÇA OPERACIONAL — LEITURA RESTRITIVA**

Esta lista é **FECHADA E TAXATIVA**. Somente os convênios expressamente listados abaixo (com suas respectivas variações de nomenclatura) possuem atendimento na clínica.

O agente está programado com **"Tolerância Zero" para presunção de cobertura**. Caso o paciente informe um plano que não se encontre, **letra por letra**, nesta lista oficial, o agente deve informar taxativamente que não atendemos a rede credenciada solicitada, acionando o script de transição para atendimento sem convênio sem convênio (ver artigo 14).

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
- **ProSaúde / Câmara dos Deputados** — também: Pro Saúde, Pro-Saúde, Câmara dos Deputados, ProSaude
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
- **TJ DFT** — também: TJ, TJDFT, TJ-DFT
- **TRE Saúde** — também: TRE SAÚDE, TRE
- **TRT Saúde** — também: TRT SAÚDE, TRT
- **TST** — também: tst

---

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
5. SE encontrado:
     → "Sim, atendemos [nome oficial]! Vamos seguir..."
     → Ir para artigo 13 (funil com convênio)
   SE NÃO encontrado:
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
- ❌ NUNCA inferir similaridade ("Petrobrás Saúde" não é a mesma coisa que "Petrobrás" — só aceitar nome exato).
- ❌ NUNCA mencionar que SDP/Prisma não aceitam convênio ANTES de saber o motivo da consulta.
