// Load test: import index.ts exactly as pi would (jiti), with the pi-provided
// packages aliased to pi's install, feed it a stub ExtensionAPI, and confirm
// registration runs. Validates all imports resolve + code executes (no model call).
import { promises as fs } from "node:fs";
import { existsSync } from "node:fs";
import { createHash } from "node:crypto";
import * as path from "node:path";
import os from "node:os";
import { fileURLToPath } from "node:url";

const PIROOT = "/home/dyadmin/.hermes/node/lib/node_modules/@earendil-works/pi-coding-agent";
const { createJiti } = await import(`${PIROOT}/node_modules/jiti/lib/jiti.mjs`);
const here = path.dirname(fileURLToPath(import.meta.url));

const jiti = createJiti(import.meta.url, {
  interopDefault: true,
  alias: {
    "@earendil-works/pi-coding-agent": `${PIROOT}/dist/index.js`,
    typebox: `${PIROOT}/node_modules/typebox/build/index.mjs`,
    "@earendil-works/pi-ai": `${PIROOT}/node_modules/@earendil-works/pi-ai/dist/index.js`,
  },
});

const mod = await jiti.import(path.join(here, "index.ts"));
const factory = mod.default ?? mod;

const tools = new Map();
const commands = new Map();
const events = new Map();
const pi = {
  registerTool: (def) => tools.set(def.name, def),
  registerCommand: (name, def) => commands.set(name, def),
  on: (evt, h) => events.set(evt, h),
  sendMessage: () => {},
  sendUserMessage: () => {},
  registerShortcut: () => {},
  registerFlag: () => {},
  setActiveTools: () => {},
  getAllTools: () => [...tools.values()],
};

let failures = 0;
const ok = (c, m) => {
  console.log(`${c ? "  ok  " : "FAIL  "}${m}`);
  if (!c) failures++;
};

await factory(pi);

ok(tools.has("create_subsite"), "registered tool create_subsite");
ok(commands.has("new-subsite"), "registered command /new-subsite");

const tool = tools.get("create_subsite");
ok(tool && typeof tool.execute === "function", "tool has execute()");
ok(tool && tool.parameters && tool.parameters.type === "object", "typebox parameters schema built");
ok(!!tool.parameters?.properties?.slug, "schema has slug property");
ok(!tool.parameters?.properties?.theme, "model cannot supply the template theme");
ok(!tool.parameters?.properties?.themeConfirmed, "model cannot self-assert theme confirmation");
ok(!tool.parameters?.properties?.emitArtifact, "new-site theme record cannot be disabled");
ok(!!tool.parameters?.properties?.brand, "schema has StringEnum brand property");
ok(Array.isArray(tool.promptGuidelines) && tool.promptGuidelines.length > 0, "tool has promptGuidelines");
ok(tool.executionMode === "sequential", "tool serializes calls within a Pi session");

// Exercise the tool end-to-end against a throwaway repo copy (dryRun=false).
async function copyDir(src, dst, skip = new Set([".git", "node_modules", "website.old"])) {
  await fs.mkdir(dst, { recursive: true });
  for (const e of await fs.readdir(src, { withFileTypes: true })) {
    if (skip.has(e.name)) continue;
    const s = path.join(src, e.name);
    const d = path.join(dst, e.name);
    if (e.isDirectory()) await copyDir(s, d, skip);
    else if (e.isFile()) await fs.copyFile(s, d);
  }
}
async function treeFingerprint(root) {
  const hash = createHash("sha256");
  async function walk(dir) {
    const entries = await fs.readdir(dir, { withFileTypes: true });
    entries.sort((a, b) => a.name.localeCompare(b.name));
    for (const entry of entries) {
      const full = path.join(dir, entry.name);
      const rel = path.relative(root, full);
      hash.update(`${entry.isDirectory() ? "d" : "f"}:${rel}\0`);
      if (entry.isDirectory()) await walk(full);
      else if (entry.isFile()) hash.update(await fs.readFile(full));
    }
  }
  await walk(root);
  return hash.digest("hex");
}
const tmp = await fs.mkdtemp(path.join(os.tmpdir(), "dyuhaus-load-"));
await copyDir("/home/dyadmin/githubStaging/dyuhaus.com", tmp);

