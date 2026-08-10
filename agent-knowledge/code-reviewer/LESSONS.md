# code-reviewer lessons

This is durable, harness-neutral working knowledge for the `code-reviewer` profile.
Keep behavioral, reusable lessons here; do **not** store secrets, credentials,
personal data, private task content, or chronological task logs.

**Do not hand-edit this file to record a lesson.** It lives in a branch-mutable
tree, so appending to it is a read-modify-write that a branch switch can silently
undo. Record lessons with:

```bash
python3 lessons.py add --key code-reviewer --task "<task type>" \
  --lesson "<reusable lesson>" --evidence "<path, command, or measurement>"
```

and fold them in later with `python3 lessons.py promote --key code-reviewer --apply`,
which is a deliberate, reviewable act. Hand edits are for consolidation only.

## Durable practices

- Read the profile and applicable project instructions before work.

## Dated lessons

<!-- Entries are written by `lessons.py promote`, in the documented format:
- YYYY-MM-DD | task type | reusable lesson | evidence/path or validation command
When this section reaches 50 entries, fold the oldest reusable items into Durable
practices and remove the consolidated dated entries. -->

- 2026-07-29 | live-infra rename review | Two candidate findings in one review were artifacts of the evidence-gathering step, not the code: grep -o of <link> tags made commented-out stylesheets look active (raw file read showed the <!-- -->), and a probe loop that prepended the host to already-absolute hrefs produced false 404s on pages that were live-200. Before reporting, re-verify any extraction-based evidence (grep -o, generated probe loops) against raw file content and a hand-built request. | verified via sed -n on index.html + direct curl of each URL
- 2026-07-29 | credential/identity toolchain review | When reviewing wrappers that inject a machine-account identity, do not stop at the code paths: verify the STORED identity data against the remote's actual attribution (git log author emails on the branch, then `gh api repos/<owner>/<repo>/commits/<sha> -q .author.login`). A valid token paired with a wrongly-registered author email silently reattributes every commit to the human account while every script "works". Also empirically test fail-open on empty (not just missing) credential files — `gh` treats empty GH_TOKEN as unset and falls back to the ambient login. | validated: git credential fill with/without helper reset + commits API on homelab PR 12
- 2026-07-31 | live bind-mounted config review | For a config file that is single-file bind-mounted into a running container, the vendor's own validator run via `docker run --rm -v <candidate>:<path>:ro <image> ...` is the authoritative check (cloudflared has `tunnel --config ... ingress validate` and `ingress rule <url>` to prove exactly which rule a hostname now matches, with no credentials needed); and a `docker exec ... cat | cmp` probe of the live config can fail with rc=127 because distroless images ship no cat — treat that as exec failure, never as a config mismatch. When the working tree IS the deploy, also flag the pre-merge window: until the branch merges, any `git checkout main` in that repo re-arms the old config on the next container restart. | verified: cloudflared ingress validate OK + "Matched rule #15 http_status:404" on homelab chore/models-site-offline; exec cat rc=127
