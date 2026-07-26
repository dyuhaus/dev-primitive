# builder lessons

This is durable, harness-neutral working knowledge for the `builder` profile.
Keep behavioral, reusable lessons here; do **not** store secrets, credentials,
personal data, private task content, or chronological task logs.

## Durable practices

- Read the profile and applicable project instructions before work.

## Dated lessons

<!-- Append at most one evidence-backed, generalized entry after substantive work:
- YYYY-MM-DD | task type | reusable lesson | evidence/path or validation command
When this section reaches 50 entries, fold the oldest reusable items into Durable
practices and remove the consolidated dated entries. -->
- 2026-07-25 | static-site disclosure changes | Cards moved into collapsed native disclosures should be excluded from scroll-reveal selectors so an observer cannot mark hidden content before it is opened. | Static HTML validation for `three/index.html` confirmed all five hidden cards omit `reveal`.
- 2026-07-26 | static-site publication | When a non-secret browser localStorage key triggers a secret scanner, add a narrowly scoped repository allowlist and rerun the hook rather than bypassing it. | `dyuhaus.com/.gitleaks.toml` permits only `jobs/index.html` and `jobsweep.marks.v1`; staged gitleaks scan and commit passed.
- 2026-07-26 | vault archive creation | A dated note in an otherwise inventoried subtree can still be orphaned; add its explicit hub link and rerun the vault graph validator before reporting success. | `vault-link-check.py` initially reported the new job-sweep archive unreachable, then passed after linking it from `Navigation/Job Search.md`.
- 2026-07-26 | PR artifact validation | Validate the exact remote PR ref rather than a similarly named local worktree; stale worktrees can render an older artifact even when the PR branch is correct. | `git show origin/fix/job-sweep-2026-07-26:jobs/index.html` matched the mirror SHA and passed Playwright desktop/mobile checks, while `.wt-jobs-publish` contained an older page.
