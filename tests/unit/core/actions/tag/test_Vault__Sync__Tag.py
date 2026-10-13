"""Tests for Vault__Sync__Tag — the edges of named, signed release pointers: unknown and
invalid names, read-only clones, offline refresh, objects the host lost or swapped,
signatures that do not verify, and merges the entry does not win. Two real clones over
the in-memory host; the happy path lives in tests/unit/review/test_Tags_Reflog_Lease.py."""
import base64
import json
import os
import time

import pytest

from tests._helpers.vault_test_env                  import Vault__Test_Env
from sgit_ai.core.actions.tag.Vault__Sync__Tag      import Vault__Sync__Tag, BAD, MISSING, NO_KEY, UNSIGNED, VERIFIED
from sgit_ai.core.actions.index.Vault__Index_Sync   import Vault__Index_Sync
from sgit_ai.core.Vault__Errors                     import Vault__Tag_Error
from sgit_ai.core.Vault__Sync                       import Vault__Sync
from sgit_ai.network.api.Vault__API                 import Vault__API
from sgit_ai.schemas.Schema__Branch_Index           import Schema__Branch_Index
from sgit_ai.schemas.Schema__Object_Tag             import Schema__Object_Tag
from sgit_ai.schemas.Schema__Tag_Ref                import Schema__Tag_Ref


def _write(d, rel, content):
    full = os.path.join(d, rel); os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, 'w') as f: f.write(content)


