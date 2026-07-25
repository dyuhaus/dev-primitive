#!/usr/bin/env python3
"""Explainable, deterministic task router for the configurable agent framework.

The router never calls a model and never dispatches work itself.  It produces a
recommendation which the calling harness must show and confirm before invoking
the selected profile.  Direct-call-only profiles, including Team Leader, are
hard excluded even if a malformed configuration claims they are eligible.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

ROOT = Path(__file__).resolve().parent
DEFAULT_CONFIG = ROOT / "roles.config.json"

# Specific signals intentionally take precedence over broad capability words.
# Each tuple is (signal name, regex, agent weights, explanatory text).
RULES: Tuple[Tuple[str, str, Dict[str, int], str], ...] = (
    ("vault", r"\b(vault|obsidian|wikilink|wiki\s*link|broken\s+link|cross[- ]?link|navigation\s+hub|table\s+of\s+contents|toc|note\s+taxonomy|index)\b", {"librarian": 12}, "Vault, navigation, or link-maintenance language"),
    ("technical-docs", r"\b(readme|runbook|api\s+(?:reference|docs?|documentation)|configuration\s+reference|architecture\s+note|implementation\s+guide|technical\s+documentation)\b", {"tech-writer": 11}, "technical-documentation artifact language"),
    ("general-prose", r"\b(email|e-?mail|letter|proposal|speech|narrative|announcement|press\s+release|correspondence|copywriting|launch\s+copy)\b", {"prose-writer": 11}, "audience-facing prose language"),
    ("frontend", r"\b(front[- ]?end|frontend|react|vue|component|css|html|tailwind|responsive|accessib(?:ility|le)|a11y|keyboard|layout|design\s+system|ui|user\s+interface)\b", {"fe-designer": 10}, "frontend, responsive, or accessibility language"),
    ("complex-engineering", r"\b(architecture|architectural|root[- ]?cause|trade[- ]?off|migration|distributed|service\s+design|system\s+design|refactor(?:ing)?\s+(?:the\s+)?(?:\w+\s+)?service|redesign\s+(?:the\s+)?(?:\w+\s+)?service|broker\s+service)\b", {"planner": 11, "builder": 4}, "architecture or complex-engineering language"),
    ("implementation", r"\b(implement|build|code|program|fix|debug|test|script|parser)\b", {"builder": 4, "l1-programmer": 3}, "implementation language"),
    ("explicit-outline", r"\b(explicit(?:ly)?\s+(?:outlined|specified)|exact\s+outline|following\s+(?:this|the)\s+(?:outline|plan|steps)|small\s+(?:isolated\s+)?(?:script|fix|test)|unit\s+test)\b", {"l1-programmer": 8}, "clear, small outlined implementation language"),
    ("routine-maintenance", r"\b(clean\s*up|cleanup|rotate|logs?|maintenance|status|housekeeping|routine|permissions?\s+check|update\s+dependency)\b", {"runner": 6}, "routine maintenance language"),
    ("multi-workstream", r"\b(coordinate|workstreams?|multiple\s+agents?|across\s+(?:several|multiple)|dependencies\s+between|website.*docs.*email|launch.*docs)\b", {}, "multi-workstream coordination language"),
)


def load_config(path: Path) -> Dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("config root must be an object")
    return data


def eligible_profiles(config: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Return profiles that are safe automatic-recommendation destinations."""
    profiles: Dict[str, Dict[str, Any]] = {}
    for key, entry in (config.get("roles") or {}).items():
        if key in {"planner", "builder"} and isinstance(entry, dict):
            profiles[key] = entry
    for key, entry in (config.get("agents") or {}).items():
        if not isinstance(entry, dict):
            continue
        # Belt-and-suspenders: never route Team Leader, even with bad metadata.
        if key == "team-leader" or entry.get("invocation") == "direct-call-only":
            continue
        if entry.get("autoSelectEligible") is True:
            profiles[key] = entry
    return profiles


