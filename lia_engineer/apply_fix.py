"""Aplica FixProposal em produção: pytest local → git commit → git push.

Não toca em main direto. Cria branch `lia-engineer/fix-<bug_id>-<timestamp>`
e abre PR. Easypanel auto-deploya quando merge na main. O engineer_loop
decide se faz merge automático (após smoke OK) ou se escala humano.

Falhas de cada etapa são REPORTADAS no resultado pra notify_fn decidir
o que comunicar.
"""
from __future__ import annotations

import os
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .propose_fix import FixProposal


REPO_ROOT = Path(os.getenv(
    "LIA_ENGINEER_REPO_ROOT",
    "/Users/fabiophilipecostamartins/Documents/Claude/Projects/AGENTE IA BLINK",
))
GITHUB_USER = os.getenv("LIA_ENGINEER_GH_USER", "oabphi-blip")
GITHUB_TOKEN = os.getenv("LIA_ENGINEER_GH_TOKEN", "")


@dataclass
class ApplyResult:
    """Resultado da tentativa de aplicar um FixProposal."""

    push_ok: bool
    commit_sha: Optional[str] = None
    branch_name: Optional[str] = None
    pytest_ok: bool = False
    pytest_output: str = ""
    erro: str = ""


def aplicar_fix(proposta: FixProposal, repo: Path = REPO_ROOT) -> ApplyResult:
    """Aplica fix em branch isolada + push.

    Etapas:
        1. git checkout main && git pull (sincroniza)
        2. cria branch lia-engineer/fix-<id>-<ts>
        3. escreve arquivo_teste com pytest novo
        4. aplica diff (patch)
        5. roda pytest LOCAL — se falhar, aborta
        6. git add + commit + push branch
        7. (opcional) abre PR via GitHub API

    Returns:
        ApplyResult com push_ok, commit_sha, branch_name.
    """
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    branch = f"lia-engineer/fix-{proposta.bug_report.padrao_id}-{ts}"

    try:
        # 1) Sincronizar main
        _run(["git", "-C", str(repo), "checkout", "main"])
        _run(["git", "-C", str(repo), "pull", "origin", "main"])

        # 2) Criar branch
        _run(["git", "-C", str(repo), "checkout", "-b", branch])

        # 3) Escrever pytest novo
        teste_path = repo / proposta.arquivo_teste
        teste_path.parent.mkdir(parents=True, exist_ok=True)
        teste_path.write_text(proposta.teste_codigo, encoding="utf-8")

        # 4) Aplicar diff
        with tempfile.NamedTemporaryFile("w", suffix=".patch", delete=False) as f:
            f.write(proposta.diff_unified)
            patch_path = f.name
        try:
            _run(["git", "-C", str(repo), "apply", "--3way", patch_path])
        finally:
            os.unlink(patch_path)

        # 5) Rodar pytest LOCAL contra arquivo de teste novo + responder
        pytest_proc = subprocess.run(
            ["python3", "-m", "pytest", proposta.arquivo_teste, "-q"],
            cwd=str(repo), capture_output=True, text=True, timeout=300,
        )
        pytest_ok = pytest_proc.returncode == 0
        pytest_output = (pytest_proc.stdout + pytest_proc.stderr)[-2000:]

        if not pytest_ok:
            # Rollback branch
            _run(["git", "-C", str(repo), "reset", "--hard", "origin/main"])
            _run(["git", "-C", str(repo), "checkout", "main"])
            _run(["git", "-C", str(repo), "branch", "-D", branch])
            return ApplyResult(
                push_ok=False, pytest_ok=False, pytest_output=pytest_output,
                erro="pytest falhou — fix rejeitado", branch_name=branch,
            )

        # 6) Commit + push
        _run(["git", "-C", str(repo), "add", "-A"])
        _run(["git", "-C", str(repo), "commit", "-m", proposta.commit_message])
        # Pegar SHA
        sha = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            capture_output=True, text=True,
        ).stdout.strip()

        # Push usando token GH (se disponível)
        if GITHUB_TOKEN:
            push_url = f"https://{GITHUB_USER}:{GITHUB_TOKEN}@github.com/oabphi-blip/agente-blink.git"
            _run(["git", "-C", str(repo), "push", push_url, branch])
        else:
            _run(["git", "-C", str(repo), "push", "origin", branch])

        return ApplyResult(
            push_ok=True, commit_sha=sha, branch_name=branch,
            pytest_ok=True, pytest_output=pytest_output,
        )

    except subprocess.CalledProcessError as e:
        return ApplyResult(push_ok=False, erro=f"git: {e.stderr or e}", branch_name=branch)
    except Exception as e:
        return ApplyResult(push_ok=False, erro=f"{type(e).__name__}: {e}", branch_name=branch)


def merge_para_main(branch: str, repo: Path = REPO_ROOT) -> bool:
    """Faz fast-forward merge de branch fix → main + push. Só após smoke OK."""
    try:
        _run(["git", "-C", str(repo), "checkout", "main"])
        _run(["git", "-C", str(repo), "merge", "--ff-only", branch])
        if GITHUB_TOKEN:
            push_url = f"https://{GITHUB_USER}:{GITHUB_TOKEN}@github.com/oabphi-blip/agente-blink.git"
            _run(["git", "-C", str(repo), "push", push_url, "main"])
        else:
            _run(["git", "-C", str(repo), "push", "origin", "main"])
        return True
    except subprocess.CalledProcessError:
        return False


def rollback(commit_sha: str, repo: Path = REPO_ROOT) -> bool:
    """Reverte um commit específico na main + push.

    Usado quando fix passou pytest local mas falhou smoke em prod.
    """
    try:
        _run(["git", "-C", str(repo), "checkout", "main"])
        _run(["git", "-C", str(repo), "revert", "--no-edit", commit_sha])
        if GITHUB_TOKEN:
            push_url = f"https://{GITHUB_USER}:{GITHUB_TOKEN}@github.com/oabphi-blip/agente-blink.git"
            _run(["git", "-C", str(repo), "push", push_url, "main"])
        else:
            _run(["git", "-C", str(repo), "push", "origin", "main"])
        return True
    except subprocess.CalledProcessError:
        return False


def _run(cmd: list) -> subprocess.CompletedProcess:
    """Wrapper subprocess que levanta em falha. Não captura stdout em sucesso
    pra não esconder logs em produção."""
    return subprocess.run(cmd, check=True, capture_output=True, text=True)
