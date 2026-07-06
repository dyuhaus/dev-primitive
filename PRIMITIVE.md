# Two-Model Development Primitive

A small, portable primitive for developing with **two roles on two different
model classes**: one model *plans and reasons*, another model *scripts and
builds*. It is harness-neutral and provider-neutral — Claude Code is just one
adapter. The exact model class for each role is customizable in one file.

## The idea

| Role | Does | Model |
|------|------|-------|
| **planner** | planning & reasoning: architecture, design, root-cause analysis, sequencing, review-before-build | a *reasoning-tier* model class you choose |
| **builder** | actual scripting & building: writing/editing code, running builds & tests, applying a plan | a *coding-tier* model class you choose |

**Loop:** reason with the planner → hand its plan to the builder → build → verify.
Substantive work is routed by kind; trivial lookups and one-line edits stay
inline. The session's main loop acts as an **orchestrator** that dispatches each
kind of work to the right model rather than doing both itself.

## Single source of truth

Everything is driven by [`roles.config.json`](./roles.config.json). It defines
the two roles and, for each, a **model class** (plus an optional pinned `id` and
a `provider`). To change which model does the planning or the building, edit that
file and regenerate — nothing else.

```jsonc
"planner": { "model": { "class": "fable", "id": "", "provider": "anthropic" }, "readOnly": true }
"builder": { "model": { "class": "opus",  "id": "", "provider": "anthropic" }, "readOnly": false }
```

- `class` — the customizable model class/alias (e.g. `fable`, `opus`, `sonnet`,
  or a provider-specific class). On harnesses that support aliases it resolves to
  the newest model in that family, so it auto-upgrades as new models ship.
- `id` — optional exact model to pin (e.g. `claude-opus-4-8`). When set it wins
  over `class` (no auto-upgrade).
- `provider` — a key into the `providers` map, which names the wire protocol and
  the env vars for the API key / base URL. Point a role at any provider
  (Anthropic, any OpenAI-compatible endpoint incl. OpenRouter, Google, or a local
  model) without touching code.

The config is validated by [`roles.schema.json`](./roles.schema.json) and by
`apply.py validate`.

## Usage

```bash
python3 apply.py validate    # check config, print the resolved role/model table
python3 apply.py show        # same table
python3 apply.py claude      # (re)generate the Claude Code adapter
python3 apply.py generic     # print a paste-in block for any other harness
python3 apply.py all         # do both
python3 apply.py claude --dry-run   # preview without writing
```

## Adapters — adding this to any harness

An *adapter* turns the config into whatever a given harness understands. Each is
thin and driven entirely by `roles.config.json`.

- **Claude Code** (`adapters/claude-code/`): `apply.py claude` renders two
  subagents (`~/.claude/agents/planner.md`, `builder.md`) with the configured
  `model:` and a `/pb` slash command that runs the plan→build loop. The main loop
  auto-delegates to them.
- **Any prompt/instruction-based harness** (Codex, Hermes, Gemini, a bespoke
  agent, a raw system prompt): `apply.py generic` prints a portable Markdown block
  naming the two roles, their resolved model classes, and each role's provider +
  env vars. Paste it into that harness's `AGENTS.md` / `GEMINI.md` / system
  prompt. The harness then selects the two models via its own native mechanism.
- **A programmatic/OpenAI-compatible client**: read `roles.config.json` directly,
  pick `roles.<role>.model` (id or class) and the `providers[...]` entry for the
  base URL / key env, and instantiate one client per role.

To support a **new** harness, add `adapters/<harness>/` templates (with
`{{PLANNER_MODEL}}` / `{{BUILDER_MODEL}}` / `{{PLANNER_PURPOSE}}` /
`{{BUILDER_PURPOSE}}` placeholders) and a small function in `apply.py` that
renders them. The config never changes.

## Portability rules (inherited from the machine contract)

- Durable state lives in these normal files (JSON, schema, Markdown, a stdlib
  script) — nothing is hidden in one harness's memory or chat history.
- No provider or model is hardcoded as the only path; swap classes/providers in
  the config.
- No secrets in the config — only the *names* of env vars that hold them.

## Per-project override

This lives at `/home/dyadmin/dev-primitive/` as the machine default. A project
that needs different classes can copy `roles.config.json` into the project and
run `apply.py --config <that file> ...`; nearest config wins, mirroring how
`AGENTS.md` nests.
