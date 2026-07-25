# audit lessons

This is durable, harness-neutral working knowledge for the `audit` profile.
Keep behavioral, reusable lessons here; do **not** store secrets, credentials,
personal data, private task content, or chronological task logs.

## Durable practices

- Read the profile and applicable project instructions before work.

## Dated lessons

<!-- Append at most one evidence-backed, generalized entry after substantive work:
- YYYY-MM-DD | task type | reusable lesson | evidence/path or validation command
When this section reaches 50 entries, fold the oldest reusable items into Durable
practices and remove the consolidated dated entries. -->
- 2026-07-25 | agent-routing audit | A plan-before-build config flag must affect the router's selected destination, not merely documentation or tool prompts; otherwise generic implementation can bypass the required planning phase. | `python3 -m unittest discover -s tests -v` and `node adapters/pi/pb-primitive/_selftest.mjs`