const ctx = { cwd: tmp, hasUI: false, mode: "print", ui: { notify: () => {} } };
const beforeRejected = await treeFingerprint(tmp);
const rejected = await tool.execute("gate", { slug: "unconfirmed" }, undefined, undefined, ctx);
ok(rejected.isError, "tool refuses theme selection without an interactive user");
ok((await treeFingerprint(tmp)) === beforeRejected, "non-interactive refusal changes no repo file");

const cancelledCtx = {
  cwd: tmp,
  hasUI: true,
  mode: "tui",
  ui: { notify: () => {}, select: async () => undefined },
};
const beforeCancelled = await treeFingerprint(tmp);
const cancelled = await tool.execute("cancelled", { slug: "cancelled" }, undefined, undefined, cancelledCtx);
ok(cancelled.isError, "tool refuses a cancelled theme selection");
ok((await treeFingerprint(tmp)) === beforeCancelled, "cancelled selection changes no repo file");

const rpcCtx = {
  cwd: tmp,
  hasUI: true,
  mode: "rpc",
  ui: { notify: () => {}, select: async () => "Noir" },
};
const beforeRpc = await treeFingerprint(tmp);
const rpcForged = await tool.execute("rpc", { slug: "rpc-forged" }, undefined, undefined, rpcCtx);
ok(rpcForged.isError, "new-site selection is refused in forgeable RPC mode");
ok((await treeFingerprint(tmp)) === beforeRpc, "RPC refusal changes no repo file");

const abortedController = new AbortController();
let selectorReceivedAbortSignal = false;
const abortedCtx = {
  cwd: tmp,
  hasUI: true,
  mode: "tui",
  ui: {
    notify: () => {},
    select: async (_label, _options, selectOptions) => {
      selectorReceivedAbortSignal = selectOptions?.signal === abortedController.signal;
      abortedController.abort();
      return "Noir";
    },
  },
};
const beforeAborted = await treeFingerprint(tmp);
const aborted = await tool.execute(
  "aborted",
  { slug: "aborted-selection" },
  abortedController.signal,
  undefined,
  abortedCtx,
);
ok(selectorReceivedAbortSignal, "theme selector receives the tool abort signal");
ok(aborted.isError, "tool stops when theme selection is aborted");
ok((await treeFingerprint(tmp)) === beforeAborted, "aborted selection changes no repo file");

const toolCtx = (themeLabel) => ({
  cwd: tmp,
  hasUI: true,
  mode: "tui",
  ui: { notify: () => {}, select: async () => themeLabel },
});

