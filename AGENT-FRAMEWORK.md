# Configurable Agent Framework

This repository defines a portable registry of purpose-specific agents. The
shared `roles.config.json` is provider- and harness-neutral; `roles.schema.json`
describes the data shape, and `apply.py` validates and renders adapters. Pi
resolves the same shared registry as every other harness; its OpenRouter overlay
was removed on 2026-07-26.

<!-- BEGIN GENERATED: roster (apply.py docs) -->
Beyond the `planner`/`builder` core there are 9 specialists: `runner`, `tech-writer`, `prose-writer`, `l1-programmer`, `librarian`, `fe-designer`, `code-reviewer`, plus 2 direct-call-only profiles that must never be auto-selected — `team-leader`, `audit`.
<!-- END GENERATED: roster -->

<!-- BEGIN GENERATED: roster-table (apply.py docs) -->
| Key | Display name | Model | Provider | Invocation | Auto-select |
|---|---|---|---|---|---|
| `planner` | Planner | `gpt-5.6-sol` | `openai` | `default` | `false` |
| `builder` | Builder | `gpt-5.6-terra` | `openai` | `default` | `false` |
| `runner` | Runner | `gpt-5.6-terra` | `openai` | `default` | `true` |
| `tech-writer` | Tech Writer | `gpt-5.6-terra` | `openai` | `default` | `true` |
| `prose-writer` | Prose Writer | `gpt-5.6-terra` | `openai` | `default` | `true` |
| `team-leader` | Team Leader | `gpt-5.6-terra` | `openai` | `direct-call-only` | `false` |
| `l1-programmer` | L1 Programmer | `gpt-5.6-terra` | `openai` | `default` | `true` |
| `librarian` | Librarian | `gpt-5.6-terra` | `openai` | `default` | `true` |
| `fe-designer` | FE-Designer | `gpt-5.6-terra` | `openai` | `default` | `true` |
| `audit` | Audit | `gpt-5.6-sol` | `openai` | `direct-call-only` | `false` |
| `code-reviewer` | Code Reviewer | `gpt-5.6-sol` | `openai` | `default` | `false` |
<!-- END GENERATED: roster-table -->

## Architecture

- **Runner** is the everyday front door for maintenance, routine work, triage,
  and escalation. It identifies whether a task belongs with another specialist.
- **Planner** and **Builder** are the PB development core. Planner is the
  read-only reasoning specialist. Builder is the senior engineer for complex
  systems and may delegate a clearly outlined, well-scoped subtask to L1 or a
  separable frontend implementation to FE-Designer.
- **L1 Programmer** is the junior/intern implementation specialist for basic
  scripts, tests, small fixes, and explicitly outlined work. It must escalate
  architecture or unclear scope to Builder/Planner.
- **Tech Writer** handles technical documentation: READMEs, references,
  runbooks, architecture notes, and implementation guides.
- **Prose Writer** handles non-technical prose: correspondence, proposals,
  narratives, speeches, and general communications.
- **Librarian** maintains the Vault and documentation information architecture:
  navigation, indexes, cross-links, naming, and structural consistency.
- **FE-Designer** designs and implements accessible, responsive frontend
  components, layouts, interactions, and design-system refinements. Builder
  owns complex system integration; FE-Designer escalates backend, architecture,
  product, and brand decisions rather than guessing them.
- **Code Reviewer** adversarially reviews a branch, diff, or codebase for real
  defects before it reaches main. The Git Workflow Standard makes a pre-PR review
  mandatory on **every** harness, and this is the profile that performs it —
  under Claude Code as `/code-reviewer`, under Codex additionally through the
  native `codex review` subcommand, elsewhere by adopting the profile. It is
  read-only and never fixes what it finds.
- **Light workflow audit** is an automatic, read-only post-step after completed
  Planner → Builder or Planner → specialist work. It checks plan adherence,
  evidence, omissions, and follow-up at `xhigh` effort; it is intentionally
  smaller than the direct-call Audit specialist and never edits or delegates.
- **Audit** reproduces and repairs failures in AI harnesses, routing,
  extensions, runtime processes, and developer-tool integrations. It works
  directly without delegated agents, updates both durable source and installed
  surfaces, and verifies reinstall/PR preservation. It is **direct-call-only**.

<!-- BEGIN GENERATED: auditor-models (apply.py docs) -->
The two review roles run on `gpt-5.6-sol` on `openai` at `xhigh` for the light post-workflow audit and `gpt-5.6-sol` on `openai` at `xhigh` for the direct-call Audit profile. Both use the active OpenAI routing and the configured `xhigh` effort; they are distinct from the Terra build/action path.
<!-- END GENERATED: auditor-models -->
- **Team Leader** coordinates genuinely large tasks that require multiple
  workstreams. It is **direct-call-only** and must never be automatically
  selected or self-invoked.

