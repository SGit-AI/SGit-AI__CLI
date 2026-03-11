import os
import tempfile
import shutil
from sg_send_cli.pki.PKI__Keyring import PKI__Keyring


class Test_PKI__Keyring:

    def setup_method(self):
        self.tmp_dir    = tempfile.mkdtemp()
        self.keyring_dir = os.path.join(self.tmp_dir, 'keyring')
        self.keyring    = PKI__Keyring(keyring_dir=self.keyring_dir)

    def teardown_method(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_add_and_get_contact(self):
        self.keyring.add_contact(
            label='Alice', fingerprint='sha256:aaaa111122223333',
            public_key_pem='-----BEGIN PUBLIC KEY-----\nABC\n-----END PUBLIC KEY-----',
            signing_key_pem='-----BEGIN PUBLIC KEY-----\nDEF\n-----END PUBLIC KEY-----',
            signing_fingerprint='sha256:bbbb444455556666')
        contact = self.keyring.get_contact('sha256:aaaa111122223333')
        assert contact['label']       == 'Alice'
        assert contact['fingerprint'] == 'sha256:aaaa111122223333'

    def test_get_missing_contact(self):
        assert self.keyring.get_contact('sha256:0000000000000000') is None

    def test_list_contacts_empty(self):
        assert self.keyring.list_contacts() == []

    def test_list_contacts(self):
        self.keyring.add_contact('Alice', 'sha256:aaaa111122223333', 'pem-a', '')
        self.keyring.add_contact('Bob',   'sha256:bbbb111122223333', 'pem-b', '')
        contacts = self.keyring.list_contacts()
        assert len(contacts) == 2
        labels = [c['label'] for c in contacts]
        assert 'Alice' in labels
        assert 'Bob'   in labels

    def test_remove_contact(self):
        self.keyring.add_contact('Alice', 'sha256:aaaa111122223333', 'pem', '')
        assert self.keyring.remove_contact('sha256:aaaa111122223333') is True
        assert self.keyring.get_contact('sha256:aaaa111122223333') is None

    def test_remove_missing_contact(self):
        assert self.keyring.remove_contact('sha256:0000000000000000') is False

    def test_lookup_by_signing_fingerprint(self):
        self.keyring.add_contact(
            label='Alice', fingerprint='sha256:aaaa111122223333',
            public_key_pem='pem', signing_key_pem='sig-pem',
            signing_fingerprint='sha256:sig1111122223333')
        contact = self.keyring.lookup_by_signing_fingerprint('sha256:sig1111122223333')
        assert contact is not None
        assert contact['label'] == 'Alice'

    def test_lookup_by_signing_fingerprint_not_found(self):
        assert self.keyring.lookup_by_signing_fingerprint('sha256:0000000000000000') is None
