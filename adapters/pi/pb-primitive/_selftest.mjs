import assert from "node:assert/strict";
import { promises as fs } from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const PIROOT = "/home/dyadmin/.hermes/node/lib/node_modules/@earendil-works/pi-coding-agent";
const { createJiti } = await import(`${PIROOT}/node_modules/jiti/lib/jiti.mjs`);
const here = path.dirname(fileURLToPath(import.meta.url));
const jiti = createJiti(import.meta.url, {
	interopDefault: true,
	alias: {
		"@earendil-works/pi-coding-agent": `${PIROOT}/dist/index.js`,
		"@earendil-works/pi-agent-core": `${PIROOT}/node_modules/@earendil-works/pi-agent-core/dist/index.js`,
		"@earendil-works/pi-ai": `${PIROOT}/node_modules/@earendil-works/pi-ai/dist/index.js`,
		"@earendil-works/pi-tui": `${PIROOT}/node_modules/@earendil-works/pi-tui/dist/index.js`,
		typebox: `${PIROOT}/node_modules/typebox/build/index.mjs`,
	},
});

const config = await jiti.import(path.join(here, "config.ts"));
const roles = await jiti.import(path.join(here, "roles.ts"));
const subagent = await jiti.import(path.join(here, "subagent.ts"));
const indexModule = await jiti.import(path.join(here, "index.ts"));

const valid = {
	version: 1,
	roles: {
		planner: { purpose: "reason", readOnly: true, model: { class: "fable", id: "", provider: "anthropic" } },
		builder: { purpose: "build", readOnly: false, model: { class: "opus", id: "claude-opus-pinned", provider: "anthropic" } },
	},
	providers: { anthropic: { type: "anthropic", apiKeyEnv: "ANTHROPIC_API_KEY", baseUrlEnv: "" } },
};

assert.deepEqual(config.validateConfig(valid), []);
assert.ok(config.validateConfig({ version: 0, roles: {}, providers: {} }).length >= 3);
assert.equal(config.resolveModel(valid.roles.builder), "claude-opus-pinned");
assert.equal(config.roleView(valid, "planner").model, "fable");
assert.deepEqual(config.roleView(valid, "planner").infoSources, []);

const root = await fs.mkdtemp(path.join(os.tmpdir(), "pb-primitive-test-"));
const child = path.join(root, "a", "b");
await fs.mkdir(child, { recursive: true });
await fs.writeFile(path.join(root, "roles.config.json"), JSON.stringify(valid));
assert.equal(path.resolve(config.resolveConfigPath(child).path), path.join(root, "roles.config.json"));
await fs.mkdir(path.join(root, "a", ".pi"), { recursive: true });
await fs.writeFile(path.join(root, "a", ".pi", "roles.config.json"), JSON.stringify(valid));
assert.equal(path.resolve(config.resolveConfigPath(child).path), path.join(root, "a", ".pi", "roles.config.json"));

// Pi-only overlay precedence. A project config always wins; when absent a
// complete, valid Pi overlay wins; an invalid/missing overlay safely falls back.
const defaultsRoot = await fs.mkdtemp(path.join(os.tmpdir(), "pb-defaults-test-"));
const defaultsCwd = path.join(defaultsRoot, "work");
await fs.mkdir(defaultsCwd, { recursive: true });
const machinePath = path.join(defaultsRoot, "machine.json");
const overlayPath = path.join(defaultsRoot, "overlay.json");
const overlay = structuredClone(valid);
overlay.roles.planner.model = { class: "moonshotai/kimi-k3", id: "moonshotai/kimi-k3", provider: "openrouter" };
overlay.roles.builder.model = { class: "openai/gpt-5.6-terra", id: "openai/gpt-5.6-terra", provider: "openrouter" };
overlay.providers.openrouter = { type: "openai", apiKeyEnv: "OPENROUTER_API_KEY", baseUrlEnv: "OPENROUTER_BASE_URL" };
await fs.writeFile(machinePath, JSON.stringify(valid));
await fs.writeFile(overlayPath, JSON.stringify(overlay));
let resolved = config.loadResolved(defaultsCwd, { machineDefault: machinePath, piOverlay: overlayPath });
assert.equal(resolved.sourceKind, "pi-overlay");
assert.equal(config.roleView(resolved.cfg, "planner").model, "moonshotai/kimi-k3");
assert.equal(config.roleView(resolved.cfg, "builder").model, "openai/gpt-5.6-terra");
await fs.writeFile(path.join(defaultsRoot, "roles.config.json"), JSON.stringify(valid));
resolved = config.loadResolved(defaultsCwd, { machineDefault: machinePath, piOverlay: overlayPath });
assert.equal(resolved.sourceKind, "project");
assert.equal(config.roleView(resolved.cfg, "planner").model, "fable");
await fs.rm(path.join(defaultsRoot, "roles.config.json"));
await fs.writeFile(overlayPath, "not json");
resolved = config.loadResolved(defaultsCwd, { machineDefault: machinePath, piOverlay: overlayPath });
assert.equal(resolved.sourceKind, "machine");
assert.match(resolved.overlayWarning, /Pi overlay unavailable/);
assert.equal(config.roleView(resolved.cfg, "planner").model, "fable");
resolved = config.loadResolved(defaultsCwd, { machineDefault: machinePath, piOverlay: path.join(defaultsRoot, "missing.json") });
assert.equal(resolved.sourceKind, "machine");
assert.match(resolved.overlayWarning, /Pi overlay unavailable/);

