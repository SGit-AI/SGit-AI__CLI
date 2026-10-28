import time

from sgit_ai.crypto.signing.SSH__Allowed_Signers import SSH__Allowed_Signers
from sgit_ai.crypto.signing.SSH__Public_Key      import SSH__Public_Key
from sgit_ai.crypto.signing.SSH__Revocation_List import SSH__Revocation_List
from tests.unit.crypto.signing.signing_keys      import Signing_Keys


class Test_SSH__Allowed_Signers:

    def setup_method(self):
        self.keys = Signing_Keys()
        _, _, self.line = self.keys.make('ed25519')
        _, _, self.other = self.keys.make('nistp256')
        self.blob = SSH__Public_Key().from_openssh_line(self.line).blob

    def teardown_method(self):
        self.keys.cleanup()

    def parse(self, text):
        return SSH__Allowed_Signers().parse(text)

    def test_comments_blank_lines_and_unreadable_lines_are_skipped(self):
        allowed = self.parse(f'# comment\n\nnot a key line\nme@x {self.line} my laptop\n')
        assert [str(e.principals) for e in allowed.entries] == ['me@x'] and allowed.entries[0].line_number == 4

    def test_namespaces(self):
        allowed = self.parse(f'a@x namespaces="git" {self.line}\nb@x namespaces="file" {self.line}\nc@x {self.line}\n')
        assert [str(e.principals) for e in allowed.lines_for(self.blob, 'git')] == ['a@x', 'c@x']

    def test_quoted_options_with_commas_and_quoted_principals(self):
        allowed = self.parse(f'"a@x,b@x" namespaces="git,file",valid-before="20300101Z" {self.line}\n')
        entry   = allowed.entries[0]
        assert (str(entry.principals), str(entry.namespaces), str(entry.valid_before)) == ('a@x,b@x', 'git,file', '20300101Z')

    def test_two_lines_for_one_key_give_two_principals_in_file_order(self):
        allowed = self.parse(f'first@x {self.line}\nother@x {self.other}\nsecond@x {self.line}\n')
        assert [str(e.principals) for e in allowed.lines_for(self.blob, 'git')] == ['first@x', 'second@x']

    def test_validity_windows_utc_and_local(self):
        allowed = self.parse(f'a@x valid-after="20200101Z",valid-before="20300101000000Z" {self.line}\n')
        entry   = allowed.entries[0]
        assert allowed.time_problem(entry, int(time.time())) == ''
        assert 'valid-after 20200101Z' in allowed.time_problem(entry, 1_500_000_000)
        assert 'valid-before 20300101000000Z' in allowed.time_problem(entry, 1_950_000_000)
        assert allowed.parse_time('202001011200') == int(time.mktime((2020, 1, 1, 12, 0, 0, 0, 0, -1)))

    def test_pattern_lists(self):
        allowed = SSH__Allowed_Signers()
        assert allowed.pattern_list_matches('git', 'g?t')
        assert allowed.pattern_list_matches('git', 'file,*')
        assert not allowed.pattern_list_matches('git', '*,!git')
        assert not allowed.pattern_list_matches('git', '!file')                     # negation alone matches nothing

    def test_cert_authority_asks_for_delegation(self):
        assert self.parse(f'*@x cert-authority {self.line}\n').has_cert_authority


class Test_SSH__Revocation_List:

    def setup_method(self):
        self.keys = Signing_Keys()

    def teardown_method(self):
        self.keys.cleanup()

    def test_plain_key_lines(self):
        _, _, line = self.keys.make('ed25519')
        revoked    = SSH__Revocation_List().load(self.keys.write('revoked', f'# old laptop\n{line}\n'))
        assert revoked.is_revoked(SSH__Public_Key().from_openssh_line(line).blob) and not revoked.is_krl()

    def test_krl_magic_is_detected(self):
        path = self.keys.write('krl', '')
        with open(path, 'wb') as f:
            f.write(b'SSHKRL\n\x00' + b'\x00' * 40)
        assert SSH__Revocation_List().load(path).is_krl()
