// Self-test for the sub-site scaffolder pure logic (core.ts + templates.ts).
// Run: node _selftest.mjs   (uses pi's bundled jiti to load the TS)
import { createJiti } from "/home/dyadmin/.hermes/node/lib/node_modules/@earendil-works/pi-coding-agent/node_modules/jiti/lib/jiti.mjs";
import { promises as fs } from "node:fs";
import { existsSync, writeFileSync } from "node:fs";
import { createHash } from "node:crypto";
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
const confirmed = (raw, theme = "literary") => core.withConfirmedTheme(raw, theme);

const REAL_REPO = "/home/dyadmin/githubStaging/dyuhaus.com";
const tmp = await fs.mkdtemp(path.join(os.tmpdir(), "dyuhaus-scaffold-"));
console.log("temp repo:", tmp);
await copyDir(REAL_REPO, tmp);

const htaccessBefore = await fs.readFile(path.join(tmp, ".htaccess"), "utf8");
const htaccessModeBefore = (await fs.stat(path.join(tmp, ".htaccess"))).mode & 0o7777;
const readmeBefore = await fs.readFile(path.join(tmp, "README.md"), "utf8");

/* ---- 1. static site ---------------------------------------------------- */
console.log("\n[1] static sub-site 'labs'");
const { cfg, error } = core.buildConfig(confirmed({
  slug: "labs",
  title: "IHTC Labs",
  description: "Experimental IHTC demos.",
  brand: "ihtc",
  mode: "static",
  pages: ["about", "demos"],
}, "ihtc"));
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
ok(existsSync(path.join(tmp, "subsite-artifacts/labs/scaffold.complete.json")), "completion record created last");

const idx = await fs.readFile(path.join(tmp, "labs/index.html"), "utf8");
const aboutPage = await fs.readFile(path.join(tmp, "labs/about.html"), "utf8");
ok(idx.includes('href="styles.css"'), "index.html uses relative styles.css");
ok(idx.includes('href="about.html"') && idx.includes('href="demos.html"'), "nav links to extra pages");
ok(aboutPage.includes('href="index.html"'), "extra pages link back to the site home page");
ok(idx.includes("Content-Security-Policy"), "index.html keeps CSP meta");
ok(idx.includes("<title>IHTC Labs</title>"), "confirmed template page receives the project title");
ok(
  (await fs.readFile(path.join(tmp, "labs/styles.css"), "utf8")) ===
    core.applyCanonicalIhtcTokens(await fs.readFile(path.join(tmp, "starter/ihtc/styles.css"), "utf8")),
  "IHTC scaffold keeps the confirmed stylesheet with canonical brand tokens",
);

const manifest = JSON.parse(await fs.readFile(path.join(tmp, "subsite-artifacts/labs/site.manifest.json"), "utf8"));
ok(manifest.site.subdomain === "labs.dyuhaus.com", "manifest subdomain correct");
ok(manifest.design.template.key === "ihtc", "manifest carries confirmed theme");
ok(manifest.design.template.reference.endsWith("/ihtc/"), "manifest carries live theme reference");
ok(manifest.design.template.confirmedByUser === true, "manifest records explicit theme confirmation");
ok(manifest.design.tokens.red === "#dd1b27", "manifest carries the IHTC template's red token");
ok(manifest.pages.length === 3, "manifest lists 3 pages");
ok(manifest.schema === "dyuhaus.subsite-artifact/v2", "manifest uses completion-aware schema");
const manifestText = await fs.readFile(path.join(tmp, "subsite-artifacts/labs/site.manifest.json"), "utf8");
const completion = JSON.parse(
  await fs.readFile(path.join(tmp, "subsite-artifacts/labs/scaffold.complete.json"), "utf8"),
);
ok(
  completion.manifestSha256 === createHash("sha256").update(manifestText).digest("hex"),
  "completion record is bound to the exact manifest",
);
const completionPath = path.join(tmp, "subsite-artifacts/labs/scaffold.complete.json");
const completionText = await fs.readFile(completionPath, "utf8");
await fs.writeFile(completionPath, completionText.replace(completion.manifestSha256, "0".repeat(64)));
const tamperedCompletion = await core.readPersistedSiteConfig(tmp, "labs");
ok(tamperedCompletion.error?.includes("does not match its manifest"), "tampered completion record is refused");
await fs.writeFile(completionPath, completionText);

