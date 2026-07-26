import copy
import importlib.util
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("apply", ROOT / "apply.py")
apply = importlib.util.module_from_spec(spec)
spec.loader.exec_module(apply)


class ApplyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with (ROOT / "roles.config.json").open(encoding="utf-8") as fh:
            cls.config = json.load(fh)

    def test_current_config_and_all_specialists_validate(self):
        self.assertEqual(apply.validate(self.config), [])
        self.assertEqual(set(apply.SPECIALIST_KEYS), set(self.config["agents"]))
        self.assertEqual(self.config["roles"]["planner"]["model"], {"class": "fable", "id": "", "provider": "anthropic"})
        self.assertEqual(self.config["roles"]["builder"]["model"], {"class": "opus", "id": "", "provider": "anthropic"})
        fe = self.config["agents"]["fe-designer"]
        self.assertEqual(fe["displayName"], "FE-Designer")
        self.assertTrue(fe["autoSelectEligible"])
        self.assertEqual(fe["model"], {"class": "sonnet", "id": "", "provider": "anthropic"})
        workflow_audit = self.config["routing"]["postWorkflowAudit"]
        self.assertTrue(workflow_audit["enabled"])
        self.assertEqual(workflow_audit["model"], {"class": "sonnet", "id": "", "provider": "anthropic"})
        self.assertEqual(workflow_audit["thinking"], "medium")
        audit = self.config["agents"]["audit"]
        self.assertEqual(audit["displayName"], "Audit")
        # Deliberately not the builder's model: an audit should not be the same
        # model reviewing its own work.
        self.assertEqual(audit["model"], {"class": "fable", "id": "", "provider": "anthropic"})
        self.assertNotEqual(audit["model"]["class"], self.config["roles"]["builder"]["model"]["class"])
        self.assertEqual(audit["invocation"], "direct-call-only")
        self.assertFalse(audit["autoSelectEligible"])
        self.assertFalse(audit["canDelegate"])
        self.assertEqual(audit["delegateTo"], [])

    def test_every_configured_model_is_anthropic(self):
        """This machine no longer uses external models (2026-07-26)."""
        self.assertEqual(set(self.config["providers"]), {"anthropic"})
        models = [entry["model"] for entry in self.config["roles"].values()]
        models += [entry["model"] for entry in self.config["agents"].values()]
        models.append(self.config["routing"]["postWorkflowAudit"]["model"])
        for model in models:
            self.assertEqual(model["provider"], "anthropic", model)
            self.assertNotIn("/", model.get("class", ""), model)
            self.assertNotIn("/", model.get("id", ""), model)

    def test_no_pi_openrouter_overlay_remains(self):
        self.assertFalse((ROOT / "adapters" / "pi" / "roles.config.pi.json").exists())

    def test_rendering_a_non_anthropic_profile_fails_loudly(self):
        """The trap this replaced: Claude Code silently discards such a value."""
        with self.assertRaises(SystemExit):
            apply.claude_model_field("openai/gpt-5.6-sol", "openrouter")
        self.assertEqual(apply.claude_model_field("opus", "anthropic"), "opus")

    def test_direct_call_only_cannot_be_auto_selected(self):
        bad = copy.deepcopy(self.config)
        bad["agents"]["team-leader"]["autoSelectEligible"] = True
        errors = apply.validate(bad)
        self.assertTrue(any("direct-call-only" in error for error in errors))

    def test_router_config_and_info_sources_validate(self):
        self.assertEqual(self.config["routing"]["automaticSelection"]["status"], "confirmation-required")
        self.assertTrue(self.config["routing"]["automaticSelection"]["enabled"])
        self.assertEqual(self.config["routing"]["automaticSelection"]["fallback"], "runner")
        for key, entry in self.config["agents"].items():
            self.assertTrue(entry["infoSources"], key)
        disabled_audit = copy.deepcopy(self.config)
        disabled_audit["routing"]["postWorkflowAudit"] = {"enabled": False}
        self.assertEqual(apply.validate(disabled_audit), [])
        default_thinking_audit = copy.deepcopy(self.config)
        default_thinking_audit["routing"]["postWorkflowAudit"].pop("thinking")
        self.assertEqual(apply.validate(default_thinking_audit), [])
        bad_audit = copy.deepcopy(self.config)
        bad_audit["routing"]["postWorkflowAudit"]["thinking"] = "extreme"
        self.assertTrue(any("postWorkflowAudit.thinking" in error for error in apply.validate(bad_audit)))
        bad_threshold = copy.deepcopy(self.config)
        bad_threshold["routing"]["automaticSelection"]["threshold"] = 2
        self.assertTrue(any("threshold" in error for error in apply.validate(bad_threshold)))
        bad_fallback = copy.deepcopy(self.config)
        bad_fallback["routing"]["automaticSelection"]["fallback"] = "team-leader"
        self.assertTrue(any("fallback" in error for error in apply.validate(bad_fallback)))

    def test_knowledge_generation_preserves_lessons(self):
        with tempfile.TemporaryDirectory() as directory:
            original = apply.SCRIPT_DIR
            try:
                apply.SCRIPT_DIR = Path(directory)
                apply.install_knowledge(self.config, False)
                lesson = apply.SCRIPT_DIR / "agent-knowledge" / "runner" / "LESSONS.md"
                lesson.write_text(lesson.read_text(encoding="utf-8") + "\n- 2026-07-24 | test | preserve me | test\n", encoding="utf-8")
                apply.install_knowledge(self.config, False)
                self.assertIn("preserve me", lesson.read_text(encoding="utf-8"))
                for key in apply.ALL_AGENT_KEYS:
                    self.assertTrue((apply.SCRIPT_DIR / "agent-knowledge" / key / "PROFILE.md").is_file())
            finally:
                apply.SCRIPT_DIR = original

    def test_old_two_role_config_remains_valid(self):
        old = {key: copy.deepcopy(self.config[key]) for key in ("version", "roles", "providers")}
        old["version"] = 1
        old["roles"]["builder"].pop("canDelegate", None)
        old["roles"]["builder"].pop("delegateTo", None)
        self.assertEqual(apply.validate(old), [])

    def test_generic_output_documents_registry_and_caveat(self):
        output = apply.generic_block(self.config)
        for key in apply.SPECIALIST_KEYS:
            self.assertIn(f"`{key}`", output)
        self.assertIn("applicability recognition", output)
        self.assertIn("direct-call-only", output)

    def test_set_specialist_in_dry_run_does_not_write(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "roles.config.json"
            path.write_text(json.dumps(self.config), encoding="utf-8")
            args = type("Args", (), {"role": "l1-programmer", "model": "test-model", "cls": None, "pin_id": None, "provider": None})()
            changed = copy.deepcopy(self.config)
            apply.apply_set(changed, args)
            self.assertEqual(changed["agents"]["l1-programmer"]["model"]["class"], "test-model")
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["agents"]["l1-programmer"]["model"]["class"], "haiku")

    def test_claude_dry_run_has_all_specialist_targets_and_policy(self):
        output = io.StringIO()
        with redirect_stdout(output):
            apply.install_claude(self.config, Path("/tmp/agent-framework-test-home"), True)
        rendered = output.getvalue()
        for key in apply.SPECIALIST_KEYS:
            self.assertIn(f"/tmp/agent-framework-test-home/.claude/agents/{key}.md", rendered)
        self.assertIn("direct-call-only", rendered)
        self.assertIn("never self-invoke", rendered)
        self.assertIn("/route.md", rendered)
        self.assertIn("Knowledge directory", rendered)
        self.assertIn("/.claude/agents/workflow-audit.md", rendered)
        self.assertIn("enabled=true", rendered)
        self.assertIn("medium", rendered)
        self.assertIn("Light audit", rendered)

    def test_every_agent_gets_invoke_and_model_commands(self):
        output = io.StringIO()
        with redirect_stdout(output):
            apply.install_claude(self.config, Path("/tmp/agent-framework-test-home"), True)
        rendered = output.getvalue()
        base = "/tmp/agent-framework-test-home/.claude/commands"
        for key in apply.SPECIALIST_KEYS:
            self.assertIn(f"{base}/{key}.md", rendered)
            self.assertIn(f"{base}/{key}-model.md", rendered)
        self.assertIn(f"{base}/agent-catalog.md", rendered)
        # /agents is a Claude Code builtin; the catalog must not claim that name.
        self.assertNotIn(f"{base}/agents.md", rendered)

    def test_catalog_names_the_direct_call_only_profiles(self):
        output = io.StringIO()
        with redirect_stdout(output):
            apply.install_claude(self.config, Path("/tmp/agent-framework-test-home"), True)
        rendered = output.getvalue()
        self.assertIn("team-leader", rendered)
        self.assertIn("audit", rendered)
        self.assertNotIn("{{DIRECT_CALL_ONLY}}", rendered)

    def test_no_unsubstituted_placeholders_remain(self):
        output = io.StringIO()
        with redirect_stdout(output):
            apply.install_claude(self.config, Path("/tmp/agent-framework-test-home"), True)
        self.assertNotIn("{{", output.getvalue())

    def test_short_purpose_trims_without_breaking_a_word(self):
        long = "designs things; builds other things, and also reviews a third category of things"
        short = apply.short_purpose(long, limit=40)
        self.assertLessEqual(len(short), 41)
        self.assertNotIn("  ", short)
        self.assertEqual(apply.short_purpose("brief purpose"), "brief purpose")

    def test_delegation_note_reflects_configuration(self):
        may = apply.delegation_note({"can_delegate": True, "delegate_to": ["l1-programmer"]})
        self.assertIn("l1-programmer", may)
        self.assertIn("does not delegate", apply.delegation_note({"can_delegate": False}))

    def test_rendered_claude_agents_never_emit_a_provider_qualified_model(self):
        output = io.StringIO()
        with redirect_stdout(output):
            apply.install_claude(self.config, Path("/tmp/agent-framework-test-home"), True)
        for line in output.getvalue().splitlines():
            if line.startswith("model:"):
                value = line.split(":", 1)[1].strip()
                self.assertNotIn("/", value, f"unresolvable frontmatter model: {value}")


if __name__ == "__main__":
    unittest.main()
