# pi adapter

The pi adapter is a **live adapter**, not a generated one.

It is installed globally at:

```text
$HOME/.pi/agent/extensions/pb-primitive/
```

The extension reads the nearest project `roles.config.json` or
`.pi/roles.config.json`, falling back to the checked-out copy of this
repository's `roles.config.json`. Therefore this repository's
configuration remains the single source of truth and there is no `apply.py pi`
generation step that can become stale.

The live adapter provides:

- `planner_agent` and `builder_agent` tools;
- `/pb` for one plan-to-build pass;
- `/pbg` for a bounded plan/build/verify loop;
- `/pb-show` for config and model resolution diagnostics.

Planner read-only behavior is enforced by the child pi tool allowlist
`read,grep,find,ls`. Provider and model are passed explicitly for both child
roles. See the installed extension's `README.md` for operation, validation, and
security details.

Validate without a model call:

```bash
node ~/.pi/agent/extensions/pb-primitive/_selftest.mjs
pi --no-extensions -e ~/.pi/agent/extensions/pb-primitive/index.ts --list-models fable
python3 apply.py validate   # from the repository root
```

This adapter intentionally does not change role configuration. Continue using
`roles.config.json` and the existing `apply.py set` workflow for model changes.

The provider fields consumed by the `api` transport (`baseUrl`, the
`~/appdata/<provider>/api-key` keyfile default, and provider-scoped
`classIds["<provider>:<class>"]` keys) are ignored by this pi adapter — it passes
provider and model explicitly through pi's own model selection.
