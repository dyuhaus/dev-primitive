import assert from "node:assert/strict";
import { promises as fs } from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const PIROOT = process.env.PI_CODING_AGENT_ROOT ?? "/home/dyadmin/.hermes/node/lib/node_modules/@earendil-works/pi-coding-agent";
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

// Exercise the active OpenAI registry, not a historical Anthropic fixture: Pi
// must carry each role's registered effort instead of inheriting ambient state.
const valid = JSON.parse(await fs.readFile(path.resolve(here, "../../../roles.config.json"), "utf8"));

assert.deepEqual(config.validateConfig(valid), []);
assert.ok(config.validateConfig({ version: 0, roles: {}, providers: {} }).length >= 3);
assert.equal(config.resolveModel(valid.roles.builder), "gpt-5.6-terra");
assert.equal(config.roleView(valid, "planner").model, "gpt-5.6-sol");
assert.equal(config.roleView(valid, "planner").effort, "xhigh");
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
overlay.roles.planner.model = { class: "gpt-5.6-sol", id: "gpt-5.6-sol", provider: "openrouter", effort: "xhigh" };
overlay.roles.builder.model = { class: "gpt-5.6-terra", id: "gpt-5.6-terra", provider: "openrouter", effort: "xhigh" };
overlay.providers.openrouter = { type: "openai", apiKeyEnv: "OPENROUTER_API_KEY", baseUrlEnv: "OPENROUTER_BASE_URL" };
overlay.routing = {
	postWorkflowAudit: {
		enabled: true,
		model: { class: "gpt-5.6-sol", id: "gpt-5.6-sol", provider: "openrouter", effort: "xhigh" },
		thinking: "xhigh",
	},
};
await fs.writeFile(machinePath, JSON.stringify(valid));
await fs.writeFile(overlayPath, JSON.stringify(overlay));
let resolved = config.loadResolved(defaultsCwd, { machineDefault: machinePath, piOverlay: overlayPath });
assert.equal(resolved.sourceKind, "pi-overlay");
assert.equal(config.roleView(resolved.cfg, "planner").model, "gpt-5.6-sol");
assert.equal(config.roleView(resolved.cfg, "builder").model, "gpt-5.6-terra");
assert.equal(resolved.cfg.routing.postWorkflowAudit.thinking, "xhigh");
const disabledAuditConfig = structuredClone(overlay);
disabledAuditConfig.routing.postWorkflowAudit = { enabled: false };
assert.deepEqual(config.validateConfig(disabledAuditConfig), []);
const defaultThinkingConfig = structuredClone(overlay);
delete defaultThinkingConfig.routing.postWorkflowAudit.thinking;
assert.deepEqual(config.validateConfig(defaultThinkingConfig), []);
await fs.writeFile(path.join(defaultsRoot, "roles.config.json"), JSON.stringify(valid));
resolved = config.loadResolved(defaultsCwd, { machineDefault: machinePath, piOverlay: overlayPath });
assert.equal(resolved.sourceKind, "project");
assert.equal(config.roleView(resolved.cfg, "planner").model, "gpt-5.6-sol");
await fs.rm(path.join(defaultsRoot, "roles.config.json"));
await fs.writeFile(overlayPath, "not json");
resolved = config.loadResolved(defaultsCwd, { machineDefault: machinePath, piOverlay: overlayPath });
assert.equal(resolved.sourceKind, "machine");
assert.match(resolved.overlayWarning, /Pi overlay unavailable/);
assert.equal(config.roleView(resolved.cfg, "planner").model, "gpt-5.6-sol");
resolved = config.loadResolved(defaultsCwd, { machineDefault: machinePath, piOverlay: path.join(defaultsRoot, "missing.json") });
assert.equal(resolved.sourceKind, "machine");
assert.match(resolved.overlayWarning, /Pi overlay unavailable/);

assert.deepEqual(config.parseTaskAndUntil("build it until: tests pass"), { task: "build it", until: "tests pass" });
assert.deepEqual(config.parseTaskAndUntil("explain until loops"), { task: "explain until loops", until: null });
assert.deepEqual(config.parseTaskAndUntil("task until: one until: final condition"), {
	task: "task until: one",
	until: "final condition",
});

