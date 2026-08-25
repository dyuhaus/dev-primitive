// Templates + brand themes for the dyuhaus.com sub-site scaffolder.
//
// Everything here is pure data / string building. No filesystem or pi APIs, so
// it is trivial to unit test and to reuse from the portable artifact.

export type BrandKey = "ihtc" | "personal" | "none";
// tunnel  = static files served by ops/static-server.cjs on a port, fronted by
//           cloudflared (the default; pl400 model), with an .htaccess fallback.
// static  = Hostinger repo root, routed by .htaccess only (no tunnel).
// service = cloudflared tunnel -> a user-provided backend on an explicit port.
export type SiteMode = "tunnel" | "static" | "service";

export interface SubsiteConfig {
  /** folder name + subdomain label, e.g. "labs" -> labs.dyuhaus.com */
  slug: string;
  /** full subdomain, e.g. labs.dyuhaus.com */
  subdomain: string;
  title: string;
  description: string;
  brand: BrandKey;
  mode: SiteMode;
  /** local origin port for tunnel/service mode (auto-assigned for tunnel if unset) */
  port?: number;
  /** also serve under dyuhaus.com/<slug>/ (path routing), like pp-dev-associate */
  routeAsPath: boolean;
  /** true only for hashed/fingerprinted assets (Vite). Hand-authored -> false. */
  immutableAssets: boolean;
  /** extra page slugs (without .html); index is always present */
  pages: string[];
  tagline?: string;
  createdAt: string;
}

export interface BrandTheme {
  key: BrandKey;
  name: string;
  full: string;
  tagline: string;
  /** display/heading face (Space Grotesk) */
  fontDisplay: string;
  /** body face (Inter) — kept as fontSans for back-compat */
  fontSans: string;
  fontMono: string;
  tokens: {
    bg: string;
    panel: string;
    text: string;
    muted: string;
    accent: string;
    accentDark: string;
    accent2: string;
    bright: string;
    line: string;
    radius: string;
    radiusLg: string;
    container: string;
    shadow: string;
  };
  voice: { do: string[]; dont: string[] };
}

const SANS_SYSTEM =
  'ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif';
const MONO_SYSTEM =
  'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace';

// dyuhaus.com website house style — the terminal type shared across all
// *.dyuhaus.com sub-sites. See /home/dyadmin/brand/ihtc/BRAND-PROFILE.md
// → "Website House Style — dyuhaus.com family". Loaded via Google Fonts.
const FONT_DISPLAY = '"Space Grotesk", ' + SANS_SYSTEM;
const FONT_BODY = '"Inter", ' + SANS_SYSTEM;
const FONT_MONO = '"JetBrains Mono", ' + MONO_SYSTEM;
// Google Fonts stylesheet the house style loads (fonts.googleapis / gstatic).
export const HOUSE_FONTS_HREF =
  "https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500;700&family=Space+Grotesk:wght@500;700&display=swap";

export const THEMES: Record<BrandKey, BrandTheme> = {
  // Canonical IHTC tokens — mirror /home/dyadmin/brand/ihtc/BRAND-PROFILE.md
  ihtc: {
    key: "ihtc",
    name: "IHTC",
    full: "In House Technology & Consulting",
    tagline: "No sci-fi gimmicks. Just outcomes.",
    fontDisplay: FONT_DISPLAY,
    fontSans: FONT_BODY,
    fontMono: FONT_MONO,
    tokens: {
      bg: "#171616",
      panel: "#1F1F1F",
      text: "#F3F4F6",
      muted: "#9C9996",
      accent: "#DD1B27",
      accentDark: "#A40C1B",
      accent2: "#2CAC5E",
      bright: "#66E891",
      line: "rgba(156, 153, 150, 0.22)",
      radius: "8px",
      radiusLg: "12px",
      container: "1180px",
      shadow: "0 18px 48px rgba(0, 0, 0, 0.45)",
    },
    voice: {
      do: [
        "Clear inputs, clear outputs, human review.",
        "Practical technology help for real teams.",
        "Useful, safe, and maintainable.",
      ],
      dont: [
        "Leverage AI to transform...",
        "Unlock the power of...",
        "Revolutionary / game-changing / cutting-edge (unless specific).",
      ],
    },
  },
  // David Yuhaus personal — neutral dark, echoes the main dyuhaus.com feel.
  personal: {
    key: "personal",
    name: "David Yuhaus",
    full: "David Yuhaus",
    tagline: "AI & Infrastructure Specialist",
    fontDisplay: FONT_DISPLAY,
    fontSans: FONT_BODY,
    fontMono: FONT_MONO,
    tokens: {
      bg: "#0d0f12",
      panel: "#171a1f",
      text: "#e8eaed",
      muted: "#9aa0a6",
      accent: "#4f9cf9",
      accentDark: "#2f7de0",
      accent2: "#34d399",
      bright: "#7dd3fc",
      line: "rgba(255, 255, 255, 0.10)",
      radius: "8px",
      radiusLg: "14px",
      container: "1120px",
      shadow: "0 18px 48px rgba(0, 0, 0, 0.5)",
    },
    voice: {
      do: ["Concrete, technical, honest.", "Show the system, not the hype."],
      dont: ["Buzzword salad.", "Vague founder-speak."],
    },
  },
  // Unbranded neutral grayscale — a blank, safe starting point.
  none: {
    key: "none",
    name: "Sub-site",
    full: "dyuhaus.com sub-site",
    tagline: "",
    fontDisplay: FONT_DISPLAY,
    fontSans: FONT_BODY,
    fontMono: FONT_MONO,
    tokens: {
      bg: "#0f1115",
      panel: "#181b20",
      text: "#eceef1",
      muted: "#9aa1a9",
      accent: "#5b8def",
      accentDark: "#3f6fd0",
      accent2: "#3fb984",
      bright: "#8fd0ff",
      line: "rgba(255, 255, 255, 0.10)",
      radius: "8px",
      radiusLg: "12px",
      container: "1120px",
      shadow: "0 18px 48px rgba(0, 0, 0, 0.5)",
    },
    voice: { do: [], dont: [] },
  },
};

