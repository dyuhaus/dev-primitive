/**
 * pb-primitive / config.ts
 *
 * Pure, side-effect-light config logic for the two-role development primitive.
 *
 * The single source of truth is dev-primitive/roles.config.json. This module
 * mirrors the resolution + validation semantics of dev-primitive/apply.py so
 * the pi adapter is a *live* reader of the same config (not a generated copy).
 *
 * Precedence: the nearest project-level roles.config.json (walking up from the
 * working directory) overrides the machine-default config. If none is found,
 * the machine default is used. This mirrors how AGENTS.md nests.
 *
 * No secrets ever live in the config — only the *names* of env vars. This
 * module never reads or prints secret values.
 */

import * as fs from "node:fs";
import * as path from "node:path";

/** Shared, harness-neutral default configuration. */
export const MACHINE_DEFAULT_CONFIG = "/home/dyadmin/dev-primitive/roles.config.json";
/** Pi-only complete configuration, consulted only when no project config exists. */
export const PI_DEFAULT_CONFIG = "/home/dyadmin/dev-primitive/adapters/pi/roles.config.pi.json";

export type ConfigSourceKind = "project" | "pi-overlay" | "machine";

export interface ConfigPaths {
	machineDefault?: string;
	piOverlay?: string;
}

export interface ModelMutation {
	/** New model class/identifier. A bare model update clears a prior pinned id. */
	model?: string;
	/** Optional exact model id pin. This overrides class resolution when non-empty. */
	id?: string;
	/** Provider key defined in the selected configuration's providers map. */
	provider?: string;
}

export const ROLE_KEYS = ["planner", "builder"] as const;
export type RoleKey = (typeof ROLE_KEYS)[number];

const PROVIDER_TYPES = ["anthropic", "openai", "google", "local"] as const;

export interface ModelSpec {
	class?: string;
	id?: string;
	provider?: string;
}

export interface RoleSpec {
	purpose?: string;
	readOnly?: boolean;
	model?: ModelSpec;
	canDelegate?: boolean;
	delegateTo?: string[];
}

export interface AgentSpec extends RoleSpec {
	displayName?: string;
	tools?: string[];
	invocation?: "default" | "direct-call-only";
	autoSelectEligible?: boolean;
	capabilities?: string[];
	boundaries?: string[];
	escalateTo?: string[];
	outputContract?: string[];
	infoSources?: string[];
}

export interface ProviderSpec {
	type?: string;
	apiKeyEnv?: string;
	baseUrlEnv?: string;
}

export interface RolesConfig {
	version?: number;
	description?: string;
	roles?: Record<string, RoleSpec>;
	agents?: Record<string, AgentSpec>;
	routing?: {
		note?: string;
		automaticSelection?: {
			enabled?: boolean;
			status?: string;
			threshold?: number;
			fallback?: string;
			audit?: { enabled?: boolean; path?: string };
		};
		[k: string]: unknown;
	};
	providers?: Record<string, ProviderSpec>;
}

export interface RoleView {
	role: string;
	displayName: string;
	/** Resolved model string: pinned id wins, else the class/alias. */
	model: string;
	class: string;
	id: string;
	provider: string;
	providerType: string;
	apiKeyEnv: string;
	baseUrlEnv: string;
	purpose: string;
	readOnly: boolean;
	tools: string[];
	invocation: "default" | "direct-call-only";
	autoSelectEligible: boolean;
	capabilities: string[];
	boundaries: string[];
	escalateTo: string[];
	canDelegate: boolean;
	delegateTo: string[];
	outputContract: string[];
	infoSources: string[];
	/** true when a pinned id is active (no auto-upgrade). */
	pinned: boolean;
}

