from __future__ import annotations

import shlex
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from .guardrails import CommandPolicy, PolicyViolation


@dataclass(slots=True)
class CommandResult:
    command: list[str]
    returncode: int
    stdout: str
    stderr: str


class Sandbox:
    """Runs bounded, non-shell commands in a fixed workspace after validation."""

    DEFAULT_EXECUTABLES = frozenset({
        "cargo", "go", "make", "mypy", "npm", "npx", "pnpm", "pyright",
        "pytest", "python", "python3", "ruff", "yarn",
    })

    def __init__(
        self,
        workspace: Path,
        policy: CommandPolicy | None = None,
        timeout: int = 120,
        allowed_executables: frozenset[str] | None = None,
    ):
        self.workspace = workspace.resolve()
        self.policy = policy or CommandPolicy()
        self.timeout = timeout
        self.allowed_executables = allowed_executables or self.DEFAULT_EXECUTABLES

    def run(self, command: str | Sequence[str], *, approved: bool = False) -> CommandResult:
        argv = shlex.split(command) if isinstance(command, str) else list(command)
        if not argv:
            raise ValueError("Command must not be empty")
        executable = Path(argv[0]).name
        if executable not in self.allowed_executables:
            raise PolicyViolation(f"Executable is not allowlisted: {executable}")
        self.policy.check(argv, approved=approved)
        completed = subprocess.run(
            argv,
            cwd=self.workspace,
            shell=False,
            text=True,
            capture_output=True,
            timeout=self.timeout,
            env={"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": "/tmp/forge-home"},
        )
        return CommandResult(argv, completed.returncode, completed.stdout, completed.stderr)
