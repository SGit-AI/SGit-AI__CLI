"""Interop vectors shared with the web UI (tests/_fixtures/interop_vectors.json).

Both clients must reproduce every value here byte for byte: object ids at 12 and
32 hex, the deterministic tree encryption (IV = HMAC-SHA256(read_key, plaintext)[:12]),
and the canonical commit signing bytes (JCS of the stored commit JSON minus
"signature"). A change that breaks one of these is a cross-client incompatibility,
not a refactor. The 7 Oct 2026 reply to the SG/Send team carries the same values."""
import base64
import hashlib
import hmac
import json
import os
import tempfile

from sgit_ai.crypto.Vault__Crypto            import Vault__Crypto
from sgit_ai.crypto.PKI__Crypto              import PKI__Crypto
from sgit_ai.schemas.Schema__Object_Commit   import Schema__Object_Commit
from sgit_ai.storage.Vault__Commit           import Vault__Commit
from sgit_ai.storage.Vault__Object_Store     import Vault__Object_Store
from sgit_ai.storage.Vault__Ref_Manager      import Vault__Ref_Manager

FIXTURE = os.path.join(os.path.dirname(__file__), '..', '..', '_fixtures', 'interop_vectors.json')


class Test_Interop__Vectors:

    def setup_method(self):
        with open(FIXTURE) as f:
            self.v = json.load(f)
        self.crypto = Vault__Crypto(); self.pki = PKI__Crypto()
        d = tempfile.mkdtemp()
        self.vc = Vault__Commit(crypto=self.crypto, pki=self.pki,
                                object_store=Vault__Object_Store(vault_path=d, crypto=self.crypto),
                                ref_manager=Vault__Ref_Manager(vault_path=d, crypto=self.crypto))

    def test_object_id_formats(self):
        v  = self.v['object_id']; c = v['ciphertext_ascii'].encode()
        h  = hashlib.sha256(c).hexdigest()
        assert h == v['sha256']
        assert self.crypto.compute_object_id(c) == v['format_1'] == 'obj-cas-imm-' + h[:12]
        assert 'obj-cas-imm-' + h[:32] == v['format_2']

    def test_deterministic_tree_encryption(self):
        v   = self.v['tree_deterministic']; key = bytes.fromhex(v['read_key_hex'])
        pt  = v['plaintext_utf8'].encode('utf-8')
        assert hashlib.sha256(pt).hexdigest() == v['plaintext_sha256']
        assert hmac.new(key, pt, hashlib.sha256).digest()[:12].hex() == v['iv_hex']
        ct  = self.crypto.encrypt_deterministic(key, pt)
        assert ct.hex() == v['ciphertext_hex']
        assert self.crypto.compute_object_id(ct) == v['object_id']
        assert self.crypto.decrypt(key, bytes.fromhex(v['ciphertext_hex'])) == pt
        assert self.crypto.encrypt_metadata_deterministic(key, v['name_plain']) == v['name_enc']

    def test_commit_signing_bytes_and_signature(self):
        v   = self.v['commit_signing']
        cd  = v['stored_commit_json']
        sb  = self.vc.signing_bytes(cd)
        assert sb.decode('utf-8') == v['signing_bytes_utf8']
        assert hashlib.sha256(sb).hexdigest() == v['signing_bytes_sha256']
        assert '"signature"' not in v['signing_bytes_utf8']
        pub = self.pki.import_public_key_pem(v['test_public_key_pem'])
        assert self.pki.compute_fingerprint(pub) == v['key_fingerprint']
        assert self.pki.verify(pub, base64.b64decode(v['signature_b64']), sb)
        assert base64.b64decode(v['signature_b64']).hex() == v['signature_r_s_hex']
        commit = Schema__Object_Commit.from_json(cd)
        assert self.vc.verify_commit_signature(commit, pub) is True
        # the same key signing the same bytes again verifies too (ECDSA is randomised, so no byte compare)
        priv = self.pki.import_private_key_pem(v['test_private_key_pem'])
        assert self.pki.verify(pub, self.pki.sign(priv, sb), sb)

    def test_legacy_commits_still_verify(self):
        """A commit signed before the canonical form (author_key_id null) verifies over the legacy bytes."""
        priv, pub = self.pki.generate_signing_key_pair()
        cd  = dict(self.v['legacy_signing_bytes_example'] and json.loads(self.v['legacy_signing_bytes_example']['bytes_utf8']))
        cd['signature'] = base64.b64encode(self.pki.sign(priv, self.vc.legacy_signing_bytes(cd))).decode()
        commit = Schema__Object_Commit.from_json(cd)
        assert commit.author_key_id is None
        assert self.vc.verify_commit_signature(commit, pub) is True
        cd['author_key_id'] = 'key-rnd-imm-0011223344556677'            # claims canonical form: legacy bytes no longer accepted
        assert self.vc.verify_commit_signature(Schema__Object_Commit.from_json(cd), pub) is False

    def test_new_commits_carry_author_key_id_and_canonical_signature(self):
        key = bytes.fromhex(self.v['tree_deterministic']['read_key_hex'])
        priv, pub = self.pki.generate_signing_key_pair()
        cid = self.vc.create_commit(read_key=key, tree_id='obj-cas-imm-1b397bef28b6', message='m',
                                    signing_key=priv, author_key_id='key-rnd-imm-aabbccdd00112233')
        cm  = self.vc.load_commit(cid, key)
        assert str(cm.author_key_id) == 'key-rnd-imm-aabbccdd00112233'
        sb  = self.vc.signing_bytes(cm.json())
        assert self.pki.verify(pub, base64.b64decode(str(cm.signature)), sb)
        assert json.loads(sb) == {k: v for k, v in cm.json().items() if k != 'signature'}
