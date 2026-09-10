# audit lessons

This is durable, harness-neutral working knowledge for the `audit` profile.
Keep behavioral, reusable lessons here; do **not** store secrets, credentials,
personal data, private task content, or chronological task logs.

**Do not hand-edit this file to record a lesson.** It lives in a branch-mutable
tree, so appending to it is a read-modify-write that a branch switch can silently
undo. Recording is report-only unless the current task specifically grants
write authority for the lesson inbox. Do not append during a read-only task.
When authorized, record at most one lesson with:

```bash
python3 "$DEV_PRIMITIVE/lessons.py" add --key audit --task "<task type>" \
  --lesson "<reusable lesson>" --evidence "<path, command, or measurement>"
```

See [PROFILE.md](./PROFILE.md) for the same command in context. A bare
`python3 lessons.py` only works from the checkout that holds the script.

`lessons.py promote` is the only route from the inbox into this repository, and
it is **run by a person** who reviews the diff and commits it — not by an agent
mid-task, and not from a background job. Hand edits to this file are for one
thing: consolidating dated entries into `## Durable practices`.

## Durable practices

- Read the profile and applicable project instructions before work.

## Dated lessons

<!-- Entries are written by `lessons.py promote`, in the documented format:
- YYYY-MM-DD | task type | reusable lesson | evidence/path or validation command
When this section reaches 50 entries, fold the oldest reusable items into Durable
practices and remove the consolidated dated entries. -->
- 2026-07-25 | agent-routing audit | A plan-before-build config flag must affect the router's selected destination, not merely documentation or tool prompts; otherwise generic implementation can bypass the required planning phase. | `python3 -m unittest discover -s tests -v` and `node adapters/pi/pb-primitive/_selftest.mjs`
- 2026-08-17 | harness permissions audit | A headless agent's effective permission boundary is its spawn-time working directory (`claude -p` auto-denies every prompt, so cwd + `--settings` rules ARE the whole boundary). Fixing a too-narrow cwd by widening to `$HOME` is the opposite failure: it exposes credential stores (`~/.claude`, `~/.ssh`, `~/appdata/**`), lets the agent read/EDIT the assistant's own `~/.claude/.../MEMORY.md` (a persistent cross-session injection vector), and collapses every session onto one shared `~/.claude` project slug. Least privilege = a fresh per-session workspace dir + a per-session `--settings` file (kept OUTSIDE that workspace so the agent can't edit its own grants) carrying narrow `allow` (specific contract files), scoped `additionalDirectories`, and explicit `deny` over the credential/history stores. Verify the mechanism against the real CLI before assuming (Claude Code honors allow/deny/additionalDirectories headless; absolute rule paths need a `//` prefix — a single slash silently no-matches), and mutation-prove the PRODUCTION spawn path, not just the fallback. | maestro PR #8; `node test/maestro-security-test.js` checks B10–B12
