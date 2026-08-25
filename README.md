# dev-primitive

A small, portable, provider-neutral primitive for configurable task agents.
The original two-model loop remains the **PB core**: one model *plans and
reasons*, another *scripts and builds*. It now also registers purpose-specific
specialists.

<!-- BEGIN GENERATED: roster (apply.py docs) -->
Beyond the `planner`/`builder` core there are 9 specialists: `runner`, `tech-writer`, `prose-writer`, `l1-programmer`, `librarian`, `fe-designer`, `code-reviewer`, plus 2 direct-call-only profiles that must never be auto-selected — `team-leader`, `audit`.
<!-- END GENERATED: roster -->

See [`AGENT-FRAMEWORK.md`](./AGENT-FRAMEWORK.md) for the architecture and
future agent-creation process.

```
planner  →  reasoning-tier model  →  architecture, design, root-cause, sequencing, review
builder  →  coding-tier model     →  writing/editing code, running builds & tests, applying the plan
```

**Loop:** reason with the planner → hand its plan to the builder → build → verify.
The session's main loop is an *orchestrator* that routes each kind of work to the
right model instead of doing both itself. Trivial lookups and one-line edits stay
inline. Planner is the entry point for substantive generic engineering, not for
every prompt: confirmed domain specialists, Runner, and explicitly outlined L1
work can be direct destinations. Planner recommends handoffs; it does not spawn
other specialists itself.

## Quickstart

```bash
python3 apply.py validate    # check config, print the resolved role/model table
python3 apply.py claude      # manual-only: renders only an Anthropic-compatible registry
python3 apply.py generic     # print a paste-in block for any other harness
python3 apply.py all         # knowledge + portable block; retires stale generated Claude PB/profiles
python3 apply.py knowledge    # regenerate agent-knowledge/*/PROFILE.md; preserve LESSONS.md
python3 router.py --explain "Update the Vault index"  # recommend a specialist
python3 apply.py set builder --effort xhigh   # change a role's effort + refresh existing surfaces
```

No third-party dependencies (Python 3.8+ stdlib only).

## The one knob: `roles.config.json`

`roles.planner` and `roles.builder` preserve the PB interface. Specialist
profiles live under the optional `agents` registry and each has its own model,
capabilities, boundaries, invocation policy, and escalation/delegation rules.
`router.py` deterministically recognizes applicable agents and supplies an
explainable handoff. Pi can offer that handoff automatically, but it always
requires the user's confirmation before delegation. Completed Planner →
Builder/specialist workflows receive a small read-only audit at xhigh effort
before the final report; it is separate from the full Audit agent, which is
explicitly invoked for AI-harness/runtime bug audits and does not call delegated
agents. Team Leader and Audit are direct-call-only and cannot be selected by the
router.

<!-- BEGIN GENERATED: auditor-models (apply.py docs) -->
The two review roles run on `gpt-5.6-sol` on `openai` at `xhigh` for the light post-workflow audit and `gpt-5.6-sol` on `openai` at `xhigh` for the direct-call Audit profile. Both use the active OpenAI routing and the configured `xhigh` effort; they are distinct from the Terra build/action path.
<!-- END GENERATED: auditor-models -->

Everything is driven by [`roles.config.json`](./roles.config.json) — the single
source of truth. Each role has a **customizable model class**:

```jsonc
"planner": { "model": { "class": "gpt-5.6-sol", "id": "", "provider": "openai", "effort": "xhigh" }, "readOnly": true }
"builder": { "model": { "class": "gpt-5.6-terra", "id": "", "provider": "openai", "effort": "xhigh" }, "readOnly": false }
```

- **`class`** — the model class/alias (for example `gpt-5.6-sol` or
  `gpt-5.6-terra`).
- **`id`** — optional exact model to pin. When set it
  overrides `class`.
- **`effort`** — validated reasoning effort (`low`, `medium`, `high`, `xhigh`,
  or `max`); active OpenAI automation roles require `xhigh`.
- **`provider`** — a key into the `providers` map, naming the wire protocol and
  the **env vars** for the API key / base URL. Consumers map a role to a harness
  by the provider's *key*, so use one of the recognised keys — `anthropic`,
  `openai`, `deepseek`, `openrouter` — and not a private synonym: a DeepSeek
  endpoint keyed `dsh` validates cleanly and is then silently unroutable.

This shared file is harness-neutral: its active Planner/Builder assignments are
`gpt-5.6-sol` and `gpt-5.6-terra` on OpenAI at `xhigh`, unless a project-level
config overrides them. `routing.postWorkflowAudit` uses Sol at `xhigh`.

**A model class is only useful on a harness that can dispatch it.** Claude Code
resolves a subagent's `model:` against Anthropic classes and `claude-*` ids and
**silently discards** anything else, running the session model instead — so
`apply.py` refuses to render a Claude profile it cannot dispatch, and refuses to
write a registry change that would produce one. The active registry therefore
does not generate Claude profiles. In Codex, direct profile adoption runs on
the current session model; delegated work must explicitly pass the registry
`model` and `reasoning_effort` to `spawn_agent`.

