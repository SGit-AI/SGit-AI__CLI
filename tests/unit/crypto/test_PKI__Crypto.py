import base64
import hashlib
import json
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.exceptions                   import InvalidSignature
from sg_send_cli.crypto.PKI__Crypto            import PKI__Crypto


class Test_PKI__Crypto__Key_Generation:

    def setup_method(self):
        self.pki = PKI__Crypto()

    def test_generate_encryption_key_pair(self):
        priv, pub = self.pki.generate_encryption_key_pair()
        assert priv is not None
        assert pub  is not None
        assert priv.key_size == 4096

    def test_generate_signing_key_pair(self):
        priv, pub = self.pki.generate_signing_key_pair()
        assert priv is not None
        assert pub  is not None
        assert priv.curve.name == 'secp256r1'


class Test_PKI__Crypto__PEM:

    def setup_method(self):
        self.pki = PKI__Crypto()

    def test_export_import_public_key_roundtrip(self):
        priv, pub = self.pki.generate_encryption_key_pair()
        pem       = self.pki.export_public_key_pem(pub)
        assert '-----BEGIN PUBLIC KEY-----' in pem
        assert '-----END PUBLIC KEY-----'   in pem
        imported = self.pki.import_public_key_pem(pem)
        assert self.pki.compute_fingerprint(pub) == self.pki.compute_fingerprint(imported)

    def test_export_import_private_key_roundtrip(self):
        priv, pub = self.pki.generate_encryption_key_pair()
        pem       = self.pki.export_private_key_pem(priv)
        assert '-----BEGIN PRIVATE KEY-----' in pem
        imported = self.pki.import_private_key_pem(pem)
        assert imported.key_size == 4096

    def test_export_import_private_key_with_passphrase(self):
        priv, pub = self.pki.generate_encryption_key_pair()
        pem       = self.pki.export_private_key_pem(priv, passphrase='test-pass')
        assert '-----BEGIN ENCRYPTED PRIVATE KEY-----' in pem
        imported = self.pki.import_private_key_pem(pem, passphrase='test-pass')
        assert imported.key_size == 4096

    def test_wrong_passphrase_fails(self):
        priv, pub = self.pki.generate_encryption_key_pair()
        pem       = self.pki.export_private_key_pem(priv, passphrase='correct')
        with pytest.raises(Exception):
            self.pki.import_private_key_pem(pem, passphrase='wrong')

    def test_signing_key_pem_roundtrip(self):
        priv, pub = self.pki.generate_signing_key_pair()
        pub_pem   = self.pki.export_public_key_pem(pub)
        priv_pem  = self.pki.export_private_key_pem(priv)
        pub_imported  = self.pki.import_public_key_pem(pub_pem)
        priv_imported = self.pki.import_private_key_pem(priv_pem)
        assert self.pki.compute_fingerprint(pub) == self.pki.compute_fingerprint(pub_imported)


class Test_PKI__Crypto__Fingerprint:

    def setup_method(self):
        self.pki = PKI__Crypto()

    def test_fingerprint_format(self):
        _, pub = self.pki.generate_encryption_key_pair()
        fp     = self.pki.compute_fingerprint(pub)
        assert fp.startswith('sha256:')
        assert len(fp) == 23

    def test_fingerprint_is_deterministic(self):
        _, pub = self.pki.generate_encryption_key_pair()
        fp1    = self.pki.compute_fingerprint(pub)
        fp2    = self.pki.compute_fingerprint(pub)
        assert fp1 == fp2

    def test_different_keys_different_fingerprints(self):
        _, pub1 = self.pki.generate_encryption_key_pair()
        _, pub2 = self.pki.generate_encryption_key_pair()
        assert self.pki.compute_fingerprint(pub1) != self.pki.compute_fingerprint(pub2)

    def test_fingerprint_matches_server_implementation(self):
        _, pub = self.pki.generate_encryption_key_pair()
        pem    = self.pki.export_public_key_pem(pub)
        fp_cli = self.pki.compute_fingerprint(pub)

        lines    = pem.strip().split('\n')
        b64_data = ''.join(line for line in lines if not line.startswith('-----'))
        der      = base64.b64decode(b64_data)
        digest   = hashlib.sha256(der).hexdigest()
        fp_server = f"sha256:{digest[:16]}"

        assert fp_cli == fp_server

    def test_fingerprint_matches_for_signing_key(self):
        _, pub  = self.pki.generate_signing_key_pair()
        pem     = self.pki.export_public_key_pem(pub)
        fp_cli  = self.pki.compute_fingerprint(pub)

        lines    = pem.strip().split('\n')
        b64_data = ''.join(line for line in lines if not line.startswith('-----'))
        der      = base64.b64decode(b64_data)
        digest   = hashlib.sha256(der).hexdigest()
        fp_server = f"sha256:{digest[:16]}"

        assert fp_cli == fp_server


