# Supply Chain Risk Report — `SGit-AI__CLI`

**Scanned:** `/home/user/SGit-AI__CLI`  
**Commit:** `5c409ac7b0d5`  
**Manifests read:** `pyproject.toml`, `requirements-test.txt`  
**Scanned at:** 2026-10-11T22:51:23+00:00  
**Direct dependencies:** 5 (PyPI 5)

## Summary

- **No known advisory affects any of the 5 direct dependencies** — but 5 of them were not checked at a project-resolved version (latest-release fallback or go.mod minimum; see Method and caveats).
- Transitive dependencies were **not examined**: no lockfile resolves the transitive tree (package-lock.json, uv.lock, or a go 1.17+ go.mod).
- 0 of 5 dependencies carry at least one finding, 0 of which reach production.
- Weakest coverage: **Repository archived**, established for 0 of 5; the Coverage section lists every criterion.

## Production dependencies

Every direct dependency is declared as a development dependency, so none
of them ships in the built artifact.

## Findings

No dependency was flagged on these criteria.

## Upstream repository and CI hygiene — OpenSSF Scorecard

These criteria describe each dependency's own repository, not the audited
project. Remediation, where any exists, is upstream.

No criterion in this tier was assessable for any dependency.

## Transitive advisories

Not examined: no lockfile resolves the transitive tree (package-lock.json, uv.lock, or a go 1.17+ go.mod). Commit a lockfile to close this gap.

## Informational

Measured, not flagged.

- **Publish provenance**: not determinable for any dependency in this project.
- **Security policy published**: not determinable for any dependency in this project.
- **Download volume**: not determinable for any dependency in this project.

## Coverage

What was and was not measured, per criterion.

| Criterion | Tier | Assessed | Flagged | Not assessable |
|---|---|---|---|---|
| Known advisories | A | 5/5 | 0 | 0 |
| Deprecated or yanked | A | 5/5 | 0 | 0 |
| Repository archived | A | 0/5 | 0 | 5 |
| Maintenance activity | A | 0/5 | 0 | 5 |
| Publisher concentration | B | 0/5 | 0 | 5 |
| Install-time script execution | B | 0/5 | 0 | 5 |
| Dangerous CI workflow | scorecard | 0/5 | 0 | 5 |
| CI token permissions | scorecard | 0/5 | 0 | 5 |
| Checked-in binaries | scorecard | 0/5 | 0 | 5 |
| Changes reviewed by a second person | scorecard | 0/5 | 0 | 5 |
| Publish provenance | info | 0/5 | 0 | 5 |
| Security policy published | info | 0/5 | 0 | 5 |
| Download volume | info | 0/5 | 0 | 5 |

## Not assessable

**Repository archived**

- 5 dependencies — the GitHub API did not answer: `coverage`, `cryptography`, `osbot-utils`, `pytest`, `pytest-cov`

**Checked-in binaries**

- 5 dependencies — the GitHub API did not answer: `coverage`, `cryptography`, `osbot-utils`, `pytest`, `pytest-cov`

**Changes reviewed by a second person**

- 5 dependencies — the GitHub API did not answer: `coverage`, `cryptography`, `osbot-utils`, `pytest`, `pytest-cov`

**Dangerous CI workflow**

- 5 dependencies — the GitHub API did not answer: `coverage`, `cryptography`, `osbot-utils`, `pytest`, `pytest-cov`

**Download volume**

- 5 dependencies — PyPI's download counters are disabled and return -1: `coverage`, `cryptography`, `osbot-utils`, `pytest`, `pytest-cov`

**Install-time script execution**

- 5 dependencies — install-time execution depends on whether a wheel or an sdist is installed, which this collector does not determine: `coverage`, `cryptography`, `osbot-utils`, `pytest`, `pytest-cov`

**Publish provenance**

- 5 dependencies — PyPI publish attestations are not read by this collector: `coverage`, `cryptography`, `osbot-utils`, `pytest`, `pytest-cov`

**Publisher concentration**

- 5 dependencies — PyPI publishes no upload ACL, so who can publish this package is not observable: `coverage`, `cryptography`, `osbot-utils`, `pytest`, `pytest-cov`

**Security policy published**

- 5 dependencies — the GitHub API did not answer: `coverage`, `cryptography`, `osbot-utils`, `pytest`, `pytest-cov`

**Maintenance activity**

- 5 dependencies — the GitHub API did not answer: `coverage`, `cryptography`, `osbot-utils`, `pytest`, `pytest-cov`

**CI token permissions**

- 5 dependencies — the GitHub API did not answer: `coverage`, `cryptography`, `osbot-utils`, `pytest`, `pytest-cov`

## Method and caveats

- 3 Poetry dependencies in the tool.poetry.dependencies table were not parsed; only PEP 621 and PEP 735 tables are read.
- 5 dependencies are specified as a version range with no lockfile, so their advisories were matched against the current latest release rather than against what this project installs — commit a lockfile for an exact answer: coverage, cryptography, osbot-utils, pytest, pytest-cov
- Optional tooling detected: npm. Not installed, so not used: bundler-audit, cargo-audit, osv-scanner, pip-audit.
- Direct dependencies only. Advisories attach to the package that ships the affected code, so an umbrella package can look clean while its components are not — rails 5.0.0 reports 0 advisories where actionpack 5.0.0 reports 10. Transitive dependencies were not examined: no lockfile resolves the transitive tree (package-lock.json, uv.lock, or a go 1.17+ go.mod).
- HTTP sources: 8 fetched, 5 served from cache (oldest 0.0h old), 0 refetched as stale, 0 unavailable offline, 5 errors.
