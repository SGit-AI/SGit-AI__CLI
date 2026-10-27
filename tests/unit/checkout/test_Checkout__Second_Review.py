"""Second review of 26 Oct (independent review of the fix round): stale bytes a `pull
--no-checkout` left are refreshed by `checkout --since-pull` (R1); a file write that fails
is never recorded, never makes a clone full, and stops a pull before its head moves (R2);
a folder replaced by a file of the same name refuses while the folder still holds a stray
file (R3); a selective pack clone refuses a head whose trees are missing (R4); a rebuilt
checkout record says so (R6); a tree entry without a content hash is compared with its
blob (R9)."""
import os
import shutil

import pytest

from sgit_ai.core.Vault__Errors                import Vault__Dirty_Working_Tree_Error
from sgit_ai.storage.Vault__Checkout_Set       import Vault__Checkout_Set
from tests._helpers.pack_env                   import Pack__Env
from tests._helpers.vault_test_env             import TEST_VAULT_KEY

FILES = {'raw/uk/gov/a.txt': b'a\n', 'raw/uk/gov/b.txt': b'bb\n', 'top.md': b'# top\n'}


@pytest.fixture(params=[True, False], ids=['pack', 'loose'])
def vault(request):
    env = Pack__Env()
    mk  = env.pack_vault if request.param else env.normal_vault
    sync, a, key = mk(dict(FILES), vault_key=TEST_VAULT_KEY)
    return env, sync, a, key


def _push(env, sync, a, files=None, deletes=()):
    for d in deletes:
        p = os.path.join(a, d)
        shutil.rmtree(p) if os.path.isdir(p) else os.remove(p)
    if files:
        env.write(a, files)
    sync.commit(a, message='up'); sync.push(a)


