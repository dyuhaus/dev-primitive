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
SPECIALIST_KEYS = ("runner", "tech-writer", "prose-writer", "team-leader", "l1-programmer", "librarian", "fe-designer", "audit", "code-reviewer")
ALL_AGENT_KEYS = ROLE_KEYS + SPECIALIST_KEYS

# Wire protocols a provider entry may declare. `deepseek` and `openrouter` were
# added on 2026-08-21: this machine has been multi-provider since 2026-08-16
# (Codex on OpenAI, Pi on OpenRouter, dsh on DeepSeek) and a registry that
# cannot name them cannot describe the machine it configures.
PROVIDER_TYPES = ("anthropic", "openai", "google", "deepseek", "openrouter", "local")

# Provider *key* names consumers recognise. Downstream tools (Maestro's
# backend/lib/roles.js, the harness adapters below) map a role to a harness by
# the provider's key, not by its type — so a DeepSeek provider keyed `dsh`
# validates cleanly and is then silently unroutable. Keys outside this set are
# allowed but warned about, because refusing them would break a private config.
RECOGNISED_PROVIDER_KEYS = ("anthropic", "openai", "deepseek", "openrouter")

# Which provider types each harness adapter can actually *dispatch* a model to.
# This is a property of the harness, not of the machine's policy: Claude Code
# resolves a subagent's `model:` against Anthropic classes and ids only, Codex
# against OpenAI models, dsh against DeepSeek models. An adapter that emits a
# model field it cannot dispatch produces a profile that silently runs on the
# session model while its own file claims otherwise.
ADAPTER_DISPATCHABLE_PROVIDER_TYPES = {
    "claude-code": ("anthropic",),
    "codex": ("openai",),
    "dsh": ("deepseek",),
    "pi": ("openrouter", "anthropic"),
    "hermes": (),  # Hermes takes its model from its own harness configuration.
}

# Model classes and id prefixes Claude Code will actually resolve. Anything else
# in a `model:` frontmatter field is discarded silently by the harness.
ANTHROPIC_MODEL_CLASSES = ("opus", "sonnet", "haiku", "fable", "default", "inherit")
ANTHROPIC_MODEL_ID_PREFIXES = (
    "claude-",
    "anthropic.claude-",
    "us.anthropic.claude-",
    "eu.anthropic.claude-",
    "apac.anthropic.claude-",
)


class AdapterUnsupported(Exception):
    """One harness adapter cannot render the current registry.

    Raised instead of exiting so a caller can decide: an explicit single-adapter
    request is a hard failure, while a multi-surface refresh skips that adapter
    with a warning and still regenerates the neutral surfaces.
    """


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
            if prov.get("type") not in PROVIDER_TYPES:
                errs.append(f"providers.{name}.type must be one of {'|'.join(PROVIDER_TYPES)}")
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
# Claude Code model fields
# --------------------------------------------------------------------------- #
# Claude Code resolves a subagent's `model:` frontmatter against Anthropic
# classes and ids only, and silently discards anything else — the subagent then
# runs on the session model while its file still claims otherwise.
#
# This guard used to be keyed on the provider *name* and was called from exactly
# one place (the specialists loop). Neither half worked: `apply.py set <role>
# <model>` never touches the provider field, so the guard could not fire on the
# path the documented one-liner actually uses, and planner, builder and the
# post-workflow auditor bypassed it entirely. `set builder gpt-5.6-terra` exited
# 0, printed a success table, and rendered an undispatchable model nine times.
#
# It is now keyed on the resolved model class checked against the classes and id
# prefixes Claude Code can really resolve, it covers every profile including the
# PB roles and the auditor, and it refuses to render rather than emitting a value
# the harness will throw away.


def provider_type_of(cfg: dict, provider_name: str) -> str:
    return str(((cfg.get("providers") or {}).get(provider_name) or {}).get("type", ""))