The profiles intentionally separate mission, model, tools, boundaries,
escalation, delegation, and output expectations. A model change is a config
change, not a prompt edit.

## Configuration

`roles.config.json` contains the shared cross-harness configuration:

- `roles.planner` and `roles.builder`: compatibility entries for the existing PB
  primitive and commands.
- `agents`: specialist profiles keyed by stable machine names.
- `providers`: provider protocol and environment-variable *names*. Secrets never
  belong in this file.
- `routing.postWorkflowAudit`: configures the lightweight model and thinking
  level used after completed Planner → executor workflows.
- `routing.automaticSelection`: configures the deterministic `router.py`.
  `enabled` permits a supporting harness to offer automatic applicability
  recognition; every harness must still obtain confirmation before delegation.

Each specialist profile has:

| Field | Meaning |
|---|---|
| `displayName` | Human-facing name |
| `purpose` | Mission statement |
| `model` | Independent `{class, id, provider}` selection; `class` is always required and `id` optionally pins an exact model |
| `readOnly` / `tools` | Operational permission intent and harness tool list |
| `invocation` | `default` or `direct-call-only` |
| `autoSelectEligible` | Future selector eligibility; must be false for direct-call-only profiles |
| `capabilities` | Positive signals describing suitable work |
| `boundaries` | Non-goals and stop/escalation conditions |
| `escalateTo` | Agent keys that can receive escalation/recommendations |
| `canDelegate` / `delegateTo` | Whether and where this profile may delegate |
| `outputContract` | Required report/result behaviors |
| `infoSources` | Required evidence sources and native inspection/validation guidance |

**Provider posture.** This machine ran Anthropic-only from 2026-07-26; that was
superseded on 2026-08-16 and it is multi-provider now — Codex on OpenAI, Pi on
OpenRouter, dsh on DeepSeek. See the provider-posture paragraph in
`/home/dyadmin/AGENTS.md` for the current position; do not treat the older
Anthropic-only wording anywhere as a live rule.

The active registry is OpenAI-only: Sol at `xhigh` for planning/audit/review and
Terra at `xhigh` for build/action roles. What remains a live constraint is
**dispatchability, which is per harness**:

| Adapter | Can dispatch | Emits a `model:` field |
|---|---|---|
| Claude Code | Anthropic classes (`opus`, `sonnet`, `haiku`, `fable`, …) and `claude-*` ids | yes |
| Codex | OpenAI models | no |
| dsh | DeepSeek models | no |
| Pi | OpenRouter and Anthropic | no (routes through its own tools) |
| Hermes | nothing — model comes from its harness config | no |

Claude Code **silently discards** a `model:` value it cannot resolve and runs the
subagent on the session model, so its manual adapter refuses the active OpenAI
registry. `all` then retires only manifest-owned stale generated Claude
PB/profile files. For Codex, direct adoption states that it uses the current
session model; delegation must explicitly set `spawn_agent` `model` and
`reasoning_effort`. Other adapters do not pretend to dispatch unsupported
registry models.

The Pi-only OpenRouter overlay (`adapters/pi/roles.config.pi.json`) was removed
on 2026-07-26; Pi's `config.ts` falls back to the shared registry when no overlay
exists, and `install_harness.py` treats an absent overlay as normal. A
project-local `roles.config.json` still overrides.

Useful commands:

```bash
python3 apply.py validate
python3 apply.py show
python3 apply.py roster                    # the canonical roster line
python3 apply.py generic
python3 apply.py docs                      # refresh the generated doc blocks
python3 apply.py set l1-programmer --effort xhigh --no-apply
python3 apply.py claude --dry-run
python3 install_harness.py all --dry-run   # every harness surface + shared skills
```

`apply.py claude` is manual-only and requires an Anthropic-compatible registry;
the active registry is intentionally refused. `install_harness.py codex|dsh|hermes`
renders native skills. The generated files are not hand-edited.

## Explainable routing

`router.py` is a stdlib-only, deterministic applicability classifier. It extracts
artifact, action, complexity, outline, Vault, documentation, prose, frontend,
and routine-maintenance signals; scores only eligible profiles; and returns a
JSON-serializable applicability result with reasons, score table, confidence, and
clarifying questions. It never calls a model or silently dispatches work.

```bash
python3 router.py --explain "Update the Vault index and fix broken wikilinks"
python3 router.py --json "Refactor the broker service architecture"
```

After each successfully completed Planner → executor workflow—including every
completed `/pbg` round—supporting adapters run one small post-workflow audit
using `routing.postWorkflowAudit` at the registry's `xhigh` effort.
The reviewer receives the task, plan, executor identity, and executor evidence;
it is read-only, does not delegate, and appends an advisory verdict. It does not
replace the full explicit `/audit` specialist.

