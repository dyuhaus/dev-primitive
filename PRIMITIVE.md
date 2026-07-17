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

## Role transports (`access`)

Besides *which* model a role uses, each role has a **transport** — *how* it is
reached — set by a per-role `access` field:

```jsonc
"planner": { "access": "harness", "model": { "class": "fable", ... } }
```

- **`harness`** (the default; absent means `harness`) — the role runs through the
  harness's own native model selection and auth. In Claude Code this is a subagent
  with a `model:` line, billed to the interactive session.
- **`api`** — the role runs as a **direct provider API call**, billed to that
  provider's own credentials, bypassing the session's auth. Use this when a role's
  model isn't available (or shouldn't be billed) through the harness's subscription.

**Why it exists / the auth-precedence fact.** In Claude Code, a headless call
(`claude -p ... --output-format json`) with the provider key in the child
process's environment uses *that key* with no prompt, while the parent session
keeps its own subscription OAuth. The JSON envelope's `total_cost_usd` is the proof
the call billed the API key rather than the subscription. `access: "api"` captures
this split in config so every adapter can honor it.

**Key source (never the secret itself in config).** An api-transport role reads its
key from the provider's `apiKeyEnv` variable if set, else from the file named by the
provider's `apiKeyFile` (default `~/appdata/anthropic/api-key`, dir `0700` / file
`0600`). The env var wins when both exist. Provision the keyfile interactively with
[`bin/set-api-key`](./bin/set-api-key) — it refuses to run without a terminal, reads
the key with echo off, writes it `0600`, and prints only a length + short
fingerprint, never the secret. `--verify` makes one tiny real call to confirm the
key bills the API.

**Model resolution for the API path.** Harness aliases (e.g. `fable`) may not be
valid `--model` ids, so the api path resolves the model as **`model.id` →
`classIds[class]` → the literal class** (best effort). Map aliases to concrete ids
in the top-level `classIds` object, e.g. `"classIds": { "fable": "claude-fable-5" }`;
`validate` warns if an api role would fall through to a bare class.

**Running an api role.** [`bin/role-call <role> "<task>"`](./bin/role-call) is the
ready-made wrapper: it composes the role's charter (`apply.py prompt <role>`) with
the task, applies the read-only tool allowlist for read-only roles, runs the
headless `claude` call with the key exported *only* into that child process (never
in argv or logs), prints the plan/report to stdout and a
`[role-call] role=… model=… cost=$… session=…` line to stderr. `--task-file`, `-`
(stdin), `--ping`, and `--dry-run` are supported. `apply.py resolve <role>` exposes
the same facts machine-readably for a bespoke wrapper.

**Switching / degradation.** `apply.py set <role> --access api|harness` flips a
role's transport and regenerates. Switching a role **to** `api` deletes its
generated Claude Code subagent file (a hand-edited one without the generated marker
is left in place with a warning) — its absence is deliberate, there is no shim; the
`/pb` and `/pbg` commands are rewritten to call `bin/role-call` for that role
instead. Switching **back** to `harness` recreates the subagent. If the key is
missing, `role-call` exits non-zero with a remedial message (provision the key, or
`set <role> --access harness` to fall back to the subscription).

**Cost note.** Direct API calls bill real money. Fable over the API is roughly
$10 / $50 per million input / output tokens, so a substantial planning turn can cost
several dollars; `role-call` prints each run's `total_cost_usd` so it's never hidden.

### Flip runbook (subscription → API for the planner)

When the provider key exists and you're ready to route planning over the API:

1. `bin/set-api-key` — provision the Anthropic key (run it yourself in a terminal).
2. `bin/role-call planner --ping` — confirm a `cost=$…` line appears (bills the key).
3. `python3 apply.py set planner --access api` — flip the transport + regenerate
   (this removes `~/.claude/agents/planner.md`).
4. Smoke `/pb` on a tiny task — confirm the orchestrator invokes `role-call planner`
   and relays the cost.
5. Update any harness-level orchestrator guidance (e.g. machine `AGENTS.md`) in the
   **same** session — after the flip there is no `planner` subagent to delegate to.

## Usage

```bash
python3 apply.py validate    # check config, print the resolved role/model table
python3 apply.py show        # same table
python3 apply.py claude      # (re)generate the Claude Code adapter
python3 apply.py generic     # print a paste-in block for any other harness
python3 apply.py all         # do both
python3 apply.py set builder sonnet   # change a role's model + regenerate (easy path)
python3 apply.py set planner --access api   # change a role's transport (see "Role transports")
python3 apply.py resolve planner      # machine-readable role facts (transport, model, key source)
python3 apply.py prompt planner       # the rendered role charter (used by bin/role-call)
python3 apply.py claude --dry-run   # preview without writing
```

Use `apply.py set <role> <class>` to change a model in one step (it edits
`roles.config.json`, validates, and regenerates); pass `--id` to pin an exact
model, `--access harness|api` to change the transport, `--no-apply` to only update
the config.

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

- **Claude Code** (`adapters/claude-code/`): `apply.py claude` renders a subagent
  per **harness-transport** role (`~/.claude/agents/planner.md`, `builder.md`) with
  the configured `model:`, and slash commands: `/pb` (one plan→build pass) and
  `/pbg` (loop until a done-condition holds), plus `/pbg-builder` and `/pbg-planner`
  to switch a role's model or transport from chat. The main loop auto-delegates to
  them. A role with `access: "api"` gets **no subagent** — its generated file is
  removed and the `/pb` / `/pbg` commands instead instruct the orchestrator to run
  `bin/role-call <role>` (per-transport dispatch fragments live in
  `adapters/claude-code/dispatch/`).
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
- No secrets in the config — only the *names* of env vars or *paths* to key files
  that hold them.

## Per-project override

This lives at `/home/dyadmin/dev-primitive/` as the machine default. A project
that needs different classes can copy `roles.config.json` into the project and
run `apply.py --config <that file> ...`; nearest config wins, mirroring how
`AGENTS.md` nests.
