#!/usr/bin/env python3
"""Recover access to a legacy Simple-Token vault (April-2026 era).

WHY THIS EXISTS
    The Simple Token scheme was removed from sgit in v0.15.0 (security: a
    ~30-bit token is recoverable from public data in ~0.1s on a GPU). Removing
    the CODE did not make the DATA unrecoverable: the token -> keys derivation
    is pure maths, and everything downstream of the read key is unchanged in
    the current CLI. This script reproduces that derivation exactly, as
    recovered from git history (commit 5e62605^,
    sgit_ai/crypto/simple_token/Simple_Token.py), and probes the server to
    report whether the data actually survives.

    Use it on vaults YOU OWN, to get your data out into a modern vault. It
    deliberately lives in scripts/ and NOT in sgit_ai/ — the CLI must not
    regain simple-token support.

THE TRAP THIS SCRIPT AVOIDS
    `sgit clone <token>:<vault_id>` looks like it should work, and it did on
    pre-0.15 CLIs (which detected the token in the passphrase slot and ignored
    the vault_id). On a current CLI that string is parsed as an ordinary
    {passphrase}:{vault_id} vault key and PBKDF2s into a COMPLETELY DIFFERENT
    read key — so it always fails with "no branch index / no named ref",
    whether or not the data is there. That is a false negative, not proof of
    a dead vault. Use the read-key clone this script prints instead.

USAGE
    python scripts/recover_legacy_simple_token_vault.py <token> [--base-url URL] [--probe]

    --probe needs an access token in SG_SEND_ACCESS_TOKEN (or --token).
"""
import argparse
import hashlib
import json
import os
import sys
import urllib.error
import urllib.request

from cryptography.hazmat.primitives          import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

# --- the legacy constants, verbatim from the deleted Simple_Token class -----
PBKDF2_SALT       = b'sgraph-send-v1'
PBKDF2_ITERATIONS = 600_000
PBKDF2_KEY_LEN    = 32

DEFAULT_BASE_URL  = 'https://dev.send.sgraph.ai'


class Legacy_Simple_Token:
    """Exact reproduction of the removed Simple_Token derivation."""

    def __init__(self, token: str):
        self.token = token

    def transfer_id(self) -> str:                     # also served as the vault_id
        return hashlib.sha256(self.token.encode('utf-8')).hexdigest()[:12]

    def aes_key(self) -> bytes:
        return hashlib.pbkdf2_hmac('sha256', self.token.encode('utf-8'),
                                   PBKDF2_SALT, PBKDF2_ITERATIONS,
                                   dklen=PBKDF2_KEY_LEN)

    def _hkdf(self, info: bytes) -> bytes:
        return HKDF(algorithm=hashes.SHA256(), length=32,
                    salt=None, info=info).derive(self.aes_key())

    def read_key(self)  -> bytes: return self._hkdf(b'vault-read-key')
    def write_key(self) -> bytes: return self._hkdf(b'vault-write-key')
    def ec_seed(self)   -> bytes: return self._hkdf(b'vault-ec-seed')


REF_DOMAIN          = 'sg-vault-v1:file-id:ref'
BRANCH_INDEX_DOMAIN = 'sg-vault-v1:file-id:branch-index'


def derive_file_ids(read_key: bytes, vault_id: str) -> dict:
    """The ref / branch-index locators.

    Inlined (rather than imported) so this script runs standalone from a bare
    checkout during a recovery. It is byte-identical to the current CLI's
    Vault__Crypto.derive_ref_file_id / derive_branch_index_file_id — which is
    exactly why a modern read-key clone can still open a legacy vault. The
    --self-check flag asserts that equivalence when sgit_ai is importable.
    """
    import hmac

    def file_id(domain: str) -> str:
        return hmac.new(read_key, f'{domain}:{vault_id}'.encode(),
                        hashlib.sha256).hexdigest()[:12]

    return dict(ref_file_id          = 'ref-pid-muw-' + file_id(REF_DOMAIN),
                branch_index_file_id = 'idx-pid-muw-' + file_id(BRANCH_INDEX_DOMAIN))


