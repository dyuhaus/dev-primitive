/**
 * pb-primitive / subagent.ts
 *
 * Spawns an isolated child `pi` process for one role invocation and captures
 * its structured JSONL output. Modeled on pi's canonical subagent example so
 * it follows the same mechanics:
 *   - JSONL parsing of --mode json stdout (message_end / tool_result_end)
 *   - streamed onUpdate callbacks
 *   - abort propagation: SIGTERM, then SIGKILL after a grace period
 *   - a hard timeout that aborts the child
 *   - temp prompt files written mode 0600 and cleaned up in a finally block
 *   - model-visible output capped at 50KB while full evidence is kept in details
 *   - a module-level straggler registry so session_shutdown can kill leftovers
 *
 * The child inherits the parent process environment (and thus pi auth). This
 * module never reads, forwards explicitly, or logs secret values.
 */

import { type ChildProcess, spawn } from "node:child_process";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import type { AgentToolResult } from "@earendil-works/pi-agent-core";
import type { Message } from "@earendil-works/pi-ai";
import type { RoleView } from "./config.ts";
import { buildChildArgs } from "./roles.ts";

export const OUTPUT_CAP = 50 * 1024;
/** Default per-child wall-clock timeout (ms). Generous; roles do real work. */
export const DEFAULT_TIMEOUT_MS = 20 * 60 * 1000;
const KILL_GRACE_MS = 5000;
const TEMP_DIR_PREFIX = "pi-pb-primitive-";
const STALE_TEMP_MAX_AGE_MS = 60 * 60 * 1000;

export interface UsageStats {
	input: number;
	output: number;
	cacheRead: number;
	cacheWrite: number;
	cost: number;
	contextTokens: number;
	turns: number;
}

export interface RunResult {
	role: string;
	provider: string;
	model?: string;
	exitCode: number;
	messages: Message[];
	stderr: string;
	usage: UsageStats;
	stopReason?: string;
	errorMessage?: string;
	wasAborted: boolean;
	timedOut: boolean;
}

export interface RunResultDetails {
	kind: "pb-primitive";
	results: RunResult[];
	label?: string;
}

export type OnUpdate = (partial: AgentToolResult<RunResultDetails>) => void;

/* -------------------------------------------------- straggler registry */

const liveChildren = new Set<ChildProcess>();

/** Kill any child processes still running (called from session_shutdown). */
export function killAllStragglers(): void {
	for (const proc of Array.from(liveChildren)) {
		try {
			proc.kill("SIGTERM");
			setTimeout(() => {
				try {
					if (!proc.killed) proc.kill("SIGKILL");
				} catch {
					/* ignore */
				}
			}, KILL_GRACE_MS);
		} catch {
			/* ignore */
		}
	}
}

export function liveChildCount(): number {
	return liveChildren.size;
}

/** Remove only old, owned prompt directories left behind by hard-killed Pi processes. */
export function cleanupStalePromptDirs(now = Date.now()): number {
	const root = os.tmpdir();
	let removed = 0;
	let names: string[];
	try {
		names = fs.readdirSync(root);
	} catch {
		return 0;
	}
	for (const name of names) {
		if (!name.startsWith(TEMP_DIR_PREFIX)) continue;
		const candidate = path.join(root, name);
		try {
			const stat = fs.lstatSync(candidate);
			if (!stat.isDirectory() || stat.isSymbolicLink()) continue;
			if (typeof process.getuid === "function" && stat.uid !== process.getuid()) continue;
			if (now - stat.mtimeMs < STALE_TEMP_MAX_AGE_MS) continue;
			fs.rmSync(candidate, { recursive: true, force: true });
			removed++;
		} catch {
			// Best-effort startup hygiene; never disable the extension for cleanup.
		}
	}
	return removed;
}

/* ------------------------------------------------------- helpers */

export function getFinalOutput(messages: Message[]): string {
	for (let i = messages.length - 1; i >= 0; i--) {
		const msg = messages[i];
		if (msg.role === "assistant") {
			for (const part of msg.content) {
				if (part.type === "text") return part.text;
			}
		}
	}
	return "";
}

