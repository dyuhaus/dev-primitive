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
- 2026-07-29 | credential/identity toolchain review | When reviewing wrappers that inject a machine-account identity, do not stop at the code paths: verify the STORED identity data against the remote's actual attribution (git log author emails on the branch, then `gh api repos/<owner>/<repo>/commits/<sha> -q .author.login`). A valid token paired with a wrongly-registered author email silently reattributes every commit to the human account while every script "works". Also empirically test fail-open on empty (not just missing) credential files — `gh` treats empty GH_TOKEN as unset and falls back to the ambient login. | validated: git credential fill with/without helper reset + commits API on homelab PR 12
- 2026-08-11 | filesystem-write containment review | A note-drop that does `fs.access(candidate)` then `fs.writeFile(candidate, ...)` with the DEFAULT flag has two confirmed defects the containment/realpath check does not cover: (a) two concurrent same-title calls both pass access() then both write the same path, silently overwriting one note (verified with Promise.allSettled → only the second body survived); (b) if `candidate` is a DANGLING symlink pointing outside the root (target missing), realpath() throws so the resolver falls to its "not-yet-existing file" parent branch and blesses it, access() sees the broken link as absent, and writeFile FOLLOWS the symlink and writes outside the root entirely. A leaf symlink defeats a resolver that only realpaths the parent. Both are closed by a single atomic exclusive create (`{flag:"wx"}`), which O_EXCL-rejects a dangling symlink with EEXIST — verified directly. Always attack check-then-write with (1) concurrency and (2) a pre-planted dangling symlink at the target name, not just `..`/absolute paths. | validated in dy-mcp feat/vault-local-mount via a temp-vault tsx harness
