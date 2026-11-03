# design-floor checker (vendored)

Copy of the ADR-0007 design floor checker, run by
[`design-floor.yml`](../.github/workflows/design-floor.yml). The source of truth, its tests and
its 62 fixtures live in `architecture-docs/design-floor/` (private); this copy exists because a
public reusable workflow cannot check out a private repository.

| File | From | SHA-256 |
|---|---|---|
| `check.mjs` (1.1.9) | `architecture-docs` @ `2c9ac1d` | `df809e4d8a09f6e41e885f870fcdb5db4bed91fa565637a1e8249cac4227b50b` |
| `package.json` | `architecture-docs` @ `439db24` (dev dependencies only: typescript, @types/node) | `87c6454671c60c2e4b33acbcaf3906c23256d4431566492c00bf235791d3628b` |
| `package-lock.json` | `architecture-docs` @ `439db24` | `abf854f0d567bec018deb66da55c7760e17df7acfe4df6af2de5c7f24bfaf8d2` |
| `tsconfig.json` | `architecture-docs` @ `eb9dbca` (type check only: self-test `checker-typecheck` runs `tsc`) | `9003e3c75014f7a193fee2de10b706520a516d57c00d6d5bfdf98f19ed521b03` |
| `globals.d.ts` | `architecture-docs` @ `eb9dbca` | `8eadeb70f5e910cf7c940721607048547cb6a300a01cfc1540e1d8b26e206977` |

Do not edit these files here. To update:

1. Change and test the checker in `architecture-docs` (`npm test` in `design-floor/`).
2. Copy these files here unchanged, update this table, and commit that on its own.
3. Set `FLOOR_REF` in `design-floor.yml` to that commit's SHA in a second commit, and release a
   new minor version.
