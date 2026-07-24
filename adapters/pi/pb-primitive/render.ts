/**
 * pb-primitive / render.ts
 *
 * TUI rendering helpers for the planner_agent / builder_agent tool results and
 * for the /pb, /pbg, /pb-show report messages. Rendering-only; no process or
 * config logic lives here.
 */

import { getMarkdownTheme } from "@earendil-works/pi-coding-agent";
import type { Message } from "@earendil-works/pi-ai";
import { Box, Container, Markdown, Spacer, Text } from "@earendil-works/pi-tui";
import { getFinalOutput, isFailed, type RunResult, type RunResultDetails } from "./subagent.ts";

function formatTokens(count: number): string {
	if (count < 1000) return count.toString();
	if (count < 10000) return `${(count / 1000).toFixed(1)}k`;
	if (count < 1000000) return `${Math.round(count / 1000)}k`;
	return `${(count / 1000000).toFixed(1)}M`;
}

export function formatUsageStats(r: RunResult): string {
	const u = r.usage;
	const parts: string[] = [];
	if (u.turns) parts.push(`${u.turns} turn${u.turns > 1 ? "s" : ""}`);
	if (u.input) parts.push(`↑${formatTokens(u.input)}`);
	if (u.output) parts.push(`↓${formatTokens(u.output)}`);
	if (u.cacheRead) parts.push(`R${formatTokens(u.cacheRead)}`);
	if (u.cacheWrite) parts.push(`W${formatTokens(u.cacheWrite)}`);
	if (u.cost) parts.push(`$${u.cost.toFixed(4)}`);
	if (u.contextTokens > 0) parts.push(`ctx:${formatTokens(u.contextTokens)}`);
	if (r.model) parts.push(`${r.provider}/${r.model}`);
	return parts.join(" ");
}

type DisplayItem = { type: "text"; text: string } | { type: "toolCall"; name: string; args: Record<string, any> };

export function getDisplayItems(messages: Message[]): DisplayItem[] {
	const items: DisplayItem[] = [];
	for (const msg of messages) {
		if (msg.role === "assistant") {
			for (const part of msg.content) {
				if (part.type === "text") items.push({ type: "text", text: part.text });
				else if (part.type === "toolCall")
					items.push({ type: "toolCall", name: part.name, args: (part as any).arguments });
			}
		}
	}
	return items;
}

function formatToolCall(name: string, args: Record<string, any>, fg: (c: any, t: string) => string): string {
	const preview = (s: string, n: number) => (s.length > n ? `${s.slice(0, n)}…` : s);
	switch (name) {
		case "bash":
			return fg("muted", "$ ") + fg("toolOutput", preview(String(args?.command ?? "…"), 60));
		case "read":
			return fg("muted", "read ") + fg("accent", String(args?.path ?? args?.file_path ?? "…"));
		case "write":
			return fg("muted", "write ") + fg("accent", String(args?.path ?? args?.file_path ?? "…"));
		case "edit":
			return fg("muted", "edit ") + fg("accent", String(args?.path ?? args?.file_path ?? "…"));
		case "grep":
			return fg("muted", "grep ") + fg("accent", `/${String(args?.pattern ?? "")}/`);
		case "find":
			return fg("muted", "find ") + fg("accent", String(args?.pattern ?? "*"));
		case "ls":
			return fg("muted", "ls ") + fg("accent", String(args?.path ?? "."));
		default:
			return fg("accent", name) + fg("dim", ` ${preview(JSON.stringify(args ?? {}), 50)}`);
	}
}

const COLLAPSED_ITEMS = 10;

/** Render a single role RunResult (used by planner_agent / builder_agent). */
export function renderRoleResult(details: RunResultDetails | undefined, result: any, expanded: boolean, theme: any) {
	if (!details || details.results.length === 0) {
		const text = result?.content?.[0];
		return new Text(text?.type === "text" ? text.text : "(no output)", 0, 0);
	}
	const r = details.results[0];
	const err = isFailed(r);
	const icon = err ? theme.fg("error", "✗") : theme.fg("success", "✓");
	const roleLabel = details.label ?? r.role;
	const items = getDisplayItems(r.messages);
	const finalOutput = getFinalOutput(r.messages);
	const mdTheme = getMarkdownTheme();

	const header = () => {
		let h = `${icon} ${theme.fg("toolTitle", theme.bold(roleLabel))} ${theme.fg("muted", `(${r.provider}/${r.model})`)}`;
		if (err && r.stopReason) h += ` ${theme.fg("error", `[${r.stopReason}]`)}`;
		return h;
	};

	if (expanded) {
		const c = new Container();
		c.addChild(new Text(header(), 0, 0));
		if (err && r.errorMessage) c.addChild(new Text(theme.fg("error", `Error: ${r.errorMessage}`), 0, 0));
		c.addChild(new Spacer(1));
		for (const item of items) {
			if (item.type === "toolCall")
				c.addChild(new Text(theme.fg("muted", "→ ") + formatToolCall(item.name, item.args, theme.fg.bind(theme)), 0, 0));
		}
		if (finalOutput) {
			c.addChild(new Spacer(1));
			c.addChild(new Markdown(finalOutput.trim(), 0, 0, mdTheme));
		}
		const usage = formatUsageStats(r);
		if (usage) {
			c.addChild(new Spacer(1));
			c.addChild(new Text(theme.fg("dim", usage), 0, 0));
		}
		return c;
	}

	let text = header();
	if (err && r.errorMessage) text += `\n${theme.fg("error", `Error: ${r.errorMessage}`)}`;
	else if (items.length === 0) text += `\n${theme.fg("muted", "(no output)")}`;
	else {
		const shown = items.slice(-COLLAPSED_ITEMS);
		const skipped = items.length - shown.length;
		if (skipped > 0) text += `\n${theme.fg("muted", `… ${skipped} earlier items`)}`;
		for (const item of shown) {
			if (item.type === "text")
				text += `\n${theme.fg("toolOutput", item.text.split("\n").slice(0, 3).join("\n"))}`;
			else text += `\n${theme.fg("muted", "→ ") + formatToolCall(item.name, item.args, theme.fg.bind(theme))}`;
		}
		if (skipped > 0) text += `\n${theme.fg("muted", "(Ctrl+O to expand)")}`;
	}
	const usage = formatUsageStats(r);
	if (usage) text += `\n${theme.fg("dim", usage)}`;
	return new Text(text, 0, 0);
}

/** Render a pb-primitive report message (markdown body inside a boxed card). */
export function renderReportMessage(message: any, opts: { expanded: boolean }, theme: any) {
	const mdTheme = getMarkdownTheme();
	const box = new Box(1, 1, (t: string) => theme.bg("customMessageBg", t));
	const content = typeof message.content === "string" ? message.content : "";
	box.addChild(new Markdown(content.trim() || "(empty report)", 0, 0, mdTheme));
	return box;
}
