from sgit_ai.schemas.publish.Schema__Vault_Cover import Schema__Vault_Cover


class Test_Schema__Vault_Cover:

    def test_round_trip(self):
        cover = Schema__Vault_Cover(title       = 'Investor Pack — Q3',
                                    description = 'Financials, cap table and board deck.',
                                    updated     = '2026-08-17T12:00:00Z',
                                    access      = 'ir@example.com',
                                    public      = False)
        assert Schema__Vault_Cover.from_json(cover.json()).json() == cover.json()

    def test_access_keeps_email_shape(self):
        cover = Schema__Vault_Cover(access='ir@example.com')
        assert str(cover.access) == 'ir@example.com'

    def test_markup_is_stripped_from_cover_text(self):
        cover = Schema__Vault_Cover(title='<script>alert(1)</script>')
        assert '<' not in str(cover.title)
        assert '>' not in str(cover.title)
