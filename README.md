# platform-ci-workflows

Reusable GitHub Actions workflows (`workflow_call`) for the CI and security baseline of
`bookchaowalit` repositories (DevSecOps Phase 1). Client repositories do not use these: they
get no CI/CD.

| Workflow | Does |
|---|---|
| [`ci-node.yml`](.github/workflows/ci-node.yml) | npm/pnpm install (lockfile required), Biome or ESLint, typecheck, Vitest / `test` script, optional build |
| [`ci-python.yml`](.github/workflows/ci-python.yml) | uv install, Ruff lint + format check, mypy or pyright, pytest (or a custom test command) |
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

With `postgres: true`, `DATABASE_URL=postgresql://postgres@127.0.0.1:5432/postgres` is
exported. Map it to the name your tests read inside `test-command`, for example
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

### Security policy

| Scanner | Fails when | Scope |
|---|---|---|
| Gitleaks | any secret | PR: the PR's commits. Push: the pushed range. Otherwise: full history |
| Semgrep CE (`p/default`) | PR: a finding the PR introduces. Full scans: report only (`semgrep-block-full-scan: true` to fail) | whole checkout |
| OSV-Scanner | any known vulnerability | every lockfile / manifest |
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
  scan on this repository.
