"""Tests for Schema__Local_Config — current 3-field schema (my_branch_id, mode, sparse).

Covers:
  - Default construction (all fields at default)
  - Construction with fields
  - Field types (Safe_Str__Branch_Id, Enum__Local_Config_Mode, bool)
  - Round-trip invariant: from_json(obj.json()).json() == obj.json()
  - Loose-on-read: legacy single-field files (only my_branch_id) still load correctly
  - Extra fields are dropped on load (allowlist / M8 pattern)
  - json.dump compatibility (the serialised form is directly writable)
"""
import json

from sgit_ai.schemas.Schema__Local_Config       import Schema__Local_Config
from sgit_ai.safe_types.Enum__Local_Config_Mode import Enum__Local_Config_Mode


BRANCH_ID   = 'branch-clone-abcdef0123456789'


class Test_Schema__Local_Config:

    def test_default_construction(self):
        config = Schema__Local_Config()
        assert config.my_branch_id is None
        assert config.mode         is None
        assert config.sparse       is False

    def test_construction_with_branch_id_only(self):
        config = Schema__Local_Config(my_branch_id=BRANCH_ID)
        assert str(config.my_branch_id) == BRANCH_ID
        assert config.mode              is None
        assert config.sparse            is False

    def test_construction_full(self):
        config = Schema__Local_Config(
            my_branch_id = BRANCH_ID,
            mode         = Enum__Local_Config_Mode.READ_ONLY,
            sparse       = True,
        )
        assert str(config.my_branch_id) == BRANCH_ID
        assert config.mode              == Enum__Local_Config_Mode.READ_ONLY
        assert config.sparse            is True

    def test_field_types(self):
        config = Schema__Local_Config(my_branch_id=BRANCH_ID)
        assert type(config.my_branch_id).__name__ == 'Safe_Str__Branch_Id'

    def test_enum_serialises_as_value_string(self):
        config = Schema__Local_Config(mode=Enum__Local_Config_Mode.READ_ONLY)
        assert config.json()['mode'] == 'read_only'

    def test_round_trip_default(self):
        config    = Schema__Local_Config()
        restored  = Schema__Local_Config.from_json(config.json())
        assert restored.json() == config.json()

    def test_round_trip_branch_id_only(self):
        config   = Schema__Local_Config(my_branch_id=BRANCH_ID)
        restored = Schema__Local_Config.from_json(config.json())
        assert restored.json() == config.json()

    def test_round_trip_full(self):
        config = Schema__Local_Config(
            my_branch_id = BRANCH_ID,
            mode         = Enum__Local_Config_Mode.READ_ONLY,
            sparse       = True,
        )
        restored = Schema__Local_Config.from_json(config.json())
        assert restored.json() == config.json()
        assert restored.mode   == Enum__Local_Config_Mode.READ_ONLY
        assert restored.sparse is True

    def test_loose_on_read__legacy_file(self):
        """Legacy local_config.json with only my_branch_id must load without error."""
        legacy = {'my_branch_id': BRANCH_ID}
        config = Schema__Local_Config.from_json(legacy)
        assert str(config.my_branch_id) == BRANCH_ID
        assert config.mode              is None
        assert config.sparse            is False

    def test_extra_fields_dropped_on_load(self):
        """Unknown extra fields are silently dropped (allowlist / loose-on-read)."""
        raw = {
            'my_branch_id': BRANCH_ID,
            'mode':         'read_only',
            'sparse':       True,
            'share_token':  'injected',
            'unknown':      42,
        }
        config = Schema__Local_Config.from_json(raw)
        assert not hasattr(config, 'share_token')
        assert not hasattr(config, 'unknown')
        assert str(config.my_branch_id) == BRANCH_ID
        assert config.sparse            is True

    def test_extra_fields_not_written_on_save(self):
        """Round-trip through json() never re-introduces extra fields."""
        raw = {
            'my_branch_id': BRANCH_ID,
            'share_token':  'injected',
        }
        serialised = Schema__Local_Config.from_json(raw).json()
        assert 'share_token' not in serialised

    def test_json_dump_compatible(self):
        """json.json() output can be directly passed to json.dump()."""
        config = Schema__Local_Config(
            my_branch_id = BRANCH_ID,
            mode         = Enum__Local_Config_Mode.READ_ONLY,
            sparse       = True,
        )
        dumped   = json.dumps(config.json())
        reloaded = json.loads(dumped)
        assert reloaded['mode']       == 'read_only'
        assert reloaded['sparse']     is True

    def test_sparse_false_not_omitted(self):
        """sparse=False is serialised as False, not omitted — full round-trip contract."""
        config = Schema__Local_Config(my_branch_id=BRANCH_ID)
        data   = config.json()
        assert 'sparse' in data
        assert data['sparse'] is False


class Test_Schema__Local_Config__ReadOnly:
    """Architect contract §3.3 / §7.1 — READ_ONLY mode with my_branch_id=None."""

    def test_read_only_member_exists(self):
        assert Enum__Local_Config_Mode.READ_ONLY.value == 'read_only'

    def test_construction_read_only(self):
        config = Schema__Local_Config(my_branch_id = None,
                                      mode         = Enum__Local_Config_Mode.READ_ONLY,
                                      sparse       = False)
        assert config.my_branch_id is None
        assert config.mode         == Enum__Local_Config_Mode.READ_ONLY
        assert config.sparse       is False

    def test_read_only_serialises_as_value_string(self):
        config = Schema__Local_Config(mode=Enum__Local_Config_Mode.READ_ONLY)
        assert config.json()['mode'] == 'read_only'

    def test_round_trip_read_only_my_branch_id_none(self):
        """from_json(obj.json()).json() == obj.json() with mode=READ_ONLY, my_branch_id=None."""
        config   = Schema__Local_Config(my_branch_id = None,
                                        mode         = Enum__Local_Config_Mode.READ_ONLY,
                                        sparse       = False)
        restored = Schema__Local_Config.from_json(config.json())
        assert restored.json()      == config.json()
        assert restored.mode        == Enum__Local_Config_Mode.READ_ONLY
        assert restored.my_branch_id is None

    def test_round_trip_read_only_sparse_true(self):
        config   = Schema__Local_Config(my_branch_id = None,
                                        mode         = Enum__Local_Config_Mode.READ_ONLY,
                                        sparse       = True)
        restored = Schema__Local_Config.from_json(config.json())
        assert restored.json() == config.json()
        assert restored.sparse is True

    def test_on_disk_shape_matches_clone_step_output(self):
        """The exact dict the RO clone step writes loads back to a READ_ONLY config."""
        raw    = {'my_branch_id': None, 'mode': 'read_only', 'sparse': False}
        config = Schema__Local_Config.from_json(raw)
        assert config.mode         == Enum__Local_Config_Mode.READ_ONLY
        assert config.my_branch_id is None
        assert config.json()       == raw
