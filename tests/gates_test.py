"""Run the coverage-gate and Test step scripts of ci-node.yml / ci-python.yml against
crafted inputs, including the failure paths the reusable-workflow self-test cannot show.

Usage: python tests/gates_test.py   (needs PyYAML, node, and coverage.py on PATH)
"""

import json
import os
import pathlib
import subprocess
import sys
import tempfile

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
WORKFLOWS = ROOT / ".github" / "workflows"


def step(workflow: str, name: str) -> str:
    doc = yaml.safe_load((WORKFLOWS / workflow).read_text())
    job = next(iter(doc["jobs"].values()))
    return next(s["run"] for s in job["steps"] if s.get("name") == name)


def run(script: str, cwd: pathlib.Path, **env: str) -> subprocess.CompletedProcess:
    summary = cwd / "summary.md"
    full_env = {**os.environ, "GITHUB_STEP_SUMMARY": str(summary), **env}
    # GitHub runs `run:` steps with `bash -e {0}`.
    return subprocess.run(["bash", "-e", "-c", script], cwd=cwd, env=full_env, capture_output=True, text=True)


FAILURES: list[str] = []


def check(label: str, result: subprocess.CompletedProcess, ok: bool, expect: str = "", forbid: str = "") -> None:
    out = result.stdout + result.stderr
    passed = (result.returncode == 0) == ok and expect in out and not (forbid and forbid in out)
    print(f"{'PASS' if passed else 'FAIL'}  {label}")
    if not passed:
        FAILURES.append(label)
        print(f"      rc={result.returncode}, expected {'0' if ok else 'non-zero'} and {expect!r}\n{out}")


def node_summary(d: pathlib.Path, pct: float, total: int = 10) -> None:
    (d / "coverage").mkdir(exist_ok=True)
    metric = {"total": total, "covered": round(total * pct / 100), "pct": pct}
    data = {"total": {k: metric for k in ("lines", "statements", "functions", "branches")}}
    (d / "coverage" / "coverage-summary.json").write_text(json.dumps(data))


def node_cases(tmp: pathlib.Path) -> None:
    gate = step("ci-node.yml", "Coverage gate")
    test = step("ci-node.yml", "Test")

    def case(name: str) -> pathlib.Path:
        d = tmp / f"node-{name}"
        d.mkdir()
        (d / "package.json").write_text('{"name": "x"}')
        return d

    d = case("pass"); node_summary(d, 85.0)
    check("node gate: 85% vs 80 passes", run(gate, d, THRESHOLD="80"), True, "meets the 80% threshold")
    d = case("nonotice"); node_summary(d, 81.0)
    check("node gate: 81% vs 80 passes without notice", run(gate, d, THRESHOLD="80"), True, "meets", forbid="::notice::")
    d = case("ratchet"); node_summary(d, 92.5)
    check("node gate: 92.5% vs 80 passes with ratchet notice", run(gate, d, THRESHOLD="80"), True, "raise coverage-threshold to 92")
    d = case("below"); node_summary(d, 33.33)
    check("node gate: 33.33% vs 90 fails", run(gate, d, THRESHOLD="90"), False, "is below the 90% threshold")
    d = case("missing")
    check("node gate: missing summary fails", run(gate, d, THRESHOLD="80"), False, "not found")
    d = case("zero"); node_summary(d, 100.0, total=0)
    check("node gate: zero measured lines fails", run(gate, d, THRESHOLD="80"), False, "measured no lines")
    for bad in ("101", "abc", "1e3", "-5", "80%"):
        d = case(f"bad{bad.replace('%', 'pct')}"); node_summary(d, 100.0)
        check(f"node gate: threshold {bad!r} rejected", run(gate, d, THRESHOLD=bad), False, "must be a number from 0 to 100")

    d = case("require")
    check("node test: require-tests without test script fails",
          run(test, d, CMD="auto", PM="npm", REQUIRE_TESTS="true", THRESHOLD=""), False, "require-tests is on")
    d = case("warn")
    check("node test: no test script only warns by default",
          run(test, d, CMD="auto", PM="npm", REQUIRE_TESTS="false", THRESHOLD=""), True, "tests skipped")
    d = case("norunner")
    check("node test: threshold without vitest/jest fails",
          run(test, d, CMD="auto", PM="npm", REQUIRE_TESTS="false", THRESHOLD="80"), False, "needs vitest or jest")
    d = case("stale"); node_summary(d, 100.0)
    run(test, d, CMD="true", PM="npm", REQUIRE_TESTS="false", THRESHOLD="80")
    check("node test+gate: stale committed summary does not satisfy the gate", run(gate, d, THRESHOLD="80"), False, "not found")


def python_cases(tmp: pathlib.Path) -> None:
    gate = step("ci-python.yml", "Coverage gate")
    test = step("ci-python.yml", "Test")

    def case(name: str, covered_calls: int) -> pathlib.Path:
        d = tmp / f"py-{name}"
        d.mkdir()
        (d / "mod.py").write_text("".join(f"def f{i}():\n    return {i}\n\n" for i in range(4)))
        calls = "; ".join(f"mod.f{i}()" for i in range(covered_calls))
        (d / "drive.py").write_text(f"import mod\n{calls}\n")
        (d / ".coveragerc").write_text("[run]\nsource = mod\n")
        if covered_calls >= 0:
            subprocess.run([sys.executable, "-m", "coverage", "run", "drive.py"], cwd=d, check=True)
        return d

    # mod.py has 8 statements: 4 defs always run; each called function adds 1 (4 calls = 100%).
    d = case("pass", 4)
    check("python gate: 100% vs 80 passes with ratchet notice", run(gate, d, THRESHOLD="80"), True, "raise coverage-threshold to 100")
    d = case("below", 1)
    check("python gate: 62.5% vs 90 fails", run(gate, d, THRESHOLD="90"), False, "below the 90% threshold")
    d = case("exact", 2)
    check("python gate: 75% vs 75 passes without notice", run(gate, d, THRESHOLD="75"), True, "", forbid="::notice::")
    d = case("nodata", -1)
    check("python gate: no .coverage data fails", run(gate, d, THRESHOLD="80"), False, "no coverage data")
    for bad in ("101", "abc", "1e3"):
        d = case(f"bad{bad}", 4)
        check(f"python gate: threshold {bad!r} rejected", run(gate, d, THRESHOLD=bad), False, "must be a number from 0 to 100")
    d = case("stale", 4)
    run(test, d, CMD="true", THRESHOLD="80")
    check("python test+gate: stale .coverage does not satisfy the gate", run(gate, d, THRESHOLD="80"), False, "no coverage data")


def main() -> int:
    with tempfile.TemporaryDirectory() as t:
        tmp = pathlib.Path(t)
        node_cases(tmp)
        python_cases(tmp)
    print(f"\n{len(FAILURES)} failed" if FAILURES else "\nall gate cases passed")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
