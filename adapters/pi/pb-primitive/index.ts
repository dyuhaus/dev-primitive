import { BorderedLoader, type ExtensionAPI, type ExtensionContext } from "@earendil-works/pi-coding-agent";
import { spawn } from "node:child_process";
import { Type } from "typebox";
import {
	configuredAgentKeys,
	getConfiguredAgent,
	loadConfigFile,
	loadResolved,
	mutateModel,
	parseTaskAndUntil,
	PI_DEFAULT_CONFIG,
	renderValidatedReport,
	roleView,
	validateConfig,
	writeConfigAtomic,
	type LoadResult,
	type RoleView,
	type RolesConfig,
} from "./config.ts";
import { renderReportMessage, renderRoleResult } from "./render.ts";
import { builderSystemPrompt, plannerSystemPrompt, specialistSystemPrompt, verifierSystemPrompt } from "./roles.ts";
import {
	capOutput,
	cleanupStalePromptDirs,
	getResultOutput,
	isFailed,
	killAllStragglers,
	runRole,
	type RunResult,
	type RunResultDetails,
} from "./subagent.ts";

const MAX_GOAL_ROUNDS = 3;
const ROUTER_PATH = "/home/dyadmin/dev-primitive/router.py";
const TaskParameters = Type.Object({
	task: Type.String({ description: "The complete task to delegate to this role." }),
});

export interface ModelCommandArguments {
	model?: string;
	id?: string;
	provider?: string;
}

export interface RouteDecision {
	status: "recommendation";
	selected: string;
	confidence: number;
	reasons: string[];
	candidates: Array<{ agent: string; score: number }>;
	needs_clarification: boolean;
	questions: string[];
}

/** Validate JSON from the local deterministic router before acting on it. */
export function parseRouterDecision(raw: string): RouteDecision {
	const value = JSON.parse(raw) as Partial<RouteDecision>;
	if (value.status !== "recommendation" || typeof value.selected !== "string" || !value.selected) throw new Error("router returned an invalid recommendation");
	if (typeof value.confidence !== "number" || value.confidence < 0 || value.confidence > 1) throw new Error("router returned an invalid confidence");
	if (!Array.isArray(value.reasons) || !value.reasons.every((item) => typeof item === "string")) throw new Error("router returned invalid reasons");
	if (!Array.isArray(value.candidates) || !value.candidates.every((item) => typeof item?.agent === "string" && typeof item?.score === "number")) throw new Error("router returned invalid candidates");
	if (typeof value.needs_clarification !== "boolean" || !Array.isArray(value.questions) || !value.questions.every((item) => typeof item === "string")) throw new Error("router returned invalid clarification fields");
	return value as RouteDecision;
}

/** Invoke router.py without a shell, so task text can never become shell code. */
async function getRouteDecision(task: string, cwd: string, configPath: string, signal?: AbortSignal): Promise<RouteDecision> {
	return new Promise((resolve, reject) => {
		const child = spawn("python3", [ROUTER_PATH, "--json", "--cwd", cwd, "--config", configPath, task], {
			cwd,
			stdio: ["ignore", "pipe", "pipe"],
			shell: false,
		});
		let stdout = "";
		let stderr = "";
		child.stdout.on("data", (chunk) => { stdout += String(chunk); });
		child.stderr.on("data", (chunk) => { stderr += String(chunk); });
		const abort = () => child.kill("SIGTERM");
		signal?.addEventListener("abort", abort, { once: true });
		child.on("error", (error) => reject(error));
		child.on("close", (code) => {
			signal?.removeEventListener("abort", abort);
			if (code !== 0) return reject(new Error(`router.py exited ${code}: ${stderr.trim() || "no diagnostic"}`));
			try { resolve(parseRouterDecision(stdout)); } catch (error) { reject(error); }
		});
	});
}

function formatRouteDecision(decision: RouteDecision): string {
	const alternatives = decision.candidates.slice(0, 4).map((item) => `${item.agent} (${item.score})`).join(", ") || "none";
	const lines = [
		`## Agent recommendation: ${decision.selected}`,
		`Confidence: ${(decision.confidence * 100).toFixed(0)}%`,
		"Status: confirmation is required before delegation.",
		"", "### Reasons", ...decision.reasons.map((reason) => `- ${reason}`),
		"", `### Candidate scores\n${alternatives}`,
	];
	if (decision.needs_clarification) lines.push("", "### Clarification", ...decision.questions.map((question) => `- ${question}`));
	return lines.join("\n");
}

