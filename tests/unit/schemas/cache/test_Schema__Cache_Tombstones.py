from sgit_ai.schemas.cache.Schema__Cache_Tombstones import (Schema__Cache_Tombstone,
                                                            Schema__Cache_Tombstones)
from sgit_ai.safe_types.Enum__Cache_Kind             import Enum__Cache_Kind


class Test_Schema__Cache_Tombstone:

    def test_round_trip(self):
        t = Schema__Cache_Tombstone(kind     = Enum__Cache_Kind.POINTER,
                                    cache_id = 'cch-pid-snw-aabbccddeeff',
                                    path     = 'media/photos')
        assert Schema__Cache_Tombstone.from_json(t.json()).json() == t.json()

    def test_defaults(self):
        t = Schema__Cache_Tombstone()
        assert t.kind == Enum__Cache_Kind.VALUE
        assert t.cache_id is None


class Test_Schema__Cache_Tombstones:

    def test_round_trip_with_entries(self):
        ts = Schema__Cache_Tombstones()
        ts.removed.append(Schema__Cache_Tombstone(kind     = Enum__Cache_Kind.VALUE,
                                                  cache_id = 'cch-pid-snw-001122334455',
                                                  path     = 'keys/api.json'))
        ts.removed.append(Schema__Cache_Tombstone(kind     = Enum__Cache_Kind.POINTER,
                                                  cache_id = 'cch-pid-snw-556677889900',
                                                  path     = 'media'))
        assert Schema__Cache_Tombstones.from_json(ts.json()).json() == ts.json()
        assert len(ts.removed) == 2

    def test_empty_round_trip(self):
        ts = Schema__Cache_Tombstones()
        assert Schema__Cache_Tombstones.from_json(ts.json()).json() == ts.json()
        assert ts.removed == []
