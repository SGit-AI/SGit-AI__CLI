"""The `user_signature` member (design__02 §5.1, step 1): outside both signatures' bytes.

Clients that do not know the member compute the same signing bytes, an unsigned
commit or tag is stored byte for byte as before, and either signature verifies alone."""
import base64
import json

import pytest

from sgit_ai.crypto.PKI__Crypto                      import PKI__Crypto
from sgit_ai.crypto.Vault__Crypto                    import Vault__Crypto
from sgit_ai.safe_types.Enum__User_Signature_Format  import Enum__User_Signature_Format
from sgit_ai.safe_types.Safe_Str__User_Signature_Blob import Safe_Str__User_Signature_Blob
from sgit_ai.schemas.Schema__Object_Commit           import Schema__Object_Commit
from sgit_ai.schemas.Schema__Object_Tag              import Schema__Object_Tag
from sgit_ai.schemas.Schema__User_Signature          import Schema__User_Signature
from sgit_ai.storage.Vault__Commit                   import Vault__Commit
from sgit_ai.storage.Vault__Object_Store             import Vault__Object_Store

READ_KEY = bytes(range(32))
BLOB     = base64.b64encode(b'U' * 300).decode()


class Test_Vault__Commit__User_Signature:

    def setup_method(self, method):
        import tempfile
        self.tmp       = tempfile.mkdtemp()
        self.crypto    = Vault__Crypto()
        self.pki       = PKI__Crypto()
        self.vc        = Vault__Commit(crypto=self.crypto, pki=self.pki,
                                       object_store=Vault__Object_Store(vault_path=self.tmp, crypto=self.crypto))
        self.priv, self.pub = self.pki.generate_signing_key_pair()

    def teardown_method(self, method):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def stored(self, commit_id) -> dict:
        return json.loads(self.crypto.decrypt(READ_KEY, self.vc.object_store.load(commit_id)))

    def test_an_unsigned_commit_is_stored_without_the_member(self):
        cid = self.vc.create_commit(read_key=READ_KEY, tree_id='obj-cas-imm-1b397bef28b6', message='m',
                                    signing_key=self.priv, author_key_id='key-rnd-imm-aabbccdd00112233')
        assert 'user_signature' not in self.stored(cid)
        assert set(self.stored(cid)) == {'schema', 'tree_id', 'parents', 'timestamp_ms', 'message_enc', 'branch_id',
                                         'signature', 'author_key_id', 'author_signature', 'attestations'}

    def test_adding_a_user_signature_keeps_the_clone_signature_valid(self):
        cid    = self.vc.create_commit(read_key=READ_KEY, tree_id='obj-cas-imm-1b397bef28b6', message='m',
                                       signing_key=self.priv, author_key_id='key-rnd-imm-aabbccdd00112233')
        commit = self.vc.load_commit(cid, READ_KEY)
        before = self.vc.signing_bytes(commit.json())
        commit.user_signature = Schema__User_Signature(format=Enum__User_Signature_Format.SSH, blob=BLOB)
        assert self.vc.signing_bytes(commit.json()) == before
        assert self.vc.verify_commit_signature(commit, self.pub)
        round_trip = Schema__Object_Commit.from_json(json.loads(json.dumps(self.vc.stored_json(commit))))
        assert round_trip.user_signature.format == Enum__User_Signature_Format.SSH
        assert self.vc.verify_commit_signature(round_trip, self.pub)

    def test_a_legacy_commit_still_verifies_with_the_member_present(self):
        commit = Schema__Object_Commit(schema='commit_v1', tree_id='obj-cas-imm-1b397bef28b6', timestamp_ms=1)
        legacy = self.vc.legacy_signing_bytes(commit.json())
        assert b'user_signature' not in legacy
        commit.signature      = base64.b64encode(self.pki.sign(self.priv, legacy)).decode()
        commit.user_signature = Schema__User_Signature(format=Enum__User_Signature_Format.OPENPGP, blob=BLOB)
        assert self.vc.verify_commit_signature(commit, self.pub)

    def test_old_clients_drop_the_member_and_compute_the_same_bytes(self):
        commit = Schema__Object_Commit(schema='commit_v1', tree_id='obj-cas-imm-1b397bef28b6', timestamp_ms=1,
                                       author_key_id='key-rnd-imm-aabbccdd00112233',
                                       user_signature=Schema__User_Signature(format='ssh', blob=BLOB))
        old_view = {k: v for k, v in commit.json().items() if k != 'user_signature'}   # what an old schema keeps
        assert self.vc.signing_bytes(old_view) == self.vc.signing_bytes(commit.json())

    def test_the_schemas_round_trip(self):
        for obj in (Schema__Object_Commit(user_signature=Schema__User_Signature(format='openpgp', blob=BLOB)),
                    Schema__Object_Tag(user_signature=Schema__User_Signature(format='ssh', blob=BLOB)),
                    Schema__Object_Commit(), Schema__Object_Tag()):
            assert type(obj).from_json(obj.json()).json() == obj.json()

    def test_the_blob_type_refuses_what_is_not_base64(self):
        for bad in ('short', 'not base64 at all!' * 3, 'A' * 9000):
            with pytest.raises(ValueError):
                Safe_Str__User_Signature_Blob(bad)
