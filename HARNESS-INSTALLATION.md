# Harness-level installation

The agent framework is now installed at the harness level rather than being
available only inside this repository.

## Source and installed surfaces

`/home/dyadmin/dev-primitive/` remains the portable source of truth:

- `roles.config.json` — harness-neutral profiles and models
- `roles.schema.json` — structure
- `apply.py` — validation, Claude rendering, and generated knowledge profiles
- `router.py` — deterministic, explainable applicability routing with confirmation-required handoff
- `agent-knowledge/` — generated profiles plus preserved durable lessons
- `install_harness.py` — cross-harness installation

Installed surfaces:

<!-- BEGIN GENERATED: harness-surfaces (apply.py docs) -->
| Harness | Surface | Result |
|---|---|---|
| Claude Code | `~/.claude/agents/` and `~/.claude/commands/` | PB subagents, `/pb`, `/pbg`, `/route`, `/agent-catalog`, and a `/<agent>` + `/<agent>-model` pair per profile. The only adapter that writes a `model:` field, and the only one that can dispatch the registry's Anthropic classes. |
| Codex | `~/.codex/skills/agent-*/SKILL.md` | One skill per profile plus `agent-framework`, `agent-pb`, `agent-route`. No model routing: Codex dispatches OpenAI models, so every profile runs on the session model. `codex review` is the native review path. |
| dsh | `~/.dsh/skills/agent-*/SKILL.md` | The same skill set through dsh's filesystem skill provider (`user-dsh` root). No model routing: dsh dispatches DeepSeek models. Delegation exists through its `subagent` tool but carries no per-profile model. |
| Pi | `~/.pi/agent/extensions/pb-primitive/` | PB tools plus a generated `<key>_agent` tool per profile, resolved from this same registry. |
| Hermes | `~/.hermes/skills/agent-*/SKILL.md` | One skill per profile including `planner` and `builder`. Hermes's active model comes from its own harness configuration. No Hermes CLI is installed today. |
<!-- END GENERATED: harness-surfaces -->

Every profile in the registry is rendered onto every surface:

<!-- BEGIN GENERATED: roster (apply.py docs) -->
Beyond the `planner`/`builder` core there are 9 specialists: `runner`, `tech-writer`, `prose-writer`, `l1-programmer`, `librarian`, `fe-designer`, `code-reviewer`, plus 2 direct-call-only profiles that must never be auto-selected — `team-leader`, `audit`.
<!-- END GENERATED: roster -->

<!-- BEGIN GENERATED: roster-table (apply.py docs) -->
| Key | Display name | Model | Provider | Invocation | Auto-select |
|---|---|---|---|---|---|
| `planner` | Planner | `fable` | `anthropic` | `default` | `false` |
| `builder` | Builder | `opus` | `anthropic` | `default` | `false` |
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

Refresh all supported harnesses:

```bash
python3 /home/dyadmin/dev-primitive/install_harness.py all
# or refresh only one target:
python3 /home/dyadmin/dev-primitive/install_harness.py codex
python3 /home/dyadmin/dev-primitive/install_harness.py skills
```

Preview without writing:

```bash
python3 /home/dyadmin/dev-primitive/install_harness.py all --dry-run
```

The installer regenerates the agent-knowledge profiles, mirrors the shared
`~/skills` roots into every harness's skill directory, syncs the versioned Pi
addon from `adapters/pi/pb-primitive/`, then renders the Codex, dsh, Hermes and
Claude surfaces — in that order, deliberately. The neutral surfaces have nothing
to do with any one harness's model-dispatch limits, so a profile the Claude
adapter cannot render makes `all` warn and skip **that one adapter** while
everything else still installs. `install_harness.py claude` on its own still
fails hard, because there the refusal is the answer.

The shared-skills step is additive: an existing entry is left exactly as it is
and nothing is ever removed. Without it a Codex session carries a handful of the
shared skills and none of `git-workflow`, `subsite-scaffold`,
`decommission-checklist` or `harden-service`, while its instructions assume it
has them.

The installer contains no credentials and never prints secret values. Generated
files should not be hand-edited; update the source registry and reinstall.

## Model behavior

Every harness resolves Planner/Builder from the shared harness-neutral registry:
`fable` and `opus` on Anthropic. Pi, when no project-level roles config is
present, resolves that same shared registry exactly like the other harnesses —
its OpenRouter overlay was removed on 2026-07-26 — and Pi project configs still
win where one exists.

**Resolving a model and dispatching it are different things.** Only the Claude
Code adapter writes a `model:` field, and it can do so because Claude Code
resolves Anthropic classes and `claude-*` ids. It also *silently discards*
anything else and runs the session model, so `apply.py` refuses to render a
Claude profile it cannot dispatch rather than emitting a file that lies. Codex
dispatches OpenAI models and dsh dispatches DeepSeek models, so their rendered
profiles carry no model field at all and state plainly that the profile runs on
the session model. Hermes skills carry the registry's routing intent as
metadata, while Hermes's active model comes from its own harness configuration.

