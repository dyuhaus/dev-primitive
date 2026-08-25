# subsite-scaffold (pi extension)

Scaffolds a new sub-site under the **dyuhaus.com** repo the same way the existing
sub-sites are set up (`cadence/`, `dad/`, `pp-dev-associate/`, …) **and** emits a
portable *artifact* bundle you can carry off this headless box to generate the
real UI somewhere with a browser / design tooling.

Global extension, auto-discovered from `~/.pi/agent/extensions/subsite-scaffold/`.

## What it does

Given a slug (e.g. `labs`), in one pass it:

1. **Requires an explicit template-theme choice** before any files are planned
   or written: Literary, Noir, Science Fiction, High Fantasy, Horror, Poetry,
   Correspondence, or IHTC. There is no default.
2. **Creates the sub-site folder from that confirmed template**:
   `index.html` (+ any extra pages), the template's `styles.css` and exact
   `script.js`, `robots.txt`, and `assets/`. IHTC CSS variables are reconciled
   to the canonical brand profile as they are copied. The page title and description are
   adapted to the new project while the selected composition, palette, type,
   and behavior remain intact. It is self-contained, has no build step, uses
   relative asset paths, and keeps the template CSP.
3. **Wires up routing** (idempotently). Hosting mode decides how:
   - **tunnel** (default) → static files served by `ops/static-server.cjs` on an
     auto-assigned port, fronted by the Cloudflare tunnel: adds a
     `tunnel/config.yml` ingress entry (`<slug>.dyuhaus.com → http://localhost:<port>`,
     before the catch-all 404) **and** an `.htaccess` rewrite + cache rule as a
     Hostinger fallback. The brief lists the `dy-<slug>-static` NSSM service to add.
   - **static** → adds only the `.htaccess` `RewriteCond`/`RewriteRule` block for
     `<slug>.dyuhaus.com` plus a `no_immutable_assets` cache-revalidate rule.
   - **service** → adds a `tunnel/config.yml` ingress pointing `<slug>.dyuhaus.com`
     at `http://localhost:<port>` (your own backend; explicit `port` required).
   - Adds a row to the `README.md` **Domains** table in every mode.
   - Adds `subsite-artifacts` to the `.htaccess` block list so the artifact is
     never served publicly.
4. **Emits a portable artifact** in `subsite-artifacts/<slug>/`:
   - `site.manifest.json` — machine-readable spec (routing, brand, confirmed template, pages, hosting; portable design data only when authoritative)
   - `scaffold.complete.json` — exact-manifest completion record, written last
   - `BRIEF.md` — human/LLM design brief + deploy checklist
   - `tokens.css` — authoritative brand/IHTC variables when applicable; otherwise an explicit pointer to the confirmed genre reference with no generic fallback values
   - `PROMPT.md` — ready-to-paste UI generation prompt
   - `README.md` — how to use the artifact off-box
   - optionally zips it into `~/transfer/` for handoff (uses `zip`, falls back to `tar.gz`).

The idea: this box is headless, so the extension copies the confirmed template
as the working site and adds the wiring here. The artifact carries everything a
UI generator needs to replace the sample content elsewhere. Drop the finished
files back into `<slug>/`, commit, and push through the normal PR workflow.

## Usage

### Interactive (TUI)

```
/new-subsite            # prompts for theme, slug, title, brand, mode, pages, etc.
/new-subsite labs       # pre-fills the slug
```

### LLM tool

The model can call `create_subsite`. Example intents:

- "Add a new static IHTC sub-site `labs` under dyuhaus.com."
- "Scaffold `widget.dyuhaus.com` as a service on port 8790 and zip the artifact."

For any new site, including one for an existing project, the tool itself opens
a selector in the local Pi TUI and waits for David to choose the theme. Theme
selection is deliberately absent from the model-callable schema, and
RPC/headless selection responses are not accepted. Those supported extension
entrypoints cannot silently supply the choice; direct shell or source-level
actions remain governed by the machine contract's mandatory ask-first rule. A
non-interactive call or a cancelled selection is refused before planning.

