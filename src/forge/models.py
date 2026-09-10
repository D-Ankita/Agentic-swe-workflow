from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal


class Stage(StrEnum):
    PLANNING = "planning"
    ARCHITECTURE = "architecture"
    GENERATION = "generation"
    EXECUTION = "execution"
    QA = "qa"
    ANALYSIS = "analysis"
    CORRECTION = "correction"
    RELEASE = "release"


@dataclass(slots=True)
class Task:
    title: str
    description: str
    acceptance_criteria: list[str] = field(default_factory=list)


@dataclass(slots=True)
class FileEdit:
    path: str
    action: Literal["create", "update", "delete"]
    content: str | None = None
    expected_sha256: str | None = None


@dataclass(slots=True)
class ChangeSet:
    summary: str
    edits: list[FileEdit] = field(default_factory=list)


@dataclass(slots=True)
class AgentResult:
    stage: Stage
    summary: str
    data: dict[str, Any] = field(default_factory=dict)
    cost_usd: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class RunContext:
    run_id: str
    task: Task
    workspace: Path
    artifacts: list[AgentResult] = field(default_factory=list)
    iteration: int = 0

    def latest(self, stage: Stage) -> AgentResult | None:
        return next((item for item in reversed(self.artifacts) if item.stage == stage), None)
