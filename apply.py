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

Options:
    --config PATH   config file (default: roles.config.json next to this script)
    --home PATH     home dir for the Claude Code adapter (default: $HOME)
    --dry-run       print what would be written instead of writing
    --id ID         (set) pin an exact model id; empty string clears the pin
    --class CLASS   (set) set the model class explicitly
    --provider P    (set) set the role's provider
    --no-apply      (set) update the config but do not regenerate the adapter

No third-party dependencies. Python 3.8+.
"""
import argparse
import json
import os
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
ROLE_KEYS = ("planner", "builder")


# ---------------------------------------------------------------- load + validate
def load_config(path: Path) -> dict:
    try:
        with path.open(encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        fail(f"config not found: {path}")
    except json.JSONDecodeError as exc:
        fail(f"config is not valid JSON: {exc}")


def validate(cfg: dict) -> list:
    """Return a list of human-readable errors ([] means valid)."""
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
    for key in ROLE_KEYS:
        role = roles.get(key)
        if not isinstance(role, dict):
            errs.append(f"roles.{key} is required and must be an object")
            continue
        if not isinstance(role.get("purpose"), str) or not role.get("purpose"):
            errs.append(f"roles.{key}.purpose must be a non-empty string")
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

    return errs


def resolve_model(role: dict) -> str:
    """Pinned id wins; otherwise the customizable class/alias."""
    model = role.get("model", {})
    mid = str(model.get("id", "")).strip()
    return mid if mid else str(model.get("class", "")).strip()


def apply_set(cfg: dict, args) -> list:
    """Mutate cfg in place for the `set` action; return a list of human-readable changes.
    The caller re-validates and writes. Pinned id wins over class at resolve time, so setting a
    class without --id clears any existing pin to keep behavior intuitive."""
    role = args.role
    if not role:
        fail("`set` needs a role: planner | builder  (e.g. python3 apply.py set builder sonnet)")
    rm = cfg["roles"][role]["model"]
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
    if not changes:
        fail("nothing to set — pass a model class, or one of --id / --class / --provider")
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
        "base_url_env": prov.get("baseUrlEnv", ""),
        "purpose": role.get("purpose", ""),
        "read_only": bool(role.get("readOnly", False)),
    }


# ---------------------------------------------------------------- rendering
def render(text: str, mapping: dict) -> str:
    for k, v in mapping.items():
        text = text.replace("{{" + k + "}}", v)
    return text


def template_mapping(cfg: dict) -> dict:
    p = role_view(cfg, "planner")
    b = role_view(cfg, "builder")
    return {
        "PLANNER_MODEL": p["model"],
        "BUILDER_MODEL": b["model"],
        "PLANNER_PURPOSE": p["purpose"],
        "BUILDER_PURPOSE": b["purpose"],
        "PLANNER_PROVIDER": p["provider"],
        "BUILDER_PROVIDER": b["provider"],
    }


def write_out(target: Path, content: str, dry: bool) -> None:
    if dry:
        print(f"--- would write {target} ---")
        print(content)
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    print(f"  wrote {target}")


# ---------------------------------------------------------------- adapters
def install_claude(cfg: dict, home: Path, dry: bool) -> None:
    mapping = template_mapping(cfg)
    tdir = SCRIPT_DIR / "adapters" / "claude-code"
    jobs = [
        (tdir / "planner.md.tmpl", home / ".claude" / "agents" / "planner.md"),
        (tdir / "builder.md.tmpl", home / ".claude" / "agents" / "builder.md"),
        (tdir / "pb.md.tmpl", home / ".claude" / "commands" / "pb.md"),
        (tdir / "pbg.md.tmpl", home / ".claude" / "commands" / "pbg.md"),
        (tdir / "pbg-builder.md.tmpl", home / ".claude" / "commands" / "pbg-builder.md"),
        (tdir / "pbg-planner.md.tmpl", home / ".claude" / "commands" / "pbg-planner.md"),
    ]
    print("Claude Code adapter:")
    for tmpl, target in jobs:
        if not tmpl.exists():
            fail(f"missing template: {tmpl}")
        write_out(target, render(tmpl.read_text(encoding="utf-8"), mapping), dry)


def generic_block(cfg: dict) -> str:
    p = role_view(cfg, "planner")
    b = role_view(cfg, "builder")

    def prov_line(v):
        bits = [f"provider `{v['provider']}` ({v['provider_type']})",
                f"key env `{v['api_key_env']}`"]
        if v["base_url_env"]:
            bits.append(f"base-url env `{v['base_url_env']}`")
        return ", ".join(bits)

    routing = cfg.get("routing", {})
    note = routing.get("note", "")
    return f"""## Two-Model Development Method (portable primitive)

This project develops with **two roles**, each pinned to a customizable model
class. Map these to your harness's native model selection; do not hardcode any
single model as the only path.

- **planner — model `{p['model']}`** ({prov_line(p)}). Read-only.
  Does: {p['purpose']}.
- **builder — model `{b['model']}`** ({prov_line(b)}).
  Does: {b['purpose']}.

**Loop:** reason with the *planner* model → hand the resulting plan to the
*builder* model → build → verify. {note}

The model classes above are configured in `dev-primitive/roles.config.json`
(the single source of truth). Change them there and regenerate rather than
editing this block by hand.
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
    print()


def fail(msg: str) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------- main
def main() -> None:
    ap = argparse.ArgumentParser(description="Two-role dev primitive generator.")
    ap.add_argument("action", choices=["validate", "show", "claude", "generic", "all", "set"])
    ap.add_argument("role", nargs="?", choices=["planner", "builder"],
                    help="(set) which role to modify")
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
    ap.add_argument("--no-apply", action="store_true",
                    help="(set) update the config but do not regenerate the Claude Code adapter")
    args = ap.parse_args()

    cfg = load_config(Path(args.config))
    errs = validate(cfg)
    if errs:
        print("Config is INVALID:", file=sys.stderr)
        for e in errs:
            print(f"  - {e}", file=sys.stderr)
        sys.exit(1)

    if args.action == "set":
        changes = apply_set(cfg, args)          # mutates cfg in place
        errs = validate(cfg)                    # re-validate the mutated config
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
            return
        cfg_path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Updated {args.role}: " + "; ".join(changes))
        print(f"  wrote {cfg_path}\n")
        print_table(cfg)
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
