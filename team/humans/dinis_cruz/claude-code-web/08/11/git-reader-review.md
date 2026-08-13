# Review: `_to_review/git-reader-implementation/git_reader.zip`

**Date:** 2026-08-11
**Reviewer:** Claude Code (web session)
**Verdict:** Real and close to ship-ready. ~600 lines of implementation that genuinely parse the `.git` object store — loose objects, packfile index v2 (including large offsets), OFS_DELTA/REF_DELTA reconstruction, symbolic refs and `packed-refs` — with zero dependencies beyond `osbot-utils`. Verified against this repository's own 906-commit history. Two findings, one fixed in review, one that must be fixed before ship.

## What was verified (against `/home/user/SGit-AI__CLI`, no git binary)

- `branches()` → `['dev', 'claude/sgit-positioning-proposal-gfxmgx']` ✓
- `head_commit()` → correct SHA (`2e2dd4c`), author, message; `files_changed` correctly
  identified exactly the 1 file added by the HEAD commit ✓
- `commits(depth=5)` → correct first-parent walk with real authors (Claude, GitHub Actions, Dinis Cruz) ✓
- `flatten_tree(HEAD.tree)` → 1,161 files resolved through packfiles and deltas ✓

## Finding 1 — FIXED IN REVIEW: missing `= None` defaults on non-empty Safe_Str fields

`Schema__Git__Tree_Entry.name` and `Schema__Git__File_Change.path` are typed
`Safe_Str__Git__Tree_Path` (which has `allow_empty = False`) with **no `= None` default**.
Under current osbot-utils (tested on 3.70+), Type_Safe eagerly constructs a default
instance for annotated fields during class-kwargs processing, and a non-empty Safe_Str
cannot be default-constructed → `ValueError: value cannot be None when allow_empty is False`
on *any* instantiation, even with all fields provided.

This is exactly the pattern this repo's CLAUDE.md mandates (`vault_id : Safe_Str__Vault_Id = None`).
Fix applied in the reviewed copy (one line each):

```python
class Schema__Git__Tree_Entry(Type_Safe):
    name : Safe_Str__Git__Tree_Path = None    # was: no default → crashed on instantiation

class Schema__Git__File_Change(Type_Safe):
    path : Safe_Str__Git__Tree_Path = None    # same
```

Note: the zip's tests presumably passed on the author's osbot-utils version — pin/re-run
the test suite against the version sgit actually uses before merging.

## Finding 2 — MUST FIX BEFORE SHIP: sanitization regexes destroy data fidelity

The new primitives use default Safe_Str sanitization (replace disallowed chars with `_`),
which is wrong for a *reader* — output must round-trip byte-faithfully:

- Paths come out as `team_humans_dinis_cruz_claude_code_web_08_11_...` —
  `/` and `.` are munged, so `flatten_tree` keys cannot be mapped back to real files.
- Commit messages lose spaces, newlines, and punctuation
  (`docs__sgit_ai_website_positioning__messaging...`).

`Safe_Str__Git__Tree_Path` needs a permissive regex (git allows nearly everything except
NUL and `/` *within components*; full paths need `/` and `.`), and
`Safe_Str__Git__Commit_Message` / `Safe_Str__Git__Author_Line` need free-text handling
(preserve whitespace and punctuation; the 64KB cap is fine). Author name/email fields
have the same issue (`GitHub_Actions` for "GitHub Actions").

## Known limitations (stated in its README, acceptable for v1)

Read-only · first-parent traversal only · no submodules · no shallow clones ·
no working-tree status/diff.

## Why this matters for sgit (recorded for the website/positioning work)

1. **Git repos inside vaults become legible.** A vault can hold a complete repo,
   `.git` included; with this reader, any agent, Lambda, or sandbox that can read the
   cloned files can render history/branches/diffs — no git binary required. Pairs
   naturally with sparse clones (fetch `.git` only, walk history, fetch files on demand).
2. **It validates the sgit bet.** git's object model is small enough to reimplement
   legibly in ~600 typed lines — the same model sgit rebuilt over an encrypted CAS.
   One mental model across the whole stack.
3. The sgit.ai site now documents this as an **engineering preview** (honestly marked
   in-review, with both findings disclosed) at `vault/git-and-vaults.html` (site v0.1.4).

## Recommended next steps

1. Apply the Finding 1 one-liners; re-run the zip's tests on the pinned osbot-utils.
2. Rewrite the three primitives' regexes for byte-faithful round-tripping (Finding 2),
   with round-trip tests against a real repo (this one is a good fixture: 906 commits,
   packfiles, merge commits, long messages).
3. Then promote out of `_to_review/` into a proper package (or into `sgit_ai/` if the
   vault-repo-legibility use case is wanted soon).
