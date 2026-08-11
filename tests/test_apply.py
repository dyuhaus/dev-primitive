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

    def test_generated_commands_reference_nothing_that_was_removed(self):
        """A generated command must not instruct the user to run a deleted path."""
        output = io.StringIO()
        with redirect_stdout(output):
            apply.install_claude(self.config, Path("/tmp/agent-framework-test-home"), True)
        rendered = output.getvalue()
        for gone in ("external_review.py", "roles.config.pi.json", "openrouter"):
            self.assertNotIn(gone, rendered, f"generated output still references {gone}")

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

    def test_every_generated_profile_routes_lessons_through_lessons_py(self):
        """A profile must never tell an agent to hand-edit LESSONS.md.

        That instruction is what produced the lost update: a read-modify-write of
        a file inside a branch-mutable tree.
        """
        for key in apply.ALL_AGENT_KEYS:
            profile = apply.profile_markdown(self.config, key)
            self.assertIn(f"lessons.py\" add --key {key}", profile, key)
            self.assertIn("never by editing `lessons.md` yourself", profile.lower(), key)
            self.assertNotIn("append at most one", profile.lower(), key)

    def test_generated_lessons_file_forbids_hand_editing(self):
        for key in apply.ALL_AGENT_KEYS:
            body = apply.lessons_markdown(key)
            self.assertIn("Do not hand-edit this file to record a lesson", body, key)
            self.assertIn(f"lessons.py\" add --key {key}", body, key)

    def test_no_committed_documentation_hands_an_agent_a_bare_lessons_py(self):
        """`python3 lessons.py …` only runs from the checkout holding the script.

        Profiles and lessons files are read by agents working in OTHER
        repositories; there the bare form is `can't open file`, and a lesson that
        cannot be recorded is a lesson lost. Every generated command must name
        the anchor it is relative to.
        """
        generated = {f"lessons_markdown({key})": apply.lessons_markdown(key)
                     for key in apply.ALL_AGENT_KEYS}
        generated.update({f"profile_markdown({key})": apply.profile_markdown(self.config, key)
                          for key in apply.ALL_AGENT_KEYS})
        generated["knowledge_readme()"] = apply.knowledge_readme()
        # Scoped to what an agent reads *per task* from another repository. The
        # top-level README/AGENT-FRAMEWORK quickstarts are human-facing, sit
        # beside `python3 apply.py`, and are unambiguous about their cwd.
        committed = {str(path): path.read_text(encoding="utf-8")
                     for path in (apply.SCRIPT_DIR / "agent-knowledge").rglob("*.md")}
        for label, body in {**generated, **committed}.items():
            for line in body.splitlines():
                # A COMMAND, not prose that mentions the bare form in order to
                # warn against it.
                self.assertFalse(
                    line.strip().startswith("python3 lessons.py"),
                    f"{label} gives a command that only runs from one directory: {line!r}",
                )

    def test_no_committed_documentation_embeds_this_machines_path(self):
        """The repository is public and portable; only ~/.claude output is local."""
        for path in (apply.SCRIPT_DIR / "agent-knowledge").rglob("*.md"):
            for line in path.read_text(encoding="utf-8").splitlines():
                self.assertNotIn(
                    str(apply.SCRIPT_DIR / "lessons.py"), line,
                    f"{path} bakes a machine-specific script path into a tracked file",
                )

    def test_the_generated_lessons_file_does_not_tell_an_agent_to_run_promote(self):
        """`promote` is the human review step, and the docs say so.

        Telling the agent to "fold them in later with `promote --apply`" in the
        file it is instructed to read before every task hands it the one
        read-modify-write in the system — inside a branch-mutable tree, which is
        the failure this deliverable exists to remove. Nothing enforces the
        "run by a person" claim; `--apply` is a plain flag.
        """
        for key in apply.ALL_AGENT_KEYS:
            body = apply.lessons_markdown(key)
            self.assertNotIn("--apply", body, key)
            self.assertIn("run by a person", body, key)
        for path in (apply.SCRIPT_DIR / "agent-knowledge").rglob("LESSONS.md"):
            self.assertNotIn("--apply", path.read_text(encoding="utf-8"), str(path))

    def test_committed_lessons_headers_match_the_generator(self):
        """LESSONS.md is preserved once created, so its header silently drifts."""
        marker = "\n## Durable practices\n"
        for key in apply.ALL_AGENT_KEYS:
            path = apply.SCRIPT_DIR / "agent-knowledge" / key / "LESSONS.md"
            committed = path.read_text(encoding="utf-8").split(marker, 1)[0]
            expected = apply.lessons_markdown(key).split(marker, 1)[0]
            self.assertEqual(committed, expected, f"{path} header has drifted")

    def test_committed_lessons_files_carry_the_current_intake_header(self):
        """Existing LESSONS.md files are preserved, so their header can drift."""
        for key in apply.ALL_AGENT_KEYS:
            path = apply.SCRIPT_DIR / "agent-knowledge" / key / "LESSONS.md"
            text = path.read_text(encoding="utf-8")
            self.assertIn("Do not hand-edit this file to record a lesson", text, key)
            self.assertNotIn("<!-- Append at most one", text, key)

    def test_knowledge_readme_states_the_property_and_the_durability_caveat(self):
        readme = apply.knowledge_readme()
        self.assertIn("branch-mutable", readme)
        self.assertIn("O_CREAT | O_EXCL", readme)
        self.assertIn("not under git and has no automatic off-box copy", readme)
        self.assertIn("queue, not an archive", readme)
        self.assertIn("promote", readme)

    @staticmethod
    def _rendered_sections(config):
        """Split the dry-run stream into {target path: rendered content}.

        Asserting against the whole stream is too weak: one template carrying the
        instruction makes the assertion pass for every other template too.
        """
        output = io.StringIO()
        with redirect_stdout(output):
            apply.install_claude(config, Path("/tmp/agent-framework-test-home"), True)
        sections, current = {}, None
        for line in output.getvalue().splitlines():
            if line.startswith("--- would write ") and line.endswith(" ---"):
                current = line[len("--- would write "):-len(" ---")]
                sections[current] = []
            elif current:
                sections[current].append(line)
        return {key: "\n".join(value) for key, value in sections.items()}

    def test_every_generated_claude_agent_routes_lessons_through_lessons_py(self):
        sections = self._rendered_sections(self.config)
        base = "/tmp/agent-framework-test-home/.claude/agents"
        for key in apply.ALL_AGENT_KEYS:
            body = sections[f"{base}/{key}.md"]
            self.assertIn("lessons.py add --key", body, key)
            self.assertIn(key, body.split("lessons.py add --key", 1)[1][:40], key)
            self.assertNotIn("append at most one", body.lower(), key)

    def test_no_generated_claude_agent_tells_an_agent_to_append_to_lessons_md(self):
        sections = self._rendered_sections(self.config)
        for target, body in sections.items():
            lowered = body.lower()
            self.assertNotIn("append at most one", lowered, target)
            self.assertNotIn("lesson\n  to `lessons.md`", lowered, target)

    def test_installing_from_a_linked_worktree_is_refused(self):
        """The deployment path, enforced rather than remembered.

        Generated Claude agents embed an ABSOLUTE `lessons.py` path resolved from
        wherever apply.py runs. Run it from a linked worktree — which this
        machine's rules require for feature work — and every agent is installed
        with a path `git worktree prune` deletes, while the "never hand-edit
        LESSONS.md" instruction still stands. That is every lesson silently
        unrecordable, with nothing to notice it.
        """
        with tempfile.TemporaryDirectory() as directory:
            worktree = Path(directory) / "linked"
            worktree.mkdir()
            (worktree / "lessons.py").write_text("# stub\n", encoding="utf-8")
            (worktree / ".git").write_text(
                "gitdir: /elsewhere/.git/worktrees/linked\n", encoding="utf-8")
            original = apply.SCRIPT_DIR
            try:
                apply.SCRIPT_DIR = worktree
                with self.assertRaises(SystemExit) as ctx:
                    apply.assert_generated_paths_are_installable(False)
                self.assertIn("linked git worktree", str(ctx.exception))
                # A dry run must still render, or the generator cannot be reviewed.
                apply.assert_generated_paths_are_installable(True)
            finally:
                apply.SCRIPT_DIR = original

    def test_installing_with_a_missing_lessons_script_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            primary = Path(directory) / "primary"
            (primary / ".git").mkdir(parents=True)
            original = apply.SCRIPT_DIR
            try:
                apply.SCRIPT_DIR = primary
                with self.assertRaises(SystemExit) as ctx:
                    apply.assert_generated_paths_are_installable(False)
                self.assertIn("does not exist", str(ctx.exception))
                # With the script present and a primary checkout, it proceeds.
                (primary / "lessons.py").write_text("# stub\n", encoding="utf-8")
                apply.assert_generated_paths_are_installable(False)
            finally:
                apply.SCRIPT_DIR = original

    def test_install_claude_runs_the_path_guard(self):
        """The guard must be wired into the command, not merely defined."""
        with tempfile.TemporaryDirectory() as directory:
            worktree = Path(directory) / "linked"
            worktree.mkdir()
            (worktree / "lessons.py").write_text("# stub\n", encoding="utf-8")
            (worktree / ".git").write_text("gitdir: /elsewhere\n", encoding="utf-8")
            original = apply.SCRIPT_DIR
            try:
                apply.SCRIPT_DIR = worktree
                with self.assertRaises(SystemExit) as ctx:
                    apply.install_claude(self.config, Path(directory) / "home", False)
                # Assert on the MESSAGE. A bare `assertRaises(SystemExit)` passes
                # against a guard that never ran, because this fixture has no
                # adapters/ directory and install_claude exits on the missing
                # template a moment later — the test would confirm nothing.
                self.assertIn("linked git worktree", str(ctx.exception))
                self.assertFalse((Path(directory) / "home").exists(),
                                 "agents were written before the guard ran")
            finally:
                apply.SCRIPT_DIR = original

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