/** Durable transcript acknowledgement emitted before a confirmed child starts. */
export function formatAcceptedRoute(decision: RouteDecision, displayName: string, task: string): string {
	return `${formatRouteDecision(decision)}\n\n## Accepted task\n\n${task.trim()}\n\nDelegating to **${displayName}** now. Progress is shown below; press Esc to cancel.`;
}

/** True only for plain, interactive text that can safely enter confirmed routing. */
export function shouldAutoRouteInput(text: string, source: string | undefined, hasImages = false): boolean {
	const trimmed = text.trim();
	return source === "interactive" && !hasImages && Boolean(trimmed) && !trimmed.startsWith("/") && !trimmed.startsWith("!");
}

/** Parse a Pi-only agent model command without passing input to a shell. */
export function parseModelCommandArguments(raw: string): ModelCommandArguments {
	const tokens = raw.trim() ? raw.trim().split(/\s+/) : [];
	const parsed: ModelCommandArguments = {};
	for (let index = 0; index < tokens.length; index++) {
		const token = tokens[index];
		if (token === "--id" || token === "--provider") {
			const value = tokens[++index];
			if (!value || value.startsWith("--")) throw new Error(`${token} needs a value`);
			if (token === "--id") {
				if (parsed.id !== undefined) throw new Error("--id may be supplied only once");
				parsed.id = value;
			} else {
				if (parsed.provider !== undefined) throw new Error("--provider may be supplied only once");
				parsed.provider = value;
			}
			continue;
		}
		if (token.startsWith("--")) throw new Error(`unknown flag '${token}'; use --id or --provider`);
		if (parsed.model !== undefined) throw new Error("provide only one model before flags");
		parsed.model = token;
	}
	return parsed;
}

function systemPromptFor(key: string, view: RoleView): string {
	if (key === "planner") return plannerSystemPrompt(view.purpose);
	if (key === "builder") return builderSystemPrompt(view.purpose);
	return specialistSystemPrompt(view);
}

function commandNotice(ctx: ExtensionContext, message: string, level: "info" | "warning" | "error" = "info"): void {
	if (ctx.hasUI) ctx.ui.notify(message, level);
	else console.log(message);
}

function configError(loaded: LoadResult): string | null {
	if (loaded.loadError) return loaded.loadError;
	if (!loaded.cfg) return "roles config could not be loaded";
	if (loaded.errors.length) return `invalid roles config ${loaded.sourcePath}:\n- ${loaded.errors.join("\n- ")}`;
	return null;
}

function resolveRole(ctx: ExtensionContext, key: string): { loaded: LoadResult; view?: RoleView; error?: string } {
	const loaded = loadResolved(ctx.cwd);
	const error = configError(loaded);
	if (error || !loaded.cfg) return { loaded, error: error ?? "unknown config error" };
	if (!(key in (loaded.cfg.roles ?? {})) && !(key in (loaded.cfg.agents ?? {}))) return { loaded, error: `agent '${key}' is not configured` };
	return { loaded, view: roleView(loaded.cfg, key) };
}

function details(label: string, results: RunResult[]): RunResultDetails {
	return { kind: "pb-primitive", label, results };
}

function outcomeText(result: RunResult): string {
	return capOutput(getResultOutput(result));
}

const ROUTE_CLASSIFY_STATUS = "pb-primitive-classify";
const ROUTE_PROGRESS_STATUS = "pb-primitive-route";
const ROUTE_PROGRESS_WIDGET = "pb-primitive-route-progress";

