// Self-test for the sub-site scaffolder pure logic (core.ts + templates.ts).
// Run: node _selftest.mjs   (uses pi's bundled jiti to load the TS)
import { createJiti } from "/home/dyadmin/.hermes/node/lib/node_modules/@earendil-works/pi-coding-agent/node_modules/jiti/lib/jiti.mjs";
import { promises as fs } from "node:fs";
import { existsSync } from "node:fs";
import * as path from "node:path";
import os from "node:os";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const jiti = createJiti(import.meta.url, { interopDefault: true });

let failures = 0;
function ok(cond, msg) {
  console.log(`${cond ? "  ok  " : "FAIL  "}${msg}`);
  if (!cond) failures++;
}

async function copyDir(src, dst, skip = new Set([".git", "node_modules", "website.old"])) {
  await fs.mkdir(dst, { recursive: true });
  for (const entry of await fs.readdir(src, { withFileTypes: true })) {
    if (skip.has(entry.name)) continue;
    const s = path.join(src, entry.name);
    const d = path.join(dst, entry.name);
    if (entry.isDirectory()) await copyDir(s, d, skip);
    else if (entry.isFile()) await fs.copyFile(s, d);
  }
}

const core = await jiti.import(path.join(here, "core.ts"));

const REAL_REPO = "/home/dyadmin/githubStaging/dyuhaus.com";
const tmp = await fs.mkdtemp(path.join(os.tmpdir(), "dyuhaus-scaffold-"));
console.log("temp repo:", tmp);
await copyDir(REAL_REPO, tmp);

const htaccessBefore = await fs.readFile(path.join(tmp, ".htaccess"), "utf8");
const readmeBefore = await fs.readFile(path.join(tmp, "README.md"), "utf8");

/* ---- 1. static site ---------------------------------------------------- */
console.log("\n[1] static sub-site 'labs'");
const { cfg, error } = core.buildConfig({
  slug: "labs",
  title: "IHTC Labs",
  description: "Experimental IHTC demos.",
  brand: "ihtc",
  mode: "static",
  pages: ["about", "demos"],
});
ok(!error && cfg, `buildConfig ok ${error ?? ""}`);
const planned = await core.plan(tmp, cfg, true);
const applied = await core.apply(tmp, planned);
ok(existsSync(path.join(tmp, "labs/index.html")), "labs/index.html created");
ok(existsSync(path.join(tmp, "labs/about.html")), "labs/about.html created");
ok(existsSync(path.join(tmp, "labs/demos.html")), "labs/demos.html created");
ok(existsSync(path.join(tmp, "labs/styles.css")), "labs/styles.css created");
ok(existsSync(path.join(tmp, "labs/script.js")), "labs/script.js created");
ok(existsSync(path.join(tmp, "labs/robots.txt")), "labs/robots.txt created");
ok(existsSync(path.join(tmp, "labs/assets")), "labs/assets/ created");
ok(existsSync(path.join(tmp, "subsite-artifacts/labs/BRIEF.md")), "artifact BRIEF.md created");
ok(existsSync(path.join(tmp, "subsite-artifacts/labs/PROMPT.md")), "artifact PROMPT.md created");
ok(existsSync(path.join(tmp, "subsite-artifacts/labs/tokens.css")), "artifact tokens.css created");
ok(existsSync(path.join(tmp, "subsite-artifacts/labs/site.manifest.json")), "artifact manifest created");

const idx = await fs.readFile(path.join(tmp, "labs/index.html"), "utf8");
ok(idx.includes('href="styles.css"'), "index.html uses relative styles.css");
ok(idx.includes('href="about.html"') && idx.includes('href="demos.html"'), "nav links to extra pages");
ok(idx.includes("Content-Security-Policy"), "index.html keeps CSP meta");

const manifest = JSON.parse(await fs.readFile(path.join(tmp, "subsite-artifacts/labs/site.manifest.json"), "utf8"));
ok(manifest.site.subdomain === "labs.dyuhaus.com", "manifest subdomain correct");
ok(manifest.design.tokens.accent === "#DD1B27", "manifest carries IHTC accent token");
ok(manifest.pages.length === 3, "manifest lists 3 pages");

const htaccessAfter = await fs.readFile(path.join(tmp, ".htaccess"), "utf8");
ok(/RewriteCond %\{HTTP_HOST\} \^labs\\\.dyuhaus\\\.com/.test(htaccessAfter), ".htaccess has labs rewrite cond");
ok(htaccessAfter.includes("RewriteRule ^(.*)$ /labs/$1 [L]"), ".htaccess has labs rewrite rule");
ok(htaccessAfter.includes('SetEnvIf Request_URI "^/labs/" no_immutable_assets'), ".htaccess has labs cache-revalidate");
ok(/RedirectMatch 404 \^\/\([^\n]*subsite-artifacts[^\n]*\)\(\/\|\$\)/.test(htaccessAfter), ".htaccess blocks subsite-artifacts");
ok(!htaccessAfter.includes("/labs/$1 [L]\n\n\n"), "no triple-blank artifacts");

const readmeAfter = await fs.readFile(path.join(tmp, "README.md"), "utf8");
ok(readmeAfter.includes("labs.dyuhaus.com"), "README has labs domain row");
// ensure README table still well-formed: row is inside the Domains table
const domSection = readmeAfter.slice(readmeAfter.indexOf("## Domains"));
ok(/\|\s*`labs\.dyuhaus\.com`.*\|/.test(domSection), "README row is a table row in Domains section");

