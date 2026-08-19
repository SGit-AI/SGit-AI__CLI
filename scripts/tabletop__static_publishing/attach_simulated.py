"""SIMULATION of `sgit vault attach` (P9 — not built), per the acceptance criteria in
05__implementation-phases.md. Binds a key to an EXISTING .sg_vault/bare checkout
(e.g. a fresh `git clone` of a one-repo vault, which has bare/ but no local/).

Real parts: key parsing/derivation and the validation that the derived ref file id
exists in bare/refs (sgit's own Vault__Crypto). Simulated: writing local/.

Usage:
  attach_simulated.py <dir> --vault-key <sgit_private_vault_...:vid>  --base-url U --token T
  attach_simulated.py <dir> --read-key  <hex|sgit_*_read_...> --vault-id <vid> [--base-url U --token T]
"""
import argparse
import json
import os
import sys

from sgit_ai.crypto.Vault__Crypto import Vault__Crypto


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('directory')
    ap.add_argument('--vault-key')
    ap.add_argument('--read-key')
    ap.add_argument('--vault-id')
    ap.add_argument('--base-url', default='')
    ap.add_argument('--token', default='')
    a = ap.parse_args()

    sg_dir   = os.path.join(a.directory, '.sg_vault')
    refs_dir = os.path.join(sg_dir, 'bare', 'refs')
    if not os.path.isdir(refs_dir):
        print(f'error: {sg_dir} has no bare/refs — not a vault checkout'); return 1

    crypto = Vault__Crypto()
    if a.vault_key:
        keys = crypto.derive_keys_from_vault_key(a.vault_key)
        mode = 'read-write'
    elif a.read_key and a.vault_id:
        keys = crypto.import_read_key(a.read_key, a.vault_id)
        mode = 'read-only'
    else:
        print('error: need --vault-key, or --read-key + --vault-id'); return 1

    ref_file_id = str(keys['ref_file_id'])
    if not os.path.isfile(os.path.join(refs_dir, ref_file_id)):        # P9: validate FIRST
        print(f'error: derived ref {ref_file_id} not found in bare/refs — wrong key '
              f'for this store. Nothing written.'); return 1

    local = os.path.join(sg_dir, 'local')
    os.makedirs(local, exist_ok=True)
    # P9 acceptance (found live): attach is MODE-EXCLUSIVE — remove the other
    # mode's artifacts, or the shipped clone-mode guard refuses to open the vault.
    for stale in ('clone_mode.json', 'vault_key'):
        path = os.path.join(local, stale)
        if os.path.isfile(path):
            os.remove(path)
    if mode == 'read-write':
        with open(os.path.join(local, 'vault_key'), 'w') as f:
            f.write(a.vault_key)
    else:
        with open(os.path.join(local, 'clone_mode.json'), 'w') as f:
            json.dump({'mode': 'read-only', 'vault_id': str(keys['vault_id']),
                       'read_key': str(keys['read_key']),
                       'branch_name': 'current'}, f, indent=2)   # exact Schema__Clone_Mode shape
    with open(os.path.join(local, 'config.json'), 'w') as f:
        json.dump({'my_branch_id': None,
                   'mode': 'read_only' if mode == 'read-only' else None,   # rw mode is null in Schema__Local_Config
                   'sparse': False}, f)
    if a.base_url:
        open(os.path.join(local, 'base_url'), 'w').write(a.base_url)
    if a.token:
        open(os.path.join(local, 'token'), 'w').write(a.token)
    print(f'attached ({mode}): vault {keys["vault_id"]}  ref {ref_file_id} verified in bare/refs')
    return 0


if __name__ == '__main__':
    sys.exit(main())
