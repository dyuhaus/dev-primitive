# Explicit Planner -> Builder

PB is an invoked Codex workflow. Ordinary work stays in the current session;
there is no automatic planner, builder, role recommendation, or workflow audit.

## Execution contract

Both roles currently use `gpt-6-astra` at `xhigh`, resolved from
`roles.config.json`. One model can perform two separate roles; this is not a
claim of independent-model review. The Planner returns a read-only terminal
plan before Builder starts. The Builder receives that reviewed plan and its
profile boundaries. Verification checks the resulting artifact.

`/pb is exactly one pass`. Only explicit `/pbg` permits repetition;
`/pbg is capped at exactly three rounds`. A second inconclusive proof or two
rounds without measurable progress is BLOCKED. Do not expand scope after the
first failed real proof. No background loop is implied by task persistence.

An explicit PB invocation covers its two ordered parent dispatches without a
repeated confirmation. A worker's `canDelegate`, `delegateTo`, and current task
authority still govern nested handoffs. Team Leader requires its own explicit
request. No automatic post-workflow audit or audit verdict is required.

## Source and permissions

`roles.config.json` owns the roles and models. Generated Codex skills and
`agent-knowledge/*/PROFILE.md` must be regenerated from it; `LESSONS.md` is
preserved and requires specific write authorization. A read-only task never
writes lessons. Plans and skills do not authorize deployment, provider access,
service changes, or publication. David reviews and merges source PRs in GitHub.

<!-- BEGIN GENERATED: roster (apply.py docs) -->
Beyond the `planner`/`builder` core there are 9 specialists: `runner`, `tech-writer`, `prose-writer`, `l1-programmer`, `librarian`, `fe-designer`, `code-reviewer`, plus 2 direct-call-only profiles that must never be auto-selected — `team-leader`, `audit`.
<!-- END GENERATED: roster -->

<!-- BEGIN GENERATED: auditor-models (apply.py docs) -->
Review policy: automatic workflow audit disabled; requested Audit uses `gpt-5.6-sol` on `openai` at `xhigh`. Requested code review uses the registry-configured Code Reviewer; neither review nor Audit is an automatic workflow gate.
<!-- END GENERATED: auditor-models -->

## Supported surface

Use [the Codex installer](HARNESS-INSTALLATION.md). Other harnesses are
retired and are neither installed nor behaviorally evaluated. Report an
unavailable Codex model or capability; do not substitute another harness.

## Authorized lesson recording

A useful lesson remains report-only until the task specifically authorizes the
inbox write. Read-only work never records or promotes a lesson. `$DEV_PRIMITIVE`
is the primary checkout containing `lessons.py`:

```bash
python3 "$DEV_PRIMITIVE/lessons.py" add --key builder --task "<task type>" \
  --lesson "<reusable lesson>" --evidence "<path or command>"
python3 "$DEV_PRIMITIVE/lessons.py" show
```

Each authorized `add` writes one new file outside Git; it does not append to
`LESSONS.md`. Human-run `promote` previews the proposed repository change and
requires `--apply` to write; it never commits. Recording, promotion, and GitHub
merge retain their separate authority boundaries. The inbox is a temporary queue,
not a durable archive. See [the knowledge guide](agent-knowledge/README.md).
