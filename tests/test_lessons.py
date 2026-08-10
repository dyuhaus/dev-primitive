"""Tests for lessons.py — the append-only lesson intake.

Every test here is written to be killable. `tests/control_mutants.py` mutates one
piece of logic at a time and names which test dies for which mutant. A green run
of this file on its own proves nothing; that control does.
"""
import hashlib
import importlib.util
import io
import json
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("lessons", ROOT / "lessons.py")
lessons = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lessons)

KEY = "builder"


class LessonsTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="lessons-test-"))
        self.state = self.tmp / "state"
        self.repo = self.tmp / "repo"
        (self.repo / "agent-knowledge" / KEY).mkdir(parents=True)
        self.lessons_md = self.repo / "agent-knowledge" / KEY / "LESSONS.md"
        self.lessons_md.write_text(
            "# builder lessons\n\n## Durable practices\n\n- Read the profile.\n\n"
            "## Dated lessons\n\n<!-- format note -->\n"
            "- 2026-01-01 | seed | an existing lesson | seed evidence\n",
            encoding="utf-8",
        )
        self._env = dict(os.environ)
        os.environ["AGENT_KNOWLEDGE_INBOX_ROOT"] = str(self.state)
        os.environ["AGENT_SESSION_ID"] = "abcdef01-2222-3333-4444-555555555555"
        self._old_knowledge = lessons.REPO_KNOWLEDGE_DIR
        lessons.REPO_KNOWLEDGE_DIR = self.repo / "agent-knowledge"

    def tearDown(self):
        lessons.REPO_KNOWLEDGE_DIR = self._old_knowledge
        os.environ.clear()
        os.environ.update(self._env)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def add(self, **kwargs):
        params = dict(
            key=KEY,
            task="tuning a constant",
            lesson="Measure the candidate at the gate's own sample size.",
            evidence="tools/balance-gate.sh --repeats 3",
        )
        params.update(kwargs)
        return lessons.add_lesson(**params)


class AddWritesOneNewFile(LessonsTestBase):
    def test_add_creates_a_single_new_file_and_reads_nothing(self):
        path = self.add()
        self.assertTrue(path.is_file())
        self.assertEqual(len(lessons.pending_entries(KEY)), 1)
        self.assertIn("| tuning a constant |", path.read_text(encoding="utf-8"))

    def test_entry_filename_is_utc_session_random(self):
        path = self.add()
        match = lessons.ENTRY_NAME_RE.match(path.name)
        self.assertIsNotNone(match, f"unexpected entry name: {path.name}")
        self.assertEqual(match.group(2), "abcdef01")

    def test_add_never_touches_the_repository_lessons_file(self):
        before = self.lessons_md.read_bytes()
        self.add()
        self.assertEqual(self.lessons_md.read_bytes(), before)

    def test_add_leaves_earlier_entries_byte_identical(self):
        first = self.add()
        original = first.read_bytes()
        self.add(lesson="A second, genuinely separate practice.", allow_multiple=True)
        self.assertEqual(first.read_bytes(), original)


class ExclusiveCreate(LessonsTestBase):
    """The O_EXCL claim: a losing writer must never truncate the winner."""

    def test_a_name_collision_never_overwrites_the_existing_entry(self):
        original_rand = lessons._rand4
        lessons._rand4 = lambda: "beef"
        try:
            first = self.add()
            body = first.read_bytes()
            with self.assertRaises(lessons.LessonError) as ctx:
                self.add(
                    lesson="A different lesson that must not land on top.",
                    allow_multiple=True,
                )
            self.assertIn("unique entry name", str(ctx.exception))
            # The decisive assertion: the winner's bytes are untouched.
            self.assertEqual(first.read_bytes(), body)
            self.assertNotIn("must not land on top", first.read_text(encoding="utf-8"))
            self.assertEqual(len(lessons.pending_entries(KEY)), 1)
        finally:
            lessons._rand4 = original_rand

    def test_open_flags_include_o_excl(self):
        source = (ROOT / "lessons.py").read_text(encoding="utf-8")
        self.assertIn("os.O_EXCL", source)


class BranchMutableGuard(LessonsTestBase):
    """The property: no lesson write inside a branch-mutable tree."""

    def test_add_refuses_when_the_inbox_is_inside_a_git_work_tree(self):
        (self.state / ".git").mkdir(parents=True)
        with self.assertRaises(lessons.LessonError) as ctx:
            self.add()
        self.assertIn("git work tree", str(ctx.exception))
        self.assertEqual(lessons.pending_entries(KEY), [])

    def test_a_linked_worktree_git_file_counts_too(self):
        self.state.mkdir(parents=True, exist_ok=True)
        (self.state / ".git").write_text("gitdir: /elsewhere/.git/worktrees/x\n", encoding="utf-8")
        with self.assertRaises(lessons.LessonError):
            self.add()

    def test_guard_detects_a_repository_several_levels_up(self):
        (self.tmp / ".git").mkdir()
        self.assertEqual(
            lessons.branch_mutable_ancestor(self.state / KEY / "inbox"), self.tmp
        )

    def test_a_state_root_outside_any_repository_is_accepted(self):
        self.assertIsNone(lessons.branch_mutable_ancestor(self.state / KEY / "inbox"))
        self.assertTrue(self.add().is_file())