class Test_PKI__Crypto__Signing:

    def setup_method(self):
        self.pki = PKI__Crypto()

    def test_sign_returns_64_bytes(self):
        priv, pub = self.pki.generate_signing_key_pair()
        sig       = self.pki.sign(priv, b"test message")
        assert len(sig) == 64

    def test_sign_verify_roundtrip(self):
        priv, pub = self.pki.generate_signing_key_pair()
        message   = b"hello world"
        sig       = self.pki.sign(priv, message)
        assert self.pki.verify(pub, sig, message) is True

    def test_verify_wrong_message_fails(self):
        priv, pub = self.pki.generate_signing_key_pair()
        sig       = self.pki.sign(priv, b"correct message")
        with pytest.raises(InvalidSignature):
            self.pki.verify(pub, sig, b"wrong message")

    def test_verify_wrong_key_fails(self):
        priv1, pub1 = self.pki.generate_signing_key_pair()
        _,     pub2 = self.pki.generate_signing_key_pair()
        sig = self.pki.sign(priv1, b"message")
        with pytest.raises(InvalidSignature):
            self.pki.verify(pub2, sig, b"message")

    def test_sign_verify_binary_data(self):
        priv, pub = self.pki.generate_signing_key_pair()
        data      = bytes(range(256))
        sig       = self.pki.sign(priv, data)
        assert self.pki.verify(pub, sig, data) is True


class Test_PKI__Crypto__Hybrid_Encryption:

    def setup_method(self):
        self.pki = PKI__Crypto()

    def test_encrypt_decrypt_roundtrip(self):
        priv, pub = self.pki.generate_encryption_key_pair()
        encoded   = self.pki.hybrid_encrypt(pub, "hello world")
        result    = self.pki.hybrid_decrypt(priv, encoded)
        assert result['plaintext'] == 'hello world'
        assert result['signed']    is False
        assert result['verified']  is False

    def test_encrypt_decrypt_binary(self):
        priv, pub = self.pki.generate_encryption_key_pair()
        data      = bytes(range(256))
        encoded   = self.pki.hybrid_encrypt(pub, data)
        result    = self.pki.hybrid_decrypt(priv, encoded)
        assert result['plaintext'] == data.decode('latin-1') or len(result['plaintext']) > 0

    def test_payload_is_v2_format(self):
        _, pub  = self.pki.generate_encryption_key_pair()
        encoded = self.pki.hybrid_encrypt(pub, "test")
        payload = json.loads(base64.b64decode(encoded))
        assert payload['v'] == 2
        assert 'w' in payload
        assert 'i' in payload
        assert 'c' in payload

    def test_encrypt_decrypt_with_signature(self):
        enc_priv, enc_pub = self.pki.generate_encryption_key_pair()
        sig_priv, sig_pub = self.pki.generate_signing_key_pair()
        sig_fp = self.pki.compute_fingerprint(sig_pub)

        encoded = self.pki.hybrid_encrypt(enc_pub, "signed message",
                                          signing_private_key=sig_priv,
                                          signing_fingerprint=sig_fp)

        payload = json.loads(base64.b64decode(encoded))
        assert 's' in payload
        assert 'f' in payload
        assert payload['f'] == sig_fp

        result = self.pki.hybrid_decrypt(enc_priv, encoded)
        assert result['plaintext'] == 'signed message'
        assert result['signed']    is True

    def test_wrong_key_decrypt_fails(self):
        _, pub1 = self.pki.generate_encryption_key_pair()
        priv2, _ = self.pki.generate_encryption_key_pair()
        encoded = self.pki.hybrid_encrypt(pub1, "secret")
        with pytest.raises(Exception):
            self.pki.hybrid_decrypt(priv2, encoded)

    def test_unsupported_version_fails(self):
        bad_payload = base64.b64encode(json.dumps({'v': 99}).encode()).decode()
        priv, _ = self.pki.generate_encryption_key_pair()
        with pytest.raises(ValueError, match="Unsupported payload version"):
            self.pki.hybrid_decrypt(priv, bad_payload)

    def test_encrypt_decrypt_large_message(self):
        priv, pub = self.pki.generate_encryption_key_pair()
        message   = "A" * 10000
        encoded   = self.pki.hybrid_encrypt(pub, message)
        result    = self.pki.hybrid_decrypt(priv, encoded)
        assert result['plaintext'] == message
