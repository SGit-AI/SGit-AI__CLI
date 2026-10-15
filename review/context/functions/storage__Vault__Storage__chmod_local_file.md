## `chmod_local_file` in sgit_ai/storage/Vault__Storage.py (L139-L144)

```python
# L141-L144
try:    os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
except OSError: pass
```

**Purpose:** Best-effort 0600 on an already-written `.sg_vault/local` file. Pre-dates `Vault__Secret_File`.

**Inputs & Assumptions:** `path` trusted. `os.chmod` follows symlinks (changes the target's mode). Errors swallowed — a failure leaves the previous mode and nothing reports it.

**Cross-Function Dependencies:** One caller: `Step__Clone__Create_Clone_Branch.py:L54` on `pending_path` (not read; by name a pending-state file). `Vault__Sync__Push._save_push_state` L757 does its own `os.chmod` rather than calling this.

**Open Questions:** what `pending_path` holds at `Step__Clone__Create_Clone_Branch.py:L54` — not inspected.
