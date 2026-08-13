# Brief 17 — Commit-id prefix resolution on the CLI

**Date:** 2026-05-07
**Audience:** SGit Dev Agent
**Scheduling:** lands as a small reviewer-fix-style pass; can fold into brief 16 or stand alone. Estimated effort: ~½ day.
**Author:** Villager orchestrator (Opus)

---

## 1. Why this exists

`sgit history log` prints commit IDs with the `obj-cas-imm-` prefix stripped — short, scannable, exactly what users want to see:

```
$ sgit history log -n 4
  6c6191cdf3a8 (HEAD)  @Content: mail to @Dinis ...
  64ad437be4f0          Merge current into local
  7bb808ebb2fc          @Content: status vault live ...
  1293ff9a80ee          @Content: components-in-markdown brief ...
```

But every command that accepts a commit-id argument expects the **full** form. When the user copies `6c6191cdf3a8` from the log into `history diff`, the resolver does a literal lookup on `.sg_vault/bare/data/6c6191cdf3a8` and gets `FileNotFoundError`. The CLI then surfaces the misleading hint "run sgit pull" — but the object IS local, just under a different name.

```
$ sgit history diff "6c6191cdf3a8..1293ff9a80ee" --files-only
error: [Errno 2] No such file or directory:
  Safe_Str__Vault_Path('./.sg_vault/bare/data/6c6191cdf3a8')
  hint: object not cached locally — run: sgit pull  to fetch missing history     ← wrong
```

This makes the conductor-agent and human-typed-CLI flows broken in different ways:
- **Agents using `--json`** are fine — the JSON output contains the full `commit_id` with prefix.
- **Humans copying hashes from `history log`** are NOT fine — every diff/show/reset/revert command rejects the short form.

Git solves this by accepting any unique prefix of a commit hash (`git show 6c6191`). Sgit should do the same.

---

## 2. The fix

### 2a. New helper: `_resolve_commit_id`

In `sgit_ai/storage/Vault__Object_Store.py` (it lives close to where the lookups happen) or `sgit_ai/cli/_helpers.py` (already exists for `parse_commit_range`), add:

```python
def resolve_commit_id(input_id: str, obj_store) -> str:
    """Resolve a user-supplied commit identifier to the full obj-cas-imm-* form.

    Accepts:
      - Full form (obj-cas-imm-<hash>): validate exists, return as-is.
      - Short hash (<12-hex>): prepend obj-cas-imm- and check; return on match.
      - Even shorter prefix (e.g. 6c6191): walk bare/data/ for files starting
        with obj-cas-imm-<prefix>; return the unique match.

    Raises:
      Vault__Commit_Not_Found_Error    — no match
      Vault__Commit_Ambiguous_Error    — multiple matches; lists candidates
    """
    if not input_id:
        raise ValueError('empty commit id')

    # 1. Already full form — validate and return.
    if input_id.startswith('obj-cas-imm-'):
        if obj_store.exists(input_id):
            return input_id
        raise Vault__Commit_Not_Found_Error(
            f'commit not found: {input_id}'
        )

    # 2. Bare hash (any length) — try full prefix match.
    candidate = f'obj-cas-imm-{input_id}'
    if obj_store.exists(candidate):
        return candidate

    # 3. Shorter prefix — walk and search.
    matches = obj_store.list_objects_with_prefix(f'obj-cas-imm-{input_id}')
    if len(matches) == 1:
        return matches[0]
    if len(matches) == 0:
        raise Vault__Commit_Not_Found_Error(
            f'commit not found: {input_id} '
            f'(did you mean obj-cas-imm-{input_id}?)'
        )
    raise Vault__Commit_Ambiguous_Error(
        f'ambiguous commit id {input_id!r} — {len(matches)} matches:\n  ' +
        '\n  '.join(matches[:10])
    )
```

The helper requires one new method on `Vault__Object_Store`:

```python
def list_objects_with_prefix(self, prefix: str) -> list[str]:
    """Return all object filenames in bare/data/ starting with prefix."""
    if not os.path.isdir(self.data_dir):
        return []
    return sorted(f for f in os.listdir(self.data_dir) if f.startswith(prefix))
```

Two new typed errors in `sgit_ai/core/Vault__Errors.py`:

```python
class Vault__Commit_Not_Found_Error(Exception): pass
class Vault__Commit_Ambiguous_Error(Exception): pass
```

The errors are typed (not bare `RuntimeError`) so the CLI's friendly-error handler can format them distinctly — "commit not found" vs "ambiguous prefix" should produce different output.

### 2b. Apply at every CLI commit-id consumption site

Find every place a CLI argument is treated as a commit ID and route through `resolve_commit_id` BEFORE handing off to the underlying action. Audit list:

| Command | Argument | File / handler |
|---|---|---|
| `history show <id>` | `commit_id` | `CLI__Diff.cmd_show` |
| `history diff --commit / --commit2` | both | `CLI__Diff.cmd_diff` |
| `history diff <from>..<to>` | both sides of the range | `CLI__Diff.cmd_diff` (range path) |
| `history log <from>..<to>` | both sides | `CLI__Diff.cmd_log` (range path) |
| `history reset <id>` | `commit_id` | `CLI__Vault.cmd_reset` |
| `history revert --commit <id>` | `commit_id` | `CLI__Revert.cmd_revert` |