class SessionDiscipline(LessonsTestBase):
    def test_second_lesson_from_the_same_session_is_refused(self):
        self.add()
        with self.assertRaises(lessons.LessonError) as ctx:
            self.add(lesson="Another lesson from the same session.")
        self.assertIn("already has", str(ctx.exception))
        self.assertEqual(len(lessons.pending_entries(KEY)), 1)

    def test_allow_multiple_permits_a_deliberate_second_entry(self):
        self.add()
        self.add(lesson="Another lesson from the same session.", allow_multiple=True)
        self.assertEqual(len(lessons.pending_entries(KEY)), 2)

    def test_a_different_session_is_not_blocked(self):
        self.add()
        self.add(lesson="A lesson from a different session.", session="99999999-aaaa")
        self.assertEqual(len(lessons.pending_entries(KEY)), 2)


class ContentGuards(LessonsTestBase):
    def test_credential_shaped_text_is_refused(self):
        with self.assertRaises(lessons.LessonError) as ctx:
            self.add(evidence="used the key sk-ant-api03-ABCDEFGHIJKLMNOP")
        self.assertIn("credential-shaped", str(ctx.exception))
        self.assertEqual(lessons.pending_entries(KEY), [])

    def test_ordinary_paths_and_commands_are_not_flagged(self):
        self.assertEqual(
            lessons.scan_for_secrets(
                "/home/dyadmin/dev-primitive/agent-knowledge/builder/LESSONS.md "
                "python3 -m unittest discover -s tests test_knowledge_generation_preserves_lessons"
            ),
            [],
        )

    def test_the_field_separator_is_refused_in_a_field(self):
        with self.assertRaises(lessons.LessonError) as ctx:
            self.add(task="build | deploy")
        self.assertIn("field separator", str(ctx.exception))

    def test_an_overlong_lesson_is_refused_as_a_task_log(self):
        with self.assertRaises(lessons.LessonError) as ctx:
            self.add(lesson="x " * 900)
        self.assertIn("limit is", str(ctx.exception))

    def test_newlines_are_normalized_into_one_line(self):
        path = self.add(lesson="first part\n  second part")
        entry = lessons.parse_entry(path)
        self.assertIn("first part second part", entry["line"])
        self.assertEqual(len(entry["line"].splitlines()), 1)

    def test_an_unknown_profile_key_is_refused(self):
        with self.assertRaises(lessons.LessonError):
            lessons.resolve_key("not-a-profile")


