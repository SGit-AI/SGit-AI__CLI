## `_location` in sgit_ai/network/api/Vault__API__Static.py (L70-L84)

**Purpose:** Where one object lives for a layout: an absolute local path (contained in the served folder) or a percent-encoded URL under `base_url`.

**Inputs & Assumptions:**
- `layout`, `vault_id`, `file_id` (str). `file_id` may come from a **manifest** the host published (`list_files` L215 → callers → `read`/`batch_read`), so it is treated as host-supplied (comment L75-L79, "A4").

**Outputs & Effects:** path/URL string, or `None` when a local path would escape the root.

**Block-by-Block:**
```python
# L72-L82 (local)
root = os.path.abspath(self._root())
full = os.path.abspath(os.path.join(root, rel))
if full != root and not full.startswith(root + os.sep):
    return None
return full
```
- **What:** the minimal inline equivalent of `Vault__Path_Guard` (layer rule keeps the storage guard out of `network`, L77-L79).
- **Assumes:** `abspath` normalises `..`; symlinks inside the served folder are not resolved (`abspath` does not `realpath`), so a link under root pointing outside is still "inside" by this test. `nothing found` on symlink resolution here. Test: `test_local_read_refuses_traversal_file_id`.
- **Establishes:** `full` is `root` or under `root + os.sep` (string-prefix containment).

```python
# L83-L84 (http)
safe = '/'.join(quote(part, safe='') for part in rel.split('/'))
return f'{self._root()}/{safe}'
```
- **What:** each path segment percent-encoded; `/` kept as separator. A `..` segment is sent to the host as-is (`quote('..')` is `..`), which the http server resolves — the client writes nothing to disk by this path (downloads go through `Vault__Verified_Write.is_store_path`, which refuses non-store ids).

**Cross-Function Dependencies:** callers `read` L99, `batch_read` L163, `presigned_read_url` L191. Callee `_fetch` treats `None` as absent (L117-L118).

**Open Questions:** none.
