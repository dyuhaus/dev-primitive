#!/usr/bin/env python3
"""Configuration and adapter generator for the portable agent framework.

The config contains the legacy-compatible PB roles (planner/builder) and an
optional registry of specialist agents. The separate router.py recognizes
applicable profiles; every harness handoff remains confirmation-required.
"""
import argparse
import json
import os
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
ROLE_KEYS = ("planner", "builder")
SPECIALIST_KEYS = ("runner", "tech-writer", "prose-writer", "team-leader", "l1-programmer", "librarian", "fe-designer", "audit")
ALL_AGENT_KEYS = ROLE_KEYS + SPECIALIST_KEYS


def fail(msg: str) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    raise SystemExit(1)


def load_config(path: Path) -> dict:
    try:
        with path.open(encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        fail(f"config not found: {path}")
    except json.JSONDecodeError as exc:
        fail(f"config is not valid JSON: {exc}")


def validate(cfg: dict) -> list:
    errs = []
    if not isinstance(cfg.get("version"), int) or cfg.get("version", 0) < 1:
        errs.append("version must be an integer >= 1")
    providers = cfg.get("providers")
    if not isinstance(providers, dict) or not providers:
        errs.append("providers must be a non-empty object")
        providers = {}
    else:
        for name, prov in providers.items():
            if not isinstance(prov, dict):
                errs.append(f"providers.{name} must be an object")
                continue
            if prov.get("type") not in ("anthropic", "openai", "google", "local"):
                errs.append(f"providers.{name}.type must be one of anthropic|openai|google|local")
            if not isinstance(prov.get("apiKeyEnv"), str):
                errs.append(f"providers.{name}.apiKeyEnv must be a string")

    roles = cfg.get("roles")
    if not isinstance(roles, dict):
        errs.append("roles must be an object")
        roles = {}

    def validate_model(model, path):
        if not isinstance(model, dict):
            errs.append(f"{path} must be an object")
            return
        cls, mid = model.get("class", ""), model.get("id", "")
        if not isinstance(cls, str):
            errs.append(f"{path}.class must be a string")
            cls = ""
        if not isinstance(mid, str):
            errs.append(f"{path}.id must be a string")
            mid = ""
        if not (cls.strip() or mid.strip()):
            errs.append(f"{path} needs a non-empty class or id")
        provider = model.get("provider")
        if not isinstance(provider, str) or not provider:
            errs.append(f"{path}.provider must be a string")
        elif provider not in providers:
            errs.append(f"{path}.provider '{provider}' is not defined in providers")

    def validate_entry(entry, path, specialist=False):
        if not isinstance(entry, dict):
            errs.append(f"{path} must be an object")
            return
        if not isinstance(entry.get("purpose"), str) or not entry.get("purpose"):
            errs.append(f"{path}.purpose must be a non-empty string")
        validate_model(entry.get("model"), f"{path}.model")
        if "canDelegate" in entry and not isinstance(entry["canDelegate"], bool):
            errs.append(f"{path}.canDelegate must be boolean")
        for field in ("escalateTo", "delegateTo", "infoSources"):
            if field in entry and (not isinstance(entry[field], list) or not all(isinstance(x, str) for x in entry[field])):
                errs.append(f"{path}.{field} must be a list of strings")
        if specialist:
            fields = ("displayName", "tools", "invocation", "autoSelectEligible", "capabilities", "boundaries", "escalateTo", "canDelegate", "delegateTo", "outputContract", "infoSources")
            for field in fields:
                if field not in entry:
                    errs.append(f"{path}.{field} is required")
            if not isinstance(entry.get("displayName"), str) or not entry.get("displayName"):
                errs.append(f"{path}.displayName must be a non-empty string")
            if entry.get("invocation") not in ("default", "direct-call-only"):
                errs.append(f"{path}.invocation must be default or direct-call-only")
            if not isinstance(entry.get("autoSelectEligible"), bool):
                errs.append(f"{path}.autoSelectEligible must be boolean")
            elif entry.get("invocation") == "direct-call-only" and entry.get("autoSelectEligible"):
                errs.append(f"{path}: direct-call-only agents cannot be auto-select eligible")
            for field in ("tools", "capabilities", "boundaries", "escalateTo", "delegateTo", "outputContract"):
                if not isinstance(entry.get(field), list) or not all(isinstance(x, str) for x in entry.get(field, [])):
                    errs.append(f"{path}.{field} must be a list of strings")

    for key in ROLE_KEYS:
        if key not in roles:
            errs.append(f"roles.{key} is required and must be an object")
        else:
            validate_entry(roles[key], f"roles.{key}")

    agents = cfg.get("agents")
    if agents is not None:
        if not isinstance(agents, dict):
            errs.append("agents must be an object")
        else:
            for key, agent in agents.items():
                validate_entry(agent, f"agents.{key}", specialist=True)
            known = set(roles) | set(agents)
            for namespace, entries in (("roles", roles), ("agents", agents)):
                for key, entry in entries.items():
                    if not isinstance(entry, dict):
                        continue
                    for field in ("escalateTo", "delegateTo"):
                        targets = entry.get(field, [])
                        if not isinstance(targets, list):
                            continue
                        for target in targets:
                            if isinstance(target, str) and target not in known:
                                errs.append(f"{namespace}.{key}.{field} references unknown agent '{target}'")

    routing = cfg.get("routing")
    if routing is not None:
        if not isinstance(routing, dict):
            errs.append("routing must be an object")
        else:
            post_audit = routing.get("postWorkflowAudit")
            if post_audit is not None:
                if not isinstance(post_audit, dict):
                    errs.append("routing.postWorkflowAudit must be an object")
                else:
                    enabled = post_audit.get("enabled")
                    if not isinstance(enabled, bool):
                        errs.append("routing.postWorkflowAudit.enabled must be boolean")
                    if enabled is True:
                        validate_model(post_audit.get("model"), "routing.postWorkflowAudit.model")
                    elif "model" in post_audit:
                        validate_model(post_audit.get("model"), "routing.postWorkflowAudit.model")
                    if "thinking" in post_audit and post_audit.get("thinking") not in ("off", "minimal", "low", "medium", "high", "xhigh", "max"):
                        errs.append("routing.postWorkflowAudit.thinking must be a supported thinking level")
            selection = routing.get("automaticSelection")
            if selection is not None:
                if not isinstance(selection, dict):
                    errs.append("routing.automaticSelection must be an object")
                else:
                    if "enabled" in selection and not isinstance(selection["enabled"], bool):
                        errs.append("routing.automaticSelection.enabled must be boolean")
                    if "status" in selection and not isinstance(selection["status"], str):
                        errs.append("routing.automaticSelection.status must be a string")
                    if "threshold" in selection and (not isinstance(selection["threshold"], (int, float)) or isinstance(selection["threshold"], bool) or not 0 <= selection["threshold"] <= 1):
                        errs.append("routing.automaticSelection.threshold must be a number from 0 to 1")
                    fallback = selection.get("fallback")
                    if fallback is not None:
                        profile = agents.get(fallback) if isinstance(agents, dict) else None
                        if not isinstance(fallback, str) or not isinstance(profile, dict):
                            errs.append("routing.automaticSelection.fallback must reference a registered specialist")
                        elif profile.get("invocation") == "direct-call-only" or not profile.get("autoSelectEligible"):
                            errs.append("routing.automaticSelection.fallback must reference an auto-select-eligible, non-direct-call-only specialist")
                    audit = selection.get("audit")
                    if audit is not None:
                        if not isinstance(audit, dict):
                            errs.append("routing.automaticSelection.audit must be an object")
                        else:
                            if "enabled" in audit and not isinstance(audit["enabled"], bool):
                                errs.append("routing.automaticSelection.audit.enabled must be boolean")
                            if "path" in audit and (not isinstance(audit["path"], str) or not audit["path"].strip()):
                                errs.append("routing.automaticSelection.audit.path must be a non-empty string")
    return errs


def get_agent(cfg: dict, key: str) -> dict:
    if key in ROLE_KEYS:
        return cfg["roles"][key]
    agents = cfg.get("agents", {})
    if key not in agents:
        fail(f"agent '{key}' is not configured; available specialists: {', '.join(agents) or '(none)'}")
    return agents[key]


def resolve_model(entry: dict) -> str:
    model = entry.get("model", {})
    return str(model.get("id", "")).strip() or str(model.get("class", "")).strip()


def apply_set(cfg: dict, args) -> list:
    if not args.role:
        fail("`set` needs a role or specialist key")
    model = get_agent(cfg, args.role)["model"]
    changes = []
    new_class = args.cls if args.cls is not None else args.model
    if new_class is not None:
        model["class"] = new_class
        changes.append(f"class -> '{new_class}'")
        if args.pin_id is None and str(model.get("id", "")).strip():
            model["id"] = ""
            changes.append("id -> '' (cleared so class is active)")
    if args.pin_id is not None:
        model["id"] = args.pin_id
        changes.append(f"id -> '{args.pin_id}'" if args.pin_id.strip() else "id -> '' (pin cleared)")
    if args.provider is not None:
        model["provider"] = args.provider
        changes.append(f"provider -> '{args.provider}'")
    if not changes:
        fail("nothing to set — pass a model class, or --id/--class/--provider")
    return changes


def role_view(cfg: dict, key: str) -> dict:
    entry = get_agent(cfg, key)
    provider_name = entry["model"]["provider"]
    provider = cfg["providers"][provider_name]
    return {
        "role": key,
        "model": resolve_model(entry),
        "class": entry["model"].get("class", ""),
        "id": entry["model"].get("id", ""),
        "provider": provider_name,
        "provider_type": provider.get("type", ""),
        "purpose": entry.get("purpose", ""),
        "read_only": bool(entry.get("readOnly", False)),
        "display_name": entry.get("displayName", key.title()),
        "tools": entry.get("tools", []),
        "invocation": entry.get("invocation", "default"),
        "auto_select": entry.get("autoSelectEligible", False),
        "capabilities": entry.get("capabilities", []),
        "boundaries": entry.get("boundaries", []),
        "escalate_to": entry.get("escalateTo", []),
        "can_delegate": bool(entry.get("canDelegate", False)),
        "delegate_to": entry.get("delegateTo", []),
        "output_contract": entry.get("outputContract", []),
        "info_sources": entry.get("infoSources", []),
    }


def render(text: str, mapping: dict) -> str:
    for key, value in mapping.items():
        text = text.replace("{{" + key + "}}", str(value))
    return text


# --------------------------------------------------------------------------- #
# external-provider dispatch (Claude Code)
# --------------------------------------------------------------------------- #
# Claude Code resolves a subagent's `model:` frontmatter against Anthropic
# classes and ids only. An unrecognized value — e.g. an OpenRouter id like
# `openai/gpt-5.6-sol` — is discarded without error and the subagent silently
# runs on the session's own model. For profiles that are configured on another
# vendor family precisely so their judgement is independent, that failure is
# invisible and produces a verdict that reads as cross-family when it is not.
#
# So: emit a resolvable `inherit` for those profiles, and require the real
# verdict to come from scripts/external_review.py, which dispatches the
# configured provider directly.
EXTERNAL_REVIEW_SCRIPT = SCRIPT_DIR / "scripts" / "external_review.py"


def is_external(provider: str) -> bool:
    return bool(provider) and provider != "anthropic"


def claude_model_field(model: str, provider: str) -> str:
    return "inherit" if is_external(provider) else model


def claude_tools(tools, provider: str) -> list:
    """External profiles need Bash to reach the review script."""
    tools = list(tools)
    if is_external(provider) and "Bash" not in tools:
        tools.append("Bash")
    return tools


def claude_model_summary(model: str, provider: str) -> str:
    """Description text that does not overstate what the subagent runs on."""
    if is_external(provider):
        return (
            f"gathers evidence on the session model, then obtains its verdict from "
            f"{model} through the external review bridge"
        )
    return f"running on the configured model class ({model})"


def external_dispatch_block(profile: str, model: str, provider: str) -> str:
    """Instructions that keep an external-model profile actually external."""
    if not is_external(provider):
        return ""
    return f"""
## Model dispatch — required

Your configured model is `{model}` from provider `{provider}`. **This harness
cannot dispatch that provider for a subagent.** Its `model:` frontmatter accepts
only Anthropic classes and ids; an unrecognized value is discarded silently and
the subagent runs on the session's own model instead. The frontmatter above
therefore says `inherit`, which is honest about what *you* run on.

The consequence is that **you are not the reviewer**. You gather and structure
the evidence; `{model}` returns the verdict. Get it by running exactly:

```bash
python3 {EXTERNAL_REVIEW_SCRIPT} \\
  --profile {profile} --input <payload-file>
```

Write the payload to a file first (task, plan, executor identity, evidence, and
the specific questions you need answered), then pass it with `--input`. The
script resolves the model from the registry, calls the provider, and prints the
verdict under a provenance header.

Hard rules:

- If the script exits non-zero, **report the failure and stop**. Do not proceed
  on your own judgement.
- Never present your own text as though it came from `{model}`. Quote or
  summarize the script's output and attribute it.
- Never read, echo, or pass along credentials. The script resolves the key
  itself from the local secret store.
- `Bash` is granted for this call. Use it for the review script and for
  read-only evidence gathering consistent with this profile's tool intent —
  not to widen your scope.

Confirm the path is configured before relying on it:

```bash
python3 {EXTERNAL_REVIEW_SCRIPT} --check --profile {profile}
```
"""


def template_mapping(cfg: dict) -> dict:
    p, b = role_view(cfg, "planner"), role_view(cfg, "builder")
    post_audit = ((cfg.get("routing") or {}).get("postWorkflowAudit") or {})
    audit_model = resolve_model({"model": post_audit.get("model", {})})
    audit_provider = (post_audit.get("model") or {}).get("provider", "")
    return {
        "PLANNER_MODEL": p["model"],
        "BUILDER_MODEL": b["model"],
        "PLANNER_PURPOSE": p["purpose"],
        "BUILDER_PURPOSE": b["purpose"],
        "PLANNER_PROVIDER": p["provider"],
        "BUILDER_PROVIDER": b["provider"],
        "WORKFLOW_AUDIT_ENABLED": str(post_audit.get("enabled", False)).lower(),
        "WORKFLOW_AUDIT_MODEL": audit_model,
        "WORKFLOW_AUDIT_THINKING": post_audit.get("thinking", "medium"),
        "WORKFLOW_AUDIT_MODEL_FIELD": claude_model_field(audit_model, audit_provider),
        "WORKFLOW_AUDIT_MODEL_SUMMARY": claude_model_summary(audit_model, audit_provider),
        "WORKFLOW_AUDIT_TOOLS": ", ".join(
            claude_tools(["Read", "Grep", "Glob"], audit_provider)
        ),
        "WORKFLOW_AUDIT_DISPATCH": external_dispatch_block(
            "workflow-audit", audit_model, audit_provider
        ),
    }


def write_out(target: Path, content: str, dry: bool) -> None:
    if dry:
        print(f"--- would write {target} ---")
        print(content)
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    print(f"  wrote {target}")


def list_text(items):
    return "\n".join(f"- {item}" for item in items) or "- None specified"


def install_claude(cfg: dict, home: Path, dry: bool) -> None:
    mapping = template_mapping(cfg)
    tdir = SCRIPT_DIR / "adapters" / "claude-code"
    jobs = [
        (tdir / "planner.md.tmpl", home / ".claude" / "agents" / "planner.md"),
        (tdir / "builder.md.tmpl", home / ".claude" / "agents" / "builder.md"),
        (tdir / "workflow-audit.md.tmpl", home / ".claude" / "agents" / "workflow-audit.md"),
        (tdir / "pb.md.tmpl", home / ".claude" / "commands" / "pb.md"),
        (tdir / "pbg.md.tmpl", home / ".claude" / "commands" / "pbg.md"),
        (tdir / "pbg-builder.md.tmpl", home / ".claude" / "commands" / "pbg-builder.md"),
        (tdir / "pbg-planner.md.tmpl", home / ".claude" / "commands" / "pbg-planner.md"),
        (tdir / "route.md.tmpl", home / ".claude" / "commands" / "route.md"),
    ]
    agent_template = tdir / "agent.md.tmpl"
    if cfg.get("agents") and not agent_template.exists():
        fail(f"missing template: {agent_template}")
    for key in cfg.get("agents", {}):
        view = role_view(cfg, key)
        values = {
            "AGENT_KEY": key,
            "AGENT_DISPLAY_NAME": view["display_name"],
            "AGENT_MODEL": view["model"],
            "AGENT_MODEL_FIELD": claude_model_field(view["model"], view["provider"]),
            "AGENT_MODEL_SUMMARY": claude_model_summary(view["model"], view["provider"]),
            "AGENT_DISPATCH": external_dispatch_block(
                key, view["model"], view["provider"]
            ),
            "AGENT_PROVIDER": view["provider"],
            "AGENT_PURPOSE": view["purpose"],
            "AGENT_READ_ONLY": str(view["read_only"]).lower(),
            "AGENT_TOOLS": ", ".join(claude_tools(view["tools"], view["provider"])),
            "AGENT_INVOCATION": view["invocation"],
            "AGENT_AUTO_SELECT": str(view["auto_select"]).lower(),
            "AGENT_CAPABILITIES": list_text(view["capabilities"]),
            "AGENT_BOUNDARIES": list_text(view["boundaries"]),
            "AGENT_ESCALATE_TO": ", ".join(view["escalate_to"]) or "none",
            "AGENT_CAN_DELEGATE": str(view["can_delegate"]).lower(),
            "AGENT_DELEGATE_TO": ", ".join(view["delegate_to"]) or "none",
            "AGENT_OUTPUT_CONTRACT": list_text(view["output_contract"]),
            "AGENT_INFO_SOURCES": list_text(view["info_sources"]),
            "AGENT_KNOWLEDGE_DIR": str(SCRIPT_DIR / "agent-knowledge" / key),
        }
        jobs.append((agent_template, home / ".claude" / "agents" / f"{key}.md", values))
    for item in jobs:
        template, target = item[0], item[1]
        values = item[2] if len(item) == 3 else mapping
        if not template.exists():
            fail(f"missing template: {template}")
        write_out(target, render(template.read_text(encoding="utf-8"), values), dry)


ROLE_INFO_SOURCES = {
    "planner": [
        "Read the nearest AGENTS.md, README, manifests, affected source, and relevant tests before planning.",
        "Use read-only inspection and native documentation to distinguish evidence from assumptions.",
    ],
    "builder": [
        "Read the verified planner output, nearest AGENTS.md, project documentation, and affected implementation before editing.",
        "Run the project's native validation commands and inspect their evidence before reporting completion.",
    ],
}


def knowledge_info_sources(cfg: dict, key: str) -> list:
    if key in ROLE_INFO_SOURCES:
        return ROLE_INFO_SOURCES[key]
    return role_view(cfg, key).get("info_sources", [])


def profile_markdown(cfg: dict, key: str) -> str:
    view = role_view(cfg, key)
    sources = knowledge_info_sources(cfg, key)
    return f'''<!-- Generated by apply.py knowledge from roles.config.json. Do not hand-edit; edit configuration or generator inputs, then regenerate. -->
# {view["display_name"]} profile

## Specialty
{view["purpose"]}

## Capabilities
{list_text(view["capabilities"])}

## Boundaries
{list_text(view["boundaries"])}

## Information gathering
{list_text(sources)}

## Output contract
{list_text(view["output_contract"])}

## Durable lessons
Before substantive work, read [LESSONS.md](./LESSONS.md) alongside the source
material above. After substantive work, append at most one generalized,
evidence-backed lesson in the documented format if it will improve future work.
Never include secrets, personal data, credentials, raw task logs, or private
content. At 50 dated entries, consolidate the oldest reusable points into
`## Durable practices` before adding more. Do not modify this profile; regenerate
it with `python3 apply.py knowledge`. The lessons file is deliberately preserved.
'''


def lessons_markdown(key: str) -> str:
    return f'''# {key} lessons

This is durable, harness-neutral working knowledge for the `{key}` profile.
Keep behavioral, reusable lessons here; do **not** store secrets, credentials,
personal data, private task content, or chronological task logs.

## Durable practices

- Read the profile and applicable project instructions before work.

## Dated lessons

<!-- Append at most one evidence-backed, generalized entry after substantive work:
- YYYY-MM-DD | task type | reusable lesson | evidence/path or validation command
When this section reaches 50 entries, fold the oldest reusable items into Durable
practices and remove the consolidated dated entries. -->
'''


def install_knowledge(cfg: dict, dry: bool) -> None:
    root = SCRIPT_DIR / "agent-knowledge"
    readme = root / "README.md"
    readme_content = '''# Agent knowledge and lessons

This directory is the portable, source-controlled knowledge location for every
registered profile. `PROFILE.md` files are generated from `roles.config.json`
(and the PB defaults in `apply.py`) by `python3 apply.py knowledge`. Change the
source configuration, not generated profiles. `LESSONS.md` is intentionally
created once and then preserved across regenerations.

Before substantive work, an agent reads its profile, lessons, project
instructions, and the profile's information sources. After work it may append
**at most one** reusable, evidence-backed lesson in the documented dated format.
Lessons are not task logs and must never contain secrets, credentials, personal
data, raw private content, or unverified claims. At 50 dated entries, consolidate
the oldest reusable entries into `## Durable practices`.
'''
    if not readme.exists():
        write_out(readme, readme_content, dry)
    for key in ALL_AGENT_KEYS:
        directory = root / key
        write_out(directory / "PROFILE.md", profile_markdown(cfg, key), dry)
        lessons = directory / "LESSONS.md"
        if lessons.exists():
            if dry:
                print(f"--- would preserve {lessons} ---")
        else:
            write_out(lessons, lessons_markdown(key), dry)


def generic_block(cfg: dict) -> str:
    lines = ["## Configurable Agent Framework", "", "Planner and Builder are the PB core. router.py provides deterministic, explainable applicability recognition; every handoff requires confirmation before delegation. Team Leader is never automatically selected.", "", "### PB core"]
    for key in ROLE_KEYS:
        view = role_view(cfg, key)
        mode = "read-only" if view["read_only"] else "write-capable"
        lines.append(f"- **{key}** — `{view['model']}` ({view['provider']}); {mode}. {view['purpose']}")
    lines += ["", "### Specialist registry", "", "| Key | Model | Invocation | Auto-select | Purpose |", "|---|---|---|---|---|"]
    for key in cfg.get("agents", {}):
        view = role_view(cfg, key)
        lines.append(f"| `{key}` | `{view['model']}` | `{view['invocation']}` | `{str(view['auto_select']).lower()}` | {view['purpose']} |")
    lines += ["", "Team Leader is direct-call-only and must never be selected automatically. Use Runner as the everyday front door; use Planner → Builder for substantive development. Change models only in roles.config.json and regenerate adapters."]
    return "\n".join(lines) + "\n"


def print_table(cfg: dict) -> None:
    print(f"config version {cfg.get('version')} — resolved agents:\n")
    for key in ROLE_KEYS:
        view = role_view(cfg, key)
        print(f"  {key:14} -> {view['model']} [{view['provider']}, readOnly={view['read_only']}]")
    for key in cfg.get("agents", {}):
        view = role_view(cfg, key)
        print(f"  {key:14} -> {view['model']} [{view['invocation']}, autoSelect={view['auto_select']}, provider={view['provider']}]")
    if not cfg.get("agents"):
        print("  (no specialist agents configured)")
    print()


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate the configurable agent framework and harness adapters.")
    ap.add_argument("action", choices=["validate", "show", "claude", "generic", "knowledge", "all", "set"])
    ap.add_argument("role", nargs="?", help="(set) PB role or specialist key")
    ap.add_argument("model", nargs="?", help="(set) model class")
    ap.add_argument("--config", default=str(SCRIPT_DIR / "roles.config.json"))
    ap.add_argument("--home", default=os.environ.get("HOME", str(Path.home())))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--id", dest="pin_id", default=None)
    ap.add_argument("--class", dest="cls", default=None)
    ap.add_argument("--provider", default=None)
    ap.add_argument("--no-apply", action="store_true")
    args = ap.parse_args()
    cfg_path, cfg = Path(args.config), load_config(Path(args.config))
    errors = validate(cfg)
    if errors:
        print("Config is INVALID:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        raise SystemExit(1)
    if args.action == "set":
        changes = apply_set(cfg, args)
        errors = validate(cfg)
        if errors:
            fail("resulting config would be invalid: " + "; ".join(errors))
        if args.dry_run:
            print(f"[dry-run] {args.role}: {'; '.join(changes)}")
            print_table(cfg)
            return
        cfg_path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Updated {args.role}: {'; '.join(changes)}")
        print_table(cfg)
        if not args.no_apply:
            install_claude(cfg, Path(args.home).expanduser(), False)
        return
    if args.action in ("validate", "show"):
        print("Config is valid.\n")
        print_table(cfg)
        return
    if args.action in ("claude", "all"):
        install_claude(cfg, Path(args.home).expanduser(), args.dry_run)
    if args.action in ("knowledge", "all"):
        install_knowledge(cfg, args.dry_run)
    if args.action in ("generic", "all"):
        print("\n" + generic_block(cfg))


if __name__ == "__main__":
    main()
