"""Run the step scripts of deploy-railway.yml / deploy-vercel.yml against a local stub of the
GitHub, Railway GraphQL and Vercel REST APIs and of the deployed service, including the failure
paths (refused ref, stale commit, failed build, wrong commit, failed smoke test, rollback hint)
that a reusable-workflow self-test cannot show.

Usage: python tests/deploy_test.py   (needs PyYAML, bash, curl and jq on PATH)
"""

import json
import os
import pathlib
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
WORKFLOWS = ROOT / ".github" / "workflows"
SHA = "a" * 40
OLD = "b" * 40

# Env names each step must receive from its `env:` block; the harness sets exactly these.
STEP_ENV = {
    "Check the commit": {"ALLOWED_REF", "GH_TOKEN"},
    "Smoke test": {"HEALTH_URL", "HEALTH_EXPECT", "COMMIT_URL", "COMMIT_FIELD", "ATTEMPTS", "INTERVAL"},
    ("deploy-railway.yml", "Record the live deployment"): {"RAILWAY_TOKEN", "SERVICE_ID", "ENVIRONMENT_ID"},
    ("deploy-railway.yml", "Deploy the commit"): {"RAILWAY_TOKEN", "SERVICE_ID", "ENVIRONMENT_ID"},
    ("deploy-railway.yml", "Wait for the deployment"): {"RAILWAY_TOKEN", "DEPLOYMENT_ID", "TIMEOUT_MINUTES", "POLL_SECONDS"},
    ("deploy-railway.yml", "Rollback hint"): {"PREV_ID", "PREV_COMMIT", "DEPLOYMENT_ID", "SERVICE_ID"},
    ("deploy-vercel.yml", "Record the live deployment"): {"VERCEL_TOKEN", "PROJECT_ID", "TEAM_ID"},
    ("deploy-vercel.yml", "Deploy the commit"): {"VERCEL_TOKEN", "PROJECT_ID", "TEAM_ID", "ALLOWED_REF"},
    ("deploy-vercel.yml", "Wait for the deployment"): {"VERCEL_TOKEN", "TEAM_ID", "DEPLOYMENT_ID", "TIMEOUT_MINUTES", "POLL_SECONDS"},
    ("deploy-vercel.yml", "Rollback hint"): {"PREV_ID", "PREV_COMMIT", "DEPLOYMENT_ID", "PROJECT_ID"},
}


def step(workflow: str, name: str) -> str:
    doc = yaml.safe_load((WORKFLOWS / workflow).read_text())
    job = doc["jobs"]["deploy"]
    found = next(s for s in job["steps"] if s.get("name") == name)
    assert "${{" not in found["run"], f"{workflow} {name}: expression inside run:"
    want = STEP_ENV.get((workflow, name)) or STEP_ENV[name]
    assert set(found.get("env", {})) == want, f"{workflow} {name}: env keys changed"
    assert job["defaults"]["run"]["shell"] == "bash", f"{workflow}: default shell changed"
    assert job["concurrency"]["cancel-in-progress"] is False, f"{workflow}: a deploy must never be cancelled midway"
    return found["run"]


class Stub:
    """Mutable fake state shared by the HTTP handler."""

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.tip = SHA
        self.statuses = ["BUILDING", "DEPLOYING", "SUCCESS"]  # Railway status per poll
        self.deployed_commit = SHA
        self.deploy_error = False
        self.vercel_states = ["BUILDING", "READY"]
        self.health = [200]  # status per probe; the last one repeats
        self.health_body = '{"status":"ok"}'
        self.running = SHA
        self.requests: list[tuple[str, str, str]] = []