class Test_Checkout__Second_Review:

    def test_since_pull_refreshes_a_checked_out_file_the_no_checkout_pull_left_stale(self, vault):
        env, sync, a, key = vault
        sync_b, b = env.clone(key, 'b', no_checkout=True)
        sync_b.checkout(b, paths=['raw/uk/gov/a.txt'])
        _push(env, sync, a, {'raw/uk/gov/a.txt': b'a2\n'})
        _push(env, sync, a, {'raw/uk/gov/a.txt': b'a3\n'})                      # two pulls' worth behind
        sync_b.pull(b, checkout=False)
        assert env.tree(b)['raw/uk/gov/a.txt'] == b'a\n'
        assert Vault__Checkout_Set().load_stale(b) == {'raw/uk/gov/a.txt': sync_b.crypto.content_hash(b'a\n')}
        r = sync_b.checkout(b, since_pull=True)
        assert r['written'] == ['raw/uk/gov/a.txt'] and r['kept_dirty'] == []
        assert env.tree(b)['raw/uk/gov/a.txt'] == b'a3\n' and sync_b.status(b)['clean']
        assert Vault__Checkout_Set().load_stale(b) == {}

    def test_an_edit_on_top_of_stale_bytes_is_still_kept(self, vault):
        env, sync, a, key = vault
        sync_b, b = env.clone(key, 'b', no_checkout=True)
        sync_b.checkout(b, paths=['raw/uk/gov/a.txt'])
        _push(env, sync, a, {'raw/uk/gov/a.txt': b'a2\n'})
        sync_b.pull(b, checkout=False)
        env.write(b, {'raw/uk/gov/a.txt': b'my edit\n'})
        r = sync_b.checkout(b, since_pull=True)
        assert r['kept_dirty'] == ['raw/uk/gov/a.txt'] and env.tree(b)['raw/uk/gov/a.txt'] == b'my edit\n'

    def test_checkout_all_with_a_file_in_the_way_reports_it_records_nothing_and_stays_selective(self, vault):
        env, sync, a, key = vault
        sync_b, b = env.clone(key, 'b', no_checkout=True)
        env.write(b, {'raw': b'my notes\n'})                                   # a file where a folder goes
        r = sync_b.checkout(b, all_files=True)
        assert r['full'] is False and sorted(r['failed']) == ['raw/uk/gov/a.txt', 'raw/uk/gov/b.txt']
        assert 'raw/uk/gov/a.txt' not in r['written'] and Vault__Checkout_Set().load(b) == {'top.md'}
        st = sync_b.status(b)
        assert st['sparse'] and st['deleted'] == []
        os.remove(os.path.join(b, 'raw'))
        with pytest.raises(RuntimeError, match='nothing to commit'):
            sync_b.commit(b, message='tidy')                                   # nothing reads as deleted
        r = sync_b.checkout(b, all_files=True)
        assert r['full'] and env.tree(b) == FILES

    def test_a_pull_that_cannot_write_a_file_stops_before_its_head_moves_and_a_retry_succeeds(self, vault):
        env, sync, a, key = vault
        sync_b, b = env.clone(key, 'b')
        head_before = sync_b.status(b)['clone_head']
        _push(env, sync, a, {'raw/uk/gov/new/n.txt': b'n\n'})
        env.write(b, {'raw/uk/gov/new': b'a file where the incoming folder goes\n'})   # untracked, in the way
        with pytest.raises(Vault__Dirty_Working_Tree_Error, match='raw/uk/gov/new'):
            sync_b.pull(b)
        assert sync_b.status(b)['clone_head'] == head_before
        os.remove(os.path.join(b, 'raw/uk/gov/new'))
        sync_b.pull(b)
        assert env.tree(b) == env.tree(a) and sync_b.status(b)['clean']

    @pytest.mark.parametrize('stray', ['x/notes.txt', 'x/.DS_Store'])
    def test_a_folder_replaced_by_a_file_refuses_while_the_folder_holds_a_stray_file(self, vault, stray):
        env, sync, a, key = vault
        env.write(a, {'x/y.txt': b'y\n'}); sync.commit(a, message='x'); sync.push(a)
        sync_b, b = env.clone(key, 'b')
        _push(env, sync, a, {'x': b'x is a file now\n'}, deletes=['x'])
        env.write(b, {stray: b'local stray\n'})
        with pytest.raises(Vault__Dirty_Working_Tree_Error, match='a folder stands where the incoming file goes'):
            sync_b.pull(b)
        assert env.tree(b)['x/y.txt'] == b'y\n'                                 # nothing written, nothing deleted
        os.remove(os.path.join(b, stray))
        sync_b.pull(b)
        assert env.tree(b)['x'] == b'x is a file now\n' and sync_b.status(b)['clean']

    def test_a_selective_pack_clone_refuses_a_head_whose_folder_tree_is_missing(self):
        import io, zipfile
        from sgit_ai.core.actions.pack.Vault__Packs import PACK_SNAPSHOTS
        from sgit_ai.storage.Vault__Sub_Tree        import FLAT_CACHE
        env = Pack__Env()
        sync, a, key = env.pack_vault(dict(FILES), vault_key=TEST_VAULT_KEY)
        c   = sync._init_components(a); vid = str(c.vault_id)
        head = sync.status(a)['clone_head']
        from sgit_ai.core.actions.pack.Vault__Pack_Index import Vault__Pack_Index
        tree = Vault__Pack_Index(crypto=sync.crypto, api=env.api).commit_fields(os.path.join(a, '.sg_vault'), head, c.read_key)['tree_id']
        from sgit_ai.storage.Vault__Sub_Tree import Vault__Sub_Tree
        gone = Vault__Sub_Tree(crypto=sync.crypto, obj_store=c.obj_store).flatten_dirs(tree, c.read_key)['raw/uk']
        key_p = next(k for k in env.api._store if k.startswith(f'{vid}/{PACK_SNAPSHOTS}'))
        buf   = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(env.api._store[key_p])) as src, zipfile.ZipFile(buf, 'w') as dst:
            for info in src.infolist():
                if not info.filename.endswith(gone):
                    dst.writestr(info, src.read(info))
        name = key_p.rsplit('/', 1)[-1].split('__')
        env.api._store.pop(key_p)
        env.api._store[f'{vid}/{PACK_SNAPSHOTS}{name[0]}__{name[1]}__{len(buf.getvalue())}.zip'] = buf.getvalue()
        FLAT_CACHE.clear()
        with pytest.raises(Exception, match='not in the local store'):
            env.clone(key, 'n', no_checkout=True)

    def test_a_rebuilt_record_says_so(self, capsys):
        env = Pack__Env()
        sync, a, key = env.pack_vault(dict(FILES), vault_key=TEST_VAULT_KEY)
        sync_b, b = env.clone(key, 'b', no_checkout=True)
        sync_b.checkout(b, paths=['top.md'])
        with open(Vault__Checkout_Set().path(b), 'w') as f:
            f.write('{not json')                                               # unreadable, not missing
        st = sync_b.status(b)
        assert st['clean'] and Vault__Checkout_Set().load(b) == {'top.md'}
        assert 'rebuilt from the 1 tracked file(s) on disk' in capsys.readouterr().err


class Test_Checkout__Build_Agent_Round_2:

    def test_a_no_checkout_pack_clone_refuses_a_head_blob_the_packs_did_not_bring(self):
        """N1: with the tree walk skipped, a selective pack clone checked nothing; a pack with
        a refused blob let it finish and the next checkout found the gap."""
        import io, zipfile
        from sgit_ai.core.actions.pack.Vault__Packs import PACK_SNAPSHOTS
        from sgit_ai.storage.Vault__Sub_Tree        import FLAT_CACHE
        env = Pack__Env()
        sync, a, key = env.pack_vault(dict(FILES), vault_key=TEST_VAULT_KEY)
        c    = sync._init_components(a); vid = str(c.vault_id)
        blob = sync._get_head_flat_map(a)[0]['top.md']['blob_id']
        key_p = next(k for k in env.api._store if k.startswith(f'{vid}/{PACK_SNAPSHOTS}'))
        buf   = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(env.api._store[key_p])) as src, zipfile.ZipFile(buf, 'w') as dst:
            for info in src.infolist():
                if not info.filename.endswith(blob):
                    dst.writestr(info, src.read(info))
        name = key_p.rsplit('/', 1)[-1].split('__')
        env.api._store.pop(key_p)
        env.api._store[f'{vid}/{PACK_SNAPSHOTS}{name[0]}__{name[1]}__{len(buf.getvalue())}.zip'] = buf.getvalue()
        FLAT_CACHE.clear()
        with pytest.raises(Exception, match='clone incomplete.*top.md'):
            env.clone(key, 'n', no_checkout=True)
