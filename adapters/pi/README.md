# pi adapter

The pi adapter is a set of **live, harness-level addons**, not project-local
adapters. `install_harness.py pi` syncs every directory listed in
`PI_EXTENSIONS` into Pi's auto-discovery path:

```text
$HOME/.pi/agent/extensions/pb-primitive/
$HOME/.pi/agent/extensions/subsite-scaffold/
```

`pb-primitive` is the agent framework described below. `subsite-scaffold` is a
separate extension documented in
[`subsite-scaffold/README.md`](./subsite-scaffold/README.md); see
"Sub-site scaffolding" at the end of this file for how it relates to the
`subsite-scaffold` *skill* used by other harnesses.

The extension first reads the nearest project `roles.config.json` or
`.pi/roles.config.json`, then falls back to this repository's shared,
harness-neutral `roles.config.json`.

**The Pi-only OpenRouter overlay was removed on 2026-07-26.** Pi now resolves
the same shared OpenAI/Codex registry as every other automated harness. Every
OpenAI-backed role carries an explicit required effort; Pi rejects a missing or
invalid effort rather than falling back to an ambient setting or another
provider.

The live adapter provides:

- `planner_agent` and `builder_agent` tools plus the internal `workflow_audit`
  post-workflow review tool;
- `runner_agent`, `tech_writer_agent`, `prose_writer_agent`,
  `team_leader_agent`, `l1_programmer_agent`, `librarian_agent`,
  `fe_designer_agent`, and `audit_agent` tools; `team_leader_agent` and
  `audit_agent` reject model-initiated calls because both are direct-call-only;
- `/pb` for one Planner → Builder pass followed by a lightweight configured
  audit at the registry's exact thinking effort;
- `/pbg` for a bounded plan/build/light-audit/verify loop;
- `/agents` to list every agent command, matching model command, and active
  provider/model assignment (or not-configured status).
- `/route <task>` to run the deterministic local router, show its reasons and
  alternatives, then request confirmation before invoking the recommendation.
- `/pb-show` for config and model resolution diagnostics.
- Explicit agent commands: `/planner`, `/builder`, `/runner`, `/tech-writer`,
  `/prose-writer`, `/team-leader`, `/l1-programmer`, `/librarian`,
  `/fe-designer`, and `/audit`. Audit runs directly on its configured model without
  delegated agents and is intended for harness/runtime bug audits.
- A `/<agent>-model` command for every agent. With no overlay present these
  report the shared registry value; writing one recreates a Pi-only overlay, so
  prefer `apply.py set` unless a Pi-specific divergence is actually wanted.
  Team Leader runs only via its explicit `/team-leader` command.

Planner and lightweight-auditor read-only behavior is enforced by the child Pi
tool allowlist `read,grep,find,ls`. Provider, model, and the registry's exact
thinking level (currently `xhigh`) are passed explicitly to every child. The light reviewer is narrower than the
full direct-call `/audit` agent and cannot edit or delegate. See the installed extension's `README.md` for operation, validation, and
security details.

Validate without a model call:

```bash
node ~/.pi/agent/extensions/pb-primitive/_selftest.mjs
pi --no-extensions -e ~/.pi/agent/extensions/pb-primitive/index.ts --list-models gpt-5.6-terra
python3 apply.py validate   # from the repository root
```

This adapter intentionally does not change configuration. Use the shared
`/home/dyadmin/dev-primitive/roles.config.json` and the normal `apply.py set`
workflow for model changes; with no Pi overlay, that is the only path and it
applies to every harness at once. Install or refresh the harness surfaces
with:

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

## Sub-site scaffolding

`subsite-scaffold/` is a second, independent Pi extension (`/new-subsite` and
the `create_subsite` tool). It is vendored here so it is version-controlled and
covered by `repo-backup`; it previously existed only inside `~/.pi`.

**Its routing output is partly stale — read this before using it.** The
extension writes Cloudflare ingress into the `dyuhaus.com` repo's
`tunnel/config.yml`, which is a sanitized Windows-era copy of a *different*
tunnel (`bfbfae39-…`) still listing decommissioned hostnames. The live
`*.dyuhaus.com` path is the homelab compose stack: one `nginx:alpine` service
per site plus the `apps-cloudflared-1` container reading
`~/homelab/compose/apps/cloudflared.yml` (tunnel `1f32fde8-…`).

Therefore:

- For **routing and deployment**, follow the `subsite-scaffold` *skill*
  (`~/githubStaging/homelab-skills/subsite-scaffold/SKILL.md`), which targets
  the live compose + nginx + `cloudflared.yml` path. That skill is
  authoritative for every harness, Pi included.
- Use this extension for what it is uniquely good at: generating the static
  skeleton and the **portable artifact bundle** (`site.manifest.json`,
  `BRIEF.md`, `tokens.css`, `PROMPT.md`) that carries a design spec off this
  headless box, plus the `.htaccess` block for the Hostinger-served apex.

Validate without a model call:

```bash
node ~/.pi/agent/extensions/subsite-scaffold/_selftest.mjs
```
