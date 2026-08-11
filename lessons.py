#!/usr/bin/env python3
"""lessons.py — append-only intake for durable agent lessons.

WHY THIS EXISTS
---------------
Agents used to record durable lessons by *appending to* a shared file inside the
repository: `agent-knowledge/<key>/LESSONS.md`. That is a read-modify-write of a
file in a **branch-mutable tree**, and it produced two observed failures:

  1. A branch switch replaced `LESSONS.md` underneath an agent that had already
     read it. The agent wrote back what it had read plus its own line, which
     reported as a lost update — but no lock was ever contended. `flock` does
     not fix this: the file's *contents* changed for a reason that has nothing
     to do with concurrent writers. Removing the read-modify-write does fix it.
  2. An orchestrator's own working-tree edits were swept into a concurrently
     running agent's commit, because the lesson write dirtied the same tree the
     orchestrator was working in.

THE PROPERTY THIS FILE ENFORCES
-------------------------------
**No lesson write may be a read-modify-write of a file inside a branch-mutable
tree.**

`add` therefore never reads, appends to, or rewrites any existing file. It
creates ONE NEW FILE per lesson, with `O_CREAT | O_EXCL`, under a state root
that is not a git work tree — `~/appdata/agent-knowledge/<key>/inbox/` by
default. Two writers cannot collide: `O_EXCL` makes the kernel adjudicate, and a
losing writer retries with a fresh name rather than overwriting. `add` refuses
outright if its target resolves inside a git work tree, so the property is
enforced at runtime and not merely documented.

`promote` is the ONLY path from the inbox into the repository's `LESSONS.md`.
It is a deliberate, reviewable act: it previews by default, requires `--apply`
to write, compares-and-swaps on the file it read (aborting if the file changed
underneath it, which is exactly the branch-switch case), replaces atomically,
and never commits anything.

Three properties of `promote` are load-bearing and were each once absent:

  * **The compare-and-swap is unconditional.** Consuming an inbox entry is a
    write, including when the entry is filed as an already-present duplicate —
    and "already present" is a conclusion drawn from bytes read earlier. Guard
    the CAS on "is there anything to append" and a batch of duplicates skips
    verification, so a branch switch that reverted `LESSONS.md` in between
    deletes those lessons while reporting success.
  * **One unreadable entry never blocks the others.** A zero-length file with a
    well-formed name is `add`'s own crash artifact. It is reported, left in
    place, and never consumed; the readable entries promote normally.
  * **Each profile is its own transaction.** One profile's refusal must not
    leave the profiles before it written and the profiles after it unvisited
    under a single non-zero exit code.

DURABILITY, STATED PLAINLY
--------------------------
`~/appdata` is not under git and has no automatic off-box copy on this machine
(`repo-backup` walks git repos under `~/githubStaging` plus `~/homelab`; the
`bridge` and `micro-llm-game` encrypted snapshots are per-app opt-ins). An
un-promoted lesson therefore lives in exactly one place, on one disk. That is
acceptable *because the inbox is a queue, not an archive* — the durable home is
the repository, and `promote` is what moves a lesson there. Promote often;
treat a large inbox as a backlog at risk, not as storage.

Stdlib only. Python 3.8+.
"""
from __future__ import annotations

import argparse
import errno
import hashlib
import json
import os
import re
import secrets
import socket
import sys
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
CONFIG_PATH = SCRIPT_DIR / "roles.config.json"
REPO_KNOWLEDGE_DIR = SCRIPT_DIR / "agent-knowledge"

SCHEMA = "agent-lesson/1"
DATED_HEADING = "## Dated lessons"
CONSOLIDATION_THRESHOLD = 50
NAME_COLLISION_RETRIES = 8

# Field separator of the documented dated-lesson line:
#   - YYYY-MM-DD | task type | reusable lesson | evidence/path or validation command
FIELD_SEP = "|"
MAX_FIELD_CHARS = {"task": 120, "lesson": 1200, "evidence": 800}

