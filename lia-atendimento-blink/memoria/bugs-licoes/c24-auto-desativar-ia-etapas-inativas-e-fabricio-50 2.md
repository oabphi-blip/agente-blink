# Bug C-24 — Auto-desativar IA em etapas operacionais + Fabrício 50+ (não "exclusivamente catarata")

**Data:** 11/06/2026
**Commits:** e4e7201 `fix(bug-c24)` + 94ae99e `fix(bug-c24a-rev): restringir _STATUS_INATIVOS_IA a 4 etapas`

## C-24a — Lia respondia em etapas operacionais

### Sintoma
Equipe humana reclamou: ao mover lead pra etapas operacionais (ATENDIMENTO HUMANO,
CIRURGIAS, LENTES, FORNECEDORES), Lia continuava respondendo.

### Causa raiz
Não havia gatilho que desativasse a IA quando o lead entrava numa etapa onde humano
estava atuando.

### Fix
- `webhook.py` ganha `_STATUS_INATIVOS_IA`. **Lista RESTRITA (revisão Fábio 11/06 13:40)**
  = `{106563343 ATENDIMENTO HUMANO, 106157139 CIRURGIAS, 106484343 LENTES,
  106484347 FORNECEDORES}` — SÓ essas 4.
- Etapas 8-REALIZADO, 09-PRÓXIMA, Closed-won, Closed-lost MANTÊM IA ativa (Lia faz
  follow-up / NPS / reativação nelas).
- Endpoint `/admin/kommo-trigger-status-change` bifurca: status ∈ INATIVOS →
  `ATIVADO IA = Desativado`; demais etapas operacionais → `ATIVADO IA = Ativado`.

> Nota: o commit inicial (e4e7201) tinha um set largo de 8 etapas; o commit de revisão
> (94ae99e) restringiu pra 4 conforme correção do Fábio. Usar SEMPRE a lista de 4.

## C-24b — Fabrício "exclusivamente catarata" era restritivo demais

### Sintoma
Regra anterior dizia "Fabrício atende exclusivamente catarata". Paciente 50+ pode não
saber que tem catarata → matching médico falhava / parecia restritivo.

### Fix — Regra E5.7-A reescrita (matching por IDADE + MOTIVO)
- Pediátrico → Karla.
- Adulto 18–49 + rotina → Karla (Avaliação do Processamento Visual).
- **Adulto 50+ + qualquer motivo → Dr. Fabrício Freitas, especialista em saúde ocular do
  adulto 50+.**
- Catarata declarada (qualquer idade) → Fabrício.
- APV / Prisma / Estrabismo (qualquer idade) → Karla.
- Tom PROIBIDO: "exclusivamente catarata", "só faz cirurgia".
- Tom correto: "Para adultos 50+ o atendimento é com Dr. Fabrício Freitas".

## Cenário pytest sugerido

- "status_change → 1-ATENDIMENTO HUMANO → ATIVADO IA = Desativado."
- "status_change → 8-REALIZADO → ATIVADO IA = Ativado (Lia segue ativa)."
- "Adulto 55a + rotina → roteia Fabrício; criança 8a + rotina → Karla."

## Tags

`#ativado-ia` `#status-change` `#webhook` `#medico-matching` `#fabricio-50` `#handoff-humano`