Pi offers explicit `/<agent>` slash commands for every profile and
`/<agent>-model` commands; `/agents` is its native catalog, listing every
available agent command and the effective active model assignment.

Changing a model is one command — `apply.py set <role-or-agent> <class>` — and
it refreshes **every surface that is already installed**, not Claude Code's
alone. It also renders every present adapter against the in-memory config before
writing, so a rejected change leaves the registry and the installed surfaces
still agreeing rather than disagreeing three ways.

Two limits on that refresh, both deliberate:

- **It updates; it never installs.** `set` rewrites generated files that already
  exist and creates none. `~/.dsh` existing means dsh is installed on the
  machine, not that this primitive has ever written a profile into it — a
  routine model switch must not stand up a harness surface nobody asked for.
  When a surface is missing, `set` says so and names the install command.
  Installing is `install_harness.py <harness>`, run on purpose.
- **Only Claude Code can veto a model.** It is the one adapter that resolves a
  `model:` field, so it is the one that can reject a model class. The skill
  adapters render the configured model as prose and will render anything, so
  `set` reports them as *rendered*, never as having *validated* the model. On a
  machine with no Claude Code, `set` says plainly that nothing checked the class.

Note the division of labour between the two entry points: `install_harness.py`
mirrors the shared `~/skills` roots into each harness, and `apply.py` never does
that at any action.

Completed Planner → executor workflows also run the configured lightweight audit
at medium thinking; it is read-only and distinct from `/audit`.

<!-- BEGIN GENERATED: auditor-models (apply.py docs) -->
The two review roles run on `sonnet` for the light post-workflow audit and `fable` for the direct-call Audit profile. Both are Anthropic models chosen to differ from the builder's, which is model-level independence, not cross-family independence — say so when an artifact ranks or compares AI models.
<!-- END GENERATED: auditor-models -->

## Routing behavior

`routing.postWorkflowAudit` configures the small post-workflow reviewer used by
Pi and generated Claude PB flows. It receives the task, plan, and executor
evidence, then appends a concise advisory verdict without editing or delegation.

`router.py` classifies a task deterministically and returns an explainable
applicability result. Pi automatically offers an eligible handoff when
`enabled: true`, while Claude and Pi `/route` show it on demand. Every path
requires confirmation and never silently invokes any profile; the portable
alternative is:

```bash
python3 /home/dyadmin/dev-primitive/router.py --explain 'task'
```

Runner is the low-confidence fallback. With `planBeforeBuild` enabled, generic
substantive implementation is confirmed as a Planner handoff and Pi then runs
Planner → Builder; direct specialist matches and explicitly outlined L1 work do
not pay that planning round-trip. Planner recommends specialists but does not
invoke them. Team Leader and Audit have `direct-call-only` semantics in every
adapter and are hard-excluded from routing. Invoke `/audit` explicitly for
harness/runtime audits that must work directly without Planner, Builder, or
other delegated agents.

Run `python3 /home/dyadmin/dev-primitive/apply.py knowledge` to refresh the
generated specialty profiles. It preserves `agent-knowledge/*/LESSONS.md`.

## Verification

```bash
cd /home/dyadmin/dev-primitive
python3 apply.py validate
python3 -m unittest discover -s tests -v
python3 router.py --explain 'Update the Vault index and fix broken wikilinks'
python3 apply.py knowledge
python3 apply.py docs                       # must report no drift
node ~/.pi/agent/extensions/pb-primitive/_selftest.mjs
python3 install_harness.py all --dry-run
```

A behavioural check for the model-routing guard, run against a **scratch copy**
of the registry so the real one is never touched:

```bash
cp roles.config.json /tmp/scratch-roles.json
python3 - <<'EOF'
import json; c=json.load(open('/tmp/scratch-roles.json'))
c['roles']['planner']['model']['class']='gpt-5.6-terra'
json.dump(c, open('/tmp/scratch-roles.json','w'))
EOF
python3 apply.py claude --config /tmp/scratch-roles.json --home /tmp/scratch-home --dry-run
# expected: exit 1, naming roles.planner, emitting no files
python3 apply.py all --config /tmp/scratch-roles.json --home /tmp/scratch-home --dry-run
# expected: exit 0, a warning that the Claude adapter was skipped, neutral
# surfaces still rendered
```

To roll back an installation, remove only the generated `agent-*` skill
directories and the specialist Claude files, then reinstall the prior source
configuration. Do not remove unrelated user skills, agents, sessions, or
credentials — and note that the shared-skill symlinks are not generated content:
leave them alone.
