#!/usr/bin/env python3
"""Install the configured agent registry into user-level harness surfaces.

The repository remains the portable source of truth. This installer materializes
native adapters into Claude Code, Codex, dsh, Pi and Hermes, and mirrors the
shared skill roots into each harness's skill directory. It never copies secrets.

Two things are deliberate here:

* **Neutral surfaces generate first.** The agent-knowledge profiles and the
  shared-skill links have nothing to do with any one harness's model-dispatch
  limits, so one undispatchable profile must not stop them regenerating.
* **A refusal is per-adapter.** `install_harness.py claude` fails hard when the
  Claude adapter cannot render; `install_harness.py all` warns, skips that one
  adapter, and still installs everything else.
"""
import argparse
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import apply as primitive  # noqa: E402

SKILL_ADAPTERS = ("codex", "dsh", "hermes")
TARGETS = ("pi", "claude", "codex", "dsh", "hermes", "skills", "all")


def load():
    cfg = primitive.load_config(ROOT / "roles.config.json")
    errors = primitive.validate(cfg)
    if errors:
        raise SystemExit("Invalid source config:\n" + "\n".join(f"- {e}" for e in errors))
    return cfg


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
    # The Pi-only OpenRouter overlay was removed on 2026-07-26. Pi's config.ts
    # already falls back to the shared harness-neutral registry when the overlay
    # file is absent, so its absence is the normal case. An overlay is still
    # honored if one is reintroduced, and is validated before use.
    overlay = ROOT / "adapters" / "pi" / "roles.config.pi.json"
    if overlay.is_file():
        overlay_errors = primitive.validate(primitive.load_config(overlay))
        if overlay_errors:
            raise SystemExit(
                "Invalid Pi-only overlay:\n" + "\n".join(f"- {error}" for error in overlay_errors)
            )
    for name in PI_EXTENSIONS:
        sync_pi_extension(name, home, dry_run)
    if dry_run:
        if overlay.is_file():
            print(f"Pi will read the live overlay at {overlay}; it is not copied into ~/.pi.")
        else:
            print("No Pi overlay present; Pi resolves the shared roles.config.json.")


def install_skill_adapter(cfg, home, adapter, dry_run):
    """Render one skill-based harness surface (Codex, dsh, Hermes)."""
    print(f"[{adapter}] rendering agent profiles into {home / primitive.HARNESS_SKILL_ROOTS[adapter]}")
    primitive.install_harness_skills(cfg, home, adapter, dry_run)


def main():
    parser = argparse.ArgumentParser(description="Install agent profiles into harness-level adapters")
    parser.add_argument("target", choices=TARGETS)
    parser.add_argument("--home", default=os.environ.get("HOME", str(Path.home())))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    cfg = load()
    home = Path(args.home).expanduser()
    everything = args.target == "all"
    skipped = []

    # Neutral surfaces first. Profiles are generated source documentation;
    # LESSONS.md files are only initialized when absent, so refreshing harness
    # adapters never erases them.
    primitive.install_knowledge(cfg, args.dry_run)
    if args.target in ("skills", "all"):
        print("[skills] mirroring the shared skill roots into every harness")
        primitive.link_shared_skills(home, args.dry_run)

    if args.target in ("pi", "all"):
        install_pi(home, args.dry_run)

    for adapter in SKILL_ADAPTERS:
        if args.target in (adapter, "all"):
            install_skill_adapter(cfg, home, adapter, args.dry_run)

    if args.target in ("claude", "all"):
        try:
            primitive.install_claude(cfg, home, args.dry_run)
        except primitive.AdapterUnsupported as exc:
            if not everything:
                raise SystemExit(f"ERROR: {exc}")
            skipped.append("claude")
            print(f"WARNING: skipping the Claude Code adapter — {exc}", file=sys.stderr)
            # The all-installer has the same intentional retirement obligation
            # as apply.py all: obsolete, manifest-owned PB/profile files must
            # not remain as a silent Anthropic automation fallback.
            primitive.retire_stale_claude_surface(cfg, home, args.dry_run)

    if skipped:
        print(
            f"\nInstalled everything except: {', '.join(skipped)}. "
            "The registry and the other surfaces are current.",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
