# Configurable Agent Framework and PB Primitive

This repository is a portable, provider-neutral framework for purpose-specific
agents. Its original two-model development loop is the **PB core**: Planner
reasons and Builder implements. Additional specialists are registered in
`roles.config.json`. See `AGENT-FRAMEWORK.md` for the complete architecture,
routing design, and agent-creation process.

## The PB core

| Role | Does | Model |
|------|------|-------|
| **planner** | read-only planning, architecture, root-cause analysis, sequencing, and approach review | configurable reasoning-tier class |
| **builder** | senior engineering: complex systems, implementation, builds/tests; may delegate clearly outlined subtasks to L1 | configurable coding-tier class |

**Loop:** reason with Planner → hand the plan to Builder → build → verify.
Trivial lookups and one-line edits may remain inline. The existing `/pb` and
`/pbg` commands remain the PB interface. Planner is not the universal default:
domain-specific work may route directly to a confirmed specialist, ambiguous or
routine work uses Runner, and a small explicitly outlined implementation may use
L1. Planner does not call specialists itself; it recommends the next role and
the parent orchestrator owns handoff. Builder may narrowly delegate to L1 or
FE-Designer when its harness exposes those tools.

## Single source of truth

Everything is driven by [`roles.config.json`](./roles.config.json):

- `roles.planner` and `roles.builder` preserve the PB compatibility surface.
- `agents` contains the specialist profiles.
- `providers` names wire protocols and environment-variable names. Secrets do
  not belong in this file. Use a recognised provider key — `anthropic`,
  `openai`, `deepseek`, `openrouter` — because consumers map a role to a harness
  by that key, not by the provider's declared type.

<!-- BEGIN GENERATED: roster (apply.py docs) -->
Beyond the `planner`/`builder` core there are 9 specialists: `runner`, `tech-writer`, `prose-writer`, `l1-programmer`, `librarian`, `fe-designer`, `code-reviewer`, plus 2 direct-call-only profiles that must never be auto-selected — `team-leader`, `audit`.
<!-- END GENERATED: roster -->

This shared registry is harness-neutral. Claude Code, Codex, dsh, Pi and generic
consumers all resolve its Planner/Builder defaults (`fable`/`opus` on Anthropic)
unless a project-level config exists. Pi resolves the shared registry exactly
like every other harness; its former OpenRouter overlay was removed on
2026-07-26.

Each model has a configurable `class`, optional pinned `id`, and `provider`.
Pinned ids win over classes. Use aliases when automatic provider upgrades are
wanted. Run `apply.py set <role-or-agent> <class>` to change a model.

The config is checked by [`roles.schema.json`](./roles.schema.json) and
`apply.py validate`. `routing.postWorkflowAudit` adds a compact read-only review
at medium thinking after completed Planner → executor work; it checks the plan,
result evidence, omissions, and follow-up without editing or delegating. This is
separate from the full direct-call Audit specialist, which directly investigates
and repairs harness/runtime failures without invoking delegated agents.

<!-- BEGIN GENERATED: auditor-models (apply.py docs) -->
The two review roles run on `sonnet` for the light post-workflow audit and `fable` for the direct-call Audit profile. Both are Anthropic models chosen to differ from the builder's, which is model-level independence, not cross-family independence — say so when an artifact ranks or compares AI models.
<!-- END GENERATED: auditor-models -->

`router.py` supplies deterministic, explainable applicability recognition.
When `routing.automaticSelection.enabled` is true, a supporting harness may
offer a handoff but must obtain confirmation before delegation; no agent is
silently dispatched. Team Leader and Audit are always direct-call-only.

## Usage

```bash
python3 apply.py validate
python3 apply.py show
python3 apply.py generic
python3 apply.py claude --dry-run
python3 apply.py knowledge
python3 router.py --explain "Update the Vault index"
python3 apply.py set l1-programmer sonnet --no-apply
```

`apply.py claude` renders the existing Planner/Builder adapters plus a generic
Claude Code adapter for each configured specialist. Generated files are not
hand-edited.

## Looping until a condition holds

The plain loop (`/pb`) runs one plan→build pass. **`/pbg <task> until:
<condition>` is the portable bounded loop** — plan → build → verify, repeated
until the condition holds — and it is the form to name in any harness-neutral
instruction, because it needs nothing from the harness. Some harnesses also have
a native, harness-enforced goal loop (Claude Code's `/goal` + Stop-hook, dsh's
`/goal`); those are stronger where they exist and absent everywhere else, so they
belong in that harness's adapter, not in the shared contract.

## Adapters

- **Claude Code:** `apply.py claude` generates PB commands/subagents and
  specialist profiles from the registry, with a real `model:` field. It is the
  only adapter that emits one, and it refuses to render a profile whose model
  Claude Code cannot dispatch.
- **Codex and dsh:** `install_harness.py codex|dsh` renders every profile as a
  native skill (`<root>/agent-<key>/SKILL.md`). Neither harness can dispatch the
  registry's model classes, so neither emits a model field; each profile states
  which model actually runs.
- **Hermes:** the same skill surface, including `planner` and `builder`.
  Hermes's active model comes from its own harness configuration.
- **Pi:** the global PB addon resolves this shared registry — there is no Pi
  overlay any more, though one is still honored if reintroduced. Completed
  Planner → executor work, including each `/pbg` round, runs the configured
  light workflow audit before reporting. `/route <task>` runs the same local
  recommendation router and asks for confirmation; see `adapters/pi/README.md`
  for precedence.
- **Anything else:** `apply.py generic` prints a portable description of the PB
  core and specialist registry to paste into a system prompt.

## Durable agent knowledge

`agent-knowledge/<key>/PROFILE.md` is regenerated by `apply.py knowledge` from
the registry; it documents each agent's specialty, information gathering, and
boundaries. Each neighboring `LESSONS.md` is deliberately preserved and stores
only generalized, evidence-backed practices—never secrets, personal data, or
task logs. Agents read these files before substantive work and may add one
lesson afterward when the project permits the mutation.

## Portability rules

- Durable state is normal repository files, not one harness's chat memory.
- No provider/model is the only path; change configuration rather than code.
- No credentials or secrets are placed in config or generated prompts.
- A host's tool permissions remain authoritative; metadata is not a security
  bypass.