ENTRY_NAME_RE = re.compile(r"^(\d{8}T\d{6}Z)-([0-9a-z]{8})-([0-9a-f]{4})\.md$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)

SESSION_ENV_VARS = (
    "AGENT_SESSION_ID",
    "CLAUDE_SESSION_ID",
    "CLAUDE_CODE_SESSION_ID",
    "PI_SESSION_ID",
    "CODEX_SESSION_ID",
)

# Credential shapes. This repository is PUBLIC and `promote` copies text into it,
# so the cheapest place to stop a secret is before it is ever written down.
SECRET_PATTERNS = (
    ("anthropic key", re.compile(r"sk-ant-[A-Za-z0-9_\-]{8,}")),
    ("openai-style key", re.compile(r"\bsk-[A-Za-z0-9]{20,}")),
    ("github token", re.compile(r"\b(gh[pousr]_[A-Za-z0-9]{16,}|github_pat_[A-Za-z0-9_]{20,})")),
    ("aws access key id", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("google api key", re.compile(r"\bAIza[0-9A-Za-z_\-]{20,}")),
    ("slack token", re.compile(r"\bxox[baprs]-[A-Za-z0-9\-]{10,}")),
    ("private key block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    # A long token-shaped run: 40+ characters mixing digits, upper and lower
    # case, unbroken by a space, `/` or `.`.
    #
    # Every clause here is load-bearing against a FALSE POSITIVE, and this repo
    # is public, so a false positive means an agent's real lesson is refused.
    # `/` and `.` are excluded so a long path cannot form the run
    # (`/home/dyadmin/appdata/training-code401/PASSWORD` otherwise matches).
    # Requiring all three character classes spares snake_case identifiers
    # (`test_promote_aborts_when_the_target_changed_underneath_it` — 57
    # characters, and the first thing this rule wrongly rejected) and lowercase
    # hex git SHAs.
    #
    # This is a first line, not the last: the commit that `promote` produces is
    # still scanned by the repository's gitleaks pre-commit hook.
    ("token-shaped blob", re.compile(
        r"(?=[A-Za-z0-9+=_\-]*[0-9])(?=[A-Za-z0-9+=_\-]*[A-Z])(?=[A-Za-z0-9+=_\-]*[a-z])"
        r"[A-Za-z0-9+=_\-]{40,}"
    )),
)


class LessonError(Exception):
    """A refusal with a human-actionable message. Never a partial write."""


# --------------------------------------------------------------------------
# Roots
# --------------------------------------------------------------------------

def state_root() -> Path:
    """Where lesson entries are written.

    Precedence: explicit env override, then this machine's `~/appdata`
    convention, then the XDG state directory. The root must never be inside a
    git work tree; `assert_not_branch_mutable` enforces that at write time.
    """
    override = os.environ.get("AGENT_KNOWLEDGE_INBOX_ROOT")
    if override:
        return Path(override).expanduser()
    appdata = Path.home() / "appdata"
    if appdata.is_dir():
        return appdata / "agent-knowledge"
    xdg = os.environ.get("XDG_STATE_HOME")
    base = Path(xdg).expanduser() if xdg else Path.home() / ".local" / "state"
    return base / "agent-knowledge"


def inbox_dir(key: str) -> Path:
    return state_root() / key / "inbox"


def promoted_dir(key: str) -> Path:
    return state_root() / key / "promoted"


def repo_lessons_path(key: str) -> Path:
    return REPO_KNOWLEDGE_DIR / key / "LESSONS.md"


def branch_mutable_ancestor(path: Path) -> "Path | None":
    """Return the git work tree containing `path`, or None.

    A `.git` entry is checked for *existence*, not type: a linked worktree has a
    `.git` FILE, and a lesson written into a linked worktree is exactly as
    exposed to a branch switch as one written into a primary checkout.

    Symlinks are RESOLVED, not merely normalized. `os.path.abspath` is lexical:
    it collapses `..` without following links, so a state root that is a symlink
    to `some-repo/sub/dir` walks the *link's* parents — which are outside any
    repository — and the guard passes while the write lands inside a work tree.
    `os.path.realpath` walks the link, so the parents examined are the real
    ones. That is the difference between enforcing the property and documenting
    it.
    """
    try:
        resolved = Path(os.path.realpath(os.path.expanduser(str(path))))
    except OSError:  # pragma: no cover - defensive
        return None
    for candidate in (resolved, *resolved.parents):
        if (candidate / ".git").exists():
            return candidate
    return None


def assert_not_branch_mutable(path: Path) -> None:
    """Refuse to write a lesson anywhere a branch switch can rewrite it."""
    repo = branch_mutable_ancestor(path)
    if repo is not None:
        raise LessonError(
            f"refusing to write a lesson inside a git work tree: {path}\n"
            f"  the tree at {repo} is branch-mutable — a checkout can replace the file\n"
            f"  under a reader, which is the failure this tool exists to remove.\n"
            f"  Set AGENT_KNOWLEDGE_INBOX_ROOT to a path outside any repository."
        )


# --------------------------------------------------------------------------
# Identity
# --------------------------------------------------------------------------

def _squash_to_8(raw: str) -> str:
    """Reduce any session identifier to 8 characters of `[0-9a-z]`.

    ASCII-only is not cosmetic. `str.isalnum()` is true for non-ASCII letters,
    so a session id such as `héllowörld` produced the token `héllowör` and a
    filename `ENTRY_NAME_RE` does not match — the entry was written and then
    invisible to `show` and `promote`. A silently unreachable lesson is the
    exact failure class this tool exists to remove.
    """
    alnum = [c for c in raw.lower() if c.isascii() and c.isalnum()]
    if len(alnum) >= 8:
        return "".join(alnum[:8])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:8]


def session_id(explicit: "str | None" = None) -> "tuple[str, str]":
    """Return (8-char session token, provenance).

    Falls back to a value derived from the parent process, which is stable for
    the life of one harness session on Linux and merely unique elsewhere. The
    provenance string is recorded in the entry so a reader can tell a real
    session id from a derived one.
    """
    if explicit:
        return _squash_to_8(explicit), "explicit"
    for var in SESSION_ENV_VARS:
        value = os.environ.get(var)
        if value:
            return _squash_to_8(value), f"env:{var}"
    parts = [socket.gethostname(), str(os.getppid())]
    try:
        with open(f"/proc/{os.getppid()}/stat", encoding="utf-8") as fh:
            parts.append(fh.read().rsplit(")", 1)[-1].split()[19])
        source = "derived:ppid"
    except (OSError, IndexError):
        parts.append(secrets.token_hex(8))
        source = "derived:random"
    return _squash_to_8(hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()), source


def _rand4() -> str:
    return secrets.token_hex(2)


def _fsync_directory(path: Path) -> None:
    """Make a newly created entry's *name* durable, not just its bytes."""
    try:
        fd = os.open(str(path), os.O_RDONLY)
    except OSError:  # pragma: no cover - not every platform allows this
        return
    try:
        os.fsync(fd)
    except OSError:  # pragma: no cover - directory fsync is unsupported on some filesystems
        pass
    finally:
        os.close(fd)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def entry_filename(now: datetime, session: str, rand: str) -> str:
    return f"{now.strftime('%Y%m%dT%H%M%SZ')}-{session}-{rand}.md"


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------

def clean_field(name: str, value: str) -> str:
    text = " ".join((value or "").split())
    if not text:
        raise LessonError(f"--{name} is empty after whitespace normalization")
    if FIELD_SEP in text:
        raise LessonError(
            f"--{name} may not contain {FIELD_SEP!r}: it is the dated-lesson field separator"
        )
    limit = MAX_FIELD_CHARS[name]
    if len(text) > limit:
        raise LessonError(
            f"--{name} is {len(text)} characters; the limit is {limit}. "
            "A lesson is a generalized practice, not a task log — shorten it."
        )
    return text


def scan_for_secrets(text: str) -> "list[str]":
    return [label for label, pattern in SECRET_PATTERNS if pattern.search(text)]


def assert_no_secrets(text: str) -> None:
    hits = scan_for_secrets(text)
    if hits:
        raise LessonError(
            "refusing to record a lesson containing credential-shaped text: "
            + ", ".join(hits)
            + "\n  This repository is public and `promote` copies the text into it."
        )


def dated_line(date: str, task: str, lesson: str, evidence: str) -> str:
    return f"- {date} | {task} | {lesson} | {evidence}"


# --------------------------------------------------------------------------
# add
# --------------------------------------------------------------------------

def existing_sessions(key: str) -> "dict[str, list[str]]":
    """Map session token -> pending entry filenames. A directory listing, not a
    read-modify-write; the inbox is not branch-mutable so the listing is stable.
    """
    out: "dict[str, list[str]]" = {}
    directory = inbox_dir(key)
    if not directory.is_dir():
        return out
    for name in sorted(os.listdir(directory)):
        match = ENTRY_NAME_RE.match(name)
        if match:
            out.setdefault(match.group(2), []).append(name)
    return out


def _entry_is_readable(path: Path) -> bool:
    try:
        parse_entry(path)
    except (LessonError, OSError, UnicodeDecodeError):
        return False
    return True


def entry_text(key: str, date: str, session: str, source: str, task: str, line: str, created: datetime) -> str:
    return (
        "---\n"
        f"schema: {SCHEMA}\n"
        f"key: {key}\n"
        f"date: {date}\n"
        f"created: {created.strftime('%Y-%m-%dT%H:%M:%SZ')}\n"
        f"session: {session}\n"
        f"session_source: {source}\n"
        f"task: {task}\n"
        "---\n"
        f"{line}\n"
    )


def add_lesson(
    key: str,
    task: str,
    lesson: str,
    evidence: str,
    date: "str | None" = None,
    session: "str | None" = None,
    allow_multiple: bool = False,
) -> Path:
    """Create exactly one new file. Never reads or rewrites an existing file."""
    task = clean_field("task", task)
    lesson = clean_field("lesson", lesson)
    evidence = clean_field("evidence", evidence)
    assert_no_secrets(" ".join((task, lesson, evidence)))

    now = _utc_now()
    day = date or now.strftime("%Y-%m-%d")
    if not DATE_RE.match(day):
        raise LessonError(f"--date must be YYYY-MM-DD, got {day!r}")
    try:
        datetime.strptime(day, "%Y-%m-%d")
    except ValueError:
        raise LessonError(f"--date is not a real calendar date: {day!r}")

    token, source = session_id(session)
    if not allow_multiple:
        # Count only entries a reader can actually parse. A zero-length or
        # truncated file is `add`'s own crash artifact, not a recorded lesson,
        # and letting it satisfy "this session already recorded one" locks the
        # session out of recording anything until a human deletes the file.
        # Reading inbox files is safe: the inbox is not branch-mutable, and this
        # never reads or rewrites the file `add` is about to create.
        pending = [
            name for name in existing_sessions(key).get(token, [])
            if _entry_is_readable(inbox_dir(key) / name)
        ]
        if pending:
            raise LessonError(
                f"session {token} already has {len(pending)} pending lesson(s) for {key}: "
                + ", ".join(pending)
                + "\n  At most one lesson per profile per session is the standing rule."
                "\n  Pass --allow-multiple only if the second lesson is genuinely separate."
            )

    directory = inbox_dir(key)
    assert_not_branch_mutable(directory)
    directory.mkdir(parents=True, exist_ok=True)

    line = dated_line(day, task, lesson, evidence)
    payload = entry_text(key, day, token, source, task, line, now).encode("utf-8")

    last_name = ""
    for _ in range(NAME_COLLISION_RETRIES):
        last_name = entry_filename(now, token, _rand4())
        # A name the readers cannot parse is a lesson that is written and then
        # invisible. Refuse before creating the file rather than after.
        if not ENTRY_NAME_RE.match(last_name):
            raise LessonError(
                f"refusing to write an entry named {last_name!r}: `show` and `promote` "
                "would not recognize it, so the lesson would be silently unreachable"
            )
        target = directory / last_name
        try:
            # O_EXCL: the kernel adjudicates. A losing writer never truncates the
            # winner's file, and no reader ever sees a partial entry.
            fd = os.open(str(target), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            continue
        except OSError as exc:  # pragma: no cover - defensive
            if exc.errno == errno.EEXIST:
                continue
            raise
        with os.fdopen(fd, "wb") as fh:
            fh.write(payload)
            fh.flush()
            # The inbox has no off-box copy (see agent-knowledge/README.md), so
            # this is the only copy of the lesson until it is promoted. Pay for
            # the fsync; a zero-length entry after a crash is a lost lesson.
            os.fsync(fh.fileno())
        _fsync_directory(directory)
        return target
    raise LessonError(
        f"could not claim a unique entry name after {NAME_COLLISION_RETRIES} attempts "
        f"(last tried {last_name}); nothing was written and no existing entry was touched"
    )


# --------------------------------------------------------------------------
# read / show
# --------------------------------------------------------------------------

def parse_entry(path: Path) -> dict:
    raw = path.read_text(encoding="utf-8")
    meta: dict = {"file": str(path), "name": path.name}
    body_lines: "list[str]" = []
    lines = raw.splitlines()
    if lines and lines[0].strip() == "---":
        closing = None
        for index in range(1, len(lines)):
            if lines[index].strip() == "---":
                closing = index
                break
        if closing is None:
            raise LessonError(f"{path}: front matter is not terminated")
        for raw_line in lines[1:closing]:
            if ":" in raw_line:
                name, _, value = raw_line.partition(":")
                meta[name.strip()] = value.strip()
        body_lines = lines[closing + 1:]
    else:
        body_lines = lines
    line = next((item for item in body_lines if item.startswith("- ")), None)
    if line is None:
        raise LessonError(f"{path}: no dated-lesson line (a line starting with '- ')")
    meta["line"] = line.rstrip()
    return meta


def pending_entries(key: str) -> "list[Path]":
    directory = inbox_dir(key)
    if not directory.is_dir():
        return []
    return [directory / name for name in sorted(os.listdir(directory)) if ENTRY_NAME_RE.match(name)]


def dated_heading_index(body: "list[str]") -> "int | None":
    """Index of the `## Dated lessons` heading LINE, or None.

    Located by exact match on the stripped line, and every caller uses this one
    function. A substring test (`DATED_HEADING in text`) and a line-equality
    search disagree on `## Dated lessons (archive)`: the substring test says the
    section is present, the equality search finds nothing, and `next()` without
    a default then raises `StopIteration` — not a `LessonError`, so `main`'s
    handler misses it and the operator gets a traceback. The trigger is a human
    retitling the heading during the 50-entry consolidation the docs ask for.
    """
    for index, item in enumerate(body):
        if item.strip() == DATED_HEADING:
            return index
    return None


def dated_section_bounds(body: "list[str]") -> "tuple[int, int] | None":
    """(first line after the heading, first line of the next `## ` section)."""
    start = dated_heading_index(body)
    if start is None:
        return None
    end = len(body)
    for index in range(start + 1, len(body)):
        if body[index].startswith("## "):
            end = index
            break
    return start + 1, end


def count_dated(key: str) -> int:
    """Number of real dated entries in `<key>/LESSONS.md`.

    Two things are deliberately excluded. HTML comments, because the generated
    template's own format note *contains a line in the entry format*
    (`- YYYY-MM-DD | task type | ...`), so a freshly generated, entirely empty
    file otherwise reports 1 and every populated file is off by one. And
    anything after the next `## ` heading, because the old count ran to EOF and
    swept up the bullets of every following section.
    """
    path = repo_lessons_path(key)
    if not path.is_file():
        return 0
    body = path.read_text(encoding="utf-8").splitlines()
    bounds = dated_section_bounds(body)
    if bounds is None:
        return 0
    start, end = bounds
    section = HTML_COMMENT_RE.sub("", "\n".join(body[start:end]))
    return sum(1 for item in section.splitlines() if item.startswith("- "))


def agent_keys() -> "list[str]":
    try:
        with CONFIG_PATH.open(encoding="utf-8") as fh:
            cfg = json.load(fh)
    except (OSError, ValueError) as exc:
        raise LessonError(f"cannot read {CONFIG_PATH}: {exc}")
    return list(cfg.get("roles", {})) + list(cfg.get("agents", {}))


def resolve_key(key: str) -> str:
    keys = agent_keys()
    if key not in keys:
        raise LessonError(f"unknown profile key {key!r}; known keys: {', '.join(keys)}")
    return key


def show(keys: "list[str]", as_json: bool) -> int:
    report = []
    for key in keys:
        entries = []
        for path in pending_entries(key):
            try:
                entries.append(parse_entry(path))
            except LessonError as exc:
                entries.append({"file": str(path), "name": path.name, "error": str(exc)})
        report.append({
            "key": key,
            "inbox": str(inbox_dir(key)),
            "pending": entries,
            "promoted": _count_promoted(key),
            "repo_dated_lessons": count_dated(key),
        })
    if as_json:
        print(json.dumps({"state_root": str(state_root()), "profiles": report}, indent=2))
        return 0
    print(f"state root: {state_root()}")
    print(f"repository: {REPO_KNOWLEDGE_DIR}")
    for item in report:
        print(
            f"\n{item['key']}: {len(item['pending'])} pending, "
            f"{item['promoted']} promoted, {item['repo_dated_lessons']} in LESSONS.md"
        )
        for entry in item["pending"]:
            if "error" in entry:
                print(f"  ! {entry['name']}: {entry['error']}")
                continue
            print(f"  {entry['name']}  (session {entry.get('session', '?')})")
            print(f"    {entry['line']}")
    return 0


def _count_promoted(key: str) -> int:
    directory = promoted_dir(key)
    if not directory.is_dir():
        return 0
    return sum(1 for name in os.listdir(directory) if ENTRY_NAME_RE.match(name))


# --------------------------------------------------------------------------
# promote
# --------------------------------------------------------------------------

def insert_dated_lines(text: str, lines: "list[str]") -> str:
    """Insert dated lines at the end of the `## Dated lessons` section."""
    body = text.splitlines()
    bounds = dated_section_bounds(body)
    if bounds is None:
        raise LessonError(
            f"target file has no {DATED_HEADING!r} heading of its own.\n"
            f"  The heading line must read exactly {DATED_HEADING!r} — a retitled heading such "
            f"as '{DATED_HEADING} (archive)' is not recognized.\n"
            "  Restore the heading, then re-run promote. Nothing was written and no inbox "
            "entry was consumed."
        )
    start, end = bounds
    while end > start and not body[end - 1].strip():
        end -= 1
    merged = body[:end] + lines + body[end:]
    return "\n".join(merged) + "\n"


def file_identity(path: Path) -> "tuple[int, int] | None":
    """(device, inode) of `path`, or None if it does not exist.

    `git checkout` does not rewrite a tracked file in place; it unlinks and
    recreates it, so the inode changes even when the bytes happen to be
    identical. Content hashing alone cannot see that.
    """
    try:
        info = path.stat()
    except OSError:
        return None
    return (info.st_dev, info.st_ino)


def atomic_write(path: Path, text: str) -> None:
    tmp = path.with_name(path.name + f".tmp-{os.getpid()}-{_rand4()}")
    try:
        tmp.write_text(text, encoding="utf-8")
        os.replace(str(tmp), str(path))
    except BaseException:
        # Never leave a stray temp file in a repository worktree: it would show
        # up as an untracked change in somebody else's `git status`.
        try:
            tmp.unlink()
        except OSError:
            pass
        raise


def promote(key: str, apply_changes: bool) -> dict:
    """Fold pending inbox entries into the repository's LESSONS.md.

    This is the one place a lesson enters a branch-mutable tree, and it is a
    deliberate act: preview by default, `--apply` to write, compare-and-swap on
    the bytes that were read, atomic replace, no commit.
    """
    target = repo_lessons_path(key)
    if not target.is_file():
        raise LessonError(f"no LESSONS.md for {key} at {target}; run `python3 apply.py knowledge` first")

    # One unreadable entry must not jam the queue. A kill, OOM or ENOSPC between
    # `add`'s O_EXCL create and its write leaves a zero-length file whose NAME is
    # perfectly well formed — `add`'s own crash artifact. Parsing every entry up
    # front and letting the first failure propagate turned that artifact into a
    # total outage: `promote` (with and without --apply) exited 2 for the whole
    # run, and with no --key it did so partway through the key list. Malformed
    # entries are now reported, never consumed, and never block the readable
    # ones.
    entries = pending_entries(key)
    parsed, malformed = [], []
    for path in entries:
        try:
            parsed.append((path, parse_entry(path)))
        except (LessonError, OSError, UnicodeDecodeError) as exc:
            malformed.append((path, str(exc)))

    identity = file_identity(target)
    before = target.read_bytes()
    text = before.decode("utf-8")
    digest = hashlib.sha256(before).hexdigest()
    # Compare whole LINES, not substrings. `line in text` classifies a genuinely
    # new, SHORTER lesson as a duplicate of a longer existing one that happens to
    # contain it — and a "duplicate" is consumed into promoted/, so the lesson is
    # deleted from the queue having never reached the repository.
    existing_lines = {item.strip() for item in text.splitlines()}

    to_add, duplicates, seen = [], [], set()
    for path, meta in parsed:
        line = meta["line"]
        assert_no_secrets(line)
        stripped = line.strip()
        if stripped in existing_lines or stripped in seen:
            duplicates.append((path, line))
        else:
            seen.add(stripped)
            to_add.append(line)

    result = {
        "key": key,
        "target": str(target),
        "applied": False,
        "promoted": [line for line in to_add],
        "duplicates": [str(path) for path, _ in duplicates],
        "malformed": [{"file": str(path), "error": message} for path, message in malformed],
        "moved": [],
        "dated_after": count_dated(key) + len(to_add),
    }
    if not parsed:
        return result
    if not apply_changes:
        return result

    # Prepare the merge BEFORE the compare-and-swap so a refusal (a missing or
    # retitled heading) aborts with nothing written and nothing consumed.
    merged = insert_dated_lines(text, to_add) if to_add else None

    # Compare-and-swap on BOTH the bytes and the file identity, and do it
    # UNCONDITIONALLY — including when every entry was classified a duplicate and
    # there is nothing to write.
    #
    # Guarding this on `if to_add:` reintroduced the exact failure this file
    # exists to prevent. "Already present" is a conclusion drawn from `text`,
    # which was read earlier; if a branch switch reverted LESSONS.md in between,
    # the lines are NOT present on the file that now exists, and consuming the
    # entries on the strength of the stale read deletes the lessons outright —
    # applied: true, promoted: [], entries filed under promoted/, nothing in the
    # repository. Consuming an entry is a write. Every write here is verified.
    #
    # The identity check catches a `git checkout` that replaced the file with
    # byte-identical content but a new inode.
    #
    # This narrows the window; it does not eliminate it. `promote` remains the
    # one read-modify-write in the system, which is precisely why it is a
    # deliberate human-run command and not something an agent does mid-task.
    # Nothing here is safe to call from a background job.
    current = target.read_bytes()
    if hashlib.sha256(current).hexdigest() != digest or file_identity(target) != identity:
        raise LessonError(
            f"{target} changed while promote was preparing its edit "
            "(branch switch, concurrent promote, or a manual edit). "
            "Nothing was written and no inbox entry was consumed — re-run promote."
        )
    if merged is not None:
        atomic_write(target, merged)

    promoted_root = promoted_dir(key)
    assert_not_branch_mutable(promoted_root)
    promoted_root.mkdir(parents=True, exist_ok=True)
    for path, _ in parsed:
        destination = promoted_root / path.name
        os.replace(str(path), str(destination))
        result["moved"].append(str(destination))

    result["applied"] = True
    return result


def print_promote(results: "list[dict]", failures: "list[tuple[str, str]]" = ()) -> int:
    any_pending = False
    malformed_total = 0
    for result in results:
        malformed = result.get("malformed", [])
        malformed_total += len(malformed)
        pending = len(result["promoted"]) + len(result["duplicates"]) + len(malformed)
        if not pending:
            continue
        any_pending = True
        verb = "promoted" if result["applied"] else "would promote"
        print(f"\n{result['key']}: {verb} {len(result['promoted'])} into {result['target']}")
        for line in result["promoted"]:
            print(f"  + {line}")
        for path in result["duplicates"]:
            print(f"  = already present, will be filed as promoted: {path}")
        for item in malformed:
            print(f"  ! UNREADABLE, left in the inbox: {item['file']}")
            print(f"      {item['error']}")
        if result["dated_after"] > CONSOLIDATION_THRESHOLD:
            print(
                f"  ! {result['key']} now has {result['dated_after']} dated lessons "
                f"(> {CONSOLIDATION_THRESHOLD}); consolidate the oldest into "
                "'## Durable practices'."
            )
    for key, message in failures:
        print(f"\n{key}: FAILED — nothing written, nothing consumed for this profile")
        for line in str(message).splitlines():
            print(f"  {line}")
    if not any_pending and not failures:
        print("nothing pending.")
        return 0
    if any(result["applied"] for result in results):
        # `promote` writes into the checkout this script lives in, so the diff is
        # in THAT tree — name it, and say so plainly, because on this machine the
        # canonical checkout doubles as a live deploy source and must not be
        # branch-switched or committed to casually.
        print(f"\nWritten into {SCRIPT_DIR}. Review the diff and commit it yourself:")
        print(f"  git -C {SCRIPT_DIR} diff -- agent-knowledge/")
        print("  If that checkout is a deploy source or is not the branch you intend to")
        print("  commit on, move the diff to a worktree before committing. `promote` never")
        print("  commits, and never switches a branch.")
    elif any_pending:
        print("\nPreview only. Re-run with --apply to write.")
    if malformed_total:
        print(
            f"\n{malformed_total} unreadable inbox entr"
            f"{'y was' if malformed_total == 1 else 'ies were'} skipped and left in place. "
            "A zero-length entry is a\ncrash artifact from an interrupted `add` — inspect it, "
            "then delete it. Nothing else\nwas blocked by it."
        )
    if failures or malformed_total:
        return 2
    return 0


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="lessons.py",
        description="Append-only intake for durable agent lessons (one file per append).",
    )
    sub = ap.add_subparsers(dest="command", required=True)

    add = sub.add_parser("add", help="record one lesson as a new file in the inbox")
    add.add_argument("--key", required=True, help="profile key, e.g. builder")
    add.add_argument("--task", required=True, help="task type this lesson came from")
    add.add_argument("--lesson", required=True, help="the generalized, reusable lesson")
    add.add_argument("--evidence", required=True, help="evidence: path, command, or measurement")
    add.add_argument("--date", help="YYYY-MM-DD (default: today, UTC)")
    add.add_argument("--session", help="session identifier (default: harness env, else derived)")
    add.add_argument("--allow-multiple", action="store_true", help="permit a second lesson from this session")
    add.add_argument("--json", action="store_true")

    show_p = sub.add_parser("show", help="show pending inbox entries")
    show_p.add_argument("--key", help="profile key (default: all)")
    show_p.add_argument("--json", action="store_true")

    prom = sub.add_parser("promote", help="fold inbox entries into the repo's LESSONS.md")
    prom.add_argument("--key", help="profile key (default: all)")
    prom.add_argument("--apply", action="store_true", help="write; without it this is a preview")
    prom.add_argument("--json", action="store_true")
    return ap


def main(argv: "list[str] | None" = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "add":
            path = add_lesson(
                resolve_key(args.key),
                args.task,
                args.lesson,
                args.evidence,
                date=args.date,
                session=args.session,
                allow_multiple=args.allow_multiple,
            )
            if args.json:
                print(json.dumps({"written": str(path)}))
            else:
                print(f"wrote {path}")
                print("Not in the repository yet. `lessons.py promote --key "
                      f"{args.key} --apply` files it into LESSONS.md.")
            return 0
        keys = [resolve_key(args.key)] if args.key else agent_keys()
        if args.command == "show":
            return show(keys, args.json)
        # Promote each profile independently. Letting one key's refusal abort the
        # loop left the keys before it already written and consumed while the
        # keys after it never ran — and the caller saw a single non-zero exit,
        # from which "nothing happened" is the natural and wrong reading. Each
        # key is its own transaction; the run reports every outcome.
        results, failures = [], []
        for key in keys:
            try:
                results.append(promote(key, args.apply))
            except LessonError as exc:
                failures.append((key, str(exc)))
        if args.json:
            print(json.dumps(
                {"results": results,
                 "failed": [{"key": key, "error": message} for key, message in failures]},
                indent=2,
            ))
            return 2 if failures or any(r.get("malformed") for r in results) else 0
        return print_promote(results, failures)
    except LessonError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
