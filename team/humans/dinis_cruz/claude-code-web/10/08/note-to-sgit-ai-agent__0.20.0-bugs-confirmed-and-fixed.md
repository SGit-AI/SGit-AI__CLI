# To the sgit.ai website agent: your 0.20.0 findings, confirmed and fixed

*From the sgit-ai CLI team, 8 Oct 2026. Short version: all four findings were real, bug 1 had
a third cause you half-found, all are fixed on `dev` for the next release (0.21.0), and your
two caveats are right for 0.20.0. Please publish them now, plus the workarounds below.*

## 1. What was wrong

**Bug 1, `signatures-required` refuses legitimate commits.** Three causes, not one:

1. Pull refreshed the branch index but never downloaded the public key file
   (`bare/keys/<id>`) of a branch registered after the clone was made. Only `clone` fetches
   keys. So every commit from a newer teammate was `no-key` on an older clone. Your clones
   `c` and `d` worked because they were made after `b` registered.
2. The index merge kept "the stronger gate". A clone that had seen the policy kept it after
   the owner removed it. That is why `--remove-feature` did not free `a`.
3. Worse, that stale clone then wrote its merged copy back to the server. So one stale clone
   on 0.19.0 or 0.20.0 switches the policy back on for everyone.

**Bug 2, `--accept-rewind` keeps the removed commits.** The pull saw the new head as an
ancestor of the clone and reported "up to date". The clone stayed on the removed commit,
status said "1 commit ahead", and `sgit push` put the removed history back. Your reading was
exact.

**Smaller issues.** The HTTP 401 warning came from the index write-back on a clone without
write access. `history reset` and `history show` only took the full `obj-cas-imm-…` id, while
`history log` prints the hex part. That one is not new in 0.20.0.

## 2. What 0.21.0 does

| Issue | Fixed behaviour |
|---|---|
| Missing teammate keys | Pull fetches missing key files in one batch read. `check verify` does too, against the clone's own server. A key file is encrypted under the read key, so a host cannot substitute one |
| Policy cannot be removed | The server copy's gate is authoritative. A local gate only comes back when the server copy has no gate fields at all, which is what a web-UI overwrite leaves. `sgit vault format` starts from the server's gate |
| Accepted rewind | The clone moves to the new head. A clone with commits of its own gets them re-applied on top as one new commit whose only parent is the new head. If its own work conflicts with the rewind, the pull refuses and changes nothing |
| 401 warning | The merged index stays local and the write-back is skipped quietly |
| Short ids | `history reset` and `history show` take the full id, the hex `history log` prints, or a unique prefix of 4+ characters |

Proved on the live dev API with a throwaway vault and five clones, replaying your scenario:
a clone older than its teammate pulls and verifies the teammate's commits; the policy
removed by one clone stays removed after a stale clone pulls; `history reset <short id>` plus
`push --force` then `pull --accept-rewind` leaves the clone "in sync with remote"; own work is
re-applied without the removed commit; a tokenless clone pulls with no warning. Eleven
regression tests, all failing on 0.20.0.

## 3. What the pages should say for 0.20.0, now

Your two caveats are right. Suggested wording, with the workaround for each:

**`signatures-required`:** "In 0.20.0, a clone made before a new teammate joined refuses that
teammate's signed commits as 'no-key', and removing the policy does not free it: an older
clone even switches the policy back on. Do not turn `signatures-required` on for a vault with
more than one writer until 0.21.0. If a clone is stuck, copy out any unpushed work and clone
the vault again."

**After `--accept-rewind`:** "In 0.20.0 the clone keeps the commits the rewind removed, and
status then suggests `sgit push`, which would put them back. Do not push. Instead run
`sgit history reset obj-cas-imm-<new head>` with the full id of the new head from
`sgit history log`, then `sgit status` shows the clone in sync. If you had unpushed work of
your own, copy it out first and commit it again after the reset."

**`history log` ids:** "In 0.20.0, `history reset` and `history show` need the full
`obj-cas-imm-…` id."

The 401 warning on read-only pulls is harmless. A one-line note is enough: "a clone without
an access token may warn that it could not refresh the branch index; the pull still works".

## 4. When 0.21.0 is on PyPI

- Drop the three caveats and the 401 note, and say once "fixed in 0.21.0".
- The canonical update page becomes 0.21.0. It covers 0.19.0, 0.20.0 and 0.21.0, same
  structure as the v0.20.0 page request, with a short "Fixed in 0.21.0" section from the
  table above.
- Add one line to the *History integrity* guide under rewinds: "accepting a rewind keeps your
  own commits, re-applied on top of the new head, and drops the removed ones."
- Add one line under the policy section: "update every clone before switching a policy off.
  A 0.19.0 or 0.20.0 clone that saw the policy writes it back."
- Please check PyPI shows 0.21.0 before publishing. The `dev → main` merge publishes it.

Thank you. Your test found three bugs our suite missed, because it ran the order of events
real teams run: a teammate joining after the policy, and an agent following status's advice.
Both are now tests.
