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
file and regenerate (or run `apply.py set <role> <class>`, which does both in one
step) — nothing else. From within Claude Code, `/pbg-builder <model>` and
`/pbg-planner <model>` do the same for each role.

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
python3 apply.py set builder sonnet   # change a role's model + regenerate (easy path)
python3 apply.py claude --dry-run   # preview without writing
```

Use `apply.py set <role> <class>` to change a model in one step (it edits
`roles.config.json`, validates, and regenerates); pass `--id` to pin an exact
model, `--no-apply` to only update the config.

## Looping until a condition holds

The plain loop (`/pb`) runs one plan→build pass. Two ways to keep going until an
explicit done-condition holds:

- **Harness-enforced (recommended): `/goal` then `/pb`.** The built-in
  `/goal <done-condition>` sets a session-scoped completion condition and keeps
  working across turns until it holds (a fast model checks after every turn) or you
  run `/goal clear`; it auto-clears when met. Set it first, then send `/pb <task>`
  as the next message; the goal governs the plan→build turns. This uses the
  harness's own Stop-hook loop, so the guarantee is real. `/goal` and `/pb` can't
  be combined in one message — `/goal` is a built-in (only recognized alone at the
  start of a message) and `/pb` immediately spawns subagents (ending any command
  chain) — so send them as two messages.
- **Single-command (softer): `/pbg <task> until: <done-condition>`.** A convenience
  variant that emulates the loop inside the orchestrator (plan → build → verify →
  loop, bounded). Model-driven, not harness-enforced — use it when you want one
  line and accept the weaker guarantee. Omit `until:` and the planner derives
  explicit acceptance criteria first.

## Adapters — adding this to any harness

An *adapter* turns the config into whatever a given harness understands. Each is
thin and driven entirely by `roles.config.json`.

- **Claude Code** (`adapters/claude-code/`): `apply.py claude` renders two
  subagents (`~/.claude/agents/planner.md`, `builder.md`) with the configured
  `model:` and slash commands: `/pb` (one plan→build pass) and `/pbg` (loop
  until a done-condition holds), plus `/pbg-builder` and `/pbg-planner` to switch
  a role's model from chat. The main loop auto-delegates to them.
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
