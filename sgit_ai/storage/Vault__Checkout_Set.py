"""Vault__Checkout_Set — which tracked files a selective working copy holds.

A clone made with `--no-checkout` (or `--sparse`) holds the vault's objects and index
but writes no file; `sgit checkout <path>` and `sgit checkout --since-pull` write the
ones an agent needs. The question every command then asks about a tracked path that
is not on disk is "was it never written, or was it deleted?". The answer is this
record, `.sg_vault/local/checkout.json`: the paths sgit wrote (clone, pull, checkout,
fetch) or committed from disk. A tracked path absent from disk and in the set is a
deletion; absent and not in the set is simply not checked out.

A clone with no record keeps the older sparse rule (a file whose blob is not in the
local store was never there), which pack vaults cannot use: their packs bring every
blob. The record names paths in clear, like the flat and scan caches beside it
(TM-R41); it is derivable (the working copy) and losing it costs nothing but the
rule falling back to "everything on disk is what is checked out" on the next write.

`last-pull.json` beside it records what the last pull changed, so `sgit checkout
--since-pull` can write exactly the files the researchers added.
"""
import json
import os
from osbot_utils.type_safe.Type_Safe        import Type_Safe
from sgit_ai.storage.Vault__Storage        import Vault__Storage

CHECKOUT_FILE  = 'checkout.json'
LAST_PULL_FILE = 'last-pull.json'
CHECKOUT_VERSION = 1


class Vault__Checkout_Set(Type_Safe):

    def path(self, directory: str) -> str:
        return os.path.join(Vault__Storage().local_dir(directory), CHECKOUT_FILE)

    def exists(self, directory: str) -> bool:
        return os.path.isfile(self.path(directory))

    def load(self, directory: str):
        """The set of checked-out paths, or None when this clone keeps no record (a full
        clone, or a sparse clone from before the record existed)."""
        try:
            with open(self.path(directory)) as f:
                data = json.load(f)
            if not isinstance(data, dict) or data.get('version') != CHECKOUT_VERSION:
                return None
            paths = data.get('paths')
            return {str(p) for p in paths} if isinstance(paths, list) else None
        except (OSError, ValueError):
            return None

    def save(self, directory: str, paths) -> None:
        path = self.path(directory)
        os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
        tmp = path + '.tmp'
        fd  = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w') as f:
            json.dump(dict(version=CHECKOUT_VERSION, paths=sorted(set(paths))), f, separators=(',', ':'))
        os.replace(tmp, path)

    def init_empty(self, directory: str) -> None:
        self.save(directory, set())

    def remove(self, directory: str) -> None:
        try:
            os.remove(self.path(directory))
        except OSError:
            pass

    def add(self, directory: str, paths) -> None:
        current = self.load(directory)
        if current is None:
            return                                                  # no record: nothing to keep
        self.save(directory, current | set(paths))

    def discard(self, directory: str, paths) -> None:
        current = self.load(directory)
        if current is None:
            return
        self.save(directory, current - set(paths))

    def materialised(self, path: str, entry: dict, obj_store, sparse: bool, paths=None) -> bool:
        """Whether a tracked path counts as checked out: always on a full clone; by the
        record when there is one; else by the older rule (its blob is local)."""
        if not sparse:
            return True
        if paths is not None:
            return path in paths
        return obj_store is not None and obj_store.exists(str((entry or {}).get('blob_id') or ''))

    # ------------------------------------------------------------------ the last pull
    def last_pull_path(self, directory: str) -> str:
        return os.path.join(Vault__Storage().local_dir(directory), LAST_PULL_FILE)

    def record_pull(self, directory: str, head: str, added, modified, deleted, written) -> None:
        try:
            path = self.last_pull_path(directory)
            os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
            tmp = path + '.tmp'
            fd  = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, 'w') as f:
                json.dump(dict(version=CHECKOUT_VERSION, head=str(head or ''), added=sorted(added), modified=sorted(modified),
                               deleted=sorted(deleted), written=sorted(written)), f, separators=(',', ':'))
            os.replace(tmp, path)
        except OSError:
            pass                                                    # a note for `checkout --since-pull`: never a failure

    def last_pull(self, directory: str):
        try:
            with open(self.last_pull_path(directory)) as f:
                data = json.load(f)
            return data if isinstance(data, dict) and data.get('version') == CHECKOUT_VERSION else None
        except (OSError, ValueError):
            return None
