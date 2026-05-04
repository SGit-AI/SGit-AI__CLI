import json

from osbot_utils.type_safe.Type_Safe          import Type_Safe
from sgit_ai.schemas.Schema__Dump_Result      import Schema__Dump_Result
from sgit_ai.schemas.Schema__Dump_Diff        import Schema__Dump_Diff


class Vault__Dump_Diff(Type_Safe):
    """Compares two Schema__Dump_Result snapshots and reports all divergences.

    Implements Feature 3 from the brief: diff-state.
    """

    def diff(self, dump_a: Schema__Dump_Result,
             dump_b: Schema__Dump_Result,
             label_a: str = '', label_b: str = '') -> Schema__Dump_Diff:
        """Compare two dump snapshots and return a Schema__Dump_Diff.

        All comparisons are by ID strings — no crypto operations are needed.
        """
        result = Schema__Dump_Diff(
            label_a = label_a or str(dump_a.source) if dump_a.source else 'A',
            label_b = label_b or str(dump_b.source) if dump_b.source else 'B',
        )

        self._diff_refs(dump_a, dump_b, result)
        self._diff_objects(dump_a, dump_b, result)
        self._diff_branches(dump_a, dump_b, result)
        self._diff_danglings(dump_a, dump_b, result)
        self._diff_commits(dump_a, dump_b, result)

        # Counts
        result.refs_diff_count     = (len(result.refs_only_in_a) +
                                      len(result.refs_only_in_b) +
                                      len(result.refs_diverged))
        result.objects_diff_count  = (len(result.objects_only_in_a) +
                                      len(result.objects_only_in_b))
        result.branches_diff_count = (len(result.branches_only_in_a) +
                                      len(result.branches_only_in_b) +
                                      len(result.branches_head_differ))
        result.total_diffs         = (result.refs_diff_count +
                                      result.objects_diff_count +
                                      result.branches_diff_count +
                                      len(result.commits_only_in_a) +
                                      len(result.commits_only_in_b))
        result.identical           = int(result.total_diffs) == 0

        return result

    def diff_from_files(self, path_a: str, path_b: str) -> Schema__Dump_Diff:
        """Load two JSON dump files and diff them."""
        dump_a = self._load_dump(path_a)
        dump_b = self._load_dump(path_b)
        return self.diff(dump_a, dump_b, label_a=path_a, label_b=path_b)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _load_dump(self, path: str) -> Schema__Dump_Result:
        with open(path, 'r') as fh:
            data = json.load(fh)
        return Schema__Dump_Result.from_json(data)

    def _diff_refs(self, a: Schema__Dump_Result, b: Schema__Dump_Result,
                   result: Schema__Dump_Diff) -> None:
        refs_a = {str(r.ref_id): str(r.commit_id) if r.commit_id else ''
                  for r in a.refs if r.ref_id}
        refs_b = {str(r.ref_id): str(r.commit_id) if r.commit_id else ''
                  for r in b.refs if r.ref_id}

        ids_a = set(refs_a.keys())
        ids_b = set(refs_b.keys())

        result.refs_only_in_a = sorted(ids_a - ids_b)
        result.refs_only_in_b = sorted(ids_b - ids_a)

        for ref_id in sorted(ids_a & ids_b):
            if refs_a[ref_id] != refs_b[ref_id]:
                result.refs_diverged.append(ref_id)

    def _diff_objects(self, a: Schema__Dump_Result, b: Schema__Dump_Result,
                      result: Schema__Dump_Diff) -> None:
        ids_a = {str(o.object_id) for o in a.objects if o.object_id}
        ids_b = {str(o.object_id) for o in b.objects if o.object_id}

        result.objects_only_in_a = sorted(ids_a - ids_b)
        result.objects_only_in_b = sorted(ids_b - ids_a)

    def _diff_branches(self, a: Schema__Dump_Result, b: Schema__Dump_Result,
                       result: Schema__Dump_Diff) -> None:
        branches_a = {str(br.branch_id): str(br.head_commit) if br.head_commit else ''
                      for br in a.branches if br.branch_id}
        branches_b = {str(br.branch_id): str(br.head_commit) if br.head_commit else ''
                      for br in b.branches if br.branch_id}

        ids_a = set(branches_a.keys())
        ids_b = set(branches_b.keys())

        result.branches_only_in_a = sorted(ids_a - ids_b)
        result.branches_only_in_b = sorted(ids_b - ids_a)

        for bid in sorted(ids_a & ids_b):
            if branches_a[bid] != branches_b[bid]:
                result.branches_head_differ.append(bid)

    def _diff_danglings(self, a: Schema__Dump_Result, b: Schema__Dump_Result,
                        result: Schema__Dump_Diff) -> None:
        result.dangling_in_a = [str(d) for d in a.dangling_ids]
        result.dangling_in_b = [str(d) for d in b.dangling_ids]

    def _diff_commits(self, a: Schema__Dump_Result, b: Schema__Dump_Result,
                      result: Schema__Dump_Diff) -> None:
        ids_a = {str(c.commit_id) for c in a.commits if c.commit_id}
        ids_b = {str(c.commit_id) for c in b.commits if c.commit_id}

        result.commits_only_in_a = sorted(ids_a - ids_b)
        result.commits_only_in_b = sorted(ids_b - ids_a)
