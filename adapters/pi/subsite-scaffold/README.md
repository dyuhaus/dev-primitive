# subsite-scaffold (pi extension)

Scaffolds a new sub-site under the **dyuhaus.com** repo the same way the existing
sub-sites are set up (`cadence/`, `dad/`, `pp-dev-associate/`, …) **and** emits a
portable *artifact* bundle you can carry off this headless box to generate the
real UI somewhere with a browser / design tooling.

Global extension, auto-discovered from `~/.pi/agent/extensions/subsite-scaffold/`.

## What it does

Given a slug (e.g. `labs`), in one pass it:

1. **Creates the sub-site folder** `<slug>/` with a working static skeleton:
   `index.html` (+ any extra pages), `styles.css` (brand tokens + base layout),
   `script.js`, `robots.txt`, `assets/`. Self-contained, no build step, relative
   asset paths, CSP meta intact — matching the repo's static sub-site pattern.
2. **Wires up routing** (idempotently). Hosting mode decides how:
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
3. **Emits a portable artifact** in `subsite-artifacts/<slug>/`:
   - `site.manifest.json` — machine-readable spec (routing, brand, tokens, pages, hosting)
   - `BRIEF.md` — human/LLM design brief + deploy checklist
   - `tokens.css` — portable CSS variables (drop-in)
   - `PROMPT.md` — ready-to-paste UI generation prompt
   - `README.md` — how to use the artifact off-box
   - optionally zips it into `~/transfer/` for handoff (uses `zip`, falls back to `tar.gz`).

The idea: this box is headless, so the extension builds the skeleton + wiring
here, and the artifact carries everything a UI generator needs elsewhere. Drop
the generated files back into `<slug>/`, commit, push `main` — Hostinger auto-pulls.

## Usage

### Interactive (TUI)

```
/new-subsite            # prompts for slug, title, brand, mode, pages, etc.
/new-subsite labs       # pre-fills the slug
```

### LLM tool

The model can call `create_subsite`. Example intents:

- "Add a new static IHTC sub-site `labs` under dyuhaus.com."
- "Scaffold `widget.dyuhaus.com` as a service on port 8790 and zip the artifact."

Key parameters: `slug` (required), `title`, `description`, `brand`
(`ihtc` | `personal` | `none`, default `ihtc`), `mode` (`tunnel` | `static` |
`service`, default **`tunnel`**), `port` (required for `service`; auto-assigned
for `tunnel`), `routeAsPath`, `immutableAssets`,
`pages` (extra page slugs), `emitArtifact` (default true), `zipArtifact`,
`dryRun`, `repoPath`.

## Repo resolution

`repoPath` arg → `$DYUHAUS_SITE_REPO` → walk up from cwd → default
`/home/dyadmin/githubStaging/dyuhaus.com`. A directory only counts if it has
`.htaccess`, `README.md`, and `index.html`.

## Brand tokens

`ihtc` tokens mirror `/home/dyadmin/brand/ihtc/BRAND-PROFILE.md` (the canonical
source of truth). If that profile changes, update `templates.ts` `THEMES.ihtc`
to match — the brand profile always wins.

## Safety / idempotency

- Existing site files and artifact files are **never overwritten** (create-only),
  so re-running won't clobber generated UI. Delete a file/folder to regenerate it.
- Wiring patches are added at most once (re-running is a no-op).
- Nothing is committed or pushed; no secrets are read or written.

## Files

| File | Role |
|------|------|
| `index.ts` | pi glue: registers the `create_subsite` tool + `/new-subsite` command |
| `core.ts` | pure logic: config, planning, wiring patchers, apply, zip (no pi imports) |
| `templates.ts` | HTML/CSS/JS + manifest/brief/prompt builders + brand themes |
| `_selftest.mjs` | unit test for `core.ts`/`templates.ts` (uses pi's bundled jiti) |
| `_loadtest.mjs` | loads `index.ts` like pi does and exercises the tool end-to-end |
| `build-template-site.mjs` | refreshes the IHTC child in the `starter/` template library |

## Template / showcase site

`build-template-site.mjs` refreshes the IHTC reference at
`starter/ihtc/` (→ `starter.dyuhaus.com/ihtc/`). It renders the exact layout new
IHTC sites ship with and displays a portable artifact example in tabbed,
copyable code panels. The script requires the template-library hub to be present
and never writes the hub or its curated artifact bundle:

```bash
cd ~/.pi/agent/extensions/subsite-scaffold
node build-template-site.mjs [repoPath]   # writes starter/ihtc/ only
```

It is safe to re-run after the library has landed: only `starter/ihtc/` is
created or overwritten; `starter/index.html`, the other genre templates, and
`subsite-artifacts/starter/`, routing, and repository documentation are preserved.

## Tests

```bash
cd ~/.pi/agent/extensions/subsite-scaffold
node _selftest.mjs     # pure logic against a throwaway repo copy
node _loadtest.mjs     # full extension load + tool.execute end-to-end
```

Both copy the real repo to a temp dir; they never modify the live repo.
