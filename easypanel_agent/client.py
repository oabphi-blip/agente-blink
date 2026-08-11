"""Cliente HTTP fino para a API tRPC do Easypanel.

A API do Easypanel expõe ~341 procedures em /api/trpc/<namespace>.<procedure>.
- QUERIES (leitura): GET /api/trpc/<proc>?input=<urlencoded JSON {"json": {...}}>
- MUTATIONS (escrita): POST /api/trpc/<proc> com body {"json": {...}}

Resposta de sucesso: {"result": {"data": {"json": <payload>}}}
Resposta de erro:    {"error":  {"json": {"message": "...", "code": -32xxx}}}

Esta classe abstrai esse formato e expõe métodos Pythonic para as operações
mais usadas, mais um escape-hatch (`trpc`) para qualquer procedure crua.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional
from urllib.parse import quote

import requests

log = logging.getLogger(__name__)


class EasypanelError(RuntimeError):
    """Erro retornado pela API do Easypanel."""

    def __init__(self, message: str, code: Optional[int] = None, raw: Optional[dict] = None):
        super().__init__(message)
        self.code = code
        self.raw = raw


class EasypanelClient:
    """Cliente para a API tRPC do Easypanel."""

    def __init__(self, base_url: str, token: str, timeout: int = 30):
        if not base_url:
            raise ValueError("base_url é obrigatório (ex: http://easypanel:3000)")
        if not token:
            raise ValueError("token é obrigatório")
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            }
        )

    # ------------------------------------------------------------------ raw

    def trpc(
        self,
        procedure: str,
        params: Optional[dict] = None,
        method: str = "GET",
    ) -> Any:
        """Chama uma procedure tRPC arbitrária e devolve o payload `.result.data.json`.

        Use `method="GET"` para queries de leitura e `method="POST"` para mutations.
        """
        url = f"{self.base_url}/api/trpc/{procedure}"
        payload = {"json": params or {}}

        if method.upper() == "GET":
            # tRPC embute o input na querystring como JSON urlencoded
            input_qs = quote(json.dumps(payload), safe="")
            resp = self._session.get(
                f"{url}?input={input_qs}", timeout=self.timeout
            )
        else:
            resp = self._session.post(url, json=payload, timeout=self.timeout)

        try:
            data = resp.json()
        except ValueError:
            raise EasypanelError(
                f"Resposta não-JSON da API ({resp.status_code}): {resp.text[:300]}"
            )

        if "error" in data:
            err = data["error"].get("json", {})
            raise EasypanelError(
                err.get("message", "Erro desconhecido"),
                code=err.get("code"),
                raw=data,
            )

        return data.get("result", {}).get("data", {}).get("json")

    # ----------------------------------------------------------- projetos

    def list_projects(self) -> list[dict]:
        return self.trpc("projects.listProjects") or []

    def list_projects_and_services(self) -> list[dict]:
        return self.trpc("projects.listProjectsAndServices") or []

    def inspect_project(self, project_name: str) -> dict:
        return self.trpc("projects.inspectProject", {"projectName": project_name})

    def create_project(self, name: str) -> dict:
        return self.trpc("projects.createProject", {"name": name}, method="POST")

    def destroy_project(self, name: str) -> dict:
        return self.trpc("projects.destroyProject", {"name": name}, method="POST")

    # ----------------------------------------------------------- app (services)
    # Procedures de serviço ficam sob services.<tipo>.* no Easypanel v2.30+

    def inspect_app(self, project_name: str, service_name: str) -> dict:
        return self.trpc(
            "services.app.inspectService",
            {"projectName": project_name, "serviceName": service_name},
        )

    def deploy_app(self, project_name: str, service_name: str) -> dict:
        return self.trpc(
            "services.app.deployService",
            {"projectName": project_name, "serviceName": service_name},
            method="POST",
        )

    def start_app(self, project_name: str, service_name: str) -> dict:
        return self.trpc(
            "services.app.startService",
            {"projectName": project_name, "serviceName": service_name},
            method="POST",
        )

    def stop_app(self, project_name: str, service_name: str) -> dict:
        return self.trpc(
            "services.app.stopService",
            {"projectName": project_name, "serviceName": service_name},
            method="POST",
        )

    def restart_app(self, project_name: str, service_name: str) -> dict:
        return self.trpc(
            "services.app.restartService",
            {"projectName": project_name, "serviceName": service_name},
            method="POST",
        )

    def destroy_app(self, project_name: str, service_name: str) -> dict:
        return self.trpc(
            "services.app.destroyService",
            {"projectName": project_name, "serviceName": service_name},
            method="POST",
        )

    def update_app_env(
        self, project_name: str, service_name: str, env: str
    ) -> dict:
        """Atualiza variáveis de ambiente do app (env no formato KEY=value separado por \\n)."""
        return self.trpc(
            "services.app.updateEnv",
            {"projectName": project_name, "serviceName": service_name, "env": env},
            method="POST",
        )

    def update_app_source_image(
        self, project_name: str, service_name: str, image: str
    ) -> dict:
        return self.trpc(
            "services.app.updateSourceImage",
            {
                "projectName": project_name,
                "serviceName": service_name,
                "image": image,
            },
            method="POST",
        )

    # ----------------------------------------------------------- bancos

    def inspect_database(
        self, db_type: str, project_name: str, service_name: str
    ) -> dict:
        """db_type: postgres | mysql | mariadb | mongo | redis"""
        return self.trpc(
            f"services.{db_type}.inspectService",
            {"projectName": project_name, "serviceName": service_name},
        )

    # ----------------------------------------------------------- domínios

    def list_domains(self, project_name: str, service_name: str) -> list[dict]:
        return self.trpc(
            "domains.listDomains",
            {"projectName": project_name, "serviceName": service_name},
        ) or []

    def create_domain(
        self,
        project_name: str,
        service_name: str,
        host: str,
        https: bool = True,
        port: int = 80,
        path: str = "/",
    ) -> dict:
        return self.trpc(
            "domains.createDomain",
            {
                "projectName": project_name,
                "serviceName": service_name,
                "host": host,
                "https": https,
                "port": port,
                "path": path,
            },
            method="POST",
        )

    # ----------------------------------------------------------- monitor
    # No Easypanel v2.30+ as procedures de monitor ficam sob monitorOld.*

    def get_system_stats(self) -> dict:
        return self.trpc("monitorOld.getSystemStats")

    def get_service_stats(self, project_name: str, service_name: str) -> dict:
        return self.trpc(
            "monitorOld.getServiceStats",
            {"projectName": project_name, "serviceName": service_name},
        )

    def get_storage_stats(self) -> list[dict]:
        return self.trpc("monitorOld.getStorageStats") or []

    def get_advanced_stats(self) -> dict:
        return self.trpc("monitorOld.getAdvancedStats")

    def get_monitor_table(self) -> list[dict]:
        return self.trpc("monitorOld.getMonitorTableData") or []

    # ----------------------------------------------------------- sistema

    def list_users(self) -> list[dict]:
        return self.trpc("users.listUsers") or []

    def list_certificates(self) -> list[dict]:
        return self.trpc("certificates.listCertificates") or []

    def get_server_ip(self) -> str | dict:
        return self.trpc("settings.getServerIp")

    def list_docker_containers(
        self, project_name: str, service: str = ""
    ) -> list[dict]:
        """Lista containers Docker; passe `service` vazio para todos do projeto."""
        return self.trpc(
            "projects.getDockerContainers",
            {"projectName": project_name, "service": service},
        ) or []