export function isFailed(result: RunResult): boolean {
	return (
		result.exitCode !== 0 ||
		result.timedOut ||
		result.wasAborted ||
		result.stopReason === "error" ||
		result.stopReason === "aborted"
	);
}

export function getResultOutput(result: RunResult): string {
	if (isFailed(result)) {
		return result.errorMessage || result.stderr || getFinalOutput(result.messages) || "(no output)";
	}
	return getFinalOutput(result.messages) || "(no output)";
}

export function capOutput(output: string): string {
	const byteLength = Buffer.byteLength(output, "utf8");
	if (byteLength <= OUTPUT_CAP) return output;
	let truncated = output.slice(0, OUTPUT_CAP);
	while (Buffer.byteLength(truncated, "utf8") > OUTPUT_CAP) truncated = truncated.slice(0, -1);
	const omitted = byteLength - Buffer.byteLength(truncated, "utf8");
	return `${truncated}\n\n[Output truncated: ${omitted} bytes omitted. Full evidence retained in tool details.]`;
}

async function writePromptToTempFile(label: string, prompt: string): Promise<{ dir: string; filePath: string }> {
	const tmpDir = await fs.promises.mkdtemp(path.join(os.tmpdir(), TEMP_DIR_PREFIX));
	const safeName = label.replace(/[^\w.-]+/g, "_");
	const filePath = path.join(tmpDir, `prompt-${safeName}.md`);
	await fs.promises.writeFile(filePath, prompt, { encoding: "utf-8", mode: 0o600 });
	return { dir: tmpDir, filePath };
}

function getPiInvocation(args: string[]): { command: string; args: string[] } {
	const currentScript = process.argv[1];
	const isBunVirtualScript = currentScript?.startsWith("/$bunfs/root/");
	if (currentScript && !isBunVirtualScript && fs.existsSync(currentScript)) {
		return { command: process.execPath, args: [currentScript, ...args] };
	}
	const execName = path.basename(process.execPath).toLowerCase();
	const isGenericRuntime = /^(node|bun)(\.exe)?$/.test(execName);
	if (!isGenericRuntime) {
		return { command: process.execPath, args };
	}
	return { command: "pi", args };
}

/* ------------------------------------------------------- runRole */

export interface RunRoleParams {
	cwd: string;
	view: RoleView;
	/** Extra system-prompt text appended for this role (role brief). */
	systemPrompt: string;
	/** The task/prompt text delivered as the child's user message. */
	prompt: string;
	signal?: AbortSignal;
	onUpdate?: OnUpdate;
	timeoutMs?: number;
	label?: string;
}

/**
 * Run a single role in an isolated child pi process and return a structured
 * result. Never throws for normal failures — inspect `isFailed(result)`.
 */
