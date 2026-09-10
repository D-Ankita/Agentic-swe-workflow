from __future__ import annotations

from dataclasses import asdict
from typing import Protocol

from .models import AgentResult, RunContext, Stage
from .providers import CodeProvider, ProposalOnlyProvider
from .retrieval import CodeRetriever
from .tools import Sandbox
from .workspace import WorkspaceEditor


class Agent(Protocol):
    stage: Stage

    def run(self, context: RunContext) -> AgentResult: ...


class PlanningAgent:
    stage = Stage.PLANNING

    def run(self, context: RunContext) -> AgentResult:
        criteria = context.task.acceptance_criteria or ["Implementation satisfies the stated requirement", "Automated tests pass"]
        return AgentResult(self.stage, "Converted the requirement into an executable delivery plan", {
            "goal": context.task.description,
            "acceptance_criteria": criteria,
            "steps": ["retrieve relevant context", "implement the smallest safe change", "run quality gates", "prepare reviewed release"],
        })


class ArchitectureAgent:
    stage = Stage.ARCHITECTURE

    def __init__(self, retriever: CodeRetriever):
        self.retriever = retriever

    def run(self, context: RunContext) -> AgentResult:
        hits = self.retriever.search(context.task.description)
        return AgentResult(self.stage, f"Decomposed work with {len(hits)} relevant codebase contexts", {
            "components": ["domain change", "automated verification", "release notes"],
            "context": [{"path": hit.path, "score": round(hit.score, 2), "excerpt": hit.excerpt} for hit in hits],
            "risks": ["regression", "unsafe tool invocation", "insufficient test coverage"],
        })


class GenerationAgent:
    stage = Stage.GENERATION

    def __init__(self, provider: CodeProvider | None = None, editor: WorkspaceEditor | None = None, *, approved: bool = False):
        self.provider = provider or ProposalOnlyProvider()
        self.editor = editor
        self.approved = approved

    def run(self, context: RunContext) -> AgentResult:
        changes = self.provider.propose(context)
        applied = []
        if changes.edits and self.approved:
            if self.editor is None:
                raise RuntimeError("Approved edits require a workspace editor")
            applied = self.editor.apply(changes)
        return AgentResult(self.stage, "Applied approved change plan" if applied else "Produced a reviewable change proposal", {
            "proposal": changes.summary,
            "edits": [asdict(edit) for edit in changes.edits],
            "applied": applied,
            "approval_required": bool(changes.edits and not self.approved),
            "mode": "applied" if applied else "proposal-only",
        })


class ExecutionAgent:
    stage = Stage.EXECUTION

    def __init__(self, sandbox: Sandbox, command: str):
        self.sandbox, self.command = sandbox, command

    def run(self, context: RunContext) -> AgentResult:
        result = self.sandbox.run(self.command)
        return AgentResult(self.stage, "Sandbox command completed", {
            "command": result.command, "returncode": result.returncode,
            "stdout": result.stdout[-4000:], "stderr": result.stderr[-4000:],
        })


class QAAgent:
    stage = Stage.QA

    def run(self, context: RunContext) -> AgentResult:
        execution = context.latest(Stage.EXECUTION)
        passed = bool(execution and execution.data["returncode"] == 0)
        return AgentResult(self.stage, "Quality gate passed" if passed else "Quality gate failed", {
            "passed": passed,
            "checks": [{"name": "configured test command", "passed": passed}],
        })


class ErrorAnalysisAgent:
    stage = Stage.ANALYSIS

    def run(self, context: RunContext) -> AgentResult:
        execution = context.latest(Stage.EXECUTION)
        stderr = execution.data.get("stderr", "") if execution else "No execution result"
        return AgentResult(self.stage, "Diagnosed the failed quality gate", {
            "root_cause_hint": stderr[-1200:] or "Command returned a non-zero exit code without stderr",
            "retryable": context.iteration < 1,
        })


class CorrectionAgent:
    stage = Stage.CORRECTION

    def run(self, context: RunContext) -> AgentResult:
        return AgentResult(self.stage, "Prepared a bounded correction attempt", {
            "strategy": "Re-run after error analysis; provider integrations may apply a targeted patch here",
            "iteration": context.iteration + 1,
        })


class ReleaseAgent:
    stage = Stage.RELEASE

    def run(self, context: RunContext) -> AgentResult:
        qa = context.latest(Stage.QA)
        ready = bool(qa and qa.data["passed"])
        return AgentResult(self.stage, "Release candidate awaits human approval" if ready else "Release blocked", {
            "ready": ready, "human_approval_required": True, "action": "open_pull_request" if ready else "fix_quality_gate",
        })
