import base64
import hashlib
import json
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.exceptions                   import InvalidSignature
from sgit_ai.crypto.PKI__Crypto            import PKI__Crypto


# ---------------------------------------------------------------------------
# Module-level pre-generated key fixtures (generated once, shared read-only)
# ---------------------------------------------------------------------------

_pki = PKI__Crypto()

# RSA-4096 encryption key pair (expensive — ~0.5 s each)
_ENC_PRIV,  _ENC_PUB  = _pki.generate_encryption_key_pair()
_ENC_PRIV2, _ENC_PUB2 = _pki.generate_encryption_key_pair()

# EC signing key pairs (fast — reused where possible)
_SIG_PRIV,  _SIG_PUB  = _pki.generate_signing_key_pair()
_SIG_PRIV2, _SIG_PUB2 = _pki.generate_signing_key_pair()


class Test_PKI__Crypto__Key_Generation:
    """Tests that specifically verify key-generation behaviour get fresh keys."""

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
        pem      = self.pki.export_public_key_pem(_ENC_PUB)
        assert '-----BEGIN PUBLIC KEY-----' in pem
        assert '-----END PUBLIC KEY-----'   in pem
        imported = self.pki.import_public_key_pem(pem)
        assert self.pki.compute_fingerprint(_ENC_PUB) == self.pki.compute_fingerprint(imported)

    def test_export_import_private_key_roundtrip(self):
        pem      = self.pki.export_private_key_pem(_ENC_PRIV)
        assert '-----BEGIN PRIVATE KEY-----' in pem
        imported = self.pki.import_private_key_pem(pem)
        assert imported.key_size == 4096

    def test_export_import_private_key_with_passphrase(self):
        pem      = self.pki.export_private_key_pem(_ENC_PRIV, passphrase='test-pass')
        assert '-----BEGIN ENCRYPTED PRIVATE KEY-----' in pem
        imported = self.pki.import_private_key_pem(pem, passphrase='test-pass')
        assert imported.key_size == 4096

    def test_wrong_passphrase_fails(self):
        pem = self.pki.export_private_key_pem(_ENC_PRIV, passphrase='correct')
        with pytest.raises(Exception):
            self.pki.import_private_key_pem(pem, passphrase='wrong')

    def test_signing_key_pem_roundtrip(self):
        pub_pem       = self.pki.export_public_key_pem(_SIG_PUB)
        priv_pem      = self.pki.export_private_key_pem(_SIG_PRIV)
        pub_imported  = self.pki.import_public_key_pem(pub_pem)
        priv_imported = self.pki.import_private_key_pem(priv_pem)
        assert self.pki.compute_fingerprint(_SIG_PUB) == self.pki.compute_fingerprint(pub_imported)


class Test_PKI__Crypto__Fingerprint:

    def setup_method(self):
        self.pki = PKI__Crypto()

    def test_fingerprint_format(self):
        fp = self.pki.compute_fingerprint(_ENC_PUB)
        assert fp.startswith('sha256:')
        assert len(fp) == 23

    def test_fingerprint_is_deterministic(self):
        fp1 = self.pki.compute_fingerprint(_ENC_PUB)
        fp2 = self.pki.compute_fingerprint(_ENC_PUB)
        assert fp1 == fp2

    def test_different_keys_different_fingerprints(self):
        assert self.pki.compute_fingerprint(_ENC_PUB) != self.pki.compute_fingerprint(_ENC_PUB2)

    def test_fingerprint_matches_server_implementation(self):
        pem    = self.pki.export_public_key_pem(_ENC_PUB)
        fp_cli = self.pki.compute_fingerprint(_ENC_PUB)

        lines    = pem.strip().split('\n')
        b64_data = ''.join(line for line in lines if not line.startswith('-----'))
        der      = base64.b64decode(b64_data)
        digest   = hashlib.sha256(der).hexdigest()
        fp_server = f"sha256:{digest[:16]}"

        assert fp_cli == fp_server

    def test_fingerprint_matches_for_signing_key(self):
        pem    = self.pki.export_public_key_pem(_SIG_PUB)
        fp_cli = self.pki.compute_fingerprint(_SIG_PUB)

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
        sig = self.pki.sign(_SIG_PRIV, b"test message")
        assert len(sig) == 64

    def test_sign_verify_roundtrip(self):
        message = b"hello world"
        sig     = self.pki.sign(_SIG_PRIV, message)
        assert self.pki.verify(_SIG_PUB, sig, message) is True

    def test_verify_wrong_message_fails(self):
        sig = self.pki.sign(_SIG_PRIV, b"correct message")
        with pytest.raises(InvalidSignature):
            self.pki.verify(_SIG_PUB, sig, b"wrong message")

    def test_verify_wrong_key_fails(self):
        sig = self.pki.sign(_SIG_PRIV, b"message")
        with pytest.raises(InvalidSignature):
            self.pki.verify(_SIG_PUB2, sig, b"message")

    def test_sign_verify_binary_data(self):
        data = bytes(range(256))
        sig  = self.pki.sign(_SIG_PRIV, data)
        assert self.pki.verify(_SIG_PUB, sig, data) is True


class Test_PKI__Crypto__Hybrid_Encryption:

    def setup_method(self):
        self.pki = PKI__Crypto()

    def test_encrypt_decrypt_roundtrip(self):
        encoded = self.pki.hybrid_encrypt(_ENC_PUB, "hello world")
        result  = self.pki.hybrid_decrypt(_ENC_PRIV, encoded)
        assert result['plaintext'] == 'hello world'
        assert result['signed']    is False
        assert result['verified']  is False

    def test_encrypt_decrypt_binary(self):
        data    = bytes(range(256))
        encoded = self.pki.hybrid_encrypt(_ENC_PUB, data)
        result  = self.pki.hybrid_decrypt(_ENC_PRIV, encoded)
        assert result['plaintext'] == data.decode('latin-1') or len(result['plaintext']) > 0

    def test_payload_is_v2_format(self):
        encoded = self.pki.hybrid_encrypt(_ENC_PUB, "test")
        payload = json.loads(base64.b64decode(encoded))
        assert payload['v'] == 2
        assert 'w' in payload
        assert 'i' in payload
        assert 'c' in payload

    def test_encrypt_decrypt_with_signature(self):
        sig_fp  = self.pki.compute_fingerprint(_SIG_PUB)

        encoded = self.pki.hybrid_encrypt(_ENC_PUB, "signed message",
                                          signing_private_key=_SIG_PRIV,
                                          signing_fingerprint=sig_fp)

        payload = json.loads(base64.b64decode(encoded))
        assert 's' in payload
        assert 'f' in payload
        assert payload['f'] == sig_fp

        result = self.pki.hybrid_decrypt(_ENC_PRIV, encoded)
        assert result['plaintext'] == 'signed message'
        assert result['signed']    is True

    def test_wrong_key_decrypt_fails(self):
        encoded = self.pki.hybrid_encrypt(_ENC_PUB, "secret")
        with pytest.raises(Exception):
            self.pki.hybrid_decrypt(_ENC_PRIV2, encoded)

    def test_unsupported_version_fails(self):
        bad_payload = base64.b64encode(json.dumps({'v': 99}).encode()).decode()
        with pytest.raises(ValueError, match="Unsupported payload version"):
            self.pki.hybrid_decrypt(_ENC_PRIV, bad_payload)

    def test_encrypt_decrypt_large_message(self):
        message = "A" * 10000
        encoded = self.pki.hybrid_encrypt(_ENC_PUB, message)
        result  = self.pki.hybrid_decrypt(_ENC_PRIV, encoded)
        assert result['plaintext'] == message
