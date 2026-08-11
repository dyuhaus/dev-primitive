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
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("lessons", ROOT / "lessons.py")
lessons = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lessons)

KEY = "builder"

# The format note is the REAL one `apply.py` generates, not a stand-in. It
# contains a line in the dated-entry format (`- YYYY-MM-DD | ...`), which is
# exactly what made `count_dated` report 1 for an entirely empty file and one too
# many for every populated one. A fixture that writes `<!-- format note -->`
# instead cannot see that, and did not.
GENERATED_FORMAT_NOTE = (
    "<!-- Entries are written by `lessons.py promote`, in the documented format:\n"
    "- YYYY-MM-DD | task type | reusable lesson | evidence/path or validation command\n"
    "When this section reaches 50 entries, fold the oldest reusable items into Durable\n"
    "practices and remove the consolidated dated entries. -->\n"
)
SEED_LESSONS_MD = (
    "# builder lessons\n\n## Durable practices\n\n- Read the profile.\n\n"
    "## Dated lessons\n\n" + GENERATED_FORMAT_NOTE +
    "- 2026-01-01 | seed | an existing lesson | seed evidence\n"
)

# A well-formed NAME with no parseable content: precisely what a kill, OOM or
# ENOSPC between `add`'s O_EXCL create and its write leaves behind.
CRASH_ARTIFACT_NAME = "20260101T000000Z-deadbeef-0000.md"


class LessonsTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="lessons-test-"))
        self.state = self.tmp / "state"
        self.repo = self.tmp / "repo"
        (self.repo / "agent-knowledge" / KEY).mkdir(parents=True)
        self.lessons_md = self.repo / "agent-knowledge" / KEY / "LESSONS.md"
        self.lessons_md.write_text(SEED_LESSONS_MD, encoding="utf-8")
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
        """The clock is PINNED, not merely assumed to be slow.

        The entry name embeds `%H%M%S` and `add` samples the clock per call, so
        the collision this forces only happens when both calls land in the same
        UTC second. Left to the real clock the test passes ~99.99% of the time
        and silently fails whenever it straddles a second boundary — and it is
        the ONLY test that kills the `O_EXCL` mutant, so a flake there is the
        whole exclusive-create claim going unasserted.
        """
        original_rand, original_now = lessons._rand4, lessons._utc_now
        pinned = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        lessons._rand4 = lambda: "beef"
        lessons._utc_now = lambda: pinned
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
            lessons._rand4, lessons._utc_now = original_rand, original_now

    def test_the_collision_test_above_would_not_fire_on_the_real_clock(self):
        """Guards the pin itself: without it the collision simply does not occur."""
        original_rand, original_now = lessons._rand4, lessons._utc_now
        clock = {"t": datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)}
        lessons._rand4 = lambda: "beef"
        lessons._utc_now = lambda: clock["t"]
        try:
            self.add()
            clock["t"] += timedelta(seconds=1)  # the boundary the real clock crosses
            second = self.add(lesson="One second later.", allow_multiple=True)
            self.assertTrue(second.is_file())
            self.assertEqual(len(lessons.pending_entries(KEY)), 2)
        finally:
            lessons._rand4, lessons._utc_now = original_rand, original_now

    def test_open_flags_include_o_excl(self):
        source = (ROOT / "lessons.py").read_text(encoding="utf-8")
        self.assertIn("os.O_EXCL", source)