const plannerArgs = roles.buildChildArgs(config.roleView(valid, "planner"));
assert.ok(plannerArgs.includes("--no-session"));
assert.ok(plannerArgs.includes("--no-extensions"), "child Pi must not recursively load global routing/extensions");
assert.ok(plannerArgs.includes("openai"));
assert.ok(plannerArgs.includes("gpt-5.6-sol"));
assert.equal(plannerArgs[plannerArgs.indexOf("--thinking") + 1], "xhigh");
assert.equal(plannerArgs[plannerArgs.indexOf("--tools") + 1], "read,grep,find,ls");
assert.ok(!plannerArgs.includes("bash"));
const builderArgs = roles.buildChildArgs(config.roleView(valid, "builder"));
assert.ok(builderArgs.includes("gpt-5.6-terra"));
assert.equal(builderArgs[builderArgs.indexOf("--thinking") + 1], "xhigh");
assert.ok(!builderArgs.includes("--tools"));
const auditView = config.roleView({ ...overlay, agents: { "workflow-audit": { purpose: "audit", readOnly: true, model: overlay.routing.postWorkflowAudit.model } } }, "workflow-audit");
const auditArgs = roles.buildChildArgs(auditView);
assert.equal(auditView.model, "gpt-5.6-sol");
assert.equal(auditArgs[auditArgs.indexOf("--thinking") + 1], "xhigh");
assert.equal(auditArgs[auditArgs.indexOf("--tools") + 1], "read,grep,find,ls");
assert.match(roles.workflowAuditSystemPrompt(), /smaller and more focused than the direct-call Audit specialist/);