/** Keep accepted routed work visible while an isolated child Pi is running. */
export async function withRouteProgress<T>(
	ctx: ExtensionContext,
	displayName: string,
	task: string,
	work: (signal?: AbortSignal) => Promise<T>,
): Promise<T> {
	if (!ctx.hasUI) return work(ctx.signal);
	const taskPreview = task.replace(/\s+/g, " ").trim().slice(0, 180);

	// A cancellable modal is the clearest acknowledgement in the TUI and gives
	// Esc a real AbortSignal to propagate to the isolated child process.
	if (ctx.mode === "tui") {
		let workError: unknown;
		const result = await ctx.ui.custom<{ ok: true; value: T } | null>((tui, theme, _keybindings, done) => {
			const loader = new BorderedLoader(tui, theme, `Accepted → ${displayName}\n${taskPreview}\nRunning in an isolated Pi process...`);
			loader.onAbort = () => done(null);
			work(loader.signal)
				.then((value) => done({ ok: true, value }))
				.catch((error) => {
					workError = error;
					done(null);
				});
			return loader;
		});
		if (workError) throw workError;
		if (!result) throw new Error(`${displayName} delegation canceled.`);
		return result.value;
	}

	// RPC has UI notifications/status but no terminal component. Keep a visible
	// status and widget until completion, and always clean both up.
	const started = Date.now();
	const render = () => {
		const elapsed = Math.max(0, Math.floor((Date.now() - started) / 1000));
		ctx.ui.setStatus(ROUTE_PROGRESS_STATUS, `Running ${displayName} · ${elapsed}s`);
		ctx.ui.setWidget(ROUTE_PROGRESS_WIDGET, [`Accepted → ${displayName}`, taskPreview, `${elapsed}s elapsed`]);
	};
	render();
	const ticker = setInterval(render, 1000);
	try {
		return await work(ctx.signal);
	} finally {
		clearInterval(ticker);
		ctx.ui.setStatus(ROUTE_PROGRESS_STATUS, undefined);
		ctx.ui.setWidget(ROUTE_PROGRESS_WIDGET, undefined);
	}
}

async function runConfiguredRole(
	key: string,
	task: string,
	ctx: ExtensionContext,
	onUpdate?: Parameters<typeof runRole>[0]["onUpdate"],
	label?: string,
	signal?: AbortSignal,
): Promise<{ result?: RunResult; view?: RoleView; sourcePath: string; error?: string }> {
	const resolved = resolveRole(ctx, key);
	if (resolved.error || !resolved.view) {
		return { sourcePath: resolved.loaded.sourcePath, error: resolved.error ?? "role resolution failed" };
	}
	const view = resolved.view;
	const systemPrompt = systemPromptFor(key, view);
	const result = await runRole({
		cwd: ctx.cwd,
		view,
		systemPrompt,
		prompt: `Task: ${task}`,
		signal: signal ?? ctx.signal,
		onUpdate,
		label: label ?? `${key}_agent`,
	});
	return { result, view, sourcePath: resolved.loaded.sourcePath };
}

async function routeSelectedTask(selected: string, task: string, ctx: ExtensionContext): Promise<{ text: string; results: RunResult[] }> {
	if (selected === "planner") return plannerThenBuilder(task, ctx);
	const resolved = resolveRole(ctx, selected);
	const displayName = resolved.view?.displayName ?? selected;
	let result: Awaited<ReturnType<typeof runConfiguredRole>>;
	try {
		result = await withRouteProgress(ctx, displayName, task, (signal) =>
			runConfiguredRole(selected, task, ctx, undefined, `${selected} route`, signal),
		);
	} catch (error) {
		return { text: `${displayName} did not complete: ${(error as Error).message}`, results: [] };
	}
	if (result.error || !result.result) return { text: `${selected} did not start: ${result.error ?? "unknown error"}`, results: [] };
	return { text: `## ${displayName} result\n\n${outcomeText(result.result)}`, results: [result.result] };
}

async function plannerThenBuilder(task: string, ctx: ExtensionContext): Promise<{ text: string; results: RunResult[] }> {
	const results: RunResult[] = [];
	const planned = await runConfiguredRole("planner", task, ctx, undefined, "planner");
	if (planned.error || !planned.result) {
		return { text: `Planning did not start: ${planned.error}`, results };
	}
	results.push(planned.result);
	if (isFailed(planned.result)) {
		return { text: `Planning failed.\n\n${outcomeText(planned.result)}`, results };
	}
	const plan = getResultOutput(planned.result);

	if (ctx.hasUI) {
		const approved = await ctx.ui.confirm(
			"Run the builder?",
			`The read-only planner completed. Continue with the configured builder?\n\n${capOutput(plan).slice(0, 3000)}`,
		);
		if (!approved) return { text: `Builder canceled after planning.\n\n## Plan\n\n${capOutput(plan)}`, results };
	}

	const buildTask = `Original task:\n${task}\n\nVerbatim planner output (do not silently replace it):\n---\n${plan}\n---\n\nImplement the task, validate it, and report changes and remaining risks.`;
	const built = await runConfiguredRole("builder", buildTask, ctx, undefined, "builder");
	if (built.error || !built.result) {
		return { text: `Builder did not start: ${built.error}\n\n## Plan\n\n${capOutput(plan)}`, results };
	}
	results.push(built.result);
	return {
		text: `## Plan\n\n${capOutput(plan)}\n\n## Builder result\n\n${outcomeText(built.result)}`,
		results,
	};
}

