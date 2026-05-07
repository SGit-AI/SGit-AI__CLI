# Brief 09 — Structured error handling at schema-parse boundaries

**Date:** 2026-05-07
**Audience:** SGit Dev Agent
**Scheduling:** lands alongside or after brief 07 (which introduces `.vault-settings` as a new parse boundary). Estimated effort: ~½ day.
**Author:** Villager orchestrator (Opus)

---

## 1. Why this exists

Today, when sgit downloads a payload from the server (vault index, branch meta, commit, tree, blob, `.vault-settings`, move-history) and the payload doesn't match the expected `Schema__*` shape, the parse failure surfaces as a generic Python `ValueError` or `TypeError` from inside `Type_Safe.from_json(...)`. By the time the user sees it, all useful context is gone:

```
$ sgit-ac clone coral-bank-5246
Cloning into 'coral-bank-5246'...
  ▸ Checking SGit-AI for vault: coral-bank-5246
  ▸ Vault found on SGit-AI — cloning with simple token keys
  ▸ Deriving vault keys
  ▸ Downloading vault index
error: ValueError in "clone" — Cannot convert '2026-05-07T01:28:18.495Z' to integer
  at /usr/local/lib/python3.12/site-packages/sgit_ai/workflow/Workflow__Runner.py:128 in run
  run with --debug for full details
```

The user is told nothing useful: which schema failed, which field, what value was expected, what producer might have written the bad data, what to do about it. The actual root cause was the SG/Send web client writing `created_at` as an ISO 8601 string when sgit's `Schema__Branch_Meta.created_at` is `Safe_UInt__Timestamp` (epoch ms). The schema is correct; the wire-boundary error handling is bad.

This brief fixes the error handling. The schema types (`Safe_UInt__Timestamp` and friends) stay as they are — epoch ms is the canonical sgit timestamp type and shouldn't change. What changes is how sgit reports parse failures.

---

## 2. The fix

### 2a. New typed exception

In `sgit_ai/core/Vault__Errors.py` (extend the existing typed-error module):

```python
class Vault__Schema_Parse_Error(Exception):
    """Wire payload failed to parse against the expected Type_Safe schema."""
    def __init__(self, *, schema: str, source: str, field: str = '',
                 value: str = '', cause: Exception = None):
        self.schema = schema   # 'Schema__Branch_Meta'
        self.source = source   # 'bare/indexes/<index-id> from https://dev.send.sgraph.ai'
        self.field  = field    # 'created_at' (best-effort; '' if unparseable)
        self.value  = value    # the offending value (truncated to 80 chars)
        self.cause  = cause
        super().__init__(self._format_message())

    def _format_message(self) -> str:
        parts = [f'Failed to parse {self.schema}']
        if self.source:
            parts.append(f'from {self.source}')
        if self.field:
            parts.append(f'— field "{self.field}" rejected value {self.value!r}')
        elif self.value:
            parts.append(f'— offending value {self.value!r}')
        if self.cause:
            parts.append(f'(underlying: {type(self.cause).__name__}: {self.cause})')
        return '; '.join(parts)
```