For an existing site, the tool does not ask again. It reuses the complete
persisted creation settings; the pinned pre-theme Job Sweep manifest carrying
the old terminal style is recognized as a legacy IHTC site. Conflicting new arguments are
ignored. An existing site with no reusable manifest is handed to the
existing-site workflow instead of being guessed at.

The selector offers `literary`, `noir`, `science-fiction`, `high-fantasy`,
`horror`, `poetry`, `correspondence`, and `ihtc`.

Key parameters: `slug` (required), `title`, `description`, `brand`
(`ihtc` | `personal` | `none`, default `ihtc`), `mode` (`tunnel` | `static` |
`service`, default **`tunnel`**), `port` (required for `service`; auto-assigned
for `tunnel`), `routeAsPath`, `immutableAssets`,
`pages` (extra page slugs), `zipArtifact`, `dryRun`, `repoPath`.

## Repo resolution

`repoPath` arg → `$DYUHAUS_SITE_REPO` → walk up from cwd → default
`/home/dyadmin/githubStaging/dyuhaus.com`. A directory only counts if it has
`.htaccess`, `README.md`, and `index.html`.

## Brand tokens

`ihtc` tokens mirror `/home/dyadmin/brand/ihtc/BRAND-PROFILE.md` (the canonical
source of truth). If that profile changes, update `templates.ts` `THEMES.ihtc`
to match — the brand profile always wins. For every non-IHTC genre choice,
including a site that carries the IHTC name or mark, the artifact omits generic
token/font fields and points to the confirmed live template so fallback design
data cannot override its palette or typography.

## Safety / idempotency

- Existing site files and artifact files are **never overwritten** (create-only),
  so re-running won't clobber generated UI. Delete a file/folder to regenerate it.
- Supported new-site entrypoints take theme confirmation only from the local
  interactive selector; model arguments and RPC responses cannot supply it.
  Refused calls write nothing. This is a visible workflow control, not an OS
  privilege boundary: Pi and its tools share one Unix account, so direct file or
  source actions must obey the machine-level rule.
- Existing sites reuse all persisted creation settings without a second theme
  prompt. Conflicting arguments cannot mix new routing with stale artifacts.
- New sites atomically publish the confirmed site identity before any site file
  is written, then publish a manifest-bound completion record only after every
  scaffold write succeeds. Concurrent extension attempts cannot mix themes. A
  partial site directory is never treated as complete; an interrupted run
  reuses its recorded settings only after David reconfirms the theme in the
  local TUI. Completed sites remain regenerable if their generated folder is
  removed.
- Wiring patches are added at most once (re-running is a no-op).
- Nothing is committed or pushed.

## Files

| File | Role |
|------|------|
| `index.ts` | pi glue: registers the `create_subsite` tool + `/new-subsite` command |
| `core.ts` | pure logic: config, planning, wiring patchers, apply, zip (no pi imports) |
| `templates.ts` | HTML/CSS/JS + manifest/brief/prompt builders + brand themes |
| `_selftest.mjs` | unit test for `core.ts`/`templates.ts` (uses pi's bundled jiti) |
| `_loadtest.mjs` | loads `index.ts` like pi does and exercises the tool end-to-end |
| `build-template-site.mjs` | read-only verification for the curated IHTC child in the `starter/` template library |

## Template / showcase site

`build-template-site.mjs` is retained as a compatibility command, but it no
longer generates the template. The IHTC reference at `starter/ihtc/` (→
`starter.dyuhaus.com/ihtc/`) is hand-authored and authoritative. The command
delegates to the library-owned `ops/validate-starter-templates.mjs`, then exits
without writing any file; the site repo therefore owns the one validation
contract:

```bash
cd ~/.pi/agent/extensions/subsite-scaffold
node build-template-site.mjs [repoPath]   # verifies only; writes nothing
```

It is safe to run after the library has landed because it is non-mutating. If
the curated IHTC child is missing or incomplete, restore it from the
`dyuhaus.com` repository; do not regenerate or overwrite it from this extension.

## Tests

```bash
cd ~/.pi/agent/extensions/subsite-scaffold
node _selftest.mjs     # pure logic against a throwaway repo copy
node _loadtest.mjs     # full extension load + tool.execute end-to-end
```

Both copy the real repo to a temp dir; they never modify the live repo.