export async function runRole(params: RunRoleParams): Promise<RunResult> {
	const { cwd, view, systemPrompt, prompt, signal, onUpdate } = params;
	const timeoutMs = params.timeoutMs ?? DEFAULT_TIMEOUT_MS;
	const label = params.label ?? view.role;

	const result: RunResult = {
		role: view.role,
		provider: view.provider,
		model: view.model,
		exitCode: 0,
		messages: [],
		stderr: "",
		usage: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, cost: 0, contextTokens: 0, turns: 0 },
		wasAborted: false,
		timedOut: false,
	};

	const emitUpdate = () => {
		if (!onUpdate) return;
		onUpdate({
			content: [{ type: "text", text: getFinalOutput(result.messages) || "(running…)" }],
			details: { kind: "pb-primitive", results: [result], label },
		});
	};

	let systemTmpDir: string | null = null;
	let systemTmpPath: string | null = null;
	let taskTmpDir: string | null = null;
	let taskTmpPath: string | null = null;

	try {
		if (systemPrompt.trim()) {
			const tmp = await writePromptToTempFile(`${label}-system`, systemPrompt);
			systemTmpDir = tmp.dir;
			systemTmpPath = tmp.filePath;
		}
		const taskTmp = await writePromptToTempFile(`${label}-task`, prompt);
		taskTmpDir = taskTmp.dir;
		taskTmpPath = taskTmp.filePath;

		const args = buildChildArgs(view, { appendSystemPromptFile: systemTmpPath ?? undefined });
		// Pi expands @text-file arguments into the initial user message. Keep task
		// content out of argv so large plans/evidence cannot hit execve E2BIG.
		args.push(`@${taskTmpPath}`);

		const exitCode = await new Promise<number>((resolve) => {
			const invocation = getPiInvocation(args);
			const proc = spawn(invocation.command, invocation.args, {
				cwd,
				shell: false,
				stdio: ["ignore", "pipe", "pipe"],
				// env inherited implicitly — carries pi auth without us reading it.
			});
			liveChildren.add(proc);

			let buffer = "";
			let timer: NodeJS.Timeout | null = null;
			let killGrace: NodeJS.Timeout | null = null;
			let settled = false;
			let abortHandler: (() => void) | null = null;

			const processLine = (line: string) => {
				if (!line.trim()) return;
				let event: any;
				try {
					event = JSON.parse(line);
				} catch {
					return;
				}
				if (event.type === "message_end" && event.message) {
					const msg = event.message as Message;
					result.messages.push(msg);
					if (msg.role === "assistant") {
						result.usage.turns++;
						const u = (msg as any).usage;
						if (u) {
							result.usage.input += u.input || 0;
							result.usage.output += u.output || 0;
							result.usage.cacheRead += u.cacheRead || 0;
							result.usage.cacheWrite += u.cacheWrite || 0;
							result.usage.cost += u.cost?.total || 0;
							result.usage.contextTokens = u.totalTokens || 0;
						}
						if (!result.model && (msg as any).model) result.model = (msg as any).model;
						if ((msg as any).stopReason) result.stopReason = (msg as any).stopReason;
						if ((msg as any).errorMessage) result.errorMessage = (msg as any).errorMessage;
					}
					emitUpdate();
				}
				if (event.type === "tool_result_end" && event.message) {
					result.messages.push(event.message as Message);
					emitUpdate();
				}
			};

			proc.stdout.on("data", (data) => {
				buffer += data.toString();
				const lines = buffer.split("\n");
				buffer = lines.pop() || "";
				for (const line of lines) processLine(line);
			});
			proc.stderr.on("data", (data) => {
				result.stderr += data.toString();
			});

			const cleanup = () => {
				if (timer) clearTimeout(timer);
				if (killGrace) clearTimeout(killGrace);
				if (signal && abortHandler) signal.removeEventListener("abort", abortHandler);
				liveChildren.delete(proc);
			};

			const finish = (code: number) => {
				if (settled) return;
				settled = true;
				if (buffer.trim()) processLine(buffer);
				cleanup();
				resolve(code);
			};

			const killProc = (reason: "abort" | "timeout") => {
				if (settled) return;
				if (reason === "abort") result.wasAborted = true;
				if (reason === "timeout") result.timedOut = true;
				try {
					proc.kill("SIGTERM");
				} catch {
					/* ignore */
				}
				killGrace = setTimeout(() => {
					try {
						proc.kill("SIGKILL");
					} catch {
						/* ignore */
					}
				}, KILL_GRACE_MS);
			};

			proc.on("close", (code) => finish(code ?? (result.wasAborted || result.timedOut ? 1 : 0)));
			proc.on("error", () => {
				result.stderr += result.stderr ? "" : "failed to spawn child pi process";
				finish(1);
			});

			timer = setTimeout(() => killProc("timeout"), timeoutMs);

			if (signal) {
				abortHandler = () => killProc("abort");
				if (signal.aborted) abortHandler();
				else signal.addEventListener("abort", abortHandler, { once: true });
			}
		});

		result.exitCode = exitCode;
		if (result.timedOut && !result.errorMessage) {
			result.errorMessage = `Timed out after ${Math.round(timeoutMs / 1000)}s`;
		}
		if (result.wasAborted && !result.errorMessage) {
			result.errorMessage = "Aborted";
		}
		return result;
	} finally {
		for (const tmpDir of [systemTmpDir, taskTmpDir]) {
			if (!tmpDir) continue;
			try {
				fs.rmSync(tmpDir, { recursive: true, force: true });
			} catch {
				/* ignore */
			}
		}
	}
}
