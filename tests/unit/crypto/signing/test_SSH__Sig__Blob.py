import base64
import json

import pytest

from sgit_ai.crypto.signing.SSH__Sig__Blob import SSH__Sig__Blob, MAGIC
from sgit_ai.crypto.signing.SSH__Wire      import SSH__Wire, Vault__SSH_Format_Error

VECTOR = json.load(open('tests/_fixtures/interop_vectors.json'))['commit_user_signing']


class Test_SSH__Sig__Blob:

    def setup_method(self):
        self.blob = base64.b64decode(VECTOR['stored_commit_json']['user_signature']['blob'])

    def test_parses_the_ssh_keygen_vector(self):
        sig = SSH__Sig__Blob().parse(self.blob)
        assert (sig.namespace, sig.reserved, sig.hash_algorithm) == (b'git', b'', b'sha512')
        assert sig.build() == self.blob
        assert sig.signed_data(VECTOR['signing_bytes_utf8'].encode()).hex() == VECTOR['sshsig_signed_data_hex']

    def test_armor_round_trip_matches_ssh_keygen(self):
        sig = SSH__Sig__Blob()
        assert sig.armor(self.blob) == VECTOR['armored']
        assert sig.dearmor(VECTOR['armored']) == self.blob
        assert all(len(row) <= 70 for row in VECTOR['armored'].splitlines())

    def rebuilt(self, **changes) -> bytes:
        sig = SSH__Sig__Blob().parse(self.blob)
        for name, value in changes.items():
            setattr(sig, name, value)
        return sig.build()

    @pytest.mark.parametrize('bad, message', [
        (lambda b: b'SSHSIX' + b[6:],                                   'wrong magic'),
        (lambda b: MAGIC + SSH__Wire().uint32(2) + b[10:],              'version 2'),
        (lambda b: b + b'\x00',                                         'trailing byte'),
        (lambda b: b[:-3],                                              'truncated'),
        (lambda b: MAGIC + SSH__Wire().uint32(1) + b'\x00' * 7000,      'cap'),
    ])
    def test_malformed_blobs_are_refused_by_name(self, bad, message):
        with pytest.raises(Vault__SSH_Format_Error, match=message):
            SSH__Sig__Blob().parse(bad(self.blob))

    def test_an_unknown_hash_is_refused(self):
        with pytest.raises(Vault__SSH_Format_Error, match='not sha256 or sha512'):
            SSH__Sig__Blob().parse(self.rebuilt(hash_algorithm=b'md5')).signed_data(b'x')

    def test_dearmor_refuses_what_is_not_armored(self):
        with pytest.raises(Vault__SSH_Format_Error):
            SSH__Sig__Blob().dearmor('hello')
