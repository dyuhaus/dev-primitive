// build-template-site.mjs
//
// Generates the "starter" showcase sub-site in the dyuhaus.com repo. It renders
// the exact layout newly created sites get, plus the portable artifact bundle
// (manifest / tokens / brief / prompt) for an example site, shown in code
// panels. Reproducible: re-run to refresh the showcase after template changes.
//
//   node build-template-site.mjs [repoPath]
//
// Uses pi's bundled jiti to load the TypeScript template/core modules.
import { promises as fs } from "node:fs";
import * as path from "node:path";
import { fileURLToPath } from "node:url";

const PIROOT = "/home/dyadmin/.hermes/node/lib/node_modules/@earendil-works/pi-coding-agent";
const { createJiti } = await import(`${PIROOT}/node_modules/jiti/lib/jiti.mjs`);
const here = path.dirname(fileURLToPath(import.meta.url));
const jiti = createJiti(import.meta.url, { interopDefault: true });

const T = await jiti.import(path.join(here, "templates.ts"));
const C = await jiti.import(path.join(here, "core.ts"));

const repo = process.argv[2] || C.resolveRepo(process.cwd());
if (!C.isSiteRepo(repo)) {
  console.error(`Not a dyuhaus.com site repo: ${repo}`);
  process.exit(1);
}

const esc = (s) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

/* ---- configs ----------------------------------------------------------- */
// The showcase site itself.
const starter = C.buildConfig({
  slug: "starter",
  title: "Sub-site Starter",
  description:
    "The reference template for dyuhaus.com sub-sites: the exact layout new sites ship with, plus the portable artifact bundle that drives off-box UI generation.",
  brand: "ihtc",
  mode: "tunnel",
  port: 8785,
  pages: [],
}).cfg;

// An example new site, used only to render representative files + artifact.
const example = C.buildConfig({
  slug: "aurora",
  title: "Aurora · IHTC",
  description: "Example IHTC sub-site scaffolded by subsite-scaffold.",
  brand: "ihtc",
  mode: "static",
  pages: ["pricing"],
}).cfg;

const exIndexPage = T.pageList(example)[0];
const files = {
  "index.html": T.buildPage(example, exIndexPage),
  "styles.css": T.buildStylesCss(example),
  "script.js": T.buildScriptJs(example),
};
const artifact = {
  "site.manifest.json": T.buildTokensJson(example),
  "tokens.css": T.buildTokensCss(example),
  "BRIEF.md": T.buildBrief(example),
  "PROMPT.md": T.buildPrompt(example),
};

const theme = T.themeFor(starter);
const tk = theme.tokens;

/* ---- helpers ----------------------------------------------------------- */
let uid = 0;
function tabs(items) {
  const gid = `g${uid++}`;
  const tablist = items
    .map(
      (it, i) =>
        `<button class="tab" role="tab" id="${gid}-t${i}" aria-controls="${gid}-p${i}" aria-selected="${i === 0}">${esc(
          it.label,
        )}</button>`,
    )
    .join("\n            ");
  const panels = items
    .map((it, i) => {
      const cid = `${gid}-c${i}`;
      return `<div class="tabpanel" role="tabpanel" id="${gid}-p${i}" aria-labelledby="${gid}-t${i}"${
        i === 0 ? "" : " hidden"
      }>
              <div class="code-head"><span class="code-name">${esc(it.label)}</span><button class="copy-btn" data-copy="${cid}">Copy</button></div>
              <pre class="code-block"><code id="${cid}">${esc(it.code)}</code></pre>
            </div>`;
    })
    .join("\n            ");
  return `<div class="code-tabs" data-tabs>
          <div class="tablist" role="tablist">
            ${tablist}
          </div>
          <div class="tabpanels">
            ${panels}
          </div>
        </div>`;
}

