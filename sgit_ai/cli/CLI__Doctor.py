import sys
from osbot_utils.type_safe.Type_Safe                                                  import Type_Safe
from osbot_utils.type_safe.primitives.domains.identifiers.safe_int.Timestamp_Now      import Timestamp_Now
from sgit_ai.cli.doctor.Doctor__Context                                           import Doctor__Context
from sgit_ai.cli.doctor.Check__Parse_URL                      import Check__Parse_URL
from sgit_ai.cli.doctor.Check__DNS_Resolve                    import Check__DNS_Resolve
from sgit_ai.cli.doctor.Check__TCP_Reachable                  import Check__TCP_Reachable
from sgit_ai.cli.doctor.Check__Loopback_Container_Warn        import Check__Loopback_Container_Warn
from sgit_ai.cli.doctor.Check__TLS_Handshake                  import Check__TLS_Handshake
from sgit_ai.cli.doctor.Check__API_Info                       import Check__API_Info
from sgit_ai.cli.doctor.Check__Token_Verify                   import Check__Token_Verify
from sgit_ai.cli.doctor.Check__Vault_Known                    import Check__Vault_Known
from sgit_ai.cli.doctor.Check__Write_Probe                    import Check__Write_Probe
from sgit_ai.safe_types.Enum__Doctor_Status                   import Enum__Doctor_Status
from sgit_ai.schemas.Schema__Doctor__Report                   import Schema__Doctor__Report

_STATUS_ICON = {
    Enum__Doctor_Status.PASS: '✓',
    Enum__Doctor_Status.WARN: '⚠',
    Enum__Doctor_Status.FAIL: '✗',
    Enum__Doctor_Status.SKIP: '─',
}

_FATAL_CHECKS = {'parse_url', 'dns_resolve', 'tcp_reachable', 'tls_handshake'}