export function themeFor(cfg: SubsiteConfig): BrandTheme {
  return THEMES[cfg.brand] ?? THEMES.none;
}

/** Escape a slug for use inside an Apache/regex host pattern. */
export function slugRegex(slug: string): string {
  return slug.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function esc(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function pageTitle(slug: string): string {
  return slug
    .split(/[-_]/)
    .map((w) => (w ? w[0].toUpperCase() + w.slice(1) : w))
    .join(" ");
}

/** All pages for the site: index first, then extras. */
export function pageList(cfg: SubsiteConfig): { slug: string; file: string; label: string; isIndex: boolean }[] {
  const pages = [{ slug: "index", file: "index.html", label: "Home", isIndex: true }];
  for (const p of cfg.pages) {
    const s = p.replace(/\.html$/i, "").trim();
    if (!s || s === "index") continue;
    pages.push({ slug: s, file: `${s}.html`, label: pageTitle(s), isIndex: false });
  }
  return pages;
}

/* --------------------------------------------------------------------------
 * HTML
 * ------------------------------------------------------------------------ */

export function buildPage(
  cfg: SubsiteConfig,
  page: { slug: string; file: string; label: string; isIndex: boolean },
): string {
  const theme = themeFor(cfg);
  const pages = pageList(cfg);
  const nav = pages
    .map((p) => {
      const active = p.file === page.file ? ' aria-current="page"' : "";
      return `          <a href="${p.file}"${active}>${esc(p.label)}</a>`;
    })
    .join("\n");

  const title = page.isIndex ? cfg.title : `${pageTitle(page.slug)} · ${cfg.title}`;
  const heroTitle = page.isIndex ? cfg.title : pageTitle(page.slug);
  const heroLede = page.isIndex
    ? esc(cfg.description)
    : "Placeholder page. Replace this content when you generate the real UI from the artifact.";
  const eyebrow = theme.tagline
    ? `<p class="eyebrow">// ${esc(theme.tagline)}</p>`
    : `<p class="eyebrow">// ${esc(cfg.subdomain)}</p>`;
  const brandFull = cfg.brand !== "none" ? `${esc(theme.full)} · ` : "";
  const routingBlurb =
    cfg.mode === "tunnel"
      ? "A local static origin is fronted by the Cloudflare tunnel (with an <code>.htaccess</code> fallback)."
      : cfg.mode === "service"
        ? "A Cloudflare tunnel ingress points the subdomain at your local service."
        : "<code>.htaccess</code> routes the subdomain to this folder.";

  const bootLines = [
    `$ ./serve ${cfg.slug}`,
    "▸ load brand tokens .......... ok",
    `▸ mount ${cfg.subdomain} ...... ok`,
    "✓ ready",
  ];
  const heroTerm = page.isIndex
    ? `
          <div class="term-window">
            <div class="term-bar">
              <span class="dots" aria-hidden="true"><i></i><i></i><i></i></span>
              <span class="term-title">${esc(cfg.slug)} — bash</span>
              <button class="replay" id="replay" type="button">↻ replay</button>
            </div>
            <pre class="boot" aria-hidden="true"><code id="boot" data-lines="${esc(bootLines.join("|"))}">${esc(bootLines.join("\n"))}</code></pre>
          </div>`
    : "";

  const heroBlock = page.isIndex
    ? `      <section class="hero">
        <div class="wrap hero-grid">
          <div class="hero-copy">
            ${eyebrow}
            <h1>${esc(heroTitle)}</h1>
            <p class="lede">${heroLede}</p>
            <div class="hero-actions">
              <a class="button primary" href="#content">[ get started ]</a>
              <a class="button ghost" href="https://dyuhaus.com">[ dyuhaus.com ]</a>
            </div>
            <p class="fine-print">// scaffolded — replace from subsite-artifacts/${esc(cfg.slug)}/</p>
          </div>${heroTerm}
        </div>
      </section>`
    : `      <section class="hero">
        <div class="wrap">
          ${eyebrow}
          <h1>${esc(heroTitle)}</h1>
          <p class="lede">${heroLede}</p>
          <div class="hero-actions">
            <a class="button ghost" href="index.html">[ home ]</a>
          </div>
        </div>
      </section>`;

  const contentBlock = page.isIndex
    ? `

      <section id="content" class="band">
        <span class="ghost-num" aria-hidden="true">01</span>
        <div class="wrap">
          <div class="section-head">
            <p class="sec-head"><span class="path">~/${esc(cfg.slug)}</span> <span class="dollar">$</span> ls --wired</p>
            <h2>Scaffolded starting point</h2>
            <p>A house-style skeleton from the <code>subsite-scaffold</code> pi extension. Flesh it out from the artifact in <code>subsite-artifacts/${esc(cfg.slug)}/</code>.</p>
          </div>
          <div class="grid-3">
            <article class="tile"><h3>Brand tokens wired<span class="tstat"></span></h3><p>Colors, type, spacing, and radius are already in <code>styles.css</code> as CSS variables.</p></article>
            <article class="tile"><h3>Routing wired<span class="tstat"></span></h3><p>${routingBlurb}</p></article>
            <article class="tile"><h3>Portable artifact<span class="tstat"></span></h3><p>A self-describing spec + brief lets you generate the real UI on a machine with a browser.</p></article>
          </div>
        </div>
      </section>`
    : "";

  return `<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <link rel="icon" type="image/svg+xml" href="/favicon.svg" />
    <title>${esc(title)}</title>
    <meta name="description" content="${esc(cfg.description)}" />
    <meta http-equiv="Content-Security-Policy" content="default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; img-src 'self' data:; font-src https://fonts.gstatic.com; connect-src 'self';" />
    <meta property="og:title" content="${esc(cfg.title)}" />
    <meta property="og:description" content="${esc(cfg.description)}" />
    <meta property="og:type" content="website" />
    <link rel="preconnect" href="https://fonts.googleapis.com" />
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
    <link href="${HOUSE_FONTS_HREF}" rel="stylesheet" />
    <link rel="stylesheet" href="styles.css" />
  </head>
  <body>
    <header class="site-header">
      <div class="wrap header-row">
        <a href="index.html" class="brand">
          <span class="dots" aria-hidden="true"><i></i><i></i><i></i></span>
          <span class="brand-name"><b>${esc(cfg.slug)}</b> · dyuhaus.com</span>
        </a>
        <nav class="nav" aria-label="Primary navigation">
${nav}
        </nav>
      </div>
    </header>

    <main>
${heroBlock}${contentBlock}
    </main>

    <footer class="site-footer">
      <div class="wrap">
        <p class="fine-print">// ${brandFull}<a href="https://dyuhaus.com">dyuhaus.com</a></p>
      </div>
    </footer>

    <div class="statusbar" aria-hidden="true">
      <div class="wrap statusbar-row">
        <span class="sb-item sb-live"><span class="dot"></span> LIVE</span>
        <span class="sb-item">${esc(cfg.subdomain)}</span>
        <span class="sb-item sb-clock" id="sb-clock">--:--:--</span>
      </div>
    </div>

    <script src="script.js"></script>
  </body>
</html>
`;
}

/* --------------------------------------------------------------------------
 * CSS
 * ------------------------------------------------------------------------ */

export function buildTokensCss(cfg: SubsiteConfig): string {
  const t = themeFor(cfg);
  const k = t.tokens;
  return `/* ${t.full} — dyuhaus.com sub-site tokens (terminal house style), portable.
 * Palette resolves from the brand theme; type is the shared dyuhaus house style.
 * Source of truth for IHTC: /home/dyadmin/brand/ihtc/BRAND-PROFILE.md
 *   -> "Website House Style — dyuhaus.com family". The brand profile always wins.
 */
:root {
  /* palette (brand) */
  --bg: ${k.bg};
  --bg-0: #0d0c0c;
  --panel: ${k.panel};
  --text: ${k.text};
  --text-dim: color-mix(in srgb, ${k.text} 80%, ${k.bg});
  --muted: ${k.muted};
  --text-faint: color-mix(in srgb, ${k.muted} 55%, transparent);
  --accent: ${k.accent};
  --accent-dark: ${k.accentDark};
  --accent-2: ${k.accent2};
  --bright: ${k.bright};
  --line: ${k.line};
  --border-hi: color-mix(in srgb, ${k.muted} 30%, transparent);
  --radius: ${k.radius};
  --radius-lg: ${k.radiusLg};
  --container: ${k.container};
  --shadow: ${k.shadow};
  /* type (dyuhaus house style — loaded via Google Fonts) */
  --font-display: ${t.fontDisplay};
  --font-body: ${t.fontSans};
  --font-mono: ${t.fontMono};
}
`;
}

export function buildStylesCss(cfg: SubsiteConfig): string {
  return `${buildTokensCss(cfg)}
/* dyuhaus.com terminal house style. See BRAND-PROFILE.md → Website House Style. */
* { box-sizing: border-box; }
html { scroll-behavior: smooth; }

body {
  margin: 0;
  font-family: var(--font-body);
  color: var(--text);
  line-height: 1.6;
  padding-bottom: 42px;
  background:
    radial-gradient(880px 420px at 15% -6%, color-mix(in srgb, var(--accent) 14%, transparent), transparent 60%),
    radial-gradient(880px 420px at 85% -6%, color-mix(in srgb, var(--accent-2) 12%, transparent), transparent 60%),
    var(--bg);
  -webkit-font-smoothing: antialiased;
}
body::before {
  content: "";
  position: fixed; inset: 0; z-index: 9999; pointer-events: none; opacity: 0.5;
  background: repeating-linear-gradient(0deg, rgba(255, 255, 255, 0.014) 0 1px, transparent 1px 3px);
}
a { color: inherit; text-decoration: none; }
::selection { background: var(--bright); color: #06130b; }
code { font-family: var(--font-mono); font-size: 0.9em; color: var(--bright); }
img, svg { max-width: 100%; }

.wrap { width: min(var(--container), calc(100% - 40px)); margin: 0 auto; }
.path { color: var(--bright); }
.dollar { color: var(--accent); }
.cursor { display: inline-block; width: 0.6ch; height: 1.02em; vertical-align: -0.14em; margin-left: 4px; background: var(--bright); animation: blink 1.1s steps(2, end) infinite; }
@keyframes blink { 50% { opacity: 0; } }
@keyframes pulse { 50% { opacity: 0.35; } }

/* Header — terminal window bar */
.site-header { position: sticky; top: 0; z-index: 20; background: color-mix(in srgb, var(--bg) 88%, transparent); backdrop-filter: blur(10px); border-bottom: 1px solid var(--line); }
.header-row { display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 12px 0; }
.brand { display: flex; align-items: center; gap: 12px; }
.dots { display: inline-flex; gap: 6px; flex: none; }
.dots i { width: 11px; height: 11px; border-radius: 50%; border: 1px solid; display: inline-block; }
.dots i:nth-child(1) { border-color: var(--accent); }
.dots i:nth-child(2) { border-color: var(--muted); }
.dots i:nth-child(3) { border-color: var(--accent-2); }
.brand-name { font-family: var(--font-mono); font-size: 0.9rem; color: var(--muted); }
.brand-name b { color: var(--bright); font-weight: 700; }
.nav { display: flex; gap: 4px; align-items: center; flex-wrap: wrap; font-family: var(--font-mono); font-size: 0.82rem; }
.nav a { color: var(--muted); padding: 4px 8px; border: 1px solid transparent; border-radius: 5px; }
.nav a::before { content: "["; color: var(--text-faint); }
.nav a::after { content: "]"; color: var(--text-faint); }
.nav a:hover, .nav a[aria-current="page"] { color: #06130b; background: var(--bright); border-color: var(--bright); }
.nav a:hover::before, .nav a:hover::after,
.nav a[aria-current="page"]::before, .nav a[aria-current="page"]::after { color: #06130b; }

/* Hero */
.hero { padding: 84px 0 56px; }
.hero-grid { display: grid; grid-template-columns: minmax(0, 1.05fr) minmax(0, 0.95fr); gap: 34px; align-items: center; }
.hero-copy { min-width: 0; }
.hero .eyebrow { font-family: var(--font-mono); font-size: 0.84rem; color: var(--muted); margin: 0 0 18px; }
.hero h1 { font-family: var(--font-display); font-weight: 700; font-size: clamp(2rem, 5.2vw, 3.25rem); line-height: 1.03; letter-spacing: -0.01em; margin: 0 0 18px; max-width: 20ch; }
.hero h1 .accent { color: var(--bright); }
.hero .lede { color: var(--text-dim); font-size: 1.12rem; max-width: 60ch; margin: 0 0 24px; }
.hero-actions { display: flex; gap: 10px; flex-wrap: wrap; }
.hero .fine-print { margin-top: 20px; }

/* Terminal window + boot log */
.term-window { border: 1px solid var(--border-hi); border-radius: var(--radius-lg); overflow: hidden; background: var(--bg-0); box-shadow: var(--shadow); }
.term-bar { display: flex; align-items: center; gap: 10px; padding: 9px 13px; background: var(--panel); border-bottom: 1px solid var(--line); }
.term-bar .dots i { width: 10px; height: 10px; }
.term-title { font-family: var(--font-mono); font-size: 0.78rem; color: var(--text-faint); }
.term-bar .replay { margin-left: auto; appearance: none; background: transparent; color: var(--muted); border: 1px solid var(--border-hi); border-radius: 6px; padding: 3px 9px; font-family: var(--font-mono); font-size: 0.72rem; cursor: pointer; }
.term-bar .replay:hover { color: var(--bright); border-color: var(--accent-2); }
.boot { margin: 0; padding: 16px 18px; font-family: var(--font-mono); font-size: 0.82rem; line-height: 1.7; color: var(--text-dim); min-height: 168px; white-space: pre-wrap; word-break: break-word; }
.boot::after { content: "▋"; color: var(--bright); animation: blink 1.1s steps(2, end) infinite; }

/* Buttons — bracketed terminal actions */
.button { display: inline-flex; align-items: center; gap: 8px; font-family: var(--font-mono); font-size: 0.9rem; padding: 9px 16px; border-radius: var(--radius); border: 1px solid var(--border-hi); color: var(--text); transition: transform 0.12s ease, background 0.15s ease, border-color 0.15s ease, color 0.15s ease; }
.button:hover { transform: translateY(-1px); }
.button.primary { border-color: var(--accent-2); color: var(--bright); }
.button.primary:hover { background: var(--bright); color: #06130b; border-color: var(--bright); }
.button.ghost { color: var(--muted); }
.button.ghost:hover { border-color: var(--accent); color: var(--accent); }

/* Bands + section heads */
.band { position: relative; padding: 60px 0; border-top: 1px solid var(--line); overflow: hidden; }
.ghost-num { position: absolute; top: 6px; right: 2%; font-family: var(--font-display); font-weight: 700; font-size: clamp(6rem, 16vw, 12rem); line-height: 1; color: var(--text); opacity: 0.03; pointer-events: none; user-select: none; }
.section-head { position: relative; max-width: 64ch; margin: 0 0 28px; }
.sec-head { font-family: var(--font-mono); font-size: 0.86rem; color: var(--muted); margin: 0 0 12px; }
.section-head h2 { font-family: var(--font-display); font-weight: 700; font-size: clamp(1.5rem, 3vw, 2rem); margin: 0 0 10px; }
.section-head > p { color: var(--text-dim); margin: 0; }

/* Cards — proc/service style */
.grid-3 { display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 16px; }
.tile { background: var(--panel); border: 1px solid var(--border-hi); border-radius: var(--radius-lg); box-shadow: var(--shadow); display: flex; flex-direction: column; overflow: hidden; transition: border-color 0.15s ease, transform 0.12s ease; }
.tile:hover { border-color: var(--accent-2); transform: translateY(-2px); }
.tile h3 { margin: 0; padding: 11px 16px; font-family: var(--font-mono); font-size: 0.92rem; font-weight: 500; color: var(--text); border-bottom: 1px solid var(--line); display: flex; align-items: center; gap: 8px; }
.tile h3::before { content: ">"; color: var(--bright); }
.tile h3 .tstat { margin-left: auto; width: 8px; height: 8px; border-radius: 50%; background: var(--bright); box-shadow: 0 0 8px var(--bright); animation: pulse 1.8s ease-in-out infinite; }
.tile p { margin: 0; padding: 14px 16px; color: var(--text-dim); font-size: 0.95rem; }

/* Footer + status bar */
.site-footer { margin-top: 18px; padding: 18px 0; border-top: 1px solid var(--line); }
.fine-print { color: var(--muted); font-size: 0.85rem; margin: 0; font-family: var(--font-mono); }
.fine-print a { color: var(--bright); }
.statusbar { position: fixed; left: 0; right: 0; bottom: 0; z-index: 30; background: color-mix(in srgb, var(--bg) 82%, black); border-top: 1px solid var(--border-hi); backdrop-filter: blur(8px); }
.statusbar-row { display: flex; align-items: center; gap: 12px; padding: 8px 0; font-family: var(--font-mono); font-size: 0.75rem; color: var(--muted); }
.sb-item { display: inline-flex; align-items: center; gap: 7px; white-space: nowrap; }
.sb-live { color: var(--bright); }
.sb-live .dot { width: 8px; height: 8px; border-radius: 50%; background: var(--bright); box-shadow: 0 0 8px var(--bright); animation: pulse 1.8s ease-in-out infinite; }
.sb-muted { color: var(--text-faint); }
.sb-clock { margin-left: auto; color: var(--text-dim); }

:target { scroll-margin-top: 88px; }
@media (prefers-reduced-motion: reduce) {
  .cursor, .boot::after, .tile h3 .tstat, .sb-live .dot { animation: none; }
  html { scroll-behavior: auto; }
}
@media (max-width: 820px) { .hero-grid { grid-template-columns: 1fr; gap: 24px; } }
@media (max-width: 640px) {
  .hero { padding: 56px 0 40px; }
  .header-row { flex-direction: column; align-items: flex-start; }
  .ghost-num { display: none; }
}
@media (max-width: 560px) { .sb-muted { display: none; } }
`;
}

export function buildScriptJs(cfg: SubsiteConfig): string {
  return `// ${cfg.title} — dyuhaus.com sub-site (terminal house style). Self-contained, no deps.
(function () {
  "use strict";
  var reduce = !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);

  // live status-bar clock
  var clock = document.getElementById("sb-clock");
  if (clock) {
    var pad = function (n) { return (n < 10 ? "0" : "") + n; };
    var tick = function () {
      var d = new Date();
      clock.textContent = pad(d.getHours()) + ":" + pad(d.getMinutes()) + ":" + pad(d.getSeconds());
    };
    tick();
    setInterval(tick, 1000);
  }

  // hero boot-log typewriter (replayable via the [replay] button)
  var boot = document.getElementById("boot");
  if (boot) {
    var raw = boot.getAttribute("data-lines") || "";
    var lines = raw ? raw.split("|") : [];
    var timer = null;
    var runBoot = function () {
      if (timer) { clearTimeout(timer); timer = null; }
      if (!lines.length) return;
      if (reduce) { boot.textContent = lines.join("\\n"); return; }
      boot.textContent = "";
      var li = 0, ci = 0;
      var step = function () {
        if (li >= lines.length) { timer = null; return; }
        var head = lines.slice(0, li).join("\\n");
        var cur = lines[li];
        if (ci <= cur.length) {
          boot.textContent = head + (li ? "\\n" : "") + cur.slice(0, ci);
          ci++;
          timer = setTimeout(step, 18 + Math.floor(Math.random() * 22));
        } else {
          li++; ci = 0;
          timer = setTimeout(step, 260);
        }
      };
      timer = setTimeout(step, 400);
    };
    runBoot();
    var replay = document.getElementById("replay");
    if (replay) replay.addEventListener("click", runBoot);
  }
})();
`;
}

export function buildRobots(cfg: SubsiteConfig): string {
  return `User-agent: *
Allow: /

Sitemap: https://${cfg.subdomain}/sitemap.xml
`;
}

/* --------------------------------------------------------------------------
 * Portable artifact
 * ------------------------------------------------------------------------ */

export function buildManifest(cfg: SubsiteConfig): Record<string, unknown> {
  const t = themeFor(cfg);
  const pages = pageList(cfg);
  return {
    schema: "dyuhaus.subsite-artifact/v1",
    generatedAt: cfg.createdAt,
    generatedBy: "pi extension: subsite-scaffold",
    site: {
      slug: cfg.slug,
      subdomain: cfg.subdomain,
      title: cfg.title,
      description: cfg.description,
      pathRoute: cfg.routeAsPath ? `/${cfg.slug}/` : null,
    },
    brand: {
      key: t.key,
      name: t.name,
      full: t.full,
      tagline: cfg.tagline || t.tagline,
      source: t.key === "ihtc" ? "/home/dyadmin/brand/ihtc/BRAND-PROFILE.md" : null,
      voice: t.voice,
    },
    design: {
      style: "dyuhaus-terminal-house-style",
      fonts: { display: t.fontDisplay, body: t.fontSans, mono: t.fontMono },
      fontsHref: HOUSE_FONTS_HREF,
      tokens: t.tokens,
    },
    pages: pages.map((p) => ({ file: p.file, label: p.label, isIndex: p.isIndex })),
    hosting: {
      mode: cfg.mode,
      servedFrom:
        cfg.mode === "tunnel"
          ? `cloudflared tunnel -> http://localhost:${cfg.port} (origin: ops/static-server.cjs, STATIC_ROOT=${cfg.slug})`
          : cfg.mode === "service"
            ? `cloudflared tunnel -> http://localhost:${cfg.port}`
            : "Hostinger repo root, routed by .htaccess into the folder",
      port: cfg.mode === "static" ? null : cfg.port ?? null,
      staticOrigin:
        cfg.mode === "tunnel"
          ? { server: "ops/static-server.cjs", staticRoot: cfg.slug, nssmService: `dy-${cfg.slug}-static` }
          : null,
      immutableAssets: cfg.immutableAssets,
      repo: "git@github.com:dyuhaus/dyuhaus.com.git",
      deployBranch: "main",
    },
    files: {
      subsiteDir: `${cfg.slug}/`,
      entry: `${cfg.slug}/index.html`,
      styles: `${cfg.slug}/styles.css`,
      script: `${cfg.slug}/script.js`,
    },
    wiring: {
      htaccessRewrite: cfg.mode === "static" || cfg.mode === "tunnel",
      htaccessCacheRevalidate: (cfg.mode === "static" || cfg.mode === "tunnel") && !cfg.immutableAssets,
      readmeDomainRow: true,
      tunnelIngress: cfg.mode === "service" || cfg.mode === "tunnel",
    },
  };
}

export function buildTokensJson(cfg: SubsiteConfig): string {
  return JSON.stringify(buildManifest(cfg), null, 2) + "\n";
}

export function buildBrief(cfg: SubsiteConfig): string {
  const t = themeFor(cfg);
  const k = t.tokens;
  const voiceDo = t.voice.do.length ? t.voice.do.map((s) => `  - ${s}`).join("\n") : "  - (no brand voice constraints)";
  const voiceDont = t.voice.dont.length ? t.voice.dont.map((s) => `  - ${s}`).join("\n") : "  - (none)";
  const pages = pageList(cfg)
    .map((p) => `  - \`${p.file}\` — ${p.label}${p.isIndex ? " (landing page)" : ""}`)
    .join("\n");

  return `# Design brief — ${cfg.title}

**Subdomain:** \`${cfg.subdomain}\`${cfg.routeAsPath ? ` (also \`dyuhaus.com/${cfg.slug}/\`)` : ""}
**Brand:** ${t.full}${t.tagline ? ` — _${cfg.tagline || t.tagline}_` : ""}
**Hosting:** ${
    cfg.mode === "tunnel"
      ? `Static files served by \`ops/static-server.cjs\` on \`localhost:${cfg.port}\`, fronted by the Cloudflare tunnel (\`.htaccess\` fallback on Hostinger).`
      : cfg.mode === "service"
        ? `Service on \`localhost:${cfg.port}\` fronted by the Cloudflare tunnel.`
        : "Static, served from the dyuhaus.com repo via `.htaccess` on Hostinger."
  }
**Generated:** ${cfg.createdAt}

> This artifact is the portable spec for the sub-site. It is meant to be carried
> **off this headless Linux box** to a machine with a browser / design tooling,
> where you generate the real UI, then drop the result back into \`${cfg.slug}/\`
> in the dyuhaus.com repo and push. Hostinger auto-pulls \`main\`.

## What already exists in the repo

- \`${cfg.slug}/\` folder with a working skeleton (\`index.html\`, \`styles.css\`, \`script.js\`, \`assets/\`).
- Routing wired (${
    cfg.mode === "tunnel"
      ? "Cloudflare tunnel ingress + `.htaccess` fallback"
      : cfg.mode === "service"
        ? "Cloudflare tunnel ingress"
        : "`.htaccess` rewrite"
  }) and a row in the repo \`README.md\` Domains table.
- These design tokens baked into \`styles.css\` (and shipped standalone as \`tokens.css\`).

## Purpose

${cfg.description}

## Pages to design

${pages}

## Palette

| Token | Value | Use |
|-------|-------|-----|
| Background | \`${k.bg}\` | Page background |
| Panel | \`${k.panel}\` | Cards / elevated surfaces |
| Text | \`${k.text}\` | Primary text |
| Muted | \`${k.muted}\` | Secondary text |
| Accent | \`${k.accent}\` | Primary CTA / highlight |
| Accent dark | \`${k.accentDark}\` | Hover / depth |
| Accent 2 | \`${k.accent2}\` | Success / secondary accent |
| Bright | \`${k.bright}\` | Digital pop / code |

- **Radius:** ${k.radius} standard, ${k.radiusLg} large
- **Container max width:** ${k.container}
- **Shadow:** \`${k.shadow}\`
- **Type (dyuhaus house style):** display \`Space Grotesk\`, body \`Inter\`, mono \`JetBrains Mono\` — loaded via Google Fonts.

## House style — dyuhaus.com terminal

All \`*.dyuhaus.com\` sub-sites share one **terminal / developer** aesthetic on a
dark charcoal field (see BRAND-PROFILE.md -> "Website House Style"). Match it:

- **Window chrome**: a red/silver/green three-dot cluster on the header and
  panels; a fixed bottom **status bar** (\`LIVE · <domain> · live clock\`).
- **Prompts**: section headers read \`~/path $ command\` (path in the bright
  accent, \`$\` in red); mono \`//\` micro-labels; \`>\`-prefixed card headers with a
  pulsing "running" dot; large faint **ghost section numbers**.
- **Actions** are bracketed: \`[ do the thing ]\`; links underline in the accent.
- Ambient motion: blinking cursor, a replayable **boot-log typewriter** in the
  hero, pulsing dots. **Honor \`prefers-reduced-motion\`.**
- The shipped \`styles.css\` already implements this from \`tokens.css\`; keep those
  classes and behaviors when you regenerate the UI.

## Voice & tone

Do say:
${voiceDo}

Do not say:
${voiceDont}

## Constraints (keep the static sub-site pattern)

- **Self-contained:** local HTML/CSS/JS + \`assets/\` only. No build step and no
  CDN **JavaScript**. The house fonts (Space Grotesk / Inter / JetBrains Mono)
  load from Google Fonts — the only allowed external dependency.
- Keep the CSP meta (\`default-src 'self'\`, with \`style-src\`/\`font-src\` for Google
  Fonts as in the skeleton); avoid inline \`<script>\`.
- Reference styles with a relative path (\`styles.css\`), not an absolute one, so
  both subdomain and path routing work.
- ${cfg.immutableAssets ? "Hashed asset filenames (immutable caching)." : "Plain asset filenames — the repo `.htaccess` marks this folder revalidate-on-load."}
${
  cfg.brand === "ihtc"
    ? "- Use the canonical IHTC logo `/home/dyadmin/brand/ihtc/logo/IHTC_logo.png`; do not recreate the mark.\n"
    : ""
}
## How to generate the UI off-box

1. Copy this artifact folder (or the whole repo) to a machine with a browser.
2. Feed \`PROMPT.md\` + \`site.manifest.json\` + \`tokens.css\` to your UI generator
   (v0, Cursor, Figma-to-code, a local browser preview, etc.).
3. Produce final \`index.html\`${cfg.pages.length ? " and the other pages listed above" : ""} plus assets.
4. Replace the skeleton files in \`${cfg.slug}/\` with the generated output.
5. Verify locally in a browser, commit, and push \`main\`.

## Deploy checklist

- [ ] DNS: route \`${cfg.subdomain}\` to the tunnel: \`cloudflared tunnel route dns <tunnel-id> ${cfg.subdomain}\`.
${
  cfg.mode === "tunnel"
    ? `- [ ] Ops: add an NSSM static-origin service \`dy-${cfg.slug}-static\` in \`ops/setup-services.ps1\` running \`ops/static-server.cjs\` with \`PORT=${cfg.port}\` and \`STATIC_ROOT=<repo>\\\\${cfg.slug}\`, then re-run the script.\n- [ ] Tunnel: confirm the \`${cfg.subdomain}\` ingress entry in \`tunnel/config.yml\` (\`-> http://localhost:${cfg.port}\`) and restart cloudflared.\n`
    : cfg.mode === "service"
      ? `- [ ] Tunnel: confirm the \`${cfg.subdomain}\` ingress entry and run the local service on \`:${cfg.port}\`.\n`
      : `- [ ] Hostinger: point \`${cfg.subdomain}\` at the same document root as dyuhaus.com (the \`.htaccess\` rewrite does the rest).\n`
}- [ ] Commit + push \`main\`; confirm Hostinger auto-pull picked it up.
- [ ] Load \`https://${cfg.subdomain}\` and check styles, links, and CSP (no console errors).
`;
}

export function buildPrompt(cfg: SubsiteConfig): string {
  const t = themeFor(cfg);
  const k = t.tokens;
  return `# Generation prompt — ${cfg.title}

Paste this into your UI/codegen tool on a machine with a browser. Attach
\`tokens.css\` and \`site.manifest.json\` from this artifact folder.

---

Build a self-contained static website for **${cfg.subdomain}**.

Purpose: ${cfg.description}

Brand: ${t.full}${t.tagline ? ` (${cfg.tagline || t.tagline})` : ""}. Voice: ${
    t.voice.do.length ? t.voice.do.join(" ") : "clean, direct, practical"
  } Avoid hype words${t.voice.dont.length ? ` such as: ${t.voice.dont.join("; ")}` : ""}.

Design system — the dyuhaus.com **terminal house style** (use exactly, from tokens.css):
- Dark charcoal field ${k.bg}, panels ${k.panel}, text ${k.text}, muted ${k.muted}.
- Bright terminal accent ${k.bright} (prompts, cursor, links, live status); rules/success ${k.accent2}; attention/red ${k.accent} (hover ${k.accentDark}).
- Radius ${k.radius}/${k.radiusLg}, container ${k.container}, shadow "${k.shadow}".
- Type: display "Space Grotesk", body "Inter", mono "JetBrains Mono" (Google Fonts).

Match the house style (the included styles.css already implements it):
- Terminal window chrome (red/silver/green dots); a fixed bottom status bar with a live clock.
- Section headers as shell prompts (~/path $ command); mono // labels; >-prefixed cards with a pulsing dot; big faint ghost section numbers; bracketed [ actions ].
- Ambient motion: blinking cursor, a replayable hero boot-log typewriter, pulsing dots — all honoring prefers-reduced-motion.

Pages: ${pageList(cfg)
    .map((p) => p.file)
    .join(", ")}.

Hard requirements:
- Output plain HTML/CSS/JS with NO build step and NO external JavaScript/CDN.
  The house fonts load from Google Fonts via <link> — that is the only allowed external.
- Keep a Content-Security-Policy meta: default-src 'self'; script-src 'self';
  style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src https://fonts.gstatic.com.
- Reference CSS/JS with RELATIVE paths so the page works under both
  https://${cfg.subdomain} and https://dyuhaus.com/${cfg.slug}/.
- Fully responsive, accessible (semantic landmarks, focus states, alt text).
${cfg.brand === "ihtc" ? "- Use the IHTC house logo; do not invent a new mark.\n" : ""}
Deliver the complete files ready to drop into the ${cfg.slug}/ folder.
`;
}

export function buildArtifactReadme(cfg: SubsiteConfig): string {
  return `# Artifact — ${cfg.title} (\`${cfg.subdomain}\`)

Portable spec for a dyuhaus.com sub-site, generated by the \`subsite-scaffold\`
pi extension. This folder is **blocked from the public web** by the repo
\`.htaccess\` (it lives under \`subsite-artifacts/\`).

## Why this exists

This box is headless (no browser / design GUI). The scaffolder creates a working
skeleton in \`${cfg.slug}/\` and wires up routing, but the real visual design is
meant to be generated elsewhere. This artifact is everything a downstream tool
needs to do that, independent of this machine.

## Contents

| File | Use |
|------|-----|
| \`site.manifest.json\` | Machine-readable spec (routing, brand, tokens, pages, hosting). |
| \`BRIEF.md\` | Human/LLM design brief + deploy checklist. |
| \`tokens.css\` | Portable CSS variables (drop-in). |
| \`PROMPT.md\` | Ready-to-paste generation prompt. |

## Workflow

1. Copy this folder to a machine with a browser.
2. Generate the UI from \`PROMPT.md\` + \`site.manifest.json\` + \`tokens.css\`.
3. Put the generated files into \`${cfg.slug}/\` in the dyuhaus.com repo.
4. Commit + push \`main\`. Hostinger auto-pulls.
`;
}
