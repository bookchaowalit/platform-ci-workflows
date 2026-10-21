# platform-ci-workflows

Reusable GitHub Actions workflows (`workflow_call`) for the CI and security baseline of
`bookchaowalit` repositories (DevSecOps Phase 1). Client repositories do not use these: they
get no CI/CD.

| Workflow | Does |
|---|---|
| [`ci-node.yml`](.github/workflows/ci-node.yml) | npm/pnpm install (lockfile required), Biome or ESLint, typecheck, Vitest / `test` script, optional coverage gate, optional build |
| [`ci-python.yml`](.github/workflows/ci-python.yml) | uv install, Ruff lint + format check, mypy or pyright, pytest (or a custom test command), optional coverage gate |
| [`security.yml`](.github/workflows/security.yml) | Gitleaks, Semgrep CE, OSV-Scanner, Trivy fs (vuln + IaC misconfig) |

Everything runs as pinned binaries or pinned packages, without Docker, so the same workflows
run on GitHub-hosted runners and on the Railway self-hosted runner.

## Where jobs run

| Repository | `runner` input | PostgreSQL |
|---|---|---|
| Public | `'"ubuntu-24.04"'` (default) | `postgres: true` starts the VM's preinstalled server |
| Private | `'["self-hosted","linux","x64","railway"]'` | `postgres: true` runs `start-postgres` (PostgreSQL 17 baked into the runner image) |