class EntryIsAlwaysReachable(LessonsTestBase):
    """A written-but-invisible entry is a lost lesson with no error."""

    def test_a_non_ascii_session_id_still_yields_a_readable_entry(self):
        try:
            path = self.add(session="héllowörld-session-id")
        except lessons.LessonError as exc:
            # Without the ASCII squash the unreadable-name guard fires instead,
            # which is a refusal, not a lost lesson — but the lesson is still
            # not recorded, so this is a failure of this test's claim.
            self.fail(f"a non-ASCII session id must still produce a reachable entry: {exc}")
        self.assertIsNotNone(
            lessons.ENTRY_NAME_RE.match(path.name), f"unreadable entry name: {path.name}"
        )
        self.assertEqual(lessons.pending_entries(KEY), [path])
        result = lessons.promote(KEY, apply_changes=False)
        self.assertEqual(len(result["promoted"]), 1)

    def test_every_written_entry_is_visible_to_show_and_promote(self):
        sessions = ("6163b36c-1a5b", "héllowörld", "AB", "ЖЖЖЖЖЖЖЖ", "12345678")
        written = set()
        for index, session in enumerate(sessions):
            try:
                written.add(self.add(
                    session=session, lesson=f"Distinct practice {index}.", allow_multiple=True
                ))
            except lessons.LessonError as exc:
                self.fail(f"session {session!r} produced no recordable entry: {exc}")
        self.assertEqual(len(written), len(sessions))
        self.assertEqual(set(lessons.pending_entries(KEY)), written)
        self.assertEqual(
            len(lessons.promote(KEY, apply_changes=False)["promoted"]), len(sessions)
        )

    def test_an_unparseable_entry_name_is_refused_rather_than_written(self):
        original = lessons.entry_filename
        lessons.entry_filename = lambda now, session, rand: "not-an-entry-name.md"
        try:
            with self.assertRaises(lessons.LessonError) as ctx:
                self.add()
        finally:
            lessons.entry_filename = original
        self.assertIn("silently unreachable", str(ctx.exception))
        self.assertEqual(list(lessons.inbox_dir(KEY).iterdir()), [])


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

    def test_a_symlinked_state_root_pointing_into_a_repository_is_refused(self):
        """The guard must RESOLVE, not merely normalize.

        `os.path.abspath` is lexical: it walks the link's own parents, which are
        outside any repository, so the guard passed while the write landed inside
        a git work tree — the one hole in "enforced at runtime, not merely
        documented". Symlinking to the repository ROOT was already caught
        (`.exists()` follows links); symlinking to a SUBDIRECTORY was not.
        """
        work_tree = self.tmp / "some-repo"
        (work_tree / ".git").mkdir(parents=True)
        (work_tree / "sub" / "dir").mkdir(parents=True)
        link = self.tmp / "linked-state"
        link.symlink_to(work_tree / "sub" / "dir")
        os.environ["AGENT_KNOWLEDGE_INBOX_ROOT"] = str(link)

        self.assertEqual(
            lessons.branch_mutable_ancestor(link / KEY / "inbox"),
            work_tree,
            "the guard did not follow the symlink into the work tree",
        )
        with self.assertRaises(lessons.LessonError) as ctx:
            self.add()
        self.assertIn("git work tree", str(ctx.exception))
        # Decisive: nothing was written anywhere inside the repository.
        self.assertEqual(
            [p for p in work_tree.rglob("*") if p.is_file() and p.suffix == ".md"], []
        )


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

    def test_an_unreadable_pending_entry_does_not_lock_the_session_out(self):
        """A crash artifact is not a recorded lesson.

        The one-per-session check matched on FILENAME alone, so a session whose
        write was interrupted could never record anything again — the crash that
        lost the first lesson silently blocked every later one too.
        """
        inbox = lessons.inbox_dir(KEY)
        inbox.mkdir(parents=True, exist_ok=True)
        (inbox / CRASH_ARTIFACT_NAME).write_bytes(b"")
        try:
            path = self.add(session="deadbeef")
        except lessons.LessonError as exc:
            # self.fail, not a propagated error: an ERROR can mean the test never
            # reached its assertions, and the control harness scores only
            # assertion failures as verifying a claim.
            self.fail(f"a crash artifact blocked this session from recording a lesson: {exc}")
        self.assertTrue(path.is_file())
        self.assertEqual(len(lessons.pending_entries(KEY)), 2)

    def test_a_readable_pending_entry_still_blocks_the_session(self):
        """The narrowing must not disarm the rule it narrows."""
        self.add(session="deadbeef")
        with self.assertRaises(lessons.LessonError) as ctx:
            self.add(session="deadbeef", lesson="A second one from this session.")
        self.assertIn("already has", str(ctx.exception))


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

    def test_realistic_evidence_strings_are_not_refused_as_secrets(self):
        """A false positive refuses a real lesson. Each of these once did or could."""
        for text in (
            "test_promote_aborts_when_the_target_changed_underneath_it",
            "/home/dyadmin/appdata/training-code401/PASSWORD.txt",
            "~/githubStaging/InHouseTrader/scripts/ls_responder.py at commit 3dba990",
            "python3 -m unittest discover -s tests; tests/control_mutants.py",
            "a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4",  # a 40-char lowercase sha
        ):
            self.assertEqual(lessons.scan_for_secrets(text), [], text)
            self.add(evidence=text)
            for path in lessons.pending_entries(KEY):
                path.unlink()

    def test_each_credential_rule_catches_something_only_it_catches(self):
        """Asserted per rule.

        A sample that trips two rules cannot show that either one works: the
        generic length rule was silently covering every vendor prefix here.
        """
        # Assembled at runtime, never written out as a literal: these are
        # decoys, but the repository's own gitleaks pre-commit hook cannot tell
        # the difference and blocked the commit that first spelled them out.
        # Concatenation keeps the fixtures honest without weakening the scanner
        # or reaching for --no-verify.
        q = "q" * 24
        samples = {
            "anthropic key": "sk-" + "ant-api03-" + q,
            "openai-style key": "sk-" + q,
            "github token": "gh" + "p_" + q,
            "aws access key id": "AK" + "IAIOSFODNN7EXAMPLE",
            "google api key": "AI" + "za" + q,
            "slack token": "xo" + "xb-" + q,
            "private key block": "-----BEGIN " + "RSA PRIVATE KEY" + "-----",
            # Low entropy on purpose, so the repo's scanner does not read this
            # decoy as real; it still has the shape our rule looks for.
            "token-shaped blob": ("aZ0" * 14)[:40],
        }
        for label, sample in samples.items():
            hits = lessons.scan_for_secrets(sample)
            self.assertIn(label, hits, f"{label} not matched by {sample!r} (got {hits})")
            self.assertEqual(hits, [label], f"{sample!r} trips more than {label}: {hits}")
        with self.assertRaises(lessons.LessonError):
            self.add(evidence=f"token was {samples['github token']}")

    def test_an_impossible_calendar_date_is_refused(self):
        with self.assertRaises(lessons.LessonError) as ctx:
            self.add(date="2026-02-30")
        self.assertIn("not a real calendar date", str(ctx.exception))
        self.assertEqual(lessons.pending_entries(KEY), [])


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

    def test_promote_aborts_when_the_file_was_replaced_with_identical_bytes(self):
        """`git checkout` recreates the file: same bytes, new inode."""
        self.add()
        original_read = lessons.Path.read_bytes
        state = {"calls": 0}
        body = self.lessons_md.read_text(encoding="utf-8")

        def read_bytes(self_path):
            data = original_read(self_path)
            if Path(self_path) == self.lessons_md:
                state["calls"] += 1
                if state["calls"] == 1:
                    replacement = self.lessons_md.with_name("swap")
                    replacement.write_text(body, encoding="utf-8")
                    os.replace(str(replacement), str(self.lessons_md))
            return data

        lessons.Path.read_bytes = read_bytes
        try:
            with self.assertRaises(lessons.LessonError) as ctx:
                lessons.promote(KEY, apply_changes=True)
        finally:
            lessons.Path.read_bytes = original_read
        self.assertIn("changed while promote", str(ctx.exception))
        self.assertEqual(self.lessons_md.read_text(encoding="utf-8"), body)
        self.assertEqual(len(lessons.pending_entries(KEY)), 1)

    def test_a_failed_write_leaves_no_temp_file_in_the_worktree(self):
        self.add()
        before = set(os.listdir(self.lessons_md.parent))
        original = lessons.os.replace

        def boom(src, dst):
            raise OSError("simulated failure")

        lessons.os.replace = boom
        try:
            with self.assertRaises(OSError):
                lessons.promote(KEY, apply_changes=True)
        finally:
            lessons.os.replace = original
        self.assertEqual(set(os.listdir(self.lessons_md.parent)), before)

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

    def _swap_target_after_first_read(self, replacement: str) -> dict:
        """Replace LESSONS.md after promote's first read of it — a branch switch."""
        original_read = lessons.Path.read_bytes
        state = {"calls": 0}

        def read_bytes(self_path):
            data = original_read(self_path)
            if Path(self_path) == self.lessons_md:
                state["calls"] += 1
                if state["calls"] == 1:
                    self.lessons_md.write_text(replacement, encoding="utf-8")
            return data

        lessons.Path.read_bytes = read_bytes
        self.addCleanup(lambda: setattr(lessons.Path, "read_bytes", original_read))
        return state

    def test_an_all_duplicate_batch_verifies_the_target_before_consuming_anything(self):
        """The original failure, surviving inside its own fix.

        "Already present" is a conclusion drawn from bytes read earlier. Guarding
        the compare-and-swap on `if to_add:` meant an all-duplicate batch skipped
        verification entirely and consumed the inbox anyway — so a branch switch
        that reverted LESSONS.md between the read and the file moves deleted the
        lessons outright, reporting `applied: true`.
        """
        path = self.add()
        line = lessons.parse_entry(path)["line"]
        # On the branch we are looking at, the line is already there.
        self.lessons_md.write_text(
            self.lessons_md.read_text(encoding="utf-8") + line + "\n", encoding="utf-8"
        )
        reverted = (
            "# builder lessons\n\n## Dated lessons\n\n"
            "- 2025-12-31 | other branch | a different file entirely | other\n"
        )
        state = self._swap_target_after_first_read(reverted)

        with self.assertRaises(lessons.LessonError) as ctx:
            lessons.promote(KEY, apply_changes=True)
        self.assertIn("changed while promote", str(ctx.exception))
        self.assertGreaterEqual(state["calls"], 2, "promote never re-read the target")
        # The decisive assertions: the lesson is still queued, and the file that
        # actually exists is untouched.
        self.assertEqual(len(lessons.pending_entries(KEY)), 1)
        self.assertEqual(lessons._count_promoted(KEY), 0)
        self.assertEqual(self.lessons_md.read_text(encoding="utf-8"), reverted)
        self.assertNotIn(line, reverted)

    def test_a_shorter_new_lesson_is_not_a_duplicate_of_a_longer_existing_one(self):
        """`line in text` is a substring test; a contained lesson was eaten."""
        new_line = lessons.parse_entry(self.add()).pop("line")
        for path in lessons.pending_entries(KEY):
            path.unlink()
        # An existing entry that CONTAINS the new one, plus more evidence.
        self.lessons_md.write_text(
            self.lessons_md.read_text(encoding="utf-8") + new_line + " and docs/gate.md\n",
            encoding="utf-8",
        )
        self.add()
        result = lessons.promote(KEY, apply_changes=True)
        self.assertEqual(result["duplicates"], [], "a shorter distinct lesson was called a duplicate")
        self.assertEqual(result["promoted"], [new_line])
        body = self.lessons_md.read_text(encoding="utf-8")
        self.assertIn(new_line + "\n", body)
        self.assertIn(new_line + " and docs/gate.md\n", body)

    def test_an_exact_duplicate_is_still_detected_after_the_line_comparison(self):
        """The narrowing must not go so far that real duplicates slip through."""
        line = lessons.parse_entry(self.add())["line"]
        self.lessons_md.write_text(
            self.lessons_md.read_text(encoding="utf-8") + line + "\n", encoding="utf-8"
        )
        result = lessons.promote(KEY, apply_changes=True)
        self.assertEqual(result["promoted"], [])
        self.assertEqual(len(result["duplicates"]), 1)
        self.assertEqual(self.lessons_md.read_text(encoding="utf-8").count(line), 1)

    def test_one_unreadable_entry_does_not_block_the_readable_ones(self):
        """`add`'s own crash artifact must not jam the only path into the repo."""
        self.add()
        (lessons.inbox_dir(KEY) / CRASH_ARTIFACT_NAME).write_bytes(b"")
        result = lessons.promote(KEY, apply_changes=True)
        self.assertEqual(len(result["promoted"]), 1)
        self.assertTrue(result["applied"])
        self.assertIn("gate's own sample size", self.lessons_md.read_text(encoding="utf-8"))
        self.assertEqual(len(result["malformed"]), 1)
        self.assertIn(CRASH_ARTIFACT_NAME, result["malformed"][0]["file"])
        # Skipped is not discarded: a truncated entry may still hold text.
        self.assertTrue((lessons.inbox_dir(KEY) / CRASH_ARTIFACT_NAME).is_file())

    def test_an_unreadable_entry_is_reported_and_never_consumed(self):
        """Skipping must not mean discarding: a truncated entry may hold text."""
        (lessons.inbox_dir(KEY)).mkdir(parents=True, exist_ok=True)
        victim = lessons.inbox_dir(KEY) / CRASH_ARTIFACT_NAME
        victim.write_bytes(b"")
        result = lessons.promote(KEY, apply_changes=True)
        self.assertEqual(len(result["malformed"]), 1)
        self.assertTrue(victim.is_file(), "the unreadable entry was consumed")
        self.assertEqual(lessons._count_promoted(KEY), 0)
        self.assertFalse(result["applied"])

    def test_a_preview_with_only_an_unreadable_entry_does_not_raise(self):
        (lessons.inbox_dir(KEY)).mkdir(parents=True, exist_ok=True)
        (lessons.inbox_dir(KEY) / CRASH_ARTIFACT_NAME).write_bytes(b"")
        result = lessons.promote(KEY, apply_changes=False)
        self.assertEqual(len(result["malformed"]), 1)

    def test_a_retitled_dated_heading_refuses_instead_of_raising_stopiteration(self):
        """The guard and the search must use one predicate.

        A substring guard plus a line-equality search disagree on
        `## Dated lessons (archive)`, and the bare `next()` then raised
        StopIteration — which `main` does not catch, so the operator got a
        traceback instead of the human-actionable refusal this file promises.
        The trigger is the 50-entry consolidation the docs ask a human to do.
        """
        self.lessons_md.write_text(
            SEED_LESSONS_MD.replace("## Dated lessons\n", "## Dated lessons (archive)\n"),
            encoding="utf-8",
        )
        self.add()
        before = self.lessons_md.read_bytes()
        with self.assertRaises(lessons.LessonError) as ctx:
            lessons.promote(KEY, apply_changes=True)
        self.assertIn("heading", str(ctx.exception))
        self.assertEqual(self.lessons_md.read_bytes(), before)
        self.assertEqual(len(lessons.pending_entries(KEY)), 1)

    def test_the_retitled_heading_reaches_the_cli_as_an_error_not_a_traceback(self):
        self.lessons_md.write_text(
            SEED_LESSONS_MD.replace("## Dated lessons\n", "## Dated lessons (archive)\n"),
            encoding="utf-8",
        )
        self.add()
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = lessons.main(["promote", "--key", KEY, "--apply"])
        self.assertEqual(code, 2)
        self.assertIn("FAILED", buffer.getvalue())


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


