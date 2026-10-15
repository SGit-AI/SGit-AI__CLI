import pytest

from sgit_ai.safe_types.Safe_Str__Container_Name    import Safe_Str__Container_Name
from sgit_ai.safe_types.Safe_Str__Container_Runtime import Safe_Str__Container_Runtime
from sgit_ai.safe_types.Safe_Str__Host_Path         import Safe_Str__Host_Path
from sgit_ai.safe_types.Safe_Str__Image_Ref         import Safe_Str__Image_Ref
from sgit_ai.safe_types.Safe_Str__Platform_Tag      import Safe_Str__Platform_Tag


class Test_Safe_Str__Serve_Types:

    def test_values_are_kept_exactly(self):
        assert str(Safe_Str__Image_Ref('ghcr.io/org/img@sha256:' + 'a' * 64)).endswith('a' * 64)
        assert str(Safe_Str__Host_Path('C:\\Users\\Dinis Cruz\\vault é')) == 'C:\\Users\\Dinis Cruz\\vault é'
        assert str(Safe_Str__Container_Name('sgit-serve-0a1b2c')) == 'sgit-serve-0a1b2c'
        assert str(Safe_Str__Container_Runtime('podman')) == 'podman'
        assert str(Safe_Str__Platform_Tag('26.0.1')) == '26.0.1'

    @pytest.mark.parametrize('cls, bad', [(Safe_Str__Image_Ref, '-v'), (Safe_Str__Image_Ref, 'a b'),
                                          (Safe_Str__Container_Name, '-rm'), (Safe_Str__Container_Runtime, 'Docker;'),
                                          (Safe_Str__Host_Path, 'a\nb'), (Safe_Str__Platform_Tag, 'x y')])
    def test_refused_never_rewritten(self, cls, bad):
        with pytest.raises(ValueError):
            cls(bad)