def self_check(read_key: bytes, vault_id: str, ids: dict) -> str:
    """Assert the inlined derivation still matches the installed CLI."""
    try:
        from sgit_ai.crypto.Vault__Crypto import Vault__Crypto
    except ImportError:
        return 'skipped (sgit_ai not importable)'
    crypto = Vault__Crypto()
    expect = dict(ref_file_id          = 'ref-pid-muw-' + crypto.derive_ref_file_id(read_key, vault_id),
                  branch_index_file_id = 'idx-pid-muw-' + crypto.derive_branch_index_file_id(read_key, vault_id))
    return 'OK — matches the installed CLI' if expect == ids else f'MISMATCH! cli={expect} script={ids}'


def http_get(url: str, token: str = None, timeout: int = 30) -> tuple:
    req = urllib.request.Request(url)
    if token:
        req.add_header('x-sgraph-access-token', token)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except Exception as e:                                   # network/DNS/TLS
        return -1, str(e).encode()


def probe(base_url: str, token: str, vault_id: str, ids: dict) -> dict:
    """Is the data actually there? Checks BOTH surfaces a legacy token could use:
    the vault object store, and the transfers API (a token could address either)."""
    out = {}
    status, body = http_get(f'{base_url}/api/vault/list/{vault_id}', token)
    files = None
    if status == 200:
        try:
            files = json.loads(body).get('files', [])
        except Exception:
            pass
    out['vault_list']      = dict(status=status, file_count=(len(files) if files is not None else None))
    out['vault_files']     = files[:10] if files else []
    for label, fid in (('ref', ids['ref_file_id']), ('index', ids['branch_index_file_id'])):
        sub = 'refs' if label == 'ref' else 'indexes'
        st, _ = http_get(f'{base_url}/api/vault/read/{vault_id}/bare/{sub}/{fid}', token)
        out[f'{label}_status'] = st
    st, body = http_get(f'{base_url}/api/transfers/info/{vault_id}', token)
    out['transfer_info'] = dict(status=st, body=body[:200].decode('utf-8', 'replace'))
    return out


def analyse(token: str, args) -> dict:
    """Derive everything for one token, optionally probing the server."""
    st       = Legacy_Simple_Token(token)
    vault_id = st.transfer_id()
    read_key = st.read_key()
    ids      = derive_file_ids(read_key, vault_id)

    result = dict(token      = token,
                  vault_id   = vault_id,
                  read_key   = read_key.hex(),
                  write_key  = st.write_key().hex(),
                  aes_key    = st.aes_key().hex(),
                  **ids)
    if args.self_check:
        result['self_check'] = self_check(read_key, vault_id, ids)
    if args.probe:
        result['probe'] = probe(args.base_url, args.access_token, vault_id, ids)
        pr = result['probe']
        result['alive'] = (pr['vault_list']['file_count'] or 0) > 0 or pr['ref_status'] == 200
    return result


