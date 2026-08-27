// Pure logic for the sub-site scaffolder: no pi / typebox imports, only node
// builtins + templates. Kept separate so it can be unit-tested with plain node
// (`node --experimental-strip-types`) on a headless box.

import { promises as fs } from "node:fs";
import { existsSync } from "node:fs";
import * as path from "node:path";
import { execFile } from "node:child_process";
import { promisify } from "node:util";

import {
  type SubsiteConfig,
  type BrandKey,
  type SiteMode,
  buildPage,
  buildStylesCss,
  buildScriptJs,
  buildRobots,
  buildTokensJson,
  buildTokensCss,
  buildBrief,
  buildPrompt,
  buildArtifactReadme,
  pageList,
  slugRegex,
} from "./templates";

const execFileAsync = promisify(execFile);

export const DEFAULT_REPO = "/home/dyadmin/githubStaging/dyuhaus.com";
export const ARTIFACT_ROOT = "subsite-artifacts";
export const TRANSFER_DIR = "/home/dyadmin/transfer";

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
  kind: "create" | "patch" | "skip";
  note: string;
  contents?: string;
}

export interface RawInput {
  slug: string;
  title?: string;
  description?: string;
  brand?: BrandKey;
  mode?: SiteMode;
  port?: number;
  routeAsPath?: boolean;
  immutableAssets?: boolean;
  pages?: string[];
  tagline?: string;
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
  await resolvePort(repo, cfg);
  const siteDir = cfg.slug;

  for (const p of pageList(cfg)) {
    const full = path.join(repo, siteDir, p.file);
    out.push({
      path: path.join(siteDir, p.file),
      kind: existsSync(full) ? "skip" : "create",
      note: existsSync(full) ? "exists" : p.isIndex ? "landing page" : "extra page",
      contents: buildPage(cfg, p),
    });
  }
  out.push({
    path: path.join(siteDir, "styles.css"),
    kind: existsSync(path.join(repo, siteDir, "styles.css")) ? "skip" : "create",
    note: "brand tokens + base layout",
    contents: buildStylesCss(cfg),
  });
  out.push({
    path: path.join(siteDir, "script.js"),
    kind: existsSync(path.join(repo, siteDir, "script.js")) ? "skip" : "create",
    note: "starter script",
    contents: buildScriptJs(cfg),
  });
  out.push({
    path: path.join(siteDir, "robots.txt"),
    kind: existsSync(path.join(repo, siteDir, "robots.txt")) ? "skip" : "create",
    note: "robots",
    contents: buildRobots(cfg),
  });
  out.push({
    path: path.join(siteDir, "assets", ".gitkeep"),
    kind: existsSync(path.join(repo, siteDir, "assets")) ? "skip" : "create",
    note: "assets dir",
    contents: "",
  });

  if (emitArtifact) {
    const aDir = path.join(ARTIFACT_ROOT, cfg.slug);
    const artifactFiles: [string, string][] = [
      ["site.manifest.json", buildTokensJson(cfg)],
      ["tokens.css", buildTokensCss(cfg)],
      ["BRIEF.md", buildBrief(cfg)],
      ["PROMPT.md", buildPrompt(cfg)],
      ["README.md", buildArtifactReadme(cfg)],
    ];
    for (const [name, body] of artifactFiles) {
      const full = path.join(repo, aDir, name);
      out.push({
        path: path.join(aDir, name),
        kind: existsSync(full) ? "skip" : "create",
        note: existsSync(full) ? "artifact exists" : "artifact",
        contents: body,
      });
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

  return out;
}

export async function apply(repo: string, planned: PlannedFile[]): Promise<string[]> {
  const done: string[] = [];
  // Collapse multiple patches to the same file: apply the last (fully patched) version.
  const seenPatch = new Set<string>();
  for (let i = planned.length - 1; i >= 0; i--) {
    const item = planned[i];
    if (item.kind === "patch") {
      if (seenPatch.has(item.path)) planned[i] = { ...item, kind: "skip", contents: undefined };
      else seenPatch.add(item.path);
    }
  }
  for (const item of planned) {
    if (item.kind === "skip" || item.contents === undefined) continue;
    const full = path.join(repo, item.path);
    await fs.mkdir(path.dirname(full), { recursive: true });
    await fs.writeFile(full, item.contents, "utf8");
    done.push(`${item.kind === "patch" ? "patched" : "created"} ${item.path}`);
  }
  return done;
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
  const creates = planned.filter((p) => p.kind === "create").length;
  const patches = planned.filter((p) => p.kind === "patch").length;
  const skips = planned.filter((p) => p.kind === "skip").length;
  return [
    `Sub-site: ${cfg.title}`,
    `Subdomain: https://${cfg.subdomain}${cfg.routeAsPath ? `  (also /${cfg.slug}/)` : ""}`,
    `Brand: ${cfg.brand}   Mode: ${cfg.mode}${cfg.mode !== "static" && cfg.port ? ` (:${cfg.port})` : ""}`,
    `Repo: ${repo}`,
    `Pages: ${pageList(cfg).map((p) => p.file).join(", ")}`,
    "",
    `Plan: ${creates} create, ${patches} patch, ${skips} skip`,
    ...planned.map((p) => `  [${p.kind}] ${p.path}${p.note ? `  — ${p.note}` : ""}`),
  ].join("\n");
}
