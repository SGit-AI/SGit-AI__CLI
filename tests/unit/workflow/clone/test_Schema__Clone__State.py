"""Tests for Schema__Clone__State — accumulating state for Workflow__Clone."""
import pytest

from sgit_ai.schemas.workflow.clone.Schema__Clone__State  import Schema__Clone__State
from sgit_ai.safe_types.Safe_Str__Vault_Key               import Safe_Str__Vault_Key
from sgit_ai.safe_types.Safe_Str__File_Path               import Safe_Str__File_Path
from sgit_ai.safe_types.Safe_Str__Vault_Id                import Safe_Str__Vault_Id
from sgit_ai.safe_types.Safe_Str__Commit_Id               import Safe_Str__Commit_Id
from sgit_ai.safe_types.Safe_Str__Write_Key               import Safe_Str__Write_Key


class Test_Schema__Clone__State:

    def test_round_trip_invariant_empty(self):
        s = Schema__Clone__State()
        assert Schema__Clone__State.from_json(s.json()).json() == s.json()

    def test_round_trip_invariant_with_values(self):
        s = Schema__Clone__State(
            vault_key       = Safe_Str__Vault_Key('pass:abcd1234'),
            directory       = Safe_Str__File_Path('/tmp/clone'),
            sparse          = True,
        )
        assert Schema__Clone__State.from_json(s.json()).json() == s.json()

    def test_initial_fields_are_none(self):
        s = Schema__Clone__State()
        assert s.vault_key       is None
        assert s.directory       is None
        assert s.vault_id        is None
        assert s.named_commit_id is None
        assert s.sg_dir          is None
        assert s.clone_branch_id is None

    def test_sparse_defaults_false(self):
        s = Schema__Clone__State()
        assert s.sparse is False

    def test_root_tree_ids_defaults_empty_list(self):
        s = Schema__Clone__State()
        assert s.root_tree_ids == []

    def test_commit_id_preserves_dashes(self):
        """Regression: Safe_Str__Commit_Id must not replace dashes with underscores."""
        cid = Safe_Str__Commit_Id('obj-cas-imm-ffbb5a290065')
        assert str(cid) == 'obj-cas-imm-ffbb5a290065'

    def test_from_json_preserves_commit_id_dashes(self):
        data = Schema__Clone__State().json()
        data['named_commit_id'] = 'obj-cas-imm-aabb11223344'
        s = Schema__Clone__State.from_json(data)
        assert str(s.named_commit_id) == 'obj-cas-imm-aabb11223344'

    def test_round_trip_with_commit_id(self):
        data = Schema__Clone__State().json()
        data['named_commit_id'] = 'obj-cas-imm-aabb11223344'
        s    = Schema__Clone__State.from_json(data)
        s2   = Schema__Clone__State.from_json(s.json())
        assert str(s2.named_commit_id) == 'obj-cas-imm-aabb11223344'

    def test_numeric_timing_fields_default_zero(self):
        s = Schema__Clone__State()
        assert s.n_commits    is None
        assert s.t_commits_ms is None
        assert s.n_blobs      is None
