# Product

<!-- impeccable:product-schema 1 -->

## Platform

reusable GitHub Actions workflows (`workflow_call`) and the vendored ADR-0007 design-floor checker

## Users

- The owner's repositories (public and private, personal and org), which call these workflows by
  commit SHA. Client repositories do not: they get no CI/CD.
- Agents changing those repositories, who adopt a workflow instead of copying CI steps.

## Product Purpose

One reviewed CI, security and deploy baseline instead of a copy per repository: Node and Python
CI with optional coverage gates, the security scans (Gitleaks, Semgrep CE, OSV-Scanner, Trivy),
Railway and Vercel deploy verification, and the design-floor check (README table).

Success: callers stay on a pinned release, `self-test.yml` exercises every workflow on each
change, and a new release never breaks a caller silently.

## Positioning

The DevSecOps Phase 1 baseline (ADR-0003, ADR-0004, ADR-0007 in architecture-docs). Everything
runs as pinned binaries or packages without Docker, so the same workflows run on GitHub-hosted
runners and on the self-hosted runner pool for private repositories.

## Operating Context

- Releases are semver tags with GitHub releases; the `v1` tag follows the latest v1 release.
  Callers pin a full commit SHA with the tag in a comment.
- `design-floor/` is a vendored copy of the architecture-docs checker (`design-floor/SOURCE.md`
  lists each file, its source commit and hash), because a public workflow cannot check out a
  private repository. Its `tsconfig.json` is type-checked in `self-test.yml`.
- CI: `self-test.yml` (actionlint, the workflows against fixtures in `tests/fixtures/`, the gate
  and deploy script tests, the checker type check) on GitHub-hosted runners (public repository).

Sentry waiver: nothing here runs as a service; the workflows run inside callers' CI, where a failure is a red job on that commit.

## Capabilities and Constraints

- Never stores secrets: callers pass their own through `secrets:` inputs.
- Deploy workflows only verify or trigger the platform's own deploy of an exact commit, then
  smoke-test it; a red CI never deploys.
- Out of scope: client repositories and any repository the owner has not opted in.

## Measures

- `self-test.yml` green on `main` (target: always).
- Callers on the latest release of each workflow they use (the R4 adoption report covers the
  design-floor job).
