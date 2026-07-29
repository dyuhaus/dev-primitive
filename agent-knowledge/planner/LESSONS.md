# planner lessons

This is durable, harness-neutral working knowledge for the `planner` profile.
Keep behavioral, reusable lessons here; do **not** store secrets, credentials,
personal data, private task content, or chronological task logs.

## Durable practices

- Read the profile and applicable project instructions before work.

## Dated lessons

<!-- Append at most one evidence-backed, generalized entry after substantive work:
- YYYY-MM-DD | task type | reusable lesson | evidence/path or validation command
When this section reaches 50 entries, fold the oldest reusable items into Durable
practices and remove the consolidated dated entries. -->
- 2026-07-27 | headless Unity game design/planning | For GUI-less toolchains, make every visual claim mechanically verifiable from inside the app (e.g. ScreenCapture driven by CLI flags) — window-manager captures of a shared X display pick up other apps' windows and can pass a blank render through colour-count checks | /home/dyadmin/githubStaging/unity-gamedev/bin/unity-verify (root-window fallback) vs in-game harness spec in scratchpad GAME-PLAN.md §10
- 2026-07-28 | game difficulty retuning | When threats can exit the arena harmlessly, scaling their toughness makes the game EASIER (they survive long enough to leave, not to threaten); put scaling only on actors that hold position or shoot, and scale transients via count/speed/cadence/behavior instead | measured: enemy-HP scaling moved level-0 calibration from wave 6 to wave 9 (easier) in Star Salvage; spec scratchpad BALANCE-RETUNE.md §0
- 2026-07-28 | game design revision | When a design law was derived from a measured pathology, record its enabling premise next to the law; a new mechanic that prices the previously-free behavior (e.g. a leak penalty on formerly-harmless despawns) inverts the law, so re-derive it from the new premises instead of re-applying the old rejection — and couple the two in code comments ("if X is removed, Y must be removed with it") | BALANCE-RETUNE.md §0 law vs V2-FLOORS-SPEC.md §0 rewrite (scratchpad); EconomyConfig.cs design-law block
- 2026-07-28 | preference-mining confound design | For small decision ledgers, do not gate signals on a single-axis overlap percentage — a fully-confounded slice can be a mixture whose largest single confounder covers <50% (observed: 45%); instead re-apply the exact existing signal thresholds to the residual after removing records explained by already-emitted higher-priority (decision-axis) signals, so the only "magic numbers" are ones already trusted | verified on a 110-record ledger: mixture slice residual analysis in job-sweep preferences spec
- 2026-07-28 | infinite-scaling game economy design | For "endless" exponential progression, choose the income growth (m/sector) and shop feel (cost ratio c, stat ratio d per level) and DERIVE the enemy growth g = d^(ln m / ln c) as a computed constant — the power-vs-difficulty race then holds as an identity a unit test can assert, instead of a tuning hope; and make unreachable depth testable by defining a closed-form steady-state profile S(f) that debug cheats can install, turning "verify sector 200" into a 3-minute measured run | scratchpad V3-INFINITE-SPEC.md §3/§10 (star-salvage); model check: TTK ratio 10.7/10.8/11.0 at f=10/20/50
- 2026-07-29 | progression-system design on a provable economy | When adding heterogeneous content (skill trees, perks) to a game whose infinite-scaling claim is an identity over uniform growth rates, keep every new effect a bounded f-invariant constant and absorb its total into the already-measured anchor/offset constants — never into the derived rates — and make the spec COMPUTE its declared aggregate from the per-node table instead of hand-totalling it: my first hand-declared branch totals were wrong twice (x1.71 claimed as x1.45; x2.53 vs a [1.95,2.35] band) and the table-product check caught both at spec time | scratchpad V4-WEAPON-TREES-SPEC.md §2/§5 (star-salvage); verified: python product check totals 2.32/2.22/2.25, ratio 1.046
