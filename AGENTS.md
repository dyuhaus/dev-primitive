# dev-primitive — Agent Guide

This repository supports Codex only. `AGENTS.md` is its project entrypoint.

## Project

The Codex agent registry for this machine: one portable
`roles.config.json` describing every agent profile, plus generators that render
it into Codex's native surface.

- `roles.config.json` — the single source of truth. Never hand-edit a generated
  file; change this and regenerate.
- `roles.schema.json` — the data shape, including which provider key names
  consumers actually recognise.
- `apply.py` — validation, Codex skills, generated knowledge profiles and
  generated documentation; retired adapters are not installable.
- `router.py` — deterministic, explainable applicability routing. Always
  confirmation-required; it never dispatches.
- `install_harness.py` — installs those surfaces and mirrors the shared
  `~/skills` roots into Codex's skill directory. It is the **only**
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

### Codex-only operation

Codex is the only supported runtime and installation target. Planner -> Builder
is explicit-invocation only, both roles use `gpt-6-astra` at xhigh, and neither task size
nor a router recommendation automatically starts it. Automatic workflow audit
is disabled. Requested reviews use `gpt-5.6-sol`; other specialists remain registry-configured on Codex.
`install_harness.py all` means Codex and shared skill links only. Retired targets
refuse before writing. See HARNESS-INSTALLATION.md for exact source/live checks.

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
- Deploy coupling: installed `~/.codex/skills` are generated copies. Install
  from verified merged source and compare the installed surface afterward.
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
