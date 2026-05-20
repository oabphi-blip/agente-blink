"""Definições de tools que o agente Claude pode invocar.

Cada tool é descrita no formato JSON-Schema esperado pela API da Anthropic
(parâmetro `tools` em messages.create). O dispatcher (`run_tool`) recebe o
nome e o input e chama o método correspondente do EasypanelClient.
"""

from __future__ import annotations

import json
from typing import Any

from .client import EasypanelClient, EasypanelError


# --------------------------------------------------------------------- specs

TOOL_SPECS: list[dict] = [
    {
        "name": "list_projects",
        "description": "Lista todos os projetos existentes no Easypanel.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "list_projects_and_services",
        "description": (
            "Lista todos os projetos juntamente com os serviços de cada um. "
            "Use para ter uma visão geral completa da infraestrutura."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "inspect_project",
        "description": "Retorna detalhes de um projeto específico (incluindo serviços).",
        "input_schema": {
            "type": "object",
            "properties": {
                "project_name": {"type": "string", "description": "Nome do projeto."}
            },
            "required": ["project_name"],
        },
    },
    {
        "name": "create_project",
        "description": "Cria um novo projeto vazio.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Nome do projeto (somente letras, números e hífens).",
                }
            },
            "required": ["name"],
        },
    },
    {
        "name": "destroy_project",
        "description": (
            "Destrói (deleta) um projeto e TODOS os serviços dentro dele. "
            "Operação irreversível — confirme com o usuário antes de chamar."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
    },
    {
        "name": "inspect_app",
        "description": (
            "Inspeciona um serviço do tipo 'app' (imagem Docker ou git). "
            "Retorna fonte, env, deploy, mounts, ports e URL de deploy."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "project_name": {"type": "string"},
                "service_name": {"type": "string"},
            },
            "required": ["project_name", "service_name"],
        },
    },
    {
        "name": "deploy_app",
        "description": "Faz o redeploy de um serviço app (puxa última imagem/commit e reinicia).",
        "input_schema": {
            "type": "object",
            "properties": {
                "project_name": {"type": "string"},
                "service_name": {"type": "string"},
            },
            "required": ["project_name", "service_name"],
        },
    },
    {
        "name": "start_app",
        "description": "Inicia um serviço app parado.",
        "input_schema": {
            "type": "object",
            "properties": {
                "project_name": {"type": "string"},
                "service_name": {"type": "string"},
            },
            "required": ["project_name", "service_name"],
        },
    },
    {
        "name": "stop_app",
        "description": "Para um serviço app em execução.",
        "input_schema": {
            "type": "object",
            "properties": {
                "project_name": {"type": "string"},
                "service_name": {"type": "string"},
            },
            "required": ["project_name", "service_name"],
        },
    },
    {
        "name": "restart_app",
        "description": "Reinicia um serviço app.",
        "input_schema": {
            "type": "object",
            "properties": {
                "project_name": {"type": "string"},
                "service_name": {"type": "string"},
            },
            "required": ["project_name", "service_name"],
        },
    },
    {
        "name": "destroy_app",
        "description": (
            "Destrói um serviço app. Operação irreversível — confirme antes."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "project_name": {"type": "string"},
                "service_name": {"type": "string"},
            },
            "required": ["project_name", "service_name"],
        },
    },
    {
        "name": "update_app_env",
        "description": (
            "Atualiza as variáveis de ambiente de um app. "
            "O parâmetro `env` deve ser uma string no formato KEY=value, uma por linha. "
            "Substitui completamente o env anterior — recupere o atual com inspect_app antes se quiser preservar valores."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "project_name": {"type": "string"},
                "service_name": {"type": "string"},
                "env": {
                    "type": "string",
                    "description": "Conteúdo do .env (KEY=value separado por \\n).",
                },
            },
            "required": ["project_name", "service_name", "env"],
        },
    },
    {
        "name": "update_app_source_image",
        "description": "Troca a imagem Docker de um serviço app (ex: 'n8nio/n8n:1.123.21').",
        "input_schema": {
            "type": "object",
            "properties": {
                "project_name": {"type": "string"},
                "service_name": {"type": "string"},
                "image": {"type": "string"},
            },
            "required": ["project_name", "service_name", "image"],
        },
    },
    {
        "name": "inspect_database",
        "description": (
            "Inspeciona um serviço de banco de dados (Postgres, MySQL, MariaDB, Mongo ou Redis)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "db_type": {
                    "type": "string",
                    "enum": ["postgres", "mysql", "mariadb", "mongo", "redis"],
                },
                "project_name": {"type": "string"},
                "service_name": {"type": "string"},
            },
            "required": ["db_type", "project_name", "service_name"],
        },
    },
    {
        "name": "list_domains",
        "description": "Lista os domínios de um serviço.",
        "input_schema": {
            "type": "object",
            "properties": {
                "project_name": {"type": "string"},
                "service_name": {"type": "string"},
            },
            "required": ["project_name", "service_name"],
        },
    },
    {
        "name": "create_domain",
        "description": "Adiciona um domínio a um serviço.",
        "input_schema": {
            "type": "object",
            "properties": {
                "project_name": {"type": "string"},
                "service_name": {"type": "string"},
                "host": {"type": "string", "description": "Ex: app.exemplo.com"},
                "https": {"type": "boolean", "default": True},
                "port": {"type": "integer", "default": 80},
                "path": {"type": "string", "default": "/"},
            },
            "required": ["project_name", "service_name", "host"],
        },
    },
    {
        "name": "get_system_stats",
        "description": "Estatísticas do servidor (CPU, memória, disco, rede).",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_service_stats",
        "description": "Estatísticas de uso de um serviço específico (CPU, memória).",
        "input_schema": {
            "type": "object",
            "properties": {
                "project_name": {"type": "string"},
                "service_name": {"type": "string"},
            },
            "required": ["project_name", "service_name"],
        },
    },
    {
        "name": "list_users",
        "description": "Lista usuários do painel Easypanel.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "list_certificates",
        "description": "Lista certificados SSL emitidos.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "list_docker_containers",
        "description": "Lista os containers Docker rodando para um projeto (opcionalmente filtrado por serviço).",
        "input_schema": {
            "type": "object",
            "properties": {
                "project_name": {"type": "string"},
                "service": {
                    "type": "string",
                    "description": "Nome do serviço para filtrar. Vazio = todos do projeto.",
                    "default": "",
                },
            },
            "required": ["project_name"],
        },
    },
    {
        "name": "trpc_raw",
        "description": (
            "Escape hatch: chama QUALQUER procedure tRPC do Easypanel pelo nome. "
            "Use quando nenhuma das outras tools couber. "
            "Method='GET' para queries (leitura), 'POST' para mutations (escrita)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "procedure": {
                    "type": "string",
                    "description": "Ex: 'postgres.inspectService', 'settings.getServerIp'",
                },
                "params": {
                    "type": "object",
                    "description": "Parâmetros da procedure (objeto JSON).",
                },
                "method": {"type": "string", "enum": ["GET", "POST"], "default": "GET"},
            },
            "required": ["procedure"],
        },
    },
]


