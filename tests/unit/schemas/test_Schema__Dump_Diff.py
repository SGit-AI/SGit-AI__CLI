from sgit_ai.schemas.Schema__Dump_Diff import Schema__Dump_Diff


class Test_Schema__Dump_Diff:

    def test_defaults(self):
        diff = Schema__Dump_Diff()
        assert diff.refs_only_in_a      == []
        assert diff.refs_only_in_b      == []
        assert diff.refs_diverged       == []
        assert diff.objects_only_in_a   == []
        assert diff.objects_only_in_b   == []
        assert diff.branches_only_in_a  == []
        assert diff.branches_only_in_b  == []
        assert diff.branches_head_differ== []
        assert diff.dangling_in_a       == []
        assert diff.dangling_in_b       == []
        assert diff.commits_only_in_a   == []
        assert diff.commits_only_in_b   == []
        assert int(diff.total_diffs)         == 0
        assert int(diff.refs_diff_count)     == 0
        assert int(diff.objects_diff_count)  == 0
        assert int(diff.branches_diff_count) == 0
        assert diff.identical == False

    def test_round_trip(self):
        diff = Schema__Dump_Diff(
            label_a           = 'local',
            label_b           = 'remote',
            refs_only_in_a    = ['ref-pid-muw-aabb'],
            refs_diverged     = ['ref-pid-muw-ccdd'],
            objects_only_in_b = ['obj-cas-imm-abcdef012345'],
            total_diffs       = 3,
            identical         = False,
        )
        restored = Schema__Dump_Diff.from_json(diff.json())
        assert restored.json() == diff.json()

    def test_identical_flag(self):
        diff = Schema__Dump_Diff(identical=True)
        assert diff.identical is True
        restored = Schema__Dump_Diff.from_json(diff.json())
        assert restored.identical is True
