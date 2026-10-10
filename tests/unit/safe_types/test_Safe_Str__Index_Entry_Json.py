import json

import pytest

from sgit_ai.safe_types.Safe_Str__Index_Entry_Json import Safe_Str__Index_Entry_Json
from sgit_ai.schemas.Schema__Branch_Index          import Schema__Branch_Index


class Test_Safe_Str__Index_Entry_Json:

    def test_keeps_canonical_json_exactly(self):
        text = json.dumps({'name': 'not a name!', 'x': [1, 'é'], 'z': None}, sort_keys=True,
                          separators=(',', ':'), ensure_ascii=True)
        assert str(Safe_Str__Index_Entry_Json(text)) == text

    def test_refuses_non_ascii_and_control_characters(self):
        for bad in ('{"name":"é"}', '{"a":1}\n', '\x00'):
            with pytest.raises(ValueError):
                Safe_Str__Index_Entry_Json(bad)

    def test_refuses_empty(self):
        with pytest.raises(ValueError):
            Safe_Str__Index_Entry_Json('')

    def test_branch_index_round_trip_with_carried_entries(self):
        obj = Schema__Branch_Index.from_json(dict(schema='branch_index_v1', branches=[], tags=[],
                                                  carried_tags=['{"name":"bad;tombstone"}']))
        assert Schema__Branch_Index.from_json(obj.json()).json() == obj.json()
