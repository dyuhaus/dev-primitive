// Pure logic for the sub-site scaffolder: no pi / typebox imports, only node
// builtins + templates. Kept separate so it can be unit-tested with plain node
// (`node --experimental-strip-types`) on a headless box.

import { promises as fs } from "node:fs";
import { existsSync } from "node:fs";
import * as path from "node:path";
import { execFile } from "node:child_process";
import { createHash, randomUUID } from "node:crypto";
import { promisify } from "node:util";

import {
  type SubsiteConfig,
  type BrandKey,
  type SiteTheme,
  type SiteMode,
  SITE_THEME_KEYS,
  buildRobots,
  buildTokensJson,
  buildArtifactTokensCss,
  buildBrief,
  buildPrompt,
  buildArtifactReadme,
  applyCanonicalIhtcTokens,
  pageList,
  themeFor,
  slugRegex,
} from "./templates";

export { applyCanonicalIhtcTokens };

const execFileAsync = promisify(execFile);

export const DEFAULT_REPO = "/home/dyadmin/githubStaging/dyuhaus.com";
export const ARTIFACT_ROOT = "subsite-artifacts";
export const COMPLETION_FILE = "scaffold.complete.json";
export const TRANSFER_DIR = "/home/dyadmin/transfer";

// Exact pre-v2 manifests that may reuse their historical theme without
// prompting. Pinning the content prevents an unknown slug from downgrading its
// schema and masquerading as a legacy site.
const TRUSTED_LEGACY_MANIFESTS: Readonly<Record<string, string>> = {
  jobs: "d6c1a47760876ab3260048335a9637d398ae2dd3126558fec3b0e4db7c1296da",
};

// Live public-exposure path: the homelab Docker Compose stack + its cloudflared
// ingress. Static sub-sites run as nginx containers reached by service name;
// Cloudflare DNS routes the hostname to the tunnel. (The dyuhaus.com repo's
// tunnel/config.yml + ops/*.ps1 describe the retired Windows host and are NOT
// the live path.) All overridable by env for other hosts.
export const HOMELAB_COMPOSE =
  process.env.DYUHAUS_COMPOSE_FILE || "/home/dyadmin/homelab/compose/apps/docker-compose.yml";
export const HOMELAB_CLOUDFLARED =
  process.env.DYUHAUS_CLOUDFLARED_FILE || "/home/dyadmin/homelab/compose/apps/cloudflared.yml";
export const TUNNEL_ID = process.env.DYUHAUS_TUNNEL_ID || "1f32fde8-8bbf-4f2c-b4e7-0d915fee44f1";
export const TAILSCALE_IP = process.env.DYUHAUS_TAILSCALE_IP || "100.108.125.82";
export const COMPOSE_PORT_BASE = 8786;

export interface PlannedFile {
  path: string; // repo-relative
  kind: "claim" | "create" | "verify" | "patch" | "complete" | "skip";
  note: string;
  contents?: string;
}

export interface RawInput {
  slug: string;
  title?: string;
  description?: string;
  theme?: SiteTheme;
  brand?: BrandKey;
  mode?: SiteMode;
  port?: number;
  routeAsPath?: boolean;
  immutableAssets?: boolean;
  pages?: string[];
  tagline?: string;
}

// Supported entrypoints add this marker after a local interactive choice, or
// while reusing an existing manifest. It guards API misuse; the machine
// contract remains authoritative for direct shell and source-level actions.
const THEME_AUTHORIZED: unique symbol = Symbol("theme-authorized");
type AuthorizedRawInput = RawInput & {
  [THEME_AUTHORIZED]: { confirmedByUser: boolean };
};

export function withConfirmedTheme(raw: RawInput, theme: SiteTheme): AuthorizedRawInput {
  return { ...raw, theme, [THEME_AUTHORIZED]: { confirmedByUser: true } };
}

function withExistingTheme(raw: RawInput, theme: SiteTheme, confirmedByUser: boolean): AuthorizedRawInput {
  return { ...raw, theme, [THEME_AUTHORIZED]: { confirmedByUser } };
}

export function isSiteRepo(dir: string): boolean {
  return (
    !!dir &&
    existsSync(path.join(dir, ".htaccess")) &&
    existsSync(path.join(dir, "README.md")) &&
    existsSync(path.join(dir, "index.html"))
  );
}

export function resolveRepo(cwd: string, explicit?: string): string {
  const candidates: string[] = [];
  if (explicit) candidates.push(explicit);
  if (process.env.DYUHAUS_SITE_REPO) candidates.push(process.env.DYUHAUS_SITE_REPO);
  let d = cwd;
  for (let i = 0; i < 8 && d; i++) {
    candidates.push(d);
    const parent = path.dirname(d);
    if (parent === d) break;
    d = parent;
  }
  candidates.push(DEFAULT_REPO);
  for (const c of candidates) {
    if (c && isSiteRepo(c)) return c;
  }
  return DEFAULT_REPO;
}

