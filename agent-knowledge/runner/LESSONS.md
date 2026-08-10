# runner lessons

This is durable, harness-neutral working knowledge for the `runner` profile.
Keep behavioral, reusable lessons here; do **not** store secrets, credentials,
personal data, private task content, or chronological task logs.

**Do not hand-edit this file to record a lesson.** It lives in a branch-mutable
tree, so appending to it is a read-modify-write that a branch switch can silently
undo. Record lessons with:

```bash
python3 lessons.py add --key runner --task "<task type>" \
  --lesson "<reusable lesson>" --evidence "<path, command, or measurement>"
```

and fold them in later with `python3 lessons.py promote --key runner --apply`,
which is a deliberate, reviewable act. Hand edits are for consolidation only.

## Durable practices

- Read the profile and applicable project instructions before work.

## Dated lessons

<!-- Entries are written by `lessons.py promote`, in the documented format:
- YYYY-MM-DD | task type | reusable lesson | evidence/path or validation command
When this section reaches 50 entries, fold the oldest reusable items into Durable
practices and remove the consolidated dated entries. -->
