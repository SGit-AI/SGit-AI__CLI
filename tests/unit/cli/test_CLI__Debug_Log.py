import time
from sgit_ai.cli.CLI__Debug_Log import CLI__Debug_Log


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
        assert log._format_size(500)         == '500 B'
        assert log._format_size(2048)        == '2.0 KB'
        assert log._format_size(1048576)     == '1.0 MB'

    def test_format_path_strips_base_url(self):
        log = CLI__Debug_Log(enabled=False)
        url = 'https://dev.send.sgraph.ai/api/vault/read/id73x4np/bare%2Fdata'
        assert log._format_path(url) == 'vault/read/id73x4np/bare/data'

    def test_format_path_decodes_url_encoding(self):
        log = CLI__Debug_Log(enabled=False)
        url = 'https://dev.send.sgraph.ai/api/vault/read/id73x4np/bare%2Frefs%2Fref-pid-muw'
        assert log._format_path(url) == 'vault/read/id73x4np/bare/refs/ref-pid-muw'

    def test_format_path_truncates_long_paths(self):
        log  = CLI__Debug_Log(enabled=False)
        url  = 'https://example.com/api/' + 'a' * 100
        path = log._format_path(url)
        assert len(path) == 70
        assert path.endswith('...')

    def test_print_header(self, capsys):
        log = CLI__Debug_Log(enabled=True)
        log.print_header()
        captured = capsys.readouterr()
        assert 'SG/Send CLI' in captured.err
        assert 'Network Debug' in captured.err
        assert 'Method' in captured.err

    def test_print_summary_with_entries(self, capsys):
        log   = CLI__Debug_Log(enabled=True)
        entry = log.log_request('GET', 'https://example.com/api', 0)
        log.log_response(entry, 200, 100)
        log.print_summary()
        captured = capsys.readouterr()
        assert 'Reqs: 1' in captured.err

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
        assert 'Reqs: 3' in captured.err

    def test_print_entry_format(self, capsys):
        log   = CLI__Debug_Log(enabled=True)
        entry = log.log_request('GET', 'https://dev.send.sgraph.ai/api/vault/read/id73x4np/bare%2Fdata', 0)
        log.log_response(entry, 200, 457)
        captured = capsys.readouterr()
        line = captured.err.strip()
        assert '[GET   ]' in line
        assert '200'      in line
        assert '457 B'    in line
        assert 'vault/read/id73x4np/bare/data' in line
        assert 'https://' not in line

    def test_print_entry_with_error_appends_err_line_49(self, capsys):
        """Line 49: entry with error field → ERR: appended to log line."""
        log   = CLI__Debug_Log(enabled=True)
        entry = log.log_request('POST', 'https://example.com/upload', 0)
        entry['error'] = 'connection refused'
        log._print_entry(entry)
        captured = capsys.readouterr()
        assert 'ERR:' in captured.err
        assert 'connection refused' in captured.err

    def test_print_header_disabled_returns_early_line_79(self, capsys):
        """Line 79: print_header() when disabled → early return, nothing printed."""
        log = CLI__Debug_Log(enabled=False)
        log.print_header()
        assert capsys.readouterr().err == ''