/* ---- 2. idempotency ---------------------------------------------------- */
console.log("\n[2] idempotent re-run");
const planned2 = await core.plan(tmp, cfg, true);
const applied2 = await core.apply(tmp, planned2);
ok(applied2.length === 0, `re-run writes nothing (wrote ${applied2.length})`);
const htaccessAfter2 = await fs.readFile(path.join(tmp, ".htaccess"), "utf8");
const count = (htaccessAfter2.match(/\/labs\/\$1 \[L\]/g) || []).length;
ok(count === 1, `labs rewrite present exactly once (found ${count})`);
const readmeAfter2 = await fs.readFile(path.join(tmp, "README.md"), "utf8");
const rowCount = (readmeAfter2.match(/labs\.dyuhaus\.com/g) || []).length;
ok(rowCount === 1, `labs README row present exactly once (found ${rowCount})`);

/* ---- 3. service mode + tunnel ----------------------------------------- */
console.log("\n[3] service sub-site 'widget' :8790");
const svc = core.buildConfig({ slug: "widget", brand: "personal", mode: "service", port: 8790 });
ok(!svc.error, `service buildConfig ok ${svc.error ?? ""}`);
const svcPlan = await core.plan(tmp, svc.cfg, true);
await core.apply(tmp, svcPlan);
const tunnelAfter = await fs.readFile(path.join(tmp, "tunnel/config.yml"), "utf8");
ok(tunnelAfter.includes("hostname: widget.dyuhaus.com"), "tunnel has widget ingress hostname");
ok(tunnelAfter.includes("service: http://localhost:8790"), "tunnel has widget origin :8790");
ok(tunnelAfter.indexOf("widget.dyuhaus.com") < tunnelAfter.indexOf("http_status:404"), "widget ingress before catch-all 404");
// service mode should NOT add an .htaccess rewrite
const htaccessSvc = await fs.readFile(path.join(tmp, ".htaccess"), "utf8");
ok(!htaccessSvc.includes("/widget/$1 [L]"), "service mode adds no .htaccess rewrite");

/* ---- 3b. tunnel mode (the default) ------------------------------------ */
console.log("\n[3b] tunnel sub-site 'portal' (default mode, auto port)");
const portal = core.buildConfig({ slug: "portal", brand: "ihtc" });
ok(!portal.error && portal.cfg.mode === "tunnel", `default mode is tunnel (${portal.cfg.mode})`);
const portalPlan = await core.plan(tmp, portal.cfg, true);
ok(typeof portal.cfg.port === "number", `tunnel auto-assigned a port (${portal.cfg.port})`);
await core.apply(tmp, portalPlan);
const tun3b = await fs.readFile(path.join(tmp, "tunnel/config.yml"), "utf8");
ok(tun3b.includes("hostname: portal.dyuhaus.com"), "tunnel has portal ingress (default mode)");
ok(tun3b.includes(`service: http://localhost:${portal.cfg.port}`), "tunnel has portal origin at auto port");
const ht3b = await fs.readFile(path.join(tmp, ".htaccess"), "utf8");
ok(ht3b.includes("/portal/$1 [L]"), "tunnel mode keeps an .htaccess fallback rewrite");
const man3b = JSON.parse(await fs.readFile(path.join(tmp, "subsite-artifacts/portal/site.manifest.json"), "utf8"));
ok(man3b.hosting.mode === "tunnel" && man3b.hosting.port === portal.cfg.port, "manifest hosting=tunnel with port");
ok(man3b.hosting.staticOrigin?.nssmService === "dy-portal-static", "manifest names the NSSM static origin");
ok(!tun3b.includes(`localhost:${portal.cfg.port}`.replace(String(portal.cfg.port), String(portal.cfg.port + 100))), "port sanity");

/* ---- 4. validation guards --------------------------------------------- */
console.log("\n[4] validation guards");
ok(core.nextFreeComposePort('  - "127.0.0.1:8786:80"\n  - "127.0.0.1:8787:80"') === 8788, "nextFreeComposePort skips used ports");
ok(core.buildConfig({ slug: "Bad Slug!" }).cfg?.slug === "bad-slug", "slug normalized");
ok(!!core.buildConfig({ slug: "ops" }).error, "reserved slug rejected");
ok(!!core.buildConfig({ slug: "svc", mode: "service" }).error, "service without port rejected");
ok(!!core.buildConfig({ slug: "" }).error, "empty slug rejected");
ok(core.resolveRepo(tmp) === tmp, "resolveRepo finds site repo from cwd");
ok(core.isSiteRepo(tmp) && !core.isSiteRepo(os.tmpdir()), "isSiteRepo discriminates");

/* ---- 5. sanity: originals untouched by dry logic ---------------------- */
ok(htaccessBefore !== htaccessAfter, "htaccess actually changed for static");
ok(readmeBefore !== readmeAfter, "README actually changed for static");

console.log(`\n${failures === 0 ? "ALL PASS" : failures + " FAILURE(S)"}`);
console.log("inspect temp repo at:", tmp);
process.exit(failures === 0 ? 0 : 1);