const swatches = [
  ["--bg", "Background", tk.bg, "bg"],
  ["--panel", "Panel", tk.panel, "panel"],
  ["--text", "Text", tk.text, "text"],
  ["--muted", "Muted", tk.muted, "muted"],
  ["--accent", "Accent", tk.accent, "accent"],
  ["--accent-dark", "Accent dark", tk.accentDark, "accent-dark"],
  ["--accent-2", "Accent 2", tk.accent2, "accent-2"],
  ["--bright", "Bright", tk.bright, "bright"],
]
  .map(
    ([v, label, hex, cls]) =>
      `<figure class="swatch"><span class="chip chip-${cls}"></span><figcaption><b>${esc(
        label,
      )}</b><code>${esc(hex)}</code><span class="var">${esc(v)}</span></figcaption></figure>`,
  )
  .join("\n            ");

/* ---- showcase page ----------------------------------------------------- */
const page = `<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <link rel="icon" type="image/svg+xml" href="/favicon.svg" />
    <title>${esc(starter.title)} · dyuhaus.com</title>
    <meta name="description" content="${esc(starter.description)}" />
    <meta http-equiv="Content-Security-Policy" content="default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self';" />
    <meta property="og:title" content="${esc(starter.title)}" />
    <meta property="og:description" content="${esc(starter.description)}" />
    <meta property="og:type" content="website" />
    <link rel="stylesheet" href="styles.css" />
  </head>
  <body>
    <header class="site-header">
      <div class="wrap header-row">
        <a href="index.html" class="brand"><span class="brand-name">Sub-site Starter</span></a>
        <nav class="nav" aria-label="Primary navigation">
          <a href="#layout">Layout</a>
          <a href="#tokens">Tokens</a>
          <a href="#files">Files</a>
          <a href="#artifact">Artifact</a>
          <a href="#pipeline">How it works</a>
        </nav>
      </div>
    </header>

    <main>
      <section class="hero">
        <div class="wrap">
          <p class="eyebrow">${esc(theme.tagline)}</p>
          <h1>${esc(starter.title)}</h1>
          <p class="lede">${esc(starter.description)}</p>
          <div class="hero-actions">
            <a class="button primary" href="#layout">See the layout</a>
            <a class="button ghost" href="#artifact">View the artifact</a>
          </div>
          <p class="fine-print">Generated by the <code>subsite-scaffold</code> pi extension. Every new <code>*.dyuhaus.com</code> sub-site starts from this layout and ships with the artifact shown below.</p>
        </div>
      </section>

      <section id="layout" class="band">
        <div class="wrap">
          <div class="section-head">
            <h2>The layout new sites ship with</h2>
            <p>These are the real components and classes a freshly scaffolded sub-site gets in <code>index.html</code> + <code>styles.css</code> — rendered live, not screenshots.</p>
          </div>

          <h3 class="demo-label">Buttons</h3>
          <div class="hero-actions demo-row">
            <a class="button primary" href="#layout">Primary action</a>
            <a class="button ghost" href="#layout">Ghost action</a>
          </div>

          <h3 class="demo-label">Cards</h3>
          <div class="grid-3">
            <article class="tile"><h3>Self-contained</h3><p>Local HTML/CSS/JS + <code>assets/</code>. No build step, no CDN, relative paths.</p></article>
            <article class="tile"><h3>Brand-wired</h3><p>Colors, type, spacing, and radius arrive as CSS variables from the brand profile.</p></article>
            <article class="tile"><h3>Routing-wired</h3><p>By default a local static origin is fronted by the <b>Cloudflare tunnel</b>, with an <code>.htaccess</code> fallback on Hostinger.</p></article>
          </div>

          <h3 class="demo-label">Type scale</h3>
          <div class="type-scale tile">
            <h1>Heading 1</h1>
            <h2>Heading 2</h2>
            <h3>Heading 3</h3>
            <p class="lede">Lede paragraph — the intro line under a heading.</p>
            <p>Body copy. Practical, direct, outcome-focused. <a href="#">Inline link</a> and <code>inline code</code>.</p>
          </div>
        </div>
      </section>

      <section id="tokens" class="band">
        <div class="wrap">
          <div class="section-head">
            <h2>Design tokens</h2>
            <p>The palette baked into every new site's <code>styles.css</code> and shipped standalone as <code>tokens.css</code> in the artifact. Source of truth: the IHTC brand profile.</p>
          </div>
          <div class="swatches">
            ${swatches}
          </div>
          <p class="fine-print">Radius ${esc(tk.radius)} / ${esc(tk.radiusLg)} · container ${esc(
            tk.container,
          )} · font <code>${esc(theme.fontSans)}</code></p>
        </div>
      </section>

      <section id="files" class="band">
        <div class="wrap">
          <div class="section-head">
            <h2>The generated files</h2>
            <p>Exactly what lands in the folder for an example site, <code>aurora.dyuhaus.com</code>.</p>
          </div>
          ${tabs([
            { label: "index.html", code: files["index.html"] },
            { label: "styles.css", code: files["styles.css"] },
            { label: "script.js", code: files["script.js"] },
          ])}
        </div>
      </section>

      <section id="artifact" class="band">
        <div class="wrap">
          <div class="section-head">
            <h2>The portable artifact</h2>
            <p>Because this host is headless, each site also ships a self-describing bundle in <code>subsite-artifacts/&lt;slug&gt;/</code>. Carry it to a machine with a browser, generate the UI, drop it back, and push. Below is the bundle for <code>aurora.dyuhaus.com</code>.</p>
          </div>
          ${tabs([
            { label: "site.manifest.json", code: artifact["site.manifest.json"] },
            { label: "tokens.css", code: artifact["tokens.css"] },
            { label: "BRIEF.md", code: artifact["BRIEF.md"] },
            { label: "PROMPT.md", code: artifact["PROMPT.md"] },
          ])}
        </div>
      </section>

      <section id="pipeline" class="band">
        <div class="wrap">
          <div class="section-head">
            <h2>How a new sub-site is made</h2>
            <p>One command on this headless box, then design happens wherever you have a browser.</p>
          </div>
          <ol class="pipeline">
            <li><span class="step">1</span><div><b>Scaffold</b><p>Run <code>/new-subsite</code> or the <code>create_subsite</code> tool. Folder, layout, routing, and README row are created here.</p></div></li>
            <li><span class="step">2</span><div><b>Carry the artifact</b><p>Copy <code>subsite-artifacts/&lt;slug&gt;/</code> (or zip it into <code>~/transfer/</code>) to a machine with a browser.</p></div></li>
            <li><span class="step">3</span><div><b>Generate the UI</b><p>Feed <code>PROMPT.md</code> + <code>site.manifest.json</code> + <code>tokens.css</code> to your design/codegen tool.</p></div></li>
            <li><span class="step">4</span><div><b>Ship it</b><p>Drop the generated files into <code>&lt;slug&gt;/</code>, commit, push <code>main</code>. The host pulls and <b>cloudflared</b> serves it (Hostinger is the fallback).</p></div></li>
          </ol>
        </div>
      </section>
    </main>

    <footer class="site-footer">
      <div class="wrap">
        <p class="fine-print">Built by ${esc(theme.full)} · <a href="https://dyuhaus.com">dyuhaus.com</a> · reference template for <code>*.dyuhaus.com</code> sub-sites</p>
      </div>
    </footer>

    <script src="script.js"></script>
  </body>
</html>
`;