Claude and Pi expose the same deliberate flow through `/route <task>`: show the
applicability result, ask for confirmation, then invoke the selected profile only
if approved. With `enabled: true`, Pi also offers this confirmation gate for
eligible ordinary interactive tasks. In noninteractive contexts Pi reports the
result but does not invoke. When `planBeforeBuild` is true, a generic substantive
implementation score is converted to Planner so the confirmed Pi handoff runs
the complete Planner → Builder workflow; an explicit specialist match or a small,
clearly outlined L1 task bypasses PB. Planner itself does not spawn specialists:
it names the recommended next role, and the parent orchestrator performs the
approved handoff. Builder is the only PB child permitted to delegate, narrowly to
L1 Programmer or FE-Designer when the harness exposes those delegation tools.
Low confidence and material ambiguity fall back to Runner. The router hard
excludes `direct-call-only` profiles and `team-leader` regardless of malformed
metadata. Multi-workstream language is reported as a cue to explicitly call Team
Leader, never as a selection. Optional audit records are JSONL with a SHA-256
hash and decision metadata only—never raw task text—and are disabled by default.

Use Runner for ordinary work and ask it to recommend escalation. Use `/pb` for a
substantive plan → build pass. Call Team Leader directly only when the task needs
multiple agents, for example a product launch requiring software changes,
technical docs, user-facing prose, and Vault updates with dependencies between
them.

Examples:

- “Clean up this service's logs and update its runbook” → Runner may perform
  maintenance and escalate the runbook portion to Tech Writer.
- “Add a small parser from this exact outline and write tests” → L1 Programmer.
- “Design and implement a new service with an API, deployment, and migration”
  → Planner then Builder; Builder may delegate isolated scripts to L1.
- “Implement the supplied component spec as a responsive, keyboard-accessible
  interface using this project’s design system” → FE-Designer.
- “Audit this stalled Pi handoff, fix feedback/cancellation, reinstall the
  extension, and preserve the repair in its PR without using other agents” →
  the user explicitly calls Audit.
- “Coordinate the website, docs, launch email, and Vault index across four
  workstreams” → the user explicitly calls Team Leader.

## Agent knowledge and lessons

`agent-knowledge/<profile>/PROFILE.md` documents every profile's specialty,
boundaries, information sources, and output expectations. `apply.py knowledge`
regenerates profiles from the registry but intentionally preserves each
`LESSONS.md`. Before substantive work an agent reads its profile, lessons, and
source material. It may append one generalized evidence-backed lesson afterward;
lessons never contain secrets, personal data, private task content, or task logs.
At 50 dated entries the oldest reusable lessons are consolidated into `## Durable
practices`. See [`agent-knowledge/README.md`](./agent-knowledge/README.md).

## Creating a future agent

1. Choose a stable kebab-case key and a clear display name. Check for collisions
   with PB roles and existing specialist keys.
2. Write one sentence for the mission and list positive capabilities.
3. Define boundaries/non-goals and explicit stop conditions. Say what the agent
   must not decide or change.
4. Decide invocation policy. Use `direct-call-only` for coordinators,
   high-impact roles, or anything that must never be selected implicitly; set
   `autoSelectEligible` to `false` in that case.
5. Choose an independent model `{class, id, provider}`. Use aliases when
   auto-upgrades are desired and pinned ids when reproducibility matters.
6. Set `readOnly` and a minimal `tools` list. Follow the host harness's real
   permission model; metadata must not be treated as a security bypass.
7. Define `escalateTo`, and if delegation is allowed set `canDelegate` and a
   narrow `delegateTo` list. Do not include a target that is not registered.
8. Define an `outputContract`: the facts, validation evidence, assumptions,
   and escalation information every result must report.
9. Define `infoSources`: concrete project material and native checks the
   specialist uses to gather verified information.
10. Add the complete profile under `agents` in `roles.config.json`. Do not add
   keys, tokens, or credentials; provider secrets remain in environment/config
   stores.
11. Run `python3 apply.py validate` and update schema/docs if the profile adds a
    genuinely new field or semantic rule.
12. Regenerate knowledge and inspect adapters with `python3 apply.py knowledge`
    and `python3 apply.py claude --dry-run`. The generic specialist template is
    sufficient for most profiles; add a dedicated template only when behavior
    truly differs.
13. Add deterministic tests for presence, validation invariants, router signals,
    rendered prompt policy, and model configuration. Run the native test suite.
14. Run `python3 apply.py docs` so the roster line and roster table in this
    document, `README.md`, `PRIMITIVE.md` and `HARNESS-INSTALLATION.md` pick the
    new profile up. A test fails the build when they are stale, because a
    hand-written roster has already drifted: the docs said eight specialists
    while the registry held nine, omitting `code-reviewer` — the one profile the
    Git Workflow Standard makes mandatory.
15. Update this document's Architecture section with the agent's purpose,
    boundaries, invocation rule, and examples. Review for least privilege,
    escalation loops, and secret leakage before merging.

The source config, schema, generator, adapter template, tests, and documentation
must be changed together so a future harness can consume the same registry.
