# dev-primitive

A small, portable, provider-neutral primitive for configurable task agents.
The original two-model loop remains the **PB core**: one model *plans and
reasons*, another *scripts and builds*. It now also registers purpose-specific
specialists such as Runner, writers, Librarian, FE-Designer, Audit, Team Leader, and L1 Programmer.
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
python3 apply.py claude      # (re)generate the Claude Code adapter (~/.claude/agents + /pb + /pbg)
python3 apply.py generic     # print a paste-in block for any other harness
python3 apply.py all         # Claude adapter, knowledge profiles, portable block
python3 apply.py knowledge    # regenerate agent-knowledge/*/PROFILE.md; preserve LESSONS.md
python3 router.py --explain "Update the Vault index"  # recommend a specialist
python3 apply.py set builder sonnet   # change a role's model + regenerate (easy path)
```

No third-party dependencies (Python 3.8+ stdlib only).

## The one knob: `roles.config.json`

`roles.planner` and `roles.builder` preserve the PB interface. Specialist
profiles live under the optional `agents` registry and each has its own model,
capabilities, boundaries, invocation policy, and escalation/delegation rules.
`router.py` deterministically recognizes applicable agents and supplies an
explainable handoff. Pi can offer that handoff automatically, but it always
requires the user's confirmation before delegation. Completed Planner →
Builder/specialist workflows receive a small read-only GPT-5.6 Sol audit at
medium thinking before the final report. This is separate from the full Audit
agent. Team Leader and Audit are
direct-call-only and cannot be selected by the router. Audit is explicitly
invoked for AI-harness/runtime bug audits and runs on GPT-5.6 Sol without
calling delegated agents.

Everything is driven by [`roles.config.json`](./roles.config.json) — the single
source of truth. Each role has a **customizable model class**:

```jsonc
"planner": { "model": { "class": "fable", "id": "", "provider": "anthropic" }, "readOnly": true }
"builder": { "model": { "class": "opus",  "id": "", "provider": "anthropic" }, "readOnly": false }
```

- **`class`** — the model class/alias (e.g. `fable`, `opus`, `sonnet`, or any
  provider-specific class). On harnesses that support aliases it resolves to the
  newest model in that family, so it auto-upgrades as new models ship.
- **`id`** — optional exact model to pin (e.g. `claude-opus-4-8`). When set it
  overrides `class`.
- **`provider`** — a key into the `providers` map (Anthropic, any
  OpenAI-compatible endpoint incl. OpenRouter, Google, or a local model), which
  names the wire protocol and the **env vars** for the API key / base URL.

This shared file is harness-neutral: Claude Code, Codex/generic consumers, and
other harnesses use its Planner/Builder values (`fable`/`opus` on Anthropic by
default). Pi alone has a complete runtime overlay at
`adapters/pi/roles.config.pi.json`, which currently selects the configured
Planner and GPT-5.6 Terra Builder through OpenRouter only when no project-level
config overrides it. `routing.postWorkflowAudit` independently pins GPT-5.6 Sol
at medium thinking for the compact post-workflow review.

Change a shared cross-harness model by editing this file and re-running
`apply.py`. Change a Pi-only model with `apply.py set --config
adapters/pi/roles.config.pi.json --no-apply`; the final flag prevents generating
Claude agents from Pi values. The config is validated by
[`roles.schema.json`](./roles.schema.json) and by `apply.py validate`. **No
secrets live here — only the names of env vars.**

## Adding it to any harness

An *adapter* turns the config into whatever a harness understands:

| Harness | How |
|---|---|
| **Claude Code** | `apply.py claude` renders two subagents (`planner`, `builder`) with the configured `model:` and `/pb` (one pass) + `/pbg` (loop until a done-condition) slash commands, plus `/pbg-builder` / `/pbg-planner` to switch a role's model from chat. |
| **Codex / Hermes / Gemini / raw system prompt** | `apply.py generic` prints a portable Markdown block (roles + resolved classes + provider env) to paste into `AGENTS.md` / `GEMINI.md` / a system prompt. |
| **Programmatic / OpenAI-compatible client** | Read the shared `roles.config.json` directly; pick `roles.<role>.model` + the `providers[...]` entry, one client per role. |

To support a **new** harness: add `adapters/<harness>/` templates (placeholders
`{{PLANNER_MODEL}}` / `{{BUILDER_MODEL}}` / `{{PLANNER_PURPOSE}}` /
`{{BUILDER_PURPOSE}}`) and a small render function in `apply.py`. The config never
changes.

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