def is_anthropic_model(model: str) -> bool:
    """True when Claude Code can resolve this value in a `model:` field."""
    name = str(model).strip().lower()
    if not name:
        return False
    if name in ANTHROPIC_MODEL_CLASSES:
        return True
    return any(name.startswith(prefix) for prefix in ANTHROPIC_MODEL_ID_PREFIXES)


def claude_model_field(model: str, provider_type: str) -> str:
    """The value to write into a Claude Code `model:` field, or refuse.

    `provider_type` is the provider's declared wire protocol, not its key name:
    a DeepSeek endpoint keyed `anthropic` must still be refused.
    """
    if provider_type and provider_type != "anthropic":
        raise AdapterUnsupported(
            f"model '{model}' uses a '{provider_type}' provider, but Claude Code can "
            "only dispatch Anthropic models for a subagent"
        )
    if not is_anthropic_model(model):
        raise AdapterUnsupported(
            f"model '{model}' is not a model class or id Claude Code can resolve "
            f"(known classes: {', '.join(ANTHROPIC_MODEL_CLASSES)}; ids must start "
            f"with one of: {', '.join(ANTHROPIC_MODEL_ID_PREFIXES)})"
        )
    return model


def claude_model_summary(model: str, provider: str) -> str:
    return f"running on the configured model class ({model})"


def claude_dispatch_report(cfg: dict) -> list:
    """Every profile the Claude adapter cannot dispatch, with the reason.

    Returns a list of one-line strings. Empty means the whole registry renders.
    Collected rather than raised on the first hit so one run names every profile
    that has to change, instead of one per re-run.
    """
    problems = []
    checks = [(f"roles.{key}", role_view(cfg, key)) for key in ROLE_KEYS]
    checks += [(f"agents.{key}", role_view(cfg, key)) for key in cfg.get("agents", {})]
    for where, view in checks:
        try:
            claude_model_field(view["model"], view["provider_type"])
        except AdapterUnsupported as exc:
            problems.append(f"{where}: {exc}")
    post_audit = ((cfg.get("routing") or {}).get("postWorkflowAudit") or {})
    if post_audit.get("model") is not None:
        model = resolve_model({"model": post_audit.get("model", {})})
        ptype = provider_type_of(cfg, (post_audit.get("model") or {}).get("provider", ""))
        try:
            claude_model_field(model, ptype)
        except AdapterUnsupported as exc:
            problems.append(f"routing.postWorkflowAudit: {exc}")
    return problems


