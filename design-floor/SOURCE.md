# design-floor checker (vendored)

Copy of the ADR-0007 design floor checker, run by
[`design-floor.yml`](../.github/workflows/design-floor.yml). The source of truth, its tests and
its 17 fixtures live in `architecture-docs/design-floor/` (private); this copy exists because a
public reusable workflow cannot check out a private repository.

| File | From | SHA-256 |
|---|---|---|
| `check.mjs` (1.0.3) | `architecture-docs` @ `b4f6320` | `f2037ddc3b1090e8b7e5b2a44fa7372867ade1acb9370639a533af4126409d35` |
| `package.json` | `architecture-docs` @ `1cffc68`, unchanged since | `7cafdae8d59300cf81a50a25a7a4aa01433cdea5763277f8d7d9cc3152c8d90d` |
| `package-lock.json` | `architecture-docs` @ `1cffc68`, unchanged since | `e63344ded30de8310f49f65e370b93f1e425f02048ce24d01193425d9cf7da25` |

Do not edit these files here. To update:

1. Change and test the checker in `architecture-docs` (`npm test` in `design-floor/`).
2. Copy the three files here unchanged, update this table, and commit that on its own.
3. Set `FLOOR_REF` in `design-floor.yml` to that commit's SHA in a second commit, and release a
   new minor version.