def extract_signals(task: str, cwd: str = "") -> Dict[str, Any]:
    """Extract stable, inspectable task facts without accessing project files."""
    text = task.lower()
    matched: List[Dict[str, str]] = []
    weights: Dict[str, int] = {}
    for name, pattern, additions, explanation in RULES:
        if re.search(pattern, text, flags=re.IGNORECASE):
            matched.append({"name": name, "reason": explanation})
            for agent, score in additions.items():
                weights[agent] = weights.get(agent, 0) + score

    path_hints: List[str] = []
    combined_paths = f"{task}\n{cwd}".lower()
    if any(part in combined_paths for part in ("obsidian vault", "vaultrepo", ".obsidian", "/vault/")) and "vault" not in {item["name"] for item in matched}:
        matched.append({"name": "vault-path", "reason": "Vault path hint"})
        weights["librarian"] = weights.get("librarian", 0) + 10
        path_hints.append("Vault path")
    if re.search(r"\.(?:tsx|jsx|css|scss|vue|html)\b", combined_paths) and "frontend" not in {item["name"] for item in matched}:
        matched.append({"name": "frontend-path", "reason": "frontend source-file hint"})
        weights["fe-designer"] = weights.get("fe-designer", 0) + 8
        path_hints.append("frontend source path")

    terms = re.findall(r"[a-z0-9][a-z0-9_-]*", text)
    ambiguous = (
        len(terms) < 3
        or bool(re.search(r"\b(help|handle this|do this|fix it|something|whatever|unsure|ambiguous)\b", text))
        or not matched
    )
    return {
        "matched": matched,
        "weights": weights,
        "pathHints": path_hints,
        "hasExplicitOutline": any(item["name"] == "explicit-outline" for item in matched),
        "hasMultipleWorkstreams": any(item["name"] == "multi-workstream" for item in matched),
        "ambiguous": ambiguous,
    }


def _capability_matches(task: str, capabilities: Iterable[Any]) -> List[str]:
    """Small config-driven bonus so custom profiles remain somewhat useful."""
    text_words = set(re.findall(r"[a-z][a-z-]+", task.lower()))
    matches: List[str] = []
    for capability in capabilities:
        phrase = str(capability).lower()
        words = [word for word in re.findall(r"[a-z][a-z-]+", phrase) if len(word) > 3]
        if words and any(word in text_words for word in words):
            matches.append(str(capability))
    return matches


def score_candidates(config: Dict[str, Any], task: str, signals: Dict[str, Any]) -> List[Dict[str, Any]]:
    profiles = eligible_profiles(config)
    weights: Dict[str, int] = signals["weights"]
    candidates: List[Dict[str, Any]] = []
    for key, entry in profiles.items():
        score = weights.get(key, 0)
        reasons = [item["reason"] for item in signals["matched"] if weights.get(key, 0) and key in _agents_for_signal(item["name"])]
        capability_matches = _capability_matches(task, entry.get("capabilities", []))
        if capability_matches:
            bonus = min(2, len(capability_matches))
            score += bonus
            reasons.append("matching configured capability: " + ", ".join(capability_matches[:2]))
        # A simple guardrail: when a concrete domain is known, Planner should
        # not overtake that specialist merely because the word "design" occurs.
        if key == "planner" and any(weights.get(k, 0) >= 10 for k in ("librarian", "tech-writer", "prose-writer", "fe-designer")):
            score = max(0, score - 5)
        if key == "l1-programmer" and weights.get("planner", 0) >= 10 and not signals["hasExplicitOutline"]:
            score = max(0, score - 5)
        candidates.append({"agent": key, "score": score, "reasons": reasons})
    candidates.sort(key=lambda item: (-item["score"], item["agent"]))
    return candidates


def _agents_for_signal(signal_name: str) -> set:
    for name, _pattern, additions, _reason in RULES:
        if name == signal_name:
            return set(additions)
    if signal_name == "vault-path":
        return {"librarian"}
    if signal_name == "frontend-path":
        return {"fe-designer"}
    return set()


def _confidence(top_score: int, second_score: int, ambiguous: bool) -> float:
    if top_score <= 0:
        return 0.20
    base = min(0.90, 0.45 + top_score * 0.045)
    margin = min(0.08, max(0, top_score - second_score) * 0.012)
    if ambiguous:
        base -= 0.20
    return round(max(0.05, min(0.95, base + margin)), 2)


