# Reviewer Fixes — B01 Delivery (v0.12.x)

**Date:** 2026-05-04
**For:** Sonnet executor (claude/sonnet-onboarding-oMP6A)
**From:** Explorer reviewer (claude/cli-explorer-session-J3WqA)
**Brief:** B01 — Instrumentation tools (`sgit dev <…>`)

This debrief documents the two fixes applied during review of the B01 delivery,
with enough context that the patterns don't recur.

---

## Fix 1 — Multi-paragraph method docstring (`Dev__Step__Clone.step_clone`)

**File:** `sgit_ai/cli/dev/Dev__Step__Clone.py`
**Rule:** CLAUDE.md — "No multi-paragraph class or method docstrings — one line max.
Module-level docstrings are fine and encouraged."

**Original:**
```python
def step_clone(self, vault_key: str, directory: str,
               no_pause: bool = True,
               on_pause: callable = None) -> Schema__Step__Clone:
    """Clone with per-step pauses.

    on_pause(step_event) is called instead of input() when no_pause=False.
    If on_pause is None and no_pause=False the default is sys.stdin.readline().
    """
```

**Fixed:**
```python
    """Clone with per-step pauses; on_pause(event) replaces input() when no_pause=False."""
```

**Why this keeps happening:** The rule applies specifically to class and method
definitions. Module-level docstrings (top of file, before any class) are fine —
the tools in B01 all have good module-level docstrings. The confusion is usually
between "documenting the module" (encouraged) and "documenting a method"
(one line only). If the detail is important, put it in the module docstring or
in a comment inside the method body.

---

## Fix 2 — Wrong Safe_* type for tree IDs (`Schema__Server__Objects.hot_tree_ids`)

**File:** `sgit_ai/cli/dev/Schema__Server__Objects.py`
**Rule:** CLAUDE.md — "Zero raw primitives in Type_Safe classes."

This fix went through two steps because the first correction was itself wrong.

### Step 1 — Raw `list` (original violation)

```python
hot_tree_ids  : list        # top-N tree IDs referenced from multiple commits (str list)
```

`list` with no type parameter is a raw collection — Type_Safe has no way to
validate its elements. This violates the "no raw primitives" rule. The reviewer
initially changed this to `list[Safe_Str]`.

### Step 2 — `list[Safe_Str]` is actively harmful

`Safe_Str` is the base safe string type. Its default behaviour is to **replace
any character that isn't alphanumeric or `_` with `_`**. Tree IDs have the
format `obj-cas-imm-[0-9a-f]{12}` — they contain hyphens. Storing a real tree
ID in a `Safe_Str` field silently corrupts it:

```python
>>> Safe_Str('obj-cas-imm-aabb11223344')
'obj_cas_imm_aabb11223344'   # hyphens → underscores — corrupted!
```

This means `list[Safe_Str]` would silently corrupt every tree ID stored, and the
round-trip invariant `from_json(obj.json()).json() == obj.json()` would pass on
the corrupted form — hiding the bug.

### Correct fix — `list[Safe_Str__Object_Id]`

```python
from sgit_ai.safe_types.Safe_Str__Object_Id import Safe_Str__Object_Id
...
hot_tree_ids  : list[Safe_Str__Object_Id]   # top-N tree IDs referenced from multiple commits
```

`Safe_Str__Object_Id` uses `MATCH` mode regex `^obj-cas-imm-[0-9a-f]{12}$`,
validates the exact format, and preserves hyphens. A value that doesn't match
raises `TypeError` at construction time rather than silently mutating.

The test that was using `hot_tree_ids=['abc']` was also fixed to use a real
object ID: `hot_tree_ids=['obj-cas-imm-aabb11223344']`.

### The general pattern to follow

When a field holds vault object IDs (commit IDs, tree IDs, blob IDs — they are
all stored as `obj-cas-imm-<12hexchars>`), the correct type is always
`Safe_Str__Object_Id`. Check `sgit_ai/safe_types/` before reaching for
`Safe_Str`:

| What you're storing | Correct type |
|---|---|
| Any vault object ID (commit / tree / blob) | `Safe_Str__Object_Id` |
| Vault ID (8-char alphanumeric suffix) | `Safe_Str__Vault_Id` |
| Branch ID | `Safe_Str__Branch_Id` |
| File path in a vault | `Safe_Str__Vault_Path` |
| Arbitrary short label / name | `Safe_Str` (after confirming no hyphens needed) |
| Arbitrary text that may contain hyphens / dots / etc. | define a domain-specific `Safe_Str__*` subclass with the right regex |

---

## Takeaway

Both violations are easy to avoid:

1. **Docstrings in methods:** one sentence, full stop. If you need more, it goes
   in a comment inside the body or in the module-level docstring.

2. **Type_Safe fields:** before writing `list` or `list[Safe_Str]`, check
   `sgit_ai/safe_types/` for a domain-specific type that matches the actual
   format. If one exists, use it. If not, create one before writing the schema.
   Never reach for `Safe_Str` for values that contain hyphens — its default
   sanitiser will corrupt them.
