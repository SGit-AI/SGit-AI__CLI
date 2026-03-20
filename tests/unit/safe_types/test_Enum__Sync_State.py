from sgit_ai.safe_types.Enum__Sync_State import Enum__Sync_State


class Test_Enum__Sync_State:

    def test_all_states_exist(self):
        expected = ['SYNCED', 'MODIFIED_LOCALLY', 'MODIFIED_REMOTELY', 'CONFLICT',
                    'ADDED_LOCALLY', 'ADDED_REMOTELY', 'DELETED_LOCALLY', 'DELETED_REMOTELY']
        actual   = [s.name for s in Enum__Sync_State]
        assert actual == expected

    def test_state_count(self):
        assert len(Enum__Sync_State) == 8

    def test_value_access(self):
        assert Enum__Sync_State.SYNCED.value            == 'synced'
        assert Enum__Sync_State.MODIFIED_LOCALLY.value   == 'modified_locally'
        assert Enum__Sync_State.CONFLICT.value           == 'conflict'

    def test_from_value(self):
        state = Enum__Sync_State('synced')
        assert state == Enum__Sync_State.SYNCED
