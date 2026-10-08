"""Vault__Reflog — a per-clone, append-only record of every local ref move.

git's reflog answers "where did this branch point three operations ago?" after
a reset, a rewind or a bad merge. sgit kept no such record: once the clone's
head moved, the previous id was only recoverable from another clone. Every
Vault__Ref_Manager.write_ref now appends old -> new here, and
`sgit history reflog` lists it; the commits themselves stay in the local
object store, so `sgit history reset <old id>` brings the head back.

Local only (never pushed), plain JSON lines under .sg_vault/local/ beside the
config, capped at MAX_ENTRIES (the oldest are dropped). Commit ids are opaque
content addresses; nothing here is secret beyond what the store already holds.
"""
import json
import os
import time
from   osbot_utils.type_safe.Type_Safe                 import Type_Safe
from   sgit_ai.schemas.Schema__Reflog_Entry            import Schema__Reflog_Entry
from   sgit_ai.safe_types.Safe_Str__Vault_Path         import Safe_Str__Vault_Path

REFLOG_FILE = 'reflog.jsonl'
MAX_ENTRIES = 1000


class Vault__Reflog(Type_Safe):
    vault_path : Safe_Str__Vault_Path = None                    # the .sg_vault directory

    def path(self) -> str:
        return os.path.join(str(self.vault_path), 'local', REFLOG_FILE)

    def append(self, ref_id: str, old_commit: str, new_commit: str) -> None:
        """Record a move. Never raises: a reflog failure must not fail the operation."""
        if not self.vault_path or (old_commit or '') == (new_commit or ''):
            return
        try:
            entry = Schema__Reflog_Entry(timestamp_ms = int(time.time() * 1000),
                                         ref_id       = ref_id,
                                         old_commit   = old_commit or None,
                                         new_commit   = new_commit or None)
            path  = self.path()
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'a') as f:
                f.write(json.dumps(entry.json()) + '\n')
            self._trim(path)
        except Exception:
            pass

    def entries(self, ref_id: str = None) -> list:
        """Newest first. ref_id filters to one ref."""
        out = []
        try:
            with open(self.path()) as f:
                for line in f:
                    try:
                        e = Schema__Reflog_Entry.from_json(json.loads(line))
                    except Exception:
                        continue                                # a damaged line is skipped, not fatal
                    if ref_id is None or str(e.ref_id) == str(ref_id):
                        out.append(e)
        except FileNotFoundError:
            return []
        return list(reversed(out))

    def _trim(self, path: str) -> None:
        with open(path) as f:
            lines = f.readlines()
        if len(lines) > MAX_ENTRIES + MAX_ENTRIES // 10:            # trim in batches, not on every write
            with open(path, 'w') as f:
                f.writelines(lines[-MAX_ENTRIES:])
