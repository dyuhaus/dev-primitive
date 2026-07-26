#!/usr/bin/env python3
"""Install the configured agent registry into user-level harness surfaces.

The repository remains the portable source of truth. This installer materializes
native adapters into Claude Code and Hermes; it never copies secrets.
"""
import argparse
import json
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import apply as primitive  # noqa: E402


def load():
    cfg = primitive.load_config(ROOT / "roles.config.json")
    errors = primitive.validate(cfg)
    if errors:
        raise SystemExit("Invalid source config:\n" + "\n".join(f"- {e}" for e in errors))
    return cfg


def bullets(items):
    return "\n".join(f"- {item}" for item in items) or "- None specified"


def hermes_skill(view, key):
    return f'''---
name: agent-{key}
description: {view["purpose"]}
category: agent-framework
metadata:
  agent_framework:
    profile: {key}
    model_class: {view["class"]}
    model_id: {view["id"]}
    provider: {view["provider"]}
    invocation: {view["invocation"]}
    auto_select_eligible: {str(view["auto_select"]).lower()}
---

# {view["display_name"]}

You are the **{view["display_name"]}** specialist (`{key}`). This is a
harness-level agent skill generated from `/home/dyadmin/dev-primitive/roles.config.json`.

## Mission
{view["purpose"]}

## Invocation
- Policy: **{view["invocation"]}**.
- `router.py` may recognize this profile as applicable, but every handoff is confirmation-required before invocation.
- {"This profile must only run when the user or supervising orchestrator explicitly invokes it. Never self-invoke or volunteer it." if view["invocation"] == "direct-call-only" else "Use this profile only for work within its stated scope; escalate when needed."}

## Capabilities
{bullets(view["capabilities"])}

## Information gathering and durable lessons
- Knowledge directory: `/home/dyadmin/dev-primitive/agent-knowledge/{key}/`.
- Before substantive work, read `PROFILE.md` and `LESSONS.md`, then consult:
{bullets(view["info_sources"])}
- After substantive work, append at most one generalized evidence-backed lesson when permitted. Never record secrets, credentials, personal data, or raw task logs. At 50 dated lessons, consolidate reusable items into Durable practices.

## Boundaries
{bullets(view["boundaries"])}

## Escalation and delegation
- Escalate/recommend: {", ".join(view["escalate_to"]) or "none"}.
- Can delegate: {str(view["can_delegate"]).lower()}.
- Allowed delegation targets: {", ".join(view["delegate_to"]) or "none"}.

## Output contract
{bullets(view["output_contract"])}

Honor the nearest `AGENTS.md`/project instructions, keep secrets out of
responses, and report assumptions, validation, escalation, and remaining risk.
'''


def framework_skill():
    return '''---
name: agent-framework
description: Use the machine-level specialist-agent framework: Runner, writers, Librarian, FE-Designer, Audit, Team Leader, L1 Programmer, Planner, and Builder.
category: agent-framework
---

# Machine Agent Framework

The harness-level specialist profiles are installed under `agent-*`. Use
**Runner** as the everyday front door for routine work and maintenance. Use
Planner → Builder for substantive software work. Builder is the senior engineer
and may delegate a clearly outlined subtask to L1 Programmer or a separable
frontend implementation to FE-Designer. Planner recommends the next role but
does not invoke specialists itself; the parent orchestrator owns handoffs.
After each completed Planner → Builder or Planner → specialist workflow, run the
configured lightweight GPT-5.6 Sol audit at medium thinking before the final
report. This review is read-only and narrower than the direct-call Audit agent.

Available skills:
- `/agent-runner`
- `/agent-tech-writer`
- `/agent-prose-writer`
- `/agent-team-leader` — direct-call-only; never automatically invoke
- `/agent-l1-programmer`
- `/agent-librarian`
- `/agent-fe-designer`
- `/agent-audit` — direct-call-only harness/tooling audit and repair

The deterministic router recognizes applicable agents: use the portable command
`python3 /home/dyadmin/dev-primitive/router.py --explain 'task'`, or `/route`
in supporting Claude/Pi adapters. Show the reasons and obtain confirmation before
invoking a handoff. Team Leader and Audit require explicit user calls and are
never automatic routing destinations. Audit directly inspects and repairs
harness/runtime failures without invoking delegated agents.

The registry source of truth is `/home/dyadmin/dev-primitive/roles.config.json`.
Generated harness adapters must not be hand-edited. Model metadata in this skill
identifies intended routing; Hermes's active model still comes from its harness
configuration unless an explicit model-routing integration is added later.
'''


