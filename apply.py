#!/usr/bin/env python3
"""
apply.py — installer/generator for the two-role development primitive.

The single source of truth is roles.config.json. This script validates it and
renders each harness's adapter from it, so the exact model *class* for the
planner and the builder is configured in one place and propagates everywhere.

Usage:
    python3 apply.py validate            # validate the config, print resolved roles
    python3 apply.py show                # print the resolved role/model table
    python3 apply.py claude              # (re)generate the Claude Code adapter
    python3 apply.py generic             # print a portable block for any harness
    python3 apply.py all                 # generate Claude Code + print portable block
    python3 apply.py set <role> <class>  # change a role's model + regenerate (e.g. set builder sonnet)
    python3 apply.py resolve <role>      # print machine-readable role facts (transport, model, key source)
    python3 apply.py prompt <role>       # print the rendered role charter (used by bin/role-call)

Options:
    --config PATH   config file (default: roles.config.json next to this script)
    --home PATH     home dir for the Claude Code adapter (default: $HOME)
    --dry-run       print what would be written instead of writing
    --id ID         (set) pin an exact model id; empty string clears the pin
    --class CLASS   (set) set the model class explicitly
    --provider P    (set) set the role's provider
    --access A      (set) set the role's transport: harness | api
    --no-apply      (set) update the config but do not regenerate the adapter
    --format F      (resolve) output format: env (default) | json

No third-party dependencies. Python 3.8+.
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
ROLE_KEYS = ("planner", "builder")
ACCESS_VALUES = ("harness", "api")
# Marker that identifies a file this generator wrote (used before deleting a stale one).
GENERATED_MARKER = "Generated from dev-primitive"


# ---------------------------------------------------------------- load + validate
def load_config(path: Path) -> dict:
    try:
        with path.open(encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        fail(f"config not found: {path}")
    except json.JSONDecodeError as exc:
        fail(f"config is not valid JSON: {exc}")


def validate(cfg: dict):
    """Return (errors, warnings) — both lists of human-readable strings. [] errors means valid."""
    errs = []
    warns = []

    if not isinstance(cfg.get("version"), int) or cfg.get("version", 0) < 1:
        errs.append("version must be an integer >= 1")

    class_ids = cfg.get("classIds")
    if class_ids is not None:
        if not isinstance(class_ids, dict):
            errs.append("classIds must be an object mapping class -> model id")
            class_ids = {}
        else:
            for k, val in class_ids.items():
                if not isinstance(val, str):
                    errs.append(f"classIds.{k} must be a string model id")
    else:
        class_ids = {}

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
            if "apiKeyFile" in prov and not isinstance(prov.get("apiKeyFile"), str):
                errs.append(f"providers.{name}.apiKeyFile must be a string (a path, not the secret)")

    roles = cfg.get("roles")
    if not isinstance(roles, dict):
        errs.append("roles must be an object")
        roles = {}
    for key in ROLE_KEYS:
        role = roles.get(key)
        if not isinstance(role, dict):
            errs.append(f"roles.{key} is required and must be an object")
            continue
        if not isinstance(role.get("purpose"), str) or not role.get("purpose"):
            errs.append(f"roles.{key}.purpose must be a non-empty string")
        access = role.get("access")
        if access is not None and access not in ACCESS_VALUES:
            errs.append(f"roles.{key}.access must be one of harness|api")
        model = role.get("model")
        if not isinstance(model, dict):
            errs.append(f"roles.{key}.model must be an object")
            continue
        cls = model.get("class", "")
        mid = model.get("id", "")
        if not isinstance(cls, str):
            errs.append(f"roles.{key}.model.class must be a string")
            cls = ""
        if not isinstance(mid, str):
            errs.append(f"roles.{key}.model.id must be a string")
            mid = ""
        if not (str(mid).strip() or str(cls).strip()):
            errs.append(f"roles.{key}.model needs a non-empty class or id")
        prov_name = model.get("provider")
        if not isinstance(prov_name, str) or not prov_name:
            errs.append(f"roles.{key}.model.provider must be a string")
        elif prov_name not in providers:
            errs.append(f"roles.{key}.model.provider '{prov_name}' is not defined in providers")
        # Warn if an api-transport role can't resolve to a concrete model id.
        if access == "api" and not str(mid).strip() and str(cls).strip() and str(cls).strip() not in class_ids:
            warns.append(
                f"{key}: access=api but class '{cls}' has no classIds entry and no pinned id; "
                f"the literal class will be passed to --model. "
                f"Pin with: python3 apply.py set {key} --id <exact-model-id>")

    return errs, warns


def resolve_model(role: dict) -> str:
    """Pinned id wins; otherwise the customizable class/alias."""
    model = role.get("model", {})
    mid = str(model.get("id", "")).strip()
    return mid if mid else str(model.get("class", "")).strip()


def resolve_api_model(cfg: dict, role: dict) -> str:
    """Model id for the direct-API transport: pinned model.id, else classIds[class], else the literal class."""
    model = role.get("model", {})
    mid = str(model.get("id", "")).strip()
    if mid:
        return mid
    cls = str(model.get("class", "")).strip()
    class_ids = cfg.get("classIds") or {}
    return class_ids.get(cls, cls)


def apply_set(cfg: dict, args) -> list:
    """Mutate cfg in place for the `set` action; return a list of human-readable changes.
    The caller re-validates and writes. Pinned id wins over class at resolve time, so setting a
    class without --id clears any existing pin to keep behavior intuitive."""
    role = args.role
    if not role:
        fail("`set` needs a role: planner | builder  (e.g. python3 apply.py set builder sonnet)")
    rd = cfg["roles"][role]
    rm = rd["model"]
    changes = []
    new_class = args.cls if args.cls is not None else args.model
    if new_class is not None:
        rm["class"] = new_class
        changes.append(f"class -> '{new_class}'")
        if args.pin_id is None and str(rm.get("id", "")).strip():
            rm["id"] = ""
            changes.append("id -> '' (cleared so the class is active)")
    if args.pin_id is not None:
        rm["id"] = args.pin_id
        changes.append(f"id -> '{args.pin_id}'" if str(args.pin_id).strip() else "id -> '' (pin cleared)")
    if args.provider is not None:
        rm["provider"] = args.provider
        changes.append(f"provider -> '{args.provider}'")
    if args.access is not None:
        rd["access"] = args.access
        changes.append(f"access -> '{args.access}'")
    if not changes:
        fail("nothing to set — pass a model class, or one of --id / --class / --provider / --access")
    return changes


def role_view(cfg: dict, key: str) -> dict:
    role = cfg["roles"][key]
    prov_name = role["model"]["provider"]
    prov = cfg["providers"][prov_name]
    return {
        "role": key,
        "model": resolve_model(role),
        "class": role["model"].get("class", ""),
        "id": role["model"].get("id", ""),
        "provider": prov_name,
        "provider_type": prov.get("type", ""),
        "api_key_env": prov.get("apiKeyEnv", ""),
        "api_key_file": prov.get("apiKeyFile", ""),
        "base_url_env": prov.get("baseUrlEnv", ""),
        "purpose": role.get("purpose", ""),
        "read_only": bool(role.get("readOnly", False)),
        "access": role.get("access", "harness"),
        "api_model": resolve_api_model(cfg, role),
    }


# ---------------------------------------------------------------- rendering
def render(text: str, mapping: dict) -> str:
    for k, v in mapping.items():
        text = text.replace("{{" + k + "}}", v)
    return text


def _ref_phrase(role: str, access: str, dev_dir: str) -> str:
    """Inline mention of a role, matching its transport."""
    if access == "harness":
        return f"the `{role}` subagent"
    return f"the {role} via `{dev_dir}/bin/role-call {role}`"


def template_mapping(cfg: dict) -> dict:
    p = role_view(cfg, "planner")
    b = role_view(cfg, "builder")
    dev_dir = str(SCRIPT_DIR)
    return {
        "PLANNER_MODEL": p["model"],
        "BUILDER_MODEL": b["model"],
        "PLANNER_PURPOSE": p["purpose"],
        "BUILDER_PURPOSE": b["purpose"],
        "PLANNER_PROVIDER": p["provider"],
        "BUILDER_PROVIDER": b["provider"],
        "PLANNER_ACCESS": p["access"],
        "BUILDER_ACCESS": b["access"],
        "PLANNER_API_MODEL": p["api_model"],
        "BUILDER_API_MODEL": b["api_model"],
        "PLANNER_REF": _ref_phrase("planner", p["access"], dev_dir),
        "BUILDER_REF": _ref_phrase("builder", b["access"], dev_dir),
        "DEV_PRIMITIVE_DIR": dev_dir,
    }


# ---------------------------------------------------------------- role charter / facts
def strip_frontmatter(text: str) -> str:
    """Drop a leading YAML frontmatter block (between the first two `---` lines)."""
    lines = text.splitlines(keepends=True)
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                return "".join(lines[i + 1:])
    return text


def render_role_prompt(cfg: dict, role: str) -> str:
    """The role's charter: its .md.tmpl body with frontmatter and the generated-comment
    stripped, rendered with the config. This is the single copy of the role prompt."""
    tmpl = SCRIPT_DIR / "adapters" / "claude-code" / f"{role}.md.tmpl"
    if not tmpl.exists():
        fail(f"missing role template: {tmpl}")
    body = strip_frontmatter(tmpl.read_text(encoding="utf-8"))
    # remove the "<!-- Generated ... -->" provenance comment
    body = re.sub(r"<!--.*?-->\s*", "", body, count=1, flags=re.DOTALL) \
        if GENERATED_MARKER in body else body
    body = render(body, template_mapping(cfg))
    return body.strip() + "\n"


def resolve_facts(cfg: dict, role: str) -> dict:
    """Machine-readable role facts for bin/role-call (order matters for env output)."""
    v = role_view(cfg, role)
    key_file = os.path.expanduser(v["api_key_file"]) if v["api_key_file"] else ""
    return {
        "ROLE": role,
        "ACCESS": v["access"],
        "MODEL": v["api_model"],
        "PROVIDER_TYPE": v["provider_type"],
        "API_KEY_ENV": v["api_key_env"],
        "API_KEY_FILE": key_file,
        "READ_ONLY": "true" if v["read_only"] else "false",
        "PURPOSE": v["purpose"],
    }


def _shquote(val: str) -> str:
    """Single-quote a value so `eval` in bash treats it as one literal."""
    return "'" + str(val).replace("'", "'\\''") + "'"


def write_out(target: Path, content: str, dry: bool) -> None:
    if dry:
        print(f"--- would write {target} ---")
        print(content)
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    print(f"  wrote {target}")


# ---------------------------------------------------------------- adapters
def _remove_stale_agent(target: Path, dry: bool) -> None:
    """A role switched to api-transport has no subagent. Remove a generated one; leave a
    hand-written file (no marker) with a warning. Absence of the file is deliberate — no shim."""
    if not target.exists():
        return
    content = target.read_text(encoding="utf-8", errors="replace")
    if GENERATED_MARKER in content:
        if dry:
            print(f"  would remove {target} (role is api-transport; use bin/role-call)")
        else:
            target.unlink()
            print(f"  removed {target} (role is api-transport; use bin/role-call)")
    else:
        print(f"  WARNING: {target} exists but was not generated by this tool "
              f"(no marker); leaving it in place. Remove it by hand if the role is api-transport.",
              file=sys.stderr)


def install_claude(cfg: dict, home: Path, dry: bool) -> None:
    mapping = template_mapping(cfg)
    tdir = SCRIPT_DIR / "adapters" / "claude-code"
    ddir = tdir / "dispatch"
    print("Claude Code adapter:")

    # Per-role subagent files: render for harness roles, remove/skip for api roles.
    agent_jobs = [
        ("planner", tdir / "planner.md.tmpl", home / ".claude" / "agents" / "planner.md"),
        ("builder", tdir / "builder.md.tmpl", home / ".claude" / "agents" / "builder.md"),
    ]
    for role, tmpl, target in agent_jobs:
        access = role_view(cfg, role)["access"]
        if access == "harness":
            if not tmpl.exists():
                fail(f"missing template: {tmpl}")
            write_out(target, render(tmpl.read_text(encoding="utf-8"), mapping), dry)
        else:
            _remove_stale_agent(target, dry)

    # Command files: two-pass render. Pass 1 renders the per-transport dispatch
    # fragment for each role; pass 2 substitutes those into the command template.
    def dispatch(role: str) -> str:
        access = role_view(cfg, role)["access"]
        frag = ddir / f"{role}-{access}.md"
        if not frag.exists():
            fail(f"missing dispatch fragment: {frag}")
        return render(frag.read_text(encoding="utf-8"), mapping).strip()

    cmd_mapping = dict(mapping)
    cmd_mapping["PLANNER_DISPATCH"] = dispatch("planner")
    cmd_mapping["BUILDER_DISPATCH"] = dispatch("builder")

    cmd_jobs = [
        (tdir / "pb.md.tmpl", home / ".claude" / "commands" / "pb.md"),
        (tdir / "pbg.md.tmpl", home / ".claude" / "commands" / "pbg.md"),
        (tdir / "pbg-builder.md.tmpl", home / ".claude" / "commands" / "pbg-builder.md"),
        (tdir / "pbg-planner.md.tmpl", home / ".claude" / "commands" / "pbg-planner.md"),
    ]
    for tmpl, target in cmd_jobs:
        if not tmpl.exists():
            fail(f"missing template: {tmpl}")
        write_out(target, render(tmpl.read_text(encoding="utf-8"), cmd_mapping), dry)


def generic_block(cfg: dict) -> str:
    p = role_view(cfg, "planner")
    b = role_view(cfg, "builder")

    def prov_line(v):
        bits = [f"provider `{v['provider']}` ({v['provider_type']})",
                f"key env `{v['api_key_env']}`"]
        if v["base_url_env"]:
            bits.append(f"base-url env `{v['base_url_env']}`")
        return ", ".join(bits)

    def reached_via(v):
        if v["access"] == "harness":
            return "  Reached via your harness's native model selection and its own auth."
        keyfile = v["api_key_file"] or "(no keyfile configured)"
        return (
            f"  Reached via a direct provider API using its own credentials — key env "
            f"`{v['api_key_env']}` or keyfile `{keyfile}` (env wins); concrete model id "
            f"`{v['api_model']}`. On this machine `dev-primitive/bin/role-call {v['role']} "
            f"\"<task>\"` is a ready-made wrapper (machine-wide claude CLI, headless); a "
            f"bespoke harness can equally call the provider API/SDK directly with those "
            f"credentials and model id.")

    routing = cfg.get("routing", {})
    note = routing.get("note", "")
    return f"""## Two-Model Development Method (portable primitive)

