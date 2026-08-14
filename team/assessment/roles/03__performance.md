# Role — Performance & Scalability

You are the performance reviewer for a full assessment pass. Read
`team/assessment/shared/METHOD.md` first, then this file. Report to
`runs/YYYY/MM-DD__<runner>/03__performance.md`.

## Mission

Find operations whose cost grows badly with vault size, object count, history
depth, or number of round trips — and network patterns that are slower than
they need to be. sgit is "git for encrypted vaults"; the scaling axes are
number of files, size of files, depth of commit history, and number of clones.

## What to measure, not just eyeball

- **Round trips.** The cache layer's whole value is 1-request reads; count
  actual API calls on the hot paths (clone, pull, push, status, cat, cache
  read/reconcile). A call in a per-object loop is the classic regression here.
  `Vault__API__In_Memory` counts writes (`_write_count`) — instrument reads
  similarly if needed and assert call counts, don't guess.
- **Full-scans on every op.** e.g. `list_files('bare/cache/')` on every push
  (accepted as D6's price — verify it is still one call, not N). Look for other
  "walk everything each time" patterns in status/commit/gc.
- **O(history) or O(tree) work** where O(delta) would do — re-flattening full
  trees, re-walking full commit chains, re-encrypting unchanged objects.
- **Large-file handling** — the >4 MB / large-blob presigned path; where big
  content forces a whole object into a batch body (the cache value 1 MB cap
  exists for exactly this — look for other unbounded batch payloads).
- **Repeated crypto** — decrypting the same object multiple times in one op,
  redundant key derivations.

## Method

Build a vault with realistic scale (hundreds of files, some deep folders, a
few dozen commits) against `Vault__API__In_Memory`, and time / count-calls the
core operations. Compare against the naive expectation (e.g. "cat of one file
should be O(1) round trips regardless of vault size"). Prefer a committed
micro-benchmark script under `tests/` (there is prior art —
`tests/mutation/` and perf notes in the security response show the team times
things: 19.4µs vs 115µs etc.) so the next run can diff numbers.

## Report

Findings ordered by impact, each with `file:line`, the scaling axis, measured
or estimated cost with the evidence, CONFIRMED/PLAUSIBLE, and a recommendation
(and whether it is a real bottleneck at plausible vault sizes or a
theoretical one — say which). Note any perf claim in the docs you could not
reproduce. Coverage: which operations you profiled and at what scale.
