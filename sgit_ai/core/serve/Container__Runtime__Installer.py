"""Container__Runtime__Installer — `sgit serve install [runtime]`.

Installs a runtime for `sgit serve`, after showing exactly what will be installed: the
product, where it comes from, its licence, whether it needs admin rights, and every
command, in order. Nothing runs until the user says yes (or passes --yes). Commands are
argv lists run with the user's terminal attached, so `sudo` asks for its own password.

Recommendation per machine:
  macOS 26+ on Apple silicon : Apple container (Podman offered too)
  other macOS                : Podman
  Linux                      : Podman (Docker Engine offered too)
  Windows                    : Podman (needs WSL2)
  anywhere                   : uv, for the no-container engine
"""
import json
import os
import tempfile
import urllib.request
from   osbot_utils.type_safe.Type_Safe                  import Type_Safe
from   sgit_ai.core.serve.Container__Command_Runner      import Container__Command_Runner
from   sgit_ai.core.serve.Container__Host                import Container__Host

APPLE_CONTAINER_RELEASES = 'https://api.github.com/repos/apple/container/releases/latest'
PODMAN_RELEASES          = 'https://api.github.com/repos/containers/podman/releases/latest'
LINUX_PODMAN = {'apt-get': ['sudo', 'apt-get', 'install', '-y', 'podman'],
                'dnf'    : ['sudo', 'dnf', 'install', '-y', 'podman'],
                'yum'    : ['sudo', 'yum', 'install', '-y', 'podman'],
                'pacman' : ['sudo', 'pacman', '-S', '--noconfirm', 'podman'],
                'zypper' : ['sudo', 'zypper', '--non-interactive', 'install', 'podman'],
                'apk'    : ['sudo', 'apk', 'add', 'podman'],
                'brew'   : ['brew', 'install', 'podman']}


