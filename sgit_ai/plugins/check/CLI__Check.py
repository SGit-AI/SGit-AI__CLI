"""CLI__Check — `sgit check <…>` namespace (fsck; verify and sign reserved for PKI)."""
import argparse

from osbot_utils.type_safe.Type_Safe import Type_Safe


class CLI__Check(Type_Safe):
    vault : object = None   # CLI__Vault instance (injected by CLI__Main)

    def register(self, subparsers: argparse._SubParsersAction):
        check_p   = subparsers.add_parser('check', help='Vault integrity checks')
        check_sub = check_p.add_subparsers(dest='check_command')
        check_p.set_defaults(func=lambda a: check_p.print_help())

        # check fsck  (was top-level `fsck`)
        fsck_p = check_sub.add_parser('fsck', help='Verify vault integrity and repair missing objects')
        fsck_p.add_argument('directory', nargs='?', default='.', help='Vault directory (default: .)')
        fsck_p.add_argument('--repair',  action='store_true', help='Download missing objects from remote')
        fsck_p.add_argument('--verbose', action='store_true', help='Show object type and referencing parent for each missing/corrupt object')
        fsck_p.set_defaults(func=self.vault.cmd_fsck)

        # check upload-objects  (recovery: push locally-present objects to server)
        upload_p = check_sub.add_parser(
            'upload-objects',
            help='Upload specific local objects to the server (recovery tool — run on the vault that HAS the objects)')
        upload_p.add_argument('directory', nargs='?', default='.', help='Vault directory (default: .)')
        upload_p.add_argument('object_ids', nargs='+', metavar='OBJ_ID',
                              help='Object IDs to upload (obj-cas-imm-...)')
        upload_p.set_defaults(func=self.vault.cmd_upload_objects)

        return check_p
