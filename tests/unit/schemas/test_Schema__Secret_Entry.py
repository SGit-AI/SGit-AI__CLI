from sgit_ai.schemas.Schema__Secret_Entry import Schema__Secret_Entry


class Test_Schema__Secret_Entry:

    def test_create_with_fields(self):
        # created_at accepts ISO strings on input and stores as Timestamp_Now (int ms).
        entry = Schema__Secret_Entry(key='my-secret', created_at='2026-03-10T12:00:00Z')
        assert str(entry.key)     == 'my-secret'
        assert int(entry.created_at) == 1773144000000   # 2026-03-10T12:00:00Z in ms

    def test_round_trip_json(self):
        entry    = Schema__Secret_Entry(key='api-key', created_at='2026-03-10T12:00:00Z')
        as_json  = entry.json()
        restored = Schema__Secret_Entry.from_json(as_json)
        assert restored.json() == as_json

    def test_legacy_iso_load(self):
        # Pre-migration data on disk used ISO strings. They must still load cleanly.
        entry = Schema__Secret_Entry.from_json({'key': 'k', 'created_at': '2026-03-10T12:00:00Z'})
        assert int(entry.created_at) == 1773144000000
