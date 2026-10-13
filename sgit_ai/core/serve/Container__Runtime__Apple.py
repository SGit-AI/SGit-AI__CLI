"""Container__Runtime__Apple — Apple's `container` tool (github.com/apple/container).

macOS on Apple silicon only; macOS 26 is the supported target (macOS 15 runs with reduced
networking). Each container is its own lightweight VM running a standard OCI image, so the
SG/Send image runs unchanged and no Docker is involved. Its CLI is docker-like but not
docker-compatible: `container system start`, `container image pull`, `container delete`,
`container inspect` (JSON).

Not yet run on a Mac by this code's author: the flags follow the project's documented
`run` options (-d, --name, -p/--publish, -v/--volume, -e, --user); `sgit serve` prints the
exact command on failure so it can be checked against `container run --help`.
"""
import json
from   sgit_ai.core.serve.Container__Runtime import Container__Runtime


class Container__Runtime__Apple(Container__Runtime):

    def name(self) -> str:
        return 'container'

    def describe(self) -> str:
        return "Apple container (macOS, Apple silicon)"

    def applies(self) -> bool:
        return self.host.is_apple_silicon()

    def ready_argv(self) -> list:
        return ['container', 'system', 'status']

    def start_service_argvs(self) -> list:
        return [['container', 'system', 'start']]

    def not_ready_hint(self) -> str:
        return 'Apple container is installed but its service is not running: `container system start`'

    def pull_argv(self, image: str) -> list:
        return ['container', 'image', 'pull', image]

    def run_argv(self, spec: dict) -> list:
        argv = ['container', 'run', '-d', '--rm', '--name', spec['name'], '-p', self.publish_flag(spec)]
        if spec.get('user'):
            argv += ['--user', spec['user']]
        return argv + ['-v', f'{spec["data_dir"]}:/data'] + self.env_flags(spec) + [spec['image']]

    def remove_argv(self, name: str) -> list:
        return ['container', 'delete', '--force', name]

    def running_argv(self, name: str) -> list:
        return ['container', 'inspect', name]

    def digest_argv(self, image: str) -> list:
        return ['container', 'image', 'inspect', image]

    def running(self, name: str) -> bool:
        result = self.runner.run(self.running_argv(name), timeout=30)
        if result['code'] != 0:
            return False
        try:
            data  = json.loads(result['out'] or '[]')
            items = data if isinstance(data, list) else [data]
            return any(str(item.get('status', '')).lower() == 'running' for item in items if isinstance(item, dict))
        except ValueError:
            return False

    def digest(self, image: str) -> str:
        result = self.runner.run(self.digest_argv(image), timeout=30)
        if result['code'] != 0:
            return ''
        text = result['out']
        start = text.find('sha256:')
        return f'{image.split(":")[0]}@{text[start:start + 71]}' if start >= 0 else ''
