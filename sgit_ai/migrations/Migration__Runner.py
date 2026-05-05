import json, os, time
from datetime import datetime, timezone
from osbot_utils.type_safe.Type_Safe import Type_Safe
from sgit_ai.migrations.Migration__Registry                  import Migration__Registry
from sgit_ai.schemas.migrations.Schema__Migration_Record     import Schema__Migration_Record
from sgit_ai.schemas.migrations.Schema__Migrations_Applied   import Schema__Migrations_Applied
from sgit_ai.safe_types.Safe_Str__Migration_Name             import Safe_Str__Migration_Name
from sgit_ai.safe_types.Safe_Str__ISO_Timestamp              import Safe_Str__ISO_Timestamp
from sgit_ai.safe_types.Safe_UInt__Timestamp                 import Safe_UInt__Timestamp

MIGRATIONS_FILE = os.path.join('local', 'migrations.json')

class Migration__Runner(Type_Safe):
    registry : Migration__Registry

    def _sg_dir(self, vault_dir: str) -> str:
        return os.path.join(vault_dir, '.sg_vault')

    def _load_applied(self, sg_dir: str) -> set:
        path = os.path.join(sg_dir, MIGRATIONS_FILE)
        if not os.path.isfile(path):
            return set()
        with open(path) as f:
            data = json.load(f)
        applied = Schema__Migrations_Applied.from_json(data)
        return {str(r.name) for r in applied.records}

    def _save_record(self, sg_dir: str, name: str, duration_ms: int, stats: dict):
        path = os.path.join(sg_dir, MIGRATIONS_FILE)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        raw = {'records': []}
        if os.path.isfile(path):
            with open(path) as f:
                raw = json.load(f)
        applied = Schema__Migrations_Applied.from_json(raw)
        record  = Schema__Migration_Record(
            name        = Safe_Str__Migration_Name(name),
            applied_at  = Safe_Str__ISO_Timestamp(
                            datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')),
            duration_ms = Safe_UInt__Timestamp(duration_ms),
            n_trees     = Safe_UInt__Timestamp(stats.get('n_trees',   0)),
            n_commits   = Safe_UInt__Timestamp(stats.get('n_commits', 0)),
            n_refs      = Safe_UInt__Timestamp(stats.get('n_refs',    0)),
        )
        applied.records.append(record)
        with open(path, 'w') as f:
            json.dump(applied.json(), f, indent=2)

    def plan(self, vault_dir: str, read_key: bytes) -> list:
        sg_dir  = self._sg_dir(vault_dir)
        applied = self._load_applied(sg_dir)
        result  = []
        for m in self.registry.all_migrations():
            if m.migration_name() not in applied and not m.is_applied(sg_dir, read_key):
                result.append(m.migration_name())
        return result

    def apply(self, vault_dir: str, read_key: bytes) -> list:
        sg_dir  = self._sg_dir(vault_dir)
        applied = self._load_applied(sg_dir)
        done    = []
        for m in self.registry.all_migrations():
            if m.migration_name() in applied or m.is_applied(sg_dir, read_key):
                continue
            t0    = int(time.monotonic() * 1000)
            stats = m.apply(sg_dir, read_key)
            dur   = int(time.monotonic() * 1000) - t0
            self._save_record(sg_dir, m.migration_name(), dur, stats)
            done.append(m.migration_name())
        return done

    def status(self, vault_dir: str) -> list:
        sg_dir = self._sg_dir(vault_dir)
        path   = os.path.join(sg_dir, MIGRATIONS_FILE)
        if not os.path.isfile(path):
            return []
        with open(path) as f:
            raw = json.load(f)
        applied = Schema__Migrations_Applied.from_json(raw)
        return [r.json() for r in applied.records]