def route(task: str, config: Dict[str, Any], cwd: str = "") -> Dict[str, Any]:
    """Return an explainable recommendation dictionary. No work is dispatched."""
    signals = extract_signals(task, cwd)
    candidates = score_candidates(config, task, signals)
    routing = config.get("routing") if isinstance(config.get("routing"), dict) else {}
    automatic = routing.get("automaticSelection") if isinstance(routing.get("automaticSelection"), dict) else {}
    threshold = automatic.get("threshold", 0.60)
    threshold = float(threshold) if isinstance(threshold, (int, float)) and not isinstance(threshold, bool) else 0.60
    fallback = automatic.get("fallback", "runner")
    if fallback == "team-leader" or fallback not in eligible_profiles(config):
        fallback = "runner" if "runner" in eligible_profiles(config) else (candidates[0]["agent"] if candidates else "runner")

    top = candidates[0] if candidates else {"agent": fallback, "score": 0, "reasons": []}
    second = candidates[1] if len(candidates) > 1 else {"score": 0}
    confidence = _confidence(int(top["score"]), int(second["score"]), bool(signals["ambiguous"]))
    needs_clarification = bool(signals["ambiguous"]) or confidence < threshold or int(top["score"]) < 4
    selected = fallback if needs_clarification else top["agent"]
    # Absolute safety rule independent of config and scores.
    if selected == "team-leader":
        selected = fallback
        needs_clarification = True

    reasons: List[str] = []
    if selected == top["agent"]:
        reasons.extend(top["reasons"] or [f"highest eligible score ({top['score']})"])
    else:
        reasons.append(f"confidence {confidence:.2f} is below the {threshold:.2f} recommendation threshold; using {fallback} as the safe front door")
    if signals["hasMultipleWorkstreams"]:
        reasons.append("multiple workstreams detected: Team Leader is direct-call-only and requires explicit user invocation")
    questions: List[str] = []
    if needs_clarification:
        questions.append("What concrete artifact or outcome should be produced?")
        if signals["hasMultipleWorkstreams"]:
            questions.append("Should this be coordinated as multiple workstreams? If so, explicitly invoke Team Leader.")
        elif selected == "runner":
            questions.append("Is this routine maintenance, a technical document, general prose, Vault organization, frontend UI, or software implementation?")

    decision = {
        "status": "recommendation",
        "selected": selected,
        "confidence": confidence,
        "threshold": threshold,
        "reasons": reasons,
        "signals": signals,
        "candidates": candidates,
        "needs_clarification": needs_clarification,
        "questions": questions,
        "automaticSelectionEnabled": bool(automatic.get("enabled", False)),
    }
    _audit_if_enabled(task, decision, automatic)
    return decision


def _audit_if_enabled(task: str, decision: Dict[str, Any], automatic: Dict[str, Any]) -> None:
    audit = automatic.get("audit") if isinstance(automatic.get("audit"), dict) else {}
    if not audit.get("enabled"):
        return
    raw_path = audit.get("path", "runtime/routing-audit.jsonl")
    if not isinstance(raw_path, str) or not raw_path.strip():
        return
    path = Path(raw_path)
    if not path.is_absolute():
        path = ROOT / path
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "taskSha256": hashlib.sha256(task.encode("utf-8")).hexdigest(),
        "selected": decision["selected"],
        "confidence": decision["confidence"],
        "needsClarification": decision["needs_clarification"],
        "signalNames": [item["name"] for item in decision["signals"]["matched"]],
        "candidateScores": [{"agent": item["agent"], "score": item["score"]} for item in decision["candidates"]],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def format_human(decision: Dict[str, Any], explain: bool) -> str:
    lines = [
        f"Recommendation: {decision['selected']} ({decision['confidence']:.0%} confidence)",
        "Status: confirmation required before invoking an agent.",
    ]
    for reason in decision["reasons"]:
        lines.append(f"- {reason}")
    if decision["needs_clarification"]:
        lines.append("Clarification needed:")
        lines.extend(f"- {question}" for question in decision["questions"])
    if explain:
        lines.extend(["", "Candidate scores:"])
        lines.extend(f"- {item['agent']}: {item['score']}" for item in decision["candidates"])
        names = ", ".join(item["name"] for item in decision["signals"]["matched"]) or "none"
        lines.append(f"Signals: {names}")
    return "\n".join(lines)


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Explainable deterministic agent-router recommendation")
    parser.add_argument("task", help="task to classify (quote it in the shell)")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG), help="roles configuration path")
    parser.add_argument("--cwd", default="", help="working-directory hint used only for classification")
    parser.add_argument("--json", action="store_true", help="print a JSON decision")
    parser.add_argument("--explain", action="store_true", help="print full candidate-score explanation")
    args = parser.parse_args(argv)
    try:
        config = load_config(Path(args.config).expanduser())
        decision = route(args.task, config, args.cwd)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"router error: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(decision, indent=2, sort_keys=True))
    else:
        print(format_human(decision, args.explain))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
