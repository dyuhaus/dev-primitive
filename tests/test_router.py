import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("router", ROOT / "router.py")
router = importlib.util.module_from_spec(spec)
spec.loader.exec_module(router)


class RouterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = json.loads((ROOT / "roles.config.json").read_text(encoding="utf-8"))

    def assert_route(self, task, agent):
        decision = router.route(task, self.config)
        self.assertEqual(decision["selected"], agent, decision)
        self.assertEqual(decision["status"], "recommendation")
        self.assertIn("confidence", decision)
        self.assertIn("candidates", decision)
        self.assertNotIn("team-leader", [item["agent"] for item in decision["candidates"]])
        self.assertNotIn("audit", [item["agent"] for item in decision["candidates"]])

    def test_canonical_specialist_routes(self):
        self.assert_route("Update the Vault index and fix broken wikilinks", "librarian")
        self.assert_route("Update the README and API runbook with verified configuration", "tech-writer")
        self.assert_route("Write a launch email and proposal for customers", "prose-writer")
        self.assert_route("Implement a responsive accessible React component with keyboard support and CSS", "fe-designer")
        self.assert_route("Following this exact outline, add a small parser script and unit test", "l1-programmer")
        self.assert_route("Refactor the broker service architecture and analyze trade-offs", "planner")
        self.assert_route("Clean up routine service logs", "runner")

    def test_generic_implementation_enters_plan_then_build(self):
        decision = router.route("Implement authentication caching and tests", self.config)
        self.assertEqual(decision["selected"], "planner")
        self.assertIn("Planner must produce the plan before Builder", " ".join(decision["reasons"]))
        self.assertEqual(decision["candidates"][0]["agent"], "builder")

    def test_plan_before_build_can_be_disabled(self):
        config = copy.deepcopy(self.config)
        config["routing"]["planBeforeBuild"] = False
        decision = router.route("Implement authentication caching and tests", config)
        self.assertEqual(decision["selected"], "builder")

    def test_ambiguous_task_falls_back_to_runner(self):
        decision = router.route("Help with this thing", self.config)
        self.assertEqual(decision["selected"], "runner")
        self.assertTrue(decision["needs_clarification"])
        self.assertTrue(decision["questions"])

    def test_audit_is_explicit_only(self):
        decision = router.route("Audit and repair a stalled Pi agent routing process", self.config)
        self.assertNotEqual(decision["selected"], "audit")
        self.assertNotIn("audit", [item["agent"] for item in decision["candidates"]])

    def test_team_leader_is_impossible_to_auto_select(self):
        bad = copy.deepcopy(self.config)
        bad["agents"]["team-leader"]["autoSelectEligible"] = True
        bad["agents"]["team-leader"]["invocation"] = "default"
        decision = router.route("Coordinate multiple agents and workstreams for the website docs and launch email", bad)
        self.assertNotEqual(decision["selected"], "team-leader")
        self.assertNotIn("team-leader", [item["agent"] for item in decision["candidates"]])
        self.assertIn("explicit user invocation", " ".join(decision["reasons"]))

    def test_audit_has_hash_not_task_text(self):
        task = "secretish unique task text must not appear in an audit"
        with tempfile.TemporaryDirectory() as directory:
            cfg = copy.deepcopy(self.config)
            audit = Path(directory) / "audit.jsonl"
            cfg["routing"]["automaticSelection"]["audit"] = {"enabled": True, "path": str(audit)}
            router.route(task, cfg)
            record = json.loads(audit.read_text(encoding="utf-8"))
            self.assertIn("taskSha256", record)
            self.assertNotIn(task, audit.read_text(encoding="utf-8"))
            self.assertNotIn("task", record)


if __name__ == "__main__":
    unittest.main()
