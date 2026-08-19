"""SIMULATION of `sgit publish` (P2 — not built yet), per the spec in
team/explorer/dev/impl-plans/08/17/static-publishing/ (01 §3-4, 07 §2).

Real parts   : key derivation, ref/index naming, commit decryption + parent walk
               (sgit_ai's own Vault__Crypto / Vault__Commit / Vault__Object_Store),
               ciphertext byte-copies, sha256 hashing.
Simulated    : the folder assembly itself, and the loader index.html (a clearly
               marked placeholder for the Web team's bundled template).

Usage: simulate_publish.py <vault_dir> [--visibility bare|public]
"""
import hashlib
import json
import os
import shutil                                    # noqa: kept for rmtree
import sys

from sgit_ai.crypto.Vault__Crypto            import Vault__Crypto
from sgit_ai.crypto.PKI__Crypto              import PKI__Crypto
from sgit_ai.storage.Vault__Object_Store     import Vault__Object_Store
from sgit_ai.storage.Vault__Commit           import Vault__Commit
from sgit_ai.storage.Vault__Ref_Manager      import Vault__Ref_Manager

LOADER_TEMPLATE = """<!doctype html>
<!-- sgit loader — SIMULATED placeholder for the bundled template (invariant I4).
     Real template is authored by the Web team; byte-identical across every vault. -->
<title>Encrypted vault</title>
<script>
// 1. key from #fragment, else glob sgit_public_read_*, else stored, else ask (01 §6)
// 2. classify_key by declaration; REFUSE sgit_private_vault_*
// 3. HMAC(read_key) -> ref file id; GET api/vault/read/{vault_id}/... ; decrypt in-page
</script>
<body>sgit vault loader (placeholder)</body>
"""


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main(vault_dir: str, visibility: str = 'bare') -> None:
    sg_dir    = os.path.join(vault_dir, '.sg_vault')
    bare_dir  = os.path.join(sg_dir, 'bare')
    out_dir   = os.path.join(sg_dir, 'publish')
    vault_key = open(os.path.join(sg_dir, 'local', 'vault_key')).read().strip()

    crypto = Vault__Crypto()
    keys   = crypto.derive_keys_from_vault_key(vault_key)
    vault_id       = str(keys['vault_id'])
    read_key       = str(keys['read_key'])
    read_key_bytes = keys['read_key_bytes']
    ref_file_id    = str(keys['ref_file_id'])

    # --- ordered commit list: head ref -> parent walk (REAL decryption) --------
    obj_store = Vault__Object_Store(vault_path=sg_dir, crypto=crypto)
    ref_mgr   = Vault__Ref_Manager(vault_path=sg_dir, crypto=crypto)
    vc        = Vault__Commit(crypto=crypto, pki=PKI__Crypto(),
                              object_store=obj_store, ref_manager=ref_mgr)
    head      = ref_mgr.read_ref(ref_file_id, read_key_bytes)
    commits, cid = [], head
    while cid:
        commits.append(cid)
        commit = vc.load_commit(cid, read_key_bytes)
        parents = [str(p) for p in (commit.parents or []) if str(p)]
        cid = parents[0] if parents else None

    # --- assemble the folder (SIMULATED assembly, spec 07 §2, r9) --------------
    # r9: the store is NOT copied. The manifest enumerates it (ids, sizes, sha256);
    # the deployer composes the served root (or serve routes to bare/ virtually).
    if os.path.isdir(out_dir):
        shutil.rmtree(out_dir)
    os.makedirs(out_dir)
    objects = []
    for root, _dirs, files in os.walk(bare_dir):
        for fname in sorted(files):
            src = os.path.join(root, fname)
            rel = os.path.relpath(src, sg_dir)                 # bare/refs/...
            with open(src, 'rb') as f:
                data = f.read()
            objects.append({'file_id': rel.replace(os.sep, '/'),
                            'size': len(data), 'sha256': sha256(data)})

    plaintext = {}
    plaintext['index.html'] = LOADER_TEMPLATE.encode()
    plaintext['cover.json'] = json.dumps({
        'title': 'ACME Employee Handbook', 'description': 'Published sgit vault',
        'access': 'ir@acme.example', 'public': visibility == 'public'},
        indent=2).encode()
    if visibility == 'public':
        plaintext[f'sgit_public_read_{read_key}'] = b''

    surface = [{'path': p, 'sha256': sha256(b) if b else sha256(b'')}
               for p, b in plaintext.items()]
    surface.append({'path': 'manifest.json', 'sha256': None})

    manifest = {'schema': 'sgit_published_v1', 'vault_id': vault_id,
                'generated_by': 'sgit v0.15.1 (publish SIMULATED)',
                'layout': 'api-path', 'visibility': visibility,
                'head': head, 'commits': commits,
                'plaintext_surface': surface, 'objects': objects}
    plaintext['manifest.json'] = json.dumps(manifest, indent=2).encode()

    for path, data in plaintext.items():
        with open(os.path.join(out_dir, path), 'wb') as f:
            f.write(data)
    with open(os.path.join(out_dir, '.gitignore'), 'w') as f:                # 07 §4
        f.write('*\n')

    print(f'Publishing vault {vault_id} -> .sg_vault/publish/')
    print(f'  Store (referenced)   {len(objects)} objects — enumerated, NOT copied (r9)')
    print(f'  Commits (head first) {commits}')
    print(f'  Plaintext surface    {len(plaintext) + 0}   '
          f'{", ".join(sorted(plaintext))}')
    print(f'  Visibility           {visibility}')


if __name__ == '__main__':
    vis = 'public' if '--visibility=public' in sys.argv or 'public' in sys.argv else 'bare'
    main(sys.argv[1], vis)