class Promote(LessonsTestBase):
    def test_preview_does_not_write_or_consume(self):
        self.add()
        before = self.lessons_md.read_bytes()
        result = lessons.promote(KEY, apply_changes=False)
        self.assertFalse(result["applied"])
        self.assertEqual(len(result["promoted"]), 1)
        self.assertEqual(self.lessons_md.read_bytes(), before)
        self.assertEqual(len(lessons.pending_entries(KEY)), 1)

    def test_apply_appends_into_the_dated_section(self):
        self.add()
        result = lessons.promote(KEY, apply_changes=True)
        self.assertTrue(result["applied"])
        text = self.lessons_md.read_text(encoding="utf-8")
        self.assertIn("gate's own sample size", text)
        dated = text.split(lessons.DATED_HEADING, 1)[1]
        self.assertIn("gate's own sample size", dated)
        self.assertNotIn("gate's own sample size", text.split(lessons.DATED_HEADING, 1)[0])

    def test_apply_consumes_the_inbox_entry_so_it_cannot_be_promoted_twice(self):
        self.add()
        lessons.promote(KEY, apply_changes=True)
        self.assertEqual(lessons.pending_entries(KEY), [])
        self.assertEqual(lessons._count_promoted(KEY), 1)
        second = lessons.promote(KEY, apply_changes=True)
        self.assertEqual(second["promoted"], [])
        self.assertEqual(
            self.lessons_md.read_text(encoding="utf-8").count("gate's own sample size"), 1
        )

    def test_promote_preserves_existing_content_and_ordering(self):
        self.add()
        lessons.promote(KEY, apply_changes=True)
        body = self.lessons_md.read_text(encoding="utf-8")
        self.assertIn("- 2026-01-01 | seed | an existing lesson | seed evidence", body)
        self.assertLess(body.index("seed evidence"), body.index("gate's own sample size"))
        self.assertIn("## Durable practices", body)

    def test_a_duplicate_line_is_filed_without_a_second_append(self):
        path = self.add()
        line = lessons.parse_entry(path)["line"]
        self.lessons_md.write_text(
            self.lessons_md.read_text(encoding="utf-8") + line + "\n", encoding="utf-8"
        )
        result = lessons.promote(KEY, apply_changes=True)
        self.assertEqual(result["promoted"], [])
        self.assertEqual(len(result["duplicates"]), 1)
        self.assertEqual(self.lessons_md.read_text(encoding="utf-8").count(line), 1)
        self.assertEqual(lessons.pending_entries(KEY), [])

    def test_promote_aborts_when_the_target_changed_underneath_it(self):
        """The branch-switch case, reproduced deterministically."""
        self.add()
        original_read = lessons.Path.read_bytes
        state = {"calls": 0}
        switched = (
            "# builder lessons\n\n## Dated lessons\n\n"
            "- 2025-12-31 | other branch | a different file entirely | other\n"
        )

        def read_bytes(self_path):
            data = original_read(self_path)
            if Path(self_path) == self.lessons_md:
                state["calls"] += 1
                if state["calls"] == 1:
                    # After promote's first read, a branch switch replaces the file.
                    self.lessons_md.write_text(switched, encoding="utf-8")
            return data

        lessons.Path.read_bytes = read_bytes
        try:
            with self.assertRaises(lessons.LessonError) as ctx:
                lessons.promote(KEY, apply_changes=True)
        finally:
            lessons.Path.read_bytes = original_read
        self.assertIn("changed while promote", str(ctx.exception))
        # Nothing written, nothing consumed: the other branch's file is intact.
        self.assertEqual(self.lessons_md.read_text(encoding="utf-8"), switched)
        self.assertEqual(len(lessons.pending_entries(KEY)), 1)

    def test_a_failed_replace_leaves_the_target_untouched(self):
        self.add()
        before = self.lessons_md.read_bytes()
        original_replace = lessons.os.replace

        def boom(src, dst):
            raise OSError("simulated failure")

        lessons.os.replace = boom
        try:
            with self.assertRaises(OSError):
                lessons.promote(KEY, apply_changes=True)
        finally:
            lessons.os.replace = original_replace
        self.assertEqual(self.lessons_md.read_bytes(), before)
        self.assertEqual(len(lessons.pending_entries(KEY)), 1)

    def test_lines_land_before_a_following_section(self):
        self.lessons_md.write_text(
            "# builder lessons\n\n## Dated lessons\n\n- 2026-01-01 | a | b | c\n\n"
            "## Appendix\n\nnot a lesson\n",
            encoding="utf-8",
        )
        self.add()
        lessons.promote(KEY, apply_changes=True)
        body = self.lessons_md.read_text(encoding="utf-8")
        self.assertLess(body.index("gate's own sample size"), body.index("## Appendix"))

    def test_promote_refuses_a_missing_target(self):
        self.lessons_md.unlink()
        self.add()
        with self.assertRaises(lessons.LessonError) as ctx:
            lessons.promote(KEY, apply_changes=True)
        self.assertIn("apply.py knowledge", str(ctx.exception))


class Show(LessonsTestBase):
    def test_show_json_reports_pending_and_repo_counts(self):
        self.add()
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            lessons.show([KEY], as_json=True)
        payload = json.loads(buffer.getvalue())
        profile = payload["profiles"][0]
        self.assertEqual(profile["key"], KEY)
        self.assertEqual(len(profile["pending"]), 1)
        self.assertEqual(profile["repo_dated_lessons"], 1)
        self.assertEqual(profile["promoted"], 0)

    def test_show_is_read_only(self):
        path = self.add()
        before = (path.read_bytes(), self.lessons_md.read_bytes())
        with redirect_stdout(io.StringIO()):
            lessons.show([KEY], as_json=False)
        self.assertEqual((path.read_bytes(), self.lessons_md.read_bytes()), before)


class Roots(unittest.TestCase):
    def setUp(self):
        self._env = dict(os.environ)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._env)

    def test_env_override_wins(self):
        os.environ["AGENT_KNOWLEDGE_INBOX_ROOT"] = "/somewhere/else"
        self.assertEqual(lessons.state_root(), Path("/somewhere/else"))

    def test_default_root_is_outside_this_repository(self):
        os.environ.pop("AGENT_KNOWLEDGE_INBOX_ROOT", None)
        root = lessons.state_root()
        self.assertFalse(str(root).startswith(str(ROOT) + os.sep), f"{root} is inside {ROOT}")
        self.assertIsNone(lessons.branch_mutable_ancestor(root))

    def test_session_token_is_eight_lowercase_alphanumerics(self):
        os.environ["AGENT_SESSION_ID"] = "6163B36C-1a5b-4995-b6b3-ab4970603f94"
        token, source = lessons.session_id()
        self.assertEqual(token, "6163b36c")
        self.assertEqual(source, "env:AGENT_SESSION_ID")

    def test_a_short_session_id_is_hashed_to_eight_characters(self):
        token, _ = lessons.session_id("ab")
        self.assertEqual(len(token), 8)
        self.assertTrue(all(c in "0123456789abcdef" for c in token))
        self.assertEqual(token, hashlib.sha256(b"ab").hexdigest()[:8])


if __name__ == "__main__":
    unittest.main()
