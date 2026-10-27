"""Vault__API.read_range (Phase 2): the presigned URL of a file is asked for once and kept
until shortly before it expires, so a range costs one request, not two (review of 26 Oct,
M4); a URL the host stops honouring is asked for again once."""
from sgit_ai.network.api.Vault__API import Vault__API


class API__Counting_Ranges(Vault__API):
    """A transport double: the presigned route and the Range fetch replaced, counted."""
    urls_asked : int  = 0
    fetched    : list
    fail_once  : bool = False
    expires_in : int  = 300

    def presigned_read_url(self, vault_id, file_id):
        self.urls_asked += 1
        return dict(url=f'https://host.example/{file_id}?sig={self.urls_asked}', expires_in=self.expires_in)

    def fetch_presigned_range(self, url, start, end, timeout=300):
        if self.fail_once:
            self.fail_once = False
            raise RuntimeError('HTTP 403: expired')
        self.fetched.append((url, start, end))
        return bytes(range(start, end + 1)), 1000, True


class Test_Vault__API__Read_Range:

    def test_the_url_is_asked_once_per_file_and_each_range_is_one_fetch(self):
        api = API__Counting_Ranges(base_url='https://host.example')
        assert api.read_range('v', 'bare/packs/commits/p.zip', 0, 3) == bytes([0, 1, 2, 3])
        assert api.read_range('v', 'bare/packs/commits/p.zip', 10, 11) == bytes([10, 11])
        assert api.read_range('v', 'bare/packs/commits/q.zip', 0, 0) == bytes([0])
        assert api.urls_asked == 2 and len(api.fetched) == 3
        assert api.fetched[0][0] == api.fetched[1][0] and api.fetched[2][0] != api.fetched[0][0]

    def test_a_url_the_host_refuses_is_asked_for_again_once(self):
        api = API__Counting_Ranges(base_url='https://host.example')
        api.read_range('v', 'f', 0, 1)
        api.fail_once = True
        assert api.read_range('v', 'f', 2, 3) == bytes([2, 3])
        assert api.urls_asked == 2 and api.fetched[-1][0].endswith('sig=2')

    def test_a_url_near_its_expiry_is_renewed(self):
        api = API__Counting_Ranges(base_url='https://host.example', expires_in=31)
        api.read_range('v', 'f', 0, 1)
        api.range_urls['f'] = (api.range_urls['f'][0], 0.0)                     # the deadline passed
        api.read_range('v', 'f', 0, 1)
        assert api.urls_asked == 2