assert.deepEqual(config.parseTaskAndUntil("build it until: tests pass"), { task: "build it", until: "tests pass" });
assert.deepEqual(config.parseTaskAndUntil("explain until loops"), { task: "explain until loops", until: null });
assert.deepEqual(config.parseTaskAndUntil("task until: one until: final condition"), {
	task: "task until: one",
	until: "final condition",
});

const plannerArgs = roles.buildChildArgs(config.roleView(valid, "planner"), { thinking: "high" });
assert.ok(plannerArgs.includes("--no-session"));
assert.ok(plannerArgs.includes("anthropic"));
assert.ok(plannerArgs.includes("fable"));
assert.equal(plannerArgs[plannerArgs.indexOf("--tools") + 1], "read,grep,find,ls");
assert.ok(!plannerArgs.includes("bash"));
const builderArgs = roles.buildChildArgs(config.roleView(valid, "builder"));
assert.ok(builderArgs.includes("claude-opus-pinned"));
assert.ok(!builderArgs.includes("--tools"));

const tools = new Map();
const commands = new Map();
const renderers = new Map();
const events = new Map();
const pi = {
	registerTool: (def) => tools.set(def.name, def),
	registerCommand: (name, def) => commands.set(name, def),
	registerMessageRenderer: (name, renderer) => renderers.set(name, renderer),
	on: (name, handler) => events.set(name, handler),
	sendMessage: () => {},
};
const factory = indexModule.default ?? indexModule;
await factory(pi);
assert.deepEqual([...tools.keys()].sort(), [
	"builder_agent",
	"fe_designer_agent",
	"l1_programmer_agent",
	"librarian_agent",
	"planner_agent",
	"prose_writer_agent",
	"runner_agent",
	"team_leader_agent",
	"tech_writer_agent",
]);
assert.ok(commands.has("pb"));
assert.ok(commands.has("pbg"));
assert.ok(commands.has("pb-show"));
assert.ok(commands.has("agents"), "missing /agents command");
assert.ok(commands.has("route"), "missing /route command");
await assert.rejects(
	() => tools.get("team_leader_agent").execute("test", { task: "coordinate" }, new AbortController().signal, () => {}, { cwd: root }),
	/direct-call-only/,
);
assert.deepEqual(indexModule.parseRouterDecision(JSON.stringify({
	status: "recommendation", selected: "runner", confidence: 0.6, reasons: ["test"],
	candidates: [{ agent: "runner", score: 1 }], needs_clarification: true, questions: ["question"],
})).selected, "runner");
assert.throws(() => indexModule.parseRouterDecision("{}"), /invalid recommendation/);
assert.equal(indexModule.shouldAutoRouteInput("Update the README", "interactive"), true);
assert.equal(indexModule.shouldAutoRouteInput("/pb Update the README", "interactive"), false);
assert.equal(indexModule.shouldAutoRouteInput("Update the README", "rpc"), false);
assert.equal(indexModule.shouldAutoRouteInput("Update the README", "interactive", true), false);
assert.equal(config.loadResolved("/home/dyadmin").cfg.routing.automaticSelection.enabled, true);
for (const key of ["planner", "builder", "runner", "tech-writer", "prose-writer", "team-leader", "l1-programmer", "librarian", "fe-designer"]) {
	assert.ok(commands.has(key), `missing /${key} command`);
	assert.ok(commands.has(`${key}-model`), `missing /${key}-model command`);
}
assert.ok(renderers.has("pb-primitive-report"));
assert.ok(events.has("session_shutdown"));

