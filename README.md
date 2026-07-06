# dev-primitive

A small, portable primitive for developing with **two model roles**: one model
*plans and reasons*, another *scripts and builds*. Harness-neutral and
provider-neutral — the exact model class for each role is set in one config file
and generated into whatever harness you use.

```
planner  →  reasoning-tier model  →  architecture, design, root-cause, sequencing, review
builder  →  coding-tier model     →  writing/editing code, running builds & tests, applying the plan
```

**Loop:** reason with the planner → hand its plan to the builder → build → verify.
The session's main loop is an *orchestrator* that routes each kind of work to the
right model instead of doing both itself. Trivial lookups and one-line edits stay
inline.

## Quickstart

```bash
python3 apply.py validate    # check config, print the resolved role/model table
python3 apply.py claude      # (re)generate the Claude Code adapter (~/.claude/agents + /pb)
python3 apply.py generic     # print a paste-in block for any other harness
python3 apply.py all         # both
```

No third-party dependencies (Python 3.8+ stdlib only).

## The one knob: `roles.config.json`

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

Change which model plans or builds by editing this file and re-running `apply.py`.
The config is validated by [`roles.schema.json`](./roles.schema.json) and by
`apply.py validate`. **No secrets live here — only the names of env vars.**

## Adding it to any harness

An *adapter* turns the config into whatever a harness understands:

| Harness | How |
|---|---|
| **Claude Code** | `apply.py claude` renders two subagents (`planner`, `builder`) with the configured `model:` and a `/pb` slash command. |
| **Codex / Hermes / Gemini / raw system prompt** | `apply.py generic` prints a portable Markdown block (roles + resolved classes + provider env) to paste into `AGENTS.md` / `GEMINI.md` / a system prompt. |
| **Programmatic / OpenAI-compatible client** | Read `roles.config.json` directly; pick `roles.<role>.model` + the `providers[...]` entry, one client per role. |

To support a **new** harness: add `adapters/<harness>/` templates (placeholders
`{{PLANNER_MODEL}}` / `{{BUILDER_MODEL}}` / `{{PLANNER_PURPOSE}}` /
`{{BUILDER_PURPOSE}}`) and a small render function in `apply.py`. The config never
changes.

## Layout

```
roles.config.json        single source of truth (edit this)
roles.schema.json        JSON-Schema validator
apply.py                 stdlib-only generator / validator
PRIMITIVE.md             full harness-neutral spec
adapters/claude-code/    planner / builder / pb templates
```

See [`PRIMITIVE.md`](./PRIMITIVE.md) for the full spec and design rules.
