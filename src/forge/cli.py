from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .models import Stage, Task
from .orchestrator import Orchestrator
from .providers import CommandCodeProvider, JsonPlanProvider


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a guardrailed agentic engineering workflow")
    parser.add_argument("requirement", help="The product or engineering requirement")
    parser.add_argument("--title", default="Engineering task")
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument("--test-command", default="python3 -m unittest discover -s tests")
    parser.add_argument("--accept", action="append", default=[], metavar="CRITERION", help="Acceptance criterion (repeatable)")
    parser.add_argument("--version", action="version", version="forge 0.4.0")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--plan", type=Path, help="JSON change plan to validate and propose")
    source.add_argument("--provider-command", help="Trusted provider command speaking Forge JSON over stdin/stdout")
    parser.add_argument("--provider-env", action="append", default=[], metavar="NAME",
                        help="Environment variable to pass to the provider (repeatable)")
    parser.add_argument("--provider-timeout", type=int, default=120, metavar="SECONDS")
    parser.add_argument("--approve-edits", action="store_true", help="Apply the supplied plan after validation")
    parser.add_argument("--resume", metavar="RUN_ID", help="Resume an existing checkpoint")
    args = parser.parse_args()
    if args.approve_edits and not (args.plan or args.provider_command):
        parser.error("--approve-edits requires --plan or --provider-command")
    if args.provider_env and not args.provider_command:
        parser.error("--provider-env requires --provider-command")
    if args.provider_timeout <= 0:
        parser.error("--provider-timeout must be positive")
    provider = JsonPlanProvider(args.plan) if args.plan else (
        CommandCodeProvider(args.provider_command, timeout=args.provider_timeout,
                            pass_env=tuple(args.provider_env)) if args.provider_command else None
    )
    context, evaluation = Orchestrator(
        args.workspace, args.test_command, provider=provider, approve_edits=args.approve_edits
    ).run(
        Task(args.title, args.requirement, args.accept), resume_id=args.resume
    )
    print(json.dumps({
        "run_id": context.run_id,
        "stages": [result.as_dict() for result in context.artifacts],
        "evaluation": {"score": evaluation.score, "dimensions": evaluation.dimensions},
    }, indent=2, default=str))
    qa = context.latest(Stage.QA)
    return 0 if qa and qa.data["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
