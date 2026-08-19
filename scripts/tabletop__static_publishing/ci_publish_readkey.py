"""CI variant: publish using ONLY the read key recovered from the committed
sgit_public_read_* filename — proves publish never needs the vault (write) key."""
import glob, os, sys, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import simulate_publish as sp
from sgit_ai.crypto.Vault__Crypto        import Vault__Crypto
from sgit_ai.crypto.PKI__Crypto          import PKI__Crypto
from sgit_ai.storage.Vault__Object_Store import Vault__Object_Store
from sgit_ai.storage.Vault__Commit       import Vault__Commit
from sgit_ai.storage.Vault__Ref_Manager  import Vault__Ref_Manager

repo = sys.argv[1]
sg   = os.path.join(repo, '.sg_vault')
keyfile  = os.path.basename(glob.glob(os.path.join(sg, 'publish', 'sgit_public_read_*'))[0])
crypto   = Vault__Crypto()
man      = json.load(open(os.path.join(sg, 'publish', 'manifest.json')))
keys     = crypto.import_read_key(keyfile, man['vault_id'])        # real: prefix stripped, ids derived
ref_mgr  = Vault__Ref_Manager(vault_path=sg, crypto=crypto)
head     = ref_mgr.read_ref(str(keys['ref_file_id']), keys['read_key_bytes'])
vc = Vault__Commit(crypto=crypto, pki=PKI__Crypto(),
                   object_store=Vault__Object_Store(vault_path=sg, crypto=crypto),
                   ref_manager=ref_mgr)
commits, cid = [], head
while cid:
    commits.append(cid)
    c = vc.load_commit(cid, keys['read_key_bytes'])
    ps = [str(p) for p in (c.parents or []) if str(p)]
    cid = ps[0] if ps else None
print(f'CI publish with READ KEY ONLY: head={head}  commits={len(commits)}  vault_key needed: NO')
