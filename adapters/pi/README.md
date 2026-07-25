# pi adapter

The pi adapter is a **live, harness-level addon**, not a project-local
adapter. It is installed globally at:

```text
$HOME/.pi/agent/extensions/pb-primitive/
```

The extension first reads the nearest project `roles.config.json` or
`.pi/roles.config.json`. Without a project override it uses the Pi-only runtime
overlay at `adapters/pi/roles.config.pi.json`, then safely falls back to this
repository's shared, harness-neutral `roles.config.json` if the overlay is
missing or invalid. The overlay is intentionally read **only by Pi**: Claude
Code, Codex/generic consumers, and other harnesses use the shared config.

The live adapter provides:

- `planner_agent` and `builder_agent` tools plus the internal `workflow_audit`
  post-workflow review tool;
- `runner_agent`, `tech_writer_agent`, `prose_writer_agent`,
  `team_leader_agent`, `l1_programmer_agent`, `librarian_agent`,
  `fe_designer_agent`, and `audit_agent` tools; `team_leader_agent` and
  `audit_agent` reject model-initiated calls because both are direct-call-only;
- `/pb` for one Planner → Builder pass followed by a lightweight GPT-5.6 Sol
  audit at medium thinking;
- `/pbg` for a bounded plan/build/light-audit/verify loop;
- `/agents` to list every agent command, matching model command, and active
  provider/model assignment (or not-configured status).
- `/route <task>` to run the deterministic local router, show its reasons and
  alternatives, then request confirmation before invoking the recommendation.
- `/pb-show` for config and model resolution diagnostics.
- Explicit agent commands: `/planner`, `/builder`, `/runner`, `/tech-writer`,
  `/prose-writer`, `/team-leader`, `/l1-programmer`, `/librarian`,
  `/fe-designer`, and `/audit`. Audit runs directly on GPT-5.6 Sol without
  delegated agents and is intended for harness/runtime bug audits.
- A `/<agent>-model` command for every agent, which shows or changes only the
  Pi overlay model. For example: `/planner-model moonshotai/kimi-k3 --provider
  openrouter --id moonshotai/kimi-k3`. Team Leader runs only via its explicit
  `/team-leader` command.

Planner and lightweight-auditor read-only behavior is enforced by the child Pi
tool allowlist `read,grep,find,ls`. Provider, model, and the audit's medium
thinking level are passed explicitly. The light reviewer is narrower than the
full direct-call `/audit` agent and cannot edit or delegate. See the installed extension's `README.md` for operation, validation, and
security details.

Validate without a model call:

```bash
node ~/.pi/agent/extensions/pb-primitive/_selftest.mjs
pi --no-extensions -e ~/.pi/agent/extensions/pb-primitive/index.ts --list-models moonshotai/kimi-k3
python3 apply.py validate   # from the repository root
```

This adapter intentionally does not change configuration. Use the shared
`/home/dyadmin/dev-primitive/roles.config.json` and the normal `apply.py set`
workflow for cross-harness model changes. Change Pi-only models with:

```bash
python3 /home/dyadmin/dev-primitive/apply.py set <role> <model> \
  --provider openrouter \
  --config /home/dyadmin/dev-primitive/adapters/pi/roles.config.pi.json \
  --no-apply
```

`--no-apply` prevents accidental generation of Claude agents from Pi-only
models. The native `/<agent>-model` slash commands are safer for interactive Pi
changes because they atomically write only that overlay; they never touch
Claude, Codex, shared registry, or project configuration. Install or refresh
the harness surfaces with:

```bash
python3 /home/dyadmin/dev-primitive/install_harness.py all
```

Project-local `roles.config.json` files can still override the source config for
PB and specialist resolution when a project explicitly needs that behavior. `/route`
passes that resolved configuration to `router.py`, so its applicability result uses
the same profile registry. When `routing.automaticSelection.enabled` is true, Pi
also recognizes ordinary interactive tasks and offers a confirmation-required
handoff. With `routing.planBeforeBuild` enabled, generic substantive
implementation enters the full Planner → Builder flow; confirmed domain
specialists and explicitly outlined L1 work remain direct. Planner recommends
rather than invokes specialists. Pi never silently invokes an agent or selects
direct-call-only Team Leader or Audit.

Every profile's generated specialty and information-gathering documentation is
in `/home/dyadmin/dev-primitive/agent-knowledge/<key>/PROFILE.md`; durable
`LESSONS.md` files sit alongside it. Refresh profiles without overwriting lessons
with `python3 /home/dyadmin/dev-primitive/apply.py knowledge`.