def run_batch(tokens: list, args) -> int:
    """Re-probe a whole registry in one pass. Prints a verdict table."""
    results = [analyse(t, args) for t in tokens]
    if args.json:
        print(json.dumps(results, indent=2))
    else:
        print(f'{"token":<22} {"vault_id":<14} {"files":>6}  verdict')
        print('-' * 62)
        for r in results:
            if args.probe:
                n       = r['probe']['vault_list']['file_count']
                verdict = 'DATA PRESENT' if r['alive'] else 'no data'
                print(f'{r["token"]:<22} {r["vault_id"]:<14} {str(n):>6}  {verdict}')
            else:
                print(f'{r["token"]:<22} {r["vault_id"]:<14} {"-":>6}  (no probe)')
        if args.probe:
            alive = [r for r in results if r['alive']]
            print()
            print(f'{len(alive)}/{len(results)} vault(s) still hold data.')
            for r in alive:
                print(f'  sgit clone {r["read_key"]}:{r["vault_id"]} recovered-{r["vault_id"]} \\')
                print(f'      --base-url {args.base_url} --token $SG_SEND_ACCESS_TOKEN')
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description='Recover keys for legacy Simple-Token vault(s)')
    p.add_argument('tokens',       nargs='*',
                   help='legacy simple token(s), e.g. make-dose-3967. Omit to read from --tokens-file or stdin.')
    p.add_argument('--tokens-file', help='file with one token per line (# comments allowed)')
    p.add_argument('--base-url',   default=os.environ.get('SGIT_BASE_URL', DEFAULT_BASE_URL))
    p.add_argument('--token',      dest='access_token',
                   default=os.environ.get('SG_SEND_ACCESS_TOKEN'),
                   help='SG/Send access token (or set SG_SEND_ACCESS_TOKEN)')
    p.add_argument('--probe',      action='store_true', help='ask the server whether the data survives')
    p.add_argument('--json',       action='store_true', help='machine-readable output')
    p.add_argument('--self-check', action='store_true',
                   help='verify the inlined derivation still matches the installed CLI')
    args = p.parse_args()

    tokens = list(args.tokens)
    if args.tokens_file:
        with open(args.tokens_file) as f:
            tokens += [ln.strip() for ln in f
                       if ln.strip() and not ln.strip().startswith('#')]
    if not tokens and not sys.stdin.isatty():
        tokens += [ln.strip() for ln in sys.stdin
                   if ln.strip() and not ln.strip().startswith('#')]
    if not tokens:
        p.error('no tokens given (pass them as arguments, --tokens-file, or on stdin)')

    if args.probe and not args.access_token:
        print('error: --probe needs an access token (SG_SEND_ACCESS_TOKEN or --token)',
              file=sys.stderr)
        return 2

    if len(tokens) > 1:
        return run_batch(tokens, args)

    result   = analyse(tokens[0], args)
    vault_id = result['vault_id']
    ids      = dict(ref_file_id=result['ref_file_id'],
                    branch_index_file_id=result['branch_index_file_id'])

    if args.json:
        print(json.dumps(result, indent=2))
        return 0

    print(f'Legacy simple token : {result["token"]}')
    print(f'  vault_id          : {vault_id}          (sha256(token)[:12])')
    print(f'  read_key          : {result["read_key"]}')
    print(f'  write_key         : {result["write_key"]}')
    print(f'  ref file_id       : bare/refs/{ids["ref_file_id"]}')
    print(f'  index file_id     : bare/indexes/{ids["branch_index_file_id"]}')
    if args.self_check:
        print(f'  self-check        : {result["self_check"]}')
    print()
    print('Recover with (works on the CURRENT CLI — read-only clone):')
    print(f'  sgit clone {result["read_key"]}:{vault_id} recovered-{vault_id} \\')
    print(f'      --base-url {args.base_url} --token $SG_SEND_ACCESS_TOKEN')
    print()
    print('Do NOT use `sgit clone <token>:<vault_id>` — on a current CLI that derives')
    print('a different key and fails even when the data is present (false negative).')

    if args.probe:
        pr = result['probe']
        print()
        print(f'Probe against {args.base_url}:')
        print(f'  vault list      : http={pr["vault_list"]["status"]} files={pr["vault_list"]["file_count"]}')
        print(f'  ref object      : http={pr["ref_status"]}')
        print(f'  index object    : http={pr["index_status"]}')
        print(f'  transfers/info  : http={pr["transfer_info"]["status"]} {pr["transfer_info"]["body"]}')
        alive = result['alive']
        print()
        print('  VERDICT: DATA PRESENT — run the clone above.' if alive else
              '  VERDICT: NO DATA at this endpoint. The keys above are correct, so if the\n'
              '           objects exist on another endpoint or in an S3 backup, they will\n'
              '           open with them. Nothing is recoverable from the token alone.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