Round-trip not required (it's an exception, not a schema). The error carries enough structured data that the CLI's friendly-error path can format it however it wants.

### 2b. New helper — `parse_or_raise`

In `sgit_ai/schemas/_helpers.py` (new file):

```python
import re

def parse_or_raise(schema_cls, payload: dict, source: str):
    """Parse `payload` into `schema_cls`. On failure, raise Vault__Schema_Parse_Error
    with structured context including the offending field name and value when
    extractable from the underlying exception.
    """
    from sgit_ai.core.Vault__Errors import Vault__Schema_Parse_Error
    try:
        return schema_cls.from_json(payload)
    except (ValueError, TypeError) as exc:
        field, value = _extract_field_and_value(exc, payload)
        raise Vault__Schema_Parse_Error(
            schema = schema_cls.__name__,
            source = source,
            field  = field,
            value  = value,
            cause  = exc,
        ) from exc

def _extract_field_and_value(exc: Exception, payload: dict) -> tuple:
    """Best-effort extraction of which field caused the parse failure.
    Type_Safe error messages typically include the offending value;
    cross-reference with the payload to find which field it came from.
    """
    msg = str(exc)
    match = re.search(r"Cannot convert '([^']+)'", msg)
    if not match:
        return '', ''
    bad_value = match.group(1)
    # Search the payload for the field that holds this value
    for k, v in (payload or {}).items():
        if str(v) == bad_value:
            return k, bad_value[:80]
    return '', bad_value[:80]
```

The field-extraction is best-effort — it depends on the underlying Type_Safe error format. If the format changes, we fall back to surfacing just the value, which is still better than nothing. The pattern is robust enough for the common case (single-field rejection on a flat schema).

### 2c. Apply at every wire-boundary parse site

Audit every `Schema__*.from_json(...)` call where the input came from the server, and replace with `parse_or_raise(Schema__*, payload, source_label)`. The `source_label` should be specific enough that the user can locate the bad data:

| Step | Schema | Source label |
|---|---|---|
| `Step__Clone__Download_Index` | `Schema__Branch_Index` | `f'bare/indexes/{index_id} from {api_url}'` |
| `Step__Clone__Download_Branch_Meta` | `Schema__Branch_Meta` | `f'branch {branch_id} in vault index'` |
| `Step__Clone__Walk_Commits` | `Schema__Object_Commit` | `f'commit {commit_id} from {api_url}'` |
| `Step__Clone__Walk_Trees` | `Schema__Object_Tree` | `f'tree {tree_id} from {api_url}'` |
| `Migration__Runner._load_applied` | `Schema__Migrations_Applied` | `f'.sg_vault/local/migrations.json'` |
| `Vault__Backup` (when brief 04 lands) | `Schema__Backup_Manifest` | `f'manifest.json inside backup zip {zip_path}'` |
| `Vault__Sync__Move` (when brief 02 lands) | `Schema__Vault_Moves` | `f'move-history.json from {api_url}'` |
| `Vault__Sync__Settings` (when brief 07 lands) | `Schema__Vault_Settings` | `f'.vault-settings blob in tree {tree_id}'` |

Same pattern at each site — the helper is small, the call is one line.

### 2d. CLI friendly-error formatting

In `CLI__Main.py._print_friendly_error` (or wherever uncaught exceptions are formatted for users):

```python
from sgit_ai.core.Vault__Errors import Vault__Schema_Parse_Error

def _print_friendly_error(self, exc, args):
    if isinstance(exc, Vault__Schema_Parse_Error):
        print(f'error: {exc}', file=sys.stderr)
        print(file=sys.stderr)
        print(f'  This usually means the vault was created or modified by a', file=sys.stderr)
        print(f'  client that wrote {exc.schema!r} in an incompatible format.', file=sys.stderr)
        print(file=sys.stderr)
        print(f'  Likely causes:', file=sys.stderr)
        print(f'    - The SG/Send web client wrote the data with a different', file=sys.stderr)
        print(f'      type than sgit expects (e.g. ISO timestamp string', file=sys.stderr)
        print(f'      instead of epoch milliseconds).', file=sys.stderr)
        print(f'    - The vault was created by a much older or much newer', file=sys.stderr)
        print(f'      sgit version with a different schema.', file=sys.stderr)
        print(file=sys.stderr)
        print(f'  To debug:', file=sys.stderr)
        print(f'    sgit --debug {sys.argv[1] if len(sys.argv) > 1 else "..."} \\', file=sys.stderr)
        print(f'      # see the full request/response payloads', file=sys.stderr)
        return
    # ... existing handling for other exception types ...
```

Actionable error message — names the schema, names the source, lists likely causes, points at the debug flag.

### 2e. Workflow__Runner step-name in error rewrap

In `sgit_ai/workflow/Workflow__Runner.py` around line 126–130:

```python
if status != Enum__Workflow_Status.SUCCESS:
    if _exc is not None:
        # Include the step name in the re-raised error message
        step_context = f'step "{self._current_step_name}" of ' if self._current_step_name else ''
        contextual_msg = f'{step_context}workflow "{self.workflow.workflow_name()}": {error_msg}'
        try:
            raise type(_exc)(contextual_msg) from _exc
        except TypeError:
            raise RuntimeError(contextual_msg) from _exc
    raise RuntimeError(error_msg or 'Workflow failed')
```

Where `self._current_step_name` is set at the start of each step's execution and cleared on success. This requires a small change to the runner's step loop to track the current step. After the change, the error reads:

```
error: ValueError in step "download-index" of workflow "clone": Failed to parse Schema__Branch_Meta from branch <branch-id> in vault index; field "created_at" rejected value '2026-05-07T01:28:18.495Z'; (underlying: ValueError: Cannot convert '2026-05-07T01:28:18.495Z' to integer)
```

Much more actionable.

---

## 3. Tests

In `tests/unit/schemas/test__helpers__parse_or_raise.py` (new):

1. `test_parse_or_raise_succeeds_on_valid_payload` — happy path; returns the parsed schema instance.
2. `test_parse_or_raise_wraps_value_error` — pass a payload with a string-where-int-expected; assert `Vault__Schema_Parse_Error` raised with `.schema`, `.source`, `.cause` populated.
3. `test_parse_or_raise_extracts_field_and_value` — pass a payload like `{'created_at': '2026-05-07T...', ...}`; assert `.field == 'created_at'` and `.value == '2026-05-07T...'` in the raised error.
4. `test_parse_or_raise_handles_unextractable_failure` — when the field can't be back-mapped, `.field == ''` and the error is still useful.
5. `test_parse_or_raise_preserves_chain` — `__cause__` on the re-raised error points at the original `ValueError`/`TypeError`.

In `tests/unit/core/test_Vault__Errors__Schema_Parse.py` (new):

6. `test_schema_parse_error_message_format` — round-trip the format string; covers both with-field and without-field cases.
7. `test_schema_parse_error_truncates_long_value` — value over 80 chars is truncated for display.

In `tests/unit/cli/test_CLI__Main__Friendly_Error.py` (extend):

8. `test_friendly_error_for_schema_parse_includes_schema_name` — set up a fake parse failure; capture stderr; assert it contains the schema name + "incompatible format" hint.
9. `test_friendly_error_for_schema_parse_suggests_debug_flag` — assert the output mentions `--debug`.

In `tests/unit/workflow/test_Workflow__Runner__Step_Name_In_Error.py` (new):

10. `test_workflow_error_includes_step_name` — register a workflow that raises in step 2; assert the re-raised exception's message contains the step name.
11. `test_workflow_error_step_name_with_typed_exception` — same but the step raises a custom typed exception; assert the TypeError fallback in the runner still includes the step name.

Plus an end-to-end test using a real `Vault__API__In_Memory` fixture:

12. `test_clone_with_malformed_branch_meta_raises_schema_parse_error` — set up the in-memory API to serve a `Schema__Branch_Index` payload where one branch's `created_at` is an ISO string; run `sgit clone <token>`; assert the user sees the structured error referencing `Schema__Branch_Meta` + `created_at` + the offending value.

---

## 4. Out of scope

- **Changing any `Safe_*` type to be more lenient** — `Safe_UInt__Timestamp` stays an integer. Schema types are the canonical contract; producers must match them.
- **Schema versioning / migration** — if a producer writes a future schema version, that's a separate problem. Today's brief is purely about reporting parse failures clearly when they happen.
- **Auto-recovery** — sgit should NOT attempt to coerce ISO strings to epoch ms automatically. Surface the error; let the producer fix the input.
- **Validation of payloads on push** — sgit's push path serialises Type_Safe instances, so it can't write malformed data. No need to add server-side validation; the schema enforces it on the client.

---

## 5. Dependencies and ordering

- Helper (`parse_or_raise`) and exception (`Vault__Schema_Parse_Error`) land first in their own commit.
- Apply to existing parse sites in a second commit.
- Wire into the friendly-error path in a third commit.
- Workflow__Runner step-name change is a fourth commit (independent).
- Tests in a fifth commit.

When briefs 02, 04, 07 land later, they should adopt `parse_or_raise` from the start at their new parse sites — the brief calls these out by name in §2c. Worth adding a one-line note to the start-here briefing pointing the Dev Agent at this brief whenever they introduce a new schema-parse boundary.

---

## 6. Verification checklist

When done:

- All ~12 new tests pass.
- The existing failing case (`sgit clone coral-bank-5246` with malformed `created_at`) produces an actionable error naming `Schema__Branch_Meta`, `created_at`, and the offending value — instead of the generic Python `ValueError`.
- Every existing `Schema__*.from_json(...)` call on server payloads is replaced with `parse_or_raise`.
- Workflow runner errors include the step name, not just the workflow name.
- KNOWN_VIOLATIONS unchanged.

Estimated effort: ~½ day total (helper + exception ~1h, apply to ~8 sites ~1.5h, friendly-error CLI integration ~1h, runner step-name ~30min, tests ~2h).
