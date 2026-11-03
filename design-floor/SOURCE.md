# design-floor checker (vendored)

Copy of the ADR-0007 design floor checker, run by
[`design-floor.yml`](../.github/workflows/design-floor.yml). The source of truth, its tests and
its 48 fixtures live in `architecture-docs/design-floor/` (private); this copy exists because a
public reusable workflow cannot check out a private repository.

| File | From | SHA-256 |
|---|---|---|
| `check.mjs` (1.1.3) | `architecture-docs` @ `63cc5b4` | `07bca38f6aba32be86552ab9454e340edd3b2d446402ece57d60bf3b9f6b3f70` |
| `package.json` | `architecture-docs` @ `439db24` (dev dependencies only: typescript, @types/node) | `87c6454671c60c2e4b33acbcaf3906c23256d4431566492c00bf235791d3628b` |
| `package-lock.json` | `architecture-docs` @ `439db24` | `abf854f0d567bec018deb66da55c7760e17df7acfe4df6af2de5c7f24bfaf8d2` |

Do not edit these files here. To update:

1. Change and test the checker in `architecture-docs` (`npm test` in `design-floor/`).
2. Copy the three files here unchanged, update this table, and commit that on its own.
3. Set `FLOOR_REF` in `design-floor.yml` to that commit's SHA in a second commit, and release a
   new minor version.
