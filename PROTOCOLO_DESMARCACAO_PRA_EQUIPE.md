# Protocolo de Desmarcação · Blink Oftalmologia

> **Para a equipe de atendimento humano (5 usuários Team).**
> Usar como referência quando o paciente sinaliza cancelar/remarcar consulta.
> Versão sincronizada com a Lia (instrução E1.7 do prompt da IA — Bug C-26).

---

## 🎯 PRINCÍPIO CENTRAL

**Quando o paciente AGENDADO sinaliza que quer cancelar ou remarcar — NÃO oferecer slot novo na primeira resposta.**

Por que: oferecer remarcação imediata passa a percepção de "fácil desmarcar e marcar de novo". Vira comportamento de no-show.

O caminho correto: **investigar o motivo primeiro**, depois decidir o destino.

---

## 1. Identificar gatilho

São frases típicas que disparam esse protocolo:

- "vou precisar cancelar"
- "não consigo nesse dia"
- "tem outro horário?"
- "tive um imprevisto"
- "preciso mudar de dia"
- "vou ter que desmarcar"
- "não vou conseguir"
- "esqueci do horário"

E o paciente está com status **5-AGENDADO**, **6-CONFIRMAR**, **7-CONFIRMADO** ou **7.1-NO-SHOW**.

---

## 2. Verificar se o paciente tem convênio aceito ou é particular

No card do Kommo, campo **CONVÊNIO**:

- ≠ "Não se aplica" e está na lista de aceitos (Saúde Caixa, TJDFT, STF, etc) → **fluxo COM convênio**
- = "Não se aplica" → **fluxo SEM convênio (particular)**

---

## 3. Mensagem-gatilho (PASSO 1)

### Se COM convênio:

> *Entendo, {primeiro nome}. Pra eu te orientar do jeito certo, posso saber o motivo da desmarcação? Foi imprevisto pessoal, alguma questão com a autorização do {nome do convênio}, ou outro motivo? 💙*

### Se SEM convênio (particular):

> *Entendo, {primeiro nome}. Pra eu te orientar do jeito certo, posso saber o motivo? Foi questão financeira, imprevisto pessoal, ou outra coisa? (Se for financeiro, tenho outras opções que talvez ajudem.) 💙*

---

## 4. Matriz de decisão (PASSO 2)

### FLUXO COM CONVÊNIO

| Resposta do paciente | Sua resposta | Ações no Kommo |
|---|---|---|
| **Imprevisto pessoal** (problema no trabalho, com filho, doente, esqueci) | "Tudo bem. Vou te incluir na nossa **fila de encaixe** com seu {convênio}. Assim que abrir uma vaga em data e horário compatíveis, te aviso." | Status → **2.LEADS FRIO**<br>A FAZER → **Encaixe**<br>ATIVADO IA → **Desativado** |
| **Problema autorização** (convênio negou, falta carteirinha, guia expirada) | "Entendo. Vou te conectar com a equipe pra resolver a autorização com o {convênio}. Em breve alguém vai te procurar." | Status → **1-ATENDIMENTO HUMANO**<br>A FAZER → **Resolver Autorização**<br>ATIVADO IA → **Desativado** |
| **Sem interesse / mudou de ideia** | "Entendi, {nome}. Fico à disposição se um dia precisar voltar. Obrigada pelo contato. 💙" | Status → **Closed-lost**<br>ATIVADO IA → **Desativado** |
| **Sintoma novo / urgência** ("estou enxergando pior", "olho vermelho", "dor de cabeça") | "Entendo. Vou te encaminhar agora pra equipe avaliar a urgência. Aguarda só um momento." | Status → **1-ATENDIMENTO HUMANO**<br>AÇÕES → **Urgente**<br>ATIVADO IA → **Desativado** |

### FLUXO SEM CONVÊNIO (particular)

| Resposta do paciente | Sua resposta | Ações no Kommo |
|---|---|---|
| **Imprevisto pessoal** | "Tudo bem. Vou te incluir na **fila de encaixe**. Quando surgir vaga compatível, te aviso." | Status → **2.LEADS FRIO**<br>A FAZER → **Encaixe**<br>ATIVADO IA → **Desativado** |
| **Questão financeira** | **ESCADA — UMA opção por turno, NUNCA listar tudo de uma vez:**<br>🟢 **Turno 1:** "Posso dividir em **2x de R$ 335,00 via Pix**, pra ficar mais leve. Te ajuda?"<br>🟡 **Turno 2 (se recusou):** "Temos o **sábado família** — R$ 511 cada, se trouxer 3 ou mais pacientes. Quer organizar com a família?"<br>🔴 **Turno 3 (se recusou):** "Posso te incluir na **fila de incentivo** — preço menor, sem horário fixo, te aviso quando surgir vaga." | **Aceitou nova condição:** manter agenda + ajustar valores no card.<br>**Recusou tudo:** Status → **2.LEADS FRIO** + A FAZER → **Encaixe** + IA → **Desativado** |
| **Sem interesse** | "Entendi. Fico à disposição. Obrigada. 💙" | Status → **Closed-lost**<br>ATIVADO IA → **Desativado** |
| **Sintoma / urgência** | "Entendo. Vou te encaminhar pra equipe avaliar urgência." | Status → **1-ATENDIMENTO HUMANO**<br>AÇÕES → **Urgente**<br>ATIVADO IA → **Desativado** |

---

## 5. Frases PROIBIDAS — nunca usar com paciente desmarcando

- ❌ "Antes de cancelar, posso te oferecer remarcar"
- ❌ "Tenho disponibilidade em outros dias / horários"
- ❌ "Talvez consiga encaixar num dia que fique mais tranquilo"
- ❌ "Prefere que eu te mostre outras opções de data?"
- ❌ "Quer ver a agenda?"
- ❌ "Deixa eu reconsultar a agenda real aqui pra você"
- ❌ "Vou te mostrar opções"

---

## 6. Conceitos

- **Encaixe** = fila de espera, gerida pelo atendimento humano. NÃO é vaga pra hoje/amanhã. Tempo de espera é variável. **A Lia (e você) NÃO promete prazo.**
- **Fila de incentivo** (só particular) = lista de pacientes dispostos a aceitar preço menor sem horário fixo. Avisamos quando vaga remanescente aparecer.

---

## 7. Anti-loop

Se o paciente **não responder** à pergunta de motivo após 1 turno (digamos, mandou outra coisa não relacionada), **não repita a pergunta**. Vai direto pro encaixe genérico:

> *Tudo bem. Vou te incluir na fila de encaixe e a equipe vai te dar retorno em breve.*

E executa as ações do ramo "imprevisto pessoal" do fluxo correspondente.

---

## 8. Casos-piloto (referência)

- **Sophia 23845330** — bebê 0-2a, TJDFT, Karla AC. Já tinha consulta marcada 11/06 16:30. Lia disse "deixa eu reconsultar a agenda" 2x e não voltou. **Correto:** mover pra LEADS FRIO + Encaixe + IA Off. Aplicado manualmente em 12/06.
- **Tito/Aline Weber 24130572** — criança 3-12, particular, Karla AN. Lia ofereceu "remarcar para um momento melhor" — frase PROIBIDA. **Correto:** ter perguntado motivo + escada financeira se aplicável.