const missingOpenAiEffort = structuredClone(valid);
delete missingOpenAiEffort.roles.planner.model.effort;
assert.ok(config.validateConfig(missingOpenAiEffort).some((error) => /model\.effort is required for OpenAI/.test(error)));
const invalidOpenAiEffort = structuredClone(valid);
invalidOpenAiEffort.roles.planner.model.effort = "ambient";
assert.ok(config.validateConfig(invalidOpenAiEffort).some((error) => /model\.effort must be a supported/.test(error)));
assert.throws(() => roles.buildChildArgs({ ...config.roleView(valid, "planner"), effort: null }), /refusing ambient Pi thinking/);

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
	"audit_agent",
	"builder_agent",
	"code_reviewer_agent",
	"fe_designer_agent",
	"l1_programmer_agent",
	"librarian_agent",
	"planner_agent",
	"prose_writer_agent",
	"runner_agent",
	"team_leader_agent",
	"tech_writer_agent",
	"workflow_audit",
]);
assert.ok(commands.has("pb"));
assert.ok(commands.has("pbg"));
assert.ok(commands.has("pb-show"));
assert.ok(commands.has("agents"), "missing /agents command");
assert.ok(commands.has("route"), "missing /route command");
assert.ok(tools.has("workflow_audit"), "missing lightweight post-workflow audit tool");
assert.match(tools.get("workflow_audit").promptGuidelines.join(" "), /exactly once/);
await assert.rejects(
	() => tools.get("team_leader_agent").execute("test", { task: "coordinate" }, new AbortController().signal, () => {}, { cwd: root }),
	/direct-call-only/,
);
await assert.rejects(
	() => tools.get("audit_agent").execute("test", { task: "audit Pi" }, new AbortController().signal, () => {}, { cwd: root }),
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
const realRouter = "/home/dyadmin/dev-primitive/router.py";
const sourceConfig = "/home/dyadmin/dev-primitive/roles.config.json";
const genericImplementation = await indexModule.getRouteDecision("Implement authentication caching and tests", root, sourceConfig, undefined, { routerPath: realRouter, timeoutMs: 5000 });
assert.equal(genericImplementation.selected, "planner", "planBeforeBuild must keep substantive generic implementation on the Planner → Builder path");
assert.match(genericImplementation.reasons.join(" "), /Planner must produce the plan before Builder/);
const outlinedImplementation = await indexModule.getRouteDecision("Following this exact outline, add a small parser script and unit test", root, sourceConfig, undefined, { routerPath: realRouter, timeoutMs: 5000 });
assert.equal(outlinedImplementation.selected, "l1-programmer", "small explicitly outlined work may bypass PB");
await assert.rejects(
	() => indexModule.getRouteDecision("test", root, machinePath, undefined, { routerPath: path.join(root, "missing-router.py"), timeoutMs: 100 }),
	/router.py exited|ENOENT/,
);
const slowRouter = path.join(root, "slow-router.py");
await fs.writeFile(slowRouter, "import time\ntime.sleep(5)\n");
await assert.rejects(
	() => indexModule.getRouteDecision("test", root, machinePath, undefined, { routerPath: slowRouter, timeoutMs: 50 }),
	/timed out/,
);
const acceptedRoute = indexModule.formatAcceptedRoute({
	status: "recommendation", selected: "fe-designer", confidence: 0.95, reasons: ["frontend"],
	candidates: [{ agent: "fe-designer", score: 12 }], needs_clarification: false, questions: [],
}, "FE-Designer", "Build the original frontend prompt");
assert.match(acceptedRoute, /## Accepted task/);
assert.match(acceptedRoute, /Build the original frontend prompt/);
assert.match(acceptedRoute, /Delegating to \*\*FE-Designer\*\*/);
assert.equal(overlay.routing?.automaticSelection?.enabled ?? false, false);
for (const key of ["planner", "builder", "runner", "tech-writer", "prose-writer", "team-leader", "l1-programmer", "librarian", "fe-designer", "audit"]) {
	assert.ok(commands.has(key), `missing /${key} command`);
	assert.ok(commands.has(`${key}-model`), `missing /${key}-model command`);
}
assert.ok(renderers.has("pb-primitive-report"));
assert.ok(events.has("session_shutdown"));

// Routed work must acknowledge acceptance and clean up RPC-compatible progress
// UI on both success and failure.
const statusUpdates = [];
const widgetUpdates = [];
const progressCtx = {
	hasUI: true,
	mode: "rpc",
	signal: undefined,
	ui: {
		setStatus: (key, value) => statusUpdates.push([key, value]),
		setWidget: (key, value) => widgetUpdates.push([key, value]),
	},
};
assert.equal(await indexModule.withRouteProgress(progressCtx, "FE-Designer", "Build the frontend", async () => "done"), "done");
assert.match(statusUpdates[0][1], /Running FE-Designer/);
assert.match(widgetUpdates[0][1][0], /Accepted → FE-Designer/);
assert.equal(statusUpdates.at(-1)[1], undefined);
assert.equal(widgetUpdates.at(-1)[1], undefined);
await assert.rejects(
	() => indexModule.withRouteProgress(progressCtx, "FE-Designer", "Fail", async () => { throw new Error("test failure"); }),
	/test failure/,
);
assert.equal(statusUpdates.at(-1)[1], undefined);
assert.equal(widgetUpdates.at(-1)[1], undefined);

// Offline child-process smoke test. A fake `pi` executable emits canonical JSON
// events, allowing JSONL parsing, temp-prompt lifecycle, result handling, and
// read-only argv enforcement to be tested without a provider/model call.
const fakeDir = await fs.mkdtemp(path.join(os.tmpdir(), "pb-fake-pi-"));
const fakePi = path.join(fakeDir, "pi");
const argsFile = path.join(fakeDir, "args.json");
const argsLog = path.join(fakeDir, "args.jsonl");
const promptCopy = path.join(fakeDir, "prompt-copy.txt");
const taskCopy = path.join(fakeDir, "task-copy.txt");
await fs.writeFile(
	fakePi,
		`#!/usr/bin/env node\nconst fs=require("node:fs");\nconst args=process.argv.slice(2);\nfs.writeFileSync(process.env.PB_ARGS_FILE, JSON.stringify(args));\nfs.appendFileSync(process.env.PB_ARGS_LOG, JSON.stringify(args)+"\\n");\nconst i=args.indexOf("--append-system-prompt");\nif(i>=0) fs.writeFileSync(process.env.PB_PROMPT_COPY, fs.readFileSync(args[i+1], "utf8"));\nconst taskArg=args.find((arg)=>arg.startsWith("@"));\nif(taskArg) fs.writeFileSync(process.env.PB_TASK_COPY, fs.readFileSync(taskArg.slice(1), "utf8"));\nconst message={role:"assistant",content:[{type:"text",text:"PB_VERIFY: PASS — FAKE CHILD OK"}],api:"test",provider:"test",model:"test-model",usage:{input:3,output:2,cacheRead:0,cacheWrite:0,totalTokens:5,cost:{input:0,output:0,cacheRead:0,cacheWrite:0,total:0}},stopReason:"stop",timestamp:Date.now()};\nconsole.log(JSON.stringify({type:"message_end",message}));\n`,
	{ mode: 0o755 },
);
const oldPath = process.env.PATH;
process.env.PATH = `${fakeDir}:${oldPath ?? ""}`;
process.env.PB_ARGS_FILE = argsFile;
process.env.PB_ARGS_LOG = argsLog;
process.env.PB_PROMPT_COPY = promptCopy;
process.env.PB_TASK_COPY = taskCopy;
const savedArgv1 = process.argv[1];
process.argv[1] = "/nonexistent/pi-entry.js";
const fakeResult = await subagent.runRole({
	cwd: root,
	view: config.roleView(valid, "planner"),
	systemPrompt: "OFFLINE ROLE PROMPT",
	prompt: "Task: offline smoke",
	timeoutMs: 5000,
});
assert.equal(subagent.isFailed(fakeResult), false);
assert.equal(subagent.getFinalOutput(fakeResult.messages), "PB_VERIFY: PASS — FAKE CHILD OK");
const fakeArgs = JSON.parse(await fs.readFile(argsFile, "utf8"));
assert.equal(fakeArgs[fakeArgs.indexOf("--tools") + 1], "read,grep,find,ls");
assert.equal(await fs.readFile(promptCopy, "utf8"), "OFFLINE ROLE PROMPT");
assert.equal(await fs.readFile(taskCopy, "utf8"), "Task: offline smoke");
assert.ok(!fakeArgs.includes("Task: offline smoke"), "task text must not be passed directly in argv");
const taskArg = fakeArgs.find((arg) => arg.startsWith("@"));
assert.ok(taskArg, "task must be supplied through Pi's @file input");
const tempPromptPath = fakeArgs[fakeArgs.indexOf("--append-system-prompt") + 1];
await assert.rejects(fs.access(tempPromptPath));
await assert.rejects(fs.access(taskArg.slice(1)));
assert.equal(subagent.liveChildCount(), 0);

const auditCwd = path.join(fakeDir, "audit-work");
await fs.mkdir(auditCwd, { recursive: true });
await fs.writeFile(path.join(auditCwd, "roles.config.json"), JSON.stringify(valid));
const auditReport = await indexModule.runPostWorkflowAudit(
	"Implement feature",
	"Plan with acceptance criteria",
	"Builder",
	"Changed files and tests pass",
	{ cwd: auditCwd, signal: undefined },
);
assert.match(auditReport.text, /FAKE CHILD OK/);
const auditRunArgs = JSON.parse(await fs.readFile(argsFile, "utf8"));
assert.equal(auditRunArgs[auditRunArgs.indexOf("--model") + 1], "gpt-5.6-sol");
assert.equal(auditRunArgs[auditRunArgs.indexOf("--thinking") + 1], "xhigh");
assert.equal(auditRunArgs[auditRunArgs.indexOf("--tools") + 1], "read,grep,find,ls");

// Exercise every automated entrypoint through the fake binary. This includes
// direct planner/builder/specialist tools and the pbg continuation path
// (planner, builder, post-workflow reviewer, verifier). Every child must carry
// the registry's OpenAI model and xhigh effort; none may inherit Pi ambient
// thinking or substitute an Anthropic fallback.
const childCtx = { cwd: root, signal: undefined, hasUI: false, mode: "rpc" };
await tools.get("planner_agent").execute("test", { task: "plan safely" }, new AbortController().signal, () => {}, childCtx);
await tools.get("builder_agent").execute("test", { task: "build safely" }, new AbortController().signal, () => {}, childCtx);
await tools.get("runner_agent").execute("test", { task: "run safely" }, new AbortController().signal, () => {}, childCtx);
await commands.get("pbg").handler("complete the test until: child routing is evidenced", childCtx);
const allChildArgs = (await fs.readFile(argsLog, "utf8")).trim().split("\n").filter(Boolean).map((line) => JSON.parse(line));
assert.equal(allChildArgs.length, 9, "planner, builder, specialist, reviewer, and pbg continuation children must all spawn exactly once");
for (const argv of allChildArgs) {
	assert.equal(argv[argv.indexOf("--provider") + 1], "openai", `child provider drifted: ${JSON.stringify(argv)}`);
	assert.ok(["gpt-5.6-sol", "gpt-5.6-terra"].includes(argv[argv.indexOf("--model") + 1]), `child model drifted: ${JSON.stringify(argv)}`);
	assert.equal(argv[argv.indexOf("--thinking") + 1], "xhigh", `child omitted registry xhigh: ${JSON.stringify(argv)}`);
}
assert.ok(allChildArgs.some((argv) => argv[argv.indexOf("--model") + 1] === "gpt-5.6-sol"), "planner/reviewer Sol child was not exercised");
assert.ok(allChildArgs.some((argv) => argv[argv.indexOf("--model") + 1] === "gpt-5.6-terra"), "builder/specialist Terra child was not exercised");
const savedPathForFailure = process.env.PATH;
process.env.PATH = "/nonexistent";
const failedAudit = await indexModule.runPostWorkflowAudit(
	"Implement feature",
	"Plan",
	"Builder",
	"Primary result must survive",
	{ cwd: auditCwd, signal: undefined },
);
process.env.PATH = savedPathForFailure;
assert.match(failedAudit.text, /primary executor result is preserved|failed without changing the primary result/);
process.argv[1] = savedArgv1;
process.env.PATH = oldPath;

// Startup hygiene removes only stale, owned pb prompt directories and leaves
// fresh directories alone.
const staleDir = await fs.mkdtemp(path.join(os.tmpdir(), "pi-pb-primitive-stale-test-"));
const freshDir = await fs.mkdtemp(path.join(os.tmpdir(), "pi-pb-primitive-fresh-test-"));
await fs.writeFile(path.join(staleDir, "prompt-test.md"), "stale", { mode: 0o600 });
const oldTime = new Date(Date.now() - 2 * 60 * 60 * 1000);
await fs.utimes(staleDir, oldTime, oldTime);
assert.ok(subagent.cleanupStalePromptDirs() >= 1);
await assert.rejects(fs.access(staleDir));
await fs.access(freshDir);
await fs.rm(freshDir, { recursive: true, force: true });

assert.deepEqual(indexModule.parseModelCommandArguments("moonshotai/kimi-k3 --provider openrouter --id exact/kimi"), {
	model: "moonshotai/kimi-k3", provider: "openrouter", id: "exact/kimi",
});
assert.deepEqual(indexModule.parseModelCommandArguments("--provider openrouter --id gpt-5.6-terra"), {
	provider: "openrouter", id: "gpt-5.6-terra",
});
assert.throws(() => indexModule.parseModelCommandArguments("model --unknown value"), /unknown flag/);
assert.throws(() => indexModule.parseModelCommandArguments("--provider"), /needs a value/);

const writableConfigPath = path.join(defaultsRoot, "writable-overlay.json");
const writable = structuredClone(overlay);
await fs.writeFile(writableConfigPath, JSON.stringify(writable));
const mutation = config.mutateModel(writable, "builder", { model: "gpt-5.6-terra", provider: "openrouter", id: "gpt-5.6-terra" });
assert.ok(mutation.some((change) => change.includes("gpt-5.6-terra")));
const normalized = config.mutateModel(writable, "planner", { model: "openrouter/moonshotai/kimi-k3", provider: "openrouter" });
assert.ok(normalized.some((change) => change.includes("moonshotai/kimi-k3")));
assert.equal(writable.roles.planner.model.class, "moonshotai/kimi-k3");
assert.deepEqual(config.validateConfig(writable), []);
const routed = structuredClone(valid);
routed.agents.runner = { displayName: "Runner", purpose: "routine", readOnly: false, model: { class: "gpt-5.6-terra", provider: "openai", effort: "xhigh" }, tools: [], invocation: "default", autoSelectEligible: true, capabilities: [], boundaries: [], escalateTo: [], canDelegate: false, delegateTo: [], outputContract: [], infoSources: ["read docs"] };
routed.routing = { automaticSelection: { enabled: true, status: "confirmation-required", threshold: 0.6, fallback: "runner", audit: { enabled: false, path: "runtime/audit.jsonl" } } };
assert.deepEqual(config.validateConfig(routed), []);
const missingDelegation = structuredClone(routed);
delete missingDelegation.agents.runner.canDelegate;
delete missingDelegation.agents.runner.delegateTo;
assert.ok(config.validateConfig(missingDelegation).some((error) => error.includes("canDelegate is required")));
assert.ok(config.validateConfig(missingDelegation).some((error) => error.includes("delegateTo must be a list")));
config.writeConfigAtomic(writableConfigPath, writable);
const persisted = JSON.parse(await fs.readFile(writableConfigPath, "utf8"));
assert.equal(persisted.roles.builder.model.id, "gpt-5.6-terra");
assert.equal(persisted.roles.planner.model.class, "moonshotai/kimi-k3");
assert.equal(valid.roles.planner.model.class, "gpt-5.6-sol");

const machine = config.loadResolved(defaultsCwd, { machineDefault: machinePath, piOverlay: writableConfigPath });
assert.equal(machine.loadError, null);
assert.equal(machine.sourceKind, "pi-overlay");
assert.equal(machine.overlayWarning, null);
assert.deepEqual(machine.errors, []);
assert.match(config.renderValidatedReport(machine.cfg), /planner\s+-> model 'moonshotai\/kimi-k3'/);
assert.match(config.renderValidatedReport(machine.cfg), /builder\s+-> model 'gpt-5\.6-terra'/);

await fs.rm(root, { recursive: true, force: true });
await fs.rm(defaultsRoot, { recursive: true, force: true });
await fs.rm(fakeDir, { recursive: true, force: true });
console.log("pb-primitive self-test: PASS (offline; no model calls)");
