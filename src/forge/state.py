from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from .models import AgentResult, RunContext, Stage, Task


class RunStore:
    """Atomic JSON checkpoints for audit and process-level recovery."""

    def __init__(self, directory: Path):
        self.directory = directory

    def save(self, context: RunContext) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        payload = {
            "run_id": context.run_id, "workspace": str(context.workspace), "iteration": context.iteration,
            "task": {"title": context.task.title, "description": context.task.description,
                     "acceptance_criteria": context.task.acceptance_criteria},
            "artifacts": [item.as_dict() for item in context.artifacts],
        }
        fd, temporary = tempfile.mkstemp(dir=self.directory, prefix=f".{context.run_id}.")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(payload, stream, indent=2, default=str)
            os.replace(temporary, self.directory / f"{context.run_id}.json")
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def load(self, run_id: str) -> RunContext:
        if not run_id.isalnum():
            raise ValueError("Invalid run id")
        raw = json.loads((self.directory / f"{run_id}.json").read_text(encoding="utf-8"))
        context = RunContext(raw["run_id"], Task(**raw["task"]), Path(raw["workspace"]), iteration=raw["iteration"])
        context.artifacts = [AgentResult(Stage(item["stage"]), item["summary"], item["data"],
                                         item.get("cost_usd", 0.0), item.get("input_tokens", 0),
                                         item.get("output_tokens", 0)) for item in raw["artifacts"]]
        return context