# Versioned Pi extensions synced from this repo into ~/.pi/agent/extensions/.
# Each entry is a directory name under adapters/pi/ that is also the extension
# name Pi auto-discovers.
PI_EXTENSIONS = ("pb-primitive", "subsite-scaffold")


def sync_pi_extension(name, home, dry_run):
    source = ROOT / "adapters" / "pi" / name
    target = home / ".pi" / "agent" / "extensions" / name
    if dry_run:
        print(f"--- would sync {source} -> {target} ---")
        return
    if not source.is_dir():
        raise SystemExit(f"Missing Pi adapter source: {source}")
    target.mkdir(parents=True, exist_ok=True)
    for item in source.iterdir():
        if item.name == "__pycache__":
            continue
        destination = target / item.name
        if item.is_file():
            shutil.copy2(item, destination)
            print(f"wrote {destination}")


def install_pi(home, dry_run):
    overlay = ROOT / "adapters" / "pi" / "roles.config.pi.json"
    if not overlay.is_file():
        raise SystemExit(f"Missing Pi-only overlay: {overlay}")
    overlay_cfg = primitive.load_config(overlay)
    overlay_errors = primitive.validate(overlay_cfg)
    if overlay_errors:
        raise SystemExit("Invalid Pi-only overlay:\n" + "\n".join(f"- {error}" for error in overlay_errors))
    for name in PI_EXTENSIONS:
        sync_pi_extension(name, home, dry_run)
    if dry_run:
        print(f"Pi will read the live overlay at {overlay}; it is not copied into ~/.pi.")


def install_hermes(cfg, home):
    skills = home / "skills"
    skills.mkdir(parents=True, exist_ok=True)
    framework = skills / "agent-framework" / "SKILL.md"
    framework.parent.mkdir(parents=True, exist_ok=True)
    framework.write_text(framework_skill(), encoding="utf-8")
    for key in cfg.get("agents", {}):
        view = primitive.role_view(cfg, key)
        target = skills / f"agent-{key}" / "SKILL.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(hermes_skill(view, key), encoding="utf-8")
        print(f"wrote {target}")
    print(f"wrote {framework}")


def main():
    parser = argparse.ArgumentParser(description="Install agent profiles into harness-level adapters")
    parser.add_argument("target", choices=("pi", "claude", "hermes", "all"))
    parser.add_argument("--home", default=os.environ.get("HOME", str(Path.home())))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    cfg = load()
    home = Path(args.home).expanduser()
    # Profiles are generated source documentation; LESSONS.md files are only
    # initialized when absent, so refreshing harness adapters never erases them.
    primitive.install_knowledge(cfg, args.dry_run)
    if args.target in ("pi", "all"):
        install_pi(home, args.dry_run)
    if args.target in ("claude", "all"):
        primitive.install_claude(cfg, home, args.dry_run)
    if args.target in ("hermes", "all"):
        if args.dry_run:
            agent_keys = list(cfg.get("agents", {}))
            print(f"--- would write {home / '.hermes/skills/agent-*' } ---")
            print(f"agent-framework and {len(agent_keys)} agent-* Hermes skills: {', '.join(agent_keys)}")
        else:
            install_hermes(cfg, home / ".hermes")


if __name__ == "__main__":
    main()