class CountDated(LessonsTestBase):
    """`count_dated` feeds `show --json` and the consolidation warning."""

    def test_an_entirely_empty_generated_file_counts_zero(self):
        """The generated format note contains a line in the entry format."""
        self.lessons_md.write_text(
            "# builder lessons\n\n## Durable practices\n\n- Read the profile.\n\n"
            "## Dated lessons\n\n" + GENERATED_FORMAT_NOTE,
            encoding="utf-8",
        )
        self.assertEqual(lessons.count_dated(KEY), 0)

    def test_the_format_note_does_not_inflate_a_populated_file(self):
        self.assertEqual(lessons.count_dated(KEY), 1)  # SEED_LESSONS_MD has exactly one
        self.add()
        lessons.promote(KEY, apply_changes=True)
        self.assertEqual(lessons.count_dated(KEY), 2)

    def test_bullets_in_a_later_section_are_not_counted_as_dated_lessons(self):
        """The old count ran to EOF and swept up every following section."""
        self.lessons_md.write_text(
            "# builder lessons\n\n## Dated lessons\n\n"
            "- 2026-01-01 | a | b | c\n\n"
            "## Appendix\n\n- not a lesson\n- also not a lesson\n",
            encoding="utf-8",
        )
        self.assertEqual(lessons.count_dated(KEY), 1)

    def test_a_retitled_heading_counts_zero_rather_than_exploding(self):
        self.lessons_md.write_text(
            SEED_LESSONS_MD.replace("## Dated lessons\n", "## Dated lessons (archive)\n"),
            encoding="utf-8",
        )
        self.assertEqual(lessons.count_dated(KEY), 0)

    def test_show_json_reports_the_corrected_count(self):
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            lessons.show([KEY], as_json=True)
        self.assertEqual(json.loads(buffer.getvalue())["profiles"][0]["repo_dated_lessons"], 1)


