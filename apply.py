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

Options:
    --config PATH   config file (default: roles.config.json next to this script)
    --home PATH     home dir for the Claude Code adapter (default: $HOME)
    --dry-run       print what would be written instead of writing

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
    ap.add_argument("action", choices=["validate", "show", "claude", "generic", "all"])
    ap.add_argument("--config", default=str(SCRIPT_DIR / "roles.config.json"))
    ap.add_argument("--home", default=os.environ.get("HOME", str(Path.home())))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    cfg = load_config(Path(args.config))
    errs = validate(cfg)
    if errs:
        print("Config is INVALID:", file=sys.stderr)
        for e in errs:
            print(f"  - {e}", file=sys.stderr)
        sys.exit(1)

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