export interface LoadResult {
	/** Absolute path the config was read from. */
	sourcePath: string;
	/** Project configs are false; Pi overlay and shared machine config are true. */
	isDefault: boolean;
	/** Which precedence layer supplied the resolved configuration. */
	sourceKind: ConfigSourceKind;
	/** Nonfatal reason the Pi overlay was skipped in favor of the shared config. */
	overlayWarning: string | null;
	/** Parsed config, or null when read/parse failed. */
	cfg: RolesConfig | null;
	/** A read/parse error string, or null. */
	loadError: string | null;
	/** Validation errors ([] means valid; only meaningful when cfg != null). */
	errors: string[];
}

/* ------------------------------------------------------------------ loading */

function candidateNames(dir: string): string[] {
	return [path.join(dir, "roles.config.json"), path.join(dir, ".pi", "roles.config.json")];
}

/** Return the nearest project-local configuration, or null when none exists. */
export function resolveProjectConfigPath(cwd: string, machineDefault = MACHINE_DEFAULT_CONFIG): string | null {
	let dir = path.resolve(cwd);
	const sharedRealPath = safeReal(machineDefault);
	while (true) {
		for (const candidate of candidateNames(dir)) {
			if (!isFile(candidate)) continue;
			// The shared registry can be encountered while working inside
			// dev-primitive itself. It remains a machine default, not a project
			// override, so Pi should still apply its Pi-only overlay.
			if (safeReal(candidate) === sharedRealPath) continue;
			return candidate;
		}
		const parent = path.dirname(dir);
		if (parent === dir) return null;
		dir = parent;
	}
}

/**
 * Resolve the nominal Pi path. `loadResolved` additionally validates the
 * overlay and falls back to the shared config if it is absent or invalid.
 */
export function resolveConfigPath(cwd: string, paths: ConfigPaths = {}): { path: string; isDefault: boolean } {
	const machineDefault = paths.machineDefault ?? MACHINE_DEFAULT_CONFIG;
	const project = resolveProjectConfigPath(cwd, machineDefault);
	if (project) return { path: project, isDefault: false };
	const overlay = paths.piOverlay ?? PI_DEFAULT_CONFIG;
	return { path: isFile(overlay) ? overlay : machineDefault, isDefault: true };
}

function isFile(p: string): boolean {
	try {
		return fs.statSync(p).isFile();
	} catch {
		return false;
	}
}

function safeReal(p: string): string {
	try {
		return fs.realpathSync(p);
	} catch {
		return path.resolve(p);
	}
}

/** Read and JSON-parse a config file. Never throws. */
export function loadConfigFile(file: string): { cfg: RolesConfig | null; loadError: string | null } {
	let raw: string;
	try {
		raw = fs.readFileSync(file, "utf-8");
	} catch (e) {
		return { cfg: null, loadError: `config not found or unreadable: ${file}` };
	}
	try {
		return { cfg: JSON.parse(raw) as RolesConfig, loadError: null };
	} catch (e) {
		return { cfg: null, loadError: `config is not valid JSON: ${(e as Error).message}` };
	}
}

/** Resolve + load + validate the config appropriate for `cwd`. Never throws.
 * Project configuration always wins. Otherwise Pi alone tries its complete
 * overlay, safely falling back to the shared machine configuration on failure.
 */
export function loadResolved(cwd: string, paths: ConfigPaths = {}): LoadResult {
	const machineDefault = paths.machineDefault ?? MACHINE_DEFAULT_CONFIG;
	const project = resolveProjectConfigPath(cwd, machineDefault);
	if (project) {
		const { cfg, loadError } = loadConfigFile(project);
		return { sourcePath: project, isDefault: false, sourceKind: "project", overlayWarning: null, cfg, loadError, errors: cfg ? validateConfig(cfg) : [] };
	}

	const overlayPath = paths.piOverlay ?? PI_DEFAULT_CONFIG;
	const overlay = loadConfigFile(overlayPath);
	if (overlay.cfg && !overlay.loadError) {
		const errors = validateConfig(overlay.cfg);
		if (!errors.length) return { sourcePath: overlayPath, isDefault: true, sourceKind: "pi-overlay", overlayWarning: null, cfg: overlay.cfg, loadError: null, errors };
		const warning = `Pi overlay is invalid (${errors.join("; ")}); using shared config instead.`;
		return loadMachine(paths, warning);
	}
	const warning = overlay.loadError ? `Pi overlay unavailable (${overlay.loadError}); using shared config instead.` : null;
	return loadMachine(paths, warning);
}

