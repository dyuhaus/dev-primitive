# dev-primitive

Codex-only agent registry and explicit Planner -> Builder workflow.
`roles.config.json` owns model routing, profile contracts, and workflow settings.
Ordinary work stays in the current Codex session. PB never starts automatically.

<!-- BEGIN GENERATED: roster (apply.py docs) -->
Beyond the `planner`/`builder` core there are 9 specialists: `runner`, `tech-writer`, `prose-writer`, `l1-programmer`, `librarian`, `fe-designer`, `code-reviewer`, plus 2 direct-call-only profiles that must never be auto-selected — `team-leader`, `audit`.
<!-- END GENERATED: roster -->

## Explicit workflow

Invoke `$agent-pb`, `/pb`, or explicitly ask for Planner -> Builder. Both roles
currently use `gpt-6-astra` at `xhigh`: one read-only planning pass, review of its
terminal plan, one implementation pass, then concrete verification. Invoking a
role alone does not automatically start the other role. Task classification,
a router recommendation, and task size never start PB. Automatic post-workflow
audit is disabled. Requested Code Review and Audit remain available.

Codex metadata sets `allow_implicit_invocation: false` for PB, Planner, Builder,
and the optional router skill. This complements the instruction boundary.

## Commands

```bash
python3 apply.py validate
python3 apply.py show
python3 apply.py roster
python3 install_harness.py codex --dry-run
python3 router.py --explain "a task"  # explicit recommendation only; no dispatch
```

Install only reviewed, human-merged source with `install_harness.py codex`;
`all` means Codex plus shared skill links and generated knowledge. Legacy
`claude`, `dsh`, `pi`, `hermes`, and `gemini` installation targets refuse before
writes. Historical adapter source is retained for reference, without an active
installation or refresh path. No model/provider/harness fallback is allowed.

## Registry and validation

Planner and Builder are the `roles` entries; specialist models remain their
configured Codex/OpenAI models. A nonempty exact model `id` overrides `class`.
Change the registry and regenerate; never hand-edit installed skills or profiles.
`apply.py set` updates existing Codex files only, preserves lessons, and does not
install missing surfaces. `install_harness.py` is the deliberate install command.

<!-- BEGIN GENERATED: auditor-models (apply.py docs) -->
Review policy: automatic workflow audit disabled; requested Audit uses `gpt-5.6-sol` on `openai` at `xhigh`. Requested code review uses the registry-configured Code Reviewer; neither review nor Audit is an automatic workflow gate.
<!-- END GENERATED: auditor-models -->

```bash
python3 apply.py validate
python3 -m unittest discover -s tests
python3 apply.py docs
python3 install_harness.py all --dry-run
```

Tests cover Codex behavior and rejection of retired entrypoints. A static pass
is not a claim of provider-backed behavioral acceptance or installed parity.

## Source layout

- `apply.py`, `install_harness.py`: validation, generation and installation.
- `router.py`: optional explainable recommendations; no execution.
- `adapters/codex`: supported templates.
- `agent-knowledge`: generated profiles and preserved lessons.
- `tests`: focused native checks.

See [framework](AGENT-FRAMEWORK.md), [PB contract](PRIMITIVE.md), and
[installation](HARNESS-INSTALLATION.md).

<!-- BEGIN GENERATED: harness-surfaces (apply.py docs) -->
| Harness | Surface | Result |
|---|---|---|
| Codex | `~/.codex/skills/agent-*/SKILL.md` | Supported. PB and its roles require explicit invocation; both use the configured Astra model. Automatic workflow audit is disabled. |
| Other harnesses | None installed or refreshed | Decommissioned. Their installers and dispatch entrypoints refuse before launch or writes. Historical source is not activation authority. |
<!-- END GENERATED: harness-surfaces -->
