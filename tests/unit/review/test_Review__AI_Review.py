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
        return _module().Review__AI_Review(str(tmp_path), 'a', 'b', 'claude-sonnet-5-5', 'medium', 0.8, 'slice')

    def test_only_new_confident_medium_or_worse_findings_gate(self, review):
        kept = review.gating([_finding(),
                              _finding(function='x', severity='low'),                 # too minor
                              _finding(function='y', confidence=0.5),                 # not sure enough
                              _finding(function='z', register='TM-R36')])             # already in the register
        assert [f['function'] for f in kept] == ['safe_fingerprint']

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
