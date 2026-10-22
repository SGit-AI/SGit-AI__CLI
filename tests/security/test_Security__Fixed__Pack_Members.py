"""Pack vaults (0.24.0): what a host that serves packs can and cannot do.

Threat model: TM-F37. A pack is a zip of objects the host stores and serves whole, so a
hostile or broken host (A1) can hand a clone a pack with a member whose bytes do not hash
to its id, a member named outside bare/data/ (a ref, a key, a path that climbs out of the
store), or a pack whose bytes are not the length its name declares. Each member is verified
against its content address before it is written, exactly as a loose object is (TM-F01,
SP-1), and a member that is not a store object is refused by name; the pack's declared
length is checked before the zip is opened. The tests below perform each attack on a
real pack vault over a lying in-memory host and prove the clone's store never holds an
unverified byte."""
import io
import os
import zipfile

import pytest

from sgit_ai.core.actions.pack.Vault__Packs      import Vault__Packs, PACK_SNAPSHOTS, PACK_COMMITS
from sgit_ai.crypto.Vault__Crypto                import Vault__Crypto
from tests._helpers.pack_env                     import Pack__Env
from tests._helpers.vault_test_env               import TEST_VAULT_KEY


def _store_is_content_addressed(store: dict) -> bool:
    crypto = Vault__Crypto()
    return all(crypto.compute_object_id(data, len(oid) - len('obj-cas-imm-')) == oid for oid, data in store.items())


def _rezip(data: bytes, mutate) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data)) as src, zipfile.ZipFile(buf, 'w') as dst:
        for member in src.namelist():
            name, body = mutate(member, src.read(member))
            if name:
                dst.writestr(name, body)
    return buf.getvalue()


def _pad(data: bytes, size: int) -> bytes:
    """Keep the declared length (the name carries it) so only the content check can catch it."""
    return data[:size] if len(data) >= size else data + b'\0' * (size - len(data))


class Test_Fixed__TM_F37__Pack_Members_Are_Verified:

    def setup_method(self):
        self.env = Pack__Env()
        self.sync, self.a, self.key = self.env.pack_vault(self.env.text_files(3), vault_key=TEST_VAULT_KEY)
        self.vid  = self.sync._init_components(self.a).vault_id
        self.snap = self.env.api.packs(self.vid, PACK_SNAPSHOTS)[0]
        self.size = Vault__Packs().parse_name(self.snap)['size']
        self.good = self.env.store_bytes(self.a)

    def _serve(self, data: bytes) -> None:
        self.env.api._store[f'{self.vid}/{self.snap}'] = data

    def _clone(self):
        sync = self.env.sync(); d = self.env.path()
        try:
            sync.clone(self.key, d)
        except Exception as error:
            return d, error
        return d, None

    def test_a_member_whose_bytes_do_not_hash_to_its_id_is_never_written(self):
        victim = sorted(self.good)[0]
        self._serve(_pad(_rezip(self.env.api.host_files(self.vid)[self.snap],
                                lambda n, b: (n, b[:-1] + bytes([b[-1] ^ 1]) if n.endswith(victim) else b)), self.size))
        d, _ = self._clone()
        store = self.env.store_bytes(d) if os.path.isdir(os.path.join(d, '.sg_vault')) else {}
        assert victim not in store
        assert _store_is_content_addressed(store)
        assert all(store[k] == self.good[k] for k in store)                     # what landed is the real object

    def test_a_member_outside_the_store_is_refused_by_name(self):
        planted = {'bare/refs/ref-pid-muw-000000000000': b'ref', 'bare/keys/key-rnd-imm-0000000000000000': b'key',
                   '../../escaped': b'x', 'bare/data/../indexes/idx': b'y'}
        def mutate(n, b):
            return (n, b)
        data = _rezip(self.env.api.host_files(self.vid)[self.snap], mutate)
        buf  = io.BytesIO(data)
        with zipfile.ZipFile(buf, 'a') as z:
            for name, body in planted.items():
                z.writestr(name, body)
        self._serve(_pad(buf.getvalue(), self.size))
        d, _ = self._clone()
        root = os.path.dirname(d)
        assert not os.path.exists(os.path.join(root, 'escaped')) and not os.path.exists(os.path.join(d, 'escaped'))
        for rel in ('bare/refs/ref-pid-muw-000000000000', 'bare/keys/key-rnd-imm-0000000000000000', 'bare/indexes/idx'):
            assert not os.path.exists(os.path.join(d, '.sg_vault', rel))
        store = self.env.store_bytes(d) if os.path.isdir(os.path.join(d, '.sg_vault')) else {}
        assert _store_is_content_addressed(store)

    def test_a_pack_whose_length_disagrees_with_its_name_is_refused_before_it_is_opened(self):
        self._serve(self.env.api.host_files(self.vid)[self.snap] + b'trailing garbage')
        d, error = self._clone()
        store = self.env.store_bytes(d) if os.path.isdir(os.path.join(d, '.sg_vault')) else {}
        assert not store or _store_is_content_addressed(store)
        assert error is not None and 'expected' in str(error)

    def test_control__the_real_pack_clones(self):
        d, error = self._clone()
        assert error is None and self.env.store_bytes(d) == self.good

    def test_a_forged_commit_pack_cannot_move_the_branch(self):
        """A pack only carries objects; the branch ref still travels as today, under the
        same compare-and-swap, and a clone's HEAD comes from the ref, not from the packs."""
        packs = Vault__Packs(crypto=Vault__Crypto(), api=self.env.api)
        forged = io.BytesIO()
        with zipfile.ZipFile(forged, 'w') as z:
            z.writestr('bare/data/obj-cas-imm-f0f0f0f0f0f0', b'not even ciphertext')
        name = packs.pack_name('obj-cas-imm-f0f0f0f0f0f0', len(forged.getvalue()))
        self.env.api._store[f'{self.vid}/{PACK_COMMITS}{name}'] = forged.getvalue()
        d, error = self._clone()
        assert error is None
        assert self.env.tree(d) == self.env.tree(self.a)
        assert 'obj-cas-imm-f0f0f0f0f0f0' not in self.env.store_bytes(d)
