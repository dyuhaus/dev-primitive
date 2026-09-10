#!/usr/bin/env python3
"""Install the supported Codex surface and shared skills; retire other targets."""
import argparse
import os
from pathlib import Path
import apply as primitive

ROOT = Path(__file__).resolve().parent
TARGETS = ("codex", "skills", "all", "claude", "dsh", "pi", "hermes", "gemini")


def main():
    parser = argparse.ArgumentParser(description="Install Codex profiles and shared skills")
    parser.add_argument("target", choices=TARGETS)
    parser.add_argument("--home", default=os.environ.get("HOME", str(Path.home())))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.target not in ("codex", "skills", "all"):
        parser.error("Only Codex is supported; other harnesses are decommissioned")
    cfg = primitive.load_config(ROOT / "roles.config.json")
    errors = primitive.validate(cfg)
    if errors:
        parser.error("Invalid source config: " + "; ".join(errors))
    home = Path(args.home).expanduser()
    primitive.install_knowledge(cfg, args.dry_run)
    if args.target in ("skills", "all"):
        primitive.link_shared_skills(home, args.dry_run)
    if args.target in ("codex", "all"):
        primitive.install_harness_skills(cfg, home, "codex", args.dry_run)


if __name__ == "__main__":
    main()