class Container__Runtime__Installer(Type_Safe):
    runner : Container__Command_Runner
    host   : Container__Host

    # ------------------------------------------------------------ choosing
    def recommended(self) -> list:
        """Runtime names worth installing on this machine, best first."""
        if self.host.is_apple_silicon() and self.host.mac_major() >= 26:
            return ['container', 'podman', 'uv']
        if self.host.is_mac():
            return ['podman', 'uv']
        if self.host.is_windows():
            return ['podman', 'uv']
        return ['podman', 'docker', 'uv']

    def plan(self, name: str = None) -> dict:
        """dict(runtime, title, details[], admin, commands[[argv]], after[]) for one runtime."""
        name = name or self.recommended()[0]
        builder = {'container': self.plan_apple_container, 'podman': self.plan_podman,
                   'docker'   : self.plan_docker,          'uv'    : self.plan_uv}.get(name)
        if builder is None:
            raise ValueError(f'sgit cannot install {name!r}; it can install: {", ".join(self.recommended())}')
        return builder()

    # --------------------------------------------------------------- plans
    def plan_apple_container(self) -> dict:
        if not self.host.is_apple_silicon():
            raise ValueError('Apple container runs only on Apple silicon Macs; use: sgit serve install podman')
        release = self.require_release(self.latest_release(APPLE_CONTAINER_RELEASES, '.pkg'),
                                       'https://github.com/apple/container/releases')
        pkg     = os.path.join(tempfile.gettempdir(), release['asset'])
        details = [f'Apple container {release["version"] or "(latest release)"}: runs Linux containers on macOS, '
                   f'each in its own lightweight VM; no Docker involved.',
                   f'Source: github.com/apple/container releases, a signed installer package'
                   + (f' ({release["size_mb"]} MB)' if release['size_mb'] else '') + '.',
                   'Licence: Apache-2.0 (open source).',
                   'Installs to /usr/local (needs your admin password), then starts its system service.']
        if self.host.mac_major() and self.host.mac_major() < 26:
            details.append(f'Note: this Mac runs macOS {self.host.os_version}; Apple supports macOS 26, and on '
                           f'macOS 15 container networking is reduced.')
        commands = [['curl', '-fL', '-o', pkg, release['url']],
                    ['sudo', 'installer', '-pkg', pkg, '-target', '/'],
                    ['container', 'system', 'start']]
        return dict(runtime='container', title='Apple container', details=details, admin=True,
                    commands=commands, after=['sgit serve'])

    def plan_podman(self) -> dict:
        details = ['Podman: an open-source, daemonless container engine (Red Hat); rootless by default; '
                   'runs Docker images.', 'Licence: Apache-2.0.']
        if self.host.is_linux():
            manager = self.host.package_manager()
            if manager not in LINUX_PODMAN:
                raise ValueError('no supported package manager found (apt-get, dnf, yum, pacman, zypper, apk); '
                                 'install Podman from https://podman.io/docs/installation')
            details.append(f'Source: your distribution\'s packages, via {manager}' +
                           (' (needs your admin password).' if manager != 'brew' else '.'))
            return dict(runtime='podman', title='Podman', details=details, admin=manager != 'brew',
                        commands=[LINUX_PODMAN[manager]], after=['sgit serve'])
        if self.host.is_mac():
            if self.runner.which('brew'):
                details.append('Source: Homebrew (`brew install podman`). It then creates and starts a small Linux '
                               'VM ("podman machine", a few GB of disk, grows as needed).')
                commands = [['brew', 'install', 'podman']]
                admin    = False
            else:
                release = self.require_release(self.latest_release(PODMAN_RELEASES, '.pkg', prefer='universal'),
                                               'https://github.com/containers/podman/releases')
                pkg     = os.path.join(tempfile.gettempdir(), release['asset'])
                details.append(f'Source: github.com/containers/podman releases {release["version"]}, the macOS '
                               f'installer package (needs your admin password). It then creates and starts a '
                               f'small Linux VM ("podman machine").')
                commands = [['curl', '-fL', '-o', pkg, release['url']],
                            ['sudo', 'installer', '-pkg', pkg, '-target', '/']]
                admin    = True
            commands += [['podman', 'machine', 'init'], ['podman', 'machine', 'start']]
            return dict(runtime='podman', title='Podman', details=details, admin=admin, commands=commands,
                        after=['sgit serve'])
        details.append('Source: winget package RedHat.Podman. Podman on Windows runs its VM in WSL2 '
                       '(`wsl --install` first if WSL is not enabled; Windows may ask to restart).')
        return dict(runtime='podman', title='Podman', details=details, admin=True,
                    commands=[['winget', 'install', '-e', '--id', 'RedHat.Podman'],
                              ['podman', 'machine', 'init'], ['podman', 'machine', 'start']],
                    after=['sgit serve'])

    def plan_docker(self) -> dict:
        if not self.host.is_linux():
            raise ValueError('Docker Desktop is installed from docker.com (its licence requires a paid plan for '
                             'larger companies); sgit installs Podman or Apple container instead')
        script = os.path.join(tempfile.gettempdir(), 'get-docker.sh')
        return dict(runtime='docker', title='Docker Engine',
                    details=['Docker Engine (Community Edition) for Linux.',
                             "Source: Docker's official install script from https://get.docker.com, run as root "
                             '(it adds Docker\'s package repository and installs docker-ce).',
                             'Licence: Apache-2.0 (Engine).'],
                    admin=True,
                    commands=[['curl', '-fsSL', '-o', script, 'https://get.docker.com'],
                              ['sudo', 'sh', script]],
                    after=['sudo systemctl start docker   (if it is not started for you)', 'sgit serve'])

    def plan_uv(self) -> dict:
        details = ['uv: a single-binary Python package manager (Astral). sgit uses it to run the SG/Send '
                   'server without any container: it fetches Python 3.12 and the server package on first use.',
                   'Licence: MIT / Apache-2.0. Installs into your home folder; no admin rights.',
                   'Note: this engine serves the API; the vault UI is bundled only in the container image.']
        if self.host.is_windows():
            commands = [['powershell', '-ExecutionPolicy', 'ByPass', '-c', 'irm https://astral.sh/uv/install.ps1 | iex']]
            details.insert(1, 'Source: https://astral.sh/uv/install.ps1 (the official installer).')
        else:
            script   = os.path.join(tempfile.gettempdir(), 'uv-install.sh')
            commands = [['curl', '-LsSf', '-o', script, 'https://astral.sh/uv/install.sh'], ['sh', script]]
            details.insert(1, 'Source: https://astral.sh/uv/install.sh (the official installer).')
        return dict(runtime='uv', title='uv', details=details, admin=False, commands=commands,
                    after=['sgit serve --runtime uv'])

    # ------------------------------------------------------------ running
    def describe(self, plan: dict) -> list:
        lines = [f'sgit serve install: {plan["title"]}', '']
        lines += [f'  {line}' for line in plan['details']]
        lines += ['', '  Commands, in order:']
        lines += [f'    $ {" ".join(argv)}' for argv in plan['commands']]
        if plan['admin']:
            lines += ['', '  Some steps need administrator rights: you will be asked for your password.']
        return lines

    def execute(self, plan: dict) -> int:
        """Run each command with the terminal attached; stop at the first failure. Returns
        the failing command's exit code, or 0."""
        for argv in plan['commands']:
            code = self.runner.run_visible(argv)
            if code != 0 and argv[:3] != ['podman', 'machine', 'init']:     # init fails when a machine exists
                return code
        return 0

    def require_release(self, release: dict, page: str) -> dict:
        """Never guess a download: without the release's real asset URL there is nothing to install."""
        if not release['url']:
            raise ValueError(f'could not look up the latest release on GitHub; download the installer from {page} '
                             f'and run it, then: sgit serve')
        return release

    def latest_release(self, url: str, suffix: str, prefer: str = '') -> dict:
        """dict(version, asset, url, size_mb) for a GitHub release asset ('' fields if unreachable)."""
        try:
            request = urllib.request.Request(url, headers={'Accept': 'application/vnd.github+json',
                                                           'User-Agent': 'sgit-ai'})
            with urllib.request.urlopen(request, timeout=15) as response:   # nosec B310: fixed https URL (GitHub releases API)
                data = json.loads(response.read().decode())
            assets = [a for a in data.get('assets') or [] if str(a.get('name', '')).endswith(suffix)]
            assets.sort(key=lambda a: prefer not in str(a.get('name', '')))
            if assets:
                return dict(version=str(data.get('tag_name') or ''), asset=str(assets[0]['name']),
                            url=str(assets[0]['browser_download_url']),
                            size_mb=round(int(assets[0].get('size') or 0) / 1e6, 1) or '')
        except Exception:   # nosec B110: lookup failed; require_release then refuses to guess
            pass
        return dict(version='', asset='', url='', size_mb='')
