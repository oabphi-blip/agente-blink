# TTS lê "Dra." como "Doutor" (masculino) — sempre escrever por extenso

**Data**: 31/05/2026
**Contexto**: geração de 24 áudios de ativação com OpenAI TTS (`tts-1-hd`, voz `alloy`).

## Sintoma

Áudio da amostra falando "**Doutor Karla Delalíbera**" em vez de
"**Doutora Karla Delalíbera**" — TTS expandiu a abreviação `Dra.` como
masculino.

Fábio detectou ouvindo a amostra antes de gerar o batch dos 24. Se tivesse
seguido, os 24 mp3 teriam ido pro WhatsApp com o título errado.

## Causa

OpenAI TTS resolve abreviações por padrão para o **masculino**:
- `Dr.` → "Doutor" (OK)
- `Dra.` → "Doutor" (ERRADO — deveria ser "Doutora")
- `Sr.` / `Sra.` — mesmo problema esperado

A abreviação ambígua entra na inferência interna e o modelo escolhe o
masculino como default.

## Fix

Em todo texto que vira áudio (roteiros TTS, scripts de ativação, qualquer
input pra `client.audio.speech.create()`), escrever os títulos **por extenso**:

- `Doutora Karla Delalíbera` (não `Dra. Karla Delalíbera`)
- `Doutor Fabrício Freitas` (não `Dr. Fabrício Freitas`)
- `Senhor` / `Senhora` (não `Sr.` / `Sra.`)

Em **texto escrito** (Kommo notes, WhatsApp, prompt da Lia) pode manter
abreviado — o problema é só na conversão pra áudio.

## Onde gravar

- `outputs/audios_karla/roteiros.json`: 18 ocorrências corrigidas em
  31/05/2026 via `Edit replace_all`
- Toda receita futura de roteiro de áudio (Fabrício, Kátia quando voltar):
  começar com "Doutor/Doutora <nome> por extenso"

## Sentinela (TODO)

Pytest novo: ler qualquer `roteiros*.json` em `outputs/audios_*/` e falhar
se encontrar `Dra.` ou `Dr.` (com ponto) no campo `texto`. Garante que
qualquer roteiro novo entre já blindado.
