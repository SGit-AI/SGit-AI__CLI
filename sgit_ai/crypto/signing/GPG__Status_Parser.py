"""GPG__Status_Parser — gpg's `[GNUPG:]` status lines, read as Git's gpg-interface.c
reads them (design__02 §5.7.2; transcripts captured from gpg 2.4 in the tests).

Only lines starting exactly with `[GNUPG:] ` count; gpg escapes newlines in user ids
(%0A), so a user id cannot forge a status line. A second exclusive status (two
signatures) is an error, as in Git."""
import re
from   osbot_utils.type_safe.Type_Safe              import Type_Safe

PREFIX    = '[GNUPG:] '
EXCLUSIVE = {'GOODSIG': 'G', 'BADSIG': 'B', 'ERRSIG': 'E', 'EXPSIG': 'X', 'EXPKEYSIG': 'Y', 'REVKEYSIG': 'R'}
ALGORITHMS = {'1': 'RSA', '2': 'RSA', '3': 'RSA', '16': 'ELGAMAL', '17': 'DSA', '18': 'ECDH', '19': 'ECDSA',
              '22': 'EDDSA', '27': 'ED25519', '28': 'ED448'}


class GPG__Status_Parser(Type_Safe):

    def parse(self, status: bytes) -> dict:
        found = dict(letter='', key_id='', uid='', fingerprint='', primary_fingerprint='', trust='', algorithm='')
        seen  = 0
        for raw in status.decode('utf-8', 'replace').split('\n'):
            if not raw.startswith(PREFIX):
                continue
            word, _, rest = raw[len(PREFIX):].rstrip('\r').partition(' ')
            if word in EXCLUSIVE:
                seen += 1
                if seen > 1:
                    return dict(found, letter='E', uid='', reason='more than one signature')
                found['letter'] = EXCLUSIVE[word]
                key_id, _, uid  = rest.partition(' ')
                found['key_id'] = key_id
                if word != 'ERRSIG':
                    found['uid'] = self.unescape(uid)
            elif word == 'VALIDSIG':
                fields = rest.split(' ')
                found['fingerprint']         = fields[0]
                found['algorithm']           = ALGORITHMS.get(fields[6], f'ALGO-{fields[6]}') if len(fields) > 6 else ''
                found['primary_fingerprint'] = fields[9] if len(fields) > 9 else fields[0]
            elif word.startswith('TRUST_'):
                found['trust'] = word[len('TRUST_'):].lower()
        return found

    def unescape(self, text: str) -> str:
        text = re.sub(r'%([0-9A-Fa-f]{2})', lambda m: chr(int(m.group(1), 16)), text)
        return ''.join(ch for ch in text if ch >= ' ' and ch != '\x7f')
