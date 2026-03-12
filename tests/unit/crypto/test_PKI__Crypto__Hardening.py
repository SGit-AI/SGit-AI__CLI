import pytest
from cryptography.exceptions         import InvalidSignature
from sg_send_cli.crypto.PKI__Crypto  import PKI__Crypto


class Test_PKI__Crypto__Hardening:

    @classmethod
    def setup_class(cls):
        cls.pki = PKI__Crypto()
        cls.enc_priv, cls.enc_pub   = cls.pki.generate_encryption_key_pair()
        cls.sign_priv, cls.sign_pub = cls.pki.generate_signing_key_pair()

    def test_hybrid_encrypt__empty_message(self):
        encoded = self.pki.hybrid_encrypt(self.enc_pub, '')
        result  = self.pki.hybrid_decrypt(self.enc_priv, encoded)
        assert result['plaintext'] == ''

    def test_hybrid_encrypt__binary_zeros(self):
        data    = b'\x00' * 1000
        encoded = self.pki.hybrid_encrypt(self.enc_pub, data)
        result  = self.pki.hybrid_decrypt(self.enc_priv, encoded)
        assert len(result['plaintext']) == 1000

    def test_sign__empty_message(self):
        sig = self.pki.sign(self.sign_priv, b'')
        assert len(sig) == 64
        assert self.pki.verify(self.sign_pub, sig, b'') is True

    def test_sign__large_message(self):
        data = b'A' * 100_000
        sig  = self.pki.sign(self.sign_priv, data)
        assert self.pki.verify(self.sign_pub, sig, data) is True

    def test_verify__truncated_signature_fails(self):
        sig = self.pki.sign(self.sign_priv, b'test')
        with pytest.raises(Exception):
            self.pki.verify(self.sign_pub, sig[:32], b'test')

    def test_verify__corrupted_signature_fails(self):
        sig       = self.pki.sign(self.sign_priv, b'test')
        corrupted = bytes([sig[0] ^ 0xFF]) + sig[1:]
        with pytest.raises((InvalidSignature, Exception)):
            self.pki.verify(self.sign_pub, corrupted, b'test')

    def test_fingerprint__encryption_key(self):
        fp = self.pki.compute_fingerprint(self.enc_pub)
        assert fp.startswith('sha256:')
        assert len(fp) == 23

    def test_fingerprint__signing_key(self):
        fp = self.pki.compute_fingerprint(self.sign_pub)
        assert fp.startswith('sha256:')
        assert len(fp) == 23

    def test_fingerprint__different_key_types_differ(self):
        enc_fp  = self.pki.compute_fingerprint(self.enc_pub)
        sign_fp = self.pki.compute_fingerprint(self.sign_pub)
        assert enc_fp != sign_fp

    def test_pem_import__corrupted_pem_fails(self):
        with pytest.raises(Exception):
            self.pki.import_public_key_pem('-----BEGIN PUBLIC KEY-----\nNOTVALID\n-----END PUBLIC KEY-----')

    def test_pem_import__empty_string_fails(self):
        with pytest.raises(Exception):
            self.pki.import_public_key_pem('')

    def test_pem_import__wrong_format_fails(self):
        with pytest.raises(Exception):
            self.pki.import_public_key_pem('just some random text')

    def test_hybrid_encrypt_decrypt__with_signature_and_keyring(self):
        sig_fp  = self.pki.compute_fingerprint(self.sign_pub)
        encoded = self.pki.hybrid_encrypt(self.enc_pub, 'signed message',
                                          signing_private_key=self.sign_priv,
                                          signing_fingerprint=sig_fp)
        result  = self.pki.hybrid_decrypt(self.enc_priv, encoded)
        assert result['plaintext'] == 'signed message'
        assert result['signed']    is True

    def test_export_private_key__no_passphrase(self):
        pem = self.pki.export_private_key_pem(self.enc_priv)
        assert '-----BEGIN PRIVATE KEY-----' in pem

    def test_export_private_key__with_passphrase(self):
        pem = self.pki.export_private_key_pem(self.enc_priv, passphrase='strong-pass')
        assert '-----BEGIN ENCRYPTED PRIVATE KEY-----' in pem
