// Load test: import index.ts exactly as pi would (jiti), with the pi-provided
// packages aliased to pi's install, feed it a stub ExtensionAPI, and confirm
// registration runs. Validates all imports resolve + code executes (no model call).
import { promises as fs } from "node:fs";
import { existsSync } from "node:fs";
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
ok(!!tool.parameters?.properties?.brand, "schema has StringEnum brand property");
ok(Array.isArray(tool.promptGuidelines) && tool.promptGuidelines.length > 0, "tool has promptGuidelines");

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
const tmp = await fs.mkdtemp(path.join(os.tmpdir(), "dyuhaus-load-"));
await copyDir("/home/dyadmin/githubStaging/dyuhaus.com", tmp);

const ctx = { cwd: tmp, hasUI: false, mode: "print", ui: { notify: () => {} } };
const res = await tool.execute(
  "t1",
  { slug: "insights", title: "IHTC Insights", description: "Reports.", brand: "ihtc", zipArtifact: true },
  undefined,
  undefined,
  ctx,
);
ok(!res.isError, "tool.execute returned success");
ok(existsSync(path.join(tmp, "insights/index.html")), "tool created insights/index.html");
ok(existsSync(path.join(tmp, "subsite-artifacts/insights/site.manifest.json")), "tool created artifact manifest");
ok(res.details && res.details.manifest?.site?.subdomain === "insights.dyuhaus.com", "result details carry manifest");
ok(typeof res.details?.zip === "string" && existsSync(res.details.zip), `zip/tar archive created: ${res.details?.zip}`);

// dryRun should write nothing new
const before = await fs.readdir(tmp);
const res2 = await tool.execute("t2", { slug: "another", dryRun: true }, undefined, undefined, ctx);
ok(res2.content[0].text.startsWith("DRY RUN"), "dryRun reports plan");
ok(!existsSync(path.join(tmp, "another")), "dryRun wrote nothing");

// cleanup archive from transfer to avoid clutter
if (res.details?.zip && existsSync(res.details.zip)) await fs.rm(res.details.zip);

console.log(`\n${failures === 0 ? "LOAD TEST PASS" : failures + " FAILURE(S)"}`);
process.exit(failures === 0 ? 0 : 1);
