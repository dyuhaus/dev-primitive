# Harness-level installation

The agent framework is now installed at the harness level rather than being
available only inside this repository.

## Source and installed surfaces

`/home/dyadmin/dev-primitive/` remains the portable source of truth:

- `roles.config.json` — harness-neutral profiles and models
- `adapters/pi/roles.config.pi.json` — Pi-only Planner/Builder OpenRouter overlay
- `roles.schema.json` — structure
- `apply.py` — validation, Claude rendering, and generated knowledge profiles
- `router.py` — deterministic, explainable applicability routing with confirmation-required handoff
- `agent-knowledge/` — generated profiles plus preserved durable lessons
- `install_harness.py` — cross-harness installation

Installed surfaces:

| Harness | Surface | Result |
|---|---|---|
| Pi | `~/.pi/agent/extensions/pb-primitive/` | PB tools plus specialist tools such as `runner_agent` and `team_leader_agent` |
| Claude Code | `~/.claude/agents/` and `~/.claude/commands/` | PB subagents/commands and specialist subagents |
| Hermes | `~/.hermes/skills/agent-*/SKILL.md` | `/agent-runner`, `/agent-tech-writer`, `/agent-prose-writer`, `/agent-team-leader`, `/agent-l1-programmer`, `/agent-librarian`, `/agent-fe-designer`, and the framework reference skill |

Refresh all supported harnesses:

```bash
python3 /home/dyadmin/dev-primitive/install_harness.py all
# or refresh only one harness:
python3 /home/dyadmin/dev-primitive/install_harness.py pi
```

Preview without writing:

```bash
python3 /home/dyadmin/dev-primitive/install_harness.py all --dry-run
```

The installer syncs the versioned Pi addon from `adapters/pi/pb-primitive/`,
then renders the Claude and Hermes surfaces. It contains no credentials and
never prints secret values. Generated
files should not be hand-edited; update the source registry and reinstall.

## Model behavior

Claude Code and generic/Codex consumers resolve Planner/Builder from the shared
harness-neutral registry: `fable` and `opus` on Anthropic. Pi alone, when no
project-level roles config is present, resolves its complete live overlay at
`adapters/pi/roles.config.pi.json`: Planner is `moonshotai/kimi-k3` and Builder
is `openai/gpt-5.6-terra` via OpenRouter. Pi project configs always win; an
invalid/missing Pi overlay safely falls back to the shared config. Pi offers
explicit `/<agent>` slash commands for every profile and `/<agent>-model`
commands to manage the Pi overlay only. `/agents` is the native catalog: it
lists every available agent command and the effective active model assignment.
Those model commands never change the
shared registry, Claude Code, Codex, Hermes, or a project configuration. Hermes
skills carry profile metadata and instructions, while Hermes's active model
remains controlled by its native harness configuration.

## Routing behavior

`router.py` classifies a task deterministically and returns an explainable
applicability result. Pi automatically offers an eligible handoff when
`enabled: true`, while Claude and Pi `/route` show it on demand. Every path
requires confirmation and never silently invokes any profile; the portable
alternative is:

```bash
python3 /home/dyadmin/dev-primitive/router.py --explain 'task'
```

Runner is the low-confidence fallback. Team Leader has `direct-call-only`
semantics in every adapter and is hard-excluded from routing even for
multi-workstream language; invoke it explicitly only.

Run `python3 /home/dyadmin/dev-primitive/apply.py knowledge` to refresh the
generated specialty profiles. It preserves `agent-knowledge/*/LESSONS.md`.

## Verification

```bash
cd /home/dyadmin/dev-primitive
python3 apply.py validate
python3 -m unittest discover -s tests -v
python3 apply.py validate --config adapters/pi/roles.config.pi.json
python3 router.py --explain 'Update the Vault index and fix broken wikilinks'
python3 apply.py knowledge
node ~/.pi/agent/extensions/pb-primitive/_selftest.mjs
python3 install_harness.py all --dry-run
```

To roll back an installation, remove only the generated `agent-*` Hermes skill
directories and specialist Claude files, then reinstall the prior source
configuration. Do not remove unrelated user skills, agents, sessions, or
credentials.