function loadMachine(paths: ConfigPaths, overlayWarning: string | null): LoadResult {
	const sourcePath = paths.machineDefault ?? MACHINE_DEFAULT_CONFIG;
	const { cfg, loadError } = loadConfigFile(sourcePath);
	return { sourcePath, isDefault: true, sourceKind: "machine", overlayWarning, cfg, loadError, errors: cfg ? validateConfig(cfg) : [] };
}

/* -------------------------------------------------------------- validation */

/**
 * Validate a parsed config. Returns human-readable error strings ([] = valid).
 * Mirrors dev-primitive/apply.py validate() so the two stay in lockstep.
 */
export function validateConfig(cfg: RolesConfig | null | undefined): string[] {
	const errs: string[] = [];
	if (!cfg || typeof cfg !== "object") {
		return ["config must be an object"];
	}

	if (typeof cfg.version !== "number" || !Number.isInteger(cfg.version) || cfg.version < 1) {
		errs.push("version must be an integer >= 1");
	}

	let providers = cfg.providers;
	if (typeof providers !== "object" || providers === null || Object.keys(providers).length === 0) {
		errs.push("providers must be a non-empty object");
		providers = {};
	} else {
		for (const [name, prov] of Object.entries(providers)) {
			if (typeof prov !== "object" || prov === null) {
				errs.push(`providers.${name} must be an object`);
				continue;
			}
			if (!PROVIDER_TYPES.includes((prov.type as any))) {
				errs.push(`providers.${name}.type must be one of anthropic|openai|google|local`);
			}
			if (typeof prov.apiKeyEnv !== "string") {
				errs.push(`providers.${name}.apiKeyEnv must be a string`);
			}
		}
	}

	const roles = cfg.roles;
	if (typeof roles !== "object" || roles === null) {
		errs.push("roles must be an object");
	}
	function validateEntry(entry: RoleSpec | undefined, pathName: string, specialist = false): void {
		if (typeof entry !== "object" || entry === null) {
			errs.push(`${pathName} must be an object`);
			return;
		}
		if (typeof entry.purpose !== "string" || !entry.purpose) errs.push(`${pathName}.purpose must be a non-empty string`);
		const model = entry.model;
		if (typeof model !== "object" || model === null) {
			errs.push(`${pathName}.model must be an object`);
			return;
		}
		const cls = typeof model.class === "string" ? model.class : "";
		const mid = typeof model.id === "string" ? model.id : "";
		if (model.class !== undefined && typeof model.class !== "string") errs.push(`${pathName}.model.class must be a string`);
		if (model.id !== undefined && typeof model.id !== "string") errs.push(`${pathName}.model.id must be a string`);
		if (!(String(mid).trim() || String(cls).trim())) errs.push(`${pathName}.model needs a non-empty class or id`);
		const provName = model.provider;
		if (typeof provName !== "string" || !provName) errs.push(`${pathName}.model.provider must be a string`);
		else if (!(provName in (providers as object))) errs.push(`${pathName}.model.provider '${provName}' is not defined in providers`);
		if (entry.canDelegate !== undefined && typeof entry.canDelegate !== "boolean") errs.push(`${pathName}.canDelegate must be boolean`);
		if (entry.delegateTo !== undefined && (!Array.isArray(entry.delegateTo) || !entry.delegateTo.every((x) => typeof x === "string"))) errs.push(`${pathName}.delegateTo must be a list of strings`);
		if (!specialist) return;
		const agent = entry as AgentSpec;
		if (typeof agent.displayName !== "string" || !agent.displayName) errs.push(`${pathName}.displayName must be a non-empty string`);
		if (agent.invocation !== "default" && agent.invocation !== "direct-call-only") errs.push(`${pathName}.invocation must be default or direct-call-only`);
		if (typeof agent.autoSelectEligible !== "boolean") errs.push(`${pathName}.autoSelectEligible must be boolean`);
		else if (agent.invocation === "direct-call-only" && agent.autoSelectEligible) errs.push(`${pathName}: direct-call-only agents cannot be auto-select eligible`);
		for (const field of ["tools", "capabilities", "boundaries", "escalateTo", "outputContract"] as const) {
			if (!Array.isArray(agent[field]) || !agent[field]!.every((x) => typeof x === "string")) errs.push(`${pathName}.${field} must be a list of strings`);
		}
	}
	for (const key of ROLE_KEYS) {
		if (!roles?.[key]) errs.push(`roles.${key} is required and must be an object`);
		else validateEntry(roles[key], `roles.${key}`);
	}
	const selection = cfg.routing?.automaticSelection;
	if (selection !== undefined) {
		if (typeof selection !== "object" || selection === null) errs.push("routing.automaticSelection must be an object");
		else {
			if (selection.enabled !== undefined && typeof selection.enabled !== "boolean") errs.push("routing.automaticSelection.enabled must be boolean");
			if (selection.status !== undefined && typeof selection.status !== "string") errs.push("routing.automaticSelection.status must be a string");
			if (selection.threshold !== undefined && (typeof selection.threshold !== "number" || !Number.isFinite(selection.threshold) || selection.threshold < 0 || selection.threshold > 1)) errs.push("routing.automaticSelection.threshold must be a number from 0 to 1");
			const fallback = selection.fallback;
			if (fallback !== undefined) {
				const profile = cfg.agents?.[fallback];
				if (typeof fallback !== "string" || !profile) errs.push("routing.automaticSelection.fallback must reference a registered specialist");
				else if (profile.invocation === "direct-call-only" || !profile.autoSelectEligible) errs.push("routing.automaticSelection.fallback must reference an auto-select-eligible, non-direct-call-only specialist");
			}
			const audit = selection.audit;
			if (audit !== undefined) {
				if (typeof audit !== "object" || audit === null) errs.push("routing.automaticSelection.audit must be an object");
				else {
					if (audit.enabled !== undefined && typeof audit.enabled !== "boolean") errs.push("routing.automaticSelection.audit.enabled must be boolean");
					if (audit.path !== undefined && (typeof audit.path !== "string" || !audit.path.trim())) errs.push("routing.automaticSelection.audit.path must be a non-empty string");
				}
			}
		}
	}
	if (cfg.agents !== undefined) {
		if (typeof cfg.agents !== "object" || cfg.agents === null) errs.push("agents must be an object");
		else {
			for (const [key, agent] of Object.entries(cfg.agents)) validateEntry(agent, `agents.${key}`, true);
			const known = new Set([...Object.keys(roles ?? {}), ...Object.keys(cfg.agents)]);
			for (const [namespace, entries] of [["roles", roles ?? {}], ["agents", cfg.agents]] as const) {
				for (const [key, entry] of Object.entries(entries)) for (const field of ["delegateTo", "escalateTo"] as const) {
					for (const target of ((entry as AgentSpec)[field] ?? [])) if (!known.has(target)) errs.push(`${namespace}.${key}.${field} references unknown agent '${target}'`);
				}
			}
		}
	}

	return errs;
}

