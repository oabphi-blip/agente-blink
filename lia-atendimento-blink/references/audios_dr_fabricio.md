# Áudios na voz do Dr. Fabrício Freitas

> 7 áudios gravados pelo Dr. Fabrício pra usar em momentos-chave da conversa de catarata.
> Cada um tem gatilho específico. O áudio ACOMPANHA o texto (nunca substitui).
> Reflexo do artigo 35 do KB. Detalhes técnicos: `voice_agent/audios_fabricio.py`.

---

## Catálogo (IDs e gatilhos)

| Áudio ID | Gatilho | Etapa | Tema |
|---|---|---|---|
| `audio_1_dr_fabricio_freitas` | Paciente novo catarata mencionou Dr. Fabrício OU motivo = catarata | E3 (após nome) | Apresentação do médico |
| `audio_6_medo_da_cirurgia` | Paciente disse "tenho medo", "fico com receio", "minha mãe tinha medo", "preocupado(a)" | E3 (acolhimento) | Tranquilizar sobre cirurgia |
| `audio_7_o_que_e_avaliacao` | Paciente perguntou "o que vai ser feito?", "como funciona a avaliação?", "preciso fazer exame?" | E3 (educação) | Explica avaliação cirúrgica |
| `audio_5_interesse_nas_lentes` | Paciente mencionou "lente intraocular", "lente premium", "lente multifocal" | E3 ramo lentes | Sobre LIO premium |
| `audio_2_preciso_cuidar_disso_agora` | Paciente disse "vou pensar", "está caro", "mais tarde", "depois decido" APÓS valor apresentado | E7 (objeção) | Urgência da cirurgia |
| `audio_4_convite_para_agendar` | Paciente superou objeção (respondeu OK ao audio 2) — ANTES de oferecer slots | E7 (pré-fechamento) | Convite pra fechar |
| `audio_3_retomada_parou_de_responder` | **NUNCA enviado pela Lia.** Disparado pelo motor de follow-up automático quando paciente parou 12-23h | Follow-up | Retomada |

---

## Como sinalizar o envio

A Lia inclui no FINAL da resposta:
```
[AUDIO:audio_id]
```

Exemplo:
```
Entendo a sua preocupação, Mariana. É absolutamente normal sentir receio.

Vou te enviar um áudio aqui que o Dr. Fabrício gravou — ele explica direto, na voz dele,
como é o procedimento.

[AUDIO:audio_6_medo_da_cirurgia]
```

O sistema (`voice_agent/pipeline.py`):
1. Detecta o marcador `[AUDIO:audio_id]`
2. Verifica guardas (janela 24h Meta, limite por conversa, paciente prefere texto?)
3. Se OK: envia o texto SEM o marcador + o áudio em sequência via Kommo execute_handlers
4. Se bloqueado: envia só o texto

---

## Guardas automáticas (sistema verifica)

- **Janela 24h Meta**: se última msg do paciente foi há mais de 23h, áudio é descartado
  (não pode enviar áudio livre fora da janela WhatsApp Cloud API)
- **Máximo 3 áudios por conversa**: pra não saturar
- **Mínimo 2 mensagens entre 2 áudios**: pra não disparar em sequência
- **Paciente prefere texto**: se na E1 escolheu "texto", NUNCA enviar áudio nessa conversa

---

## Proibições

- ❌ NUNCA enviar 2 áudios na mesma mensagem (se quiser 2, são 2 mensagens separadas)
- ❌ NUNCA enviar áudio sem texto que faça sentido sozinho (paciente pode estar em local
  sem áudio)
- ❌ NUNCA inventar marcador de áudio que não existe (só os 7 IDs listados)
- ❌ NUNCA enviar áudio na primeira mensagem da conversa (aguarde E2 ao menos)
- ❌ NUNCA usar áudio pra dúvida operacional simples (endereço, horário, sábado?)
- ❌ NUNCA enviar áudio pra paciente que NÃO é caso Dr. Fabrício (Karla/Kátia não tem)

---

## URLs públicas (hospedados no Easypanel)

`https://blink-agent.6prkfn.easypanel.host/static/audios/dr_fabricio/{filename}`

Catálogo em `voice_agent/audios/dr_fabricio/catalogo.json`.

---

## Exemplo de uso completo

### Caso: Medo da cirurgia
> Paciente: "Tenho muito medo de cirurgia nos olhos."
>
> Lia: "Entendi, Mariana. É super comum ter esse receio, e te entendo. O Dr. Fabrício
> gravou um áudio explicando direto como é o procedimento — ouve com calma:
>
> [AUDIO:audio_6_medo_da_cirurgia]"

### Caso: Apresentação institucional
> Paciente: "Quero marcar uma consulta com o Dr. Fabrício para catarata."
>
> Lia: "Que bom, [Nome]! O Dr. Fabrício gravou uma apresentação rápida pra você:
>
> [AUDIO:audio_1_dr_fabricio_freitas]
>
> Pra eu organizar o atendimento, me passa a data de nascimento e o convênio?"