def template_mapping(cfg: dict, adapter: str = "claude-code") -> dict:
    """Placeholder values for the PB templates.

    The `*_MODEL_FIELD` entries are the only values a template may put in a
    frontmatter `model:` line. They go through the adapter's dispatch guard, so
    an undispatchable model stops the render here rather than being written out.
    """
    p, b = role_view(cfg, "planner"), role_view(cfg, "builder")
    post_audit = ((cfg.get("routing") or {}).get("postWorkflowAudit") or {})
    audit_model = resolve_model({"model": post_audit.get("model", {})})
    audit_provider = (post_audit.get("model") or {}).get("provider", "")
    audit_provider_type = provider_type_of(cfg, audit_provider)
    field = claude_model_field if adapter == "claude-code" else (lambda model, _ptype: model)
    return {
        "PLANNER_MODEL": p["model"],
        "BUILDER_MODEL": b["model"],
        "PLANNER_MODEL_FIELD": field(p["model"], p["provider_type"]),
        "BUILDER_MODEL_FIELD": field(b["model"], b["provider_type"]),
        "PLANNER_PURPOSE": p["purpose"],
        "BUILDER_PURPOSE": b["purpose"],
        "PLANNER_PROVIDER": p["provider"],
        "BUILDER_PROVIDER": b["provider"],
        "WORKFLOW_AUDIT_ENABLED": str(post_audit.get("enabled", False)).lower(),
        "WORKFLOW_AUDIT_MODEL": audit_model,
        "WORKFLOW_AUDIT_MODEL_FIELD": field(audit_model, audit_provider_type),
        "WORKFLOW_AUDIT_THINKING": post_audit.get("thinking", "medium"),
        "ANTHROPIC_CLASSES": ", ".join(f"`{name}`" for name in ANTHROPIC_MODEL_CLASSES),
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


def short_purpose(purpose: str, limit: int = 90) -> str:
    """First clause of a purpose, for a one-line command description.

    Slash-command descriptions render on a single line, so the multi-clause
    registry purposes have to be trimmed. Cut on a separator when one falls in
    range so the result stays a readable phrase rather than a truncated word.
    """
    text = " ".join(purpose.split())
    if len(text) <= limit:
        return text
    window = text[:limit]
    for sep in ("; ", ": ", ", "):
        head, found, _ = window.rpartition(sep)
        if found and len(head) > limit // 3:
            return head
    return window.rsplit(" ", 1)[0] + "…"


def delegation_note(view: dict) -> str:
    """One sentence on whether this profile may delegate, for the invoke command."""
    if not view.get("can_delegate"):
        return (
            "does not delegate. If the work needs another specialist, it must say so "
            "rather than hand off."
        )
    targets = ", ".join(view.get("delegate_to") or []) or "its registered targets"
    return f"may delegate narrowly scoped subtasks to {targets}."


def render_claude(cfg: dict, home: Path) -> list:
    """Render every Claude Code surface in memory: [(target Path, content)].

    Raises AdapterUnsupported before producing anything when the registry names
    a model Claude Code cannot dispatch. Nothing is written here, so a caller can
    validate a proposed config change before it reaches disk.
    """
    problems = claude_dispatch_report(cfg)
    if problems:
        raise AdapterUnsupported(
            "the Claude Code adapter cannot dispatch every configured profile, so "
            "it refuses to render one:\n"
            + "\n".join(f"  - {line}" for line in problems)
            + "\nClaude Code discards an unresolvable `model:` value silently and "
            "runs the subagent on the session model, so emitting these files would "
            "look like success. Configure an Anthropic class for these profiles, or "
            "run the harness whose adapter can dispatch them."
        )
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
        # Pi calls this /agents; that name is a Claude Code builtin.
        (tdir / "agent-catalog.md.tmpl", home / ".claude" / "commands" / "agent-catalog.md"),
    ]
    agent_template = tdir / "agent.md.tmpl"
    invoke_template = tdir / "agent-invoke.md.tmpl"
    model_template = tdir / "agent-model.md.tmpl"
    if cfg.get("agents") and not agent_template.exists():
        fail(f"missing template: {agent_template}")
    for key in cfg.get("agents", {}):
        view = role_view(cfg, key)
        values = {
            "AGENT_KEY": key,
            "AGENT_DISPLAY_NAME": view["display_name"],
            "AGENT_MODEL": view["model"],
            "AGENT_MODEL_FIELD": claude_model_field(view["model"], view["provider_type"]),
            "AGENT_MODEL_SUMMARY": claude_model_summary(view["model"], view["provider"]),
            "AGENT_PROVIDER": view["provider"],
            "AGENT_PURPOSE": view["purpose"],
            "AGENT_READ_ONLY": str(view["read_only"]).lower(),
            "AGENT_TOOLS": ", ".join(view["tools"]),
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
            "AGENT_PURPOSE_SHORT": short_purpose(view["purpose"]),
            "AGENT_DELEGATION_NOTE": delegation_note(view),
            "ANTHROPIC_CLASSES": mapping["ANTHROPIC_CLASSES"],
        }
        jobs.append((agent_template, home / ".claude" / "agents" / f"{key}.md", values))
        # Per-agent slash commands, matching Pi's /<agent> and /<agent>-model.
        jobs.append((invoke_template, home / ".claude" / "commands" / f"{key}.md", values))
        jobs.append((model_template, home / ".claude" / "commands" / f"{key}-model.md", values))
    mapping["DIRECT_CALL_ONLY"] = (
        ", ".join(
            k for k, a in (cfg.get("agents") or {}).items()
            if a.get("invocation") == "direct-call-only"
        )
        or "none"
    )
    rendered = []
    for item in jobs:
        template, target = item[0], item[1]
        values = item[2] if len(item) == 3 else mapping
        if not template.exists():
            fail(f"missing template: {template}")
        rendered.append((target, render(template.read_text(encoding="utf-8"), values)))
    return rendered


