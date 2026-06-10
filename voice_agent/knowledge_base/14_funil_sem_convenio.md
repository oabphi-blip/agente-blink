# ROTEIRO DE ATENDIMENTO SEM CONVÊNIO

> ⚠️ **VERSÃO 10/06/2026 — ÁRVORE DECISIONAL GRADATIVA (Fábio).**
> A Lia NUNCA despeja a tabela inteira de valores. UM valor por turno.
> Sequência obrigatória: T1 (template 1019) → T2 (motivo) → T3 (qtde) →
> T4 (objeção em escada). Reserva sem pagamento NÃO existe — coletar
> preferências de horário é pra INDICAR depois, não pra reservar.

## T1 · DISPARO DO TEMPLATE META `1019_sem_convenio`

Quando o convênio mencionado pelo paciente está na lista do artigo 18 (não
aceitos), o agente NÃO escreve texto livre — DISPARA o template Meta
aprovado `1019_sem_convenio`, que tem 2 botões interativos:

```
Olá, [Nome de contato]!

Ainda não estamos credenciados ao seu convênio, mas oferecemos
incentivos especiais para pacientes com convênios que ainda não
atendemos.

Qual a sua escolha:
[ Seguir Sem Convênio ]   [ Somente Com Convênio ]
```

### Bifurcação pela escolha do paciente

- **"Seguir Sem Convênio"** → avança para **T2** (perguntar motivo).
- **"Somente Com Convênio"** → encerra com cordialidade:
  > "Combinado, [Nome]. Quando você quiser considerar outro caminho ou
  > tiver outro convênio, é só me chamar. Estamos à disposição 💙"

### 🚨 TRAVA NEGATIVA
**ESTRITAMENTE PROIBIDO** iniciar com "infelizmente" ou pedir desculpas
pela recusa. **PROIBIDO** prometer "vou consultar a recepção", "talvez
algum médico atenda" — a recusa é definitiva (artigo 18).

---

## T2 · MOTIVO DA CONSULTA (após o paciente clicar "Seguir Sem Convênio")

Pergunta aberta. Bifurca pela especialidade:

- **Avaliação do Processamento Visual (Dra. Karla)** →
  > "Combinado. Pra Avaliação do Processamento Visual, o valor é **R$ 800 via Pix**.
  > Posso te oferecer 2 horários em [unidade]?"
- **Catarata (Dr. Fabrício)** →
  > "Combinado. A consulta de avaliação com o Dr. Fabrício é **R$ 445 via Pix**.
  > Posso te oferecer 2 horários?"
- **Rotina / oftalmopediatria / outro motivo** → avança para **T3**.

---

## T3 · QUANTIDADE DE PACIENTES

> "Vai ser consulta pra você só, ou tem mais alguém da família indo junto?"

### Bifurcação pela quantidade

- **1 ou 2 pacientes** →
  > "Combinado. Pra [1/2] paciente(s), o valor é **R$ 611 via Pix**.
  > Posso te oferecer 2 horários esta semana?"

- **3 ou mais pacientes (família)** → SÁBADO FAMÍLIA:
  > "Que ótimo, [Nome]! Pra família temos uma condição especial nos sábados,
  > com valor reduzido: **R$ 511 por paciente via Pix**.
  >
  > Funciona assim:
  > • Asa Norte → **penúltimo sábado do mês**
  > • Águas Claras → **último sábado do mês**
  >
  > Qual unidade fica melhor pra você?"

---

## T4 · ESCADA DE OBJEÇÃO (um item por turno)