const res = await tool.execute(
  "t1",
  {
    slug: "insights",
    title: "IHTC Insights",
    description: "Reports.",
    brand: "ihtc",
    zipArtifact: true,
  },
  undefined,
  undefined,
  toolCtx("Noir"),
);
ok(!res.isError, "tool.execute returned success");
ok(existsSync(path.join(tmp, "insights/index.html")), "tool created insights/index.html");
ok(existsSync(path.join(tmp, "subsite-artifacts/insights/site.manifest.json")), "tool created artifact manifest");
ok(existsSync(path.join(tmp, "subsite-artifacts/insights/scaffold.complete.json")), "tool published completion record");
ok(res.details && res.details.manifest?.site?.subdomain === "insights.dyuhaus.com", "result details carry manifest");
ok(res.details?.manifest?.design?.template?.key === "noir", "result manifest carries confirmed theme");
ok(res.details?.manifest?.design?.template?.confirmedByUser === true, "result records explicit confirmation");
const promptText = await fs.readFile(path.join(tmp, "subsite-artifacts/insights/PROMPT.md"), "utf8");
ok(promptText.includes("Selected template theme: **Noir**"), "artifact prompt carries selected theme label");
ok(promptText.includes("Use that reference's composition"), "non-IHTC prompt preserves genre direction");
ok(
  promptText.includes("Preserve the canonical IHTC name, logo artwork, and voice") &&
    promptText.includes("do not recolor the genre template or replace its typography"),
  "IHTC identity remains separate from the confirmed genre design",
);
ok(!("tokens" in res.details.manifest.design), "IHTC-branded genre manifest omits terminal tokens");
ok(!("fonts" in res.details.manifest.design), "IHTC-branded genre manifest omits terminal fonts");
const insightsTokens = await fs.readFile(path.join(tmp, "subsite-artifacts/insights/tokens.css"), "utf8");
ok(
  insightsTokens.includes("Theme-specific tokens intentionally omitted") &&
    insightsTokens.includes("starter.dyuhaus.com/noir/"),
  "IHTC-branded genre artifact preserves the selected genre palette and type",
);
const insightsPage = await fs.readFile(path.join(tmp, "insights/index.html"), "utf8");
const insightsStyles = await fs.readFile(path.join(tmp, "insights/styles.css"), "utf8");
const noirStyles = await fs.readFile(path.join(tmp, "starter/noir/styles.css"), "utf8");
ok(insightsPage.includes("Courier+Prime") && !insightsPage.includes('class="term-window"'), "Noir selection produces the Noir page, not terminal chrome");
ok(insightsPage.includes("<title>IHTC Insights</title>"), "genre scaffold receives the project title");
ok(insightsStyles === noirStyles, "genre scaffold copies the confirmed template stylesheet exactly");
ok(typeof res.details?.zip === "string" && existsSync(res.details.zip), `zip/tar archive created: ${res.details?.zip}`);

let rerunSelections = 0;
const rerunCtx = {
  cwd: tmp,
  hasUI: true,
  mode: "tui",
  ui: { notify: () => {}, select: async () => { rerunSelections++; return "Horror"; } },
};
const beforeRerun = await treeFingerprint(tmp);
const rerun = await tool.execute(
  "existing-rerun",
  { slug: "insights", title: "Changed title" },
  undefined,
  undefined,
  rerunCtx,
);
ok(!rerun.isError && rerun.content[0].text.includes("reused its persisted creation settings"), "existing rerun reuses recorded settings");
ok(rerunSelections === 0, "existing rerun does not ask for a new-site theme");
ok(rerun.details?.manifest?.site?.title === "IHTC Insights", "existing rerun ignores conflicting creation inputs");
ok((await treeFingerprint(tmp)) === beforeRerun, "idempotent existing rerun changes no repo file");

await copyDir(
  path.join(tmp, "subsite-artifacts/insights"),
  path.join(tmp, "subsite-artifacts/copied-theme"),
);
const copiedArtifactBefore = await treeFingerprint(tmp);
const copiedArtifact = await tool.execute(
  "copied-artifact",
  { slug: "copied-theme" },
  undefined,
  undefined,
  rpcCtx,
);
ok(copiedArtifact.isError, "copied artifact cannot masquerade as an existing site");
ok(
  copiedArtifact.content[0].text.includes("identifies a different site"),
  "orphaned artifact is refused instead of reusing its theme",
);
ok((await treeFingerprint(tmp)) === copiedArtifactBefore, "copied-artifact refusal changes no repo file");

await copyDir(
  path.join(tmp, "subsite-artifacts/insights"),
  path.join(tmp, "subsite-artifacts/renamed-theme"),
);
await fs.mkdir(path.join(tmp, "renamed-theme"));
const renamedArtifactBefore = await treeFingerprint(tmp);
const renamedArtifact = await tool.execute(
  "renamed-artifact",
  { slug: "renamed-theme" },
  undefined,
  undefined,
  rpcCtx,
);
ok(renamedArtifact.isError, "renamed artifact cannot supply settings for a different site");
ok(
  renamedArtifact.content[0].text.includes("identifies a different site"),
  "manifest identity must match the existing site",
);
ok((await treeFingerprint(tmp)) === renamedArtifactBefore, "renamed-artifact refusal changes no repo file");

