from __future__ import annotations

import uuid
from pathlib import Path

from .agents import (ArchitectureAgent, CorrectionAgent, ErrorAnalysisAgent, ExecutionAgent,
                     GenerationAgent, PlanningAgent, QAAgent, ReleaseAgent)
from .evaluation import Evaluation, evaluate
from .models import RunContext, Stage, Task
from .observability import JsonlTracer
from .providers import CodeProvider
from .retrieval import CodeRetriever
from .tools import Sandbox
from .state import RunStore
from .workspace import WorkspaceEditor


class Orchestrator:
    def __init__(self, workspace: Path, test_command: str = "python3 -m unittest discover -s tests",
                 *, provider: CodeProvider | None = None, approve_edits: bool = False):
        self.workspace = workspace.resolve()
        self.approve_edits = approve_edits
        self.tracer = JsonlTracer(self.workspace / ".forge" / "traces.jsonl")
        self.store = RunStore(self.workspace / ".forge" / "runs")
        self.agents = [
            PlanningAgent(), ArchitectureAgent(CodeRetriever(self.workspace)),
            GenerationAgent(provider, WorkspaceEditor(self.workspace), approved=approve_edits),
            ExecutionAgent(Sandbox(self.workspace), test_command), QAAgent(),
        ]

    def run(self, task: Task, *, resume_id: str | None = None) -> tuple[RunContext, Evaluation]:
        context = self.store.load(resume_id) if resume_id else RunContext(uuid.uuid4().hex[:12], task, self.workspace)
        context.workspace = self.workspace
        pending = context.latest(Stage.GENERATION)
        if resume_id and self.approve_edits and pending and pending.data.get("approval_required"):
            context.artifacts = [item for item in context.artifacts if item.stage != Stage.GENERATION]
        completed = {artifact.stage for artifact in context.artifacts}
        for agent in self.agents:
            if agent.stage not in completed:
                self._invoke(agent, context)
                if agent.stage == Stage.GENERATION and context.latest(Stage.GENERATION).data.get("approval_required"):
                    return context, evaluate(context)
        qa = context.latest(Stage.QA)
        if qa and not qa.data["passed"]:
            if Stage.ANALYSIS not in completed:
                self._invoke(ErrorAnalysisAgent(), context)
            corrected = Stage.CORRECTION not in completed
            if corrected:
                self._invoke(CorrectionAgent(), context)
                context.iteration += 1
                self.store.save(context)
        if Stage.RELEASE not in completed:
            self._invoke(ReleaseAgent(), context)
        return context, evaluate(context)

    def _invoke(self, agent: object, context: RunContext) -> None:
        stage = agent.stage
        with self.tracer.span(context.run_id, stage.value) as usage:
            result = agent.run(context)
            usage.update(cost_usd=result.cost_usd, input_tokens=result.input_tokens, output_tokens=result.output_tokens)
            context.artifacts.append(result)
            self.store.save(context)
