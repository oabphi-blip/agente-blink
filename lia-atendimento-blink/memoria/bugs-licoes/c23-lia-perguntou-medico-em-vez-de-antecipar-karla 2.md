# Bug C-23 — Lia perguntou "qual médico" em vez de antecipar Dra. Karla

**Data:** 11/06/2026
**Lead:** 24135088 (Adrielly, 23 anos, rotina de óculos, particular)
**Commit:** 4154547 `fix(prompt): Bug C-23 rotina/oftalmologia geral SEMPRE com Dra. Karla`

## Sintoma

Lia entrou em loop de 8 mensagens em 4 minutos e terminou pedindo ao paciente:
**"Deixa eu reconferir aqui qual médico você tinha preferência. Pode me confirmar o
nome do médico que você quer atender?"** — paciente não sabe nome do médico, fluxo travou.

## Causa raiz

1. Campo `MEDICOS` no Kommo vinha errado = "Dr. Fabrício Freitas" (Fabrício não atende rotina).
2. Lia leu o campo e ficou confusa.
3. Em vez de IGNORAR o campo errado e aplicar a regra (rotina = Karla), repassou a decisão
   pro paciente.
4. Paciente não sabe qual médico → trava.

## Fix

- Regra **E5.7-A** reescrita em `_MASTER_INSTRUCTION.md`:
  - Rotina / check-up / óculos / queixa visual geral → SEMPRE Dra. Karla Delalíbera,
    especialista Avaliação do Processamento Visual.
  - Dr. Fabrício atende catarata (e — após revisão C-24 — adulto 50+).
  - Mesmo que `MEDICOS` no Kommo venha errado, Lia IGNORA e anuncia proativamente o médico
    correto, corrigindo o campo se necessário.
  - PROIBIDO perguntar "qual médico você quer". Lia decide pela especialidade do motivo.
  - Anti-loop: nunca >3 mensagens sem resposta do paciente.

## Cenário pytest sugerido

- "Lead rotina + campo MEDICOS='Fabrício' → Lia anuncia Karla, NÃO pergunta médico."
- "Lia não emite >3 mensagens consecutivas sem inbound do paciente."

## Tags

`#medico-matching` `#loop` `#campo-kommo-errado` `#rotina-karla` `#anti-loop`
