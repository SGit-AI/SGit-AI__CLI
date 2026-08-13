import tempfile
import os
import shutil
from   sgit_ai.schemas.inspect.Schema__Ignore_Reason import Schema__Ignore_Reason
from   sgit_ai.core.Vault__Ignore                     import Vault__Ignore


class Test_Schema__Ignore_Reason:

    def test_create_with_defaults(self):
        r = Schema__Ignore_Reason()
        assert r.rel_path     is None
        assert r.is_ignored   is False
        assert r.reason_code  is None
        assert r.matched_rule is None
        assert r.description  is None

    def test_create_with_values(self):
        r = Schema__Ignore_Reason(rel_path     = 'src/foo.py',
                                  is_ignored   = False,
                                  reason_code  = 'tracked',
                                  description  = 'not matched by any ignore rule')
        assert str(r.rel_path)    == 'src/foo.py'
        assert r.is_ignored        is False
        assert str(r.reason_code) == 'tracked'

    def test_round_trip(self):
        r = Schema__Ignore_Reason(rel_path     = 'config/.env',
                                  is_ignored   = True,
                                  reason_code  = 'always_ignored_file',
                                  matched_rule = '.env',
                                  description  = 'environment file with secrets')
        assert Schema__Ignore_Reason.from_json(r.json()).json() == r.json()

    def test_round_trip_tracked(self):
        r = Schema__Ignore_Reason(rel_path    = 'foo.py',
                                  is_ignored  = False,
                                  reason_code = 'tracked',
                                  description = 'not matched by any ignore rule')
        assert Schema__Ignore_Reason.from_json(r.json()).json() == r.json()


class Test_Vault__Ignore__Explain:

    def test_explain_tracked_file(self):
        ignore = Vault__Ignore()
        r = ignore.explain('foo.py')
        assert r.is_ignored         is False
        assert str(r.reason_code)  == 'tracked'

    def test_explain_always_ignored_file(self):
        ignore = Vault__Ignore()
        r = ignore.explain('.env')
        assert r.is_ignored          is True
        assert str(r.reason_code)   == 'always_ignored_file'
        assert str(r.matched_rule)  == '.env'

    def test_explain_env_secret_glob(self):
        ignore = Vault__Ignore()
        r = ignore.explain('.env.staging')
        assert r.is_ignored          is True
        assert str(r.reason_code)   == 'env_secret_glob'
        assert str(r.matched_rule)  == '.env*'

    def test_explain_env_template_is_tracked(self):
        ignore = Vault__Ignore()
        r = ignore.explain('.env.example')
        assert r.is_ignored         is False
        assert str(r.reason_code)  == 'tracked'

    def test_explain_always_ignored_dir(self):
        ignore = Vault__Ignore()
        r = ignore.explain('.vscode', is_dir=True)
        assert r.is_ignored          is True
        assert str(r.reason_code)   == 'always_ignored_dir'
        assert str(r.matched_rule)  == '.vscode'

    def test_explain_dotdir_not_in_set_is_tracked(self):
        ignore = Vault__Ignore()
        r = ignore.explain('.claude', is_dir=True)
        assert r.is_ignored         is False
        assert str(r.reason_code)  == 'tracked'

    def test_explain_gitignore_pattern(self):
        tmp = tempfile.mkdtemp()
        try:
            with open(os.path.join(tmp, '.gitignore'), 'w') as f:
                f.write('dist/\n')
            ignore = Vault__Ignore().load_gitignore(tmp)
            r = ignore.explain('dist', is_dir=True)
            assert r.is_ignored          is True
            assert str(r.reason_code)   == 'gitignore_pattern'
            assert str(r.matched_rule)  == 'dist'
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_explain_round_trip(self):
        ignore = Vault__Ignore()
        r = ignore.explain('.env')
        assert Schema__Ignore_Reason.from_json(r.json()).json() == r.json()