This project develops with **two roles**, each pinned to a customizable model
class. Map these to your harness's native model selection; do not hardcode any
single model as the only path.

- **planner — model `{p['model']}`** ({prov_line(p)}). Read-only.
  Does: {p['purpose']}.
{reached_via(p)}
- **builder — model `{b['model']}`** ({prov_line(b)}).
  Does: {b['purpose']}.
{reached_via(b)}

**Loop:** reason with the *planner* model → hand the resulting plan to the
*builder* model → build → verify. {note}

The model classes above — and each role's **transport** (`access`: `harness` or
`api`) — are configured per role in `dev-primitive/roles.config.json` (the single
source of truth). Change them there and regenerate rather than editing this block
by hand.
"""


# ---------------------------------------------------------------- reporting
def print_table(cfg: dict) -> None:
    print(f"config version {cfg.get('version')}  —  resolved roles:\n")
    for key in ROLE_KEYS:
        v = role_view(cfg, key)
        pin = "pinned id" if v["id"].strip() else "class (auto-upgrades)"
        print(f"  {key:8} -> model '{v['model']}'  [{pin}]")
        print(f"           provider={v['provider']} ({v['provider_type']}), "
              f"keyEnv={v['api_key_env'] or '-'}, "
              f"baseUrlEnv={v['base_url_env'] or '-'}, readOnly={v['read_only']}")
        if v["access"] == "api":
            key_src = f"${v['api_key_env']}" if v["api_key_env"] else "-"
            if v["api_key_file"]:
                key_src += f" or {v['api_key_file']}"
            print(f"           transport=access=api (direct API; model '{v['api_model']}', key: {key_src})")
        else:
            print("           transport=access=harness (native subagent/auth)")
    print()


def print_warnings(warns: list) -> None:
    for w in warns or []:
        print(f"WARNING: {w}", file=sys.stderr)


def warn_missing_key(cfg: dict, role: str) -> None:
    """After a set, if the role is now api-transport and no key source is available, note it.
    Advisory only (env vars/keyfiles are runtime state) — never fails."""
    if not role:
        return
    v = role_view(cfg, role)
    if v["access"] != "api":
        return
    env_set = bool(v["api_key_env"] and os.environ.get(v["api_key_env"]))
    key_file = os.path.expanduser(v["api_key_file"]) if v["api_key_file"] else ""
    file_ok = bool(key_file and os.path.isfile(key_file))
    if not (env_set or file_ok):
        print(f"WARNING: {role} is now access=api but no API key source is present "
              f"(${v['api_key_env'] or '-'} unset and {key_file or 'no keyfile'} missing). "
              f"Provision it before running: {SCRIPT_DIR}/bin/set-api-key",
              file=sys.stderr)


def fail(msg: str) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------- main
def main() -> None:
    ap = argparse.ArgumentParser(description="Two-role dev primitive generator.")
    ap.add_argument("action",
                    choices=["validate", "show", "claude", "generic", "all", "set", "resolve", "prompt"])
    ap.add_argument("role", nargs="?", choices=["planner", "builder"],
                    help="(set/resolve/prompt) which role to act on")
    ap.add_argument("model", nargs="?",
                    help="(set) new model class for the role; clears any pinned id unless --id is given")
    ap.add_argument("--config", default=str(SCRIPT_DIR / "roles.config.json"))
    ap.add_argument("--home", default=os.environ.get("HOME", str(Path.home())))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--id", dest="pin_id", default=None,
                    help="(set) pin an exact model id; pass an empty string to clear the pin")
    ap.add_argument("--class", dest="cls", default=None,
                    help="(set) set the model class explicitly")
    ap.add_argument("--provider", default=None,
                    help="(set) set the role's provider (must exist in providers)")
    ap.add_argument("--access", choices=list(ACCESS_VALUES), default=None,
                    help="(set) set the role's transport: harness | api")
    ap.add_argument("--no-apply", action="store_true",
                    help="(set) update the config but do not regenerate the Claude Code adapter")
    ap.add_argument("--format", dest="fmt", choices=["env", "json"], default="env",
                    help="(resolve) output format (default env)")
    args = ap.parse_args()

    cfg = load_config(Path(args.config))
    errs, warns = validate(cfg)
    if errs:
        print("Config is INVALID:", file=sys.stderr)
        for e in errs:
            print(f"  - {e}", file=sys.stderr)
        sys.exit(1)

    # resolve/prompt are quiet, machine-facing: no banner, no warnings on stdout.
    if args.action == "resolve":
        if not args.role:
            fail("`resolve` needs a role: planner | builder")
        facts = resolve_facts(cfg, args.role)
        if args.fmt == "json":
            print(json.dumps(facts, ensure_ascii=False))
        else:
            for k, v in facts.items():
                print(f"{k}={_shquote(v)}")
        return
    if args.action == "prompt":
        if not args.role:
            fail("`prompt` needs a role: planner | builder")
        sys.stdout.write(render_role_prompt(cfg, args.role))
        return

    print_warnings(warns)

    if args.action == "set":
        changes = apply_set(cfg, args)          # mutates cfg in place
        errs, warns = validate(cfg)             # re-validate the mutated config
        if errs:
            print("Resulting config would be INVALID (not written):", file=sys.stderr)
            for e in errs:
                print(f"  - {e}", file=sys.stderr)
            sys.exit(1)
        cfg_path = Path(args.config)
        if args.dry_run:
            print(f"[dry-run] {args.role}: " + "; ".join(changes))
            after = "skip regeneration (--no-apply)" if args.no_apply else "regenerate the Claude Code adapter"
            print(f"[dry-run] would write {cfg_path} and {after}\n")
            print_table(cfg)
            print_warnings(warns)
            warn_missing_key(cfg, args.role)
            return
        cfg_path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Updated {args.role}: " + "; ".join(changes))
        print(f"  wrote {cfg_path}\n")
        print_table(cfg)
        print_warnings(warns)
        warn_missing_key(cfg, args.role)
        if args.no_apply:
            print("(--no-apply: config updated but adapters NOT regenerated; "
                  "run `python3 apply.py claude` to apply.)")
        else:
            install_claude(cfg, Path(args.home).expanduser(), dry=False)
        return

    if args.action in ("validate", "show"):
        print("Config is valid.\n")
        print_table(cfg)
        return

    home = Path(args.home).expanduser()
    if args.action in ("claude", "all"):
        install_claude(cfg, home, args.dry_run)
    if args.action in ("generic", "all"):
        print()
        print(generic_block(cfg))


if __name__ == "__main__":
    main()