/* ---- styles (base tokens + style-guide additions) ---------------------- */
const styleguideCss = `
/* ---- starter showcase additions ---------------------------------------- */
.demo-label { margin: 30px 0 12px; font-size: 0.82rem; text-transform: uppercase; letter-spacing: 0.12em; color: var(--muted); }
.demo-row { margin-bottom: 8px; }

.type-scale h1, .type-scale h2, .type-scale h3, .type-scale p { margin: 0 0 12px; }
.type-scale h1 { font-size: 2.2rem; line-height: 1.1; }

/* Swatches */
.swatches { display: grid; grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); gap: 14px; }
.swatch { margin: 0; background: var(--panel); border: 1px solid var(--line); border-radius: var(--radius-lg); overflow: hidden; }
.swatch .chip { display: block; height: 64px; }
.swatch figcaption { display: flex; flex-direction: column; gap: 2px; padding: 12px 14px; }
.swatch figcaption b { font-size: 0.95rem; }
.swatch figcaption code { color: var(--bright); font-size: 0.85rem; }
.swatch figcaption .var { color: var(--muted); font-size: 0.78rem; font-family: var(--font-mono); }
.chip-bg { background: var(--bg); box-shadow: inset 0 0 0 1px var(--line); }
.chip-panel { background: var(--panel); box-shadow: inset 0 0 0 1px var(--line); }
.chip-text { background: var(--text); }
.chip-muted { background: var(--muted); }
.chip-accent { background: var(--accent); }
.chip-accent-dark { background: var(--accent-dark); }
.chip-accent-2 { background: var(--accent-2); }
.chip-bright { background: var(--bright); }

/* Code tabs */
.code-tabs { border: 1px solid var(--line); border-radius: var(--radius-lg); overflow: hidden; background: #0c0b0b; }
.tablist { display: flex; flex-wrap: wrap; gap: 2px; padding: 8px 8px 0; background: var(--panel); border-bottom: 1px solid var(--line); }
.tab { appearance: none; background: transparent; color: var(--muted); border: 1px solid transparent; border-bottom: none; padding: 8px 14px; border-radius: var(--radius) var(--radius) 0 0; cursor: pointer; font: inherit; font-size: 0.88rem; }
.tab:hover { color: var(--text); }
.tab[aria-selected="true"] { color: var(--text); background: #0c0b0b; border-color: var(--line); }
.code-head { display: flex; align-items: center; justify-content: space-between; padding: 10px 14px; border-bottom: 1px solid var(--line); }
.code-name { color: var(--muted); font-family: var(--font-mono); font-size: 0.82rem; }
.copy-btn { appearance: none; background: transparent; color: var(--muted); border: 1px solid var(--line); border-radius: var(--radius); padding: 4px 10px; font: inherit; font-size: 0.78rem; cursor: pointer; }
.copy-btn:hover { color: var(--text); border-color: var(--muted); }
.copy-btn.copied { color: var(--accent-2); border-color: var(--accent-2); }
.code-block { margin: 0; padding: 16px 18px; max-height: 460px; overflow: auto; font-family: var(--font-mono); font-size: 0.82rem; line-height: 1.5; color: #e7e5e2; }
.code-block code { color: inherit; font-size: inherit; }

/* Pipeline */
.pipeline { list-style: none; margin: 0; padding: 0; display: grid; gap: 14px; }
.pipeline li { display: flex; gap: 16px; align-items: flex-start; background: var(--panel); border: 1px solid var(--line); border-radius: var(--radius-lg); padding: 18px 20px; }
.pipeline .step { flex: none; width: 34px; height: 34px; display: grid; place-items: center; border-radius: 50%; background: var(--accent); color: #fff; font-weight: 700; }
.pipeline b { display: block; margin-bottom: 4px; }
.pipeline p { margin: 0; color: var(--muted); }

/* Anchor offset under sticky header */
:target { scroll-margin-top: 84px; }
`;

