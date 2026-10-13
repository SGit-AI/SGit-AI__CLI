## `read_root_file` in sgit_ai/network/api/Vault__API__Static.py (L218-L225)

**Purpose:** Bytes of a file at the site root (`manifest.json`, `cover.json`, the loader), outside the vault-object layouts. `None` when absent; a dead host raises.

**Inputs & Assumptions:** `rel_path` (str): from callers (`_read_manifest` passes `'manifest.json'`; mirror/loader tooling outside this slice). Local: `os.path.join(self._root(), rel_path)` with **no containment check** (L224) — unlike `_location`'s local branch. Callers in this slice pass a literal; `nothing found` for others. HTTP: segments percent-encoded (L222, L225).

**Outputs & Effects:** via `_fetch`: bytes / `None` / `Vault__Static_Object_Error` / `Vault__Static_Transport_Error`. Follows redirects (urlopen).

**Cross-Function Dependencies:** callers `_read_manifest` L230; `Vault__Mirror`/loader tooling (grep outside slice not performed). Callee `_fetch`.

**Open Questions:**
- unclear; need to inspect the mirror/loader callers of `read_root_file` to know whether `rel_path` is ever host- or manifest-derived (the local branch has no traversal guard).