STUB = Stub()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args) -> None:  # noqa: A002 - keep the test output readable
        pass

    def reply(self, code: int, body) -> None:
        data = body if isinstance(body, str) else json.dumps(body)
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(data.encode())

    def do_GET(self) -> None:
        STUB.requests.append(("GET", self.path, ""))
        if self.path.startswith("/repos/"):
            return self.reply(200, STUB.tip)
        if self.path == "/health":
            code = STUB.health.pop(0) if len(STUB.health) > 1 else STUB.health[0]
            return self.reply(code, STUB.health_body)
        if self.path == "/version":
            return self.reply(200, {"commit": STUB.running})
        if self.path.startswith("/v6/deployments"):
            return self.reply(200, {"deployments": [{"uid": "dpl_old", "meta": {"githubCommitSha": OLD}}]})
        if self.path.startswith("/v13/deployments/dpl_new"):
            state = STUB.vercel_states.pop(0) if len(STUB.vercel_states) > 1 else STUB.vercel_states[0]
            return self.reply(200, {"readyState": state, "meta": {"githubCommitSha": STUB.deployed_commit}})
        self.reply(404, {"error": "not found"})

    def do_POST(self) -> None:
        raw = self.rfile.read(int(self.headers.get("Content-Length", 0))).decode()
        STUB.requests.append(("POST", self.path, raw))
        if self.path == "/graphql":
            if self.headers.get("Project-Access-Token") != "rw-token":
                return self.reply(200, {"errors": [{"message": "Not Authorized"}]})
            query = json.loads(raw)["query"]
            if "serviceInstanceDeployV2" in query:
                if STUB.deploy_error:
                    return self.reply(200, {"errors": [{"message": "Repo not found"}], "data": None})
                return self.reply(200, {"data": {"serviceInstanceDeployV2": "dep-new"}})
            if "deployments(" in query:
                node = {"id": "dep-old", "meta": {"commitHash": OLD}}
                return self.reply(200, {"data": {"deployments": {"edges": [{"node": node}]}}})
            if "deployment(id" in query:
                status = STUB.statuses.pop(0) if len(STUB.statuses) > 1 else STUB.statuses[0]
                meta = {"commitHash": STUB.deployed_commit}
                return self.reply(200, {"data": {"deployment": {"status": status, "meta": meta}}})
        if self.path.startswith("/v13/deployments"):
            if STUB.deploy_error:
                return self.reply(400, {"error": {"code": "bad_request", "message": "no repo"}})
            return self.reply(200, {"id": "dpl_new"})
        self.reply(404, {"error": "not found"})


def run(script: str, cwd: pathlib.Path, base: str, **env: str) -> subprocess.CompletedProcess:
    full_env = {
        **os.environ,
        "GITHUB_STEP_SUMMARY": str(cwd / "summary.md"),
        "GITHUB_OUTPUT": str(cwd / "output"),
        "GITHUB_API_URL": base,
        "GITHUB_REPOSITORY": "bookchaowalit/finance-accounts-api",
        "GITHUB_REF": "refs/heads/main",
        "GITHUB_SHA": SHA,
        "RUNNER_TEMP": str(cwd),
        "RAILWAY_GRAPHQL_URL": f"{base}/graphql",
        "VERCEL_API_URL": base,
        **env,
    }
    (cwd / "output").write_text("")
    cmd = ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", script]
    return subprocess.run(cmd, cwd=cwd, env=full_env, capture_output=True, text=True, timeout=60)


def outputs(cwd: pathlib.Path) -> dict[str, str]:
    lines = (cwd / "output").read_text().splitlines()
    return dict(line.split("=", 1) for line in lines if "=" in line)


FAILURES: list[str] = []


def check(label: str, result: subprocess.CompletedProcess, ok: bool, expect: str = "") -> None:
    out = result.stdout + result.stderr
    passed = (result.returncode == 0) == ok and expect in out
    print(f"{'PASS' if passed else 'FAIL'}  {label}")
    if not passed:
        FAILURES.append(label)
        print(f"      rc={result.returncode}, expected {'0' if ok else 'non-zero'} and {expect!r}\n{out}")


def expect(label: str, condition: bool, detail: str = "") -> None:
    print(f"{'PASS' if condition else 'FAIL'}  {label}")
    if not condition:
        FAILURES.append(label)
        print(f"      {detail}")


