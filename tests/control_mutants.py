#!/usr/bin/env python3
"""Control harness for the lesson-intake tests.

Run:  python3 tests/control_mutants.py

WHY THIS IS NOT OPTIONAL. A green suite is not evidence that the suite tests
anything. The usual control — revert the change and watch the tests fail — does
not work for `lessons.py`, because reverting it deletes the module and the suite
dies at import, which proves nothing (a documented trap: a whole-file revert
that errors in setUp has been misread as "the control worked").

So each mutant here changes exactly ONE piece of logic or ONE instruction, and
the harness records which NAMED tests die. `M00-noop` must kill nothing; every
other mutant must be killed by an assertion failure, not an error. A survivor
means the claim it encodes is asserted nowhere.

Zero third-party dependencies.
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

# Bytecode caching silently corrupts a mutation control. `importlib` writes a
# `.pyc` for the mutated module; restoring the original in the same second with
# the SAME BYTE LENGTH — which a one-character mutant like `alnum[:6]` ->
# `alnum[:8]` guarantees — reproduces the cached (mtime, size) key exactly, so
# the next run executes the MUTANT from cache. Observed here: three unrelated
# instruction mutants "killed" all fourteen lessons.py tests. Disable caching.
CHILD_ENV = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")

# ---------------------------------------------------------------- lessons.py
LOGIC_MUTANTS = [
    ("M00-noop", "lessons.py",
     "Stdlib only. Python 3.8+.", "Stdlib only. Python 3.8 or newer."),
    ("M01-no-O_EXCL", "lessons.py",
     "os.O_WRONLY | os.O_CREAT | os.O_EXCL", "os.O_WRONLY | os.O_CREAT | os.O_TRUNC"),
    ("M02-branch-mutable-guard-off", "lessons.py",
     "    repo = branch_mutable_ancestor(path)\n    if repo is not None:",
     "    repo = branch_mutable_ancestor(path)\n    if False:"),
    ("M03-guard-misses-linked-worktrees", "lessons.py",
     'if (candidate / ".git").exists():', 'if (candidate / ".git").is_dir():'),
    ("M04-promote-no-compare-and-swap", "lessons.py",
     "        if hashlib.sha256(current).hexdigest() != digest:", "        if False:"),
    ("M05-promote-does-not-consume-the-entry", "lessons.py",
     '        os.replace(str(path), str(destination))\n        result["moved"].append(str(destination))',
     '        result["moved"].append(str(destination))'),
    ("M06-secret-guard-off", "lessons.py",
     "    hits = scan_for_secrets(text)\n    if hits:",
     "    hits = scan_for_secrets(text)\n    if False:"),
    ("M07-one-lesson-per-session-off", "lessons.py",
     "    if not allow_multiple:", "    if False:"),
    ("M08-promote-writes-non-atomically", "lessons.py",
     "    os.replace(str(tmp), str(path))", '    path.write_text(text, encoding="utf-8")'),
    ("M09-preview-writes-anyway", "lessons.py",
     "    if not apply_changes:\n        return result", "    if False:\n        return result"),
    ("M10-promote-appends-at-eof", "lessons.py",
     "    merged = body[:end] + lines + body[end:]", "    merged = body + lines"),
    ("M11-no-duplicate-detection", "lessons.py",
     "        if line in text or line in to_add:", "        if False:"),
    ("M12-field-separator-guard-off", "lessons.py",
     "    if FIELD_SEP in text:", "    if False:"),
    ("M13-state-root-inside-the-repo", "lessons.py",
     '    appdata = Path.home() / "appdata"', "    appdata = SCRIPT_DIR"),
    ("M14-session-token-truncated", "lessons.py",
     '        return "".join(alnum[:8])', '        return "".join(alnum[:6])'),
]

# --------------------------------------------------- generated instructions
INSTRUCTION_MUTANTS = [
    ("D01-profile-reverts-to-hand-append", "apply.py",
     "material above. After substantive work, record at most one generalized,\n"
     "evidence-backed lesson — **never by editing `LESSONS.md` yourself**:",
     "material above. After substantive work, append at most one generalized,\n"
     "evidence-backed lesson in the documented format if it will improve future work."),
    ("D02-lessons-template-drops-the-warning", "apply.py",
     "**Do not hand-edit this file to record a lesson.** It lives in a branch-mutable",
     "This file lives in a branch-mutable"),
    ("D03-a-committed-lessons-file-drifts", "agent-knowledge/runner/LESSONS.md",
     "**Do not hand-edit this file to record a lesson.**", "Lessons may be appended here."),
    ("D04-readme-drops-the-durability-note", "apply.py",
     "`~/appdata` is **not under git and has no automatic off-box copy**.",
     "`~/appdata` holds the inbox."),
    ("D05-readme-drops-the-queue-framing", "apply.py",
     "inbox is a **queue, not an archive**", "inbox is where lessons live"),
    ("D06-claude-template-reverts", "adapters/claude-code/agent.md.tmpl",
     "- After substantive work, record at most one generalized, evidence-backed lesson\n"
     "  when it will help future work. **Never edit `LESSONS.md` to do this**",
     "- After substantive work, append at most one generalized, evidence-backed lesson\n"
     "  to `LESSONS.md` when it will help future work. **Never edit `LESSONS.md` to do this**"),
    ("D07-claude-template-drops-lessons_py", "adapters/claude-code/agent.md.tmpl",
     "`python3 {{LESSONS_SCRIPT}} add --key {{AGENT_KEY}}",
     "`python3 nothing.py add --key {{AGENT_KEY}}"),
    ("D08-lessons-script-path-not-substituted", "apply.py",
     '            "LESSONS_SCRIPT": str(SCRIPT_DIR / "lessons.py"),',
     '            "LESSONS_SCRIPT": "",'),
]

FAIL_RE = re.compile(r"^(FAIL|ERROR): (\S+) \(([^)]+)\)")


def run_suite(root: Path):
    for cache in root.rglob("__pycache__"):
        shutil.rmtree(cache, ignore_errors=True)
    proc = subprocess.run(
        [sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests"],
        cwd=root, capture_output=True, text=True, timeout=600, env=CHILD_ENV,
    )
    out = proc.stdout + proc.stderr
    fails, errs = [], []
    for line in out.splitlines():
        match = FAIL_RE.match(line.strip())
        if match:
            (fails if match.group(1) == "FAIL" else errs).append(match.group(2))
    return proc.returncode, fails, errs, out


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        sandbox = Path(tmp) / "repo"
        shutil.copytree(REPO, sandbox, ignore=shutil.ignore_patterns(".git", "__pycache__"))
        code, fails, errs, out = run_suite(sandbox)
        print(f"BASELINE: rc={code} failures={fails} errors={errs}\n")
        if code != 0:
            print(out[-3000:])
            return 1

        survivors = []
        for name, rel, old, new in LOGIC_MUTANTS + INSTRUCTION_MUTANTS:
            path = sandbox / rel
            original = path.read_text(encoding="utf-8")
            if original.count(old) != 1:
                print(f"{name}: PATTERN NOT UNIQUE ({original.count(old)} matches) -- FIX THE MUTANT")
                survivors.append(name)
                continue
            path.write_text(original.replace(old, new, 1), encoding="utf-8")
            code, fails, errs, _ = run_suite(sandbox)
            if name.startswith("M00"):
                ok = code == 0 and not fails and not errs
                print(f"{name}: {'NO-OP OK (nothing died)' if ok else f'NO-OP BROKEN: {fails} {errs}'}")
                if not ok:
                    survivors.append(name)
            else:
                print(f"{name}: {'KILLED' if fails else ('ERRORED-ONLY' if errs else 'SURVIVED')}")
                for test in fails:
                    print(f"    killed: {test}")
                for test in errs:
                    print(f"    errored: {test}")
                if not fails and not errs:
                    survivors.append(name)
            path.write_text(original, encoding="utf-8")

        print()
        if survivors:
            print(f"SURVIVORS (claims asserted nowhere): {survivors}")
            return 1
        print("All mutants killed by at least one named test; the no-op killed nothing.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
