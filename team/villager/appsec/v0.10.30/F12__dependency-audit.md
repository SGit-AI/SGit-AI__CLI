# F12 — Dependency CVE / Version Audit

**Severity:** MEDIUM — version floor too low; environment ships old version
**Class:** Supply chain
**Disposition:** REAL-FIX-NEEDED (bump pin) + DOCUMENT
**Files:** `pyproject.toml`

## 1. Declared Pins

```toml
[tool.poetry.dependencies]
python       = ">=3.11"
osbot-utils  = ">=3.70.0"
cryptography = ">=43.0.0"
```

Floor of `cryptography >= 43.0.0` is reasonable (released August 2024).
However:

## 2. Actual Resolved Versions in This Sandbox

```
$ pip list | grep -i cryptography
cryptography       41.0.7
```

The runtime in this sandbox has **cryptography 41.0.7** installed, **below
the declared floor**. This means:

- The CI test runner may not be enforcing the pin.
- Developer environments may silently run an older `cryptography` version.
- `osbot-utils` is not installed at all (`pip show osbot-utils` →
  "not found"), suggesting the tests don't actually import it in this
  environment, OR they do via a sibling `pip install -e` setup that wasn't
  applied here.

**Recommendation:** investigate why `pip install -e ".[dev]"` did not install
`cryptography>=43.0.0` and `osbot-utils`. Add a CI step that runs
`pip-audit` or at minimum `pip check` and `pip list` to surface the
divergence.

## 3. Known CVEs in Affected Range

For `cryptography 41.0.7` specifically (this is what's installed, NOT what
the pin requires):

- **GHSA-3ww4-gg4f-jr7f / CVE-2023-50782** — Bleichenbacher timing oracle
  in PKCS#1 v1.5 RSA decryption. Fixed in `42.0.0`. **Not exploitable in
  sgit-ai** because we use AES-GCM and ECC (Ed25519/X25519 via PKI), not
  RSA-PKCS1v15.
- **CVE-2024-26130** — NULL-pointer dereference when loading malformed
  PKCS#12. Fixed in `42.0.4`. **Not exploitable** — sgit-ai does not load
  PKCS#12.
- **CVE-2024-0727** — OpenSSL DoS via crafted PKCS#12. Same — not used.
- **PYSEC-2024-228** — `X509.public_key()` with malformed subjectPublicKeyInfo.
  Sgit-ai does not parse external X.509.

**Net assessment:** the cryptography 41.0.7 installed here has known CVEs
but none are exploitable from sgit-ai's call surface (we use only AES-GCM,
HKDF-SHA256, PBKDF2HMAC-SHA256, and Ed25519/X25519 from
`cryptography.hazmat.primitives`).

**However:** running unsupported `cryptography` versions in production
environments is a hygiene failure even if no CVE is reachable today.

For `cryptography >= 43.0.0` (the declared floor):
- 43.0.0 (Aug 2024): no critical AES-GCM / HKDF / PBKDF2 advisories at audit
  time.
- Latest stable should be checked at release time; recommend bump to
  `>=44.0.0` if available, or pin to a specific tested version like
  `==43.0.1`.

## 4. `osbot-utils` Audit

- Pin `>=3.70.0`. The Type_Safe framework has no published security
  advisories in the project's GitHub issue tracker as of the audit date.
- It is a small library maintained by The Cyber Boardroom; supply chain
  trust is contingent on the upstream's release process.
- **Recommend pinning to a known-tested patch level** rather than `>=` to
  avoid silent upgrades pulling in breaking Type_Safe behaviour. The
  Architect should comment on this — a `~3.70` (compatible release) pin
  may be more appropriate than `>=3.70`.

## 5. Transitive Dependencies

`cryptography` pulls in `cffi` (which pulls in `pycparser`). No known critical
CVEs in either as of audit time. `cffi` ships C extensions; if Python 3.13
or 3.14 wheels lag, users may be forced to a source build that requires
`libssl-dev`. Operational note, not a security finding.

## 6. Tooling Recommendation

Add to CI:

```bash
pip install pip-audit
pip-audit --strict  # fail on any vulnerability
pip check           # consistency
```

Run on every PR. This catches:
- Pin drift (43.0.0 → 41.0.7 type events).
- New CVEs in transitive deps.
- Unsatisfied pins.

## 7. Disposition

- **Real fix:** investigate why the dev environment in this sandbox has
  41.0.7 instead of `>=43.0.0`. Either:
  - The lock file is missing.
  - `pip install -e ".[dev]"` was not run before the analysis.
  - The CI image diverges from poetry's resolution.
- **Real fix:** add `pip-audit` to CI (DevOps).
- **Doc:** record the audited-clean cryptography call surface (only AES-GCM,
  HKDF-SHA256, PBKDF2, Ed25519, X25519). Future audits can shortcut by
  comparing against this list.
- **Escalate to DevOps:** CI integration of `pip-audit`.
