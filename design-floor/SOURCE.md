# design-floor checker (vendored)

Copy of the ADR-0007 design floor checker, run by
[`design-floor.yml`](../.github/workflows/design-floor.yml). The source of truth, its tests and
its 17 fixtures live in `architecture-docs/design-floor/` (private); this copy exists because a
public reusable workflow cannot check out a private repository.

| File | From | SHA-256 |
|---|---|---|
| `check.mjs` (1.0.3) | `architecture-docs` @ `39e42c3` | `81a8b5973849071452e4733cd0b0444e17371892095312185d3e6572a2222418` |
| `package.json` | `architecture-docs` @ `1cffc68`, unchanged since | `7cafdae8d59300cf81a50a25a7a4aa01433cdea5763277f8d7d9cc3152c8d90d` |
| `package-lock.json` | `architecture-docs` @ `1cffc68`, unchanged since | `e63344ded30de8310f49f65e370b93f1e425f02048ce24d01193425d9cf7da25` |

Do not edit these files here. To update:

1. Change and test the checker in `architecture-docs` (`npm test` in `design-floor/`).
2. Copy the three files here unchanged, update this table, and commit that on its own.
3. Set `FLOOR_REF` in `design-floor.yml` to that commit's SHA in a second commit, and release a
   new minor version.
