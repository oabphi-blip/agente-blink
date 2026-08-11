# Filtros Anti-Alucinação (pós-geração)

> Documentação dos filtros que rodam em `voice_agent/responder.py` (`_scrub_prohibited`)
> APÓS cada resposta gerada pelo Claude, antes de enviar pro paciente. Esses filtros são a
> última linha de defesa contra erros que escapem do prompt.

## Visão geral

Toda resposta passa por 3 estágios de filtragem:

1. **Chave Pix inventada** — bloqueia totalmente, substitui por fallback.
2. **Violação do artigo 36** (50% sem Fila de Encaixe) — substitui por mensagem correta.
3. **Vocabulário vetado** (§1.4) — substituição inline.

Adicional: **anti-pattern "equipe vai retornar"** — não bloqueia, só loga warning.

---

## 1. Detector de chave Pix inventada

### Função
`_detecta_chave_pix_inventada(text: str) -> bool`

### Allowlist (chaves oficiais)
```python
_CHAVES_PIX_OFICIAIS = {
    "karladelaliberaoftalmo@gmail.com",   # Asa Norte
    "52.303.729/0001-30",                  # Águas Claras (CNPJ)
}
```

### Lógica
1. Procura "chave pix" + até 120 chars no texto
2. Se houver email no trecho → bloqueia se não estiver no allowlist
3. Se houver CNPJ formatado no trecho → bloqueia se não estiver no allowlist (normaliza
   removendo pontos/traços/barras antes de comparar)

### Fallback
Se detectado:
```
Vou alinhar a informação correta sobre pagamento com a equipe e te retorno em instantes. ✨
```

### Casos de teste
| Input | Esperado |
|---|---|
| `"Chave Pix Asa Norte: karladelaliberaoftalmo@gmail.com"` | ✅ Passa |
| `"Chave Pix Águas Claras (CNPJ): 52.303.729/0001-30"` | ✅ Passa |
| `"Pix: 52303729000130"` (sem formatação) | ✅ Passa |
| `"chave pix qualquer@gmail.com"` | ❌ Bloqueia |
| `"chave pix CNPJ 99.999.999/0001-00"` | ❌ Bloqueia |

---

## 2. Detector de violação do artigo 36

### Função
`_viola_artigo_36(text: str) -> bool`

### Lógica
- Detecta menção a "50%", "cinquenta por cento", "adiantamento" ou "sinal de"
- Se não menciona "encaixe" também → viola artigo 36

No filtro principal, essa detecção só substitui a resposta SE também houver menção a "pix"
(sinal explícito de cobrança).

### Resposta substituta
```
Antes de seguir com o pagamento, deixa eu te apresentar as duas opções da clínica:

1️⃣ *Reserva Imediata* — adiantamento de 50% via Pix; garante seu dia/horário exatos na agenda.
2️⃣ *Fila de Encaixe* — sem adiantamento; pagamento só no dia da consulta; avisamos assim
   que surgir vaga compatível com sua preferência.

Qual formato prefere?
```

### Caso de teste
| Input | Esperado |
|---|---|
| `"Para reservar, faça o Pix de 50% — R$ 305,50"` | ❌ Substitui (sem Encaixe) |
| `"Temos: Reserva 50% Pix ou Fila de Encaixe. Qual prefere?"` | ✅ Passa |

---

## 3. Substituições de vocabulário vetado

### Lista (regex compilados, case insensitive)

| Padrão | Substitui por |
|---|---|
| `\binfelizmente[,\s]*` | (vazio — remove) |
| `\bdireitinho\b` | `direito` |
| `\bcertinho\b` | `certo` |
| `\brapidinho\b` | `rápido` |
| `\bbonitinho\b` | `bonito` |
| `\bqueridinha?\b` | (vazio) |
| `\bqueridinho\b` | (vazio) |
| `\bobrigadinho\b` | `obrigada` |
| `\bconsultinha\b` | `consulta` |
| `\bfilhinha\b` | `filha` |
| `\bshow\b` | `ótimo` |
| `\btá\b` | `está` |

### Pós-processamento