def common_cases(workflow: str, tmp: pathlib.Path, base: str) -> None:
    commit = step(workflow, "Check the commit")
    smoke = step(workflow, "Smoke test")
    env = {"ALLOWED_REF": "refs/heads/main", "GH_TOKEN": "gh"}

    STUB.reset()
    check(f"{workflow}: a branch other than main is refused",
          run(commit, tmp, base, **env, GITHUB_REF="refs/heads/feature"), False, "Deploy refused")
    STUB.reset()
    check(f"{workflow}: the tip of main deploys", run(commit, tmp, base, **env), True)
    expect(f"{workflow}: skip=false at the tip", outputs(tmp) == {"skip": "false"}, str(outputs(tmp)))
    STUB.reset(); STUB.tip = OLD
    check(f"{workflow}: an older commit is skipped, not failed", run(commit, tmp, base, **env), True, "Deploy skipped")
    expect(f"{workflow}: skip=true when main moved on", outputs(tmp) == {"skip": "true"}, str(outputs(tmp)))

    smoke_env = {"HEALTH_URL": f"{base}/health", "HEALTH_EXPECT": "", "COMMIT_URL": "",
                 "COMMIT_FIELD": "commit", "ATTEMPTS": "3", "INTERVAL": "0"}
    STUB.reset(); STUB.health = [503, 503, 200]
    check(f"{workflow}: smoke retries until a sleeping service wakes", run(smoke, tmp, base, **smoke_env), True, "health OK")
    STUB.reset(); STUB.health = [500]
    check(f"{workflow}: smoke fails loudly after the last attempt", run(smoke, tmp, base, **smoke_env), False, "Smoke test failed")
    STUB.reset()
    check(f"{workflow}: smoke checks the expected body text",
          run(smoke, tmp, base, **{**smoke_env, "HEALTH_EXPECT": '"status":"down"'}), False, "Smoke test failed")
    STUB.reset()
    check(f"{workflow}: the running commit matches",
          run(smoke, tmp, base, **{**smoke_env, "COMMIT_URL": f"{base}/version"}), True, "commit OK")
    STUB.reset(); STUB.running = SHA[:7]
    check(f"{workflow}: a 7-character prefix of the commit is accepted",
          run(smoke, tmp, base, **{**smoke_env, "COMMIT_URL": f"{base}/version"}), True, "commit OK")
    STUB.reset(); STUB.running = OLD
    check(f"{workflow}: a service still on the old commit fails",
          run(smoke, tmp, base, **{**smoke_env, "COMMIT_URL": f"{base}/version"}), False, "wrong commit")
    STUB.reset(); STUB.running = ""
    check(f"{workflow}: a service that names no commit fails",
          run(smoke, tmp, base, **{**smoke_env, "COMMIT_URL": f"{base}/version"}), False, "wrong commit")


def railway_cases(tmp: pathlib.Path, base: str) -> None:
    wf = "deploy-railway.yml"
    live = step(wf, "Record the live deployment")
    deploy = step(wf, "Deploy the commit")
    wait = step(wf, "Wait for the deployment")
    hint = step(wf, "Rollback hint")
    ids = {"RAILWAY_TOKEN": "rw-token", "SERVICE_ID": "svc", "ENVIRONMENT_ID": "env"}

    STUB.reset()
    check("railway: records the live deployment", run(live, tmp, base, **ids), True)
    expect("railway: live id and commit as outputs", outputs(tmp) == {"id": "dep-old", "commit": OLD}, str(outputs(tmp)))
    STUB.reset()
    check("railway: a bad token fails before deploying",
          run(live, tmp, base, **{**ids, "RAILWAY_TOKEN": "wrong"}), False, "Not Authorized")

    STUB.reset()
    check("railway: deploys the exact commit", run(deploy, tmp, base, **ids), True, "dep-new")
    sent = json.loads(STUB.requests[-1][2])
    expect("railway: commitSha sent is GITHUB_SHA", sent["variables"]["c"] == SHA, str(sent))
    expect("railway: deployment-id output", outputs(tmp) == {"deployment-id": "dep-new"}, str(outputs(tmp)))
    STUB.reset(); STUB.deploy_error = True
    check("railway: a refused deploy fails loudly", run(deploy, tmp, base, **ids), False, "Railway refused the deploy")

    wait_env = {"RAILWAY_TOKEN": "rw-token", "DEPLOYMENT_ID": "dep-new", "TIMEOUT_MINUTES": "1", "POLL_SECONDS": "0"}
    STUB.reset()
    check("railway: waits through BUILDING/DEPLOYING to SUCCESS", run(wait, tmp, base, **wait_env), True, "SUCCESS")
    STUB.reset(); STUB.statuses = ["BUILDING", "SLEEPING"]
    check("railway: SLEEPING (app sleeping) counts as up", run(wait, tmp, base, **wait_env), True, "SLEEPING")
    for bad in ("FAILED", "CRASHED", "NEEDS_APPROVAL"):
        STUB.reset(); STUB.statuses = ["BUILDING", bad]
        check(f"railway: {bad} fails loudly", run(wait, tmp, base, **wait_env), False, f"Deploy {bad}")
    STUB.reset(); STUB.deployed_commit = OLD
    check("railway: a deployment of another commit fails", run(wait, tmp, base, **wait_env), False, "Wrong commit")
    STUB.reset(); STUB.statuses = ["WAITING"]
    check("railway: a deployment stuck WAITING times out",
          run(wait, tmp, base, **{**wait_env, "TIMEOUT_MINUTES": "0"}), False, "Deploy timed out")

    hint_env = {"PREV_ID": "dep-old", "PREV_COMMIT": OLD, "DEPLOYMENT_ID": "dep-new", "SERVICE_ID": "svc"}
    STUB.reset()
    result = run(hint, tmp, base, **hint_env)
    check("railway: rollback hint names the last good deployment", result, True, 'deploymentRollback(id: "dep-old")')
    expect("railway: rollback hint is an ::error annotation", "::error title=Production deploy failed" in result.stdout)
    expect("railway: rollback hint lands in the job summary", "dep-old" in (tmp / "summary.md").read_text())
    (tmp / "summary.md").unlink()
    check("railway: rollback hint without a previous deployment",
          run(hint, tmp, base, **{**hint_env, "PREV_ID": "", "PREV_COMMIT": ""}), True, "No earlier successful deployment")


