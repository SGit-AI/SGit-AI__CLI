"""A pull lists the commits it brings, one line each, and counts them — also when
`sgit status` (or the pull's own rewind guard) already fetched the commit objects,
and on a pack vault where the objects arrive inside packs (reported 24 Oct: "0 new
commits" and no commit lines after a status)."""
import pytest

from tests._helpers.pack_env     import Pack__Env
from tests._helpers.vault_test_env import TEST_VAULT_KEY


def _pull_events(sync, directory):
    events = []
    result = sync.pull(directory, on_progress=lambda kind, msg, detail='': events.append((kind, msg, detail)))
    return result, events


class Test_Pull__Lists_New_Commits:

    def _two_clones(self, packs: bool):
        env = Pack__Env()
        sync, a, key = (env.pack_vault if packs else env.normal_vault)(env.text_files(2), vault_key=TEST_VAULT_KEY)
        sync_b, b = env.clone(key, 'b')
        for i in range(3):
            env.write(b, {f'n{i}.md': f'new {i}\n'.encode()})
            sync_b.commit(b, message=f'commit number {i}'); sync_b.push(b)
        return env, sync, a

    @pytest.mark.parametrize('packs', [False, True], ids=['loose', 'pack'])
    def test_pull_counts_and_lists_the_three_commits(self, packs):
        env, sync, a = self._two_clones(packs)
        result, events = _pull_events(sync, a)
        lines = [(msg, detail) for kind, msg, detail in events if kind == 'commit']
        assert len(lines) == 3 and [d for _, d in lines] == ['"commit number 0"', '"commit number 1"', '"commit number 2"']
        analysed = [detail for kind, msg, detail in events if msg == 'Commit graph analysed']
        assert analysed and analysed[-1].startswith('3 new commits')

    @pytest.mark.parametrize('packs', [False, True], ids=['loose', 'pack'])
    def test_a_status_before_the_pull_does_not_hide_them(self, packs):
        env, sync, a = self._two_clones(packs)
        st = sync.status(a)                                                    # fetches the commit objects to count
        assert st['behind'] == 3
        result, events = _pull_events(sync, a)
        lines = [detail for kind, msg, detail in events if kind == 'commit']
        assert lines == ['"commit number 0"', '"commit number 1"', '"commit number 2"']
        analysed = [detail for kind, msg, detail in events if msg == 'Commit graph analysed']
        assert analysed and analysed[-1].startswith('3 new commits')