/* --------------------------------------------------------------- resolution */

/** Pinned id wins; otherwise the customizable class/alias. */
export function resolveModel(role: RoleSpec | undefined): string {
	const model = role?.model ?? {};
	const mid = String(model.id ?? "").trim();
	return mid ? mid : String(model.class ?? "").trim();
}

/** Return every configured PB role and specialist key in stable config order. */
export function configuredAgentKeys(cfg: RolesConfig): string[] {
	return [...Object.keys(cfg.roles ?? {}), ...Object.keys(cfg.agents ?? {})];
}

/** Resolve a configured PB role or specialist entry without throwing. */
export function getConfiguredAgent(cfg: RolesConfig, key: string): AgentSpec | undefined {
	return (cfg.roles?.[key] ?? cfg.agents?.[key]) as AgentSpec | undefined;
}

/** Apply one model mutation in memory. The caller validates and persists it. */
export function mutateModel(cfg: RolesConfig, key: string, update: ModelMutation): string[] {
	const entry = getConfiguredAgent(cfg, key);
	if (!entry) throw new Error(`agent '${key}' is not configured`);
	if (!entry.model) entry.model = {};
	if (update.model === undefined && update.id === undefined && update.provider === undefined) {
		throw new Error("provide a model, --id <exact-id>, or --provider <provider>");
	}
	const changes: string[] = [];
	if (update.model !== undefined) {
		let model = update.model.trim();
		if (!model) throw new Error("model must not be empty");
		// Pi accepts provider and model separately. Accept the common
		// `openrouter/<model-id>` shortcut, but persist the canonical model id
		// so child invocation never becomes openrouter/openrouter/<model-id>.
		if (model.startsWith("openrouter/")) {
			if (update.provider !== undefined && update.provider.trim() !== "openrouter") {
				throw new Error("an openrouter/ model prefix requires provider 'openrouter'");
			}
			model = model.slice("openrouter/".length);
			if (!model) throw new Error("model must not be empty after the openrouter/ prefix");
			if (update.provider === undefined && entry.model.provider !== "openrouter") {
				entry.model.provider = "openrouter";
				changes.push("provider -> 'openrouter' (inferred from model prefix)");
			}
		}
		entry.model.class = model;
		changes.push(`class -> '${model}'`);
		if (update.id === undefined && String(entry.model.id ?? "").trim()) {
			entry.model.id = "";
			changes.push("id -> '' (cleared so class is active)");
		}
	}
	if (update.id !== undefined) {
		entry.model.id = update.id.trim();
		changes.push(update.id.trim() ? `id -> '${update.id.trim()}'` : "id -> '' (pin cleared)");
	}
	if (update.provider !== undefined) {
		const provider = update.provider.trim();
		if (!provider) throw new Error("provider must not be empty");
		if (!cfg.providers?.[provider]) throw new Error(`provider '${provider}' is not defined in the Pi overlay`);
		entry.model.provider = provider;
		changes.push(`provider -> '${provider}'`);
	}
	if (!resolveModel(entry)) throw new Error("model class or id must remain non-empty");
	return changes;
}