const htaccessAfter = await fs.readFile(path.join(tmp, ".htaccess"), "utf8");
ok(((await fs.stat(path.join(tmp, ".htaccess"))).mode & 0o7777) === htaccessModeBefore, "atomic patch preserves file mode");
ok(/RewriteCond %\{HTTP_HOST\} \^labs\\\.dyuhaus\\\.com/.test(htaccessAfter), ".htaccess has labs rewrite cond");
ok(htaccessAfter.includes("RewriteRule ^(.*)$ /labs/$1 [L]"), ".htaccess has labs rewrite rule");
ok(
  htaccessAfter.includes('SetEnvIf Request_URI "^/labs/" no_immutable_assets') ||
    htaccessAfter.includes('Header set Cache-Control "public, max-age=0, must-revalidate"'),
  ".htaccess has fixed-name cache revalidation",
);
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
const wrongTheme = core.buildConfig(confirmed({
  slug: "labs",
  title: "IHTC Labs",
  description: "Experimental IHTC demos.",
  brand: "ihtc",
  mode: "static",
  pages: ["about", "demos"],
}, "noir"));
let mismatchRefused = false;
try {
  await core.plan(tmp, wrongTheme.cfg, true);
} catch (cause) {
  mismatchRefused = cause instanceof Error && cause.message.includes("different persisted theme");
}
ok(mismatchRefused, "re-run with a different theme is refused before planning");
const changedTitle = core.buildConfig(confirmed({
  slug: "labs",
  title: "Changed title",
  description: "Experimental IHTC demos.",
  brand: "ihtc",
  mode: "static",
  pages: ["about", "demos"],
}, "ihtc"));
let configChangeRefused = false;
try {
  await core.plan(tmp, changedTitle.cfg, true);
} catch (cause) {
  configChangeRefused = cause instanceof Error && cause.message.includes("different persisted title");
}
ok(configChangeRefused, "re-run cannot mix changed inputs with a create-only manifest");

const legacy = await core.readPersistedSiteConfig(tmp, "jobs");
ok(legacy.cfg?.theme === "ihtc", "legacy terminal manifest reuses the IHTC theme without a new prompt");
ok(legacy.cfg?.themeConfirmedByUser === false, "legacy migration does not claim a new user confirmation");

console.log("\n[2b] concurrent new-site claim");
const raceA = core.buildConfig(confirmed({ slug: "theme-race", mode: "static" }, "literary"));
const raceB = core.buildConfig(confirmed({ slug: "theme-race", mode: "static" }, "noir"));
const [racePlanA, racePlanB] = await Promise.all([
  core.plan(tmp, raceA.cfg, true),
  core.plan(tmp, raceB.cfg, true),
]);
const raceResults = await Promise.allSettled([
  core.apply(tmp, racePlanA),
  core.apply(tmp, racePlanB),
]);
ok(raceResults.filter((result) => result.status === "fulfilled").length === 1, "only one concurrent scaffold claims the slug");
ok(raceResults.filter((result) => result.status === "rejected").length === 1, "the losing concurrent scaffold writes nothing");
const raceManifest = JSON.parse(
  await fs.readFile(path.join(tmp, "subsite-artifacts/theme-race/site.manifest.json"), "utf8"),
);
const racePrompt = await fs.readFile(path.join(tmp, "subsite-artifacts/theme-race/PROMPT.md"), "utf8");
ok(racePrompt.includes(`**${raceManifest.design.template.label}**`), "concurrent artifact files come from one theme");

