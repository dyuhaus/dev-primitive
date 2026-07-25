# Configurable Agent Framework

This repository defines a portable registry of purpose-specific agents. The
shared `roles.config.json` is provider- and harness-neutral; `roles.schema.json`
describes the data shape, and `apply.py` validates and renders adapters. Pi alone
has a complete runtime overlay at `adapters/pi/roles.config.pi.json` for its PB
models; other harnesses never consume that file.

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
- **Light workflow audit** is an automatic, read-only post-step after completed
  Planner → Builder or Planner → specialist work. It uses GPT-5.6 Sol with
  medium thinking to check plan adherence, evidence, omissions, and follow-up;
  it is intentionally smaller than the direct-call Audit specialist and never
  edits or delegates.
- **Audit** reproduces and repairs failures in AI harnesses, routing,
  extensions, runtime processes, and developer-tool integrations. It works
  directly without delegated agents, updates both durable source and installed
  surfaces, and verifies reinstall/PR preservation. It uses GPT-5.6 Sol through
  OpenRouter and is **direct-call-only**.
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

Pi uses `adapters/pi/roles.config.pi.json` only after project-local configs
have been considered. It currently sets Planner to Kimi K3 and Builder to
GPT-5.6 Terra through OpenRouter. Claude Code, Codex/generic consumers, and
other harnesses continue to resolve shared Planner/Builder values.

Useful commands:

```bash
python3 apply.py validate
python3 apply.py validate --config adapters/pi/roles.config.pi.json
python3 apply.py show
python3 apply.py generic
python3 apply.py set l1-programmer sonnet --no-apply
python3 apply.py claude --dry-run
# Pi only — --no-apply prevents generating Claude agents from the overlay:
python3 apply.py set planner moonshotai/kimi-k3 --provider openrouter \
  --config adapters/pi/roles.config.pi.json --no-apply
```

`apply.py claude` renders the PB adapters and one generic Claude Code adapter
for every configured specialist. The generated files are not hand-edited.

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

After each completed Planner → Builder workflow, supporting adapters run one
small post-workflow audit using `routing.postWorkflowAudit` (GPT-5.6 Sol,
medium thinking by default). The reviewer receives the task, plan, and executor
evidence; it is read-only, does not delegate, and appends an advisory verdict.
It does not replace the full explicit `/audit` specialist.

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
14. Update this document with the agent's purpose, boundaries, invocation rule,
    and examples. Review for least privilege, escalation loops, and secret
    leakage before merging.

The source config, schema, generator, adapter template, tests, and documentation
must be changed together so a future harness can consume the same registry.
