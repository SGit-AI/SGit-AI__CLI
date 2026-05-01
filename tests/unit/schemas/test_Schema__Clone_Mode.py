# Tests for Schema__Clone_Mode — Type_Safe schema for clone_mode.json.
import json

from sgit_ai.schemas.Schema__Clone_Mode  import Schema__Clone_Mode
from sgit_ai.safe_types.Enum__Clone_Mode import Enum__Clone_Mode

VAULT_ID    = 'testvaultcm1'
READ_KEY_HEX = 'a' * 64   # 64 hex chars — valid Safe_Str__Write_Key value


class Test_Schema__Clone_Mode:

    def test_default_construction(self):
        cm = Schema__Clone_Mode()
        assert cm.mode     is None
        assert cm.vault_id is None
        assert cm.read_key is None

    def test_construction_with_read_only_values(self):
        cm = Schema__Clone_Mode(mode=Enum__Clone_Mode.READ_ONLY,
                                vault_id=VAULT_ID, read_key=READ_KEY_HEX)
        assert cm.mode               == Enum__Clone_Mode.READ_ONLY
        assert str(cm.vault_id)      == VAULT_ID
        assert str(cm.read_key)      == READ_KEY_HEX

    def test_field_types(self):
        cm = Schema__Clone_Mode(mode=Enum__Clone_Mode.READ_ONLY,
                                vault_id=VAULT_ID, read_key=READ_KEY_HEX)
        assert type(cm.vault_id).__name__ == 'Safe_Str__Vault_Id'
        assert type(cm.read_key).__name__ == 'Safe_Str__Write_Key'
        assert type(cm.mode).__name__     == 'Enum__Clone_Mode'

    def test_mode_serializes_as_string(self):
        """Enum field is stored as its string value in the JSON dict."""
        cm   = Schema__Clone_Mode(mode=Enum__Clone_Mode.READ_ONLY,
                                  vault_id=VAULT_ID, read_key=READ_KEY_HEX)
        d    = cm.json()
        assert d['mode'] == 'read-only'
        assert type(d['mode']) is str

    def test_round_trip_empty(self):
        cm       = Schema__Clone_Mode()
        restored = Schema__Clone_Mode.from_json(cm.json())
        assert restored.json() == cm.json()

    def test_round_trip_read_only(self):
        cm = Schema__Clone_Mode(mode=Enum__Clone_Mode.READ_ONLY,
                                vault_id=VAULT_ID, read_key=READ_KEY_HEX)
        restored = Schema__Clone_Mode.from_json(cm.json())
        assert restored.json()            == cm.json()
        assert restored.mode              == Enum__Clone_Mode.READ_ONLY
        assert str(restored.vault_id)     == VAULT_ID
        assert str(restored.read_key)     == READ_KEY_HEX

    def test_round_trip_invariant(self):
        """from_json(obj.json()).json() == obj.json() — the Type_Safe contract."""
        cm = Schema__Clone_Mode(mode=Enum__Clone_Mode.READ_ONLY,
                                vault_id=VAULT_ID, read_key=READ_KEY_HEX)
        assert Schema__Clone_Mode.from_json(cm.json()).json() == cm.json()

    def test_from_json_dict_matches_on_disk_shape(self):
        """Schema loads correctly from the exact dict shape written to clone_mode.json."""
        raw = {
            'mode':     'read-only',
            'vault_id': VAULT_ID,
            'read_key': READ_KEY_HEX,
        }
        cm = Schema__Clone_Mode.from_json(raw)
        assert cm.mode           == Enum__Clone_Mode.READ_ONLY
        assert str(cm.vault_id)  == VAULT_ID
        assert str(cm.read_key)  == READ_KEY_HEX

    def test_json_dump_compatible(self):
        """clone_mode.json() can be safely passed to json.dump."""
        cm  = Schema__Clone_Mode(mode=Enum__Clone_Mode.READ_ONLY,
                                 vault_id=VAULT_ID, read_key=READ_KEY_HEX)
        out = json.dumps(cm.json(), indent=2)
        reloaded = json.loads(out)
        assert reloaded['mode']     == 'read-only'
        assert reloaded['vault_id'] == VAULT_ID
        assert reloaded['read_key'] == READ_KEY_HEX

    # -- Loose-on-read / strict-on-write (M8 clone_mode closer) --------------

    def test_extra_field_dropped_on_load(self):
        """Unknown extra fields in clone_mode.json are silently dropped."""
        raw = {
            'mode':     'read-only',
            'vault_id': VAULT_ID,
            'read_key': READ_KEY_HEX,
            'paths':    {'secret.txt': 'obj-cas-imm-aabbccdd1122'},  # injected
            'malicious': True,
        }
        cm = Schema__Clone_Mode.from_json(raw)
        assert not hasattr(cm, 'paths')
        assert not hasattr(cm, 'malicious')

    def test_extra_field_not_written_on_save(self):
        """An injected extra field cannot survive a write-then-read round trip (M8 close)."""
        raw = {
            'mode':     'read-only',
            'vault_id': VAULT_ID,
            'read_key': READ_KEY_HEX,
            'paths':    {'secret.txt': 'blob_id'},
        }
        cm         = Schema__Clone_Mode.from_json(raw)
        serialised = cm.json()
        assert 'paths' not in serialised
        assert 'paths' not in json.loads(json.dumps(serialised))