class CLI__Doctor(Type_Safe):

    def run(self, ctx: Doctor__Context, output_json: bool = False) -> Schema__Doctor__Report:
        remote_name = str(ctx.remote_name) if ctx.remote_name else 'origin'
        remote_url  = str(ctx.url)         if ctx.url         else ''

        report = Schema__Doctor__Report(
            remote_name = remote_name,
            remote_url  = remote_url,
            started_at  = Timestamp_Now(),
            overall     = Enum__Doctor_Status.PASS,
        )

        if not output_json:
            print(f"\nsgit doctor — remote '{remote_name}' ({remote_url})\n")

        checks_to_run = [
            Check__Parse_URL(),
            Check__DNS_Resolve(),
            Check__TCP_Reachable(),
            None,                       # placeholder — loopback check needs tcp result
            Check__TLS_Handshake(),
            Check__API_Info(),
            Check__Token_Verify(),
            Check__Vault_Known(),
            Check__Write_Probe(),
        ]

        tcp_failed = False
        total      = 9

        for idx, checker in enumerate(checks_to_run, start=1):
            if checker is None:
                # loopback container warn: always run, behaviour depends on tcp_failed
                check = Check__Loopback_Container_Warn().execute(ctx, tcp_failed=tcp_failed)
            else:
                check = checker.execute(ctx)

            report.checks.append(check)

            name_col   = check.name.ljust(24) if check.name else ''
            icon       = _STATUS_ICON.get(check.status, '?')
            msg        = str(check.message) if check.message else ''
            ms_str     = f'({check.duration_ms} ms)' if check.duration_ms else ''

            if not output_json:
                print(f'  [{idx}/{total}] {icon} {name_col} {msg}  {ms_str}'.rstrip())

            if check.name == 'tcp_reachable' and check.status == Enum__Doctor_Status.FAIL:
                tcp_failed = True

            if check.status == Enum__Doctor_Status.FAIL:
                report.overall = Enum__Doctor_Status.FAIL
                if not output_json and check.hint:
                    print()
                    self.print_box(str(check.hint))
                if str(check.name) in _FATAL_CHECKS:
                    # When tcp_reachable fails, still run the loopback/container hint
                    # before short-circuiting — it carries the most actionable advice.
                    if str(check.name) == 'tcp_reachable':
                        loopback = Check__Loopback_Container_Warn().execute(ctx, tcp_failed=True)
                        report.checks.append(loopback)
                        if not output_json:
                            li     = idx + 1
                            l_icon = _STATUS_ICON.get(loopback.status, '?')
                            l_name = loopback.name.ljust(24) if loopback.name else ''
                            l_msg  = str(loopback.message) if loopback.message else ''
                            print(f'  [{li}/{total}] {l_icon} {l_name} {l_msg}'.rstrip())
                            if loopback.hint:
                                print()
                                self.print_box(str(loopback.hint))
                        start_skip = idx + 2
                    else:
                        start_skip = idx + 1
                    for remaining in range(start_skip, total + 1):
                        if not output_json:
                            print(f'  [{remaining}/{total}] ─ (skipped — prior check failed)')
                    break
            elif check.status == Enum__Doctor_Status.WARN:
                if report.overall == Enum__Doctor_Status.PASS:
                    report.overall = Enum__Doctor_Status.WARN
                if not output_json and check.hint:
                    print()
                    print(f'  Note: {str(check.hint)}')
                    print()

        if not output_json:
            print()
            overall_icon = _STATUS_ICON.get(report.overall, '?')
            label = {
                Enum__Doctor_Status.PASS: 'healthy',
                Enum__Doctor_Status.WARN: 'degraded',
                Enum__Doctor_Status.FAIL: 'FAILED',
            }.get(report.overall, str(report.overall.value))
            print(f'  Overall: {overall_icon} {label}')
            print()

        return report

    def run_subset(self, ctx: Doctor__Context) -> list:
        """Run checks 1-7 only (used by remote setup verification)."""
        checkers = [
            Check__Parse_URL(),
            Check__DNS_Resolve(),
            Check__TCP_Reachable(),
            None,
            Check__TLS_Handshake(),
            Check__API_Info(),
            Check__Token_Verify(),
        ]
        results    = []
        tcp_failed = False
        for checker in checkers:
            if checker is None:
                check = Check__Loopback_Container_Warn().execute(ctx, tcp_failed=tcp_failed)
            else:
                check = checker.execute(ctx)
            results.append(check)
            if check.name == 'tcp_reachable' and check.status == Enum__Doctor_Status.FAIL:
                tcp_failed = True
            if check.status == Enum__Doctor_Status.FAIL and str(check.name) in _FATAL_CHECKS:
                # Run loopback/container hint inline before short-circuiting
                if str(check.name) == 'tcp_reachable':
                    results.append(
                        Check__Loopback_Container_Warn().execute(ctx, tcp_failed=True))
                break
        return results

    def cmd_doctor(self, args):
        from sgit_ai.cli.CLI__Token_Store    import CLI__Token_Store
        from sgit_ai.core.Vault__Remote_Manager import Vault__Remote_Manager
        from sgit_ai.storage.Vault__Storage    import Vault__Storage

        directory   = getattr(args, 'directory',   '.')
        remote_name = getattr(args, 'remote',      None)
        output_json = getattr(args, 'json',        False)
        timeout     = getattr(args, 'timeout',     5)
        write_probe = getattr(args, 'write_probe', False)

        token_store = CLI__Token_Store()
        mgr         = Vault__Remote_Manager(storage=Vault__Storage())

        token    = token_store.load_token(directory)
        vault_id = None
        vk       = token_store.load_vault_key(directory)
        if vk:
            from sgit_ai.crypto.Vault__Crypto import Vault__Crypto
            vault_id = Vault__Crypto().derive_keys_from_vault_key(vk).get('vault_id')

        remote = None
        if remote_name:
            remote = mgr.get_remote(directory, remote_name)
        else:
            remote = mgr.get_default(directory)

        if remote:
            url         = str(remote.url)
            remote_name = str(remote.name)
            tls_verify  = remote.tls_verify
        else:
            url        = token_store.load_base_url(directory)
            tls_verify = True

        if not url:
            print('Error: no remote configured. Run: sgit vault remote add origin <url>', file=sys.stderr)
            sys.exit(1)

        ctx = Doctor__Context(
            url             = url,
            token           = token,
            vault_id        = vault_id,
            timeout_seconds = timeout,
            tls_verify      = tls_verify,
            write_probe     = write_probe,
            remote_name     = remote_name or 'origin',
        )

        report = self.run(ctx, output_json=output_json)

        if output_json:
            import json
            print(json.dumps(report.json(), indent=2))

        if report.overall == Enum__Doctor_Status.FAIL:
            sys.exit(1)

    def print_box(self, text: str, width: int = 72):
        """Render a multi-line message inside a Unicode box.

        Used to highlight recovery hints (e.g. the container-loopback advice).
        Width is character-cell based; multi-byte chars may misalign the
        right border — acceptable trade-off for now.
        """
        lines  = text.split('\n')
        border = '─' * width
        print(f'  ┌{border}┐')
        for line in lines:
            padded = line.ljust(width)
            print(f'  │ {padded} │')
        print(f'  └{border}┘')
