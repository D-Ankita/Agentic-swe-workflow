import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from forge.guardrails import ApprovalRequired, CommandPolicy, PolicyViolation
from forge.models import RunContext, Stage, Task
from forge.orchestrator import Orchestrator
from forge.retrieval import CodeRetriever
from forge.tools import Sandbox
from forge.providers import CommandCodeProvider, JsonPlanProvider
from forge.workspace import EditRejected, WorkspaceEditor


class PolicyTests(TestCase):
    def test_blocks_destructive_command(self):
        with self.assertRaises(PolicyViolation):
            CommandPolicy().check("rm -rf /")

    def test_deployment_requires_approval(self):
        with self.assertRaises(ApprovalRequired):
            CommandPolicy().check("kubectl apply -f production.yaml")
        CommandPolicy().check("kubectl apply -f production.yaml", approved=True)

    def test_sandbox_does_not_interpret_shell_operators(self):
        with TemporaryDirectory() as directory:
            marker = Path(directory) / "owned"
            result = Sandbox(Path(directory)).run(["python3", "-c", "import sys; print(sys.argv[1])", f";touch {marker}"])
            self.assertEqual(result.returncode, 0)
            self.assertFalse(marker.exists())

    def test_sandbox_rejects_non_allowlisted_executable(self):
        with TemporaryDirectory() as directory:
            with self.assertRaises(PolicyViolation):
                Sandbox(Path(directory)).run(["sh", "-c", "echo unsafe"])


class RetrievalTests(TestCase):
    def test_ranks_matching_source(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "payments.py").write_text("def refund_payment(): return 'refunded'", encoding="utf-8")
            (root / "weather.py").write_text("def forecast(): return 'sunny'", encoding="utf-8")
            hits = CodeRetriever(root).search("support payments refunds")
            self.assertEqual(hits[0].path, "payments.py")


class EditingTests(TestCase):
    def test_applies_approved_structured_plan(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            plan = root / "plan.json"
            plan.write_text(json.dumps({"summary": "Add greeting", "edits": [
                {"path": "hello.py", "action": "create", "content": "print('hello')\n"}
            ]}), encoding="utf-8")
            context, _ = Orchestrator(root, "python3 -c 'print(42)'", provider=JsonPlanProvider(plan),
                                      approve_edits=True).run(Task("Greeting", "Add greeting"))
            self.assertEqual((root / "hello.py").read_text(encoding="utf-8"), "print('hello')\n")
            self.assertEqual(context.latest(Stage.GENERATION).data["mode"], "applied")

    def test_unapproved_plan_checkpoints_before_execution_and_can_resume(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            plan = root / "plan.json"
            plan.write_text(json.dumps({"summary": "Create file", "edits": [
                {"path": "created.txt", "action": "create", "content": "safe"}
            ]}), encoding="utf-8")
            pending, _ = Orchestrator(root, provider=JsonPlanProvider(plan)).run(Task("Create", "Create file"))
            self.assertIsNone(pending.latest(Stage.EXECUTION))
            self.assertFalse((root / "created.txt").exists())
            resumed, _ = Orchestrator(root, "python3 -c 'print(42)'", provider=JsonPlanProvider(plan),
                                       approve_edits=True).run(pending.task, resume_id=pending.run_id)
            self.assertEqual((root / "created.txt").read_text(encoding="utf-8"), "safe")
            self.assertTrue(resumed.latest(Stage.QA).data["passed"])

    def test_rejects_traversal_and_stale_updates(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            editor = WorkspaceEditor(root)
            from forge.models import ChangeSet, FileEdit
            with self.assertRaises(EditRejected):
                editor.apply(ChangeSet("escape", [FileEdit("../outside", "create", "bad")]))
            (root / "file.txt").write_text("current", encoding="utf-8")
            with self.assertRaises(EditRejected):
                editor.apply(ChangeSet("stale", [FileEdit("file.txt", "update", "new", "0" * 64)]))
            with self.assertRaises(EditRejected):
                editor.apply(ChangeSet("unchecked", [FileEdit("file.txt", "delete")]))


class ProviderTests(TestCase):
    def test_external_provider_receives_context_and_returns_edits(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            script = root / "provider.py"
            script.write_text(
                "import json,sys\n"
                "request=json.load(sys.stdin)\n"
                "assert request['task']['title']=='Generated'\n"
                "assert 'response_schema' in request\n"
                "json.dump({'summary':'generated','edits':[{'path':'generated.py','action':'create','content':'VALUE = 42\\n'}]},sys.stdout)\n",
                encoding="utf-8",
            )
            provider = CommandCodeProvider(f"python3 {script}")
            context, _ = Orchestrator(root, "python3 -m py_compile generated.py", provider=provider,
                                      approve_edits=True).run(Task("Generated", "Generate module"))
            self.assertEqual((root / "generated.py").read_text(encoding="utf-8"), "VALUE = 42\n")
            self.assertTrue(context.latest(Stage.QA).data["passed"])

    def test_external_provider_gets_only_explicit_environment(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            script = root / "provider.py"
            script.write_text(
                "import json,os,sys\n"
                "json.load(sys.stdin)\n"
                "json.dump({'summary':os.environ.get('FORGE_TEST_TOKEN','missing'),'edits':[]},sys.stdout)\n",
                encoding="utf-8",
            )
            original = os.environ.get("FORGE_TEST_TOKEN")
            os.environ["FORGE_TEST_TOKEN"] = "present"
            try:
                hidden = CommandCodeProvider(f"python3 {script}").propose(
                    RunContext("run", Task("T", "D"), root)
                )
                passed = CommandCodeProvider(f"python3 {script}", pass_env=("FORGE_TEST_TOKEN",)).propose(
                    RunContext("run", Task("T", "D"), root)
                )
            finally:
                if original is None:
                    os.environ.pop("FORGE_TEST_TOKEN", None)
                else:
                    os.environ["FORGE_TEST_TOKEN"] = original
            self.assertEqual(hidden.summary, "missing")
            self.assertEqual(passed.summary, "present")


class WorkflowTests(TestCase):
    def test_successful_pipeline_reaches_guarded_release(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            context, evaluation = Orchestrator(root, "python3 -c 'print(42)'").run(Task("Demo", "Build a safe feature"))
            self.assertTrue(context.latest(Stage.QA).data["passed"])
            self.assertTrue(context.latest(Stage.RELEASE).data["human_approval_required"])
            self.assertEqual(evaluation.score, 1.0)
            self.assertTrue((root / ".forge" / "traces.jsonl").exists())

    def test_failure_is_analyzed_and_corrected(self):
        with TemporaryDirectory() as directory:
            context, _ = Orchestrator(Path(directory), "python3 -c 'raise SystemExit(2)'").run(Task("Demo", "Fail safely"))
            self.assertIsNotNone(context.latest(Stage.ANALYSIS))
            self.assertIsNotNone(context.latest(Stage.CORRECTION))
            self.assertFalse(context.latest(Stage.RELEASE).data["ready"])
