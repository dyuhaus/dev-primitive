import copy
import importlib.util
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("apply", ROOT / "apply.py")
apply = importlib.util.module_from_spec(spec)
spec.loader.exec_module(apply)

# A model class that is syntactically ordinary — no slash, no provider prefix —
# and that Claude Code cannot resolve. This is the exact shape that defeated the
# old guard: `apply.py set builder gpt-5.6-terra` never touched the provider
# field, so a provider-keyed check could not fire, and the "no slash in the name"
# heuristic in the test suite passed it too.
UNDISPATCHABLE_CLASS = "gpt-5.6-terra"
UNKNOWN_ANTHROPIC_CLASS = "unknown-anthropic-class"


def run_apply(*args, **kwargs):
    """Run apply.py as a subprocess so exit codes are observed, not inferred."""
    return subprocess.run(
        [sys.executable, str(ROOT / "apply.py"), *args],
        capture_output=True,
        text=True,
        **kwargs,
    )


class ApplyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with (ROOT / "roles.config.json").open(encoding="utf-8") as fh:
            cls.config = json.load(fh)
        # Claude rendering is still safety-tested, but the live registry is
        # intentionally OpenAI-only.  Keep a fully dispatchable Anthropic
        # fixture so these tests exercise rendering rather than failing at the
        # active-registry refusal boundary they are not about.
        cls.claude_config = copy.deepcopy(cls.config)
        cls.claude_config["providers"]["anthropic"] = {
            "type": "anthropic", "apiKeyEnv": "ANTHROPIC_API_KEY", "baseUrlEnv": ""
        }
        for key, entry in cls.claude_config["roles"].items():
            entry["model"].update({"class": "fable" if key == "planner" else "opus", "provider": "anthropic"})
        for key, entry in cls.claude_config["agents"].items():
            entry["model"].update({"class": "fable" if key in ("audit", "code-reviewer") else "sonnet", "provider": "anthropic"})
        cls.claude_config["routing"]["postWorkflowAudit"]["model"].update({"class": "sonnet", "provider": "anthropic"})
        cls.claude_config["routing"]["postWorkflowAudit"]["thinking"] = "medium"

    def test_current_config_and_all_specialists_validate(self):
        self.assertEqual(apply.validate(self.config), [])
        self.assertEqual(set(apply.SPECIALIST_KEYS), set(self.config["agents"]))
        self.assertEqual(self.config["roles"]["planner"]["model"], {"class": "gpt-5.6-sol", "id": "", "provider": "openai", "effort": "xhigh"})
        self.assertEqual(self.config["roles"]["builder"]["model"], {"class": "gpt-5.6-terra", "id": "", "provider": "openai", "effort": "xhigh"})
        fe = self.config["agents"]["fe-designer"]
        self.assertEqual(fe["displayName"], "FE-Designer")
        self.assertTrue(fe["autoSelectEligible"])
        self.assertEqual(fe["model"], {"class": "gpt-5.6-terra", "id": "", "provider": "openai", "effort": "xhigh"})
        workflow_audit = self.config["routing"]["postWorkflowAudit"]
        self.assertTrue(workflow_audit["enabled"])
        self.assertEqual(workflow_audit["model"], {"class": "gpt-5.6-sol", "id": "", "provider": "openai", "effort": "xhigh"})
        self.assertEqual(workflow_audit["thinking"], "xhigh")
        audit = self.config["agents"]["audit"]
        self.assertEqual(audit["displayName"], "Audit")
        # Deliberately not the builder's model: an audit should not be the same
        # model reviewing its own work.
        self.assertEqual(audit["model"], {"class": "gpt-5.6-sol", "id": "", "provider": "openai", "effort": "xhigh"})
        self.assertNotEqual(audit["model"]["class"], self.config["roles"]["builder"]["model"]["class"])
        self.assertEqual(audit["invocation"], "direct-call-only")
        self.assertFalse(audit["autoSelectEligible"])
        self.assertFalse(audit["canDelegate"])
        self.assertEqual(audit["delegateTo"], [])

    def test_every_model_declares_a_provider_that_exists(self):
        """Portability, not an Anthropic-only policy.

        The machine has been multi-provider since 2026-08-16, so asserting that
        every model is Anthropic asserts a policy that was superseded. What must
        hold is that every model names a declared provider and that the provider
        carries a wire protocol a consumer can map to a harness.
        """
        models = [entry["model"] for entry in self.config["roles"].values()]
        models += [entry["model"] for entry in self.config["agents"].values()]
        models.append(self.config["routing"]["postWorkflowAudit"]["model"])
        for model in models:
            self.assertIn(model["provider"], self.config["providers"], model)
            declared = self.config["providers"][model["provider"]]
            self.assertIn(declared["type"], apply.PROVIDER_TYPES, declared)

    def test_openai_models_require_effort_and_reject_anthropic_aliases(self):
        missing = copy.deepcopy(self.config)
        missing["roles"]["builder"]["model"].pop("effort")
        self.assertTrue(any("effort" in error for error in apply.validate(missing)))
        wrong_openai = copy.deepcopy(self.config)
        wrong_openai["agents"]["l1-programmer"]["model"]["class"] = "sonnet"
        self.assertTrue(any("Anthropic" in error for error in apply.validate(wrong_openai)))
        wrong_anthropic = copy.deepcopy(self.claude_config)
        wrong_anthropic["roles"]["builder"]["model"]["class"] = "gpt-5.6-terra"
        self.assertTrue(any("OpenAI" in error for error in apply.validate(wrong_anthropic)))

    def test_provider_keys_are_names_downstream_consumers_recognise(self):
        """Maestro maps a role to a harness by the provider's KEY, not its type.

        A DeepSeek endpoint keyed `dsh` validates cleanly and is then silently
        unroutable, so the recognised key names are part of the contract.
        """
        for key in self.config["providers"]:
            self.assertIn(key, apply.RECOGNISED_PROVIDER_KEYS, f"provider key '{key}' is not recognised")

    def test_no_pi_openrouter_overlay_remains(self):
        self.assertFalse((ROOT / "adapters" / "pi" / "roles.config.pi.json").exists())

    def test_the_model_guard_is_keyed_on_the_class_not_the_provider(self):
        """The trap this replaced: Claude Code silently discards such a value."""
        # Wrong provider type.
        with self.assertRaises(apply.AdapterUnsupported):
            apply.claude_model_field("openai/gpt-5.6-sol", "openai")
        # Right provider type, class Claude Code cannot resolve. This is the case
        # the old provider-keyed guard could never catch.
        with self.assertRaises(apply.AdapterUnsupported):
            apply.claude_model_field(UNDISPATCHABLE_CLASS, "anthropic")
        self.assertEqual(apply.claude_model_field("opus", "anthropic"), "opus")
        self.assertEqual(apply.claude_model_field("claude-opus-4-8", "anthropic"), "claude-opus-4-8")

    def test_undispatchable_model_on_any_profile_stops_the_claude_render(self):
        """planner, builder and the auditor used to bypass the guard entirely."""
        places = [
            ("roles", ("roles", "planner", "model")),
            ("roles", ("roles", "builder", "model")),
            ("agents", ("agents", "code-reviewer", "model")),
            ("routing", ("routing", "postWorkflowAudit", "model")),
        ]
        for label, path in places:
            with self.subTest(profile="/".join(path)):
                bad = copy.deepcopy(self.claude_config)
                node = bad
                for step in path[:-1]:
                    node = node[step]
                node[path[-1]]["class"] = UNKNOWN_ANTHROPIC_CLASS
                self.assertEqual(apply.validate(bad), [], "the config itself stays valid — that is the point")
                self.assertTrue(apply.claude_dispatch_report(bad), label)
                with self.assertRaises(apply.AdapterUnsupported):
                    apply.render_claude(bad, Path("/tmp/agent-framework-test-home"))

    def test_an_audit_with_no_model_configured_still_renders(self):
        """`postWorkflowAudit: {"enabled": false}` is valid and must stay renderable.

        Regression: routing the audit model through the dispatch guard rejected
        the absent-model case, so turning the auditor off broke the whole Claude
        render — a valid config the validator explicitly accepts.
        """
        for audit in ({"enabled": False}, {"enabled": False, "thinking": "low"}):
            with self.subTest(audit=audit):
                cfg = copy.deepcopy(self.claude_config)
                cfg["routing"]["postWorkflowAudit"] = audit
                self.assertEqual(apply.validate(cfg), [])
                rendered = apply.render_claude(cfg, Path("/tmp/agent-framework-test-home"))
                self.assertTrue(rendered)

    def test_apply_py_claude_exits_non_zero_for_a_non_anthropic_planner(self):
        """The regression test the audit asked for, asserted on the exit code."""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "roles.config.json"
            good = copy.deepcopy(self.claude_config)
            path.write_text(json.dumps(good), encoding="utf-8")
            ok = run_apply("claude", "--config", str(path), "--home", directory, "--dry-run")
            self.assertEqual(ok.returncode, 0, ok.stderr)

            bad = copy.deepcopy(self.claude_config)
            bad["roles"]["planner"]["model"] = {"class": UNDISPATCHABLE_CLASS, "id": "", "provider": "openai", "effort": "xhigh"}
            path.write_text(json.dumps(bad), encoding="utf-8")
            result = run_apply("claude", "--config", str(path), "--home", directory, "--dry-run")
            self.assertNotEqual(result.returncode, 0, "a non-Anthropic planner must fail the Claude render")
            self.assertIn("roles.planner", result.stderr)
            self.assertNotIn("model: " + UNDISPATCHABLE_CLASS, result.stdout)

    def test_all_skips_claude_but_still_regenerates_the_neutral_surfaces(self):
        """One undispatchable profile must not stop Codex/dsh/knowledge/generic."""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "roles.config.json"
            bad = copy.deepcopy(self.config)
            bad["providers"]["openai"] = {"type": "openai", "apiKeyEnv": "OPENAI_API_KEY", "baseUrlEnv": ""}
            bad["roles"]["planner"]["model"] = {"class": UNDISPATCHABLE_CLASS, "id": "", "provider": "openai", "effort": "xhigh"}
            path.write_text(json.dumps(bad), encoding="utf-8")
            result = run_apply("all", "--config", str(path), "--home", directory, "--dry-run")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("skipping the Claude Code adapter", result.stderr)
            self.assertIn("Specialist registry", result.stdout, "the generic block must still be emitted")

    def test_all_retirement_removes_only_exactly_marked_manifest_paths(self):
        """Both all entrypoints retire stale PB/profile files, never neighbours."""
        marker = apply.CLAUDE_REGISTRY_MARKER
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            owned = home / ".claude" / "agents" / "planner.md"
            route = home / ".claude" / "commands" / "route.md"
            catalog = home / ".claude" / "commands" / "agent-catalog.md"
            unrelated = home / ".claude" / "commands" / "manual.md"
            for command in (
                [sys.executable, str(ROOT / "apply.py"), "all", "--home", directory],
                [sys.executable, str(ROOT / "install_harness.py"), "all", "--home", directory],
            ):
                owned.parent.mkdir(parents=True, exist_ok=True)
                unrelated.parent.mkdir(parents=True, exist_ok=True)
                owned.write_text(marker + "\nowned\n", encoding="utf-8")
                route.write_text(apply.CLAUDE_GENERIC_MARKER + "\nroute\n", encoding="utf-8")
                catalog.write_text(apply.CLAUDE_GENERIC_MARKER + "\ncatalog\n", encoding="utf-8")
                unrelated.write_text(marker + "\nunrelated\n", encoding="utf-8")
                result = subprocess.run(command, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertFalse(owned.exists(), command)
                self.assertFalse(route.exists(), command)
                self.assertFalse(catalog.exists(), command)
                self.assertTrue(unrelated.exists(), command)

    def test_retirement_marker_matches_actual_claude_template_output(self):
        rendered = dict(apply.render_claude(self.claude_config, Path("/tmp/agent-framework-test-home")))
        planner = next(content for path, content in rendered.items() if path.name == "planner.md")
        self.assertIn(apply.CLAUDE_REGISTRY_MARKER, planner)

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
            args = type("Args", (), {"role": "l1-programmer", "model": "test-model", "cls": None, "pin_id": None, "provider": None, "effort": None})()
            changed = copy.deepcopy(self.config)
            apply.apply_set(changed, args)
            self.assertEqual(changed["agents"]["l1-programmer"]["model"]["class"], "test-model")
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["agents"]["l1-programmer"]["model"]["class"], "gpt-5.6-terra")

    def test_claude_dry_run_has_all_specialist_targets_and_policy(self):
        output = io.StringIO()
        with redirect_stdout(output):
            apply.install_claude(self.claude_config, Path("/tmp/agent-framework-test-home"), True)
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
            apply.install_claude(self.claude_config, Path("/tmp/agent-framework-test-home"), True)
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
            apply.install_claude(self.claude_config, Path("/tmp/agent-framework-test-home"), True)
        rendered = output.getvalue()
        self.assertIn("team-leader", rendered)
        self.assertIn("audit", rendered)
        self.assertNotIn("{{DIRECT_CALL_ONLY}}", rendered)

    def test_generated_commands_reference_nothing_that_was_removed(self):
        """A generated command must not instruct the user to run a deleted path."""
        output = io.StringIO()
        with redirect_stdout(output):
            apply.install_claude(self.claude_config, Path("/tmp/agent-framework-test-home"), True)
        rendered = output.getvalue()
        for gone in ("external_review.py", "roles.config.pi.json", "openrouter"):
            self.assertNotIn(gone, rendered, f"generated output still references {gone}")

    def test_no_unsubstituted_placeholders_remain(self):
        output = io.StringIO()
        with redirect_stdout(output):
            apply.install_claude(self.claude_config, Path("/tmp/agent-framework-test-home"), True)
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

    def test_claude_adapter_never_emits_a_model_it_cannot_dispatch(self):
        """The portable invariant, asserted on every rendered frontmatter line."""
        emitted = 0
        for _target, content in apply.render_claude(self.claude_config, Path("/tmp/agent-framework-test-home")):
            for line in content.splitlines():
                if line.startswith("model:"):
                    value = line.split(":", 1)[1].strip()
                    self.assertTrue(
                        apply.is_anthropic_model(value),
                        f"Claude Code cannot resolve this frontmatter model: {value}",
                    )
                    emitted += 1
        # A vacuous pass would be the failure mode here: assert the check ran.
        self.assertGreaterEqual(emitted, len(apply.ALL_AGENT_KEYS) + 1)

    # ----------------------------------------------------------------- #
    # `set` must not write before every adapter has rendered
    # ----------------------------------------------------------------- #

    def _require_yaml(self):
        """PyYAML, or skip. A real parser is the only honest check here."""
        try:
            import yaml
        except ImportError:  # pragma: no cover
            self.skipTest("PyYAML is not installed; the structural check still runs")
        return yaml

    def _scratch_registry(self, directory, cfg=None):
        path = Path(directory) / "roles.config.json"
        path.write_text(json.dumps(self.config if cfg is None else cfg, indent=2) + "\n", encoding="utf-8")
        return path

    def test_set_leaves_the_registry_untouched_when_an_adapter_refuses(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._scratch_registry(directory, self.claude_config)
            before = path.read_text(encoding="utf-8")
            apply.install_claude(self.claude_config, Path(directory), False)
            result = run_apply(
                "set", "builder", UNKNOWN_ANTHROPIC_CLASS,
                "--config", str(path), "--home", directory,
            )
            self.assertNotEqual(result.returncode, 0, result.stdout)
            self.assertEqual(path.read_text(encoding="utf-8"), before, "the registry was written before the guard ran")
            self.assertIn("nothing was written", result.stderr)

    def test_set_refreshes_every_installed_surface_not_only_claude(self):
        """A model change must reach every surface that is already installed."""
        with tempfile.TemporaryDirectory() as directory:
            path = self._scratch_registry(directory, self.claude_config)
            home = Path(directory)
            # Install the Claude fixture directly (the source-only installer
            # deliberately loads the live OpenAI registry), then install the
            # OpenAI-capable skill surfaces normally.
            apply.install_claude(self.claude_config, home, False)
            for target in ("codex", "dsh"):
                install = subprocess.run(
                    [sys.executable, str(ROOT / "install_harness.py"), target, "--home", directory],
                    capture_output=True, text=True,
                )
                self.assertEqual(install.returncode, 0, install.stderr)
            result = run_apply("set", "l1-programmer", "sonnet", "--config", str(path), "--home", directory)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["agents"]["l1-programmer"]["model"]["class"], "sonnet")
            self.assertIn("sonnet", (home / ".claude" / "agents" / "l1-programmer.md").read_text(encoding="utf-8"))
            for adapter in ("codex", "dsh"):
                skill = home / f".{adapter}" / "skills" / "agent-l1-programmer" / "SKILL.md"
                self.assertTrue(skill.is_file(), f"{adapter} surface was not refreshed")
                self.assertIn("`sonnet`", skill.read_text(encoding="utf-8"))

    def test_set_never_installs_a_harness_surface_that_was_not_there(self):
        """A routine model switch is not an install.

        `~/.dsh` existing means dsh is installed on the machine; it does not mean
        this primitive has ever written a profile into it. `set` used to render
        into every *present* harness, so changing one model class silently
        installed the Codex, dsh and Hermes surfaces — during a machine freeze
        whose whole point was that nothing new gets stood up.
        """
        with tempfile.TemporaryDirectory() as directory:
            path = self._scratch_registry(directory)
            home = Path(directory)
            for name in (".codex", ".dsh", ".hermes"):
                (home / name).mkdir()
            result = run_apply("set", "l1-programmer", "gpt-5.6-terra", "--config", str(path), "--home", directory)
            self.assertEqual(result.returncode, 0, result.stderr)
            # The registry still changed: refusing to create surfaces is not
            # refusing to do the job it was asked to do.
            self.assertEqual(
                json.loads(path.read_text(encoding="utf-8"))["agents"]["l1-programmer"]["model"]["class"], "gpt-5.6-terra"
            )
            for adapter in ("codex", "dsh", "hermes"):
                root = home / f".{adapter}" / "skills"
                self.assertFalse(root.exists(), f"set created a {adapter} surface that did not exist")
            self.assertFalse((home / ".claude").exists(), "set created a Claude Code surface that did not exist")
            self.assertIn("no generated surface installed for", result.stdout)

    def test_set_updates_an_installed_surface_without_adding_new_files(self):
        """Refreshing updates what is there; it does not grow the surface."""
        with tempfile.TemporaryDirectory() as directory:
            path = self._scratch_registry(directory)
            home = Path(directory)
            install = subprocess.run(
                [sys.executable, str(ROOT / "install_harness.py"), "dsh", "--home", directory],
                capture_output=True, text=True,
            )
            self.assertEqual(install.returncode, 0, install.stderr)
            root = home / ".dsh" / "skills"
            removed = root / "agent-audit"
            shutil.rmtree(removed)
            before = sorted(p.name for p in root.iterdir())
            result = run_apply("set", "librarian", "gpt-5.6-terra", "--config", str(path), "--home", directory)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("`gpt-5.6-terra`", (root / "agent-librarian" / "SKILL.md").read_text(encoding="utf-8"))
            self.assertEqual(sorted(p.name for p in root.iterdir()), before)
            self.assertFalse(removed.exists(), "refresh re-created a file the operator had removed")

    def test_set_claims_validation_only_where_validation_happened(self):
        """The printed assurance has to match what actually ran.

        Only Claude Code resolves a `model:` field, so only its adapter can
        reject a model class. `set` used to print "Checked against installed
        adapters: claude, codex, dsh" — naming two adapters that are structurally
        incapable of objecting to a model.
        """
        with tempfile.TemporaryDirectory() as directory:
            path = self._scratch_registry(directory)
            home = Path(directory)
            for name in (".codex", ".dsh"):
                (home / name).mkdir()
            result = run_apply("set", "librarian", "gpt-5.6-terra", "--config", str(path), "--home", directory)
            self.assertEqual(result.returncode, 0, result.stderr)
            validated = [line for line in result.stdout.splitlines() if line.startswith("Model class validated by:")]
            self.assertEqual(len(validated), 1, result.stdout)
            self.assertIn("nothing", validated[0])
            for adapter in ("codex", "dsh"):
                self.assertNotIn(adapter, validated[0], "an adapter that cannot object was named as a validator")

            # A manual or empty ~/.claude tree is not a generated adapter.
            (home / ".claude").mkdir()
            result = run_apply("set", "librarian", "gpt-5.6-sol", "--config", str(path), "--home", directory)
            self.assertEqual(result.returncode, 0, result.stderr)
            validated = [line for line in result.stdout.splitlines() if line.startswith("Model class validated by:")]
            self.assertIn("nothing", validated[0])
            self.assertFalse((home / ".claude" / "agents").exists())

    def test_set_ignores_unmarked_manual_claude_profiles(self):
        """Manual ~/.claude agents neither veto a change nor get rewritten."""
        with tempfile.TemporaryDirectory() as directory:
            path = self._scratch_registry(directory)
            home = Path(directory)
            planner = home / ".claude" / "agents" / "planner.md"
            builder = home / ".claude" / "agents" / "builder.md"
            planner.parent.mkdir(parents=True)
            planner.write_text("# Manual planner\n", encoding="utf-8")
            builder.write_text("# Manual builder\n", encoding="utf-8")

            result = run_apply("set", "librarian", "gpt-5.6-sol", "--config", str(path), "--home", directory)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Model class validated by: nothing", result.stdout)
            self.assertEqual(planner.read_text(encoding="utf-8"), "# Manual planner\n")
            self.assertEqual(builder.read_text(encoding="utf-8"), "# Manual builder\n")
            self.assertFalse((home / ".claude" / "commands").exists())

    def test_set_effort_updates_the_registry_and_rejects_invalid_values(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._scratch_registry(directory)
            result = run_apply("set", "builder", "--effort", "high", "--no-apply", "--config", str(path), "--home", directory)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["roles"]["builder"]["model"]["effort"], "high")
            invalid = run_apply("set", "builder", "--effort", "invalid", "--no-apply", "--config", str(path), "--home", directory)
            self.assertNotEqual(invalid.returncode, 0)

    # ----------------------------------------------------------------- #
    # Codex / dsh / Hermes surfaces
    # ----------------------------------------------------------------- #

    def test_every_skill_adapter_covers_roles_specialists_and_the_reviewer(self):
        for adapter in ("codex", "dsh", "hermes"):
            with self.subTest(adapter=adapter):
                rendered = dict(apply.render_harness_skills(self.config, Path("/tmp/agent-framework-test-home"), adapter))
                names = {path.parent.name for path in rendered}
                for key in apply.ALL_AGENT_KEYS:
                    self.assertIn(f"agent-{key}", names, f"{adapter} is missing agent-{key}")
                # The Hermes installer iterated only the specialists map, so the
                # PB core could never appear and the mandatory reviewer was absent.
                self.assertIn("agent-planner", names)
                self.assertIn("agent-builder", names)
                self.assertIn("agent-code-reviewer", names)
                self.assertIn("agent-framework", names)
                for path, content in rendered.items():
                    self.assertNotIn("{{", content, f"unsubstituted placeholder in {path}")
                    self.assertTrue(content.startswith("---\nname: "), path)

    def test_skill_adapters_state_honestly_how_they_route_the_model(self):
        rendered = dict(apply.render_harness_skills(self.config, Path("/tmp/agent-framework-test-home"), "codex"))
        planner = next(c for p, c in rendered.items() if p.parent.name == "agent-planner")
        self.assertIn("current Codex session model", planner)
        self.assertIn('model: "gpt-5.6-sol"', planner)
        self.assertIn('reasoning_effort: "xhigh"', planner)
        self.assertIn("substantive automated", planner)
        self.assertIn("explicitly confirmed", planner)
        for adapter in ("dsh", "hermes"):
            with self.subTest(adapter=adapter):
                rendered = dict(apply.render_harness_skills(self.config, Path("/tmp/agent-framework-test-home"), adapter))
                planner = next(c for p, c in rendered.items() if p.parent.name == "agent-planner")
                self.assertIn("cannot dispatch", planner)
                self.assertIn("runs on", planner)
                # And it must not present the configured model as a frontmatter
                # model field the harness would silently discard.
                for path, content in rendered.items():
                    frontmatter = content.split("---", 2)[1]
                    self.assertNotIn("\nmodel:", frontmatter, f"{path} emits an undispatchable model field")

    # ----------------------------------------------------------------- #
    # Generated frontmatter must survive a real YAML parse
    # ----------------------------------------------------------------- #
    # Measured, not assumed: with the description interpolated raw, dsh's own
    # filesystem skill provider loaded 10 of the 14 rendered skills and dropped
    # agent-planner, agent-builder, agent-fe-designer and agent-code-reviewer —
    # both PB roles and the mandatory reviewer — logging a warning and nothing
    # more. Four of the eleven registry purposes contain a colon-and-space.

    # A purpose built to break every naive quoting scheme at once.
    HOSTILE_PURPOSE = (
        'review a diff: correctness, "quoted" claims, back\\slashes, '
        "a trailing colon: and a #hash — all in one line"
    )

    def _skill_frontmatter(self, cfg, adapter):
        """{skill name: raw frontmatter block} for one rendered adapter surface."""
        rendered = apply.render_harness_skills(cfg, Path("/tmp/agent-framework-test-home"), adapter)
        return {path.parent.name: apply.frontmatter_of(content) for path, content in rendered}

    def test_purposes_in_the_live_registry_contain_the_shape_that_broke_this(self):
        """A vacuous pass would be the real failure mode of the tests below."""
        offenders = [k for k in apply.ALL_AGENT_KEYS if ": " in apply.role_view(self.config, k)["purpose"]]
        self.assertTrue(offenders, "no live purpose contains ': ' — the YAML tests below prove nothing")

    def test_generated_skill_frontmatter_parses_as_yaml(self):
        yaml = self._require_yaml()
        for adapter in ("codex", "dsh", "hermes"):
            for name, block in self._skill_frontmatter(self.config, adapter).items():
                with self.subTest(adapter=adapter, skill=name):
                    data = yaml.safe_load(block)
                    self.assertIsInstance(data, dict, f"{adapter}/{name} frontmatter is not a mapping")
                    self.assertEqual(data["name"], name)
                    self.assertIsInstance(data["description"], str)
                    self.assertTrue(data["description"].strip())

    def test_a_purpose_with_a_colon_round_trips_through_a_real_yaml_parse(self):
        """The exact registry shape that made four skills disappear."""
        yaml = self._require_yaml()
        cfg = copy.deepcopy(self.config)
        cfg["agents"]["code-reviewer"]["purpose"] = self.HOSTILE_PURPOSE
        cfg["roles"]["planner"]["purpose"] = "plan: think first, then hand over"
        self.assertEqual(apply.validate(cfg), [])
        for adapter in ("codex", "dsh", "hermes"):
            blocks = self._skill_frontmatter(cfg, adapter)
            with self.subTest(adapter=adapter):
                reviewer = yaml.safe_load(blocks["agent-code-reviewer"])
                self.assertEqual(reviewer["description"], self.HOSTILE_PURPOSE)
                planner = yaml.safe_load(blocks["agent-planner"])
                self.assertEqual(planner["description"], "plan: think first, then hand over")

    def test_the_generator_refuses_to_write_unparseable_frontmatter(self):
        """The stdlib backstop, so a template edit cannot reintroduce this.

        Runs with or without PyYAML: `check_frontmatter` has to catch an
        unquoted free-text scalar structurally, because a harness that drops the
        skill says nothing and the operator has no way to notice.
        """
        with self.assertRaises(SystemExit):
            apply.check_frontmatter(
                Path("SKILL.md"),
                "---\nname: agent-x\ndescription: plan: architecture and design\n---\nbody\n",
            )
        # And the shape it must keep accepting.
        apply.check_frontmatter(
            Path("SKILL.md"),
            '---\nname: agent-x\ndescription: "plan: architecture and design"\n---\nbody\n',
        )

    def test_yaml_scalar_quotes_every_value_it_is_given(self):
        for raw in ("plain", "has: colon", 'has "quotes"', "back\\slash", "", "- leading dash", "#hash"):
            with self.subTest(raw=raw):
                quoted = apply.yaml_scalar(raw)
                self.assertTrue(quoted.startswith('"') and quoted.endswith('"'), quoted)
                yaml = self._require_yaml()
                self.assertEqual(yaml.safe_load(f"v: {quoted}")["v"], raw)

    # ----------------------------------------------------------------- #
    # The same guarantee, for a Claude-specific adapter fixture
    # ----------------------------------------------------------------- #
    # The three skill adapters were covered above from the first version of this
    # fix. The Claude Code adapter was not: `render_claude()` never called
    # `check_frontmatter()`, and
    # `agent-invoke.md.tmpl` / `agent-model.md.tmpl` interpolated a registry
    # purpose into an unquoted plain scalar — the exact shape that cost dsh four
    # skills. `apply.py claude` exited 0 and wrote a slash command whose
    # frontmatter raises "mapping values are not allowed here".

    CLAUDE_COLON_PURPOSE = "triage: route work to the right place"

    def _claude_frontmatter(self, cfg):
        """{"<dir>/<file>": raw frontmatter block} for the whole Claude surface."""
        rendered = apply.render_claude(cfg, Path("/tmp/agent-framework-test-home"))
        return {f"{path.parent.name}/{path.name}": apply.frontmatter_of(content) for path, content in rendered}

    def test_the_claude_adapter_puts_a_registry_purpose_in_frontmatter(self):
        """A vacuous pass would be the real failure mode of the tests below."""
        blocks = self._claude_frontmatter(self.claude_config)
        self.assertIn("commands/runner.md", blocks)
        purpose = apply.short_purpose(apply.role_view(self.claude_config, "runner")["purpose"])
        self.assertIn(purpose, blocks["commands/runner.md"])

    def test_generated_claude_frontmatter_parses_as_yaml(self):
        yaml = self._require_yaml()
        blocks = self._claude_frontmatter(self.claude_config)
        self.assertGreaterEqual(len(blocks), 3 * len(apply.ALL_AGENT_KEYS))
        for name, block in blocks.items():
            with self.subTest(file=name):
                data = yaml.safe_load(block)
                self.assertIsInstance(data, dict, f"{name} frontmatter is not a mapping")
                self.assertIsInstance(data.get("description"), str)
                self.assertTrue(data["description"].strip())
                if name.startswith("agents/"):
                    self.assertTrue(data.get("name"))
                    self.assertTrue(data.get("model"))

    def test_a_purpose_with_a_colon_round_trips_through_the_claude_adapter(self):
        """The reviewer's reproduction, as a test.

        `triage: route work to the right place` is under the 90-character
        `short_purpose` limit and passes `apply.py validate`, so nothing before
        the render objects to it. Rendered raw it made `.claude/commands/
        runner.md` unloadable.
        """
        yaml = self._require_yaml()
        cfg = copy.deepcopy(self.claude_config)
        cfg["agents"]["runner"]["purpose"] = self.CLAUDE_COLON_PURPOSE
        cfg["agents"]["code-reviewer"]["purpose"] = self.HOSTILE_PURPOSE
        self.assertEqual(apply.validate(cfg), [])
        blocks = self._claude_frontmatter(cfg)
        runner = yaml.safe_load(blocks["commands/runner.md"])
        self.assertIn(self.CLAUDE_COLON_PURPOSE, runner["description"])
        self.assertEqual(runner["argument-hint"], "<task>, or blank to describe the agent")
        model_cmd = yaml.safe_load(blocks["commands/runner-model.md"])
        self.assertIn("apply.py set runner", model_cmd["description"])
        reviewer = yaml.safe_load(blocks["commands/code-reviewer.md"])
        self.assertIn('review a diff: correctness, "quoted" claims', reviewer["description"])

    def test_the_claude_adapter_refuses_to_write_unparseable_frontmatter(self):
        """`check_frontmatter` really does run on the Claude renders.

        A purpose carrying a newline escapes the `description: >-` block scalar
        in `agent.md.tmpl` and comes back as document structure, so the injected
        `model:` silently overrides the configured one. Duplicate keys are legal
        YAML — PyYAML keeps the last — so only the structural check catches it.
        `render_claude` writes nothing, so the build stops before the live
        `~/.claude` surface is touched.
        """
        for injected in ("triage work\nmodel: opus", "triage work\ntools: Bash"):
            cfg = copy.deepcopy(self.claude_config)
            cfg["agents"]["runner"]["purpose"] = injected
            self.assertEqual(apply.validate(cfg), [], "validate cannot see this; the render must")
            with self.subTest(injected=injected), self.assertRaises(SystemExit):
                apply.render_claude(cfg, Path("/tmp/agent-framework-test-home"))

    def test_check_frontmatter_accepts_the_shapes_the_claude_adapter_emits(self):
        """Block scalars and a bare `tools:` list are idiomatic and must pass."""
        agent = (
            "---\nname: runner\ndescription: >-\n  Runner specialist — sonnet.\n"
            "  everyday tasks: and maintenance\nmodel: sonnet\n"
            "tools: Read, Grep, Glob, Bash, Edit, Write, TodoWrite\n---\nbody\n"
        )
        apply.check_frontmatter(Path("runner.md"), agent)
        # A command has no `name:`, and saying it must have one would fail every
        # slash command the adapter emits.
        apply.check_frontmatter(
            Path("runner.md"), '---\ndescription: "x"\n---\nbody\n', required=("description",)
        )
        with self.assertRaises(SystemExit):
            apply.check_frontmatter(Path("runner.md"), '---\ndescription: "x"\n---\nbody\n')
        # Free prose with commas is still not a bare token list.
        with self.assertRaises(SystemExit):
            apply.check_frontmatter(
                Path("runner.md"), "---\nname: r\ndescription: everyday tasks, and maintenance: really\n---\nb\n"
            )
        # A block scalar with no indented body has already lost its content.
        with self.assertRaises(SystemExit):
            apply.check_frontmatter(Path("runner.md"), "---\nname: r\ndescription: >-\nmodel: sonnet\n---\nb\n")

    def test_every_skill_adapter_renders_the_same_fourteen_skills(self):
        """The count is 14 TOTAL per adapter: 11 profiles + 3 shared skills.

        Not "14 agent-* skills plus framework/pb/route" — that reading inflates
        the surface by three and hides a real loss behind a number that already
        looked too big.
        """
        expected = len(apply.ALL_AGENT_KEYS) + 3
        self.assertEqual(len(apply.ALL_AGENT_KEYS), 11)
        for adapter in ("codex", "dsh", "hermes"):
            rendered = apply.render_harness_skills(self.config, Path("/tmp/agent-framework-test-home"), adapter)
            self.assertEqual(len(rendered), expected, adapter)
            self.assertEqual(len({path for path, _ in rendered}), expected, f"{adapter} renders a duplicate target")

    def test_the_model_routing_note_is_honest_for_codex_delegation(self):
        for adapter in ("dsh", "hermes"):
            for key in apply.ALL_AGENT_KEYS:
                note = apply.model_routing_note(apply.role_view(self.config, key), adapter)
                with self.subTest(adapter=adapter, agent=key):
                    self.assertNotRegex(note, r"\ba (anthropic|openai|openrouter|undeclared)\b")
        note = apply.model_routing_note(apply.role_view(self.config, "planner"), "codex")
        self.assertIn("current Codex session model", note)
        self.assertIn('model: "gpt-5.6-sol"', note)
        self.assertIn('reasoning_effort: "xhigh"', note)

    def test_codex_pb_spawns_the_post_workflow_audit_child(self):
        rendered = apply.render_harness_skills(
            self.config, Path("/tmp/agent-framework-test-home"), "codex")
        pb = next(text for path, text in rendered if path.parent.name == "agent-pb")
        self.assertIn('separate **read-only** child', pb)
        self.assertIn('model: "gpt-5.6-sol"', pb)
        self.assertIn('reasoning_effort: "xhigh"', pb)
        self.assertIn('orchestrator must not', pb)

    def test_apply_py_does_not_mirror_the_shared_skill_roots(self):
        """The two entry points differ, and the difference is deliberate.

        `install_harness.py` mirrors ~/skills into each harness; `apply.py` never
        does, at any action. Asserted because the claim that both do it was made
        and believed once already.
        """
        source = ROOT / "apply.py"
        text = source.read_text(encoding="utf-8")
        body = text.split("def main()", 1)[1]
        self.assertNotIn("link_shared_skills", body, "apply.py main() now links shared skills; update the docs")
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            (home / "skills" / "git-workflow").mkdir(parents=True)
            (home / "skills" / "git-workflow" / "SKILL.md").write_text("---\nname: git-workflow\ndescription: x\n---\n", encoding="utf-8")
            result = run_apply("all", "--home", directory, "--dry-run")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotIn("would link", result.stdout)
            installer = subprocess.run(
                [sys.executable, str(ROOT / "install_harness.py"), "all", "--home", directory, "--dry-run"],
                capture_output=True, text=True,
            )
            self.assertEqual(installer.returncode, 0, installer.stderr)
            self.assertIn("would link", installer.stdout)

    def test_shared_skill_installer_repoints_stale_symlinks_only(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            current = home / "skills" / "git-workflow"
            current.mkdir(parents=True)
            (current / "SKILL.md").write_text("---\nname: git-workflow\ndescription: x\n---\n", encoding="utf-8")
            stale = home / "old-skills" / "git-workflow"
            stale.mkdir(parents=True)
            target = home / apply.HARNESS_SKILL_ROOTS["codex"] / "git-workflow"
            target.parent.mkdir(parents=True)
            target.symlink_to(stale)

            actions = apply.link_shared_skills(home, False, adapters=("codex",))

            self.assertEqual(actions, [(target, current.resolve())])
            self.assertTrue(target.is_symlink())
            self.assertEqual(target.resolve(), current.resolve())

            protected = home / "skills" / "local-owned"
            protected.mkdir()
            (protected / "SKILL.md").write_text("---\nname: local-owned\ndescription: x\n---\n", encoding="utf-8")
            installed = target.parent / "local-owned"
            installed.mkdir()
            actions = apply.link_shared_skills(home, False, adapters=("codex",))
            self.assertNotIn((installed, protected.resolve()), actions)
            self.assertTrue(installed.is_dir())

    def test_framework_skill_list_is_generated_from_the_registry(self):
        rendered = dict(apply.render_harness_skills(self.config, Path("/tmp/agent-framework-test-home"), "hermes"))
        framework = next(c for p, c in rendered.items() if p.parent.name == "agent-framework")
        for key in apply.ALL_AGENT_KEYS:
            self.assertIn(f"`agent-{key}`", framework)

    # ----------------------------------------------------------------- #
    # Generated documentation
    # ----------------------------------------------------------------- #

    def test_roster_line_counts_every_specialist_including_the_reviewer(self):
        sentence = apply.roster_sentence(self.config)
        self.assertIn(f"{len(self.config['agents'])} specialists", sentence)
        self.assertIn("`code-reviewer`", sentence)
        for key in self.config["agents"]:
            self.assertIn(f"`{key}`", sentence)

    def test_checked_in_docs_match_the_registry(self):
        """The anti-drift gate: the docs said eight specialists and named a
        model the registry does not configure. Regenerate with `apply.py docs`."""
        stale = apply.docs_drift(self.config)
        self.assertEqual(stale, [], f"stale generated blocks — run `python3 apply.py docs`: {stale}")

    def test_docs_do_not_name_a_model_the_registry_does_not_configure(self):
        configured = {apply.role_view(self.config, key)["model"] for key in apply.ALL_AGENT_KEYS}
        configured.add(apply.resolve_model({"model": self.config["routing"]["postWorkflowAudit"]["model"]}))
        for name in apply.DOC_FILES:
            path = ROOT / name
            if not path.exists():
                continue
            text = path.read_text(encoding="utf-8")
            self.assertIn("gpt-5.6-sol", text, f"{name} omits the live review model")
            self.assertIn("gpt-5.6-terra", text, f"{name} omits the live action model")
        self.assertIn("gpt-5.6-sol", configured)
        self.assertIn("gpt-5.6-terra", configured)


if __name__ == "__main__":
    unittest.main()
