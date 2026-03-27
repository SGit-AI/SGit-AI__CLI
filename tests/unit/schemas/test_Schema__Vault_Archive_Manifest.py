import time
from osbot_utils.type_safe.primitives.domains.identifiers.safe_int.Timestamp_Now import Timestamp_Now
from sgit_ai.schemas.Schema__Vault_Archive_Manifest import (
    Schema__Vault_Archive_Manifest, VAULT_ARCHIVE_SCHEMA_VERSION
)
from sgit_ai.schemas.Schema__Archive_Provenance import Schema__Archive_Provenance


class Test_Schema__Vault_Archive_Manifest:

    def test_create_with_defaults(self):
        m = Schema__Vault_Archive_Manifest()
        assert m.schema         is None
        assert m.vault_id       is None
        assert m.created_at     is None
        assert m.files          == 0
        assert m.total_bytes    == 0
        assert m.inner_key_type is None
        assert m.inner_key_id   is None
        assert m.description    is None
        assert m.provenance     is None

    def test_schema_version_constant(self):
        assert VAULT_ARCHIVE_SCHEMA_VERSION == 'vault_archive_v1'

    def test_created_at_uses_milliseconds(self):
        # Timestamp_Now stores milliseconds — must be > 1e12
        ts = Timestamp_Now()
        assert int(ts) > 1_000_000_000_000
        # Seconds (time.time()) would be < 2e10
        assert int(time.time()) < 2_000_000_000

    def test_created_at_is_not_seconds(self):
        # seconds would be around 1.7e9, milliseconds around 1.7e12
        ts = Timestamp_Now()
        assert int(ts) > int(time.time()) * 100

    def test_create_with_values(self):
        ts = Timestamp_Now()
        m  = Schema__Vault_Archive_Manifest(
            schema         = 'vault_archive_v1',
            vault_id       = 'abcd1234',
            created_at     = ts,
            files          = 12,
            total_bytes    = 49459,
            inner_key_type = 'vault_key',
            inner_key_id   = 'abcd1234',
            description    = 'test archive',
        )
        assert m.schema         == 'vault_archive_v1'
        assert m.vault_id       == 'abcd1234'
        assert int(m.created_at) == int(ts)
        assert m.files          == 12
        assert m.total_bytes    == 49459
        assert m.inner_key_type == 'vault_key'

    def test_round_trip_empty(self):
        m = Schema__Vault_Archive_Manifest()
        assert Schema__Vault_Archive_Manifest.from_json(m.json()).json() == m.json()

    def test_round_trip_with_values(self):
        ts = Timestamp_Now()
        m  = Schema__Vault_Archive_Manifest(
            schema         = 'vault_archive_v1',
            vault_id       = 'abcd1234',
            created_at     = ts,
            files          = 5,
            total_bytes    = 1024,
            inner_key_type = 'vault_key',
            inner_key_id   = 'abcd1234',
        )
        j = m.json()
        assert Schema__Vault_Archive_Manifest.from_json(j).json() == j

    def test_round_trip_with_provenance(self):
        ts = Timestamp_Now()
        p  = Schema__Archive_Provenance(
            branch_id = 'branch-clone-abcd1234ef56',
            commit_id = 'obj-cas-imm-abcdef012345',
        )
        m  = Schema__Vault_Archive_Manifest(
            schema         = 'vault_archive_v1',
            vault_id       = 'abcd1234',
            created_at     = ts,
            files          = 3,
            total_bytes    = 512,
            inner_key_type = 'none',
            provenance     = p,
        )
        j = m.json()
        assert Schema__Vault_Archive_Manifest.from_json(j).json() == j

    def test_created_at_in_json_is_milliseconds(self):
        before_ms = int(time.time() * 1000)
        ts        = Timestamp_Now()
        after_ms  = int(time.time() * 1000)
        m         = Schema__Vault_Archive_Manifest(created_at=ts)
        j         = m.json()
        assert before_ms <= j['created_at'] <= after_ms + 1

    def test_inner_key_type_none_mode(self):
        m = Schema__Vault_Archive_Manifest(inner_key_type='none')
        assert m.inner_key_type == 'none'

    def test_inner_key_type_pki_mode(self):
        m = Schema__Vault_Archive_Manifest(inner_key_type='pki')
        assert m.inner_key_type == 'pki'
