import hashlib
import os
import base64
import json
from cryptography.hazmat.primitives.asymmetric     import rsa, ec, padding, utils as asym_utils
from cryptography.hazmat.primitives                 import hashes, serialization
from cryptography.hazmat.primitives.ciphers.aead    import AESGCM
from osbot_utils.type_safe.Type_Safe                import Type_Safe

AES_KEY_BYTES = 32
GCM_IV_BYTES  = 12


class PKI__Crypto(Type_Safe):

    # --- Key Generation ---

    def generate_encryption_key_pair(self):
        private_key = rsa.generate_private_key(
            public_exponent = 65537,
            key_size        = 4096)
        return private_key, private_key.public_key()

    def generate_signing_key_pair(self):
        private_key = ec.generate_private_key(ec.SECP256R1())
        return private_key, private_key.public_key()

    # --- PEM Export ---

    def export_public_key_pem(self, public_key) -> str:
        return public_key.public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo
        ).decode()

    def export_private_key_pem(self, private_key, passphrase=None) -> str:
        encryption = (serialization.BestAvailableEncryption(passphrase.encode())
                      if passphrase
                      else serialization.NoEncryption())
        return private_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            encryption
        ).decode()

    # --- PEM Import ---

    def import_public_key_pem(self, pem_str):
        return serialization.load_pem_public_key(pem_str.encode())

    def import_private_key_pem(self, pem_str, passphrase=None):
        pwd = passphrase.encode() if passphrase else None
        return serialization.load_pem_private_key(pem_str.encode(), password=pwd)

    # --- Fingerprint (must match browser pki-common.js and server Service__Keys.py) ---

    def compute_fingerprint(self, public_key) -> str:
        der    = public_key.public_bytes(
            serialization.Encoding.DER,
            serialization.PublicFormat.SubjectPublicKeyInfo)
        digest = hashlib.sha256(der).hexdigest()
        return f"sha256:{digest[:16]}"

    # --- Signing (ECDSA P-256, raw r||s for Web Crypto interop) ---

    def sign(self, private_key, data: bytes) -> bytes:
        der_sig = private_key.sign(data, ec.ECDSA(hashes.SHA256()))
        r, s    = asym_utils.decode_dss_signature(der_sig)
        return r.to_bytes(32, 'big') + s.to_bytes(32, 'big')

    def verify(self, public_key, signature_raw: bytes, data: bytes) -> bool:
        r       = int.from_bytes(signature_raw[:32], 'big')
        s       = int.from_bytes(signature_raw[32:], 'big')
        der_sig = asym_utils.encode_dss_signature(r, s)
        public_key.verify(der_sig, data, ec.ECDSA(hashes.SHA256()))
        return True

    # --- Hybrid Encryption (RSA-OAEP wraps AES-256-GCM, v2 payload) ---

    def hybrid_encrypt(self, recipient_public_key, plaintext,
                       signing_private_key=None, signing_fingerprint=None) -> str:
        data    = plaintext.encode() if isinstance(plaintext, str) else plaintext
        aes_key = os.urandom(AES_KEY_BYTES)
        iv      = os.urandom(GCM_IV_BYTES)

        aesgcm     = AESGCM(aes_key)
        ciphertext = aesgcm.encrypt(iv, data, None)

        wrapped_key = recipient_public_key.encrypt(
            aes_key,
            padding.OAEP(
                mgf       = padding.MGF1(algorithm=hashes.SHA256()),
                algorithm = hashes.SHA256(),
                label     = None))

        payload = dict(v = 2,
                       w = base64.b64encode(wrapped_key).decode(),
                       i = base64.b64encode(iv).decode(),
                       c = base64.b64encode(ciphertext).decode())

        if signing_private_key and signing_fingerprint:
            sig_raw      = self.sign(signing_private_key, ciphertext)
            payload['s'] = base64.b64encode(sig_raw).decode()
            payload['f'] = signing_fingerprint

        return base64.b64encode(json.dumps(payload).encode()).decode()

    def hybrid_decrypt(self, recipient_private_key, encoded_payload,
                       contacts_keyring=None) -> dict:
        payload = json.loads(base64.b64decode(encoded_payload))

        if payload.get('v') not in (1, 2):
            raise ValueError(f"Unsupported payload version: {payload.get('v')}")

        wrapped_key = base64.b64decode(payload['w'])
        iv          = base64.b64decode(payload['i'])
        ciphertext  = base64.b64decode(payload['c'])

        aes_key = recipient_private_key.decrypt(
            wrapped_key,
            padding.OAEP(
                mgf       = padding.MGF1(algorithm=hashes.SHA256()),
                algorithm = hashes.SHA256(),
                label     = None))

        aesgcm         = AESGCM(aes_key)
        plaintext_bytes = aesgcm.decrypt(iv, ciphertext, None)

        try:
            plaintext_str = plaintext_bytes.decode('utf-8')
        except UnicodeDecodeError:
            plaintext_str = plaintext_bytes.decode('latin-1')

        result = dict(plaintext = plaintext_str,
                      signed    = False,
                      verified  = False,
                      signer    = None)

        if payload.get('s') and payload.get('f'):
            result['signed'] = True
            if contacts_keyring:
                sig_raw = base64.b64decode(payload['s'])
                contact = contacts_keyring.lookup_by_signing_fingerprint(payload['f'])
                if contact:
                    try:
                        signing_pub = self.import_public_key_pem(contact['signing_key_pem'])
                        self.verify(signing_pub, sig_raw, ciphertext)
                        result['verified'] = True
                        result['signer']   = contact.get('label', '')
                    except Exception:
                        result['verified'] = False

        return result
