import time
from sg_send_cli.cli.CLI__Debug_Log import CLI__Debug_Log


class Test_CLI__Debug_Log:

    def test_log_request_creates_entry(self):
        log   = CLI__Debug_Log(enabled=False)
        entry = log.log_request('GET', 'https://example.com/api/test', 0)
        assert entry['method'] == 'GET'
        assert entry['url']    == 'https://example.com/api/test'
        assert len(log.entries) == 1

    def test_log_response_records_duration(self):
        log   = CLI__Debug_Log(enabled=False)
        entry = log.log_request('POST', 'https://example.com/api', 100)
        log.log_response(entry, 200, 50)
        assert entry['status']    == 200
        assert entry['resp_size'] == 50
        assert entry['duration']  >= 0

    def test_log_error_records_status(self):
        log   = CLI__Debug_Log(enabled=False)
        entry = log.log_request('PUT', 'https://example.com/api', 200)
        log.log_error(entry, 403, 'Forbidden')
        assert entry['status'] == 403
        assert entry['error']  == 'Forbidden'

    def test_format_size(self):
        log = CLI__Debug_Log(enabled=False)
        assert log._format_size(0)           == '-'
        assert log._format_size(500)         == '500B'
        assert log._format_size(2048)        == '2.0KB'
        assert log._format_size(1048576)     == '1.0MB'

    def test_truncate_url_short(self):
        log = CLI__Debug_Log(enabled=False)
        url = 'https://example.com/short'
        assert log._truncate_url(url) == url

    def test_truncate_url_long(self):
        log = CLI__Debug_Log(enabled=False)
        url = 'https://example.com/' + 'a' * 100
        assert len(log._truncate_url(url)) == 80

    def test_print_summary_with_entries(self, capsys):
        log   = CLI__Debug_Log(enabled=True)
        entry = log.log_request('GET', 'https://example.com/api', 0)
        log.log_response(entry, 200, 100)
        log.print_summary()
        captured = capsys.readouterr()
        assert 'Network Summary' in captured.err
        assert 'Requests: 1' in captured.err

    def test_print_summary_no_entries(self, capsys):
        log = CLI__Debug_Log(enabled=True)
        log.print_summary()
        captured = capsys.readouterr()
        assert captured.err == ''

    def test_multiple_entries_summary(self, capsys):
        log = CLI__Debug_Log(enabled=True)
        for i in range(3):
            entry = log.log_request('GET', f'https://example.com/{i}', 0)
            log.log_response(entry, 200, 10)
        log.print_summary()
        captured = capsys.readouterr()
        assert 'Requests: 3' in captured.err
