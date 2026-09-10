from __future__ import annotations

from dataclasses import dataclass

from .models import RunContext, Stage


@dataclass(slots=True)
class Evaluation:
    score: float
    dimensions: dict[str, float]


def evaluate(context: RunContext) -> Evaluation:
    qa = context.latest(Stage.QA)
    release = context.latest(Stage.RELEASE)
    # Analysis and correction are conditional failure-path stages, not mandatory
    # work that should reduce the score of a healthy run.
    expected = {Stage.PLANNING, Stage.ARCHITECTURE, Stage.GENERATION, Stage.EXECUTION, Stage.QA, Stage.RELEASE}
    completed = {item.stage for item in context.artifacts}
    dimensions = {
        "pipeline_completion": len(expected.intersection(completed)) / len(expected),
        "test_success": float(bool(qa and qa.data.get("passed"))),
        "deployment_safety": float(bool(release and release.data.get("human_approval_required"))),
    }
    return Evaluation(round(sum(dimensions.values()) / len(dimensions), 3), dimensions)
