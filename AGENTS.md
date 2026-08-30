# dev-primitive — Agent Guide

This repository is model- and harness-agnostic. `AGENTS.md` is the portable
entrypoint for Codex, Hermes, Claude Code, and any future assistant harness.

## Project

The portable agent registry for this machine: one harness-neutral
`roles.config.json` describing every agent profile, plus generators that render
it into each harness's native surface.

- `roles.config.json` — the single source of truth. Never hand-edit a generated
  file; change this and regenerate.
- `roles.schema.json` — the data shape, including which provider key names
  consumers actually recognise.
- `apply.py` — validation, the Claude Code adapter, the Codex/dsh/Hermes skill
  adapters, the generated knowledge profiles, and the generated doc blocks.
- `router.py` — deterministic, explainable applicability routing. Always
  confirmation-required; it never dispatches.
- `install_harness.py` — installs those surfaces and mirrors the shared
  `~/skills` roots into every harness's skill directory. It is the **only**
  entry point that mirrors shared skills, and the only one that creates a
  harness surface; `apply.py set` refreshes surfaces that already exist and
  never adds one.
- `adapters/<harness>/` — templates. `agent-knowledge/` — generated `PROFILE.md`
  plus **preserved** `LESSONS.md`; never regenerate a lessons file away.

Native checks, all of which must pass before a PR:

```bash
python3 apply.py validate
python3 -m unittest discover -s tests
python3 apply.py docs                     # must report no drift
python3 install_harness.py all --dry-run
```

### What each harness can actually do here

`AGENTS.md` is read by Codex and dsh, and both get native profile skills. The
active registry is OpenAI-only: `gpt-5.6-sol` at `xhigh` for planning/audit/review
and `gpt-5.6-terra` at `xhigh` for build/action roles. In Codex, direct profile adoption uses
the current session model; a delegated child must receive explicit
`spawn_agent` `model` and `reasoning_effort` values. dsh cannot dispatch the
active OpenAI routing. The manual Claude adapter refuses this registry because
Claude discards an unresolvable `model:` value silently; `all` retires only
manifest-owned stale generated Claude PB/profile files.

Codex additionally has a native `codex review` subcommand, but automated review
is currently on-demand only. David reviews and merges pull requests in GitHub.
Hermes has no delegation mechanism at all.

## Rules

- Read `/home/dyadmin/AGENTS.md` first for the machine-level contract.
- Read this repo's `README.md`, manifests, scripts, and tests before changing
  behavior.
- Never read, print, commit, or publish secrets, local `.env` values,
  credentials, or private user data.
- Keep durable state in repo files and deterministic scripts, not in one
  harness's memory or chat history.
- Use the project's native test/build commands for validation; document any
  missing or unavailable checks.

## Git Workflow (machine standard)
This repo follows /home/dyadmin/AGENTS.md "Git Workflow Standard".
- Default branch: main (protected, PR-only, squash merge)
- Branches: feat/ fix/ chore/ docs/ exp/ (+ agent/<harness>/ optional)
- Commits: Conventional Commits; hooks must pass; never --no-verify
- Review: open the PR for David to review in GitHub. No automated review or
  certificate is required.
- Merge: David approves and squash-merges every PR. Agents never approve,
  merge, enable auto-merge, or use a relay.
- Deploy coupling: none for the repo itself — but `~/.claude/agents`,
  `~/.claude/commands` and each harness's `~/.<harness>/skills` are generated
  FROM it, so a template change is not landed until the installer has been
  re-run and the installed surface matches.
- Long-lived branch exceptions: none

## Traps this repo has actually hit

- **A guard that cannot fire.** The model guard was keyed on the `provider`
  field, which `apply.py set` never touches, and was called from one place, so
  it covered neither the PB roles nor the path the documented one-liner used.
  Key a guard on the value that actually changes, and prove it fires.
- **Writing before validating.** `set` persisted the registry and guarded
  afterwards, so a rejected change left the source of truth changed and every
  surface stale. Render every adapter against the in-memory config first.
- **A hand-written roster drifts.** The docs said eight specialists while the
  registry held nine. The roster line and roster table are generated now; run
  `python3 apply.py docs` and a test fails the build if they go stale.