def install_claude(cfg: dict, home: Path, dry: bool) -> None:
    for target, content in render_claude(cfg, home):
        write_out(target, content, dry)


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


# --------------------------------------------------------------------------- #
# Harness skill adapters (Codex, dsh, Hermes)
# --------------------------------------------------------------------------- #
# Codex, dsh and Hermes all discover skills as `<root>/<name>/SKILL.md` with
# `name` and `description` frontmatter, so one renderer serves all three; the
# per-harness templates carry the differences (which delegation tool exists,
# which review command exists, what the harness can and cannot dispatch).
#
# None of these three write a model field, because none of them can dispatch the
# Anthropic classes this registry configures. Rather than pretending otherwise,
# each profile states plainly which model the registry intends and that the
# session model is what actually runs.

HARNESS_SKILL_ROOTS = {
    "claude": ".claude/skills",
    "codex": ".codex/skills",
    "dsh": ".dsh/skills",
    "hermes": ".hermes/skills",
}

# The harness-neutral skills root every harness surface is mirrored from.
NEUTRAL_SKILL_ROOT = "skills"

HARNESS_LABELS = {"codex": "Codex", "dsh": "the DeepSeek Harness (dsh)", "hermes": "Hermes"}


def frontmatter_description(text: str, limit: int = 400) -> str:
    """A single-line skill description short enough for every harness catalog."""
    flat = " ".join(str(text).split())
    if len(flat) <= limit:
        return flat
    return flat[: limit - 1].rsplit(" ", 1)[0] + "…"


def model_routing_note(view: dict, adapter: str) -> str:
    """One honest sentence about whether this harness can run the model configured."""
    label = HARNESS_LABELS.get(adapter, adapter)
    dispatchable = ADAPTER_DISPATCHABLE_PROVIDER_TYPES.get(adapter, ())
    if view["provider_type"] in dispatchable:
        return (
            f"The registry configures this profile as `{view['model']}` on the "
            f"`{view['provider']}` provider, and {label} can dispatch that model."
        )
    return (
        f"The registry configures this profile as `{view['model']}` on the "
        f"`{view['provider']}` provider (a {view['provider_type'] or 'declared'} "
        f"endpoint). {label} cannot dispatch that model, so this profile runs on "
        "whatever model the current session is using. Treat the configured model "
        "as routing intent, not a fact about this session, and never report that "
        "the profile ran on it."
    )


def invocation_rule(view: dict) -> str:
    if view["invocation"] == "direct-call-only":
        return (
            "This profile runs only when the user explicitly asks for it. Never "
            "self-invoke it, volunteer it, or make it an automatic routing target."
        )
    return "Use this profile only for work inside its stated scope; escalate when the work leaves it."


def roster_sentence(cfg: dict) -> str:
    """The canonical one-line roster, generated so a hand-written count cannot drift."""
    agents = list(cfg.get("agents", {}))
    direct = [k for k in agents if cfg["agents"][k].get("invocation") == "direct-call-only"]
    ordinary = [k for k in agents if k not in direct]
    names = ", ".join(f"`{k}`" for k in ordinary)
    direct_names = ", ".join(f"`{k}`" for k in direct)
    return (
        f"Beyond the `planner`/`builder` core there are {len(agents)} specialists: "
        f"{names}, plus {len(direct)} direct-call-only profiles that must never be "
        f"auto-selected — {direct_names}."
    )


