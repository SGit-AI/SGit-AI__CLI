## `batch` in sgit_ai/network/api/Vault__Backend.py (L25-L43)

**Purpose:** Default "best-effort" batch: run each op one by one through `write`/`delete`. Documented as the non-atomic fallback subclasses may override (L26-L29). Only `Vault__Backend__Local` inherits it (`Vault__Backend__API.batch` overrides, L78-L79).

**Inputs & Assumptions:** `operations` (list of dicts) with `op`, `file_id`, `data` (base64).

**Outputs & Effects:** `{'status': 'ok', 'results': [...]}` with one `ok` per write/delete executed.

**Block-by-Block:**
```python
# L36-L42
if op_type in ('write', 'write-if-match'):
    payload = base64.b64decode(op['data'])
    self.write(file_id, payload)
    results.append(dict(file_id=file_id, status='ok'))
elif op_type == 'delete':
    self.delete(file_id)
    ...
```
- **What:** `write-if-match` is executed as a **plain write; `match` is never read** (L36-L39). Any other op (`read`) is silently skipped and produces no result entry.
- **Assumes:** callers do not rely on compare-and-swap through this class. True today only because nothing calls it. `nothing found` enforcing CAS here. Test: `tests/unit/api/test_Vault__Backend__Local.py::test_batch_write_and_delete`.

**Cross-Function Dependencies:** callees `write`, `delete` (subclass). Callers: none in `sgit_ai/`.

**Open Questions:**
- unclear; whether `Vault__Backend*` is dead code scheduled for removal or a planned extension point. No caller exists.