// Offline child-process smoke test. A fake `pi` executable emits canonical JSON
// events, allowing JSONL parsing, temp-prompt lifecycle, result handling, and
// read-only argv enforcement to be tested without a provider/model call.
const fakeDir = await fs.mkdtemp(path.join(os.tmpdir(), "pb-fake-pi-"));
const fakePi = path.join(fakeDir, "pi");
const argsFile = path.join(fakeDir, "args.json");
const promptCopy = path.join(fakeDir, "prompt-copy.txt");
await fs.writeFile(
	fakePi,
	`#!/usr/bin/env node\nconst fs=require("node:fs");\nconst args=process.argv.slice(2);\nfs.writeFileSync(process.env.PB_ARGS_FILE, JSON.stringify(args));\nconst i=args.indexOf("--append-system-prompt");\nif(i>=0) fs.writeFileSync(process.env.PB_PROMPT_COPY, fs.readFileSync(args[i+1], "utf8"));\nconst message={role:"assistant",content:[{type:"text",text:"FAKE CHILD OK"}],api:"test",provider:"test",model:"test-model",usage:{input:3,output:2,cacheRead:0,cacheWrite:0,totalTokens:5,cost:{input:0,output:0,cacheRead:0,cacheWrite:0,total:0}},stopReason:"stop",timestamp:Date.now()};\nconsole.log(JSON.stringify({type:"message_end",message}));\n`,
	{ mode: 0o755 },
);
const oldPath = process.env.PATH;
process.env.PATH = `${fakeDir}:${oldPath ?? ""}`;
process.env.PB_ARGS_FILE = argsFile;
process.env.PB_PROMPT_COPY = promptCopy;
const savedArgv1 = process.argv[1];
process.argv[1] = "/nonexistent/pi-entry.js";
const fakeResult = await subagent.runRole({
	cwd: root,
	view: config.roleView(valid, "planner"),
	systemPrompt: "OFFLINE ROLE PROMPT",
	prompt: "Task: offline smoke",
	timeoutMs: 5000,
});
process.argv[1] = savedArgv1;
process.env.PATH = oldPath;
assert.equal(subagent.isFailed(fakeResult), false);
assert.equal(subagent.getFinalOutput(fakeResult.messages), "FAKE CHILD OK");
const fakeArgs = JSON.parse(await fs.readFile(argsFile, "utf8"));
assert.equal(fakeArgs[fakeArgs.indexOf("--tools") + 1], "read,grep,find,ls");
assert.equal(await fs.readFile(promptCopy, "utf8"), "OFFLINE ROLE PROMPT");
const tempPromptPath = fakeArgs[fakeArgs.indexOf("--append-system-prompt") + 1];
await assert.rejects(fs.access(tempPromptPath));
assert.equal(subagent.liveChildCount(), 0);

assert.deepEqual(indexModule.parseModelCommandArguments("moonshotai/kimi-k3 --provider openrouter --id exact/kimi"), {
	model: "moonshotai/kimi-k3", provider: "openrouter", id: "exact/kimi",
});
assert.deepEqual(indexModule.parseModelCommandArguments("--provider openrouter --id openai/gpt-5.6-terra"), {
	provider: "openrouter", id: "openai/gpt-5.6-terra",
});
assert.throws(() => indexModule.parseModelCommandArguments("model --unknown value"), /unknown flag/);
assert.throws(() => indexModule.parseModelCommandArguments("--provider"), /needs a value/);

const writableConfigPath = path.join(defaultsRoot, "writable-overlay.json");
const writable = structuredClone(overlay);
await fs.writeFile(writableConfigPath, JSON.stringify(writable));
const mutation = config.mutateModel(writable, "builder", { model: "openai/gpt-5.6-terra", provider: "openrouter", id: "openai/gpt-5.6-terra" });
assert.ok(mutation.some((change) => change.includes("gpt-5.6-terra")));
const normalized = config.mutateModel(writable, "planner", { model: "openrouter/moonshotai/kimi-k3", provider: "openrouter" });
assert.ok(normalized.some((change) => change.includes("moonshotai/kimi-k3")));
assert.equal(writable.roles.planner.model.class, "moonshotai/kimi-k3");
assert.deepEqual(config.validateConfig(writable), []);
const routed = structuredClone(valid);
routed.agents = { runner: { displayName: "Runner", purpose: "routine", readOnly: false, model: { class: "sonnet", provider: "anthropic" }, tools: [], invocation: "default", autoSelectEligible: true, capabilities: [], boundaries: [], escalateTo: [], canDelegate: false, delegateTo: [], outputContract: [], infoSources: ["read docs"] } };
routed.routing = { automaticSelection: { enabled: true, status: "confirmation-required", threshold: 0.6, fallback: "runner", audit: { enabled: false, path: "runtime/audit.jsonl" } } };
assert.deepEqual(config.validateConfig(routed), []);
config.writeConfigAtomic(writableConfigPath, writable);
const persisted = JSON.parse(await fs.readFile(writableConfigPath, "utf8"));
assert.equal(persisted.roles.builder.model.id, "openai/gpt-5.6-terra");
assert.equal(persisted.roles.planner.model.class, "moonshotai/kimi-k3");
assert.equal(valid.roles.planner.model.class, "fable");

const machine = config.loadResolved("/home/dyadmin");
assert.equal(machine.loadError, null);
assert.equal(machine.sourceKind, "pi-overlay");
assert.equal(machine.overlayWarning, null);
assert.deepEqual(machine.errors, []);
assert.match(config.renderValidatedReport(machine.cfg), /planner\s+-> model 'moonshotai\/kimi-k3'/);
assert.match(config.renderValidatedReport(machine.cfg), /builder\s+-> model 'openai\/gpt-5\.6-terra'/);

await fs.rm(root, { recursive: true, force: true });
await fs.rm(defaultsRoot, { recursive: true, force: true });
await fs.rm(fakeDir, { recursive: true, force: true });
console.log("pb-primitive self-test: PASS (offline; no model calls)");