def roster_table(cfg: dict) -> str:
    lines = ["| Key | Display name | Model | Provider | Invocation | Auto-select |", "|---|---|---|---|---|---|"]
    for key in ROLE_KEYS + tuple(cfg.get("agents", {})):
        view = role_view(cfg, key)
        lines.append(
            f"| `{key}` | {view['display_name']} | `{view['model']}` | `{view['provider']}` | "
            f"`{view['invocation']}` | `{str(view['auto_select']).lower()}` |"
        )
    return "\n".join(lines)


def auditor_models(cfg: dict) -> str:
    """The models the two review roles actually run on, read from the registry."""
    post_audit = ((cfg.get("routing") or {}).get("postWorkflowAudit") or {})
    light = resolve_model({"model": post_audit.get("model", {})}) or "(unset)"
    full = role_view(cfg, "audit")["model"] if "audit" in cfg.get("agents", {}) else "(unset)"
    return f"`{light}` for the light post-workflow audit and `{full}` for the direct-call Audit profile"


def skill_list(cfg: dict, prefix: str = "agent-") -> str:
    lines = []
    for key in ROLE_KEYS + tuple(cfg.get("agents", {})):
        view = role_view(cfg, key)
        suffix = " — direct-call-only; never invoke automatically" if view["invocation"] == "direct-call-only" else ""
        lines.append(f"- `{prefix}{key}` — {short_purpose(view['purpose'])}{suffix}")
    return "\n".join(lines)


def harness_mapping(cfg: dict, adapter: str) -> dict:
    mapping = template_mapping(cfg, adapter)
    mapping.update(
        {
            "REPO_DIR": str(SCRIPT_DIR),
            "HARNESS_LABEL": HARNESS_LABELS.get(adapter, adapter),
            "ROSTER_TABLE": roster_table(cfg),
            "ROSTER_SENTENCE": roster_sentence(cfg),
            "SKILL_LIST": skill_list(cfg),
            "AUDITOR_MODELS": auditor_models(cfg),
            "PLANNER_ROUTING_NOTE": model_routing_note(role_view(cfg, "planner"), adapter),
            "BUILDER_ROUTING_NOTE": model_routing_note(role_view(cfg, "builder"), adapter),
            "DIRECT_CALL_ONLY": ", ".join(
                k for k, a in (cfg.get("agents") or {}).items() if a.get("invocation") == "direct-call-only"
            )
            or "none",
        }
    )
    return mapping