Após substituições, limpa:
- Espaços duplos → único
- `,` órfãos (vírgula antes de espaço) → remove
- `, ,` (vírgulas duplas) → vírgula simples
- Trim final

### Caso de teste
| Input | Output |
|---|---|
| `"Infelizmente, sem cobertura."` | `"sem cobertura."` |
| `"Vou te explicar direitinho rapidinho."` | `"Vou te explicar direito rápido."` |
| `"Tá bom!"` | `"está bom!"` |
| `"Posso confirmar?"` (limpo) | `"Posso confirmar?"` (inalterado) |

---

## 4. Anti-pattern "equipe vai retornar" (SOFT — só loga)

### Padrões detectados (não substitui automaticamente)

```python
_TRANSFER_ANTIPATTERN = [
    re.compile(r"equipe.{0,20}retornar", re.IGNORECASE),
    re.compile(r"equipe.{0,20}confirma", re.IGNORECASE),
    re.compile(r"sem acesso à agenda", re.IGNORECASE),
    re.compile(r"vou registrar.{0,20}prefer[êe]ncia", re.IGNORECASE),
]
```

### Por que só loga
Algumas dessas frases podem ser legítimas em situações específicas (Medware fora do ar, por
exemplo). Em vez de bloquear automaticamente, gera warning no log pra revisão posterior.

### O que fazer ao ver warning no log

1. Olhar o lead em questão.
2. Se a frase foi DESNECESSÁRIA (Lia tinha agenda real e fugiu pra humano), é bug —
   investigar por que o `mandatory_filenames` ou a `JANELA DE OFERTA DE AGENDA` não foi
   suficiente.
3. Se foi legítima (Medware caiu), tudo bem.

---

## 5. Mandatory filenames (sempre injetados no system prompt)

Não é "filtro" mas é parte da defesa contra alucinação. Em `responder.py`, no método
`reply()`, antes de chamar Claude:

```python
mandatory_filenames = [
    "00_identidade_e_unidades.md",
    "15_pagamento_pos_consulta.md",
    "17_convenios_aceitos_lista_oficial.md",
    "18_convenios_NAO_aceitos_lista_oficial.md",
    "19_tabela_valores_travas_por_medico.md",
    "22_agenda_dra_karla.md",
    "31_sdp_fluxo_excecao.md",
    "34_agenda_dr_fabricio.md",
    "36_pagamento_exclusivo_encaixe_karla.md",
]
```

Esses artigos são SEMPRE carregados, independente de retrieval por palavra-chave. Garante
que a Lia nunca opera sem saber:
- Endereços corretos das unidades (00)
- Política de pagamento pós-consulta (15)
- Lista de convênios aceitos/não (17, 18)
- Tabela de preços (19)
- Agendas dos médicos (22, 34)
- Fluxo SDP (31)
- Política sinal/encaixe (36)

Outros artigos (21, 26, etc.) são carregados sob demanda via retrieval por keywords.

---

## 6. Como adicionar novo padrão de bloqueio

Cenário: descobriu-se uma nova alucinação recorrente (ex.: Lia oferecendo descontos não
existentes).

### Passos
1. Identificar o padrão regex (ex.: `desconto de \d+%`, `oferta especial`).
2. Editar `voice_agent/responder.py`:
   - Adicionar regex em `_HALLUCINATION_PATTERNS` (bloqueio total) OU
   - Adicionar substituição em `_PROHIBITED_REPLACEMENTS` (substituição inline) OU
   - Criar função detectora dedicada (se for lógica complexa, como `_detecta_chave_pix_inventada`)
3. Adicionar casos de teste (tanto positivo quanto negativo) no script de teste do
   responder.
4. Validar `python3 -m py_compile voice_agent/responder.py`.
5. Commit + push (Easypanel faz redeploy).

### Princípio
Filtros pós-geração são caro/lento se mal feitos. Use:
- **Substituição inline** se a frase pode ser editada (vocabulário).
- **Substituição da resposta inteira** só pra coisas críticas (alucinação de pagamento,
  endereço inventado).
- **Log-only** quando o padrão é ambíguo (pode ser legítimo em casos raros).
