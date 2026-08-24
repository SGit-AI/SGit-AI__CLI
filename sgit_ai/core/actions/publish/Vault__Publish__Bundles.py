"""Vault__Publish__Bundles — bundles/ for a published vault (P6).

Two artefacts, both ZIP_STORED — ciphertext is incompressible and DEFLATE
measured LARGER (1.078× vs 1.075×) at ~10× the CPU:

  bundles/head-<commit>.zip   snapshot: every object reachable from the head
  bundles/<commit>.zip        per-commit delta: the objects that commit
                              introduced (the commit itself, plus trees and
                              blobs not present in any parent)

Names are immutable, keyed by commit id — never latest.zip. Bundles are
DERIVED, never authoritative: a missing or corrupt bundle degrades to loose
object fetches, never to a wrong result, and every object extracted from one
is id-verified before it is written (extract_verified). The union of
per-commit deltas reconstructs bare/data/ exactly (walked via parents).

Zips are deterministic: fixed timestamps, sorted members — publishing twice
produces identical bytes.
"""
import os
import zipfile

from sgit_ai.core.Vault__Sync__Base          import Vault__Sync__Base
from sgit_ai.crypto.PKI__Crypto              import PKI__Crypto
from sgit_ai.storage.Vault__Commit           import Vault__Commit
from sgit_ai.storage.Vault__Object_Store     import Vault__Object_Store
from sgit_ai.storage.Vault__Ref_Manager      import Vault__Ref_Manager
from sgit_ai.storage.Vault__Verified_Write   import Vault__Verified_Write

ZIP_EPOCH = (1980, 1, 1, 0, 0, 0)      # fixed member timestamp — determinism


class Vault__Publish__Bundles(Vault__Sync__Base):

    def build(self, sg_dir: str, out_dir: str, commits: list, read_key: bytes) -> dict:
        """Write bundles/ under out_dir. commits is the manifest's ordered
        list, head first, walked via parents (Vault__Publish supplies it)."""
        obj_store    = Vault__Object_Store(vault_path=sg_dir, crypto=self.crypto)
        vault_commit = Vault__Commit(crypto=self.crypto, pki=PKI__Crypto(),
                                     object_store=obj_store,
                                     ref_manager=Vault__Ref_Manager(vault_path=sg_dir, crypto=self.crypto))
        bundles_dir = os.path.join(out_dir, 'bundles')
        os.makedirs(bundles_dir, exist_ok=True)

        objects_of = {cid: self._objects_of_commit(vault_commit, cid, read_key)
                      for cid in commits}
        parents_of = {cid: self._parents_of(vault_commit, cid, read_key) for cid in commits}

        written = []
        if commits:
            head     = commits[0]
            snapshot = set()
            for object_ids in objects_of.values():
                snapshot |= object_ids
            written.append(self._write_zip(obj_store, bundles_dir,
                                           f'head-{head}.zip', sorted(snapshot)))
        for cid in commits:
            inherited = set()
            for parent in parents_of[cid]:
                inherited |= objects_of.get(parent, set())
            delta = objects_of[cid] - inherited
            written.append(self._write_zip(obj_store, bundles_dir, f'{cid}.zip', sorted(delta)))
        return dict(bundles=written)

    def extract_verified(self, zip_path: str, dest_sg_dir: str, read_key: bytes = None) -> dict:
        """Unpack a bundle into a bare store, id-verifying EVERY member before
        it is written (a corrupt bundle degrades, it never poisons the store).
        Returns {extracted: n, refused: [...]}"""
        writer    = Vault__Verified_Write(crypto=self.crypto)
        extracted = 0
        refused   = []
        with zipfile.ZipFile(zip_path) as bundle:
            for member in sorted(bundle.namelist()):
                data = bundle.read(member)
                if writer.save(dest_sg_dir, member, data, read_key=read_key) != writer.REFUSED:
                    extracted += 1
                else:
                    refused.append(member)
        return dict(extracted=extracted, refused=refused)

    # --- internals ----------------------------------------------------------

    def _parents_of(self, vault_commit, commit_id: str, read_key: bytes) -> list:
        try:
            commit = vault_commit.load_commit(commit_id, read_key)
            return [str(p) for p in (commit.parents or []) if str(p)]
        except Exception:
            return []

    def _objects_of_commit(self, vault_commit, commit_id: str, read_key: bytes) -> set:
        """The commit object plus every tree and blob its root tree reaches."""
        objects = {commit_id}
        try:
            commit = vault_commit.load_commit(commit_id, read_key)
        except Exception:
            return objects
        queue = [str(commit.tree_id)] if commit.tree_id else []
        while queue:
            tree_id = queue.pop()
            if not tree_id or tree_id in objects:
                continue
            objects.add(tree_id)
            try:
                tree = vault_commit.load_tree(tree_id, read_key)
            except Exception:
                continue                                  # fail-soft per object
            for entry in (tree.entries or []):
                if entry.blob_id:
                    objects.add(str(entry.blob_id))
                elif entry.tree_id:
                    queue.append(str(entry.tree_id))
        return objects

    def _write_zip(self, obj_store, bundles_dir: str, name: str, object_ids: list) -> str:
        zip_path = os.path.join(bundles_dir, name)
        with zipfile.ZipFile(zip_path, 'w', compression=zipfile.ZIP_STORED) as bundle:
            for object_id in object_ids:
                if not obj_store.exists(object_id):
                    continue                              # sparse store: bundle what exists
                info = zipfile.ZipInfo(f'bare/data/{object_id}', date_time=ZIP_EPOCH)
                info.compress_type = zipfile.ZIP_STORED
                bundle.writestr(info, obj_store.load(object_id))
        return name