const lateRaceA = core.buildConfig(confirmed({ slug: "late-race", mode: "static", tagline: "First" }, "literary"));
const lateRaceB = core.buildConfig(confirmed({ slug: "late-race", mode: "static", tagline: "Second" }, "literary"));
const lateRacePlanA = await core.plan(tmp, lateRaceA.cfg, true);
await core.apply(tmp, [lateRacePlanA[0]]);
let lateRaceRefused = false;
try {
  await core.plan(tmp, lateRaceB.cfg, true);
} catch (cause) {
  lateRaceRefused = cause instanceof Error && cause.message.includes("different persisted tagline");
}
ok(lateRaceRefused, "late concurrent plan cannot mix rendered fields with a persisted identity");

console.log("\n[2c] stale unclaimed files");
const orphanCompletion = core.buildConfig(confirmed({ slug: "orphan-completion", mode: "static" }, "noir"));
await fs.mkdir(path.join(tmp, "subsite-artifacts/orphan-completion"), { recursive: true });
await fs.writeFile(path.join(tmp, "subsite-artifacts/orphan-completion/scaffold.complete.json"), "{}\n");
let orphanCompletionRefused = false;
try {
  await core.plan(tmp, orphanCompletion.cfg, true);
} catch (cause) {
  orphanCompletionRefused = cause instanceof Error && cause.message.includes("Orphaned completion record");
}
ok(orphanCompletionRefused, "an orphaned completion record is refused before planning any writes");
ok(
  !existsSync(path.join(tmp, "orphan-completion")) &&
    !existsSync(path.join(tmp, "subsite-artifacts/orphan-completion/site.manifest.json")),
  "orphaned completion refusal leaves no scaffold output or claim",
);

const staleUnclaimed = core.buildConfig(confirmed({ slug: "stale-unclaimed", mode: "static" }, "noir"));
await fs.mkdir(path.join(tmp, "subsite-artifacts/stale-unclaimed"), { recursive: true });
await fs.writeFile(path.join(tmp, "subsite-artifacts/stale-unclaimed/PROMPT.md"), "old poetry prompt\n");
let staleUnclaimedRefused = false;
try {
  await core.plan(tmp, staleUnclaimed.cfg, true);
} catch (cause) {
  staleUnclaimedRefused = cause instanceof Error && cause.message.includes("differs from the confirmed site identity");
}
ok(staleUnclaimedRefused, "a new scaffold refuses stale files from another theme before completion");
ok(
  !existsSync(path.join(tmp, "subsite-artifacts/stale-unclaimed/site.manifest.json")),
  "stale-file refusal publishes no site identity",
);

const destinationRace = core.buildConfig(confirmed({ slug: "destination-race", mode: "static" }, "noir"));
const destinationRacePlan = await core.plan(tmp, destinationRace.cfg, true);
await fs.mkdir(path.join(tmp, "destination-race"), { recursive: true });
await fs.writeFile(path.join(tmp, "destination-race/index.html"), "unrelated site created after planning\n");
let destinationRaceRefused = false;
try {
  await core.apply(tmp, destinationRacePlan);
} catch (cause) {
  destinationRaceRefused = cause instanceof Error && cause.message.includes("refusing to claim the site");
}
ok(destinationRaceRefused, "destinations are rechecked before the site identity is claimed");
ok(
  !existsSync(path.join(tmp, "subsite-artifacts/destination-race/site.manifest.json")),
  "a late destination conflict leaves no pending site identity",
);

const failedAfterClaim = core.buildConfig(confirmed({ slug: "claim-cleanup", mode: "static" }, "poetry"));
const failedAfterClaimPlan = await core.plan(tmp, failedAfterClaim.cfg, true);
const failedClaim = failedAfterClaimPlan.find((item) => item.kind === "claim");
if (!failedClaim) throw new Error("claim-cleanup identity was not planned");
let postClaimFailureRefused = false;
try {
  await core.apply(tmp, [
    failedClaim,
    { path: "missing-parent-input.txt", kind: "patch", note: "force a post-claim failure", contents: "planned\n" },
  ]);
} catch {
  postClaimFailureRefused = true;
}
ok(postClaimFailureRefused, "a failure after claiming is reported");
ok(
  !existsSync(path.join(tmp, "subsite-artifacts/claim-cleanup/site.manifest.json")),
  "a failed application removes its own uncompleted claim",
);

