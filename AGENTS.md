# dev-primitive — Agent Guide

This repository is model- and harness-agnostic. `AGENTS.md` is the portable
entrypoint for Codex, Hermes, Claude Code, and any future assistant harness.

## Project

TODO: one-line purpose.

<!-- Expand: architecture, key directories, native build/test commands, and any
     project-specific conventions an agent must respect before changing code. -->

## Rules

- Read `/home/dyadmin/AGENTS.md` first for the machine-level contract.
- Read this repo's `README.md`, manifests, scripts, and tests before changing
  behavior.
- Never read, print, commit, or publish secrets, local `.env` values,
  credentials, or private user data.
- Keep durable state in repo files and deterministic scripts, not in one
  harness's memory or chat history.
- Use the project's native test/build commands for validation; document any
  missing or unavailable checks.

## Git Workflow (machine standard)
This repo follows /home/dyadmin/AGENTS.md "Git Workflow Standard".
- Default branch: main (protected, PR-only, squash merge)
- Branches: feat/ fix/ chore/ docs/ exp/ (+ agent/<harness>/ optional)
- Commits: Conventional Commits; hooks must pass; never --no-verify
- Review: CodeRabbit auto-reviews PRs (config: .coderabbit.yaml); address all
  findings, then request David's approval (agent PRs require it)
- Deploy coupling: <none | "merging main deploys to X — humans merge">
- Long-lived branch exceptions: <none | list + purpose>