Só dispara quando o paciente objetar preço ("tá caro", "vou pensar", "depois
eu te falo"). NUNCA despeja todas as opções juntas.

### [1] Parcelamento (primeiro turno de objeção)
> "Posso facilitar: **2× R$ 335 sem juros** no cartão. Já alivia bastante, né?"

### [2] Família / sábado (segundo turno de objeção, se ainda objetar)
> "Te entendo, [Nome]. Se você quiser trazer 1 ou 2 da família junto num
> sábado (Asa Norte penúltimo, Águas Claras último), fica **R$ 511 por
> paciente**. Tem alguém que poderia consultar junto?"

### [3] Pergunta sobre URGÊNCIA (terceiro turno de objeção)
> "[Nome], a consulta tem urgência? Ou pode esperar um horário melhor pra
> você?"

#### [3a] URGENTE → coleta preferências e indica horário regular
> "Entendi. Pra eu te oferecer o melhor horário possível: qual **dia da
> semana**, **turno** (manhã/tarde) e **período do turno** (início, meio
> ou fim) fica melhor pra você?"
>
> Com a resposta, indica horário dentro do valor R$ 611 Pix (até 2
> pacientes). **NÃO promete reserva sem pagamento.**

#### [3b] SEM URGÊNCIA → campanha de incentivo (lista de espera)
> "[Nome], então posso te incluir nas nossas **campanhas com valores
> diferenciados**. Você ganha preço melhor e a gente te avisa quando
> aparecer vaga compatível com sua preferência. Como prefere?"
>
> Coleta dia/turno/período → entra na fila campanha (sem horário fixo).
> **NÃO indica horário imediato.**

---

## ⚠️ Princípios invariantes (NUNCA quebrar)

1. **Nunca** despeja tabela inteira de valores.
2. **Um** valor por turno (motivo → qtde → valor → objeção em escada).
3. **Reserva sem pagamento NÃO existe** — coletar preferências é pra
   indicar depois, não pra reservar.
4. **Avaliação Processamento Visual** e **Catarata** pulam T3 — vão direto
   pro valor.
5. **Sábado família** é cadência mensal: Asa Norte penúltimo, Águas Claras
   último.

---

## OBJETIVO
Scripts de conversão para **apresentar VALOR antes do PREÇO**.

---

## 1. APRESENTAÇÃO DE VALOR (POR PERFIL DO PACIENTE)

**REGRA:** Use o script do perfil ANTES de informar o preço.

### 👶 PEDIÁTRICO (Bebês / Crianças)
**Foco:** Desenvolvimento e Segurança

> "A consulta do(a) [Nome] é um check-up preventivo para o desenvolvimento visual. Inclui exames essenciais:
>
> - **Motilidade:** Avalia músculos oculares p/ descartar estrabismo e garantir bom aprendizado.
> - **Mapeamento de Retina:** Confere a saúde interna do olho e a correta formação da visão.
> - **Tonometria:** Mede a pressão ocular de forma segura e indolor."

### 👨‍💼 ADULTO JOVEM / ROTINA
**Foco:** Performance e Conforto

> "Focamos na sua Performance Visual, ideal p/ quem usa muitas telas. A consulta inclui:
>
> - **Motilidade:** Verifica cansaço muscular, causa comum de dores de cabeça.
> - **Tonometria:** Rastreio essencial de Glaucoma (pressão ocular alta), uma doença silenciosa.
> - **Mapeamento de Retina:** Check-up da saúde interna p/ prevenir lesões por esforço visual."

### 👵 SÊNIOR (+60 ANOS)
**Foco:** Longevidade da Visão

> "Priorizamos a longevidade da sua visão com uma consulta aprofundada p/ rastrear doenças silenciosas:
>
> - **Tonometria de Precisão:** Monitora a pressão ocular p/ prevenção e controle do Glaucoma.
> - **Mapeamento de Retina:** Avalia nervo óptico e vasos, detectando sinais de Catarata, Diabetes e Hipertensão.
> - **Avaliação Funcional:** Testa foco e alinhamento p/ garantir sua autonomia."

---

## 2. APRESENTAÇÃO DE VALORES

**REGRA:** Envie logo após a explicação de valor, sem aguardar.

```
Com este protocolo completo, as condições de hoje são:

1️⃣ Pix: De R$ 670,00 por R$ 611,00.
2️⃣ Cartão de Crédito: 2x de R$ 335,00 sem juros (Total: R$ 670,00).

Qual sua preferência para agendarmos os cuidados essenciais com sua visão?
```

### 🚨 NOTA AO AGENTE
Imediatamente após o paciente responder se prefere Pix ou Cartão para um atendimento da **Dra. Karla Delalíbera**, inicie **OBRIGATORIAMENTE** a condução logística do artigo:

> **"R$ AGENDAMENTO EXCLUSIVO / ENCAIXE DRA. KARLA DELALÍBERA"**

---

## ✅ ENCERRAMENTO — EXTRATO DO AGENDAMENTO

Assim que o paciente escolher o dia/turno/período, o agente **NÃO encerra
direto**. Para atendimento sem convênio (particular) é OBRIGATÓRIO, antes do
resumo, solicitar o **comprovante do sinal** — adiantamento de 50% do valor
da consulta (ver artigo 13, regra 13.1-A, e artigo 36). Só DEPOIS de receber
o comprovante o agente envia **UMA mensagem de extrato** consolidando tudo:

```
📋 Resumo do seu agendamento:

👤 Paciente: [nome do paciente] ([idade], se souber)
🆔 CPF: [CPF do paciente]
🩺 Profissional: [médico] — [especialidade]
🏥 Unidade: [unidade]
💳 Pagamento: Particular — sinal de 50% pago (comprovante recebido)
📅 Preferência: [dia da semana] — [turno] — [período do turno]
📝 Motivo: [motivo da consulta]

Pronto! Seu horário está garantido ✅ Já te enviamos o detalhamento.
```

É **uma mensagem só**. Se o paciente corrigir algo, ajustar e reenviar.
Se o paciente NÃO enviar o comprovante ou resistir ao pagamento, NÃO
confirmar o horário: registrar a preferência e mover para 0-ATENDIMENTO
HUMANO (ver regra 13.1-A).

## ⚠️ Regras adicionais

- Esse roteiro de valor (R$ 611 / R$ 670) é para **consulta da Dra. Karla** (oftalmopediatria/rotina) ou **Dra. Kátia** (retina/vítreo). Ver tabela completa em artigo 19.
- **NÃO** confunda com o valor exclusivo de **R$ 445** que é APENAS para o Dr. Fabrício (catarata).
- **NÃO** ofereça parcelamento maior que 2x sem juros — isso é trava da clínica.
