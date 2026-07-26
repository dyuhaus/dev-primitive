#!/usr/bin/env python3
"""Run a review on an external (non-Anthropic) model configured in the registry.

Why this exists
---------------
Some profiles in ``roles.config.json`` deliberately run on a model from another
vendor family so their judgement is independent of the family being reviewed —
``agents.audit`` and ``routing.postWorkflowAudit`` both select GPT-5.6 Sol
through OpenRouter for exactly that reason.

Pi can honor that natively because it dispatches per-agent providers. Claude
Code cannot: its subagent ``model:`` frontmatter accepts only Anthropic classes
and ids, and an unrecognized value is silently discarded, leaving the subagent
on the session's own model. A file that says ``model: openai/gpt-5.6-sol`` and
then runs on Claude is worse than no cross-family review at all, because the
verdict still reads as independent.

This script closes that gap for any harness that cannot dispatch the provider
itself: the harness-side agent gathers evidence, then calls this script to get
the actual verdict from the configured external model. It is stdlib-only and
follows the same OpenRouter call shape as ``objectification/ob.py``.

Failure is always loud. If the key is missing, the model is unavailable, or the
call fails, this exits non-zero with an explicit message so the calling agent
cannot quietly substitute its own opinion for the external one.

Usage
-----
    external_review.py --check
    external_review.py --profile workflow-audit --input review.md
    cat review.md | external_review.py --profile audit

Secrets are read from the environment or a local env file and are never printed,
logged, or included in output.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
CONFIG = ROOT / "roles.config.json"

# Searched in order; the first file defining a non-empty key wins. These are
# local credential stores outside any repository.
ENV_FILES = (
    Path.home() / "appdata" / "objectification" / ".env",
    Path.home() / "appdata" / "model-eval" / ".env",
)

DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
KEY_VAR = "OPENROUTER_API_KEY"

# Map the registry's thinking levels onto OpenRouter's reasoning effort.
THINKING_TO_EFFORT = {"low": "low", "medium": "medium", "high": "high"}


def fail(message: str) -> "NoReturn":  # noqa: F821
    sys.stderr.write(f"external_review: {message}\n")
    raise SystemExit(2)


def load_config() -> dict:
    try:
        return json.loads(CONFIG.read_text(encoding="utf-8"))
    except FileNotFoundError:
        fail(f"missing registry: {CONFIG}")
    except ValueError as exc:
        fail(f"invalid JSON in {CONFIG}: {exc}")


def profile_model(cfg: dict, profile: str) -> dict:
    """Resolve {id, provider, thinking} for a named profile."""
    if profile == "workflow-audit":
        node = (cfg.get("routing") or {}).get("postWorkflowAudit") or {}
        model = node.get("model") or {}
        thinking = node.get("thinking", "medium")
    else:
        entry = (cfg.get("agents") or {}).get(profile)
        if not entry:
            fail(f"no agent '{profile}' in {CONFIG}")
        model = entry.get("model") or {}
        thinking = model.get("thinking", "")
    model_id = model.get("id") or model.get("class") or ""
    if not model_id:
        fail(f"profile '{profile}' has no model id or class configured")
    provider = model.get("provider", "")
    if provider == "anthropic":
        fail(
            f"profile '{profile}' is configured for provider 'anthropic'; it should "
            "run natively on the harness model, not through this script"
        )
    return {"id": model_id, "provider": provider, "thinking": thinking}


def read_key() -> str:
    """Return the OpenRouter key from the environment or a local env file.

    The value is never printed. Only its source is reported, and only on error.
    """
    value = os.environ.get(KEY_VAR, "").strip()
    if value:
        return value
    for path in ENV_FILES:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            name, _, raw = line.partition("=")
            if name.strip() != KEY_VAR:
                continue
            raw = raw.strip().strip("'\"")
            if raw:
                return raw
    searched = ", ".join(str(p) for p in ENV_FILES)
    fail(
        f"no {KEY_VAR} in the environment or any local env file ({searched}). "
        "Run the documented secret intake; do not paste the key into a prompt."
    )


def base_url() -> str:
    return os.environ.get("OPENROUTER_BASE_URL", DEFAULT_BASE_URL).rstrip("/")


def chat_completion(model: dict, prompt: str, key: str, timeout: int) -> str:
    body = {
        "model": model["id"],
        "messages": [{"role": "user", "content": prompt}],
    }
    effort = THINKING_TO_EFFORT.get(model.get("thinking", ""))
    if effort:
        body["reasoning"] = {"effort": effort}
    request = urllib.request.Request(
        base_url() + "/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": "Bearer " + key,
            "Content-Type": "application/json",
            "X-Title": "dev-primitive-external-review",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", "replace")[:400]
        except OSError:
            pass
        fail(f"HTTP {exc.code} from the provider. {detail}")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        fail(f"could not reach the provider: {exc}")
    except ValueError as exc:
        fail(f"provider returned invalid JSON: {exc}")

    if isinstance(payload.get("error"), dict):
        fail(f"provider error: {payload['error'].get('message', payload['error'])}")
    choices = payload.get("choices") or []
    if not choices:
        fail("provider returned no choices")
    text = ((choices[0].get("message") or {}).get("content") or "").strip()
    if not text:
        fail("provider returned an empty review")
    return text


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Get a review verdict from the configured external model."
    )
    parser.add_argument(
        "--profile",
        default="workflow-audit",
        help="registry profile to resolve the model from (default: workflow-audit)",
    )
    parser.add_argument("--input", help="file containing the review payload (default: stdin)")
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify configuration and key availability without calling the provider",
    )
    parser.add_argument("--timeout", type=int, default=300, help="request timeout in seconds")
    args = parser.parse_args()

    cfg = load_config()
    model = profile_model(cfg, args.profile)

    if args.check:
        read_key()  # raises with guidance when absent
        thinking = model["thinking"] or "(provider default)"
        print(f"profile:  {args.profile}")
        print(f"model:    {model['id']}")
        print(f"provider: {model['provider']}")
        print(f"thinking: {thinking}")
        print(f"endpoint: {base_url()}")
        print(f"{KEY_VAR}: present")
        return

    if args.input:
        try:
            prompt = Path(args.input).read_text(encoding="utf-8")
        except OSError as exc:
            fail(f"could not read --input: {exc}")
    else:
        prompt = sys.stdin.read()
    if not prompt.strip():
        fail("empty review payload; provide it on stdin or with --input")

    verdict = chat_completion(model, prompt, read_key(), args.timeout)
    # The header makes the provenance of the verdict unambiguous in transcripts,
    # so a reader can tell an external review from the calling model's own text.
    print(f"[external review — {model['id']} via {model['provider']}]")
    print()
    print(verdict)


if __name__ == "__main__":
    main()
