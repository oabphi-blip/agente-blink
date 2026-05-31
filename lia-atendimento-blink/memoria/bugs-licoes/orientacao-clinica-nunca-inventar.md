# PROIBIDO inventar orientação clínica (anti-padrão #2 recorrente)

> Registrada em 31/05/2026 (task #92). Fábio sinalizou que a IA estava
> repetindo o mesmo erro: chutar conteúdo clínico em vez de só repassar
> o que está em fonte verificada.

## O que aconteceu

Ao montar as mensagens do ciclo D-3 / D-1 / D-0, eu (Claude/IA) **inventei**
orientações para o paciente sem nenhuma fonte:

| Mensagem inventada | Médico | Por que era invenção |
|---|---|---|
| "exame infantil dura 1h-1h30" | Karla pediatria | duração real do slot é 30 min |
| "SDP/Prisma dura até 2 horas" | Karla SDP | slot real 30 min |
| "vale trazer brinquedo ou lanche para a criança" | Karla pediatria | sem fonte na KB |
| "venha acompanhada(o) por pessoa maior de idade" | Fabrício pré-op catarata | sem fonte na KB |
| "se a equipe pediu jejum ou pausa de medicamento" | Fabrício pré-op | sem fonte na KB |
| "exame de retina pode envolver dilatação da pupila" | Kátia | sem fonte na KB |
| "visão pode ficar embaçada por algumas horas" | Kátia / Fabrício | sem fonte na KB |

**Todas removidas**.

## A regra (Cosmoética Blink)

A Lia **nunca diz** ao paciente:
- O que trazer (brinquedo, lanche, óculos antigos, receitas, etc.)
- O que NÃO trazer
- Se vai estar acompanhada(o)
- Se há jejum
- Se há pausa de medicamento
- Quanto tempo o exame dura *além* do que está no slot Medware
- O que acontece com a visão depois do exame

…**a menos que** a orientação esteja:
1. Em artigo da `voice_agent/knowledge_base/` (autoridade KB) ou
2. Em arquivo de `lia-atendimento-blink/memoria/bugs-licoes/` validado por Fábio
3. Confirmada explicitamente pela equipe clínica.

## Como adicionar uma orientação no futuro

Quando equipe médica confirmar uma instrução verdadeira (ex.: "Karla pediu
que para crianças de 0-2 anos, mãe traga mamadeira"), seguir:

1. Criar artigo KB ou nota na memória ativa com a regra + autor + data.
2. Editar `voice_agent/mensagens_ciclo.py::_orientacao_pre_op()` adicionando
   o caso COM comentário citando o arquivo fonte.
3. Adicionar pytest que afirma presença dessa orientação SOMENTE no contexto
   correto (médico + motivo) e ausência em outros casos.
4. NUNCA pular passo 1 e 3.

## Onde isso é blindado

`tests/test_mensagens_ciclo.py` agora tem testes que afirmam a AUSÊNCIA
das frases inventadas:
- `test_NAO_inventa_orientacao_catarata_fabricio`
- `test_NAO_inventa_orientacao_pediatria_karla`
- `test_NAO_inventa_orientacao_retina_katia`
- `test_NAO_inventa_duracao_em_orientacao_karla`
- `test_NAO_inventa_duracao_em_orientacao_sdp`

Se algum LLM no futuro reintroduzir "brinquedo" ou "dilatação" nas
mensagens, build quebra na hora.

## Conexão com o padrão maior

Esta lição é a manifestação concreta dos seguintes anti-padrões do CLAUDE.md
seção 16:

- #1 "Adivinho path em vez de checar" → adivinhei orientação clínica em vez de pedir
- #2 "Codifico mapeamento sem listar a fonte" → codifiquei orientação sem KB
- #4 "Mudo prompt sem rodar pytest" → coloquei texto no prompt sem teste

Antes de qualquer texto novo que VAI AO PACIENTE, pergunta: "tem fonte?".

Última atualização: 31/05/2026
