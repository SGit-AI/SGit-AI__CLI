# Brief B08 — Workflow Runtime Polish

**Owner:** **Villager Dev**
**Status:** Ready. NEW brief, sourced from Sonnet debrief §7 ideas.
**Estimated effort:** ~1 day
**Touches:** `sgit_ai/workflow/Workflow__Runner.py`, `sgit_ai/cli/dev/CLI__Dev__Workflow.py`, `sgit_ai/plugins/_base/Plugin__Loader.py`, tests.

---

## Why this brief exists

The Sonnet debrief surfaced four small workflow-runtime / plugin-runtime improvements that are all small, all high-quality, and all ready to ship. Combined into one brief because each is too small standalone.

---

## Required reading

1. This brief.
2. `team/villager/v0.12.x__perf-brief-pack/02__sonnet-session-update-2026-05-05.md` §7 — the source ideas.
3. The four target files listed in "Touches" above.
4. `team/villager/v0.12.x__perf-brief-pack/design__07__transaction-log.md` — the audit-log design.

---

## Scope

### Polish 1 — `sgit dev workflow list` auto-discovery (debrief §7.4)

**Today:** `CLI__Dev__Workflow` only knows `Workflow__Clone` (hard-coded). After B04 + B03 land, push/pull/fetch/clone-readonly/clone-transfer workflows exist; the dev CLI should show them all.

**Fix:** `Workflow__Registry` walks `sgit_ai/workflow/*/Workflow__*.py` at startup and registers every `Workflow` subclass. `CLI__Dev__Workflow.list()` consumes the registry.

This pattern mirrors `Plugin__Loader.discover()` — same approach, different target dir.

### Polish 2 — `sgit dev workflow resume --from-step <name>` (debrief §7.1)

**Today:** workspaces persist step-by-step state but the CLI has no way to re-run a single step. `Workflow__Runner.run()` is "all or nothing".

**Fix:** add `Workflow__Runner.resume_from(step_name) -> dict` that:
1. Loads the existing workspace.
2. Marks all steps from `step_name` onward as `pending` in the manifest.
3. Resumes execution from `step_name`, reading prior steps' outputs from the workspace.

CLI: `sgit dev workflow resume <work-id> --from-step <name>`. Useful for iterating on a failing step without re-running expensive earlier steps.

### Polish 3 — Persistent transaction log (debrief §7.5 + design D7)

**Today:** `Workflow__Runner` has a transaction-log emission path (lines ~80–95 of the runner) but writes to the workspace dir, which is cleaned up on success. So nothing persists across runs.

**Fix:** when `SGIT_TRACE=1` env var is set OR `--trace` flag is passed:
1. Write one JSON line per step to `.sg_vault/local/trace.jsonl`.
2. Add `sgit dev workflow trace <vault-dir>` command that reads + pretty-prints the log.
3. Default behaviour (no env / flag) is unchanged — no audit log writes. Per design D7.

### Polish 4 — Plugin manifest round-trip validation (debrief §7.2)

**Today:** `Plugin__Loader.load_manifest()` reads JSON with `data.get()` calls and manually constructs `Schema__Plugin_Manifest`. A malformed manifest may load with missing fields and only fail at use-time.

**Fix:** Replace `data.get(...)` chain with `Schema__Plugin_Manifest.from_json(data)`. This applies Safe_Str validators at load time and catches malformed manifests immediately.

Round-trip invariant test: `assert Schema__Plugin_Manifest.from_json(obj.json()).json() == obj.json()`.

### Polish 5 — Per-plugin configuration (debrief §7.3)

**Today:** `~/.sgit/config.json` supports `enabled: bool` and `stability_required: str` per plugin. Some plugins might want their own keys (e.g., a hypothetical `history` plugin's `max_commits_shown: int`).

**Fix:** Extend `Schema__Plugin_Config` to allow arbitrary per-plugin keys; the loader reads but doesn't validate them; plugins consume their own keys. Schema:

```python
class Schema__Plugin_Toggle(Type_Safe):
    enabled            : bool                        = True
    stability_required : Enum__Plugin_Stability      = STABLE
    settings           : dict[Safe_Str, Safe_Str]    = None  # arbitrary per-plugin
```

(If `dict[Safe_Str, Safe_Str]` doesn't satisfy Type_Safe — use a dedicated `Schema__Plugin_Settings` per plugin in a future brief. For now, the loose dict is acceptable.)

---

## Hard rules

- **Type_Safe** for new schemas.
- **Workspace lifetime decisions unchanged** (D7 says off by default; this brief honors that).
- **No mocks.**
- **Coverage must not regress.**
- **Backward compat:** existing `~/.sgit/config.json` files keep working.

---

## Acceptance criteria

- [ ] `Workflow__Registry` exists and is consumed by `sgit dev workflow list`.
- [ ] `Workflow__Runner.resume_from(step_name)` works + has a test.
- [ ] `SGIT_TRACE=1` writes `.sg_vault/local/trace.jsonl`; default doesn't.
- [ ] `sgit dev workflow trace <vault-dir>` pretty-prints trace logs.
- [ ] `Plugin__Loader` uses `Schema__Plugin_Manifest.from_json(data)`.
- [ ] Plugin round-trip invariant test passes.
- [ ] Per-plugin `settings` field added to plugin config; loader reads but doesn't validate; plugin consumes.
- [ ] At least 5 new tests across the 5 polishes.
- [ ] Suite passes; coverage non-negative.

---

## When done

Return a ≤ 250-word summary:
1. Each of the 5 polishes confirmed.
2. New tests + coverage delta.
3. Any polish that surfaced a deeper issue (escalate).
