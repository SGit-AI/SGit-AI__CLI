import hashlib
from osbot_utils.type_safe.Type_Safe             import Type_Safe
from sgit_ai.safe_types.Safe_Str__Simple_Token   import Safe_Str__Simple_Token
from sgit_ai.safe_types.Safe_Str__Transfer_Id    import Safe_Str__Transfer_Id

PBKDF2_SALT       = b'sgraph-send-v1'
PBKDF2_ITERATIONS = 600000
PBKDF2_KEY_LEN    = 32


class Simple_Token(Type_Safe):
    token : Safe_Str__Simple_Token = None

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