const script = `// Sub-site Starter showcase — tabs + copy buttons. Self-contained, no deps.
(function () {
  "use strict";

  document.querySelectorAll("[data-tabs]").forEach(function (group) {
    var tabs = group.querySelectorAll('[role="tab"]');
    var panels = group.querySelectorAll('[role="tabpanel"]');
    tabs.forEach(function (tab) {
      tab.addEventListener("click", function () {
        tabs.forEach(function (t) { t.setAttribute("aria-selected", "false"); });
        panels.forEach(function (p) { p.hidden = true; });
        tab.setAttribute("aria-selected", "true");
        var panel = group.querySelector("#" + tab.getAttribute("aria-controls"));
        if (panel) panel.hidden = false;
      });
    });
  });

  document.querySelectorAll(".copy-btn").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var el = document.getElementById(btn.getAttribute("data-copy"));
      if (!el) return;
      var text = el.textContent || "";
      var done = function () {
        btn.classList.add("copied");
        var prev = btn.textContent;
        btn.textContent = "Copied";
        setTimeout(function () { btn.classList.remove("copied"); btn.textContent = prev; }, 1200);
      };
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(done).catch(function () {});
      }
    });
  });
})();
`;

/* ---- write site + real artifact + wiring ------------------------------- */
const siteDir = path.join(repo, "starter");
await fs.mkdir(path.join(siteDir, "assets"), { recursive: true });
await fs.writeFile(path.join(siteDir, "index.html"), page, "utf8");
await fs.writeFile(path.join(siteDir, "styles.css"), T.buildStylesCss(starter) + styleguideCss, "utf8");
await fs.writeFile(path.join(siteDir, "script.js"), script, "utf8");
await fs.writeFile(path.join(siteDir, "robots.txt"), T.buildRobots(starter), "utf8");
await fs.writeFile(path.join(siteDir, "assets", ".gitkeep"), "", "utf8");

