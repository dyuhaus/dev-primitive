# code-reviewer lessons

This is durable, harness-neutral working knowledge for the `code-reviewer` profile.
Keep behavioral, reusable lessons here; do **not** store secrets, credentials,
personal data, private task content, or chronological task logs.

## Durable practices

- Read the profile and applicable project instructions before work.

## Dated lessons

<!-- Append at most one evidence-backed, generalized entry after substantive work:
- YYYY-MM-DD | task type | reusable lesson | evidence/path or validation command
When this section reaches 50 entries, fold the oldest reusable items into Durable
practices and remove the consolidated dated entries. -->

- 2026-07-29 | live-infra rename review | Two candidate findings in one review were artifacts of the evidence-gathering step, not the code: grep -o of <link> tags made commented-out stylesheets look active (raw file read showed the <!-- -->), and a probe loop that prepended the host to already-absolute hrefs produced false 404s on pages that were live-200. Before reporting, re-verify any extraction-based evidence (grep -o, generated probe loops) against raw file content and a hand-built request. | verified via sed -n on index.html + direct curl of each URL