const downgradedManifest = JSON.parse(
  (await fs.readFile(path.join(tmp, "subsite-artifacts/insights/site.manifest.json"), "utf8")).replaceAll(
    "insights",
    "downgraded-theme",
  ),
);
downgradedManifest.schema = "dyuhaus.subsite-artifact/v1";
downgradedManifest.design.style = "dyuhaus-terminal-house-style";
delete downgradedManifest.design.template;
await fs.mkdir(path.join(tmp, "subsite-artifacts/downgraded-theme"), { recursive: true });
await fs.writeFile(
  path.join(tmp, "subsite-artifacts/downgraded-theme/site.manifest.json"),
  JSON.stringify(downgradedManifest, null, 2) + "\n",
);
await fs.mkdir(path.join(tmp, "downgraded-theme"), { recursive: true });
await fs.writeFile(path.join(tmp, "downgraded-theme/index.html"), "forged legacy entry\n");
const downgraded = await tool.execute("downgraded", { slug: "downgraded-theme" }, undefined, undefined, rpcCtx);
ok(downgraded.isError, "unknown site cannot bypass confirmation by downgrading to the legacy schema");

const forgedManifest = JSON.parse(
  (await fs.readFile(path.join(tmp, "subsite-artifacts/insights/site.manifest.json"), "utf8")).replaceAll(
    "insights",
    "forged-pending",
  ),
);
const forgedDir = path.join(tmp, "subsite-artifacts/forged-pending");
await fs.mkdir(forgedDir, { recursive: true });
await fs.writeFile(path.join(forgedDir, "site.manifest.json"), JSON.stringify(forgedManifest, null, 2) + "\n");
const forgedBefore = await treeFingerprint(tmp);
const forgedRpc = await tool.execute("forged-pending", { slug: "forged-pending" }, undefined, undefined, rpcCtx);
ok(forgedRpc.isError, "caller-authored pending manifest cannot authorize an RPC retry");
ok((await treeFingerprint(tmp)) === forgedBefore, "forged pending RPC refusal changes no repo file");

const forgedConfirmed = await tool.execute(
  "forged-pending-confirmed",
  { slug: "forged-pending" },
  undefined,
  undefined,
  toolCtx("Noir"),
);
ok(!forgedConfirmed.isError, "local TUI confirmation can resume matching pending settings");
ok(existsSync(path.join(tmp, "forged-pending/index.html")), "confirmed pending retry creates the site");
ok(
  existsSync(path.join(tmp, "subsite-artifacts/forged-pending/scaffold.complete.json")),
  "confirmed retry publishes completion only after the scaffold succeeds",
);

const legacyBefore = await treeFingerprint(tmp);
const legacy = await tool.execute("legacy", { slug: "jobs", dryRun: true }, undefined, undefined, ctx);
ok(!legacy.isError && legacy.details?.manifest?.design?.template?.key === "ihtc", "legacy site reuses its terminal theme without prompting");
ok((await treeFingerprint(tmp)) === legacyBefore, "legacy dry run changes no repo file");

// dryRun should write nothing new
const res2 = await tool.execute(
  "t2",
  { slug: "another", dryRun: true },
  undefined,
  undefined,
  toolCtx("Literary"),
);
ok(res2.content[0].text.startsWith("DRY RUN"), "dryRun reports plan");
ok(!existsSync(path.join(tmp, "another")), "dryRun wrote nothing");