def render_harness_skills(cfg: dict, home: Path, adapter: str) -> list:
    """Render one harness's whole skill surface: [(target Path, content)]."""
    tdir = SCRIPT_DIR / "adapters" / adapter
    root = home / HARNESS_SKILL_ROOTS[adapter]
    agent_template = tdir / "agent.SKILL.md.tmpl"
    for template in (agent_template, tdir / "framework.SKILL.md.tmpl", tdir / "pb.SKILL.md.tmpl", tdir / "route.SKILL.md.tmpl"):
        if not template.exists():
            fail(f"missing template: {template}")
    shared = harness_mapping(cfg, adapter)
    rendered = [
        (root / "agent-framework" / "SKILL.md", render((tdir / "framework.SKILL.md.tmpl").read_text(encoding="utf-8"), shared)),
        (root / "agent-pb" / "SKILL.md", render((tdir / "pb.SKILL.md.tmpl").read_text(encoding="utf-8"), shared)),
        (root / "agent-route" / "SKILL.md", render((tdir / "route.SKILL.md.tmpl").read_text(encoding="utf-8"), shared)),
    ]
    body = agent_template.read_text(encoding="utf-8")
    # Roles first, then specialists: the Hermes installer used to iterate only
    # the specialists map, so planner and builder could never appear at all.
    for key in ROLE_KEYS + tuple(cfg.get("agents", {})):
        view = role_view(cfg, key)
        values = dict(shared)
        values.update(
            {
                "AGENT_KEY": key,
                "AGENT_SKILL_NAME": f"agent-{key}",
                "AGENT_DISPLAY_NAME": view["display_name"],
                "AGENT_DESCRIPTION": frontmatter_description(view["purpose"]),
                "AGENT_PURPOSE": view["purpose"],
                "AGENT_PURPOSE_SHORT": short_purpose(view["purpose"]),
                "AGENT_MODEL": view["model"],
                "AGENT_MODEL_CLASS": view["class"],
                "AGENT_MODEL_ID": view["id"],
                "AGENT_PROVIDER": view["provider"],
                "AGENT_PROVIDER_TYPE": view["provider_type"],
                "AGENT_MODEL_ROUTING_NOTE": model_routing_note(view, adapter),
                "AGENT_DELEGATION_NOTE": delegation_note(view),
                "AGENT_INVOCATION": view["invocation"],
                "AGENT_INVOCATION_RULE": invocation_rule(view),
                "AGENT_AUTO_SELECT": str(view["auto_select"]).lower(),
                "AGENT_READ_ONLY": str(view["read_only"]).lower(),
                "AGENT_TOOLS": ", ".join(view["tools"]) or "not restricted by this harness",
                "AGENT_CAPABILITIES": list_text(view["capabilities"]),
                "AGENT_BOUNDARIES": list_text(view["boundaries"]),
                "AGENT_ESCALATE_TO": ", ".join(view["escalate_to"]) or "none",
                "AGENT_CAN_DELEGATE": str(view["can_delegate"]).lower(),
                "AGENT_DELEGATE_TO": ", ".join(view["delegate_to"]) or "none",
                "AGENT_OUTPUT_CONTRACT": list_text(view["output_contract"]),
                "AGENT_INFO_SOURCES": list_text(knowledge_info_sources(cfg, key)),
                "AGENT_KNOWLEDGE_DIR": str(SCRIPT_DIR / "agent-knowledge" / key),
            }
        )
        rendered.append((root / f"agent-{key}" / "SKILL.md", render(body, values)))
    return rendered


def install_harness_skills(cfg: dict, home: Path, adapter: str, dry: bool) -> None:
    for target, content in render_harness_skills(cfg, home, adapter):
        write_out(target, content, dry)


def link_shared_skills(home: Path, dry: bool, adapters=("claude", "codex", "dsh", "hermes")) -> list:
    """Mirror the neutral ~/skills roots into every harness's skill directory.

    Additive only: an existing entry is left exactly as it is, and nothing is
    ever removed. Without this a Codex session has five of the eighteen shared
    skills — no git-workflow, no subsite-scaffold, no decommission-checklist,
    no harden-service — while its instructions assume it has all of them.
    """
    source = home / NEUTRAL_SKILL_ROOT
    actions = []
    if not source.is_dir():
        print(f"  (no shared skill root at {source}; nothing to link)")
        return actions
    names = sorted(entry.name for entry in source.iterdir() if not entry.name.startswith("."))
    for adapter in adapters:
        root = home / HARNESS_SKILL_ROOTS[adapter]
        for name in names:
            target, origin = root / name, (source / name).resolve()
            if target.exists() or target.is_symlink():
                continue
            actions.append((target, origin))
            if dry:
                print(f"--- would link {target} -> {origin} ---")
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.symlink_to(origin)
            print(f"  linked {target} -> {origin}")
    if not actions:
        print("  every harness skill root already carries the shared skills")
    return actions


def write_config(cfg_path: Path, cfg: dict) -> None:
    """Persist the registry atomically, so a crashed write cannot truncate it."""
    payload = json.dumps(cfg, indent=2, ensure_ascii=False) + "\n"
    temp = cfg_path.with_name(cfg_path.name + ".tmp")
    temp.write_text(payload, encoding="utf-8")
    os.replace(temp, cfg_path)


def installed_adapters(home: Path) -> list:
    """Which harness surfaces exist on this machine, so `set` can refresh them."""
    present = []
    if (home / ".claude").is_dir():
        present.append("claude")
    for adapter in ("codex", "dsh", "hermes"):
        if (home / f".{adapter}").is_dir():
            present.append(adapter)
    return present