function parseVerification(text: string): "pass" | "continue" | "blocked" {
	const line = text.match(/^PB_VERIFY:\s*(PASS|CONTINUE|BLOCKED)\b/im)?.[1]?.toLowerCase();
	return line === "pass" || line === "blocked" ? line : "continue";
}

async function goalLoop(raw: string, ctx: ExtensionContext): Promise<{ text: string; results: RunResult[] }> {
	const { task, until } = parseTaskAndUntil(raw);
	if (!task) return { text: "Usage: /pbg <task> [until: <done-condition>]", results: [] };
	const results: RunResult[] = [];
	let condition = until;
	let previousEvidence = "";
	let priorContinuation = "";
	const sections: string[] = [];

	for (let round = 1; round <= MAX_GOAL_ROUNDS; round++) {
		const planningTask = condition
			? `Plan round ${round} for this task:\n${task}\n\nDone-condition:\n${condition}\n\nPrior evidence:\n${previousEvidence || "none"}\n\nPrior verifier guidance:\n${priorContinuation || "none"}`
			: `Plan round ${round} for this task and first derive explicit, testable acceptance criteria:\n${task}\n\nPrior evidence:\n${previousEvidence || "none"}`;
		const planned = await runConfiguredRole("planner", planningTask, ctx, undefined, `planner round ${round}`);
		if (planned.error || !planned.result) {
			sections.push(`## Round ${round}\n\nPlanner did not start: ${planned.error}`);
			break;
		}
		results.push(planned.result);
		if (isFailed(planned.result)) {
			sections.push(`## Round ${round}\n\nPlanner failed:\n\n${outcomeText(planned.result)}`);
			break;
		}
		const plan = getResultOutput(planned.result);
		if (!condition) condition = `Meet the explicit acceptance criteria in this planner output:\n${plan}`;

		if (ctx.hasUI) {
			const approved = await ctx.ui.confirm(
				`Build round ${round}/${MAX_GOAL_ROUNDS}?`,
				`Done-condition:\n${capOutput(condition).slice(0, 1500)}\n\nPlan:\n${capOutput(plan).slice(0, 2500)}`,
			);
			if (!approved) {
				sections.push(`## Round ${round}\n\nStopped by user after planning.\n\n${capOutput(plan)}`);
				break;
			}
		}

		const buildPrompt = `Original task:\n${task}\n\nDone-condition:\n${condition}\n\nRound: ${round}/${MAX_GOAL_ROUNDS}\n\nVerbatim plan:\n---\n${plan}\n---\n\nPrior evidence:\n${previousEvidence || "none"}\n\nImplement only the remaining work. Validate and report concrete evidence.`;
		const built = await runConfiguredRole("builder", buildPrompt, ctx, undefined, `builder round ${round}`);
		if (built.error || !built.result) {
			sections.push(`## Round ${round}\n\nBuilder did not start: ${built.error}`);
			break;
		}
		results.push(built.result);
		const buildOutput = getResultOutput(built.result);
		sections.push(`## Round ${round}\n\n### Plan\n\n${capOutput(plan)}\n\n### Builder\n\n${outcomeText(built.result)}`);
		if (isFailed(built.result)) break;

		const planner = resolveRole(ctx, "planner");
		if (planner.error || !planner.view) {
			sections.push(`\n### Verification\n\nCould not resolve verifier: ${planner.error}`);
			break;
		}
		const verifyPrompt = `Original task:\n${task}\n\nDone-condition:\n${condition}\n\nRound plan:\n${plan}\n\nBuilder evidence:\n${buildOutput}`;
		const verified = await runRole({
			cwd: ctx.cwd,
			view: planner.view,
			systemPrompt: verifierSystemPrompt(planner.view.purpose),
			prompt: verifyPrompt,
			signal: ctx.signal,
			label: `verifier round ${round}`,
		});
		results.push(verified);
		const verification = getResultOutput(verified);
		sections.push(`\n### Verification\n\n${outcomeText(verified)}`);
		if (isFailed(verified)) break;
		const state = parseVerification(verification);
		if (state === "pass" || state === "blocked") break;
		if (buildOutput.trim() === previousEvidence.trim()) {
			sections.push("\nStopped: no progress was evidenced between rounds.");
			break;
		}
		previousEvidence = buildOutput;
		priorContinuation = verification;
	}
	return { text: sections.join("\n\n"), results };
}

