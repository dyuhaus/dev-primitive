#!/usr/bin/env python3
"""Install the supported Claude Code surface and shared skills; retire other targets."""
import argparse
import os
from pathlib import Path
import apply as primitive

ROOT = Path(__file__).resolve().parent
TARGETS = ("claude", "skills", "all", "codex", "dsh", "pi", "hermes", "gemini")


def main():
    parser = argparse.ArgumentParser(description="Install Claude Code profiles and shared skills")
    parser.add_argument("target", choices=TARGETS)
    parser.add_argument("--home", default=os.environ.get("HOME", str(Path.home())))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.target not in ("claude", "skills", "all"):
        parser.error("Only Claude Code is supported; other harnesses (including Codex, retired 2026-11-17) are decommissioned")
    cfg = primitive.load_config(ROOT / "roles.config.json")
    errors = primitive.validate(cfg)
    if errors:
        parser.error("Invalid source config: " + "; ".join(errors))
    home = Path(args.home).expanduser()
    if args.target in ("claude", "all"):
        primitive.assert_generated_paths_are_installable(args.dry_run)
    primitive.install_knowledge(cfg, args.dry_run)
    if args.target in ("skills", "all"):
        primitive.link_shared_skills(home, args.dry_run)
    if args.target in ("claude", "all"):
        try:
            primitive.install_claude(cfg, home, args.dry_run)
        except primitive.AdapterUnsupported as exc:
            parser.error(str(exc))


if __name__ == "__main__":
    main()
