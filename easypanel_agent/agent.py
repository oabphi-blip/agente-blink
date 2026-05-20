"""Loop do agente Claude com tool use sobre o Easypanel.

Usa o SDK oficial `anthropic` (mesma base usada pelo Claude Agent SDK) com o
padrão tool_use/tool_result, que é a forma idiomática de construir agentes
em Python que rodam standalone (sem depender do CLI do Claude Code).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from anthropic import Anthropic

from .client import EasypanelClient
from .tools import TOOL_SPECS, run_tool

log = logging.getLogger(__name__)


SYSTEM_PROMPT = """Você é um agente especialista em Easypanel falando português brasileiro.

Você gerencia uma instância Easypanel via API tRPC usando as tools disponíveis.

REGRAS DE OURO:
1. Para operações de leitura (listar, inspecionar, monitorar), aja direto sem pedir confirmação.
2. Para operações destrutivas ou irreversíveis (destroy_project, destroy_app, atualizar env, trocar imagem, deletar domínio), SEMPRE confirme com o usuário antes de executar. Mostre exatamente o que vai acontecer.
3. Quando o usuário pedir algo vago ("mostre tudo", "status geral"), use `list_projects_and_services` + `get_system_stats` em paralelo.
4. Quando precisar do estado atual de algo antes de modificar (ex: editar env preservando valores), chame `inspect_app` primeiro.
5. Para procedures que não têm tool dedicada, use `trpc_raw` — você tem acesso a centenas de procedures da API. Padrões importantes nesta versão (v2.30+):
   - Serviços: `services.app.*`, `services.postgres.*`, `services.redis.*`, `services.mysql.*`, `services.mariadb.*`, `services.mongo.*`, `services.compose.*`, `services.wordpress.*`, `services.box.*` (ex: `services.postgres.updateCredentials`, `services.app.updateBuild`).
   - Monitor: `monitorOld.*` (getSystemStats, getServiceStats, getStorageStats, getMonitorTableData, getAdvancedStats).
   - Domínios: `domains.*` (listDomains, createDomain, deleteDomain, updateDomain, setPrimaryDomain).
   - Outros úteis: `settings.*`, `users.*`, `actions.listActions` (histórico de jobs), `databaseBackups.*`, `mounts.*`, `ports.*`, `traefik.*`.
6. Quando uma operação demora (deploy, restart), informe o usuário que disparou e que ele pode acompanhar no painel.
7. Seja conciso: respostas curtas e diretas. Quando listar muitos itens, agrupe por projeto e use formatação mínima.
8. Erros da API são devolvidos como JSON `{"error": "..."}`. Explique em linguagem clara o que aconteceu e o que o usuário pode fazer.

CONTEXTO: o usuário se chama Fábio e administra a infraestrutura via este agente.
"""


@dataclass
class AgentConfig:
    anthropic_api_key: str
    easypanel_url: str
    easypanel_token: str
    model: str = "claude-sonnet-4-5"
    max_tokens: int = 4096
    max_iterations: int = 25
    system_prompt: str = SYSTEM_PROMPT


@dataclass
class Agent:
    """Agente conversacional com memória de turnos."""

    config: AgentConfig
    _anthropic: Anthropic = field(init=False)
    _easypanel: EasypanelClient = field(init=False)
    _messages: list[dict] = field(default_factory=list)

    def __post_init__(self):
        self._anthropic = Anthropic(api_key=self.config.anthropic_api_key)
        self._easypanel = EasypanelClient(
            base_url=self.config.easypanel_url, token=self.config.easypanel_token
        )

    # ------------------------------------------------------------------

    def reset(self):
        """Limpa o histórico da conversa."""
        self._messages.clear()

    def ask(self, user_message: str, on_event=None) -> str:
        """Envia uma mensagem do usuário e roda o loop até a resposta final.

        Args:
            user_message: texto digitado pelo usuário.
            on_event: callback opcional para eventos do loop. Recebe (tipo, dado):
                - ("tool_use", {"name", "input"})
                - ("tool_result", {"name", "result"})
                - ("text", "...")
        """
        self._messages.append({"role": "user", "content": user_message})

        final_text_parts: list[str] = []

        for _ in range(self.config.max_iterations):
            response = self._anthropic.messages.create(
                model=self.config.model,
                max_tokens=self.config.max_tokens,
                system=self.config.system_prompt,
                tools=TOOL_SPECS,
                messages=self._messages,
            )

            # Anexa a resposta do assistant ao histórico (formato content blocks)
            assistant_blocks = [block.model_dump() for block in response.content]
            self._messages.append({"role": "assistant", "content": assistant_blocks})

            # Coleta textos e tool_uses
            tool_uses = []
            for block in response.content:
                if block.type == "text":
                    final_text_parts.append(block.text)
                    if on_event:
                        on_event("text", block.text)
                elif block.type == "tool_use":
                    tool_uses.append(block)
                    if on_event:
                        on_event(
                            "tool_use",
                            {"name": block.name, "input": block.input},
                        )

            # Se Claude não pediu tools, terminamos.
            if response.stop_reason != "tool_use" or not tool_uses:
                break

            # Executa cada tool_use e devolve como user/tool_result
            tool_results = []
            for tu in tool_uses:
                result_text = run_tool(self._easypanel, tu.name, tu.input or {})
                if on_event:
                    on_event(
                        "tool_result", {"name": tu.name, "result": result_text}
                    )
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tu.id,
                        "content": result_text,
                    }
                )

            self._messages.append({"role": "user", "content": tool_results})

        return "\n".join(final_text_parts).strip()
