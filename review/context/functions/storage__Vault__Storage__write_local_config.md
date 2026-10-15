## `write_local_config` in sgit_ai/storage/Vault__Storage.py (L133-L137)

```python
# L136-L137
import json
self.write_private(self.local_config_path(directory), json.dumps(data, indent=2))
```

**Purpose:** Atomic 0600 write of `.sg_vault/local/config.json` (review 0a0707d F10, docstring L134-L135).

**Inputs & Assumptions:** `directory` trusted; `data` must be JSON-serialisable — callers pass a `dict` from `Schema__Local_Config.json()` (`Vault__Sync.py:L118`, `Vault__Attach.py:L87`, `Vault__Branch_Switch.py:L528`, `Vault__Publish.py:L255`, `Vault__Sync__Scope.py:L180`, clone steps) or a raw dict read back from the file and edited (`Vault__Sync__Base.py:L148, L222`). The type hint says `dict` (a raw primitive in a Type_Safe class signature; the class field rule in CLAUDE.md is about fields, not parameters).

**Outputs & Effects:** File write via `write_private`; `config.json` is 0600 though it holds no key (mode, `my_branch_id`, `last_remote_head`, scope).

**Cross-Function Dependencies:** Callee `write_private` L128; `local_config_path` L101. Readers: `Vault__Sync__Base._read_local_config` L273-L277, `Vault__Revert._read_local_config` L191-L196.

**Open Questions:** none.