class CliIsolation(LessonsTestBase):
    def test_one_profiles_failure_does_not_skip_the_profiles_after_it(self):
        """Each key is its own transaction.

        Promoting every key in one comprehension meant the first refusal aborted
        the loop: keys before it were already written and consumed, keys after it
        never ran, and the caller saw one non-zero exit from which "nothing
        happened" is the natural — and wrong — reading.
        """
        keys = lessons.agent_keys()
        self.assertGreater(keys.index(KEY), keys.index("planner"), "fixture assumes ordering")
        for key in ("planner", KEY):
            (lessons.REPO_KNOWLEDGE_DIR / key).mkdir(parents=True, exist_ok=True)
            (lessons.REPO_KNOWLEDGE_DIR / key / "LESSONS.md").write_text(
                SEED_LESSONS_MD, encoding="utf-8")
        # planner comes first and will refuse: its heading is retitled.
        planner_md = lessons.REPO_KNOWLEDGE_DIR / "planner" / "LESSONS.md"
        planner_md.write_text(
            SEED_LESSONS_MD.replace("## Dated lessons\n", "## Dated lessons (archive)\n"),
            encoding="utf-8",
        )
        lessons.add_lesson(key="planner", task="t", lesson="A planner lesson.",
                           evidence="e", session="11111111")
        self.add(session="22222222")

        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = lessons.main(["promote", "--apply"])
        self.assertEqual(code, 2)
        # The decisive assertion: the key AFTER the failure was still promoted.
        self.assertIn("gate's own sample size", self.lessons_md.read_text(encoding="utf-8"))
        self.assertEqual(lessons.pending_entries(KEY), [])
        # And the failing key wrote and consumed nothing.
        self.assertNotIn("A planner lesson", planner_md.read_text(encoding="utf-8"))
        self.assertEqual(len(lessons.pending_entries("planner")), 1)
        self.assertIn("planner", buffer.getvalue())

    def test_a_malformed_entry_makes_the_command_exit_non_zero(self):
        """Skipped-and-left-behind must not be reported as a clean run."""
        self.add()
        (lessons.inbox_dir(KEY) / CRASH_ARTIFACT_NAME).write_bytes(b"")
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = lessons.main(["promote", "--key", KEY, "--apply"])
        self.assertEqual(code, 2)
        self.assertIn("UNREADABLE", buffer.getvalue())

    def test_a_clean_promote_still_exits_zero(self):
        self.add()
        with redirect_stdout(io.StringIO()):
            self.assertEqual(lessons.main(["promote", "--key", KEY, "--apply"]), 0)


class ControlHarnessScoring(unittest.TestCase):
    """The control harness is itself a claim, so it is itself tested."""

    @staticmethod
    def _module():
        path = ROOT / "tests" / "mutant_scoring.py"
        spec = importlib.util.spec_from_file_location("mutant_scoring", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_an_errored_only_mutant_is_not_scored_as_verified(self):
        """Its own docstring: killed by an assertion failure, not an error.

        The scoring appended to `survivors` on `not fails and not errs`, so a
        mutant that only crashed setUp was silently excluded from the survivor
        list and the run exited 0 claiming every mutant was killed — the exact
        trap the file exists to avoid, one level up.
        """
        control = self._module()
        self.assertEqual(control.classify(["T.test_a"], []), control.KILLED)
        self.assertEqual(control.classify([], ["T.test_a"]), control.ERRORED_ONLY)
        self.assertEqual(control.classify([], []), control.SURVIVED)
        self.assertTrue(control.counts_as_verified(control.KILLED))
        self.assertFalse(control.counts_as_verified(control.ERRORED_ONLY))
        self.assertFalse(control.counts_as_verified(control.SURVIVED))


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