def vercel_cases(tmp: pathlib.Path, base: str) -> None:
    wf = "deploy-vercel.yml"
    live = step(wf, "Record the live deployment")
    deploy = step(wf, "Deploy the commit")
    wait = step(wf, "Wait for the deployment")
    hint = step(wf, "Rollback hint")
    ids = {"VERCEL_TOKEN": "vc", "PROJECT_ID": "prj_1", "TEAM_ID": "team_1"}

    STUB.reset()
    check("vercel: records the live production deployment", run(live, tmp, base, **ids), True)
    expect("vercel: live id and commit as outputs", outputs(tmp) == {"id": "dpl_old", "commit": OLD}, str(outputs(tmp)))
    expect("vercel: the lookup is scoped to the team", "teamId=team_1" in STUB.requests[-1][1], STUB.requests[-1][1])

    STUB.reset()
    check("vercel: deploys the exact commit from Git", run(deploy, tmp, base, **ids, ALLOWED_REF="refs/heads/main"), True, "dpl_new")
    _, path, raw = STUB.requests[-1]
    sent = json.loads(raw)
    expect("vercel: gitSource is owner/repo at GITHUB_SHA on main",
           sent["gitSource"] == {"type": "github", "org": "bookchaowalit", "repo": "finance-accounts-api", "ref": "main", "sha": SHA}
           and sent["target"] == "production" and "teamId=team_1" in path, f"{path} {sent}")
    STUB.reset(); STUB.deploy_error = True
    check("vercel: a refused deploy fails loudly",
          run(deploy, tmp, base, **ids, ALLOWED_REF="refs/heads/main"), False, "Vercel refused the deploy")

    wait_env = {"VERCEL_TOKEN": "vc", "TEAM_ID": "team_1", "DEPLOYMENT_ID": "dpl_new", "TIMEOUT_MINUTES": "1", "POLL_SECONDS": "0"}
    STUB.reset()
    check("vercel: waits for READY", run(wait, tmp, base, **wait_env), True, "READY")
    STUB.reset(); STUB.vercel_states = ["BUILDING", "ERROR"]
    check("vercel: ERROR fails loudly", run(wait, tmp, base, **wait_env), False, "Deploy ERROR")
    STUB.reset(); STUB.deployed_commit = OLD
    check("vercel: a deployment of another commit fails", run(wait, tmp, base, **wait_env), False, "Wrong commit")

    STUB.reset()
    check("vercel: rollback hint names the last good deployment",
          run(hint, tmp, base, PREV_ID="dpl_old", PREV_COMMIT=OLD, DEPLOYMENT_ID="dpl_new", PROJECT_ID="prj_1"),
          True, "vercel rollback dpl_old")


def main() -> int:
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        with tempfile.TemporaryDirectory() as raw:
            tmp = pathlib.Path(raw)
            for workflow in ("deploy-railway.yml", "deploy-vercel.yml"):
                common_cases(workflow, tmp, base)
            railway_cases(tmp, base)
            vercel_cases(tmp, base)
    finally:
        server.shutdown()
    if FAILURES:
        print(f"\n{len(FAILURES)} failed: {FAILURES}")
        return 1
    print("\nall deploy cases passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
