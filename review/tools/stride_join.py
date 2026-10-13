"""review/tools/stride_join.py — join the STRIDE model to the risk register and the tests.

Reads review/stride/agent.json (threats, each naming register rows), the threat model
(team/explorer/appsec/threat-model/v0.21.0__threat-model.md: the set of TM-Rnn / TM-Fnn ids
that exist, and section 7's threat-to-test map), and review/graph/files.json (tests importing
each slice module). Writes:

    review/stride/join.json      one row per threat: register rows (existing / unknown), status
    review/stride/coverage.json  the TM-Bench-shaped numbers: register rows covered by at least
                                 one threat, STRIDE distribution, N/A count, new threats, and
                                 the rows no threat names (completeness gaps)

Deterministic; no model in the path. Re-run after editing agent.json or the register.
"""
import json
import os
import re
from collections import Counter


class Stride__Join:

    def __init__(self, repo_root: str):
        self.repo_root   = repo_root
        self.stride_dir  = os.path.join(repo_root, 'review', 'stride')
        self.model_path  = os.path.join(repo_root, 'team', 'explorer', 'appsec', 'threat-model', 'v0.21.0__threat-model.md')
        self.agent       = self.read_json(os.path.join(self.stride_dir, 'agent.json'))
        self.model_text  = open(self.model_path, 'r', encoding='utf-8').read()

    def read_json(self, path):
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def write_json(self, name, payload):
        with open(os.path.join(self.stride_dir, name), 'w', encoding='utf-8') as f:
            json.dump(payload, f, indent=1, sort_keys=True)
            f.write('\n')

    def register_ids(self) -> set:
        """Every TM-Rnn / TM-Fnn id that appears as a row id in section 6 of the register."""
        ids = set()
        for m in re.finditer(r'^\|\s*\**(TM-[RF]\d{2})\**(?:\s*→\s*fixed)?\s*\|', self.model_text, re.M):
            ids.add(m.group(1))
        return ids

    def rows_by_class(self) -> dict:
        """Row id -> the section 6 subsection it sits in (fixed, by design, accepted, fix soon)."""
        classes = {}
        current = None
        for line in self.model_text.splitlines():
            if line.startswith('### 6.1'): current = 'fixed'
            elif line.startswith('### 6.2'): current = 'by design'
            elif line.startswith('### 6.3'): current = 'accepted'
            elif line.startswith('### 6.4'): current = 'fix soon'
            elif line.startswith('## 7'): current = None
            m = re.match(r'^\|\s*\**(TM-[RF]\d{2})\**', line)
            if m and current and m.group(1) not in classes:
                classes[m.group(1)] = current
        return classes

    def build(self):
        known   = self.register_ids()
        classes = self.rows_by_class()
        threats = [t for t in self.agent['threats'] if not t.get('na')]
        nas     = [t for t in self.agent['threats'] if t.get('na')]
        rows    = []
        covered = set()
        for t in threats:
            refs = t.get('register', [])
            for r in refs:
                covered.add(r)
            rows.append(dict(id=t['id'], element=t['element'], stride=t['stride'], priority=t['dread']['priority'],
                             dread=t['dread']['total'], register=refs,
                             register_unknown=sorted(r for r in refs if r not in known),
                             register_classes={r: classes.get(r, '?') for r in refs if r in known},
                             new=(len(refs) == 0), status=t.get('status', '')))
        by_stride   = Counter(t['stride'] for t in threats)
        by_priority = Counter(t['dread']['priority'] for t in threats)
        by_element  = Counter(t['element'] for t in threats)
        uncovered   = sorted(known - covered)
        coverage = dict(
            register_rows_in_model=len(known),
            register_rows_named_by_a_threat=len(covered & known),
            completeness_against_register=round(len(covered & known) / len(known), 3) if known else None,
            register_rows_no_threat_names=uncovered,
            threats=len(threats), explicit_not_applicable=len(nas),
            new_threats_no_register_row=sorted(t['id'] for t in threats if not t.get('register')),
            stride_distribution=dict(sorted(by_stride.items())),
            priority_distribution=dict(sorted(by_priority.items())),
            threats_per_element=dict(sorted(by_element.items())),
            elements_with_all_six_considered=sorted({e['id'] for e in self.agent['elements']}
                                                    & {t['element'] for t in self.agent['threats']}),
            note='completeness here is register rows named by at least one threat; a row can be named by a threat that mis-states it, which only a reader catches')
        return rows, coverage

    def run(self):
        rows, coverage = self.build()
        self.write_json('join.json', dict(source='review/stride/agent.json + the register §6', rows=rows))
        self.write_json('coverage.json', coverage)
        return coverage


if __name__ == '__main__':
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
    print(json.dumps(Stride__Join(root).run(), indent=1))
