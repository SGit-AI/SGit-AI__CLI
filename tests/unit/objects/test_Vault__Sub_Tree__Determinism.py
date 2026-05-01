# Tree-id determinism tests for Vault__Sub_Tree.
import os
import tempfile

from sgit_ai.crypto.Vault__Crypto       import Vault__Crypto
from sgit_ai.objects.Vault__Object_Store import Vault__Object_Store
from sgit_ai.sync.Vault__Sub_Tree        import Vault__Sub_Tree


class Test_Vault__Sub_Tree__Determinism:

    def setup_method(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.sg_dir  = os.path.join(self.tmp_dir, '.sg_vault')
        os.makedirs(os.path.join(self.sg_dir, 'bare', 'data'), exist_ok=True)

        self.crypto    = Vault__Crypto()
        self.obj_store = Vault__Object_Store(vault_path=self.sg_dir, crypto=self.crypto)
        self.sub_tree  = Vault__Sub_Tree(crypto=self.crypto, obj_store=self.obj_store)

        # Two fixed, distinct read keys (not random — tests must be reproducible)
        self.read_key_1 = bytes.fromhex(
            '0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef'
        )
        self.read_key_2 = bytes.fromhex(
            'fedcba9876543210fedcba9876543210fedcba9876543210fedcba9876543210'
        )

    def _blob_id(self, content: bytes, read_key: bytes) -> str:
        encrypted = self.crypto.encrypt(read_key, content)
        return self.obj_store.store(encrypted)

    def _flat_map(self, files: dict, read_key: bytes) -> dict:
        """Build a flat {path: entry_dict} map, storing blobs under read_key."""
        flat = {}
        for path, content in files.items():
            blob_id = self._blob_id(content, read_key)
            flat[path] = {
                'blob_id':      blob_id,
                'size':         len(content),
                'content_hash': self.crypto.content_hash(content),
                'content_type': 'text/plain',
            }
        return flat

    # ------------------------------------------------------------------
    # Tree-id determinism (same map + same key → same id)
    # ------------------------------------------------------------------

    def test_tree_id_determinism__single_file(self):
        """build_from_flat with one file produces the same tree id on two calls."""
        files = {'hello.txt': b'hello world'}
        flat  = self._flat_map(files, self.read_key_1)
        id1   = self.sub_tree.build_from_flat(flat, self.read_key_1)
        id2   = self.sub_tree.build_from_flat(flat, self.read_key_1)
        assert id1 == id2

    def test_tree_id_determinism__multiple_files(self):
        """build_from_flat with multiple files is deterministic."""
        files = {
            'readme.md':       b'# Vault',
            'src/main.py':     b'print("hello")',
            'src/utils.py':    b'pass',
            'data/config.json': b'{"key": "value"}',
        }
        flat = self._flat_map(files, self.read_key_1)
        id1  = self.sub_tree.build_from_flat(flat, self.read_key_1)
        id2  = self.sub_tree.build_from_flat(flat, self.read_key_1)
        assert id1 == id2

    def test_tree_id_determinism__three_calls(self):
        """Three consecutive calls with identical input all return the same id."""
        files = {'a.txt': b'alpha', 'b.txt': b'beta'}
        flat  = self._flat_map(files, self.read_key_1)
        id1   = self.sub_tree.build_from_flat(flat, self.read_key_1)
        id2   = self.sub_tree.build_from_flat(flat, self.read_key_1)
        id3   = self.sub_tree.build_from_flat(flat, self.read_key_1)
        assert id1 == id2 == id3

    # ------------------------------------------------------------------
    # Cross-vault tree divergence (same map + different key → different id)
    # ------------------------------------------------------------------

    def test_cross_vault_tree_divergence__single_file(self):
        """Same file map with different read_keys must produce different tree ids.

        This is the headline AppSec property: two vaults holding identical
        plaintext must not share tree-object IDs, which would leak structural
        information across vault boundaries.
        """
        files  = {'secret.txt': b'my secret content'}
        flat1  = self._flat_map(files, self.read_key_1)
        flat2  = self._flat_map(files, self.read_key_2)
        tree1  = self.sub_tree.build_from_flat(flat1, self.read_key_1)
        tree2  = self.sub_tree.build_from_flat(flat2, self.read_key_2)
        assert tree1 != tree2

    def test_cross_vault_tree_divergence__multiple_files(self):
        """Multi-file vaults with the same content but different keys diverge."""
        files = {
            'readme.md':   b'# Shared Docs',
            'notes.txt':   b'shared notes',
        }
        flat1 = self._flat_map(files, self.read_key_1)
        flat2 = self._flat_map(files, self.read_key_2)
        id1   = self.sub_tree.build_from_flat(flat1, self.read_key_1)
        id2   = self.sub_tree.build_from_flat(flat2, self.read_key_2)
        assert id1 != id2

    # ------------------------------------------------------------------
    # Sanity: different file content → different tree id (same key)
    # ------------------------------------------------------------------

    def test_different_file_content_different_tree_id(self):
        """Changed file content under the same key must produce a different tree id."""
        flat_v1 = self._flat_map({'doc.txt': b'version 1'}, self.read_key_1)
        flat_v2 = self._flat_map({'doc.txt': b'version 2'}, self.read_key_1)
        id1     = self.sub_tree.build_from_flat(flat_v1, self.read_key_1)
        id2     = self.sub_tree.build_from_flat(flat_v2, self.read_key_1)
        assert id1 != id2

    # ------------------------------------------------------------------
    # Round-trip: flatten recovers original paths after deterministic build
    # ------------------------------------------------------------------

    def test_round_trip_flatten_recovers_paths(self):
        """flatten(build_from_flat(map, key), key) recovers the original file paths."""
        files   = {'alpha.txt': b'alpha content', 'beta/gamma.txt': b'gamma content'}
        flat    = self._flat_map(files, self.read_key_1)
        tree_id = self.sub_tree.build_from_flat(flat, self.read_key_1)
        result  = self.sub_tree.flatten(tree_id, self.read_key_1)
        assert set(result.keys()) == set(files.keys())
