---
title: "Setup Obsidian Vault — Blink"
tags: [setup, obsidian]
---

# Setup Obsidian Vault — Blink Oftalmologia

## 1. Abrir este folder como vault (3 cliques)

1. Abra Obsidian no Mac.
2. Menu **Vault → Open another vault → Open folder as vault**.
3. Selecione `/Users/fabiophilipecostamartins/Documents/Claude/Projects/AGENTE IA BLINK`.

O Obsidian vai detectar a pasta `.obsidian/` que já está configurada e carregar o vault. A primeira tela que abre é `00-INDEX.md`.

> ⚠️ Quando aparecer o prompt **"Trust author and enable plugins?"**, clique **Trust**. Sem isso, plugins comunitários ficam bloqueados.

---

## 2. Plugins essenciais (instalar nesta ordem)

**Settings → Community plugins → Browse** e instale:

### 🥇 Obrigatórios (10 min de setup)

| Plugin | Por que | O que muda no vault |
|---|---|---|
| **Dataview** | Queries SQL-like em frontmatter | Tabelas no `00-INDEX` viram automáticas (categoria → leads filtrados) |
| **Tasks** | Checklist com data de vencimento | `- [ ] revisar campanha 📅 2026-06-11` aparece num dashboard global |
| **Templater** | Templates dinâmicos com data/hora | Cria `HANDOFF_{date}.md` num clique |

### 🥈 Recomendados (depois)

| Plugin | Por que |
|---|---|
| **Kanban** | Os 9 leads REAGENDAR como cards arrastáveis (To-do → Em conversa → Agendado) |
| **Calendar** | Lateral mostra dias com handoffs/incidentes |
| **Excalidraw** | Diagramas de fluxo direto no markdown |
| **Mind Map** | Visualizar pipeline ATENDE como mapa mental |

---

## 3. Após instalar Dataview — queries prontas

Cole no `00-INDEX.md`, no fim do arquivo:

````markdown
## 📅 Handoffs ordenados (automático)

```dataview
TABLE file.mtime AS "Última edição"
FROM ""
WHERE file.name STARTS_WITH "HANDOFF"
SORT file.mtime DESC
LIMIT 10
```

## 📌 Documentos editados nas últimas 24h

```dataview
TABLE file.mtime AS "Editado"
FROM ""
WHERE file.mtime >= date(today) - dur(1 day)
SORT file.mtime DESC
```

## 🏷 Por tag

```dataview
LIST FROM #operacao
```
````

> Pra Dataview funcionar, os arquivos precisam ter frontmatter YAML no topo
> (linhas `---` com `tags:`, `data:`, etc). [[CLAUDE]] e [[MAPA_OPORTUNIDADES_LEADS_FRIO]] já têm.

---

## 4. Frontmatter sugerido pros docs vivos

Adicione no TOPO de cada arquivo (entre `---`):

```yaml
---
title: "Nome do doc"
tags: [categoria1, categoria2]
data_criacao: 2026-06-04
data_revisao: 2026-06-04
status: ativo | pausado | arquivado
responsavel: Fábio
---
```

Tags padronizadas sugeridas:
- `#operacao` — playbooks operacionais
- `#bug` — incidente/bug
- `#fix` — fix técnico
- `#campanha` — campanha de reativação
- `#kpi` — métricas
- `#handoff` — handoff de sessão
- `#memoria` — memória persistente (CLAUDE.md)
- `#mapa` — mapas/categorizações

---

## 5. Atalhos úteis (Obsidian default)

| Atalho | Ação |
|---|---|
| `Cmd+O` | Abrir nota por nome |
| `Cmd+P` | Paleta de comandos (TUDO) |
| `Cmd+E` | Alternar edição/preview |
| `Cmd+Click` em link | Abrir em painel ao lado |
| `Cmd+,` | Settings |
| `Cmd+Shift+F` | Buscar em todo vault |
| `Cmd+G` | Visualizar grafo |

---

## 6. Sync entre Macs (opcional)

Como este vault é um **repositório Git** (já tem `.git`), basta:
- `git pull` antes de começar a editar
- `git commit -am "obsidian notes"` ao final
- `git push`

Outros Macs onde você clonar o repo terão o mesmo vault, com **histórico versionado**. O `.obsidian/` é commitado junto, então as configs se replicam.

---

## 7. O que NÃO commitar

Já está no `.gitignore`:
- `.obsidian/workspace.json` (layout local de cada Mac)
- `.obsidian/workspace-mobile.json`
- `.trash/`

Sugestão de adicionar ao `.gitignore` se ainda não tem:
```
.obsidian/workspace*.json
.obsidian/cache/
.obsidian/plugins/*/data.json
```

Isso evita conflito entre layouts/caches de Macs diferentes.

---

## Próximos passos sugeridos

- [ ] Instalar Obsidian + abrir vault
- [ ] Trust + instalar Dataview, Tasks, Templater
- [ ] Conferir que `00-INDEX` renderiza links e queries
- [ ] Adicionar frontmatter aos handoffs antigos (gradual)
- [ ] Configurar tema escuro se preferir (Settings → Appearance)
