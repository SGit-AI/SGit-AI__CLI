from sgit_ai.cli.CLI__Main import CLI__Main


class Test_CLI__As_Flag__ArgParse:

    def _parse(self, argv):
        m = CLI__Main()
        return m.build_parser().parse_args(argv)

    def test_vault_share_as_flag_sets_share_as(self):
        args = self._parse(['vault', 'share', '--as', 'cold-idle-7311'])
        assert args.share_as == 'cold-idle-7311'

    def test_vault_export_as_flag_sets_share_as(self):
        args = self._parse(['vault', 'export', '--as', 'cold-idle-7311'])
        assert args.share_as == 'cold-idle-7311'

    def test_share_publish_as_flag_sets_share_as(self):
        args = self._parse(['share', 'publish', '--as', 'cold-idle-7311'])
        assert args.share_as == 'cold-idle-7311'

    def test_vault_share_as_defaults_to_none(self):
        args = self._parse(['vault', 'share'])
        assert args.share_as is None

    def test_vault_export_as_defaults_to_none(self):
        args = self._parse(['vault', 'export'])
        assert args.share_as is None

    def test_share_publish_as_defaults_to_none(self):
        args = self._parse(['share', 'publish'])
        assert args.share_as is None

    def test_vault_share_has_separate_token_for_access(self):
        args = self._parse(['vault', 'share', '--token', 'my-access-token'])
        assert args.token == 'my-access-token'
        assert args.share_as is None

    def test_vault_share_as_and_token_are_independent(self):
        args = self._parse(['vault', 'share', '--as', 'cold-idle-7311',
                            '--token', 'my-access-token'])
        assert args.share_as == 'cold-idle-7311'
        assert args.token == 'my-access-token'
