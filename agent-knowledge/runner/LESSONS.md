# runner lessons

This is durable, harness-neutral working knowledge for the `runner` profile.
Keep behavioral, reusable lessons here; do **not** store secrets, credentials,
personal data, private task content, or chronological task logs.

**Do not hand-edit this file to record a lesson.** It lives in a branch-mutable
tree, so appending to it is a read-modify-write that a branch switch can silently
undo. Record lessons with:

```bash
python3 "$DEV_PRIMITIVE/lessons.py" add --key runner --task "<task type>" \
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