/** Atomically persist a validated configuration without copying any secrets. */
export function writeConfigAtomic(file: string, cfg: RolesConfig): void {
	const dir = path.dirname(file);
	const base = path.basename(file);
	const temp = path.join(dir, `.${base}.${process.pid}.${Date.now()}.tmp`);
	let mode = 0o644;
	try { mode = fs.statSync(file).mode & 0o777; } catch { /* use default */ }
	try {
		fs.writeFileSync(temp, `${JSON.stringify(cfg, null, 2)}\n`, { encoding: "utf-8", mode });
		fs.renameSync(temp, file);
	} finally {
		try { if (fs.existsSync(temp)) fs.unlinkSync(temp); } catch { /* ignore cleanup */ }
	}
}

/**
 * Build a resolved view of a role. Assumes the config already validated;
 * defensively tolerates missing pieces so /pb-show can still render.
 */
export function roleView(cfg: RolesConfig, key: string): RoleView {
	const role = (cfg.roles?.[key] ?? cfg.agents?.[key] ?? {}) as AgentSpec;
	const model = role.model ?? {};
	const provName = String(model.provider ?? "");
	const prov = cfg.providers?.[provName] ?? {};
	const id = String(model.id ?? "");
	return {
		role: key,
		displayName: String(role.displayName ?? key),
		model: resolveModel(role),
		class: String(model.class ?? ""),
		id,
		provider: provName,
		providerType: String(prov.type ?? ""),
		apiKeyEnv: String(prov.apiKeyEnv ?? ""),
		baseUrlEnv: String(prov.baseUrlEnv ?? ""),
		purpose: String(role.purpose ?? ""),
		readOnly: Boolean(role.readOnly),
		tools: Array.isArray(role.tools) ? role.tools.map(String) : [],
		invocation: role.invocation === "direct-call-only" ? "direct-call-only" : "default",
		autoSelectEligible: Boolean(role.autoSelectEligible),
		capabilities: Array.isArray(role.capabilities) ? role.capabilities.map(String) : [],
		boundaries: Array.isArray(role.boundaries) ? role.boundaries.map(String) : [],
		escalateTo: Array.isArray(role.escalateTo) ? role.escalateTo.map(String) : [],
		canDelegate: Boolean(role.canDelegate),
		delegateTo: Array.isArray(role.delegateTo) ? role.delegateTo.map(String) : [],
		outputContract: Array.isArray(role.outputContract) ? role.outputContract.map(String) : [],
		infoSources: Array.isArray(role.infoSources) ? role.infoSources.map(String) : [],
		pinned: id.trim().length > 0,
	};
}

