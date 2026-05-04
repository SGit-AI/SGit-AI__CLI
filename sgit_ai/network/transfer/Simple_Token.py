import hashlib
import re
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives          import hashes
from osbot_utils.type_safe.Type_Safe             import Type_Safe
from sgit_ai.safe_types.Safe_Str__Simple_Token   import Safe_Str__Simple_Token
from sgit_ai.safe_types.Safe_Str__Transfer_Id    import Safe_Str__Transfer_Id

PBKDF2_SALT       = b'sgraph-send-v1'
PBKDF2_ITERATIONS = 600000
PBKDF2_KEY_LEN    = 32

SIMPLE_TOKEN_PATTERN = re.compile(r'^[a-z]+-[a-z]+-\d{4}$')


class Simple_Token(Type_Safe):
    token : Safe_Str__Simple_Token = None

    @classmethod
    def is_simple_token(cls, s: str) -> bool:
        if not isinstance(s, str):
            return False
        return bool(SIMPLE_TOKEN_PATTERN.match(s))

    def transfer_id(self) -> str:
        token_str = str(self.token)
        digest    = hashlib.sha256(token_str.encode('utf-8')).hexdigest()
        return digest[:12]

    def aes_key(self) -> bytes:
        token_str = str(self.token)
        return hashlib.pbkdf2_hmac('sha256',
                                   token_str.encode('utf-8'),
                                   PBKDF2_SALT,
                                   PBKDF2_ITERATIONS,
                                   dklen=PBKDF2_KEY_LEN)

    def aes_key_hex(self) -> str:
        return self.aes_key().hex()

    def read_key(self) -> bytes:
        hkdf = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=b'vault-read-key')
        return hkdf.derive(self.aes_key())

    def write_key(self) -> bytes:
        hkdf = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=b'vault-write-key')
        return hkdf.derive(self.aes_key())

    def ec_seed(self) -> bytes:
        hkdf = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=b'vault-ec-seed')
        return hkdf.derive(self.aes_key())

    def vault_id(self) -> str:
        return str(self.token)