Pi previously carried its own OpenRouter overlay; it was removed on 2026-07-26.
Reintroducing one is a supported path — drop a `roles.config.pi.json` back into
`adapters/pi/` and `install_harness.py` will validate and honor it — but nothing
requires it.

Change a model by editing this file and re-running `apply.py`; with no overlay
in play that single edit applies to every harness at once. The config is
validated by
[`roles.schema.json`](./roles.schema.json) and by `apply.py validate`. **No
secrets live here — only the names of env vars.**

## Adding it to any harness

An *adapter* turns the config into whatever a harness understands:

<!-- BEGIN GENERATED: harness-surfaces (apply.py docs) -->
| Harness | Surface | Result |
|---|---|---|
| Claude Code | `~/.claude/agents/` and `~/.claude/commands/` | Manual-only adapter. It can render PB subagents and commands only for an Anthropic-compatible registry; the active OpenAI registry is intentionally refused, and `all` retires only its manifest-owned stale PB/profile files. |
| Codex | `~/.codex/skills/agent-*/SKILL.md` | One skill per profile plus `agent-framework`, `agent-pb`, `agent-route`. Direct adoption runs on the current session model; delegated work must set the registry model and reasoning effort explicitly. `codex review` is the native review path. |
| dsh | `~/.dsh/skills/agent-*/SKILL.md` | The same skill set through dsh's filesystem skill provider (`user-dsh` root). No model routing: dsh dispatches DeepSeek models. Delegation exists through its `subagent` tool but carries no per-profile model. |
| Pi | `~/.pi/agent/extensions/pb-primitive/` | PB tools plus a generated `<key>_agent` tool per profile, resolved from this same registry. |
| Hermes | `~/.hermes/skills/agent-*/SKILL.md` | One skill per profile including `planner` and `builder`. Hermes's active model comes from its own harness configuration. No Hermes CLI is installed today. |
<!-- END GENERATED: harness-surfaces -->

Install them with `python3 install_harness.py <pi|claude|codex|dsh|hermes|skills|all>`.
`install_harness.py skills` additionally mirrors the shared `~/skills` roots into
every harness's skill directory, so a Codex or dsh session is not silently
missing `git-workflow`, `subsite-scaffold`, `decommission-checklist` and
`harden-service` while its instructions assume it has them.

For a harness with no adapter, `apply.py generic` prints a portable Markdown
block (roles + resolved classes) to paste into `AGENTS.md` or a system prompt,
and any programmatic client can read `roles.config.json` directly.

To support a **new** harness: add `adapters/<harness>/` templates and a small
render function in `apply.py`. A skill-based harness needs only the four
`*.SKILL.md.tmpl` files that `adapters/codex/` shows. **If the harness cannot
dispatch the registry's model classes, do not emit a model field** — render an
honest sentence saying which model actually runs. The config never changes.

**Every free-text value a template puts in YAML frontmatter must come from
`yaml_scalar()`**, which double-quotes it. Registry text is free prose: four of
the eleven `purpose` strings contain a colon-and-space, and interpolated raw
that reads as a nested mapping. dsh's skill loader then *drops the whole skill*
and writes one line to its log — measured, four of fourteen gone, including both
PB roles and the mandatory reviewer, with nothing in the catalog to say so.

A rendered frontmatter value may only be one of five shapes — verified against
all 78 files the four adapters currently render, with nothing else present:

- a **`yaml_scalar()`** value — the only form allowed for interpolated registry
  text on a single line;
- a **hand-written quoted literal** in the template, for prose no registry edit
  can reach (`route.md.tmpl`'s `description:`);
- a **bare identifier or comma-separated list of them** — `name: runner`,
  `model: sonnet`, `tools: Read, Grep, Glob`, the form Claude Code's own shipped
  agents use;
- a **block scalar** (`description: >-`) whose body stays indented past the key;
- an **empty value opening a nested mapping** (Hermes's `metadata:`), whose
  children obey the same rules.

`check_frontmatter()` runs on every rendered file of **every** adapter, Claude
Code included, and fails the build rather than let any other shape through. It
is stdlib-only, so it holds without PyYAML, and adds a real parse when PyYAML is
importable. Do not add an adapter that skips it. That claim was false when it
was first written: the three skill adapters were checked and the Claude adapter
— the one actually installed on this machine — was not, so a purpose containing
a colon rendered an unloadable slash command and `apply.py claude` exited 0.

## Layout

```
roles.config.json        single source of truth (edit this)
roles.schema.json        JSON-Schema validator
apply.py                 stdlib-only generator / validator
router.py                deterministic explainable recommendation router
agent-knowledge/         generated specialty profiles and preserved durable lessons
PRIMITIVE.md             full harness-neutral spec
adapters/claude-code/    planner / builder / PB / specialist / route templates
```

See [`PRIMITIVE.md`](./PRIMITIVE.md) for the full spec and design rules.