/* ------------------------------------------------------------- table render */

/**
 * Render the resolved role/model table. Intentionally byte-compatible with
 * dev-primitive/apply.py print_table() (including Python-style True/False) so
 * /pb-show output can be diffed against `apply.py validate`.
 */
export function renderResolvedTable(cfg: RolesConfig): string {
	const lines: string[] = [];
	lines.push(`config version ${cfg.version}  —  resolved agents:`);
	lines.push("");
	for (const key of ROLE_KEYS) {
		const v = roleView(cfg, key);
		const pin = v.id.trim() ? "pinned id" : "class (auto-upgrades)";
		lines.push(`  ${key.padEnd(14)} -> model '${v.model}'  [${pin}]`);
		lines.push(
			`           provider=${v.provider} (${v.providerType}), ` +
				`keyEnv=${v.apiKeyEnv || "-"}, ` +
				`baseUrlEnv=${v.baseUrlEnv || "-"}, readOnly=${v.readOnly ? "True" : "False"}`,
		);
	}
	for (const key of Object.keys(cfg.agents ?? {})) {
		const v = roleView(cfg, key);
		lines.push(`  ${key.padEnd(14)} -> model '${v.model}'  [${v.invocation}, autoSelect=${v.autoSelectEligible ? "True" : "False"}]`);
	}
	lines.push("");
	return lines.join("\n");
}

/** The exact text `apply.py validate` prints on success (for parity checks). */
export function renderValidatedReport(cfg: RolesConfig): string {
	return `Config is valid.\n\n${renderResolvedTable(cfg)}`;
}

/* ------------------------------------------------------------- input parsing */

/**
 * Split a /pbg argument string on a case-insensitive `until:` marker.
 * Text before the marker is the task; text after is the done-condition.
 * When there is no marker, the whole string is the task and until is null.
 */
export function parseTaskAndUntil(input: string): { task: string; until: string | null } {
	const s = input ?? "";
	const matches = Array.from(s.matchAll(/(?:^|\s)until\s*:/gi));
	const m = matches.at(-1);
	if (!m || m.index === undefined) return { task: s.trim(), until: null };
	const markerStart = m.index;
	const task = s.slice(0, markerStart).trim();
	const until = s.slice(markerStart + m[0].length).trim();
	return { task, until: until.length ? until : null };
}
