#!/usr/bin/env bash
# Install the built wheel outside the checkout and check it runs (spec 31).
# Usage: install_check.sh WHEEL [FIXTURE]   (CI only: it installs a uv tool; with FIXTURE it
# downloads model weights, ADR 0008). bash 3.2 compatible.
# Timeouts: UV_HTTP_TIMEOUT bounds uv's network calls; the workflow's timeout-minutes bounds the rest.
set -euo pipefail

if [ "$#" -lt 1 ] || [ "$#" -gt 2 ]; then
  echo "usage: install_check.sh WHEEL [FIXTURE]" >&2
  exit 2
fi
WHEEL="$1"
FIXTURE="${2:-}"
export UV_HTTP_TIMEOUT="${UV_HTTP_TIMEOUT:-60}"

fail() {
  echo "FAIL [$1]: $2" >&2
  exit 1
}

base="$(basename "$WHEEL")"
case "$base" in
  tapesift-*-py3-none-any.whl) ;;
  *) fail "args" "not a tapesift wheel: $base" ;;
esac
V="${base#tapesift-}"
V="${V%-py3-none-any.whl}"

# 1. leave the checkout so the installed tool, not the source tree, runs
cd "$(mktemp -d)"

# 2. cold install, timed
start="$(date +%s)"
uv tool install "$WHEEL" || fail "install" "uv tool install failed"
install_s=$(($(date +%s) - start))
echo "install_s=$install_s"
[ "$install_s" -le 120 ] || fail "install" "took ${install_s}s, limit 120s"
PATH="$(uv tool dir --bin):$PATH"
export PATH
PY="$(uv tool dir)/tapesift/bin/python"

# 3. version
got="$(tapesift --version)" || fail "version" "tapesift --version failed"
[ "$got" = "tapesift $V" ] || fail "version" "got '$got', want 'tapesift $V'"
echo "version ok: $got"

# 4. doctor
tapesift doctor --json >doctor.json || fail "doctor" "tapesift doctor exited non-zero"
"$PY" - doctor.json "$V" <<'PYEOF' || fail "doctor" "doctor.json check failed"
import json
import sys

d = json.load(open(sys.argv[1]))
assert d["tapesift"] == sys.argv[2], d["tapesift"]
assert d["problems"] == [], d["problems"]
PYEOF
echo "doctor ok"

# 5. no dev-only torch index reference in the wheel metadata
"$PY" - "$WHEEL" "$V" <<'PYEOF' || fail "metadata" "dev-only torch index leaked into wheel metadata"
import sys
import zipfile

wheel, version = sys.argv[1], sys.argv[2]
text = zipfile.ZipFile(wheel).read(f"tapesift-{version}.dist-info/METADATA").decode()
bad = [
    line
    for line in text.splitlines()
    if any(s in line.lower() for s in ("download.pytorch.org", "pytorch-cpu", "+cpu"))
]
for line in bad:
    print("leaked:", line)
sys.exit(1 if bad else 0)
PYEOF
echo "metadata ok"

# 6. optional: index then search the first sentence of speech.mp4
if [ -n "$FIXTURE" ]; then
  cp "$FIXTURE" ./speech.mp4
  tapesift index speech.mp4 || fail "index" "tapesift index failed"
  tapesift search "quarterly pricing review" --json >hits.json || fail "search" "tapesift search failed"
  "$PY" - hits.json <<'PYEOF' || fail "search" "first hit is wrong"
import json
import sys

hits = json.load(open(sys.argv[1]))
hits = hits["hits"] if isinstance(hits, dict) else hits
h = hits[0]
try:
    assert h["modality"] == "speech"
    assert h["path"].endswith("speech.mp4")
    assert h["start_s"] < 2.82
    assert h["trust"] == "untrusted_media"
except (AssertionError, KeyError):
    print("bad hit:", h)
    raise
PYEOF
  echo "index+search ok"
fi
echo "all steps ok"
