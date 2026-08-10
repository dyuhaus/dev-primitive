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
    # A long unbroken run of token characters, with no path or sentence
    # punctuation to break it up. Deliberately conservative: file paths contain
    # `/` and `.`, prose contains spaces, so neither trips this.
    ("high-entropy blob", re.compile(r"[A-Za-z0-9+=_\-]{56,}")),
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
    """
    try:
        resolved = Path(os.path.abspath(os.path.expanduser(str(path))))
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
    alnum = [c for c in raw.lower() if c.isalnum()]
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

    token, source = session_id(session)
    if not allow_multiple:
        pending = existing_sessions(key).get(token)
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


def count_dated(key: str) -> int:
    path = repo_lessons_path(key)
    if not path.is_file():
        return 0
    text = path.read_text(encoding="utf-8")
    if DATED_HEADING not in text:
        return 0
    section = text.split(DATED_HEADING, 1)[1]
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
    if DATED_HEADING not in text:
        raise LessonError(f"target file has no {DATED_HEADING!r} heading")
    body = text.splitlines()
    start = next(i for i, item in enumerate(body) if item.strip() == DATED_HEADING)
    end = len(body)
    for index in range(start + 1, len(body)):
        if body[index].startswith("## "):
            end = index
            break
    while end > start + 1 and not body[end - 1].strip():
        end -= 1
    merged = body[:end] + lines + body[end:]
    return "\n".join(merged) + "\n"


def atomic_write(path: Path, text: str) -> None:
    tmp = path.with_name(path.name + f".tmp-{os.getpid()}-{_rand4()}")
    tmp.write_text(text, encoding="utf-8")
    os.replace(str(tmp), str(path))


def promote(key: str, apply_changes: bool) -> dict:
    """Fold pending inbox entries into the repository's LESSONS.md.

    This is the one place a lesson enters a branch-mutable tree, and it is a
    deliberate act: preview by default, `--apply` to write, compare-and-swap on
    the bytes that were read, atomic replace, no commit.
    """
    target = repo_lessons_path(key)
    if not target.is_file():
        raise LessonError(f"no LESSONS.md for {key} at {target}; run `python3 apply.py knowledge` first")

    entries = pending_entries(key)
    parsed = []
    for path in entries:
        parsed.append((path, parse_entry(path)))

    before = target.read_bytes()
    text = before.decode("utf-8")
    digest = hashlib.sha256(before).hexdigest()

    to_add, duplicates = [], []
    for path, meta in parsed:
        line = meta["line"]
        assert_no_secrets(line)
        if line in text or line in to_add:
            duplicates.append((path, line))
        else:
            to_add.append(line)

    result = {
        "key": key,
        "target": str(target),
        "applied": False,
        "promoted": [line for line in to_add],
        "duplicates": [str(path) for path, _ in duplicates],
        "moved": [],
        "dated_after": count_dated(key) + len(to_add),
    }
    if not entries:
        return result
    if not apply_changes:
        return result

    if to_add:
        merged = insert_dated_lines(text, to_add)
        # Compare-and-swap. If the file changed between the read and the write —
        # the branch-switch case, or a concurrent promote — abort rather than
        # write back a stale body. This is why promote is safe even though it is
        # the one read-modify-write in the system.
        current = target.read_bytes()
        if hashlib.sha256(current).hexdigest() != digest:
            raise LessonError(
                f"{target} changed while promote was preparing its edit "
                "(branch switch, concurrent promote, or a manual edit). "
                "Nothing was written and no inbox entry was consumed — re-run promote."
            )
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


def print_promote(results: "list[dict]") -> int:
    any_pending = False
    for result in results:
        pending = len(result["promoted"]) + len(result["duplicates"])
        if not pending:
            continue
        any_pending = True
        verb = "promoted" if result["applied"] else "would promote"
        print(f"\n{result['key']}: {verb} {len(result['promoted'])} into {result['target']}")
        for line in result["promoted"]:
            print(f"  + {line}")
        for path in result["duplicates"]:
            print(f"  = already present, will be filed as promoted: {path}")
        if result["dated_after"] > CONSOLIDATION_THRESHOLD:
            print(
                f"  ! {result['key']} now has {result['dated_after']} dated lessons "
                f"(> {CONSOLIDATION_THRESHOLD}); consolidate the oldest into "
                "'## Durable practices'."
            )
    if not any_pending:
        print("nothing pending.")
        return 0
    if any(result["applied"] for result in results):
        print("\nWritten. Review the diff, then commit it yourself:")
        print(f"  git -C {SCRIPT_DIR} diff -- agent-knowledge/")
    else:
        print("\nPreview only. Re-run with --apply to write.")
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
        results = [promote(key, args.apply) for key in keys]
        if args.json:
            print(json.dumps(results, indent=2))
            return 0
        return print_promote(results)
    except LessonError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
