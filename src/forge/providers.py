from __future__ import annotations

import json
import os
import shlex
import subprocess
from pathlib import Path
from typing import Protocol

from .models import ChangeSet, FileEdit, RunContext, Stage


class CodeProvider(Protocol):
    def propose(self, context: RunContext) -> ChangeSet: ...


class ProposalOnlyProvider:
    def propose(self, context: RunContext) -> ChangeSet:
        return ChangeSet(f"Implement '{context.task.title}' in focused edits")


class JsonPlanProvider:
    """Loads a human-reviewable, schema-checked change plan."""

    def __init__(self, path: Path):
        self.path = path

    def propose(self, context: RunContext) -> ChangeSet:
        return parse_change_set(self.path.read_text(encoding="utf-8"))


def parse_change_set(payload: str) -> ChangeSet:
    raw = json.loads(payload)
    if not isinstance(raw, dict) or not isinstance(raw.get("summary"), str):
        raise ValueError("Plan must contain a string 'summary'")
    edits = raw.get("edits", [])
    if not isinstance(edits, list):
        raise ValueError("Plan 'edits' must be a list")
    parsed: list[FileEdit] = []
    for index, edit in enumerate(edits):
        if not isinstance(edit, dict) or edit.get("action") not in {"create", "update", "delete"} or not isinstance(edit.get("path"), str):
            raise ValueError(f"Invalid edit at index {index}")
        content = edit.get("content")
        if edit["action"] != "delete" and not isinstance(content, str):
            raise ValueError(f"Edit {index} requires string content")
        parsed.append(FileEdit(edit["path"], edit["action"], content, edit.get("expected_sha256")))
    return ChangeSet(raw["summary"], parsed)


class CommandCodeProvider:
    """Calls a trusted external model gateway using JSON over stdin/stdout."""

    def __init__(self, command: str, *, timeout: int = 120, max_output_bytes: int = 1_000_000,
                 pass_env: tuple[str, ...] = ()):
        self.argv = shlex.split(command)
        if not self.argv:
            raise ValueError("Provider command must not be empty")
        self.timeout, self.max_output_bytes, self.pass_env = timeout, max_output_bytes, pass_env

    def propose(self, context: RunContext) -> ChangeSet:
        architecture = context.latest(Stage.ARCHITECTURE)
        request = json.dumps({
            "task": {"title": context.task.title, "description": context.task.description,
                     "acceptance_criteria": context.task.acceptance_criteria},
            "workspace": str(context.workspace),
            "artifacts": [item.as_dict() for item in context.artifacts],
            "architecture": architecture.data if architecture else {},
            "response_schema": {"summary": "string", "edits": [{"path": "string", "action": "create|update|delete",
                                                                      "content": "string|null", "expected_sha256": "string|null"}]},
        }, default=str)
        environment = {"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": "/tmp/forge-provider-home"}
        for name in self.pass_env:
            if not name.replace("_", "").isalnum() or not name.upper() == name:
                raise ValueError(f"Invalid environment variable name: {name}")
            if name in os.environ:
                environment[name] = os.environ[name]
        completed = subprocess.run(self.argv, cwd=context.workspace, input=request, text=True,
                                   capture_output=True, timeout=self.timeout, env=environment, shell=False)
        if completed.returncode:
            raise RuntimeError(f"Provider exited with {completed.returncode}: {completed.stderr[-2000:]}")
        if len(completed.stdout.encode()) > self.max_output_bytes:
            raise ValueError("Provider response exceeds output limit")
        return parse_change_set(completed.stdout)