For each: at the top of the handler, after argument extraction but before action invocation, call `resolve_commit_id(arg, obj_store)`. Let the typed errors propagate; the CLI's friendly-error path renders them.

For the action-class layer (`Vault__Diff.commits_in_range`, `Vault__Diff.diff_commits`, `Vault__Diff.show_commit`, etc.) — keep them strict (full IDs only). Resolution lives at the CLI layer; action classes operate on canonical inputs. This keeps the action API clean for programmatic callers (which should already supply full IDs).

### 2c. Improved error message at the FileNotFound boundary

Today's misleading "run sgit pull" hint fires for ALL `FileNotFoundError`s on `bare/data/*`, including the typo case. Update `CLI__Diff` and `CLI__Vault` exception handling:

```python
except Vault__Commit_Not_Found_Error as e:
    print(f'error: {e}', file=sys.stderr)
    sys.exit(1)
except Vault__Commit_Ambiguous_Error as e:
    print(f'error: {e}', file=sys.stderr)
    print(f'  hint: pass a longer prefix to disambiguate.', file=sys.stderr)
    sys.exit(1)
except FileNotFoundError as e:
    if 'bare/data' in str(e):
        # Genuine missing-object case (object exists in commit graph but
        # not local) — keep the existing "run sgit pull" hint.
        print(f'error: {e}', file=sys.stderr)
        print(f'  hint: object not cached locally — run: sgit pull  to fetch '
              f'missing history', file=sys.stderr)
    else:
        print(f'error: {e}', file=sys.stderr)
    sys.exit(1)
```

Order matters: typed errors first, then the file-system fallback.

---

## 3. Tests

In `tests/unit/cli/_helpers/test_resolve_commit_id.py` (new):

1. `test_resolve_full_form_returns_unchanged` — `obj-cas-imm-abc123` → exists → returned as-is.
2. `test_resolve_full_form_not_existing_raises_not_found` — full form that doesn't exist → `Vault__Commit_Not_Found_Error`.
3. `test_resolve_short_hash_finds_object` — `abc123` → resolves to `obj-cas-imm-abc123`.
4. `test_resolve_short_prefix_unique_match` — `abc` (shorter than full hash) with one match → returns the full ID.
5. `test_resolve_short_prefix_ambiguous_raises` — `ab` matching multiple objects → `Vault__Commit_Ambiguous_Error` with candidates listed.
6. `test_resolve_unknown_id_raises_not_found` — `xyz999` matches nothing → `Vault__Commit_Not_Found_Error`.
7. `test_resolve_empty_input_raises_value_error`.
8. `test_resolve_error_message_includes_did_you_mean_hint` — `abc123` (no match in either form) → error message contains `did you mean obj-cas-imm-abc123?`.

In `tests/unit/cli/test_CLI__History__Resolve.py` (new):

9. `test_history_show_with_short_hash_works` — copy hash from `history log -n 1`, pass to `history show`, no error.
10. `test_history_diff_with_short_hashes_works` — same for diff.
11. `test_history_diff_range_with_short_hashes_works` — `<short>..<short>` syntax with the resolver.
12. `test_ambiguous_prefix_produces_actionable_error` — set up two objects with the same first 4 chars, pass the 4-char prefix, assert error message lists both candidates.
13. `test_short_hash_not_found_produces_did_you_mean_hint` — pass a 12-hex hash that doesn't resolve; assert the error mentions `obj-cas-imm-<input>`.

---

## 4. Out of scope

- **Tag / branch-name resolution.** `sgit history show v1.0` won't work after this brief. Sgit doesn't have user-facing tags or branch-name → commit-id resolution today. The error for this case should say so explicitly: `commit not found: v1.0 (sgit does not currently support tag or branch-name resolution; pass a commit hash)`. **Track tags as a future feature** — separate brief.
- **Resolution in the action-class layer.** Resolution happens once at the CLI boundary; the action classes (`Vault__Diff.show_commit`, etc.) operate on canonical full IDs only. This keeps the programmatic API clean.
- **JSON output adjustments.** `--json` paths already emit full `commit_id` values, so agents are unaffected. No changes needed there.

---

## 5. Verification checklist

When done:

- All ~13 new tests pass.
- `sgit history diff "<short-hash>..<short-hash>" --files-only` works using hashes copied from `sgit history log`.
- `sgit history show <short-hash>` works.
- An ambiguous prefix produces a clear error listing the candidates.
- A genuinely-missing-from-local object still produces the "run sgit pull" hint (no regression).
- KNOWN_VIOLATIONS unchanged.

Estimated effort: ~½ day total (helper ~1h, list_objects_with_prefix on Vault__Object_Store ~30min, apply at 6 CLI sites ~1h, friendly-error wiring ~30min, tests ~2h).

---

## 6. Why this is small but meaningful

The CLI surface today is **silently broken** for the most natural human flow: copy a commit hash from `history log`, paste it into `history diff` or `history show`. Every output of `history log` invites a follow-up command that doesn't accept the format you copied. That's a UX paper cut every user hits within their first 5 minutes.

Git's prefix-resolution is a load-bearing piece of git's UX — every git tutorial relies on it. Sgit needs the same. ~½ day of work. Slot wherever fits — fold into brief 16's reviewer-fix pass, or land standalone before brief 12.