// Real artifact bundle for the starter itself.
const aDir = path.join(repo, C.ARTIFACT_ROOT, "starter");
await fs.mkdir(aDir, { recursive: true });
await fs.writeFile(path.join(aDir, "site.manifest.json"), T.buildTokensJson(starter), "utf8");
await fs.writeFile(path.join(aDir, "tokens.css"), T.buildTokensCss(starter), "utf8");
await fs.writeFile(path.join(aDir, "BRIEF.md"), T.buildBrief(starter), "utf8");
await fs.writeFile(path.join(aDir, "PROMPT.md"), T.buildPrompt(starter), "utf8");
await fs.writeFile(path.join(aDir, "README.md"), T.buildArtifactReadme(starter), "utf8");

// Idempotent wiring on the live (possibly dirty) files.
const changes = [];
async function patchFile(rel, fns) {
  const p = path.join(repo, rel);
  let content;
  try {
    content = await fs.readFile(p, "utf8");
  } catch {
    return;
  }
  let changed = false;
  for (const fn of fns) {
    const next = fn(content);
    if (next && next !== content) {
      content = next;
      changed = true;
    }
  }
  if (changed) {
    await fs.writeFile(p, content, "utf8");
    changes.push(rel);
  }
}
await patchFile(".htaccess", [
  (c) => C.patchHtaccessRewrite(c, starter),
  (c) => C.patchHtaccessCache(c, starter),
  (c) => C.patchHtaccessBlockArtifacts(c),
]);
await patchFile("tunnel/config.yml", [(c) => C.patchTunnelIngress(c, starter)]);
// Replace any prior starter Domains row so the wording reflects the tunnel.
await patchFile("README.md", [
  (c) => {
    const stripped = c.replace(/^\|\s*`starter\.dyuhaus\.com`.*\n/m, "");
    return stripped !== c ? stripped : null;
  },
  (c) => C.patchReadmeRow(c, starter),
]);

console.log("Wrote starter/ showcase site:");
console.log("  starter/index.html  (" + page.length + " bytes)");
console.log("  starter/styles.css, starter/script.js, starter/robots.txt, starter/assets/");
console.log("  subsite-artifacts/starter/ (manifest, tokens.css, BRIEF.md, PROMPT.md, README.md)");
console.log("Wiring updated: " + (changes.length ? changes.join(", ") : "already present"));
console.log("\nSubdomain: https://starter.dyuhaus.com");
