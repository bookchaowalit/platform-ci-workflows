"""Fixture for self-test: proves DATABASE_URL points at a fresh per-job database."""

import os
import subprocess

url = os.environ["DATABASE_URL"]
name = url.rsplit("/", 1)[1]
assert name.startswith("ci_"), name
out = subprocess.run(
    ["psql", url, "-qAtc", "SELECT count(*) FROM pg_tables WHERE schemaname = 'public'"],
    check=True,
    capture_output=True,
    text=True,
).stdout.strip()
assert out == "0", f"expected an empty database, found {out} tables"
print(f"ok: {name} is empty")