const partialFailure = core.buildConfig(confirmed({ slug: "partial-failure", mode: "static" }, "literary"));
const partialFailurePlan = await core.plan(tmp, partialFailure.cfg, true);
let partialFailureRefused = false;
try {
  await core.apply(tmp, [
    partialFailurePlan[0],
    partialFailurePlan[1],
    { path: "missing-partial-input.txt", kind: "patch", note: "fail after one output", contents: "planned\n" },
  ]);
} catch {
  partialFailureRefused = true;
}
ok(partialFailureRefused, "a failure after a partial site write is reported");
ok(
  existsSync(path.join(tmp, "subsite-artifacts/partial-failure/site.manifest.json")),
  "a partial site keeps its confirmed identity for retry",
);
const partialFailureState = await core.readPersistedSiteConfig(tmp, "partial-failure");
ok(
  partialFailureState.pendingCfg?.theme === "literary" && !partialFailureState.exists,
  "a surviving partial output remains a recoverable pending scaffold",
);
const partialFailureRetry = await core.plan(tmp, partialFailureState.pendingCfg, true);
await core.apply(tmp, partialFailureRetry);
ok(
  existsSync(path.join(tmp, "subsite-artifacts/partial-failure/scaffold.complete.json")),
  "a partial-write failure retries to completion without manual cleanup",
);

const verifyRace = core.buildConfig(confirmed({ slug: "verify-race", mode: "static" }, "horror"));
const initialVerifyRacePlan = await core.plan(tmp, verifyRace.cfg, true);
const promptToVerify = initialVerifyRacePlan.find(
  (item) => item.path === "subsite-artifacts/verify-race/PROMPT.md",
);
if (!promptToVerify?.contents) throw new Error("verify-race prompt was not planned");
await fs.mkdir(path.join(tmp, "subsite-artifacts/verify-race"), { recursive: true });
await fs.writeFile(path.join(tmp, promptToVerify.path), promptToVerify.contents);
const verifyRacePlan = await core.plan(tmp, verifyRace.cfg, true);
ok(
  verifyRacePlan.some((item) => item.path === promptToVerify.path && item.kind === "verify"),
  "matching pre-existing files are marked for completion-time verification",
);
await fs.writeFile(path.join(tmp, promptToVerify.path), "changed after planning\n");
let verifyRaceRefused = false;
try {
  await core.apply(tmp, verifyRacePlan);
} catch (cause) {
  verifyRaceRefused = cause instanceof Error && cause.message.includes("changed before completion");
}
ok(verifyRaceRefused, "a file changed after planning cannot be marked complete");
ok(
  !existsSync(path.join(tmp, "subsite-artifacts/verify-race/scaffold.complete.json")),
  "completion stays unpublished after a verification race",
);

const manifestRace = core.buildConfig(confirmed({ slug: "manifest-race", mode: "static" }, "horror"));
const manifestRacePlan = await core.plan(tmp, manifestRace.cfg, true);
const manifestClaim = manifestRacePlan.find((item) => item.kind === "claim");
const manifestCompletion = manifestRacePlan.find((item) => item.kind === "complete");
if (!manifestClaim?.contents || !manifestCompletion) throw new Error("manifest-race claim or completion was not planned");
const manifestRaceCompletion = {
  ...manifestCompletion,
  get contents() {
    writeFileSync(path.join(tmp, manifestClaim.path), `${manifestClaim.contents}\n`);
    return manifestCompletion.contents;
  },
};
let manifestRaceRefused = false;
try {
  await core.apply(tmp, [manifestClaim, manifestRaceCompletion]);
} catch (cause) {
  manifestRaceRefused =
    cause instanceof Error && cause.message.includes("site.manifest.json") && cause.message.includes("changed before completion");
}
ok(manifestRaceRefused, "a claimed manifest changed before completion cannot authorize the scaffold");
ok(
  !existsSync(path.join(tmp, "subsite-artifacts/manifest-race/scaffold.complete.json")),
  "completion stays unpublished after a manifest race",
);

