"""Vault__Adversary — the attacker the threat model names, as a test fixture.

It holds what a READ-key holder holds (the read key, and with it every object of
the vault) and writes straight into the host's store (Vault__API__In_Memory's
_store), which is what a hostile host, a compromised host, or anyone colluding
with the host can do. It never touches the write key or any clone's signing key.

Used by tests/security to prove both kinds of claim:
  * a fixed attack now fails (the victim refuses, writes nothing), and
  * a known, accepted gap still exists (the attack works) — so the threat model's
    "accepted" and "by design" rows are evidence, not prose. When such a test
    starts failing, the gap closed: update the threat model row it names.
"""
import mimetypes
import os
import shutil
import tempfile

from sgit_ai.crypto.PKI__Crypto              import PKI__Crypto
from sgit_ai.crypto.Vault__Crypto            import Vault__Crypto
from sgit_ai.crypto.Vault__Key_Manager       import Vault__Key_Manager
from sgit_ai.storage.Vault__Branch_Manager   import Vault__Branch_Manager
from sgit_ai.storage.Vault__Commit           import Vault__Commit
from sgit_ai.storage.Vault__Object_Store     import Vault__Object_Store
from sgit_ai.storage.Vault__Ref_Manager      import Vault__Ref_Manager
from sgit_ai.storage.Vault__Storage          import Vault__Storage
from sgit_ai.storage.Vault__Sub_Tree         import Vault__Sub_Tree


class Vault__Adversary:

    def __init__(self, api, vault_key: str):
        self.api      = api
        self.crypto   = Vault__Crypto()
        self.pki      = PKI__Crypto()
        keys          = self.crypto.derive_keys_from_vault_key(vault_key)
        self.vault_id = keys['vault_id']
        self.read_key = keys['read_key_bytes']                 # all it holds: no write key, no signing key
        self.index_id = keys['branch_index_file_id']
        self.tmp      = tempfile.mkdtemp(prefix='adversary_')
        self.sg_dir   = os.path.join(self.tmp, '.sg_vault')
        Vault__Storage().create_bare_structure(self.sg_dir)
        self.obj_store   = Vault__Object_Store(vault_path=self.sg_dir, crypto=self.crypto)
        self.ref_manager = Vault__Ref_Manager (vault_path=self.sg_dir, crypto=self.crypto)
        self.key_manager = Vault__Key_Manager (vault_path=self.sg_dir, crypto=self.crypto, pki=self.pki)
        self.branches    = Vault__Branch_Manager(vault_path=self.sg_dir, crypto=self.crypto,
                                                 key_manager=self.key_manager, ref_manager=self.ref_manager,
                                                 storage=Vault__Storage())
        self.sub_tree    = Vault__Sub_Tree(crypto=self.crypto, obj_store=self.obj_store)
        self.commits     = Vault__Commit(crypto=self.crypto, pki=self.pki,
                                         object_store=self.obj_store, ref_manager=self.ref_manager)
        self.pull_host()

    def cleanup(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ── the host's store ────────────────────────────────────────────────
    def host_key(self, file_id: str) -> str:
        return f'{self.vault_id}/{file_id}'

    def host_read(self, file_id: str) -> bytes:
        return self.api._store.get(self.host_key(file_id))

    def host_write(self, file_id: str, data: bytes) -> None:
        self.api._store[self.host_key(file_id)] = data

    def pull_host(self) -> None:
        """Copy every file of the vault on the host into the adversary's store."""
        prefix = f'{self.vault_id}/'
        for key, data in list(self.api._store.items()):
            if key.startswith(prefix):
                path = os.path.join(self.sg_dir, key[len(prefix):])
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, 'wb') as f:
                    f.write(data)

    def push_host(self) -> int:
        """Write every local store file the host lacks (or holds differently) to the host."""
        n = 0
        for root, _dirs, files in os.walk(os.path.join(self.sg_dir, 'bare')):
            for name in files:
                full    = os.path.join(root, name)
                file_id = os.path.relpath(full, self.sg_dir).replace(os.sep, '/')
                with open(full, 'rb') as f:
                    data = f.read()
                if self.host_read(file_id) != data:
                    self.host_write(file_id, data)
                    n += 1
        return n

    # ── reading the vault ───────────────────────────────────────────────
    def index(self):
        return self.branches.load_branch_index(self.tmp, self.index_id, self.read_key)

    def named_branch(self, name: str = 'current'):
        return self.branches.get_branch_by_name(self.index(), name)

    def head_of(self, meta) -> str:
        return self.ref_manager.read_ref(str(meta.head_ref_id), self.read_key)

    # ── forging ─────────────────────────────────────────────────────────
    def blob(self, content: bytes) -> str:
        return self.obj_store.store(self.crypto.encrypt(self.read_key, content))

    def tree(self, files: dict) -> str:
        flat = {path: dict(blob_id      = self.blob(content),
                           size         = len(content),
                           content_hash = self.crypto.content_hash(content),
                           content_type = mimetypes.guess_type(path)[0] or 'application/octet-stream',
                           large        = False)
                for path, content in files.items()}
        return self.sub_tree.build_from_flat(flat, self.read_key)

    def forge_commit(self, files: dict, parent: str, branch_id: str = '', message: str = 'routine update',
                     sign: bool = True, timestamp_ms: int = None) -> str:
        """A commit with any content the adversary likes. With sign=True it is signed
        by a key pair the adversary just made and registered in bare/keys/ under the
        read key — the only thing a verifier checks about a key is that it decrypts."""
        signing_key, key_id = None, None
        if sign:
            signing_key, public_key = self.key_manager.generate_branch_key_pair()
            key_id = 'key-rnd-imm-' + self.key_manager.generate_key_id()
            self.key_manager.store_public_key(key_id, public_key, self.read_key)
        return self.commits.create_commit(self.read_key, self.tree(files), parent_ids=[parent] if parent else [],
                                          message=message, branch_id=branch_id, signing_key=signing_key,
                                          timestamp_ms=timestamp_ms, author_key_id=key_id)

    def move_branch(self, meta, commit_id: str) -> None:
        """Point a branch's head ref at commit_id, on the host."""
        self.ref_manager.write_ref(str(meta.head_ref_id), commit_id, self.read_key)
        self.push_host()

    def plant_objects(self, sg_dir: str) -> None:
        """Copy the adversary's objects and keys into a victim clone's store, as a
        fetch from the hostile host would (they are content-addressed, so they pass)."""
        for sub in ('data', 'keys'):
            src = os.path.join(self.sg_dir, 'bare', sub)
            dst = os.path.join(sg_dir, 'bare', sub)
            os.makedirs(dst, exist_ok=True)
            for name in os.listdir(src):
                if not os.path.exists(os.path.join(dst, name)):
                    shutil.copy2(os.path.join(src, name), os.path.join(dst, name))