class Test_Vault__Sync__Tag:
    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env(); cls._env.setup_two_clones(files={'a.txt': 'a v1'})

    @classmethod
    def teardown_class(cls):
        if cls._env: cls._env.cleanup_snapshot()

    def setup_method(self):
        self.env   = self._env.restore(); self.sync = self.env.sync; self.api = self.env.api
        self.alice = self.env.alice_dir; self.bob = self.env.bob_dir
        self.tags  = Vault__Sync__Tag(crypto=self.env.crypto, api=self.api)
        self.c     = self.sync._init_components(self.alice); self.vid = str(self.c.vault_id)
        self.index_key = f'{self.vid}/bare/indexes/{self.c.branch_index_file_id}'

    def teardown_method(self):
        self.env.cleanup()

    # ── helpers ─────────────────────────────────────────────────────────
    def _push(self, d, files, message='m'):
        for rel, content in files.items(): _write(d, rel, content)
        self.sync.commit(d, message=message); return self.sync.push(d)

    def _server_index(self):
        return Schema__Branch_Index.from_json(json.loads(self.env.crypto.decrypt(self.c.read_key, self.api._store[self.index_key])))

    def _put_server_index(self, index):
        self.api._store[self.index_key] = Vault__Index_Sync(crypto=self.env.crypto).encrypt(index, self.c.read_key)

    def _offline(self) -> Vault__Sync:
        return Vault__Sync(crypto=self.env.crypto, api=Vault__API(base_url='http://127.0.0.1:9'))

    def _object_key(self, tag_id: str) -> str:
        return f'{self.vid}/bare/data/{tag_id}'

    def _forget_locally(self, d, tag_id: str) -> None:
        os.remove(os.path.join(d, '.sg_vault', 'bare', 'data', tag_id))

    def _store_forged_tag(self, tag: Schema__Object_Tag) -> str:
        """Encrypt a tag object under the read key, store it on the host and in Alice's
        object store, and point an index entry for tag.name at it. Returns the tag id."""
        ciphertext = self.env.crypto.encrypt(self.c.read_key, json.dumps(tag.json()).encode())
        tag_id     = self.c.obj_store.store(ciphertext)
        self.api._store[self._object_key(tag_id)] = ciphertext
        entry = Schema__Tag_Ref(name=str(tag.name), tag_id=tag_id, timestamp_ms=int(tag.timestamp_ms), deleted=False)
        self.tags._write_entry(self.c, self.alice, entry)
        return tag_id

    # ── show / resolve / exists on names that are not tags ──────────────
    def test_show_unknown_name_raises_by_name(self):
        """show() of a name no live tag has raises Vault__Tag_Error naming it."""
        with pytest.raises(Vault__Tag_Error, match="no tag named 'v9.9'"):
            self.sync.tag_show(self.alice, 'v9.9')

    def test_resolve_of_a_name_that_cannot_be_a_tag_is_empty_not_an_error(self):
        """A string the tag-ref regex rejects (spaces, '..') resolves to '' without touching the vault."""
        assert self.tags.resolve(self.alice, 'not a tag') == ''
        assert self.tags.resolve(self.alice, 'a..b') == ''
        assert self.tags.resolve(self.alice, '') == ''
        assert self.tags.resolve(self.alice, None) == ''

    def test_resolve_and_exists_swallow_a_broken_vault(self):
        """On a directory that is not a vault, resolve() is '' and exists() is False: both are
        lookups other commands fall back from, so they never raise."""
        plain = os.path.join(self.env.tmp_dir, 'plain'); os.makedirs(plain)
        assert self.tags.resolve(plain, 'v1.0') == ''
        assert self.tags.exists(plain, 'v1.0') is False

    def test_exists_is_false_for_an_invalid_name_and_for_an_unknown_one(self):
        assert self.tags.exists(self.alice, 'not a tag') is False
        assert self.tags.exists(self.alice, 'v1.0') is False
        self.sync.tag_create(self.alice, 'v1.0', message='m')
        assert self.tags.exists(self.alice, 'v1.0') is True

    def test_resolve_of_a_verified_tag_is_its_commit(self):
        head = self.sync.tag_create(self.alice, 'v1.0', message='m')['commit_id']
        assert self.tags.resolve(self.alice, 'v1.0') == head

    # ── create: refusals ────────────────────────────────────────────────
    def test_invalid_tag_name_is_refused_before_anything_is_read(self):
        with pytest.raises(Vault__Tag_Error, match='is not a valid tag name'):
            self.sync.tag_create(self.alice, '-leading', message='m')

    def test_read_only_clone_cannot_tag(self):
        """A read-only clone has no branch of its own, so nothing to sign with."""
        keys   = self.env.crypto.derive_keys_from_vault_key(self.env.vault_key)
        ro_dir = os.path.join(self.env.tmp_dir, 'ro')
        self.sync.clone_read_only(vault_id=keys['vault_id'], read_key_hex=keys['read_key'], directory=ro_dir)
        with pytest.raises(Vault__Tag_Error, match='a read-only clone cannot tag'):
            self.sync.tag_create(ro_dir, 'v1.0', message='m')

    def test_a_revision_the_clone_does_not_understand_is_a_tag_error(self):
        """Vault__Revision's own message is carried into the Vault__Tag_Error."""
        with pytest.raises(Vault__Tag_Error, match='names no commit this clone has'):
            self.sync.tag_create(self.alice, 'v1.0', commit_id='0' * 12, message='m')

    def test_a_tag_object_id_is_accepted_as_the_commit_to_tag(self):
        """Pins what the code does today: a TAG object's id passes _resolve_commit, because
        Vault__Commit.load_commit decodes any encrypted JSON object into a Schema__Object_Commit
        (schema 'tag_v1', tree_id None) without checking its schema. So `tag create v2.0
        <tag-object-id>` succeeds and v2.0 names an object that is not a commit. The
        'is not a commit this clone has' branch is reached only by an object that is not
        JSON at all (a blob)."""
        self.sync.tag_create(self.alice, 'v1.0', message='m')
        tag_id = self.sync.tag_show(self.alice, 'v1.0')['tag_id']
        r = self.sync.tag_create(self.alice, 'v2.0', commit_id=tag_id, message='m')
        assert r['commit_id'] == tag_id
        blob_id = self.c.obj_store.store(self.env.crypto.encrypt(self.c.read_key, b'plain file bytes'))
        with pytest.raises(Vault__Tag_Error, match='which is a folder listing or a file, not a commit'):
            self.sync.tag_create(self.alice, 'v3.0', commit_id=blob_id, message='m')

    def test_a_commit_the_server_does_not_have_must_be_pushed_first(self):
        """A local, unpushed commit cannot be tagged; and a host that cannot be reached
        counts as 'not on the server' (the check never raises)."""
        _write(self.alice, 'a.txt', 'a v2'); local = self.sync.commit(self.alice, message='local only')['commit_id']
        with pytest.raises(Vault__Tag_Error, match=f'commit {local} is not on the server yet: push it first'):
            self.sync.tag_create(self.alice, 'v2.0', commit_id=local, message='m')
        with pytest.raises(Vault__Tag_Error, match='is not on the server yet'):
            self._offline().tag_create(self.alice, 'v2.0', message='m')

    def test_a_clone_with_no_head_has_nothing_to_tag(self):
        """When this clone's own head ref is gone there is no default commit: 'nothing to tag'."""
        config = self.sync._read_local_config(self.alice, self.c.storage)
        index  = self.c.branch_manager.load_branch_index(self.alice, self.c.branch_index_file_id, self.c.read_key)
        meta   = self.c.branch_manager.get_branch_by_id(index, str(config.my_branch_id))
        os.remove(self.c.ref_manager._ref_path(str(meta.head_ref_id)))
        with pytest.raises(Vault__Tag_Error, match='nothing to tag: this clone has no commits yet'):
            self.sync.tag_create(self.alice, 'v1.0', message='m')

    def test_missing_private_signing_key_is_a_tag_error_and_writes_nothing(self):
        config = self.sync._read_local_config(self.alice, self.c.storage)
        index  = self.c.branch_manager.load_branch_index(self.alice, self.c.branch_index_file_id, self.c.read_key)
        meta   = self.c.branch_manager.get_branch_by_id(index, str(config.my_branch_id))
        os.remove(os.path.join(self.c.storage.local_dir(self.alice), str(meta.public_key_id) + '.pem'))
        before = dict(self.api._store)
        with pytest.raises(Vault__Tag_Error, match='no private signing key for its branch'):
            self.sync.tag_create(self.alice, 'v1.0', message='m')
        assert self.api._store == before

    def test_existing_tag_whose_object_cannot_load_is_named_by_tag_id(self):
        """'already exists (it names X)': X is the commit when the object loads, else the tag id."""
        tag_id = self.sync.tag_create(self.alice, 'v1.0', message='m')['tag_id']
        self._forget_locally(self.alice, tag_id); self.api._store.pop(self._object_key(tag_id))
        with pytest.raises(Vault__Tag_Error, match=f"tag 'v1.0' already exists \\(it names {tag_id}\\)"):
            self.sync.tag_create(self.alice, 'v1.0', message='again')

    def test_create_loses_to_a_future_dated_tombstone_and_says_so(self):
        """An entry that does not win the index merge is reported from what the index holds,
        never assumed. Here the host holds a tombstone for the name dated an hour ahead
        (inside TAG_CLOCK_SKEW_MS, so it still counts): a fresh create, dated now, loses to it.
        An entry dated beyond the skew horizon would rank lowest and the create would win."""
        tag_id = self.sync.tag_create(self.alice, 'v1.0', message='m')['tag_id']
        self.sync.tag_delete(self.alice, 'v1.0')
        index = self._server_index()
        for t in index.tags:
            if str(t.name) == 'v1.0':
                t.timestamp_ms = int(time.time() * 1000) + 3600 * 1000
        self._put_server_index(index)
        with pytest.raises(Vault__Tag_Error, match="tag 'v1.0' was not changed: another entry for it won the merge"):
            self.sync.tag_create(self.alice, 'v1.0', message='again')

    # ── delete ──────────────────────────────────────────────────────────
    def test_delete_unknown_tag_raises(self):
        with pytest.raises(Vault__Tag_Error, match="no tag named 'ghost'"):
            self.sync.tag_delete(self.alice, 'ghost')

    def test_delete_writes_a_tombstone_dated_after_the_entry(self):
        r = self.sync.tag_create(self.alice, 'v1.0', message='m')
        d = self.sync.tag_delete(self.alice, 'v1.0')
        assert d == dict(name='v1.0', tag_id=r['tag_id'])
        entry = [t for t in self._server_index().tags if str(t.name) == 'v1.0'][0]
        assert entry.deleted is True and str(entry.tag_id) == r['tag_id']
        assert self.sync.tag_list(self.alice) == []

    # ── offline ─────────────────────────────────────────────────────────
    def test_list_and_show_fall_back_to_the_local_index_when_the_host_is_unreachable(self):
        """refresh is best effort: with the host down, list/show use this clone's copy."""
        self.sync.tag_create(self.alice, 'v1.0', message='m')
        offline = self._offline()
        assert [t['name'] for t in offline.tag_list(self.alice)] == ['v1.0']
        assert offline.tag_show(self.alice, 'v1.0')['status'] == VERIFIED

    # ── objects the host lost or swapped ────────────────────────────────
    def test_tag_object_gone_everywhere_lists_as_missing(self):
        """No local copy and the host has nothing: status 'missing', commit '', entry timestamp kept."""
        r = self.sync.tag_create(self.alice, 'v1.0', message='m')
        self._forget_locally(self.alice, r['tag_id']); self.api._store.pop(self._object_key(r['tag_id']))
        t = self.sync.tag_show(self.alice, 'v1.0')
        assert t['status'] == MISSING and t['commit_id'] == '' and t['tagger_key_id'] == '' and t['tag_id'] == r['tag_id']
        assert t['timestamp_ms'] > 0

    def test_tag_object_swapped_by_the_host_is_bad_and_not_stored(self):
        """Bytes that do not match the content address are refused: status 'bad', and the
        local object store keeps no copy of them."""
        r = self.sync.tag_create(self.alice, 'v1.0', message='m')
        self._forget_locally(self.alice, r['tag_id'])
        self.api._store[self._object_key(r['tag_id'])] = self.env.crypto.encrypt(self.c.read_key, b'{"schema":"tag_v1"}')
        assert self.sync.tag_show(self.alice, 'v1.0')['status'] == BAD
        assert not self.c.obj_store.exists(r['tag_id'])
        # resolve(): the refusal is raised inside the try, so it is swallowed to '' (not
        # followed, but also not refused by name as a stored-but-bad signature would be)
        assert self.tags.resolve(self.alice, 'v1.0') == ''

    def test_tag_object_is_fetched_from_the_host_when_this_clone_lacks_it(self):
        """A clone whose object store lacks the tag object fetches it, verifies the content
        address, and keeps it."""
        r = self.sync.tag_create(self.alice, 'v1.0', message='m')
        self._forget_locally(self.alice, r['tag_id'])
        assert self.sync.tag_show(self.alice, 'v1.0')['status'] == VERIFIED
        assert self.c.obj_store.exists(r['tag_id'])

    # ── signatures ──────────────────────────────────────────────────────
    def _real_tag(self, name: str = 'seed') -> Schema__Object_Tag:
        r = self.sync.tag_create(self.alice, name, message='m')
        return self.tags._load_tag(self.c, r['tag_id'])

    def test_unsigned_object_is_unsigned_and_refused_by_resolve(self):
        tag = self._real_tag(); tag.name = 'v1.0'; tag.signature = ''
        self._store_forged_tag(tag)
        assert self.sync.tag_show(self.alice, 'v1.0')['status'] == UNSIGNED
        with pytest.raises(Vault__Tag_Error, match="tag 'v1.0' is unsigned"):
            self.tags.resolve(self.alice, 'v1.0')

    def test_signature_that_does_not_verify_is_bad(self):
        """A signature over other bytes, and one that is not even valid base64/DER, both read 'bad'."""
        tag = self._real_tag(); tag.name = 'v1.0'; tag.message = 'edited after signing'
        self._store_forged_tag(tag)
        assert self.sync.tag_show(self.alice, 'v1.0')['status'] == BAD
        garbage = self._real_tag('seed2'); garbage.name = 'v2.0'; garbage.signature = base64.b64encode(b'not-a-der-signature').decode()
        self._store_forged_tag(garbage)
        assert self.sync.tag_show(self.alice, 'v2.0')['status'] == BAD

    def test_entry_name_that_disagrees_with_the_signed_object_is_bad(self):
        """An index entry 'v2.0' pointing at an object signed for 'seed': bad, so a name cannot be re-pointed."""
        tag = self._real_tag()
        ciphertext = self.env.crypto.encrypt(self.c.read_key, json.dumps(tag.json()).encode())
        tag_id = self.c.obj_store.store(ciphertext); self.api._store[self._object_key(tag_id)] = ciphertext
        self.tags._write_entry(self.c, self.alice, Schema__Tag_Ref(name='v2.0', tag_id=tag_id, timestamp_ms=int(tag.timestamp_ms), deleted=False))
        assert self.sync.tag_show(self.alice, 'v2.0')['status'] == BAD
        assert self.sync.tag_show(self.alice, 'seed')['status'] == VERIFIED

    def test_tagger_key_the_vault_does_not_hold_is_no_key(self):
        tag = self._real_tag(); tag.name = 'v1.0'; tag.tagger_key_id = 'key-' + '0' * 16
        self._store_forged_tag(tag)
        assert self.sync.tag_show(self.alice, 'v1.0')['status'] == NO_KEY

    def test_bob_sees_a_bad_tag_marked_bad_after_pull(self):
        tag = self._real_tag(); tag.name = 'v1.0'; tag.message = 'edited'
        self._store_forged_tag(tag)
        self.sync.pull(self.bob)
        assert {t['name']: t['status'] for t in self.sync.tag_list(self.bob)} == {'seed': VERIFIED, 'v1.0': BAD}