def refresh_surfaces(cfg: dict, home: Path, dry: bool) -> list:
    """Regenerate every installed harness surface. Returns adapters that failed.

    `set` used to refresh Claude alone, so after a model change the registry said
    one thing and every other installed surface still said the old one.
    """
    skipped = []
    install_knowledge(cfg, dry)
    for adapter in installed_adapters(home):
        try:
            if adapter == "claude":
                install_claude(cfg, home, dry)
            else:
                install_harness_skills(cfg, home, adapter, dry)
        except AdapterUnsupported as exc:
            skipped.append(adapter)
            print(f"WARNING: skipping the {adapter} adapter — {exc}", file=sys.stderr)
    return skipped


# --------------------------------------------------------------------------- #
# Generated documentation blocks
# --------------------------------------------------------------------------- #
# The roster count, the auditors' models and the per-harness surface table were
# all hand-written and all drifted: the docs named a model the registry does not
# configure, and the roster said eight specialists while the registry held nine —
# omitting code-reviewer, the one profile the Git Workflow Standard makes
# mandatory. These blocks are regenerated from the registry by `apply.py docs`
# and a test fails the build when a checked-in doc no longer matches.

DOC_FILES = ("README.md", "PRIMITIVE.md", "AGENT-FRAMEWORK.md", "HARNESS-INSTALLATION.md", "AGENTS.md")


def harness_surface_table(cfg: dict) -> str:
    rows = [
        ("Claude Code", "`~/.claude/agents/` and `~/.claude/commands/`",
         "PB subagents, `/pb`, `/pbg`, `/route`, `/agent-catalog`, and a `/<agent>` + `/<agent>-model` pair per profile. The only adapter that writes a `model:` field, and the only one that can dispatch the registry's Anthropic classes."),
        ("Codex", "`~/.codex/skills/agent-*/SKILL.md`",
         "One skill per profile plus `agent-framework`, `agent-pb`, `agent-route`. No model routing: Codex dispatches OpenAI models, so every profile runs on the session model. `codex review` is the native review path."),
        ("dsh", "`~/.dsh/skills/agent-*/SKILL.md`",
         "The same skill set through dsh's filesystem skill provider (`user-dsh` root). No model routing: dsh dispatches DeepSeek models. Delegation exists through its `subagent` tool but carries no per-profile model."),
        ("Pi", "`~/.pi/agent/extensions/pb-primitive/`",
         "PB tools plus a generated `<key>_agent` tool per profile, resolved from this same registry."),
        ("Hermes", "`~/.hermes/skills/agent-*/SKILL.md`",
         "One skill per profile including `planner` and `builder`. Hermes's active model comes from its own harness configuration. No Hermes CLI is installed today."),
    ]
    lines = ["| Harness | Surface | Result |", "|---|---|---|"]
    lines += [f"| {name} | {surface} | {result} |" for name, surface, result in rows]
    return "\n".join(lines)


DOC_BLOCKS = {
    "roster": roster_sentence,
    "roster-table": roster_table,
    "auditor-models": lambda cfg: (
        "The two review roles run on "
        + auditor_models(cfg)
        + ". Both are Anthropic models chosen to differ from the builder's, which is "
        "model-level independence, not cross-family independence — say so when an "
        "artifact ranks or compares AI models."
    ),
    "harness-surfaces": harness_surface_table,
}


BLOCK_OPEN = "<!-- BEGIN GENERATED: "


def render_doc(cfg: dict, text: str) -> str:
    """Replace every marked generated block in one document.

    Walks the document once so a block is never rescanned, which is what keeps
    this terminating regardless of how many blocks a file carries.
    """
    out, rest = [], text
    while True:
        start = rest.find(BLOCK_OPEN)
        if start < 0:
            out.append(rest)
            return "".join(out)
        out.append(rest[:start])
        rest = rest[start:]
        header_end = rest.find(" -->")
        if header_end < 0:
            fail("a generated block header is never terminated")
        header = rest[: header_end + 4]
        name = header[len(BLOCK_OPEN) :].split(" ", 1)[0]
        if name not in DOC_BLOCKS:
            fail(f"unknown generated block '{name}'; known blocks: {', '.join(DOC_BLOCKS)}")
        end_marker = f"<!-- END GENERATED: {name} -->"
        end = rest.find(end_marker)
        if end < 0:
            fail(f"generated block '{name}' is opened but never closed")
        out.append(f"{header}\n{DOC_BLOCKS[name](cfg)}\n{end_marker}")
        rest = rest[end + len(end_marker) :]


