# Agent knowledge and lessons

This directory is the portable, source-controlled knowledge location for every
registered profile. `PROFILE.md` files are generated from `roles.config.json`
(and the PB defaults in `apply.py`) by `python3 apply.py knowledge`. Change the
source configuration, not generated profiles. `LESSONS.md` is intentionally
created once and then preserved across regenerations.

Before substantive work, an agent reads its profile, lessons, project
instructions, and the profile's information sources. After work it may append
**at most one** reusable, evidence-backed lesson in the documented dated format.
Lessons are not task logs and must never contain secrets, credentials, personal
data, raw private content, or unverified claims. At 50 dated entries, consolidate
the oldest reusable entries into `## Durable practices`.
