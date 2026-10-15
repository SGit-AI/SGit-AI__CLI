"""review/tools/security_json.py — one .security.json per slice file, from data already in review/.

The house schema (threat-modeling.sgit.ai/practice/security-json): attack_surface,
vulnerabilities (with risk_decision), secrets_exposure, dependencies (with
trust_boundary_crossings), redundant_code. This tool fills each record from:

    review/graph/*.json            classes, methods, calls, tests importing the module (parser-derived)
    review/intent/mechanisms.json  which mechanisms a file implements, and their register rows
    review/findings/*.json         every finding record that names the file
    review/context/functions/      the dossier files for the module (counted and linked, not parsed)

It writes review/security/<path>.security.json. Fields the data cannot fill are left as explicit
`null` or an empty list, never guessed: a record says what the review knows about the file and
where to read more, and nothing else. Re-run after the findings or the graph change.
"""
import glob
import json
import os
import re


class Security__Json:

    def __init__(self, repo_root: str):
        self.root     = repo_root
        self.graph    = {n: self.read(os.path.join('review', 'graph', f'{n}.json'))['nodes']
                         for n in ('files', 'classes', 'methods')}
        self.mechs    = self.read(os.path.join('review', 'intent', 'mechanisms.json'))['nodes']
        self.slice    = self.read(os.path.join('review', 'slice.json'))
        self.findings = self.load_findings()
        self.context  = sorted(os.listdir(os.path.join(repo_root, 'review', 'context', 'functions')))

    def read(self, rel):
        with open(os.path.join(self.root, rel), 'r', encoding='utf-8') as f:
            return json.load(f)

    def load_findings(self) -> list:
        out = []
        for path in sorted(glob.glob(os.path.join(self.root, 'review', 'findings', '*.json'))):
            if path.endswith('ranked.json'):
                continue
            d = self.read(os.path.relpath(path, self.root))
            for r in d.get('findings', []):
                r = dict(r); r['tool'] = d['tool'].split(' (')[0]
                out.append(r)
        return out

    def group_of(self, path: str) -> str:
        for g, spec in self.slice['groups'].items():
            if path in spec['files']:
                return g
        return ''

    def context_files_for(self, path: str) -> list:
        stem = path.replace('sgit_ai/', '').replace('.py', '').replace('/', '__')
        return [f for f in self.context if f.startswith(stem + '__')]

    def record(self, file_node: dict) -> dict:
        path     = file_node['path']
        group    = self.group_of(path)
        methods  = [m for m in self.graph['methods'] if m['path'] == path]
        classes  = [c for c in self.graph['classes'] if c['path'] == path]
        findings = [f for f in self.findings if f.get('file') == path]
        mechs    = [m for m in self.mechs if path in m['files']]
        calls    = sorted({c for m in methods for c in m['resolved_calls']})
        crossings = sorted({c for c in calls if self.group_of_qualified(c) not in ('', group)})
        status_of = lambda f: f.get('status', '').split(' ')[0].rstrip(';,(')
        vulns = [dict(id=f['id'], tool=f['tool'], line=f.get('line'), title=f.get('title') or ('same as ' + str(f.get('same_as', ''))), status=status_of(f),
                      confidence=f.get('confidence'), register=f.get('register', []),
                      risk_decision=self.risk_decision(f)) for f in findings]
        return {
            'file': path, 'group': group, 'lines': file_node['lines'], 'sha256': file_node['sha256'],
            'written_by': 'review/tools/security_json.py from review/ data (2026-10-11); no model in this tool',
            'attack_surface': {
                'boundary': self.slice['groups'].get(group, {}).get('boundary'),
                'mechanisms_implemented': [dict(id=m['id'], mechanism=m['mechanism'], guarantees=m['guarantees'],
                                                does_not_guarantee=m['does_not_guarantee']) for m in mechs],
                'classes': [c['qualified'] for c in classes],
                'methods': len(methods),
                'tests_importing_this_module': len(file_node.get('tests_importing', [])),
            },
            'vulnerabilities': vulns,
            'secrets_exposure': self.secrets_exposure(path, findings),
            'dependencies': {
                'resolved_calls_within_the_slice': calls,
                'trust_boundary_crossings': crossings,
                'register_rows': sorted({r for m in mechs for r in m['register']} | {r for f in findings for r in f.get('register', [])}),
            },
            'redundant_code': [f['title'] for f in findings if 'no production caller' in f.get('title', '') or 'dead' in f.get('title', '').lower()],
            'context': {'dossier_files': self.context_files_for(path), 'where': 'review/context/functions/'},
        }

    def group_of_qualified(self, qualified: str) -> str:
        """The slice group of a resolved call target, by the file its module lives in."""
        module = qualified
        while module:
            path = module.replace('.', '/') + '.py'
            g = self.group_of(path)
            if g:
                return g
            module = module.rsplit('.', 1)[0] if '.' in module else ''
        return ''

    def risk_decision(self, f: dict):
        st = f.get('status', '')
        if st.startswith('VULN') and 'fixed' in st:
            return dict(decision='fixed', owner='sgit-ai CLI agent', rationale=st, evidence=f.get('fixed'))
        if st.startswith('KNOWN'):
            return dict(decision='accepted in the register', owner='Dinis Cruz', rationale=st, rows=f.get('register', []))
        if st.startswith('CLEARED'):
            return dict(decision='not a finding', owner='sgit-ai CLI agent', rationale=st)
        return dict(decision='open', owner=None, rationale='awaiting the step-4 verification or a fix',
                    proposed=f.get('proposed'))

    def secrets_exposure(self, path: str, findings: list) -> dict:
        names = ('key', 'token', 'secret', 'passphrase', 'pem')
        touches = any(n in path.lower() for n in names) or path.endswith(('CLI__Vault.py', 'CLI__Main.py', 'CLI__Debug_Log.py'))
        related = [f['id'] for f in findings if any(n in f.get('title', '').lower() for n in names)]
        return dict(file_handles_or_prints_secrets=touches, findings_about_secrets=related,
                    note='see the dossier for the exact functions; TM-R14/TM-R15 cover keys on argv, stdout and disk' if touches else None)

    def run(self) -> int:
        out_dir = os.path.join(self.root, 'review', 'security')
        count = 0
        for f in self.graph['files']:
            if not f['path'].endswith('.py'):
                continue
            rec  = self.record(f)
            dest = os.path.join(out_dir, f['path'] + '.security.json')
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, 'w', encoding='utf-8') as fh:
                json.dump(rec, fh, indent=1, sort_keys=True, ensure_ascii=False); fh.write('\n')
            count += 1
        return count


if __name__ == '__main__':
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
    print('records written:', Security__Json(root).run())