export default function pbPrimitive(pi: ExtensionAPI): void {
	for (const key of ["planner", "builder"] as const) {
		const name = `${key}_agent`;
		pi.registerTool({
			name,
			label: key === "planner" ? "Planner Agent" : "Builder Agent",
			description:
				key === "planner"
					? "Delegate substantive planning, architecture, root-cause analysis, or approach review to the configured read-only planner."
					: "Delegate substantive implementation, editing, builds, and tests to the configured builder after a plan exists.",
			promptSnippet:
				key === "planner" ? "Run the configured read-only reasoning role in an isolated pi process" : "Run the configured coding role in an isolated pi process",
			promptGuidelines: [
				key === "planner"
					? "Use planner_agent before substantive implementation for architecture, design, root-cause analysis, trade-offs, sequencing, and approach review; trivial lookups and one-line edits may stay inline."
					: "Use builder_agent for substantive implementation after obtaining and reviewing a plan; include the task and plan in full, then verify the result.",
			],
			parameters: TaskParameters,
			async execute(_id, params, signal, onUpdate, ctx) {
				const resolved = resolveRole(ctx, key);
				if (resolved.error || !resolved.view) throw new Error(resolved.error ?? `unable to resolve ${key}`);
				const systemPrompt = key === "planner" ? plannerSystemPrompt(resolved.view.purpose) : builderSystemPrompt(resolved.view.purpose);
				const result = await runRole({
					cwd: ctx.cwd,
					view: resolved.view,
					systemPrompt,
					prompt: `Task: ${params.task}`,
					signal,
					onUpdate,
					label: name,
				});
				return {
					content: [
						{
							type: "text",
							text: isFailed(result) ? `${name} failed:\n\n${outcomeText(result)}` : outcomeText(result),
						},
					],
					details: details(name, [result]),
				};
			},
			renderCall(args, theme) {
				return renderReportMessage(
					{ content: `**${name}**\n\n${String(args.task ?? "").slice(0, 500)}` },
					{ expanded: false },
					theme,
				);
			},
			renderResult(result, options, theme) {
				return renderRoleResult(result.details as RunResultDetails | undefined, result, options.expanded, theme);
			},
		});
	}

	const loadedForAgents = loadResolved(process.cwd());
	for (const key of Object.keys(loadedForAgents.cfg?.agents ?? {})) {
		const name = `${key.replace(/-/g, "_")}_agent`;
		pi.registerTool({
			name,
			label: loadedForAgents.cfg?.agents?.[key]?.displayName ?? key,
			description: key === "team-leader"
				? "Team Leader is direct-call-only; use /team-leader only after an explicit user request."
				: `Run the configured ${key} specialist explicitly.`,
			promptSnippet: key === "team-leader"
				? "Do not invoke this tool; Team Leader may only be run by an explicit /team-leader user command."
				: `Delegate a task explicitly to the configured ${key} specialist`,
			promptGuidelines: key === "team-leader"
				? ["Never invoke team_leader_agent. Team Leader is direct-call-only; only the user-entered /team-leader command may start it."]
				: [`Use ${name} only for work within the ${key} specialist profile. Do not automatically invoke direct-call-only agents.`, "router.py recognition requires confirmation; use /route for an explainable handoff."],
			parameters: TaskParameters,
			async execute(_id, params, signal, onUpdate, ctx) {
				if (key === "team-leader") throw new Error("Team Leader is direct-call-only. It may be run only with the explicit /team-leader command after a user request.");
				const resolved = resolveRole(ctx, key);
				if (resolved.error || !resolved.view) throw new Error(resolved.error ?? `unable to resolve ${key}`);
				const result = await runRole({ cwd: ctx.cwd, view: resolved.view, systemPrompt: specialistSystemPrompt(resolved.view), prompt: `Task: ${params.task}`, signal, onUpdate, label: name });
				return { content: [{ type: "text", text: isFailed(result) ? `${name} failed:\n\n${outcomeText(result)}` : outcomeText(result) }], details: details(name, [result]) };
			},
			renderCall(args, theme) { return renderReportMessage({ content: `**${name}**\n\n${String(args.task ?? "").slice(0, 500)}` }, { expanded: false }, theme); },
			renderResult(result, options, theme) { return renderRoleResult(result.details as RunResultDetails | undefined, result, options.expanded, theme); },
		});
	}

	// Native, explicit slash commands for every configured agent. Dynamic
	// registration keeps the harness command surface aligned with the registry.
	const commandRegistry = loadConfigFile(PI_DEFAULT_CONFIG).cfg ?? loadResolved(process.cwd()).cfg;
	for (const key of configuredAgentKeys(commandRegistry ?? ({} as RolesConfig))) {
		pi.registerCommand(key, {
			description: `Run the configured ${key} agent explicitly`,
			handler: async (args, ctx) => {
				const task = args.trim();
				if (!task) {
					commandNotice(ctx, `Usage: /${key} <task>`, "warning");
					return;
				}
				const resolved = resolveRole(ctx, key);
				const displayName = resolved.view?.displayName ?? key;
				let result: Awaited<ReturnType<typeof runConfiguredRole>>;
				try {
					result = await withRouteProgress(ctx, displayName, task, (signal) =>
						runConfiguredRole(key, task, ctx, undefined, `${key} command`, signal),
					);
				} catch (error) {
					commandNotice(ctx, `${displayName} did not complete: ${(error as Error).message}`, "error");
					return;
				}
				if (result.error || !result.result) {
					commandNotice(ctx, `${key} did not start: ${result.error ?? "unknown error"}`, "error");
					return;
				}
				const title = `## ${result.view?.displayName ?? key} result`;
				pi.sendMessage({ customType: "pb-primitive-report", content: `${title}\n\n${outcomeText(result.result)}`, display: true }, { triggerTurn: false });
			},
		});

		pi.registerCommand(`${key}-model`, {
			description: `Show or change the Pi-only model for ${key}`,
			handler: async (args, ctx) => {
				const overlay = loadConfigFile(PI_DEFAULT_CONFIG);
				if (overlay.loadError || !overlay.cfg) {
					commandNotice(ctx, `Pi model overlay unavailable: ${overlay.loadError ?? "could not load config"}`, "error");
					return;
				}
				const overlayErrors = validateConfig(overlay.cfg);
				if (overlayErrors.length) {
					commandNotice(ctx, `Pi model overlay is invalid:\n- ${overlayErrors.join("\n- ")}`, "error");
					return;
				}
				const current = getConfiguredAgent(overlay.cfg, key);
				if (!current) {
					commandNotice(ctx, `Agent '${key}' is not configured in the Pi-only overlay.`, "error");
					return;
				}
				if (!args.trim()) {
					const model = roleView(overlay.cfg, key);
					commandNotice(ctx, `${key} Pi-only model: ${model.provider}/${model.model}\nUsage: /${key}-model <model> [--provider <provider>] [--id <exact-model-id>]\nThis command changes only ${PI_DEFAULT_CONFIG}.`);
					return;
				}
				let parsed: ModelCommandArguments;
				try {
					parsed = parseModelCommandArguments(args);
				} catch (error) {
					commandNotice(ctx, `Invalid /${key}-model arguments: ${(error as Error).message}`, "error");
					return;
				}
				const next = JSON.parse(JSON.stringify(overlay.cfg)) as RolesConfig;
				let changes: string[];
				try {
					changes = mutateModel(next, key, parsed);
				} catch (error) {
					commandNotice(ctx, `Cannot change ${key} model: ${(error as Error).message}`, "error");
					return;
				}
				const errors = validateConfig(next);
				if (errors.length) {
					commandNotice(ctx, `Model change would make the Pi overlay invalid:\n- ${errors.join("\n- ")}`, "error");
					return;
				}
				try {
					writeConfigAtomic(PI_DEFAULT_CONFIG, next);
				} catch (error) {
					commandNotice(ctx, `Could not save Pi-only model overlay: ${(error as Error).message}`, "error");
					return;
				}
				const active = loadResolved(ctx.cwd);
				const activeWarning = active.sourceKind === "project"
					? `\nNote: this session uses project config ${active.sourcePath}, which still overrides the Pi overlay.`
					: "";
				commandNotice(ctx, `Updated Pi-only ${key} model: ${changes.join("; ")}\nResolved: ${roleView(next, key).provider}/${roleView(next, key).model}${activeWarning}`);
			},
		});
	}

	pi.registerCommand("route", {
		description: "Recommend an appropriate agent, then confirm before running it",
		handler: async (args, ctx) => {
			const task = args.trim();
			if (!task) {
				commandNotice(ctx, "Usage: /route <task>", "warning");
				return;
			}
			const loaded = loadResolved(ctx.cwd);
			const error = configError(loaded);
			if (error || !loaded.cfg) {
				commandNotice(ctx, `Cannot route task: ${error ?? "configuration unavailable"}`, "error");
				return;
			}
			let decision: RouteDecision;
			try {
				// Pass the resolved source to keep route metadata/models aligned with Pi's active config.
				decision = await getRouteDecision(task, ctx.cwd, loaded.sourcePath, ctx.signal);
			} catch (cause) {
				commandNotice(ctx, `Router failed: ${(cause as Error).message}`, "error");
				return;
			}
			const report = formatRouteDecision(decision);
			if (!ctx.hasUI) {
				console.log(report);
				console.log(`Run /${decision.selected} explicitly after reviewing this recommendation.`);
				return;
			}
			const selected = resolveRole(ctx, decision.selected);
			if (decision.needs_clarification) {
				commandNotice(ctx, `${report}\n\nClarify the task before an agent can be run.`, "warning");
				return;
			}
			if (decision.selected === "team-leader" || selected.error || !selected.view || selected.view.invocation === "direct-call-only") {
				commandNotice(ctx, `${report}\n\nThe recommendation is not an eligible automatic destination; invoke Team Leader only with an explicit direct call.`, "warning");
				return;
			}
			const approved = await ctx.ui.confirm(`Run ${selected.view.displayName}?`, report);
			if (!approved) {
				pi.sendMessage({ customType: "pb-primitive-report", content: `${report}\n\nDelegation canceled.`, display: true }, { triggerTurn: false });
				return;
			}
			pi.sendMessage({ customType: "pb-primitive-report", content: formatAcceptedRoute(decision, selected.view.displayName, task), display: true }, { triggerTurn: false });
			const routed = await routeSelectedTask(decision.selected, task, ctx);
			pi.sendMessage({ customType: "pb-primitive-report", content: `${report}\n\n${routed.text}`, display: true }, { triggerTurn: false });
		},
	});

	pi.registerCommand("agents", {
		description: "List all configured agent commands and their active Pi models",
		handler: async (_args, ctx) => {
			const active = loadResolved(ctx.cwd);
			const activeError = configError(active);
			const commandKeys = configuredAgentKeys(commandRegistry ?? ({} as RolesConfig));
			const lines = [
				"## Pi Agent Commands",
				"",
				`**Active configuration:** \`${active.sourcePath}\` (${active.sourceKind})`,
			];
			if (active.overlayWarning) lines.push(`**Pi overlay warning:** ${active.overlayWarning}`);
			if (activeError || !active.cfg) {
				lines.push("", `**Configuration error:** ${activeError ?? "unable to load active configuration"}`);
			} else {
				lines.push("", "| Agent | Run command | Model command | Model status |", "|---|---|---|---|");
				for (const key of commandKeys) {
					const entry = getConfiguredAgent(active.cfg, key);
					if (!entry) {
						lines.push(`| ${key} | \`/${key}\` | \`/${key}-model\` | Not configured in the active config |`);
						continue;
					}
					const view = roleView(active.cfg, key);
					const configuredModel = view.model && view.provider;
					const status = configuredModel ? `Set — \`${view.provider}/${view.model}\`${view.pinned ? " (pinned)" : ""}` : "Not set";
					lines.push(`| ${key} | \`/${key}\` | \`/${key}-model\` | ${status} |`);
				}
				lines.push("", "Use `/<agent>-model` to inspect or change only that agent's Pi-overlay model. Project-local Pi configuration still takes precedence.");
			}
			const body = lines.join("\n");
			if (ctx.hasUI) ctx.ui.notify(body, activeError ? "error" : "info");
			else console.log(body);
		},
	});

	pi.registerCommand("pb-show", {
		description: "Show the live two-role config and resolved provider/models",
		handler: async (_args, ctx) => {
			const loaded = loadResolved(ctx.cwd);
			const error = configError(loaded);
			const source = `**Config source:** \`${loaded.sourcePath}\` (${loaded.sourceKind})`;
			const warning = loaded.overlayWarning ? `\n\n**Pi overlay warning:** ${loaded.overlayWarning}` : "";
			const body = error || !loaded.cfg
				? `**pb-primitive config error**\n\n${error}${warning}`
				: `${source}${warning}\n\n\`\`\`text\n${renderValidatedReport(loaded.cfg)}\`\`\``;
			if (ctx.hasUI) ctx.ui.notify(body, error ? "error" : "info");
			else console.log(body.replace(/\*\*/g, ""));
		},
	});

	pi.registerCommand("pb", {
		description: "Run one planner → builder pass",
		handler: async (args, ctx) => {
			if (!args.trim()) {
				ctx.ui.notify("Usage: /pb <task>", "warning");
				return;
			}
			const report = await plannerThenBuilder(args.trim(), ctx);
			pi.sendMessage({ customType: "pb-primitive-report", content: report.text, display: true }, { triggerTurn: false });
		},
	});

	pi.registerCommand("pbg", {
		description: "Run a bounded planner → builder → verifier loop (max 3 rounds)",
		handler: async (args, ctx) => {
			const report = await goalLoop(args, ctx);
			pi.sendMessage({ customType: "pb-primitive-report", content: report.text, display: true }, { triggerTurn: false });
		},
	});

	pi.registerMessageRenderer("pb-primitive-report", renderReportMessage);

	// The router is deliberately an interactive confirmation gate. It detects
	// applicable profiles for ordinary user requests, but leaves slash commands,
	// shell input, images, RPC, and extension messages untouched. It never runs a
	// profile until the user confirms the explainable recommendation below.
	pi.on("input", async (event, ctx) => {
		if (!shouldAutoRouteInput(event.text, event.source, Boolean(event.images?.length))) return { action: "continue" };
		const loaded = loadResolved(ctx.cwd);
		const error = configError(loaded);
		if (error || !loaded.cfg || loaded.cfg.routing?.automaticSelection?.enabled !== true) return { action: "continue" };
		let decision: RouteDecision;
		if (ctx.hasUI) ctx.ui.setStatus(ROUTE_CLASSIFY_STATUS, "Request accepted · checking specialist fit…");
		try {
			decision = await getRouteDecision(event.text, ctx.cwd, loaded.sourcePath, ctx.signal);
		} catch (cause) {
			commandNotice(ctx, `Router unavailable; continuing normally: ${(cause as Error).message}`, "warning");
			return { action: "continue" };
		} finally {
			if (ctx.hasUI) ctx.ui.setStatus(ROUTE_CLASSIFY_STATUS, undefined);
		}
		if (decision.needs_clarification) return { action: "continue" };
		const selected = resolveRole(ctx, decision.selected);
		if (decision.selected === "team-leader" || selected.error || !selected.view || selected.view.invocation === "direct-call-only") return { action: "continue" };
		const approved = await ctx.ui.confirm(`Route to ${selected.view.displayName}?`, formatRouteDecision(decision));
		if (!approved) return { action: "continue" };
		pi.sendMessage({ customType: "pb-primitive-report", content: formatAcceptedRoute(decision, selected.view.displayName, event.text), display: true }, { triggerTurn: false });
		const routed = await routeSelectedTask(decision.selected, event.text, ctx);
		pi.sendMessage({ customType: "pb-primitive-report", content: `${formatRouteDecision(decision)}\n\n${routed.text}`, display: true }, { triggerTurn: false });
		return { action: "handled" };
	});

	pi.on("session_shutdown", async () => killAllStragglers());
	pi.on("session_start", async (_event, ctx) => {
		const stalePromptDirs = cleanupStalePromptDirs();
		if (stalePromptDirs > 0 && ctx.hasUI) ctx.ui.notify(`pb-primitive removed ${stalePromptDirs} stale temporary prompt director${stalePromptDirs === 1 ? "y" : "ies"}.`, "info");
		const loaded = loadResolved(ctx.cwd);
		const error = configError(loaded);
		if (error && ctx.hasUI) ctx.ui.notify(`pb-primitive disabled: ${error}`, "error");
		else if (loaded.overlayWarning && ctx.hasUI) ctx.ui.notify(`pb-primitive: ${loaded.overlayWarning}`, "warning");
	});
}
