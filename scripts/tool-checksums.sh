#!/usr/bin/env bash
# Print the SHA-256 of each pinned security tool's release asset, verified against the
# checksum file published in the same GitHub release. Run after Renovate bumps a
# *_VERSION in .github/workflows/security.yml or self-test.yml, then paste the new *_SHA256 values.
#
#   scripts/tool-checksums.sh            # versions read from the workflow files
set -euo pipefail

wfdir="$(cd "$(dirname "$0")/.." && pwd)/.github/workflows"
ver() { sed -n "s/^ *$1: \"\(.*\)\"/\1/p" "$wfdir/security.yml" "$wfdir/self-test.yml" | head -n1; }

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
cd "$tmp"

check() { # repo tag asset checksum-file name-of-env
  gh release download "$2" -R "$1" -p "$3" -p "$4" >/dev/null
  grep -E "[[:space:]]\*?$3\$" "$4" | sha256sum -c - >/dev/null
  printf '%s: "%s"  # %s\n' "$5" "$(sha256sum "$3" | cut -d' ' -f1)" "$3"
}

v=$(ver GITLEAKS_VERSION)
check gitleaks/gitleaks "v$v" "gitleaks_${v}_linux_x64.tar.gz" "gitleaks_${v}_checksums.txt" GITLEAKS_SHA256
v=$(ver OSV_SCANNER_VERSION)
check google/osv-scanner "v$v" osv-scanner_linux_amd64 osv-scanner_SHA256SUMS OSV_SCANNER_SHA256
v=$(ver TRIVY_VERSION)
check aquasecurity/trivy "v$v" "trivy_${v}_Linux-64bit.tar.gz" "trivy_${v}_checksums.txt" TRIVY_SHA256
v=$(ver ACTIONLINT_VERSION)
check rhysd/actionlint "v$v" "actionlint_${v}_linux_amd64.tar.gz" "actionlint_${v}_checksums.txt" ACTIONLINT_SHA256
