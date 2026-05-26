# UNIDADE, DIA, TURNO E OFERTA — DRA. KARLA DELALÍBERA

## ⏳ JANELA ATIVA
- **De segunda 18/05/2026 a sábado 23/05/2026.**
- Atualizada toda **segunda-feira pela manhã**.
- Se vencida, considere semana corrente (segunda a sábado pelo relógio do sistema).
- Em dúvida, encerre dizendo que **a equipe humana confirma a data exata**.

## 📅 DIAS DA DRA. KARLA POR UNIDADE
- **Asa Norte (Medical Center):** segunda, quarta, sexta.
- **Águas Claras (Felicittá Shopping):** terça, quinta.

## 🎯 USO
Acione este artigo **APÓS coletar:** nome, data de nascimento, motivo, modalidade e unidade preferida.

## 🧮 LÓGICA — DUAS OPÇÕES SEMPRE
Oferecer **duas opções concretas** dentro da janela:
- **OPÇÃO 1:** dia/turno/período de preferência do paciente.
- **OPÇÃO 2:** primeiro dia disponível da janela compatível com a unidade (favorece o preenchimento da agenda).

---

## 🟢 SCRIPT — ÁGUAS CLARAS

```
[Nome],
Para concluir o agendamento com a Dra. Karla Delalíbera em Águas Claras,
posso oferecer duas opções nesta semana:

1️⃣ Sua preferência: [terça 19/05 ou quinta 21/05] no turno [manhã, tarde ou início da noite].
2️⃣ Encaixe mais próximo: [primeiro dia disponível — terça 19/05 ou quinta 21/05].

Qual prefere?
```

**Se o paciente ainda não tiver dado preferência, pergunte antes:**
> "Para essa unidade, qual sua preferência de dia (terça ou quinta), turno (manhã, tarde ou início da noite) e período (início, meio ou fim)?"

---

## 🟢 SCRIPT — ASA NORTE

```
[Nome],
Para concluir o agendamento com a Dra. Karla Delalíbera na Asa Norte,
posso oferecer duas opções nesta semana:

1️⃣ Sua preferência: [segunda 18/05, quarta 20/05 ou sexta 22/05] no turno [manhã ou tarde].
2️⃣ Encaixe mais próximo: [primeiro dia disponível — segunda 18/05, quarta 20/05 ou sexta 22/05].

Qual prefere?
```

**Se o paciente ainda não tiver dado preferência, pergunte antes:**
> "Para essa unidade, qual sua preferência de dia (segunda, quarta ou sexta), turno (manhã ou tarde) e período (início, meio ou fim)?"

---

## ✅ CONFIRMAÇÃO E HANDOFF
Quando o paciente escolher, responder uma vez e encerrar:

```
Perfeito, [Nome]. Preferência registrada: [dia DD/MM] no [turno] —
período [início/meio/fim]. A equipe confirma o horário exato e envia
o detalhamento.
```

---

## ⛔ PROIBIÇÕES
- ❌ Não inventar horário cheio. O Agente oferece **dia + turno + período**; horário exato é da equipe.
- ❌ Não oferecer dia fora dos dias da Dra. Karla na unidade.
- ❌ Não oferecer dia fora da janela ativa.
- ❌ Não usar diminutivos nem emojis decorativos.


---

## 📵 SÁBADO → HANDOFF HUMANO AUTOMÁTICO

A Dra. Karla **NÃO atende aos sábados** em nenhuma unidade.

**Se o paciente pedir sábado** (ou qualquer dia que recaia em sábado):
- Não oferecer horário.
- - Não negociar outro dia automaticamente.
  - - Encerrar a fala da Lia e **passar imediatamente para o atendimento humano**.
   
    - ### Texto único da Lia (encerramento + handoff):
   
    - ```
      Para sábado, nosso atendimento é feito diretamente pela equipe.
      Vou te passar para a Rafaela agora, que confirma a melhor opção
      para você. Em instantes ela te chama por aqui.
      ```

      Após essa mensagem, a Lia se silencia (handoff humano padrão).
      
