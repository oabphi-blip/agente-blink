# Geração dos 24 áudios da Dra. Karla — TTS

## O que tem nessa pasta

- `roteiros.json` — 24 roteiros extraídos do docx
- `gerar_audios.py` — script Python que chama OpenAI TTS

## Como gerar (~2 minutos, custo ~US$ 0,25)

No Terminal do Mac:

```bash
cd ~/Documents/Claude/Projects/AGENTE\ IA\ BLINK/outputs/audios_karla
pip3 install --user openai   # se ainda não tiver
export OPENAI_API_KEY=sk-...  # cole sua chave do Easypanel
python3 gerar_audios.py
```

Vai gerar 24 arquivos `audio_01_follow_up_apos_valor.mp3` até
`audio_24_agradecimento.mp3`.

## Customizar voz

Default: voz `nova` (feminina jovem profissional) + modelo `tts-1-hd`.

Pra experimentar outra voz:

```bash
TTS_VOZ=shimmer python3 gerar_audios.py   # voz mais suave/calorosa
TTS_VOZ=fable python3 gerar_audios.py     # britânica (com sotaque)
```

## Próximos passos depois de gerar

1. **Escutar os 24** e decidir quais entram no fluxo da Lia
2. **Subir os MP3** pro voice_agent (path: `voice_agent/static/audios/`)
3. **Plugar gatilho** na `renovacao_dispatcher` que escolhe o áudio
   conforme o contexto:
   - Catarata + valor pesado → `audio_02`
   - Estrabismo infantil → `audio_11`
   - Sumiu após documentos → `audio_19`
   - etc.
4. **Anexar nas mensagens** via `wa_cloud.send_audio()` (URL do
   `AUDIO_BASE_URL` que já está em prod)

## Mapeamento gatilho → áudio (referência rápida)

| Cenário | Áudio |
|---|---|
| Sumiu depois do valor (geral) | 01 |
| Achou caro | 02 |
| "Vou pensar" | 03 |
| Não entendeu o que tem na consulta | 04 |
| Convênio não aceito | 05 |
| Hesita em ir como particular | 06 |
| Estrabismo — geral | 07 |
| Estrabismo + indicação cirúrgica | 08 |
| Estrabismo — 1ª vez | 09 |
| Medo de cirurgia estrabismo | 10 |
| Estrabismo infantil — pais preocupados | 11 |
| Rotina adulto sumiu | 12 |
| Check-up anual genérico | 13 |
| Pediatria — agendar criança | 14 |
| Pediatria — sintomas mencionados | 15 |
| Família/coletiva | 16 |
| Sem 1ª resposta | 17 |
| Travou na escolha de dia/horário | 18 |
| Travou no envio de documentos | 19 |
| Reengajamento (1-2 dias depois) | 20 |
| Última tentativa | 21 |
| Acolhimento geral | 22 |
| Por que cuidar agora | 23 |
| Agradecimento/despedida | 24 |
