# Bug cobrança antes de slot — Lia pediu R$ 305,50 sem oferecer horário

**Lead**: 24034205
**Data**: maio/2026

## Sintoma
Paciente nunca tinha escolhido horário. Lia pulou direto pra "Faça o Pix de R$ 305,50 na chave karladelaliberaoftalmo@gmail.com pra garantir seu horário". Pular etapa de qualificação.

## Causa raiz
Lia aprendeu (KB) sobre sinal de 50%, política, chaves Pix. Mas quando paciente expressou interesse vago ("quero marcar"), Lia foi direto pra cobrança porque o prompt não tinha ordem rígida.

## Fix
`voice_agent/responder.py`:

1. **`_COBRANCA_SINAL_PATTERNS`**: regex pra detectar "sinal R$", "chave Pix", "comprovante pix" na resposta gerada.

2. **`_SLOT_CONCRETO_NA_RESPOSTA`**: regex pra detectar slot concreto (dia da semana + data + hora, tipo "Segunda 10/06 às 14h30").

3. **`_viola_cobranca_antes_slot()`**: se detectou cobrança SEM slot concreto na mesma mensagem E sem menção a "encaixe", substitui pelo fallback:
   > "Antes de qualquer pagamento, deixa eu te oferecer os horários reais. Qual dia da semana e turno funcionam melhor pra você? Assim já te passo as opções concretas com data e hora."

4. **KB Regra 12.9 NOVA**: ordem rígida no `_MASTER_INSTRUCTION.md`:
   ```
   oferecer slot → confirmar → apresentar 2 opções pagamento → cobrar
   ```

## Cenário pra pytest
- caller_context: paciente novo, sem dia_consulta_ts
- Lia responde texto com "sinal R$ 305,50" sem "10/06 às 14h"
- Filtro substitui pelo fallback de oferta de horário

## Tags
`bug-fix` `pagamento` `filtro-pos-geracao` `kb-regra-12.9`
