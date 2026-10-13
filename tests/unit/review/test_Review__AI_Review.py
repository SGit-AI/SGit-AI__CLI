"""review/tools/ai_review.py: the gate's rules, without calling the API (hermetic)."""
import importlib.util
import json
import os

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def _module():
    spec   = importlib.util.spec_from_file_location('ai_review', os.path.join(REPO, 'review', 'tools', 'ai_review.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _finding(**over):
    f = dict(file='sgit_ai/crypto/pki/PKI__Key_Store.py', line=40, function='safe_fingerprint',
             category='path_traversal', severity='high', confidence=0.9, register='new',
             title='t', evidence='e', fix='f')
    f.update(over)
    return f


class Test_Review__AI_Review:

    @pytest.fixture
    def review(self, tmp_path):
        os.makedirs(tmp_path / 'review' / 'findings')
        os.makedirs(tmp_path / 'team' / 'explorer' / 'appsec' / 'threat-model')
        with open(tmp_path / 'team' / 'explorer' / 'appsec' / 'threat-model' / 'v0.21.0__threat-model.md', 'w') as f:
            f.write('| TM-F32 | fixed |\n| TM-R36 | open |\n')
        return _module().Review__AI_Review(str(tmp_path), 'a', 'b', 'claude-sonnet-5-5', 'medium', 0.8, 'slice')

    def test_only_new_confident_medium_or_worse_findings_gate(self, review):
        kept = review.gating([_finding(),
                              _finding(function='x', severity='low'),                 # too minor
                              _finding(function='y', confidence=0.5),                 # not sure enough
                              _finding(function='z', register='TM-R36')])             # already in the register
        assert [f['function'] for f in kept] == ['safe_fingerprint']

    @pytest.mark.parametrize('register', ['', ' ', 'none', 'n/a', 'NEW (not in register)', 'TM-R999', 'TM-X1', 'tm-r36'])
    def test_only_a_row_the_register_holds_exempts_a_finding(self, review, register):
        """DR2-002: anything that is not exactly an existing TM-Fnn/TM-Rnn id is new; the diff is
        attacker text and can steer the label, so the label has to be checkable."""
        assert [f['register'] for f in review.gating([_finding(register=register)])] == [register]
        assert review.gating([_finding(register='TM-R36'), _finding(register='TM-F32')]) == []

    def test_a_finding_with_no_function_is_not_a_file_wide_waiver(self, review):
        """DR2-005: an empty function made one waiver cover every finding of that category in the file."""
        a, b = _finding(function='', title='one thing'), _finding(function='', title='another thing')
        assert review.fingerprint(a) != review.fingerprint(b)
        assert review.fingerprint(a) == review.fingerprint(_finding(function='', title='One THING!'))

    def test_data_tags_carry_a_nonce_and_the_summary_quotes_model_text(self, review):
        """DR2-003 / DR2-013: a diff cannot close the block it is inside, and the job summary
        renders titles as code, never as markup."""
        assert review.tag('change') != 'change' and review.tag('change').startswith('change-')
        assert _module().Review__AI_Review(REPO, 'a', 'b', 'claude-sonnet-5-5', 'medium', 0.8, 'slice').tag('change') != review.tag('change')
        report = dict(status='fail', files=['x.py'], usd=0.1, failing=['1'],
                      findings=[dict(_finding(title='[see](https://evil.example) <img src=x> `tick`'), id='1')])
        line = [l for l in review.markdown(report).splitlines() if l.startswith('- ')][0]
        assert '`[see](https://evil.example) <img src=x> \'tick\'`' in line

    def test_a_waived_finding_does_not_gate(self, review, tmp_path):
        finding = _finding()
        fid     = review.fingerprint(finding)
        with open(tmp_path / 'review' / 'findings' / 'ai-waivers.json', 'w') as f:
            json.dump({'waivers': [{'id': fid, 'reason': 'accepted'}]}, f)
        assert review.gating([finding]) == [] and finding['waived']

    def test_the_fingerprint_ignores_wording_and_line(self, review):
        assert review.fingerprint(_finding()) == review.fingerprint(_finding(title='other words', line=99))
        assert review.fingerprint(_finding()) != review.fingerprint(_finding(category='crypto'))

    def test_haiku_long_prompts_cost_more(self, review):
        assert review.prices('claude-haiku-5-5', 50_000)  == (0.10, 0.50, 0.01)
        assert review.prices('claude-haiku-5-5', 150_000) == (0.50, 2.50, 0.05)
        assert review.prices('claude-sonnet-5-5', 150_000) == (2.00, 10.00, 0.20)

    def test_a_change_outside_the_slice_is_skipped_and_a_dry_run_calls_nothing(self):
        module = _module()
        head   = module.Review__AI_Review(REPO, 'HEAD', 'HEAD', 'claude-sonnet-5-5', 'medium', 0.8, 'slice')
        assert head.run(dry_run=False, verify=True) == (0, {'status': 'skipped', 'reason': 'no slice file changed'})
        review = module.Review__AI_Review(REPO, 'HEAD', 'HEAD', 'claude-sonnet-5-5', 'medium', 0.8, 'slice')
        review.changed_files = lambda: ['sgit_ai/crypto/Vault__Crypto.py']
        code, report = review.run(dry_run=True, verify=True)
        assert code == 0 and report['status'] == 'dry-run' and review.usage == []
        assert report['input_tokens_estimate'] > report['system_tokens_estimate'] > 1000
        assert set(report['usd']) == {'claude-haiku-5-5', 'claude-sonnet-5-5', 'claude-opus-5-5'}
