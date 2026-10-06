"""Step 4b — fetch every object in the store in one parallel sweep (full clones).

A full clone wants every object reachable from the named branch: all commits,
all trees, all blobs. The walks that follow discover those one dependency at
a time — a commit's parents are inside its ciphertext, a tree's children
inside its — so a 600-commit history is 300+ serial round trips before a
single tree is known, and the tree levels are serial too. On the DC vault
(621 commits, 8,013 trees, 9,356 blobs) that was 57 s of commits, 60 s of
trees and 46 s of blobs: ~170 s, past the per-command timeout of the agents
that clone it.

The server can list the store in one call (18,684 ids in ~11 s there), and
ids need no dependency order to download: so list once, fetch everything not
yet local in parallel chunks, verify-before-write as always, and let the
walks run against a store that already has what they ask for. The walks are
unchanged and still fetch anything missing, so a truncated or failed listing
(a static host without a manifest, an older server) only costs speed, never
correctness. Sparse clones skip this: they must not download blobs.

Cost: the listing may include objects unreachable from the named branch
(other branches, abandoned work) — on that vault ~4 %. Content-addressed and
harmless; fsck ignores unreachable objects.
"""
import time
from   concurrent.futures                                    import ThreadPoolExecutor
from   sgit_ai.safe_types.Safe_Str__Step_Name                import Safe_Str__Step_Name
from   sgit_ai.schemas.workflow.clone.Schema__Clone__State   import Schema__Clone__State
from   sgit_ai.workflow.Step                                 import Step

BULK_CHUNK   = 50          # ids per batch request (MAX_BATCH_OPS)
BULK_WORKERS = 16          # parallel batch requests


class Step__Clone__Bulk_Fetch(Step):
    name          = Safe_Str__Step_Name('bulk-fetch')
    input_schema  = Schema__Clone__State
    output_schema = Schema__Clone__State

    def execute(self, input: Schema__Clone__State, workspace) -> Schema__Clone__State:
        data = input.json()
        if input.sparse:
            return Schema__Clone__State.from_json(data)
        vault_id = str(input.vault_id)
        sg_dir   = str(input.sg_dir)
        read_key = bytes.fromhex(str(input.read_key_hex))
        workspace.ensure_managers(sg_dir)

        t0  = time.monotonic()
        ids = self.list_object_ids(workspace, vault_id)
        if ids is None:
            workspace.progress('step', 'Store listing unavailable — objects will be fetched as the walk discovers them')
            return Schema__Clone__State.from_json(data)

        wanted = [oid for oid in ids if not workspace.obj_store.exists(oid)]
        total  = len(wanted)
        workspace.progress('step', 'Listed vault store', f'{len(ids)} objects, {total} to fetch')
        fetched = self.fetch_all(workspace, vault_id, sg_dir, read_key, wanted)
        workspace.progress('step', 'Bulk fetch done',
                           f'{fetched}/{total} objects in {time.monotonic() - t0:.1f}s')
        data['n_bulk_fetched'] = fetched
        return Schema__Clone__State.from_json(data)

    def list_object_ids(self, workspace, vault_id: str):
        """Every obj-cas-imm-* id the server lists under bare/data/, or None
        when this transport cannot list (or the call failed)."""
        try:
            files = workspace.sync_client.api.list_files(vault_id, 'bare/data/')
        except Exception as error:
            workspace.progress('warn', f'store listing failed: {str(error)[:120]}')
            return None
        ids = []
        for fid in files or []:
            name = str(fid).rsplit('/', 1)[-1]
            if name.startswith('obj-cas-imm-'):
                ids.append(name)
        return ids

    def fetch_all(self, workspace, vault_id: str, sg_dir: str, read_key: bytes, ids: list) -> int:
        if not ids:
            return 0
        chunks  = [ids[i:i + BULK_CHUNK] for i in range(0, len(ids), BULK_CHUNK)]
        total   = len(ids)
        done    = [0]
        fetched = [0]
        api     = workspace.sync_client.api
        workspace.progress('download', 'Downloading objects', f'0/{total}')

        def fetch_chunk(chunk):
            got = api.batch_read(vault_id, [f'bare/data/{oid}' for oid in chunk])
            n   = 0
            for fid, blob in got.items():
                if blob and workspace.save_file(sg_dir, fid, blob, read_key):
                    n += 1
            fetched[0] += n
            done[0]    += len(chunk)
            workspace.progress('download', 'Downloading objects', f'{done[0]}/{total}')

        with ThreadPoolExecutor(max_workers=min(BULK_WORKERS, len(chunks))) as executor:
            for future in [executor.submit(fetch_chunk, c) for c in chunks]:
                future.result()
        return fetched[0]
