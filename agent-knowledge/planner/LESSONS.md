# planner lessons

This is durable, harness-neutral working knowledge for the `planner` profile.
Keep behavioral, reusable lessons here; do **not** store secrets, credentials,
personal data, private task content, or chronological task logs.

**Do not hand-edit this file to record a lesson.** It lives in a branch-mutable
tree, so appending to it is a read-modify-write that a branch switch can silently
undo. Record lessons with:

```bash
python3 "$DEV_PRIMITIVE/lessons.py" add --key planner --task "<task type>" \
  --lesson "<reusable lesson>" --evidence "<path, command, or measurement>"
```

See [PROFILE.md](./PROFILE.md) for the same command in context. A bare
`python3 lessons.py` only works from the checkout that holds the script.

`lessons.py promote` is the only route from the inbox into this repository, and
it is **run by a person** who reviews the diff and commits it — not by an agent
mid-task, and not from a background job. Hand edits to this file are for one
thing: consolidating dated entries into `## Durable practices`.

## Durable practices

- Read the profile and applicable project instructions before work.

## Dated lessons

<!-- Entries are written by `lessons.py promote`, in the documented format:
- YYYY-MM-DD | task type | reusable lesson | evidence/path or validation command
When this section reaches 50 entries, fold the oldest reusable items into Durable
practices and remove the consolidated dated entries. -->
- 2026-07-27 | headless Unity game design/planning | For GUI-less toolchains, make every visual claim mechanically verifiable from inside the app (e.g. ScreenCapture driven by CLI flags) — window-manager captures of a shared X display pick up other apps' windows and can pass a blank render through colour-count checks | /home/dyadmin/githubStaging/unity-gamedev/bin/unity-verify (root-window fallback) vs in-game harness spec in scratchpad GAME-PLAN.md §10
- 2026-07-28 | game difficulty retuning | When threats can exit the arena harmlessly, scaling their toughness makes the game EASIER (they survive long enough to leave, not to threaten); put scaling only on actors that hold position or shoot, and scale transients via count/speed/cadence/behavior instead | measured: enemy-HP scaling moved level-0 calibration from wave 6 to wave 9 (easier) in Star Salvage; spec scratchpad BALANCE-RETUNE.md §0
- 2026-07-28 | game design revision | When a design law was derived from a measured pathology, record its enabling premise next to the law; a new mechanic that prices the previously-free behavior (e.g. a leak penalty on formerly-harmless despawns) inverts the law, so re-derive it from the new premises instead of re-applying the old rejection — and couple the two in code comments ("if X is removed, Y must be removed with it") | BALANCE-RETUNE.md §0 law vs V2-FLOORS-SPEC.md §0 rewrite (scratchpad); EconomyConfig.cs design-law block
- 2026-07-28 | preference-mining confound design | For small decision ledgers, do not gate signals on a single-axis overlap percentage — a fully-confounded slice can be a mixture whose largest single confounder covers <50% (observed: 45%); instead re-apply the exact existing signal thresholds to the residual after removing records explained by already-emitted higher-priority (decision-axis) signals, so the only "magic numbers" are ones already trusted | verified on a 110-record ledger: mixture slice residual analysis in job-sweep preferences spec
- 2026-07-28 | infinite-scaling game economy design | For "endless" exponential progression, choose the income growth (m/sector) and shop feel (cost ratio c, stat ratio d per level) and DERIVE the enemy growth g = d^(ln m / ln c) as a computed constant — the power-vs-difficulty race then holds as an identity a unit test can assert, instead of a tuning hope; and make unreachable depth testable by defining a closed-form steady-state profile S(f) that debug cheats can install, turning "verify sector 200" into a 3-minute measured run | scratchpad V3-INFINITE-SPEC.md §3/§10 (star-salvage); model check: TTK ratio 10.7/10.8/11.0 at f=10/20/50
- 2026-07-29 | progression-system design on a provable economy | When adding heterogeneous content (skill trees, perks) to a game whose infinite-scaling claim is an identity over uniform growth rates, keep every new effect a bounded f-invariant constant and absorb its total into the already-measured anchor/offset constants — never into the derived rates — and make the spec COMPUTE its declared aggregate from the per-node table instead of hand-totalling it: my first hand-declared branch totals were wrong twice (x1.71 claimed as x1.45; x2.53 vs a [1.95,2.35] band) and the table-product check caught both at spec time | scratchpad V4-WEAPON-TREES-SPEC.md §2/§5 (star-salvage); verified: python product check totals 2.32/2.22/2.25, ratio 1.046
- 2026-07-29 | balance calibration across asymmetric player configurations | When a balance instrument's calibration knob is SHARED across asymmetric player configurations (ship classes, loadouts, archetypes), the calibration target must name the baseline configuration explicitly — calibrating on a specialist silently redefines the baseline as below-spec, and the miss surfaces only at the cell that was never flown before. Corollary: a declared-parity bound between content branches does not produce REALIZED parity when branches differ in how much of their value is geometry (splash/pierce/bounce), because geometry value scales with target density while a declared DPS multiplier does not — so bound realized divergence directly rather than inferring it from declared parity | star-salvage v4: offsets were calibrated per spec §11.3 on the Interceptor (base FireRateMultiplier 1.20), leaving the default Vanguard hull pinned at the band floor in BOTH its modes while the geometry-heavy Fortress cleared 5 vs band high 3 at 9.0 s/wave; leak counts 47/9/1 show the same asymmetry from the coverage side
- 2026-07-30 | game balance instrumentation | A mechanic whose value scales with target density cannot be priced by any declared constant — bound it per-event inside the mechanism (per-shell damage budget, target cap) so the bound is density-invariant by construction; and attribute/size excesses by REMOVING a component from the complete configuration, never by flying it alone, because an isolated contribution is scored against a pathology the complete configuration does not have | star-salvage HANDOFF-v4 §8.2 (isolated x1.55 trim moved the complete cell by zero; removal named MORTAR at +4.2 sectors vs 1.70 declared)
- 2026-07-30 | autonomous-gate evidence design | When a gate consumes a human out-of-band verdict (platform review/approval fields), bind the verdict to the exact artifact version: GitHub keeps reviewDecision=APPROVED across later pushes on unprotected repos, so an unpinned approved-fast-path merges code the human never saw — pin via the review object's commit_id (REST), not the computed decision field; and re-read a shared worktree's HEAD before finalizing analysis, since a builder can land commits mid-review | live probe: dyuhaus/autopilot#4 approval commit_id 2706e69c vs headRefOid 8dc73a8f while reviewDecision=APPROVED; wt-policy tip moved 638f9a1->2778f39 mid-session