export function normalizeSlug(raw: string): string {
  return (raw || "")
    .trim()
    .toLowerCase()
    .replace(/\.dyuhaus\.com.*$/i, "")
    .replace(/[^a-z0-9-]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

export function validSlug(slug: string): boolean {
  return /^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$/.test(slug);
}

export const RESERVED = new Set([
  "assets",
  "ops",
  "tunnel",
  "website",
  "node_modules",
  ARTIFACT_ROOT,
]);

export function defaultTitle(slug: string, brand: BrandKey): string {
  const nice = slug
    .split("-")
    .map((w) => (w ? w[0].toUpperCase() + w.slice(1) : w))
    .join(" ");
  return brand === "ihtc" ? `${nice} · IHTC` : nice;
}

export function buildConfig(raw: RawInput): { cfg?: SubsiteConfig; error?: string } {
  const slug = normalizeSlug(raw.slug || "");
  if (!slug) return { error: "A slug/subdomain name is required." };
  if (!validSlug(slug)) return { error: `Invalid slug "${slug}". Use lowercase letters, numbers, and hyphens.` };
  if (RESERVED.has(slug)) return { error: `"${slug}" is a reserved folder name.` };
  if (!raw.theme || !SITE_THEME_KEYS.includes(raw.theme)) {
    return {
      error:
        "A site theme is required. Ask David to choose Literary, Noir, Science Fiction, High Fantasy, Horror, Poetry, Correspondence, or IHTC.",
    };
  }
  const themeAuthorization = (raw as AuthorizedRawInput)[THEME_AUTHORIZED];
  if (!themeAuthorization) {
    return { error: "Theme confirmation is required. Wait for David to choose or confirm the theme before continuing." };
  }
  const mode: SiteMode = raw.mode ?? "tunnel";
  if (mode === "service" && !raw.port) return { error: "Service mode requires a port for the tunnel ingress." };
  const brand: BrandKey = raw.brand ?? "ihtc";
  const title = (raw.title && raw.title.trim()) || defaultTitle(slug, brand);
  const description = (raw.description && raw.description.trim()) || `${title} — a dyuhaus.com sub-site.`;
  const cfg: SubsiteConfig = {
    slug,
    subdomain: `${slug}.dyuhaus.com`,
    title,
    description,
    theme: raw.theme,
    themeConfirmedByUser: themeAuthorization.confirmedByUser,
    brand,
    mode,
    port: raw.port,
    routeAsPath: raw.routeAsPath ?? false,
    immutableAssets: raw.immutableAssets ?? false,
    pages: (raw.pages ?? []).map((p) => normalizeSlug(p)).filter(Boolean),
    tagline: raw.tagline,
    createdAt: new Date().toISOString(),
  };
  return { cfg };
}

/* -------------------------------------------------------- wiring patchers */
// Each returns new content, or null when no change is needed (idempotent).

export function patchHtaccessRewrite(content: string, cfg: SubsiteConfig): string | null {
  const rx = slugRegex(cfg.slug);
  if (content.includes(`/${cfg.slug}/$1 [L]`) || content.includes(`^${rx}\\.dyuhaus`)) return null;
  const block =
    `\n# ${cfg.slug} — static sub-site served from /${cfg.slug}/\n` +
    `RewriteCond %{HTTP_HOST} ^${rx}\\.dyuhaus\\.com(:[0-9]+)?$ [NC]\n` +
    `RewriteCond %{REQUEST_URI} !^/${cfg.slug}/\n` +
    `RewriteRule ^(.*)$ /${cfg.slug}/$1 [L]\n\n`;
  const anchor = "RewriteEngine On\n";
  const idx = content.indexOf(anchor);
  const next = idx === -1 ? content + block : content.slice(0, idx + anchor.length) + block + content.slice(idx + anchor.length);
  // Collapse any run of blank lines to a single blank line (stacked inserts).
  return next.replace(/\n{3,}/g, "\n\n");
}

export function patchHtaccessCache(content: string, cfg: SubsiteConfig): string | null {
  if (cfg.immutableAssets) return null;
  const rx = slugRegex(cfg.slug);
  const hostLine = `SetEnvIf Host "^${rx}\\.dyuhaus\\.com(:[0-9]+)?$" no_immutable_assets`;
  if (content.includes(hostLine)) return null;
  const uriLine = `SetEnvIf Request_URI "^/${cfg.slug}/" no_immutable_assets`;
  const addition = `${hostLine}\n${uriLine}\n`;
  const anchor = '<FilesMatch "\\.(html|js|css|svg|png)$">';
  const idx = content.indexOf(anchor);
  if (idx === -1) return null;
  return content.slice(0, idx) + addition + content.slice(idx);
}

export function patchHtaccessBlockArtifacts(content: string): string | null {
  const marker = "RedirectMatch 404 ^/(";
  const idx = content.indexOf(marker);
  if (idx === -1) return null;
  const lineEnd = content.indexOf("\n", idx);
  const end = lineEnd === -1 ? content.length : lineEnd;
  const line = content.slice(idx, end);
  if (line.includes(ARTIFACT_ROOT)) return null;
  const patchedLine = line.replace(")(/|$)", `|${ARTIFACT_ROOT})(/|$)`);
  if (patchedLine === line) return null;
  return content.slice(0, idx) + patchedLine + content.slice(end);
}

export function patchReadmeRow(content: string, cfg: SubsiteConfig): string | null {
  if (content.includes(cfg.subdomain)) return null;
  const served =
    cfg.mode === "tunnel"
      ? `Static \`${cfg.slug}/\` via cloudflared → \`:${cfg.port}\` (origin: \`ops/static-server.cjs\`; \`.htaccess\` fallback).`
      : cfg.mode === "service"
        ? `Service via cloudflared → \`:${cfg.port}\`.`
        : cfg.routeAsPath
          ? `Static site from this repo's \`${cfg.slug}/\` folder; also at \`/${cfg.slug}/\`, routed by \`.htaccess\`.`
          : `Static site from this repo's \`${cfg.slug}/\` folder, routed by \`.htaccess\`.`;
  const row = `| \`${cfg.subdomain}\`     | ${served} |`;

  const lines = content.split("\n");
  const domIdx = lines.findIndex((l) => /^##\s+Domains/.test(l));
  if (domIdx === -1) return null;
  let sep = -1;
  for (let i = domIdx + 1; i < lines.length && i < domIdx + 8; i++) {
    if (/^\|\s*-{2,}/.test(lines[i])) {
      sep = i;
      break;
    }
  }
  if (sep === -1) return null;
  let last = sep;
  for (let i = sep + 1; i < lines.length; i++) {
    if (lines[i].startsWith("|")) last = i;
    else break;
  }
  lines.splice(last + 1, 0, row);
  return lines.join("\n");
}

/** compose service name for a static sub-site, e.g. labs -> labs-site */
export function composeService(cfg: SubsiteConfig): string {
  return cfg.mode === "service" ? cfg.slug : `${cfg.slug}-site`;
}

/** ingress target the tunnel routes to */
export function ingressTarget(cfg: SubsiteConfig): string {
  return cfg.mode === "service"
    ? `http://${cfg.slug}:${cfg.port}`
    : `http://${cfg.slug}-site:80`;
}

/** Add the `<hostname> -> <service>` ingress to the live cloudflared.yml. */
export function patchCloudflaredIngress(content: string, cfg: SubsiteConfig): string | null {
  if (content.includes(`hostname: ${cfg.subdomain}`)) return null;
  const entry = `  - hostname: ${cfg.subdomain}\n    service: ${ingressTarget(cfg)}\n`;
  const anchor = "  - service: http_status:404";
  const idx = content.indexOf(anchor);
  if (idx === -1) return content.replace(/\n?$/, `\n${entry}`);
  return content.slice(0, idx) + entry + content.slice(idx);
}

/**
 * Add the `<hostname> -> http://localhost:<port>` ingress to the repo's
 * tunnel/config.yml (the sanitized record copy). Mirrors patchCloudflaredIngress
 * but uses a localhost origin. Idempotent; inserts before the catch-all 404.
 */
export function patchTunnelIngress(content: string, cfg: SubsiteConfig): string | null {
  if (content.includes(`hostname: ${cfg.subdomain}`)) return null;
  const entry = `  - hostname: ${cfg.subdomain}\n    service: http://localhost:${cfg.port}\n`;
  const anchor = "  - service: http_status:404";
  const idx = content.indexOf(anchor);
  if (idx === -1) return content.replace(/\n?$/, `\n${entry}`);
  return content.slice(0, idx) + entry + content.slice(idx);
}

/**
 * Add an nginx static-site service to the homelab docker-compose.yml and add it
 * to the cloudflared depends_on list. Idempotent. tunnel mode only.
 */
export function patchComposeService(content: string, cfg: SubsiteConfig): string | null {
  const svc = composeService(cfg);
  if (content.includes(`\n  ${svc}:\n`)) return null;
  const block =
    `\n  # ${cfg.subdomain} static sub-site (subsite-scaffold). Public via the tunnel.\n` +
    `  ${svc}:\n` +
    `    image: nginx:alpine\n` +
    `    restart: unless-stopped\n` +
    `    volumes:\n` +
    `      - ${DEFAULT_REPO}/${cfg.slug}:/usr/share/nginx/html:ro\n` +
    `    ports:\n` +
    `      - "127.0.0.1:${cfg.port}:80"\n` +
    `      - "${TAILSCALE_IP}:${cfg.port}:80"\n`;
  // Insert the service just before the cloudflared service block.
  const anchor = "\n  cloudflared:\n";
  const idx = content.indexOf(anchor);
  let next = idx === -1 ? content + block : content.slice(0, idx) + block + content.slice(idx);
  // Add to cloudflared depends_on (best-effort, idempotent).
  const dep = "    depends_on:\n";
  const di = next.indexOf(dep);
  if (di !== -1 && !next.includes(`      - ${svc}\n`)) {
    const at = di + dep.length;
    next = next.slice(0, at) + `      - ${svc}\n` + next.slice(at);
  }
  return next;
}

/* --------------------------------------------------------------- planning */

async function readIf(p: string): Promise<string | null> {
  try {
    return await fs.readFile(p, "utf8");
  } catch {
    return null;
  }
}

function sha256(text: string): string {
  return createHash("sha256").update(text).digest("hex");
}

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

async function readThemeScaffold(repo: string, cfg: SubsiteConfig): Promise<{
  index: string;
  styles: string;
  script: string;
  favicon: string | null;
}> {
  const themeDir = path.join(repo, "starter", cfg.theme);
  const [index, styles, script, favicon] = await Promise.all([
    readIf(path.join(themeDir, "index.html")),
    readIf(path.join(themeDir, "styles.css")),
    readIf(path.join(themeDir, "script.js")),
    readIf(path.join(themeDir, "favicon.svg")),
  ]);
  if (index === null || styles === null || script === null) {
    throw new Error(
      `Confirmed ${cfg.theme} theme is incomplete under "starter/${cfg.theme}"; restore its index.html, styles.css, and script.js before scaffolding.`,
    );
  }
  return {
    index,
    styles: cfg.theme === "ihtc" ? applyCanonicalIhtcTokens(styles) : styles,
    script,
    favicon,
  };
}

function customizeThemePage(
  source: string,
  cfg: SubsiteConfig,
  page: { file: string; label: string; isIndex: boolean },
): string {
  const title = page.isIndex ? cfg.title : `${page.label} · ${cfg.title}`;
  const extraNavigation = pageList(cfg)
    .filter((candidate) => candidate.file !== "index.html" || !page.isIndex)
    .map(
      (candidate) =>
        `<a href="${escapeHtml(candidate.file)}"${candidate.file === page.file ? ' aria-current="page"' : ""}>${escapeHtml(candidate.label)}</a>`,
    )
    .join("");
  let rendered = source
    .replace(/<title>[\s\S]*?<\/title>/i, () => `<title>${escapeHtml(title)}</title>`)
    .replace(
      /(<meta\s+name="description"\s+content=")[^"]*("\s*\/?>)/i,
      (_match, prefix: string, suffix: string) => `${prefix}${escapeHtml(cfg.description)}${suffix}`,
    )
    .replace(/href="\.\.\/"/g, 'href="https://starter.dyuhaus.com/"');
  rendered = rendered
    .replace(
      /(<meta\s+property="og:title"\s+content=")[^"]*("\s*\/?>)/i,
      (_match, prefix: string, suffix: string) => `${prefix}${escapeHtml(cfg.title)}${suffix}`,
    )
    .replace(
      /(<meta\s+property="og:description"\s+content=")[^"]*("\s*\/?>)/i,
      (_match, prefix: string, suffix: string) => `${prefix}${escapeHtml(cfg.description)}${suffix}`,
    );
  if (extraNavigation) {
    rendered = rendered.replace(
      /(<nav\b[^>]*>[\s\S]*?)(<\/nav>)/i,
      (_match, navigation: string, closingTag: string) => `${navigation}${extraNavigation}${closingTag}`,
    );
  }
  return rendered;
}

export async function buildCompletionRecord(cfg: SubsiteConfig): Promise<string> {
  const manifestSha256 = sha256(buildTokensJson(cfg));
  return JSON.stringify(
    {
      schema: "dyuhaus.subsite-completion/v1",
      slug: cfg.slug,
      manifestSha256,
      completedAt: cfg.createdAt,
    },
    null,
    2,
  ) + "\n";
}

export interface PersistedSiteConfig {
  exists: boolean;
  cfg?: SubsiteConfig;
  pendingCfg?: SubsiteConfig;
  error?: string;
}

/** Reconstruct immutable creation inputs for an existing scaffold. */
export async function readPersistedSiteConfig(repo: string, rawSlug: string): Promise<PersistedSiteConfig> {
  const slug = normalizeSlug(rawSlug);
  const siteEntryExists = !!slug && existsSync(path.join(repo, slug, "index.html"));
  const manifestPath = path.join(repo, ARTIFACT_ROOT, slug, "site.manifest.json");
  const completionPath = path.join(repo, ARTIFACT_ROOT, slug, COMPLETION_FILE);
  const manifestText = slug ? await readIf(manifestPath) : null;
  if (!siteEntryExists && manifestText === null) {
    if (existsSync(completionPath)) {
      return {
        exists: false,
        error: `Orphaned completion record for "${slug}" has no matching manifest or site entry page; refusing to scaffold over it.`,
      };
    }
    return { exists: false };
  }
  if (manifestText === null) {
    return {
      exists: siteEntryExists,
      error: `Existing site "${slug}" has no persisted scaffold configuration. Use the existing-site workflow instead.`,
    };
  }

  let manifest: any;
  try {
    manifest = JSON.parse(manifestText);
  } catch {
    return { exists: true, error: `Existing artifact for "${slug}" is unreadable; refusing to modify it.` };
  }

  const recordedSlug = typeof manifest?.site?.slug === "string" ? normalizeSlug(manifest.site.slug) : "";
  const recordedSubdomain = typeof manifest?.site?.subdomain === "string" ? manifest.site.subdomain : "";
  const recordedSiteDir = typeof manifest?.files?.subsiteDir === "string" ? manifest.files.subsiteDir : "";
  const recordedEntry = typeof manifest?.files?.entry === "string" ? manifest.files.entry : "";
  const recordedStyles = typeof manifest?.files?.styles === "string" ? manifest.files.styles : "";
  const recordedScript = typeof manifest?.files?.script === "string" ? manifest.files.script : "";
  if (
    recordedSlug !== slug ||
    recordedSubdomain !== `${slug}.dyuhaus.com` ||
    (recordedSiteDir && recordedSiteDir !== `${slug}/`) ||
    (recordedEntry && recordedEntry !== `${slug}/index.html`) ||
    (recordedStyles && recordedStyles !== `${slug}/styles.css`) ||
    (recordedScript && recordedScript !== `${slug}/script.js`)
  ) {
    return {
      exists: siteEntryExists,
      error: `Existing artifact for "${slug}" identifies a different site; refusing to reuse its settings.`,
    };
  }

  const recordedTheme = manifest?.design?.template?.key;
  const legacyIhtc = !recordedTheme && manifest?.design?.style === "dyuhaus-terminal-house-style";
  const theme = SITE_THEME_KEYS.includes(recordedTheme as SiteTheme)
    ? (recordedTheme as SiteTheme)
    : legacyIhtc
      ? "ihtc"
      : undefined;
  if (!theme) {
    return { exists: siteEntryExists, error: `Existing artifact for "${slug}" has no reusable template theme.` };
  }

  const confirmedByUser = manifest?.design?.template?.confirmedByUser === true;
  const trustedLegacy = legacyIhtc && TRUSTED_LEGACY_MANIFESTS[slug] === sha256(manifestText);
  const currentManifest =
    manifest?.schema === "dyuhaus.subsite-artifact/v2" &&
    manifest?.generatedBy === "pi extension: subsite-scaffold" &&
    !legacyIhtc;
  if (currentManifest && !confirmedByUser) {
    return { exists: false, error: `Current artifact for "${slug}" has no recorded user theme confirmation.` };
  }
  if (!currentManifest && !trustedLegacy) {
    return {
      exists: false,
      error: `Artifact "${slug}" is neither a current scaffold nor a pinned legacy scaffold.`,
    };
  }
  if (trustedLegacy && !siteEntryExists) {
    return {
      exists: false,
      error: `Legacy artifact "${slug}" has no matching existing site entry page.`,
    };
  }

  const brand = ["ihtc", "personal", "none"].includes(manifest?.brand?.key)
    ? (manifest.brand.key as BrandKey)
    : "ihtc";
  const mode = ["tunnel", "static", "service"].includes(manifest?.hosting?.mode)
    ? (manifest.hosting.mode as SiteMode)
    : "static";
  const pages = Array.isArray(manifest?.pages)
    ? manifest.pages
        .map((page: any) => (typeof page?.file === "string" ? page.file.replace(/\.html$/i, "") : ""))
        .filter((page: string) => page && page !== "index")
    : [];
  const raw = withExistingTheme(
    {
      slug,
      title: typeof manifest?.site?.title === "string" ? manifest.site.title : undefined,
      description: typeof manifest?.site?.description === "string" ? manifest.site.description : undefined,
      brand,
      mode,
      port: typeof manifest?.hosting?.port === "number" ? manifest.hosting.port : undefined,
      routeAsPath: !!manifest?.site?.pathRoute,
      immutableAssets: manifest?.hosting?.immutableAssets === true,
      pages,
      tagline: typeof manifest?.brand?.tagline === "string" ? manifest.brand.tagline : undefined,
    },
    theme,
    confirmedByUser,
  );
  const built = buildConfig(raw);
  if (!built.cfg) return { exists: true, error: built.error };
  if (typeof manifest?.generatedAt === "string") built.cfg.createdAt = manifest.generatedAt;
  if (trustedLegacy) return { exists: true, cfg: built.cfg };

  const completionText = await readIf(completionPath);
  if (completionText === null) {
    if (existsSync(completionPath)) {
      return { exists: false, error: `Completion record for "${slug}" is unreadable; refusing to reuse it.` };
    }
    // A directory is not proof of completion. Until this marker is published
    // last, even a partially written site returns through the local selector.
    return { exists: false, pendingCfg: built.cfg };
  }
  let completion: any;
  try {
    completion = JSON.parse(completionText);
  } catch {
    return { exists: false, error: `Completion record for "${slug}" is unreadable; refusing to reuse it.` };
  }
  if (
    completion?.schema !== "dyuhaus.subsite-completion/v1" ||
    completion?.slug !== slug ||
    completion?.manifestSha256 !== sha256(manifestText) ||
    completion?.completedAt !== manifest?.generatedAt
  ) {
    return { exists: false, error: `Completion record for "${slug}" does not match its manifest.` };
  }
  // A valid marker remains reusable if the generated site directory is later
  // removed intentionally for create-only regeneration.
  return { exists: true, cfg: built.cfg };
}

function persistedDifference(recorded: SubsiteConfig, requested: SubsiteConfig): string | null {
  const comparisons: [string, unknown, unknown][] = [
    ["title", recorded.title, requested.title],
    ["description", recorded.description, requested.description],
    ["tagline", recorded.tagline || themeFor(recorded).tagline, requested.tagline || themeFor(requested).tagline],
    ["theme", recorded.theme, requested.theme],
    ["brand", recorded.brand, requested.brand],
    ["mode", recorded.mode, requested.mode],
    ["port", recorded.port ?? null, requested.port ?? null],
    ["path routing", recorded.routeAsPath, requested.routeAsPath],
    ["asset caching", recorded.immutableAssets, requested.immutableAssets],
    ["pages", JSON.stringify(recorded.pages), JSON.stringify(requested.pages)],
    ["creation timestamp", recorded.createdAt, requested.createdAt],
  ];
  return comparisons.find(([, a, b]) => a !== b)?.[0] ?? null;
}

/** Next free host port at/above `base` not already published in the compose file. */
export function nextFreeComposePort(composeContent: string, base = COMPOSE_PORT_BASE): number {
  const used = new Set<number>();
  for (const m of composeContent.matchAll(/:(\d+):\d+"/g)) used.add(Number(m[1]));
  let port = base;
  while (used.has(port)) port++;
  return port;
}

/**
 * Resolve cfg.port for tunnel/service modes before templates are rendered.
 * service keeps its explicit port; tunnel auto-assigns from tunnel/config.yml.
 * Mutates and returns cfg.
 */
export async function resolvePort(_repo: string, cfg: SubsiteConfig): Promise<SubsiteConfig> {
  if (cfg.mode === "static" || cfg.port) return cfg;
  // tunnel: assign a free host validation port from the homelab compose file.
  const compose = await readIf(HOMELAB_COMPOSE);
  cfg.port = compose !== null ? nextFreeComposePort(compose) : COMPOSE_PORT_BASE;
  return cfg;
}

export async function plan(repo: string, cfg: SubsiteConfig, emitArtifact: boolean): Promise<PlannedFile[]> {
  const out: PlannedFile[] = [];
  const persisted = await readPersistedSiteConfig(repo, cfg.slug);
  if (persisted.error) throw new Error(persisted.error);
  const recorded = persisted.exists ? persisted.cfg : persisted.pendingCfg;
  if (persisted.exists && !recorded) {
    throw new Error(`Existing site "${cfg.slug}" has no reusable persisted configuration.`);
  }
  if (recorded) {
    const difference = persistedDifference(recorded, cfg);
    if (difference) {
      throw new Error(`Site "${cfg.slug}" has different persisted ${difference}; use the existing-site workflow.`);
    }
  }
  await resolvePort(repo, cfg);
  const isNew = !persisted.exists && !persisted.pendingCfg;
  const isPending = !persisted.exists && !!persisted.pendingCfg;
  const themeScaffold = await readThemeScaffold(repo, cfg);
  if (isNew) {
    out.push({
      path: path.join(ARTIFACT_ROOT, cfg.slug, "site.manifest.json"),
      kind: "claim",
      note: "atomically persist the confirmed site identity",
      contents: buildTokensJson(cfg),
    });
  }
  const siteDir = cfg.slug;

  const addCreate = async (relativePath: string, note: string, contents: string) => {
    const full = path.join(repo, relativePath);
    if (!existsSync(full)) {
      out.push({ path: relativePath, kind: "create", note, contents });
      return;
    }
    if ((isNew || isPending) && (await readIf(full)) !== contents) {
      throw new Error(
        `${isNew ? "Pre-existing" : "Interrupted scaffold"} file "${relativePath}" differs from the confirmed site identity; use the existing-site workflow.`,
      );
    }
    out.push({
      path: relativePath,
      kind: isNew || isPending ? "verify" : "skip",
      note: isNew ? "verified pre-existing file" : isPending ? "verified interrupted write" : "exists",
      contents,
    });
  };

  for (const p of pageList(cfg)) {
    await addCreate(
      path.join(siteDir, p.file),
      p.isIndex ? `landing page copied from the confirmed ${cfg.theme} theme` : `extra page using the confirmed ${cfg.theme} theme`,
      customizeThemePage(themeScaffold.index, cfg, p),
    );
  }
  await addCreate(path.join(siteDir, "styles.css"), `confirmed ${cfg.theme} theme styles`, themeScaffold.styles);
  await addCreate(path.join(siteDir, "script.js"), `confirmed ${cfg.theme} theme behavior`, themeScaffold.script);
  await addCreate(path.join(siteDir, "robots.txt"), "robots", buildRobots(cfg));
  await addCreate(path.join(siteDir, "assets", ".gitkeep"), "assets dir", "");
  if (themeScaffold.favicon !== null) {
    await addCreate(path.join(siteDir, "favicon.svg"), `confirmed ${cfg.theme} theme favicon`, themeScaffold.favicon);
  }

  if (emitArtifact) {
    const aDir = path.join(ARTIFACT_ROOT, cfg.slug);
    const artifactFiles: [string, string][] = [
      ["site.manifest.json", buildTokensJson(cfg)],
      ["tokens.css", buildArtifactTokensCss(cfg)],
      ["BRIEF.md", buildBrief(cfg)],
      ["PROMPT.md", buildPrompt(cfg)],
      ["README.md", buildArtifactReadme(cfg)],
    ];
    for (const [name, body] of artifactFiles) {
      if (isNew && name === "site.manifest.json") continue;
      await addCreate(path.join(aDir, name), "artifact", body);
    }
  }

  const htaccess = await readIf(path.join(repo, ".htaccess"));
  if (htaccess !== null) {
    let current = htaccess;
    if (cfg.mode === "static" || cfg.mode === "tunnel") {
      const p1 = patchHtaccessRewrite(current, cfg);
      out.push({
        path: ".htaccess",
        kind: p1 ? "patch" : "skip",
        note: p1 ? "add subdomain rewrite" : "rewrite already present",
        contents: p1 ?? undefined,
      });
      if (p1) current = p1;
      const p2 = patchHtaccessCache(current, cfg);
      if (p2) {
        out.push({ path: ".htaccess", kind: "patch", note: "add cache-revalidate", contents: p2 });
        current = p2;
      }
    }
    if (emitArtifact) {
      const p3 = patchHtaccessBlockArtifacts(current);
      if (p3) out.push({ path: ".htaccess", kind: "patch", note: "block subsite-artifacts from web", contents: p3 });
    }
  }

  const readme = await readIf(path.join(repo, "README.md"));
  if (readme !== null) {
    const pr = patchReadmeRow(readme, cfg);
    out.push({
      path: "README.md",
      kind: pr ? "patch" : "skip",
      note: pr ? "add Domains row" : "row already present",
      contents: pr ?? undefined,
    });
  }

  if (cfg.mode === "service" || cfg.mode === "tunnel") {
    const tunnel = await readIf(path.join(repo, "tunnel", "config.yml"));
    if (tunnel !== null) {
      const pt = patchTunnelIngress(tunnel, cfg);
      out.push({
        path: "tunnel/config.yml",
        kind: pt ? "patch" : "skip",
        note: pt ? `add ingress → :${cfg.port}` : "ingress already present",
        contents: pt ?? undefined,
      });
    }
  }

  if (!persisted.exists) {
    out.push({
      path: path.join(ARTIFACT_ROOT, cfg.slug, COMPLETION_FILE),
      kind: "complete",
      note: "publish completion only after every scaffold write",
      contents: await buildCompletionRecord(cfg),
    });
  }

  return out;
}

export async function apply(repo: string, planned: PlannedFile[], signal?: AbortSignal): Promise<string[]> {
  const done: string[] = [];
  const completionInputs = new Map<string, string>();
  const throwIfAborted = () => {
    if (signal?.aborted) throw new Error("Operation aborted; the scaffold can be retried safely.");
  };
  const publishExclusive = async (full: string, contents: string, tag: string) => {
    await fs.mkdir(path.dirname(full), { recursive: true });
    const temp = `${full}.${tag}-${process.pid}-${randomUUID()}`;
    try {
      const handle = await fs.open(temp, "wx", 0o644);
      try {
        await handle.writeFile(contents, "utf8");
        await handle.sync();
      } finally {
        await handle.close();
      }
      throwIfAborted();
      await fs.link(temp, full);
    } finally {
      await fs.unlink(temp).catch(() => {});
    }
  };
  const replaceAtomically = async (full: string, contents: string) => {
    await fs.mkdir(path.dirname(full), { recursive: true });
    const temp = `${full}.patch-${process.pid}-${randomUUID()}`;
    try {
      // Start from a metadata-preserving copy so rename does not silently drop
      // group-write, ACLs, or extended attributes from the existing file.
      await execFileAsync("cp", ["--preserve=mode,xattr", "--reflink=auto", "--", full, temp]);
      const handle = await fs.open(temp, "r+");
      try {
        await handle.truncate(0);
        await handle.writeFile(contents, "utf8");
        await handle.sync();
      } finally {
        await handle.close();
      }
      throwIfAborted();
      await fs.rename(temp, full);
    } finally {
      await fs.unlink(temp).catch(() => {});
    }
  };
  // Collapse multiple patches to the same file: apply the last (fully patched) version.
  const seenPatch = new Set<string>();
  for (let i = planned.length - 1; i >= 0; i--) {
    const item = planned[i];
    if (item.kind === "patch") {
      if (seenPatch.has(item.path)) planned[i] = { ...item, kind: "skip", contents: undefined };
      else seenPatch.add(item.path);
    }
  }
  // A plan is only a snapshot. Recheck all create/verify destinations before
  // publishing the slug claim so a site created after plan() cannot be
  // mislabeled as an interrupted scaffold.
  for (const item of planned) {
    if ((item.kind !== "create" && item.kind !== "verify") || item.contents === undefined) continue;
    const current = await readIf(path.join(repo, item.path));
    if (item.kind === "verify" && current !== item.contents) {
      throw new Error(`Scaffold file "${item.path}" changed before completion; refusing to claim the site.`);
    }
    if (item.kind === "create" && current !== null && current !== item.contents) {
      throw new Error(`Concurrent write changed "${item.path}"; refusing to claim the site.`);
    }
  }

  const claimsCreated: Array<{ full: string; contents: string }> = [];
  const completionPaths = planned
    .filter((item) => item.kind === "complete")
    .map((item) => path.join(repo, item.path));
  try {
    for (const item of planned) {
      throwIfAborted();
      const full = path.join(repo, item.path);
      if (item.kind === "claim") {
        throwIfAborted();
        try {
          await publishExclusive(full, item.contents!, "claim");
        } catch (cause: any) {
          if (cause?.code === "EEXIST") {
            throw new Error(`Site identity was claimed by another scaffold: ${item.path}`);
          }
          throw cause;
        }
        done.push(`claimed ${item.path}`);
        completionInputs.set(item.path, item.contents!);
        claimsCreated.push({ full, contents: item.contents! });
        continue;
      }
      if (item.kind === "verify") {
        completionInputs.set(item.path, item.contents!);
        continue;
      }
      if (item.kind === "skip" || item.contents === undefined) continue;
      await fs.mkdir(path.dirname(full), { recursive: true });
      if (item.kind === "create") {
        try {
          await publishExclusive(full, item.contents, "create");
        } catch (cause: any) {
          if (cause?.code === "EEXIST") {
            if ((await readIf(full)) !== item.contents) {
              throw new Error(`Concurrent write changed "${item.path}"; refusing to publish completion.`);
            }
          } else {
            throw cause;
          }
        }
      } else if (item.kind === "complete") {
        for (const [relativePath, expected] of completionInputs) {
          if ((await readIf(path.join(repo, relativePath))) !== expected) {
            throw new Error(`Scaffold file "${relativePath}" changed before completion; refusing to mark it complete.`);
          }
        }
        try {
          await publishExclusive(full, item.contents, "complete");
        } catch (cause: any) {
          if (cause?.code === "EEXIST" && (await readIf(full)) === item.contents) continue;
          if (cause?.code === "EEXIST") throw new Error(`Completion record changed concurrently: ${item.path}`);
          throw cause;
        }
      } else {
        await replaceAtomically(full, item.contents);
      }
      if (item.kind !== "complete") completionInputs.set(item.path, item.contents);
      // Publishing the completion record is the scaffold's commit point. A
      // cancellation observed after that durable link must not turn a finished
      // site into a reported failure or prevent caller-side post-processing.
      if (item.kind !== "complete") throwIfAborted();
      done.push(`${item.kind === "patch" ? "patched" : item.kind === "complete" ? "completed" : "created"} ${item.path}`);
    }
    return done;
  } catch (cause) {
    // Remove this invocation's claim only when nothing matching the scaffold
    // survived. A partial output needs the claim so the next run can safely
    // identify and resume it; an empty failed attempt must not reserve a slug.
    const completed = (await Promise.all(completionPaths.map((full) => readIf(full)))).some(
      (contents) => contents !== null,
    );
    const claimPaths = new Set(claimsCreated.map(({ full }) => path.relative(repo, full)));
    const recoverableOutputSurvives = (
      await Promise.all(
        [...completionInputs]
          .filter(([relativePath]) => !claimPaths.has(relativePath))
          .map(async ([relativePath, expected]) => (await readIf(path.join(repo, relativePath))) === expected),
      )
    ).some(Boolean);
    if (!completed && !recoverableOutputSurvives) {
      for (const claim of claimsCreated.reverse()) {
        if ((await readIf(claim.full)) === claim.contents) {
          await fs.unlink(claim.full).catch(() => {});
        }
      }
    }
    throw cause;
  }
}

export async function zipArtifact(repo: string, cfg: SubsiteConfig): Promise<string | null> {
  const aDir = path.join(repo, ARTIFACT_ROOT, cfg.slug);
  if (!existsSync(aDir)) return null;
  const stamp = new Date().toISOString().slice(0, 10);
  const out = path.join(TRANSFER_DIR, `${cfg.slug}-subsite-artifact-${stamp}.zip`);
  await fs.mkdir(TRANSFER_DIR, { recursive: true });
  try {
    await execFileAsync("zip", ["-rq", out, cfg.slug], { cwd: path.join(repo, ARTIFACT_ROOT) });
    return out;
  } catch {
    try {
      const tgz = out.replace(/\.zip$/, ".tar.gz");
      await execFileAsync("tar", ["-czf", tgz, cfg.slug], { cwd: path.join(repo, ARTIFACT_ROOT) });
      return tgz;
    } catch {
      return null;
    }
  }
}

export function pageListSummary(cfg: SubsiteConfig): string {
  return pageList(cfg)
    .map((p) => p.file)
    .join(", ");
}

export function summarize(cfg: SubsiteConfig, planned: PlannedFile[], repo: string): string {
  const claims = planned.filter((p) => p.kind === "claim").length;
  const creates = planned.filter((p) => p.kind === "create").length;
  const verifies = planned.filter((p) => p.kind === "verify").length;
  const patches = planned.filter((p) => p.kind === "patch").length;
  const completions = planned.filter((p) => p.kind === "complete").length;
  const skips = planned.filter((p) => p.kind === "skip").length;
  return [
    `Sub-site: ${cfg.title}`,
    `Subdomain: https://${cfg.subdomain}${cfg.routeAsPath ? `  (also /${cfg.slug}/)` : ""}`,
    `Theme: ${cfg.theme}   Brand: ${cfg.brand}   Mode: ${cfg.mode}${cfg.mode !== "static" && cfg.port ? ` (:${cfg.port})` : ""}`,
    `Repo: ${repo}`,
    `Pages: ${pageList(cfg).map((p) => p.file).join(", ")}`,
    "",
    `Plan: ${claims} claim, ${creates} create, ${verifies} verify, ${patches} patch, ${completions} complete, ${skips} skip`,
    ...planned.map((p) => `  [${p.kind}] ${p.path}${p.note ? `  — ${p.note}` : ""}`),
  ].join("\n");
}
