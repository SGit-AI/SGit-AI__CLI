# Tests for Schema__Push_State — Type_Safe schema for push_state.json.
import json

from sgit_ai.schemas.Schema__Push_State  import Schema__Push_State
from sgit_ai.safe_types.Safe_Str__Object_Id import Safe_Str__Object_Id


VAULT_ID       = 'testvault001'
COMMIT_ID      = 'obj-cas-imm-aabb11223344'
BLOB_ID_1      = 'obj-cas-imm-aabbccdd1122'
BLOB_ID_2      = 'obj-cas-imm-112233445566'


class Test_Schema__Push_State:

    def test_default_construction(self):
        state = Schema__Push_State()
        assert state.vault_id        is None
        assert state.clone_commit_id is None
        assert state.blobs_uploaded  == []

    def test_construction_with_values(self):
        state = Schema__Push_State(vault_id=VAULT_ID, clone_commit_id=COMMIT_ID)
        assert str(state.vault_id)        == VAULT_ID
        assert str(state.clone_commit_id) == COMMIT_ID
        assert state.blobs_uploaded       == []

    def test_field_types(self):
        state = Schema__Push_State(vault_id=VAULT_ID, clone_commit_id=COMMIT_ID)
        assert type(state.vault_id).__name__        == 'Safe_Str__Vault_Id'
        assert type(state.clone_commit_id).__name__ == 'Safe_Str__Object_Id'

    def test_blobs_uploaded_list(self):
        state = Schema__Push_State()
        state.blobs_uploaded.append(Safe_Str__Object_Id(BLOB_ID_1))
        state.blobs_uploaded.append(Safe_Str__Object_Id(BLOB_ID_2))
        assert len(state.blobs_uploaded) == 2
        assert str(state.blobs_uploaded[0]) == BLOB_ID_1

    def test_round_trip_empty(self):
        state    = Schema__Push_State()
        restored = Schema__Push_State.from_json(state.json())
        assert restored.json() == state.json()

    def test_round_trip_with_values(self):
        state = Schema__Push_State(vault_id=VAULT_ID, clone_commit_id=COMMIT_ID)
        state.blobs_uploaded.append(Safe_Str__Object_Id(BLOB_ID_1))
        restored = Schema__Push_State.from_json(state.json())
        assert restored.json()                        == state.json()
        assert str(restored.vault_id)                 == VAULT_ID
        assert str(restored.clone_commit_id)          == COMMIT_ID
        assert str(restored.blobs_uploaded[0])        == BLOB_ID_1

    def test_round_trip_multiple_blobs(self):
        state = Schema__Push_State(vault_id=VAULT_ID, clone_commit_id=COMMIT_ID)
        for blob_id in [BLOB_ID_1, BLOB_ID_2]:
            state.blobs_uploaded.append(Safe_Str__Object_Id(blob_id))
        restored = Schema__Push_State.from_json(state.json())
        assert len(restored.blobs_uploaded) == 2
        assert restored.json()              == state.json()

    def test_from_json_dict(self):
        """Schema loads correctly from the exact dict shape written to push_state.json."""
        raw = {
            'vault_id':        VAULT_ID,
            'clone_commit_id': COMMIT_ID,
            'blobs_uploaded':  [BLOB_ID_1, BLOB_ID_2],
        }
        state = Schema__Push_State.from_json(raw)
        assert str(state.vault_id)           == VAULT_ID
        assert str(state.clone_commit_id)    == COMMIT_ID
        assert len(state.blobs_uploaded)     == 2
        assert str(state.blobs_uploaded[0])  == BLOB_ID_1

    # -- M8 closer: extra field injection is dropped by schema allowlist ------

    def test_push_state_only_safe_fields__extra_field_dropped_on_load(self):
        """M8: an injected extra field is silently dropped by the schema on load."""
        raw = {
            'vault_id':        VAULT_ID,
            'clone_commit_id': COMMIT_ID,
            'blobs_uploaded':  [BLOB_ID_1],
            'paths':           {'file.txt': BLOB_ID_1},  # M8 mutation injection
            'malicious':       True,
        }
        state = Schema__Push_State.from_json(raw)
        assert not hasattr(state, 'paths')
        assert not hasattr(state, 'malicious')

    def test_push_state_only_safe_fields__extra_field_not_written_on_save(self):
        """M8: a round-trip through save/load never re-introduces injected fields."""
        raw = {
            'vault_id':        VAULT_ID,
            'clone_commit_id': COMMIT_ID,
            'blobs_uploaded':  [BLOB_ID_1],
            'paths':           {'file.txt': BLOB_ID_1},
        }
        state         = Schema__Push_State.from_json(raw)
        serialised    = state.json()
        assert 'paths' not in serialised
        restored_dict = json.loads(json.dumps(serialised))
        assert 'paths' not in restored_dict

    def test_push_state_round_trip_invariant(self):
        """from_json(obj.json()).json() == obj.json() — the Type_Safe contract."""
        state = Schema__Push_State(vault_id=VAULT_ID, clone_commit_id=COMMIT_ID)
        state.blobs_uploaded.append(Safe_Str__Object_Id(BLOB_ID_1))
        assert Schema__Push_State.from_json(state.json()).json() == state.json()
