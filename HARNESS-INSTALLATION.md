# Codex installation

> **Codex retired 2026-11-17.** Claude Code is the only harness. Planner runs on Fable and Builder on Opus; specialists use the Anthropic classes in `roles.config.json`. Codex adapter code and its install notes below are retained as history only — do not install them.

Only Codex is supported. Use a verified human-merged source revision; a passing
source test or a model-generated proposal does not authorize live activation.

<!-- BEGIN GENERATED: harness-surfaces (apply.py docs) -->
| Harness | Surface | Result |
|---|---|---|
| Claude Code | `~/.claude/agents/` and `~/.claude/commands/` | Supported. PB and its roles require explicit invocation; each subagent's `model:` comes from the registry and the adapter refuses a class Claude Code cannot dispatch. Automatic workflow audit is disabled. |
| Codex | None installed or refreshed | Retired 2026-11-17. Its renderer is retained as history; installers refuse it. |
| Other harnesses | None installed or refreshed | Decommissioned. Their installers and dispatch entrypoints refuse before launch or writes. Historical source is not activation authority. |
<!-- END GENERATED: harness-surfaces -->

## Native entrypoint

```bash
python3 install_harness.py claude --dry-run
python3 install_harness.py codex
```

`codex` regenerates knowledge and installs Codex profile skills. `skills`
links the shared `~/skills` roots into Codex. `all` performs both. Legacy
`claude`, `dsh`, `pi`, `hermes`, and `gemini` targets refuse before generation
or writes. `apply.py all` renders knowledge, generic reference and Codex only.
No other installed harness surface is refreshed by a model change.

Generated PB, Planner, Builder, router, Audit and Team Leader skills include `agents/openai.yaml`
with `policy.allow_implicit_invocation: false`. The model choices remain in
`roles.config.json`; the PB roles currently resolve to `fable` (Planner) and `opus` (Builder).
Their SKILL.md instructions require explicit invocation. Automatic profile
selection and post-workflow audit are disabled. A full Codex install adds new
metadata; `apply.py set` deliberately does not create absent files.

`--home` changes the target home but not source-side knowledge generation.
For tests, isolate both the source checkout and target home. Never install from
a dirty deployment-coupled checkout. Preserve meaningful local changes and
capture exact file preimages before activation; compare installed artifacts
with the reviewed source and run `harness-check` after changes.

## Verification

```bash
python3 apply.py validate
python3 -m unittest discover -s tests
python3 apply.py docs
python3 install_harness.py all --dry-run
```

Run focused Codex behavioral checks after reviewed installation. Assert the
ordinary-task path, explicit ordered Astra PB path, absent automatic audit,
loader metadata and source-to-live parity. Record any skipped native behavior.
Do not run the retired harnesses or reconstruct R5's cancelled release system.

### Lesson inbox inside the Linux sandbox

Codex can mount an empty, read-only `tmpfs` directory at a writable root's
`.git` path even when that path does not exist on the host. The lesson guard
recognizes only an empty, non-symlink directory with mode `0555` and exactly
one matching read-only `tmpfs` root mount in `/proc/self/mountinfo`. It continues
checking ancestors. Ordinary `.git` directories, worktree pointer files,
symlinks, nonempty mounts, and missing or ambiguous mount evidence still refuse.
No marker is removed and no sandbox permission is changed.

Check the guard in the command's actual mount namespace: a host path check
alone cannot see these sandbox placeholders. The native lesson tests cover
the exception and refusal controls; `python3 tests/control_mutants.py` checks
that removing those rules causes assertion failures.

A separate startup dependency is the native app-server's SQLite state. A
read-only `CODEX_HOME` can prevent initialization before any command is run.
For a supervised local verification, an explicit per-process
`-c sqlite_home="<private-writable-evidence-directory>"` keeps temporary runtime
state separate while preserving the normal config, authentication and skill
locations. Retain startup stderr and the exit status. An outer sandbox must
also permit the approved inbox path; an inner writable-root declaration
cannot make a read-only outer mount writable. Never change managed policy to
force a test to pass.

<!-- BEGIN GENERATED: roster-table (apply.py docs) -->
| Key | Display name | Model | Provider | Invocation | Auto-select |
|---|---|---|---|---|---|
| `planner` | Planner | `fable` | `anthropic` | `direct-call-only` | `false` |
| `builder` | Builder | `opus` | `anthropic` | `direct-call-only` | `false` |
| `runner` | Runner | `sonnet` | `anthropic` | `default` | `true` |
| `tech-writer` | Tech Writer | `sonnet` | `anthropic` | `default` | `true` |
| `prose-writer` | Prose Writer | `sonnet` | `anthropic` | `default` | `true` |
| `team-leader` | Team Leader | `opus` | `anthropic` | `direct-call-only` | `false` |
| `l1-programmer` | L1 Programmer | `haiku` | `anthropic` | `default` | `true` |
| `librarian` | Librarian | `sonnet` | `anthropic` | `default` | `true` |
| `fe-designer` | FE-Designer | `sonnet` | `anthropic` | `default` | `true` |
| `audit` | Audit | `fable` | `anthropic` | `direct-call-only` | `false` |
| `code-reviewer` | Code Reviewer | `fable` | `anthropic` | `default` | `false` |
<!-- END GENERATED: roster-table -->
