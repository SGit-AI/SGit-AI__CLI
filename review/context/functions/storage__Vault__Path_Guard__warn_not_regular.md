## `warn_not_regular` in sgit_ai/storage/Vault__Path_Guard.py (L229-L235)

```python
# L230-L235
if rel_path in Vault__Path_Guard.WARNED: return
Vault__Path_Guard.WARNED.add(rel_path)
print(f'  warning: skipped {rel_path}: not a regular file ...', file=sys.stderr)
```

**Purpose:** One stderr warning per non-regular path per process.

**Inputs & Assumptions:** `rel_path` str (a filesystem-derived name, printed verbatim to stderr). Implicit: the class-level set `WARNED` (L72), process-global and never cleared.

**Outputs & Effects:** Mutates `Vault__Path_Guard.WARNED`; writes to stderr. The set grows without bound across a long-lived process (the `sgit serve` daemon, tests) — bounded by distinct paths seen.

**Cross-Function Dependencies:** Caller `read_regular` L202, L213, L218. Shared state `WARNED` with nothing else.

**Open Questions:** none.
