"""Container__Host — the facts about this machine that decide which runtimes apply and how
to install them: OS, CPU, OS version, the user's uid/gid (a container must write the data
folder as that user), and the package manager. Fields can be set by tests."""
import os
import platform
import shutil
from   osbot_utils.type_safe.Type_Safe                 import Type_Safe
from   osbot_utils.type_safe.primitives.core.Safe_UInt import Safe_UInt
from   sgit_ai.safe_types.Safe_Str__Platform_Tag       import Safe_Str__Platform_Tag

LINUX_PACKAGE_MANAGERS = ('apt-get', 'dnf', 'yum', 'pacman', 'zypper', 'apk', 'brew')


class Container__Host(Type_Safe):
    system     : Safe_Str__Platform_Tag = None      # linux | darwin | windows
    machine    : Safe_Str__Platform_Tag = None      # x86_64 | arm64 | aarch64 | amd64
    os_version : Safe_Str__Platform_Tag = None      # macOS product version on darwin, else the kernel release
    uid        : Safe_UInt
    gid        : Safe_UInt
    has_ids    : bool = False                       # False on Windows: no --user to pass

    def detect(self):
        self.system  = platform.system().lower()
        self.machine = platform.machine().lower()
        version      = platform.mac_ver()[0] if self.system == 'darwin' else platform.release()
        self.os_version = ''.join(ch for ch in version if ch.isalnum() or ch in '._-')[:64]
        if hasattr(os, 'getuid'):
            self.uid, self.gid, self.has_ids = os.getuid(), os.getgid(), True
        return self

    def is_mac(self) -> bool:
        return str(self.system) == 'darwin'

    def is_linux(self) -> bool:
        return str(self.system) == 'linux'

    def is_windows(self) -> bool:
        return str(self.system) == 'windows'

    def is_apple_silicon(self) -> bool:
        return self.is_mac() and str(self.machine) in ('arm64', 'aarch64')

    def mac_major(self) -> int:
        try:
            return int(str(self.os_version).split('.')[0]) if self.is_mac() else 0
        except ValueError:
            return 0

    def user_spec(self) -> str:
        """'uid:gid' for `--user`, or '' where there is none (Windows)."""
        return f'{int(self.uid)}:{int(self.gid)}' if self.has_ids else ''

    def package_manager(self) -> str:
        for name in LINUX_PACKAGE_MANAGERS:
            if shutil.which(name):
                return name
        return ''
