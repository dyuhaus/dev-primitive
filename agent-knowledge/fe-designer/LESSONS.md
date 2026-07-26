# fe-designer lessons

This is durable, harness-neutral working knowledge for the `fe-designer` profile.
Keep behavioral, reusable lessons here; do **not** store secrets, credentials,
personal data, private task content, or chronological task logs.

## Durable practices

- Read the profile and applicable project instructions before work.

## Dated lessons

<!-- Append at most one evidence-backed, generalized entry after substantive work:
- YYYY-MM-DD | task type | reusable lesson | evidence/path or validation command
When this section reaches 50 entries, fold the oldest reusable items into Durable
practices and remove the consolidated dated entries. -->

- 2026-07-25 | multi-variant site prototyping | Before starting greenfield UI work, run `git status` on the target repo first — prior sessions may have left substantial uncommitted scaffolding to finish and route rather than rebuild from scratch. Also verify robots.txt promises (sitemap.xml) and README domain tables when adding sub-sites. | evidence: /home/dyadmin/githubStaging/dyuhaus.com PR #7 (one/two/three prototype dirs existed untracked; gaps were README rows, missing sitemaps)
- 2026-07-25 | interaction variant prototyping | For A/B/C comparison of one component in-place, keep a shared base class (markup + JS untouched) and add modifier classes per instance in CSS; clip-path inset() transitions on a grid-rows disclosure give convincing "unroll" effects and degrade cleanly in reduced-motion/no-JS blocks. | evidence: /home/dyadmin/githubStaging/dyuhaus.com three/styles.css `.fantasy__record--unfurl/--sideways/--double`
- 2026-07-25 | animated <details> disclosures | Animated close (preventDefault + .is-closing + transitionend) swallows rapid re-clicks because `open` stays true mid-close; handle "click while closing = cancel close", add a setTimeout fallback for missing transitionend, and check `event.target === body` in the transitionend handler so bubbled child transitions don't finish the close early. | evidence: /home/dyadmin/githubStaging/dyuhaus.com three/script.js `closeRecord/finishClose`; validated with `node --check`
- 2026-07-25 | disclosure width-jitter fix | "Section gets wider when opened" jitter usually has two compounding causes: (1) page-level horizontal shift from the vertical scrollbar appearing/disappearing — fix with `scrollbar-gutter: stable` on `html`; (2) decorative pseudo-elements (e.g. roll caps) with negative left/right overhang that make the expanded body wider than the collapsed trigger. Also watch modifier variants: a generic `[open]` rule can outrank a variant's `transform: none` and snap a perspective transform back on. | evidence: /home/dyadmin/githubStaging/dyuhaus.com three/styles.css `.fantasy__record--double` fixes

- 2026-07-25 | static-site copy editing | For "let the owner edit text without a CMS" on a static site, extract copy to content.json keyed by generated CSS selectors (bs4/soupsieve) and overlay via a tiny loader — static HTML stays as fallback and pages need only a data-page attr + one script tag. Gate the editor by token at the API level, not the HTML shell, and validate every selector matches exactly one element before shipping. | evidence: /home/dyadmin/githubStaging/WebsiteDyuhaus PR #1; tools/extract_content.py + content_server.py; 273/273 selector match check
