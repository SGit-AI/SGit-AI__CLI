## `store_raw` in sgit_ai/storage/Vault__Object_Store.py (L60-L72)

```python
# L62-L72
path = self.object_path(object_id)
if os.path.isfile(path):
    with open(path, 'rb') as f: existing = f.read()
    if existing != ciphertext: raise Vault__Object_Collision_Error(object_id)
    return object_id
os.makedirs(os.path.dirname(path), exist_ok=True)
with open(path, 'wb') as f: f.write(ciphertext)
return object_id
```

**Purpose:** Insert under a caller-chosen id, with the same no-overwrite rule as `store` but **no check that `object_id` is the hash of `ciphertext`** (docstring L61: "pre-determined object_id (used for change pack drain)").

**Inputs & Assumptions:**
- `object_id` (str): joined into the path unvalidated (L62 → L97). Callers: `Vault__GC.drain` L82 with `blob_id` from a change-pack manifest's `payload` list (a local JSON file under `bare/pending/<pack>/manifest.json`, `Vault__Change_Pack.load_pack_manifest` L89-L96; filtered only by `isinstance(blob_id, str)` L80) — those ids have the shape `obj-<12 hex>` (L44-L48), not `obj-cas-imm-`; `Vault__Sync__Tag._load_tag` L193 with `tag_id` from the branch index (`Schema__Tag_Ref.tag_id : Safe_Str__Object_Id`, strict regex) **after** `object_id_matches(tag_id, blob)` at L191 — so that caller establishes the content address itself.
- `ciphertext` (bytes): GC: local pack bytes; Tag: host bytes, verified at L191.
- Precondition "object_id is a safe leaf name": established by `Safe_Str__Object_Id` for the Tag caller; for the GC caller by the manifest having been written by `Vault__Change_Pack.create` (L44-L48) — `nothing found` that validates `payload` entries on read (no separator check, no prefix check). The pack directory is local (`bare/pending/`), and `Vault__Verified_Write.is_store_path` admits only `bare/pending/<leaf>` from a host, not `bare/pending/<pack>/manifest.json`, so a host cannot supply a manifest through the verified path; `Vault__Sync__Push._upload_bare_to_server` L788-L800 uploads everything under `bare/`, so packs *leave* a clone but the fetch paths read do not bring `bare/pending/<pack>/*` back.

**Outputs & Effects:** As `store`. Collision error on differing bytes (`tests/unit/storage/test_Vault__Object_Store__Collision.py::test_store_raw_raises_on_collision`).

**Cross-Function Dependencies:** Callee `object_path` L96. Callers above. `Vault__GC.drain` wraps the loop in `except Exception: continue` (L71, L86-L87), so a collision error skips the pack silently.

**Open Questions:**
- GC drain: whether a `payload` entry containing `/` or `..` can exist in a local manifest and what `object_path` then yields (a path outside `bare/data`, still under or outside `vault_path`); no guard between `load_pack_manifest` and `store_raw`. Input is local-only as far as the paths read here show.