const createdOutputRacePath = path.join(tmp, "created-output-race.txt");
const createdOutputCompletion = {
  path: "created-output-race.complete.json",
  kind: "complete",
  note: "race fixture completion",
  get contents() {
    writeFileSync(createdOutputRacePath, "changed concurrently\n");
    return "{}\n";
  },
};
let createdOutputRaceRefused = false;
try {
  await core.apply(tmp, [
    { path: "created-output-race.txt", kind: "create", note: "race fixture", contents: "planned\n" },
    createdOutputCompletion,
  ]);
} catch (cause) {
  createdOutputRaceRefused = cause instanceof Error && cause.message.includes("created-output-race.txt");
}
ok(createdOutputRaceRefused, "completion revalidates a newly created file");
ok(
  !existsSync(path.join(tmp, "created-output-race.complete.json")),
  "changed created output cannot be certified complete",
);

let lateAbortReads = 0;
const lateAbortSignal = {
  get aborted() {
    lateAbortReads += 1;
    return lateAbortReads >= 3;
  },
};
const lateAbortDone = await core.apply(
  tmp,
  [{ path: "late-abort.complete.json", kind: "complete", note: "late abort fixture", contents: "{}\n" }],
  lateAbortSignal,
);
ok(
  lateAbortDone.includes("completed late-abort.complete.json") &&
    existsSync(path.join(tmp, "late-abort.complete.json")),
  "an abort arriving after the completion commit point does not report failure",
);

console.log("\n[2d] interrupted new-site retry");
const interrupted = core.buildConfig(confirmed({ slug: "interrupted", mode: "static" }, "poetry"));
const interruptedPlan = await core.plan(tmp, interrupted.cfg, true);
ok(interruptedPlan[0]?.kind === "claim", "confirmed identity is the first planned write");
await core.apply(tmp, interruptedPlan.slice(0, 2));
ok(existsSync(path.join(tmp, "interrupted/index.html")), "interruption can leave a partial site directory");
ok(
  !existsSync(path.join(tmp, "subsite-artifacts/interrupted/scaffold.complete.json")),
  "partial scaffold has no completion record",
);
const retryConfig = await core.readPersistedSiteConfig(tmp, "interrupted");
ok(retryConfig.pendingCfg?.theme === "poetry" && !retryConfig.exists, "partial directory remains pending, not authorized");
const partialEntry = path.join(tmp, "interrupted/index.html");
const partialEntryText = await fs.readFile(partialEntry, "utf8");
await fs.writeFile(partialEntry, `${partialEntryText}\nchanged outside the interrupted scaffold\n`);
let changedPartialRefused = false;
try {
  await core.plan(tmp, retryConfig.pendingCfg, true);
} catch (cause) {
  changedPartialRefused = cause instanceof Error && cause.message.includes("differs from the confirmed site identity");
}
ok(changedPartialRefused, "changed partial files are refused instead of being mixed into a retry");
await fs.writeFile(partialEntry, partialEntryText);
const retryPlan = await core.plan(tmp, retryConfig.pendingCfg, true);
ok(!retryPlan.some((item) => item.kind === "claim"), "retry does not compete with its own persisted identity");
await core.apply(tmp, retryPlan);
ok(existsSync(path.join(tmp, "interrupted/index.html")), "retry completes the interrupted scaffold");
ok(
  existsSync(path.join(tmp, "subsite-artifacts/interrupted/scaffold.complete.json")),
  "retry publishes completion after all writes",
);

console.log("\n[2d] completed-site regeneration");
await fs.rename(path.join(tmp, "labs"), path.join(tmp, "labs-original"));
const completedWithoutFolder = await core.readPersistedSiteConfig(tmp, "labs");
ok(completedWithoutFolder.exists && completedWithoutFolder.cfg?.theme === "ihtc", "completion remains valid after site folder removal");
const regenerationPlan = await core.plan(tmp, completedWithoutFolder.cfg, true);
ok(regenerationPlan.some((item) => item.path === "labs/index.html" && item.kind === "create"), "missing completed-site folder is planned for regeneration");
ok(!regenerationPlan.some((item) => item.kind === "complete"), "completed regeneration does not rewrite the completion record");
await core.apply(tmp, regenerationPlan);
ok(existsSync(path.join(tmp, "labs/index.html")), "completed site regenerates without a new theme prompt");