The hosted image is pinned to `ubuntu-24.04` rather than `ubuntu-latest`, which GitHub moves to
Ubuntu 26 from 2026-10-19; moving to a newer image is a deliberate change here, not a surprise.
Private repositories never run on the local machine. The runner image and its pitfalls are in
[`platform-ops-cli/infra/ci-runner`](https://github.com/bookchaowalit/platform-ops-cli/tree/main/infra/ci-runner).
The Railway runner has no Docker, so `services:` containers, image builds, image scans,
Testcontainers and ZAP are deferred to a later phase (see the ADR in `architecture-docs`).

With `postgres: true`, every job gets a fresh database `ci_<run>_<attempt>_<n>` and
`DATABASE_URL=postgresql://postgres@127.0.0.1:5432/<that database>` is exported. The database is
dropped when the job ends, and leftovers from cancelled runs are dropped at the next start (the
Railway runner and its PostgreSQL persist between jobs). Map it to the name your tests read inside `test-command`, for example
`CRM_TEST_DATABASE_URL="$DATABASE_URL" python -m unittest`.

## Usage

Reference the workflows by **commit SHA** with the tag as a comment; Renovate keeps both up to date.

```yaml
name: CI
on:
  push:
    branches: [main]
  pull_request:
permissions:
  contents: read
concurrency:
  group: ci-${{ github.ref }}
  cancel-in-progress: true
jobs:
  web:
    uses: bookchaowalit/platform-ci-workflows/.github/workflows/ci-node.yml@<sha> # v1.0.0
    with:
      working-directory: apps/web
      build-command: npm run build
  api:
    uses: bookchaowalit/platform-ci-workflows/.github/workflows/ci-python.yml@<sha> # v1.0.0
    with:
      working-directory: services/api
  security:
    uses: bookchaowalit/platform-ci-workflows/.github/workflows/security.yml@<sha> # v1.0.0
```

For a private repository add `runner: '["self-hosted","linux","x64","railway"]'` to every job.
A personal-account private repository needs its own runner service in the Railway
`ci-runners` project first. Because one repo-scoped runner takes one job at a time, jobs queue
on it rather than running in parallel.

### `auto` defaults

Each step's command input defaults to `auto`, which detects the tool from the files in
`working-directory`; pass a command to override it, or `""` to skip the step.

- **pnpm**: the version comes from `packageManager` in `package.json`, or the `pnpm-version` input.
- **Node lint**: `biome ci .` when `biome.json(c)` exists, else the `lint` script, else skipped with a warning.
- **Node typecheck**: the `typecheck` script, else `tsc --noEmit` when `tsconfig.json` exists.
- **Python install**: `uv sync --frozen --all-extras` with `uv.lock`; else `uv pip install -r` for
  `requirements.txt` / `requirements-dev.txt`; else `uv pip install -e ".[dev]"`.
- **Python lint**: `ruff check` and `ruff format --check` (`format-check: false` turns off the latter).
  A `ruff.toml` / `[tool.ruff]` in the repository decides the rule set.
- **Python typecheck**: mypy when `[tool.mypy]` / `mypy.ini` exists, pyright when
  `[tool.pyright]` / `pyrightconfig.json` exists, else skipped with a warning.
- **Python tests**: `python -m pytest -q`.

A tool installed in the project's own environment wins over the pinned default, so a repository can pin its own Ruff.

### Tests and coverage gate (TDD standard)

Both gates are **off by default**, so existing callers do not change. Turn them on per repository
as it adopts the TDD + SDD standard (ADR-0004 in `architecture-docs`).

| Input | Workflow | Effect |
|---|---|---|
| `require-tests: true` | `ci-node` | With `test-command: auto`, a missing `test` script fails the job instead of warning. (pytest already fails when it collects no tests.) |
| `coverage-threshold: "80"` | `ci-node` | Runs `vitest run` (needs `@vitest/coverage-v8` or `-istanbul`; Vitest wins when both are listed) or `jest` directly with coverage and fails when **line** coverage is below the threshold. This bypasses the `test` script: if it adds flags, env or a wrapper (`--project`, `NODE_OPTIONS`, dotenv), pass a custom `test-command` that writes `coverage/coverage-summary.json` (json-summary reporter). Set `test.coverage.include` (Vitest) or `collectCoverageFrom` (Jest), or files no test imports are left out of the total |
| `coverage-threshold: "80"` | `ci-python` | Runs `pytest --cov` (installs pinned `pytest-cov` if missing) and fails when **total** coverage is below the threshold (`coverage report --fail-under`). Set `[tool.coverage.run] source` so only your code is measured (and unimported files still count). A custom `test-command` must leave `.coverage` data itself; run `coverage combine` after `coverage run -p` |

The threshold is a number from 0 to 100. Coverage files left in the checkout are deleted before
the tests run, so only this run's data counts. Each run writes a coverage table to the job summary,
and when coverage is 2 or more points above the threshold the job adds a notice to raise it
(the ratchet rule of ADR-0004); the notice never fails the job.
Choose the starting threshold just below the repository's current coverage, then raise it; never
lower it without a recorded exception.

### Security policy

| Scanner | Fails when | Scope |
|---|---|---|
| Gitleaks | any secret | PR: the PR's commits. Push: the pushed range. Otherwise: full history. Merge-commit diffs included |
| Semgrep CE (`p/default`) | PR: a finding the PR introduces (only new findings are reported). Full scans on `main`: every finding reported, not failing unless `semgrep-block-full-scan: true`. Parse errors/timeouts raise a warning | whole checkout |
| OSV-Scanner | any known vulnerability, or a lockfile it could not parse | every lockfile / manifest |
| Trivy fs | fixable `HIGH`/`CRITICAL` vuln or misconfiguration | whole checkout, minus `node_modules` and `.venv` |

Every scanner uploads its SARIF report as a workflow artifact (14 days). Code-scanning upload is
not used, because private repositories on the free plan cannot receive it.

Suppress a finding only with a written reason, in the repository's own file:
`.gitleaksignore` (fingerprint), `# nosemgrep: <rule-id>` + reason, `osv-scanner.toml`
(`[[IgnoredVulns]]` with `reason` and `ignoreUntil`), `.trivyignore.yaml` (with `statement`).

## Versioning

- Tags `v1.x.y` are immutable; `v1` moves to the latest `v1.x.y`. Callers pin a SHA.
- Every action is pinned by SHA. Security binaries are pinned by version **and** SHA-256. After
  Renovate bumps a `*_VERSION`, run `scripts/tool-checksums.sh` and paste the new `*_SHA256`.
- [`self-test.yml`](.github/workflows/self-test.yml) runs actionlint, shellcheck and the security
  scan on this repository, calls `ci-node` / `ci-python` on the fixtures in `tests/fixtures/`, and
  runs [`tests/gates_test.py`](tests/gates_test.py), which executes the gate and Test step scripts
  against crafted inputs to prove the failure paths (below threshold, missing or stale data,
  zero lines, invalid thresholds, `require-tests`).