# --------------------------------------------------------------------- dispatch

def _truncate(value: Any, limit: int = 6000) -> str:
    """Serializa para JSON e trunca para não estourar contexto do modelo."""
    try:
        text = json.dumps(value, ensure_ascii=False, indent=2, default=str)
    except (TypeError, ValueError):
        text = str(value)
    if len(text) > limit:
        text = text[:limit] + f"\n... [truncado, total {len(text)} chars]"
    return text


def run_tool(client: EasypanelClient, name: str, tool_input: dict) -> str:
    """Despacha a tool pelo nome e devolve o resultado serializado."""
    try:
        if name == "list_projects":
            result = client.list_projects()
        elif name == "list_projects_and_services":
            result = client.list_projects_and_services()
        elif name == "inspect_project":
            result = client.inspect_project(tool_input["project_name"])
        elif name == "create_project":
            result = client.create_project(tool_input["name"])
        elif name == "destroy_project":
            result = client.destroy_project(tool_input["name"])
        elif name == "inspect_app":
            result = client.inspect_app(
                tool_input["project_name"], tool_input["service_name"]
            )
        elif name == "deploy_app":
            result = client.deploy_app(
                tool_input["project_name"], tool_input["service_name"]
            )
        elif name == "start_app":
            result = client.start_app(
                tool_input["project_name"], tool_input["service_name"]
            )
        elif name == "stop_app":
            result = client.stop_app(
                tool_input["project_name"], tool_input["service_name"]
            )
        elif name == "restart_app":
            result = client.restart_app(
                tool_input["project_name"], tool_input["service_name"]
            )
        elif name == "destroy_app":
            result = client.destroy_app(
                tool_input["project_name"], tool_input["service_name"]
            )
        elif name == "update_app_env":
            result = client.update_app_env(
                tool_input["project_name"],
                tool_input["service_name"],
                tool_input["env"],
            )
        elif name == "update_app_source_image":
            result = client.update_app_source_image(
                tool_input["project_name"],
                tool_input["service_name"],
                tool_input["image"],
            )
        elif name == "inspect_database":
            result = client.inspect_database(
                tool_input["db_type"],
                tool_input["project_name"],
                tool_input["service_name"],
            )
        elif name == "list_domains":
            result = client.list_domains(
                tool_input["project_name"], tool_input["service_name"]
            )
        elif name == "create_domain":
            result = client.create_domain(
                tool_input["project_name"],
                tool_input["service_name"],
                tool_input["host"],
                tool_input.get("https", True),
                tool_input.get("port", 80),
                tool_input.get("path", "/"),
            )
        elif name == "get_system_stats":
            result = client.get_system_stats()
        elif name == "get_service_stats":
            result = client.get_service_stats(
                tool_input["project_name"], tool_input["service_name"]
            )
        elif name == "list_users":
            result = client.list_users()
        elif name == "list_certificates":
            result = client.list_certificates()
        elif name == "list_docker_containers":
            result = client.list_docker_containers(
                tool_input["project_name"], tool_input.get("service", "")
            )
        elif name == "trpc_raw":
            result = client.trpc(
                tool_input["procedure"],
                tool_input.get("params", {}),
                tool_input.get("method", "GET"),
            )
        else:
            return json.dumps({"error": f"Tool desconhecida: {name}"})

        return _truncate(result)

    except EasypanelError as e:
        return json.dumps(
            {"error": str(e), "code": e.code}, ensure_ascii=False
        )
    except KeyError as e:
        return json.dumps(
            {"error": f"parâmetro obrigatório ausente: {e}"}, ensure_ascii=False
        )
    except Exception as e:  # noqa: BLE001 — agente precisa ver o erro
        return json.dumps(
            {"error": f"{type(e).__name__}: {e}"}, ensure_ascii=False
        )
