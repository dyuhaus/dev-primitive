# pb-primitive — native pi plan/build adapter

A global Pi extension for the machine's portable agent framework. It reads a
**Pi-only runtime overlay** live from
`/home/dyadmin/dev-primitive/adapters/pi/roles.config.pi.json` when no project
configuration is present. The portable, harness-neutral registry remains
`/home/dyadmin/dev-primitive/roles.config.json`.

## Commands and tools

- `/agents` — list every registered agent command, its matching model command,
  and its effective active provider/model (or an explicit not-configured state).
- `/route <task>` — show the deterministic applicability result and require
  confirmation before the selected profile runs. When routing is enabled, plain
  interactive text receives the same confirmation gate; ambiguous tasks continue
  normally so the user can answer the router's clarification questions. Accepted
  handoffs immediately show a cancellable progress panel until the specialist
  finishes, fails, or is canceled.
- `/pb-show` — show the selected config and resolved provider/model table.
- `/pb <task>` — one read-only planner pass followed by a builder pass. The
  builder receives the original task and planner output verbatim.
- `/pbg <task> [until: <done-condition>]` — bounded planner/build/verification
  loop, at most three rounds. If `until:` is omitted, the first planner derives
  explicit acceptance criteria.
- `planner_agent` — isolated read-only planning tool for the parent model.
- `builder_agent` — isolated implementation tool for the parent model.
- `/planner`, `/builder`, `/runner`, `/tech-writer`, `/prose-writer`,
  `/team-leader`, `/l1-programmer`, `/librarian`, `/fe-designer`, and `/audit` —
  explicitly run the corresponding configured agent. Team Leader and Audit are
  direct-call-only: they run only through their explicit slash commands, and
  their tool surfaces reject model-initiated calls. Audit uses GPT-5.6 Sol and
  performs harness/runtime audits directly without delegated agents.
- `/<agent>-model` for every agent above — show or change that agent's **Pi-only**
  model in the Pi overlay.

### Pi-only model commands

```text
/<agent>-model
/<agent>-model <model> [--provider <provider>] [--id <exact-model-id>]
```

Examples:

```text
/planner-model moonshotai/kimi-k3 --provider openrouter --id moonshotai/kimi-k3
/librarian-model openai/gpt-5.6-terra --provider openrouter
```

No arguments displays the configured Pi-only model and usage. A bare model sets
`model.class` and clears an existing exact-id pin; `--id` sets or replaces the
pin. The command validates and atomically writes only
`/home/dyadmin/dev-primitive/adapters/pi/roles.config.pi.json`; it never edits
shared `roles.config.json`, Claude agents, Codex configuration, or project
configuration. If a project config is active, the command reports that it still
overrides the changed Pi overlay in the current session.

The extension's prompt metadata tells the parent orchestrator to delegate
substantive reasoning to `planner_agent`, then substantive implementation to
`builder_agent`. Trivial lookups and one-line edits can remain inline.

## Config precedence

From the session working directory, Pi uses the first valid configuration in
this order:

1. Nearest project `roles.config.json`.
2. Nearest project `.pi/roles.config.json`.
3. Pi-only overlay: `/home/dyadmin/dev-primitive/adapters/pi/roles.config.pi.json`.
4. Shared harness-neutral registry: `/home/dyadmin/dev-primitive/roles.config.json`.

Project configuration always wins and is never merged with the Pi overlay. The
Pi overlay is a complete schema-valid config that sets Planner to
`moonshotai/kimi-k3` and Builder to `openai/gpt-5.6-terra` through OpenRouter.
Claude Code, Codex, generic adapters, and other harnesses do not read it; they
use the shared registry (`fable`/`opus` on Anthropic) unless separately
configured. If the overlay is absent or invalid, Pi warns and safely falls back
to the shared registry. `/pb-show` reports both source layer and path.

Pinned `model.id` wins over `model.class`; otherwise Pi resolves the configured
class/alias for the configured provider.

## Security model

- Each role runs in a separate `pi --mode json -p --no-session --no-extensions`
  process. Child roles cannot recursively load the global routing extension.
- Provider and model are always passed explicitly; child processes cannot
  silently inherit the parent's model.
- A read-only role is structurally restricted to `read,grep,find,ls`. It has no
  bash, edit, or write tool.
- The builder receives normal pi tools and therefore has the same host access as
  the parent user. Review the plan before approving the interactive build.
- Children inherit pi authentication/environment. This extension never reads,
  logs, stores, or forwards secret values itself.
- Temporary role and task prompts are mode `0600`, supplied through Pi's
  file-input support rather than large process arguments, and removed recursively
  in `finally`. Child work is bounded by a wall-clock timeout and killed on abort
  or session shutdown. Startup also removes owned prompt directories older than
  one hour that were left behind by a hard-killed process.
- Model-visible child output is capped at 50 KiB. Full parsed child messages
  remain in tool-result details for the current session.
- `/pbg` stops after acceptance, a verifier block, a failed child, repeated
  evidence/no progress, or three rounds. It is bounded assistance, not an
  autonomous approval mechanism.

Project-local pi resources are executable. The machine currently sets
`defaultProjectTrust` to `always`; consider changing it to `ask` for stronger
isolation. This extension does not change that setting.

## Validation

```bash
node ~/.pi/agent/extensions/pb-primitive/_selftest.mjs
pi --no-extensions -e ~/.pi/agent/extensions/pb-primitive/index.ts --list-models moonshotai/kimi-k3
python3 /home/dyadmin/dev-primitive/apply.py validate
python3 /home/dyadmin/dev-primitive/apply.py validate --config /home/dyadmin/dev-primitive/adapters/pi/roles.config.pi.json
```

The self-test is offline and makes no model calls.

## Limitations

- The planner intentionally has no shell, so it cannot run even read-only test
  commands. It can inspect files with pi's read/search tools; the builder runs
  validation.
- Provider availability is checked by the child pi process. A configured role
  fails clearly if its provider is not authenticated or lacks credits.
- The slash model commands above are the preferred interactive Pi path. For a
  shared cross-harness model change, use the normal `apply.py set` workflow. For
  a scripted Pi-only model change, run:
  ```bash
  python3 /home/dyadmin/dev-primitive/apply.py set <role> <model> \
    --provider openrouter \
    --config /home/dyadmin/dev-primitive/adapters/pi/roles.config.pi.json \
    --no-apply
  ```
  `--no-apply` is required: without it, `apply.py set` would regenerate Claude
  agents from the Pi-only overlay.
- Interactive `/pb` and `/pbg` ask before building; print/JSON mode cannot show a
  dialog and proceeds according to the command request.