// The interactive command itself must ask for a theme; selecting one is the
// confirmation event that permits the command to reach apply().
const interactiveTmp = await fs.mkdtemp(path.join(os.tmpdir(), "dyuhaus-command-"));
await copyDir("/home/dyadmin/githubStaging/dyuhaus.com", interactiveTmp);
const inputValues = ["verse", "Verse", "A poetry project.", ""];
const selectValues = ["Poetry", "none", "static"];
const confirmValues = [false, false, true];
const selectLabels = [];
const interactiveController = new AbortController();
let interactiveThemeSignal = false;
const interactiveCtx = {
  cwd: interactiveTmp,
  hasUI: true,
  mode: "tui",
  signal: interactiveController.signal,
  ui: {
    input: async () => inputValues.shift(),
    select: async (label, _values, options) => {
      selectLabels.push(label);
      if (label.startsWith("Which theme should this new site use?")) {
        interactiveThemeSignal = options?.signal === interactiveController.signal;
      }
      return selectValues.shift();
    },
    confirm: async () => confirmValues.shift(),
    notify: () => {},
  },
};
await commands.get("new-subsite").handler("", interactiveCtx);
ok(
  selectLabels[0]?.includes("https://starter.dyuhaus.com/"),
  "interactive command shows the live library before theme selection",
);
ok(interactiveThemeSignal, "interactive command passes its abort signal to the theme selector");
ok(existsSync(path.join(interactiveTmp, "verse/index.html")), "confirmed interactive command creates site");
const interactiveManifest = JSON.parse(
  await fs.readFile(path.join(interactiveTmp, "subsite-artifacts/verse/site.manifest.json"), "utf8"),
);
ok(interactiveManifest.design.template.key === "poetry", "interactive manifest carries selected theme");
ok(!("tokens" in interactiveManifest.design), "neutral genre manifest omits generic tokens");
ok(!("fonts" in interactiveManifest.design), "neutral genre manifest omits generic fonts");
const interactiveTokens = await fs.readFile(
  path.join(interactiveTmp, "subsite-artifacts/verse/tokens.css"),
  "utf8",
);
ok(
  interactiveTokens.includes("Theme-specific tokens intentionally omitted") &&
    interactiveTokens.includes("starter.dyuhaus.com/poetry/"),
  "neutral genre artifact points to the confirmed template without fallback tokens",
);

const personalIhtc = await tool.execute(
  "personal-ihtc",
  { slug: "personal-ihtc", brand: "personal", mode: "static" },
  undefined,
  undefined,
  toolCtx("IHTC"),
);
ok(!personalIhtc.isError, "IHTC theme supports non-company branding");
const personalIhtcStyles = await fs.readFile(path.join(tmp, "personal-ihtc/styles.css"), "utf8");
const personalIhtcTokens = await fs.readFile(
  path.join(tmp, "subsite-artifacts/personal-ihtc/tokens.css"),
  "utf8",
);
const cssVariables = (source) => Object.fromEntries(
  [...source.matchAll(/--([\w-]+)\s*:\s*([^;]+);/g)].map((match) => [match[1], match[2].trim()]),
);
const scaffoldIhtcVariables = cssVariables(personalIhtcStyles.match(/:root\s*\{[\s\S]*?\}/)?.[0] ?? "");
const artifactIhtcVariables = cssVariables(personalIhtcTokens);
ok(
  JSON.stringify(artifactIhtcVariables) === JSON.stringify(scaffoldIhtcVariables),
  "IHTC artifact tokens exactly match the copied stylesheet variable contract",
);
ok(
  JSON.stringify(personalIhtc.details?.manifest?.design?.tokens) === JSON.stringify(scaffoldIhtcVariables),
  "IHTC manifest tokens exactly match the copied stylesheet variable contract",
);
ok(
  !personalIhtcStyles.includes("--accent: #4f9cf9") && !personalIhtcTokens.includes("--accent: #4f9cf9"),
  "personal brand metadata cannot replace the confirmed IHTC visual theme",
);

const existingConfirmLabels = [];
let existingSelects = 0;
await commands.get("new-subsite").handler("verse", {
  cwd: interactiveTmp,
  hasUI: true,
  mode: "tui",
  ui: {
    select: async () => { existingSelects++; return undefined; },
    confirm: async (label) => {
      existingConfirmLabels.push(label);
      return label === "Apply this plan?";
    },
    notify: () => {},
  },
});
ok(existingSelects === 0, "completed-site command does not ask for the theme again");
ok(existingConfirmLabels[0] === "Zip artifact to ~/transfer?", "completed-site command keeps the archive option");

// cleanup archive from transfer to avoid clutter
if (res.details?.zip && existsSync(res.details.zip)) await fs.rm(res.details.zip);

console.log(`\n${failures === 0 ? "LOAD TEST PASS" : failures + " FAILURE(S)"}`);
process.exit(failures === 0 ? 0 : 1);