def docs_drift(cfg: dict) -> list:
    """Documents whose generated blocks no longer match the registry."""
    stale = []
    for name in DOC_FILES:
        path = SCRIPT_DIR / name
        if not path.exists():
            continue
        current = path.read_text(encoding="utf-8")
        if render_doc(cfg, current) != current:
            stale.append(name)
    return stale


def update_docs(cfg: dict, dry: bool) -> list:
    changed = []
    for name in DOC_FILES:
        path = SCRIPT_DIR / name
        if not path.exists():
            continue
        current = path.read_text(encoding="utf-8")
        updated = render_doc(cfg, current)
        if updated == current:
            continue
        changed.append(name)
        if dry:
            print(f"--- would update generated blocks in {path} ---")
        else:
            path.write_text(updated, encoding="utf-8")
            print(f"  updated {path}")
    if not changed:
        print("  every generated documentation block already matches the registry")
    return changed


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
    ap.add_argument("action", choices=["validate", "show", "roster", "claude", "codex", "dsh", "hermes", "generic", "knowledge", "docs", "all", "set"])
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
    home = Path(args.home).expanduser()
    if args.action == "set":
        changes = apply_set(cfg, args)
        errors = validate(cfg)
        if errors:
            fail("resulting config would be invalid: " + "; ".join(errors))
        # Render every installed adapter against the IN-MEMORY config before the
        # write. `set` used to persist first and guard afterwards, so a rejected
        # change left the source of truth changed and every surface unchanged.
        for adapter in installed_adapters(home):
            try:
                if adapter == "claude":
                    render_claude(cfg, home)
                else:
                    render_harness_skills(cfg, home, adapter)
            except AdapterUnsupported as exc:
                fail(
                    f"refusing to change the registry: the {adapter} adapter cannot "
                    f"render the result, so nothing was written.\n{exc}"
                )
        if args.dry_run:
            print(f"[dry-run] {args.role}: {'; '.join(changes)}")
            print_table(cfg)
            return
        write_config(cfg_path, cfg)
        print(f"Updated {args.role}: {'; '.join(changes)}")
        print_table(cfg)
        if not args.no_apply:
            refresh_surfaces(cfg, home, False)
        return
    if args.action in ("validate", "show"):
        print("Config is valid.\n")
        print_table(cfg)
        return
    if args.action == "roster":
        print(roster_sentence(cfg))
        return
    if args.action == "docs":
        update_docs(cfg, args.dry_run)
        return
    # Neutral surfaces first: they are what a harness without an adapter reads,
    # and one undispatchable profile used to stop them regenerating too.
    if args.action in ("knowledge", "all"):
        install_knowledge(cfg, args.dry_run)
    if args.action in ("generic", "all"):
        print("\n" + generic_block(cfg))
    for adapter in ("codex", "dsh", "hermes"):
        if args.action == adapter:
            install_harness_skills(cfg, home, adapter, args.dry_run)
    if args.action in ("claude", "all"):
        try:
            install_claude(cfg, home, args.dry_run)
        except AdapterUnsupported as exc:
            # An explicit `apply.py claude` is a hard failure; inside `all` it is
            # a skip, because the neutral surfaces have nothing to do with
            # Claude Code's frontmatter limitation.
            if args.action == "claude":
                fail(str(exc))
            print(f"WARNING: skipping the Claude Code adapter — {exc}", file=sys.stderr)


if __name__ == "__main__":
    main()