/* ---- 3. service mode + tunnel ----------------------------------------- */
console.log("\n[3] service sub-site 'widget' :8790");
const svc = core.buildConfig(confirmed({
  slug: "widget",
  brand: "personal",
  mode: "service",
  port: 8790,
}, "noir"));
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
const portal = core.buildConfig(confirmed({ slug: "portal", brand: "ihtc" }, "ihtc"));
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
ok(core.buildConfig(confirmed({ slug: "Bad Slug!" })).cfg?.slug === "bad-slug", "slug normalized");
ok(!!core.buildConfig(confirmed({ slug: "ops" })).error, "reserved slug rejected");
ok(!!core.buildConfig(confirmed({ slug: "svc", mode: "service" })).error, "service without port rejected");
ok(!!core.buildConfig(confirmed({ slug: "" })).error, "empty slug rejected");
ok(!!core.buildConfig({ slug: "missing-theme" }).error, "missing theme rejected");
ok(!!core.buildConfig({ slug: "unconfirmed-theme", theme: "noir" }).error, "unconfirmed theme rejected");
ok(
  !!core.buildConfig(confirmed({ slug: "invalid-theme" }, "unknown")).error,
  "unknown theme rejected",
);
let everyThemeUsesItsSource = true;
for (const theme of ["literary", "noir", "science-fiction", "high-fantasy", "horror", "poetry", "correspondence", "ihtc"]) {
  const themed = core.buildConfig(confirmed({ slug: `source-${theme}`, mode: "static" }, theme));
  const themedPlan = await core.plan(tmp, themed.cfg, true);
  const plannedStyles = themedPlan.find((item) => item.path === `source-${theme}/styles.css`)?.contents;
  const sourceStyles = await fs.readFile(path.join(tmp, `starter/${theme}/styles.css`), "utf8");
  const expectedStyles = theme === "ihtc" ? core.applyCanonicalIhtcTokens(sourceStyles) : sourceStyles;
  everyThemeUsesItsSource &&= plannedStyles === expectedStyles;
}
ok(everyThemeUsesItsSource, "all eight choices preserve the confirmed stylesheet and canonical IHTC tokens");
const metadataInput = core.buildConfig(confirmed({
  slug: "metadata-tokens",
  title: "R&D $&",
  description: "Plans from $1 to $$5",
  mode: "static",
}, "ihtc"));
const metadataPlan = await core.plan(tmp, metadataInput.cfg, true);
const metadataPage = metadataPlan.find((item) => item.path === "metadata-tokens/index.html")?.contents ?? "";
ok(metadataPage.includes("<title>R&amp;D $&amp;</title>"), "replacement tokens stay literal in the page title");
ok(
  metadataPage.includes('<meta name="description" content="Plans from $1 to $$5" />'),
  "replacement tokens stay literal in the page description",
);
ok(metadataPage.includes('<meta property="og:title" content="R&amp;D $&amp;" />'), "Open Graph title follows the project");
ok(
  metadataPage.includes('<meta property="og:description" content="Plans from $1 to $$5" />'),
  "Open Graph description follows the project",
);
ok(core.resolveRepo(tmp) === tmp, "resolveRepo finds site repo from cwd");
ok(core.isSiteRepo(tmp) && !core.isSiteRepo(os.tmpdir()), "isSiteRepo discriminates");

/* ---- 5. sanity: originals untouched by dry logic ---------------------- */
ok(htaccessBefore !== htaccessAfter, "htaccess actually changed for static");
ok(readmeBefore !== readmeAfter, "README actually changed for static");

console.log(`\n${failures === 0 ? "ALL PASS" : failures + " FAILURE(S)"}`);
console.log("inspect temp repo at:", tmp);
process.exit(failures === 0 ? 0 : 1);
