"""Vault__Checkout_Set — which tracked files a selective working copy holds.

A clone made with `--no-checkout` (or `--sparse`) holds the vault's objects and index
but writes no file; `sgit checkout <path>` and `sgit checkout --since-pull` write the
ones an agent needs. The question every command then asks about a tracked path that
is not on disk is "was it never written, or was it deleted?". The answer is this
record, `.sg_vault/local/checkout.json`: the paths sgit wrote (clone, pull, checkout,
fetch) or committed from disk. A tracked path absent from disk and in the set is a
deletion; absent and not in the set is simply not checked out.

A loose clone with no record keeps the older sparse rule (a file whose blob is not in
the local store was never there). A pack clone cannot use it (its packs bring every
blob: with the record lost every absent file would read as deleted, commit would say
"clean" and push "uncommitted changes", for good: review of 26 Oct, M2), so it
rebuilds the record from the tracked files on disk the first time a command scans the
working copy: "what is on disk is what is checked out". The record names paths in
clear, like the flat and scan caches beside it (TM-R41); it is derivable (the working
copy) and losing it costs nothing but that rebuild.

`last-pull.json` beside it records what the last pull changed, so `sgit checkout
--since-pull` can write exactly the files the researchers added.
"""
import json
import os
from osbot_utils.type_safe.Type_Safe        import Type_Safe
from sgit_ai.storage.Vault__Storage        import Vault__Storage

CHECKOUT_FILE  = 'checkout.json'
LAST_PULL_FILE = 'last-pull.json'
STALE_FILE     = 'stale.json'
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

    def needs_rebuild(self, directory: str) -> bool:
        """A pack clone (its local/packs_absorbed.json exists) whose record is missing or
        cannot be read."""
        if self.exists(directory) and self.load(directory) is not None:
            return False
        return os.path.isfile(os.path.join(Vault__Storage().local_dir(directory), 'packs_absorbed.json'))

    def rebuild(self, directory: str, tracked: dict, on_disk: dict) -> set:
        """The record from the tracked paths present on disk; saved and returned. Said on
        stderr: a tracked file deleted on purpose before the record was lost now reads as
        "not checked out", not as a deletion (second review of 26 Oct, R6)."""
        import sys
        paths = {p for p in tracked if p in on_disk}
        self.save(directory, paths)
        print(f'  warning: .sg_vault/local/{CHECKOUT_FILE} was missing or unreadable; rebuilt from the {len(paths)} '
              f'tracked file(s) on disk. A tracked file you deleted before now reads as not checked out: '
              f'check it out and delete it again to commit the deletion.', file=sys.stderr)
        return paths

    # ------------------------------------------------------------------ stale files
    def stale_path(self, directory: str) -> str:
        return os.path.join(Vault__Storage().local_dir(directory), STALE_FILE)

    def load_stale(self, directory: str) -> dict:
        """{path: content hash of the bytes sgit left on disk} for checked-out files a
        `pull --no-checkout` moved past without writing: those bytes are stale, not an
        edit, and `sgit checkout` may write over them (second review of 26 Oct, R1)."""
        try:
            with open(self.stale_path(directory)) as f:
                data = json.load(f)
            paths = data.get('paths') if isinstance(data, dict) and data.get('version') == CHECKOUT_VERSION else None
            return {str(k): str(v) for k, v in paths.items()} if isinstance(paths, dict) else {}
        except (OSError, ValueError, AttributeError):
            return {}

    def _save_stale(self, directory: str, stale: dict) -> None:
        path = self.stale_path(directory)
        if not stale:
            try:
                os.remove(path)
            except OSError:
                pass
            return
        os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
        tmp = path + '.tmp'
        fd  = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w') as f:
            json.dump(dict(version=CHECKOUT_VERSION, paths=dict(sorted(stale.items()))), f, separators=(',', ':'))
        os.replace(tmp, path)

    def record_stale(self, directory: str, hashes: dict) -> None:
        """Add paths left stale; a path already stale keeps its first hash (the bytes on
        disk have not changed since)."""
        if not hashes:
            return
        stale = self.load_stale(directory)
        for path, h in hashes.items():
            if h and path not in stale:
                stale[path] = str(h)
        self._save_stale(directory, stale)

    def clear_stale(self, directory: str, paths) -> None:
        stale = self.load_stale(directory)
        if stale and any(p in stale for p in paths):
            self._save_stale(directory, {p: h for p, h in stale.items() if p not in set(paths)})

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
