"""SPIKE — measure the per-commit bundle proposal (08/17 static-clone round).

Not shipped code: a measurement harness backing
team/explorer/architect/reviews/08/17/v0.1__addendum__per-commit-bundles-measured.md
Run: python scripts/spike__measure_commit_bundles.py

Fork under test:
  SNAPSHOT bundle = every object reachable from commit N (self-contained)
  DELTA    bundle = only objects commit N introduces (union of all = full store)

Questions answered with numbers:
  1. how much do snapshot bundles duplicate?
  2. does the union of deltas + metadata rebuild bare/ exactly?
  3. what does an incremental pull cost under each scheme?
"""
import os, shutil, sys, tempfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from sgit_ai.core.Vault__Sync import Vault__Sync
from sgit_ai.crypto.Vault__Crypto import Vault__Crypto
from sgit_ai.crypto.PKI__Crypto import PKI__Crypto
from sgit_ai.network.api.Vault__API__In_Memory import Vault__API__In_Memory
from sgit_ai.storage.Vault__Object_Store import Vault__Object_Store
from sgit_ai.storage.Vault__Commit import Vault__Commit
from sgit_ai.storage.Vault__Ref_Manager import Vault__Ref_Manager


def reachable(vc, obj_store, read_key, commit_id, seen_trees=None):
    """All object ids reachable from a commit: the commit, its trees, its blobs."""
    ids = set()
    commit = vc.load_commit(commit_id, read_key)
    ids.add(commit_id)
    stack = [str(commit.tree_id)]
    while stack:
        tid = stack.pop()
        if tid in ids:
            continue
        ids.add(tid)
        try:
            tree = vc.load_tree(tid, read_key)
        except Exception:
            continue
        for e in tree.entries:
            if getattr(e, 'blob_id', None):
                ids.add(str(e.blob_id))
            if getattr(e, 'tree_id', None):
                stack.append(str(e.tree_id))
    return ids, commit


def main(n_commits=10, files_per_commit=20, file_size=800):
    tmp = tempfile.mkdtemp(prefix='bundles_')
    try:
        api  = Vault__API__In_Memory().setup()
        sync = Vault__Sync(crypto=Vault__Crypto(), api=api)
        origin = os.path.join(tmp, 'origin')
        r = sync.init(origin)

        commit_ids = []
        for c in range(n_commits):
            for i in range(files_per_commit):
                p = Path(origin, f'docs/s{i%5}/file{c*files_per_commit+i}.md')
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text('x'*file_size + f'\n{c}-{i}')
            # also MODIFY one existing file each round (realistic churn)
            Path(origin, 'CHANGELOG.md').write_text('entry ' * (c+1))
            res = sync.commit(origin, f'commit {c}')
            commit_ids.append(res['commit_id'])
        sync.push(origin)

        keys      = Vault__Crypto().derive_keys_from_vault_key(r['vault_key'])
        read_key  = keys['read_key_bytes']
        sg_dir    = os.path.join(origin, '.sg_vault')
        obj_store = Vault__Object_Store(vault_path=sg_dir, crypto=Vault__Crypto())
        vc        = Vault__Commit(crypto=Vault__Crypto(), pki=PKI__Crypto(),
                                  object_store=obj_store,
                                  ref_manager=Vault__Ref_Manager(vault_path=sg_dir,
                                                                 crypto=Vault__Crypto()))

        def size_of(ids):
            t = 0
            for i in ids:
                p = os.path.join(sg_dir, 'bare', 'data', i)
                if os.path.isfile(p):
                    t += os.path.getsize(p)
            return t

        # snapshots (oldest -> newest) and deltas
        snapshots, deltas, seen = [], [], set()
        for cid in commit_ids:
            ids, _commit = reachable(vc, obj_store, read_key, cid)
            snapshots.append(ids)
            deltas.append(ids - seen)
            seen |= ids

        on_disk = set(os.listdir(os.path.join(sg_dir, 'bare', 'data')))
        union   = set().union(*deltas)

        print(f'vault: {n_commits} commits x {files_per_commit} files ({file_size}B) + churn')
        print(f'  objects in bare/data      : {len(on_disk)}   ({size_of(on_disk)/1024:.0f} KB)')
        print(f'  union of per-commit deltas: {len(union)}   ({size_of(union)/1024:.0f} KB)')
        print(f'  deltas reconstruct store  : {union == on_disk}'
              f'{"" if union == on_disk else "  MISSING: " + str(len(on_disk - union))}')
        print()
        snap_total  = sum(size_of(s) for s in snapshots)
        delta_total = sum(size_of(d) for d in deltas)
        print(f'  SNAPSHOT bundles total    : {snap_total/1024:>8.0f} KB  '
              f'({snap_total/max(size_of(on_disk),1):.1f}x the store — duplication)')
        print(f'  DELTA    bundles total    : {delta_total/1024:>8.0f} KB  '
              f'({delta_total/max(size_of(on_disk),1):.1f}x the store)')
        print(f'  single full pack          : {size_of(on_disk)/1024:>8.0f} KB')
        print()
        print(f'  head snapshot alone       : {size_of(snapshots[-1])/1024:>8.0f} KB '
              f'({len(snapshots[-1])} objects) <- all a "latest only" reader needs')
        print()
        print('  incremental pull, 2 new commits arrive:')
        print(f'    per-commit deltas       : {(size_of(deltas[-1])+size_of(deltas[-2]))/1024:>8.0f} KB (2 GETs, rest cached)')
        print(f'    single full pack        : {size_of(on_disk)/1024:>8.0f} KB (whole pack re-downloaded)')
        print()
        print(f'  metadata NOT in any commit bundle (refs/indexes/keys):')
        for sub in ('refs', 'indexes', 'keys'):
            d = os.path.join(sg_dir, 'bare', sub)
            n = len(os.listdir(d)) if os.path.isdir(d) else 0
            b = sum(os.path.getsize(os.path.join(d, f)) for f in os.listdir(d)) if n else 0
            print(f'    bare/{sub:<8}: {n} files, {b} bytes')
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == '__main__':
    main()
