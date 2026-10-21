# 31. Packaging: wheel install smoke test now, release workflow later (E8)

Issue: #31   Lane: Core (CI; this spec grants the paths below)   Status: draft r3 (lean mode). Cards decided or deferred (below); ready for the lead to approve.
Revisions: 2026-10-20 r2 designed the full tag-to-PyPI release path (kept, unbuilt, in the appendix). 2026-10-20 r3, lean mode (owner: working MVP demo first; opus decides, sonnet builds): **release and publishing are deferred.** This PR only proves the built wheel installs and runs. No upload, no `release.yml`, no `.claude/settings.json` change.

Builds on main after M1 (merged, 7bcb1ee). Uses no name from an unapproved spec: `tapesift index` and `tapesift search` come from approved E7 (#30) and E6 (#29, r3), and the models step needs both on main (until then, dispatch without `models`).

## Decisions (opus, 2026-10-20, lean mode; owner delegated)
| Card | Choice | Why |
| --- | --- | --- |
| Scope | **Minimal E8**: one install-test workflow plus one shell script. Release workflow, publishing, attestations, check-dist/check-lock, build-backend pinning, zizmor, glibc container, owner runbook: **deferred** (Later; r2 design in the appendix) | The MVP demo runs from a checkout or a local wheel. Publishing is a one-way door that needs the public flip and owner setup first |
| 1 (T3) how a tag becomes an upload | **Deferred** with the release workflow. Recorded intent: r2's A (settings are the guards: tag ruleset, `pypi` environment with the owner as reviewer, publisher binding) | Nothing uploads in lean mode, so nothing to guard yet |
| 2 (T2) release supply chain | **Deferred**. Recorded intent: r2's A (`pypa/gh-action-pypi-publish` pinned by SHA, re-checked when revived; hash-pinned `uv_build`; sha256 hand-off) | Same |
| 3 (T2, security) `.claude/settings.json` deny rules | **Not in this PR. Owner OK needed** to apply r2's A list (deny `git tag *`, tag pushes, `gh release *`, `gh api` refs/releases/rulesets/deployments/environments, `gh api graphql*`; ask `gh workflow run *`) | It changes agent permission settings, which only the owner can approve. Recommend applying it before the release workflow lands |
| 4 (T3) when the PyPI name is claimed | **A for now** (no upload in lean mode). **Owner OK needed** if the repo flips public (Q9, by Oct 31) before a first PyPI release: either the owner claims the name with a placeholder upload (r2 option C; owner's own PyPI token, deleted after) or accepts the squat risk | Lean mode widens the flip-to-upload window; option C touches credentials, so it is the owner's call |

Spending: GitHub Actions minutes only (private repo quota; macOS minutes bill 10x, so macOS runs on manual dispatch only). No money.

## Goal
A `install-test` workflow builds the sdist and wheel with `uv build --no-sources`, installs the wheel with `uv tool install` outside the checkout, and checks `tapesift --version`, `tapesift doctor --json`, that no CPU-index torch reference leaked into the wheel metadata, and (on dispatch with `models=true`) that `tapesift index` then `tapesift search` finds speech.mp4's first sentence. It runs on ubuntu-24.04 for packaging PRs, and on ubuntu-24.04 and macos-15 on manual dispatch.

## Read first
- Issue #31, including "Stop and ask if".
- docs/spec.md: 184 (install under 2 minutes), 206 (platforms), 333 (v0.1 exit: `uvx tapesift` works on fresh Linux and Mac), 342 (E8).
- `docs/specs/25-m1-interfaces.md`: the `vision` extra; `[[tool.uv.index]] pytorch-cpu` and the `[tool.uv.sources]` torch entry (dev and CI only; must never reach wheel metadata, its A7 check); `doctor --json`; `out_dir` default `tapesift_index`; card 10's floors (glibc 2.28+, macOS 14+ arm64).
- `docs/specs/29-search.md` (`search --json` shape) and `docs/specs/30-runner.md` (`tapesift index PATH`).
- ADRs 0004 (private until launch), 0008 (CI runners may download models; the laptop never does), 0011 (Python 3.12 floor).
- Code: `pyproject.toml`, `src/tapesift/__init__.py`, `src/tapesift/cli/__init__.py`, `src/tapesift/cli/doctor.py`, `.github/workflows/ci.yml` (action pins by SHA).
- Observed 2026-10-20 (r2): `uv build --no-sources -o DIR` on main gives `tapesift-0.1.0.dev0-py3-none-any.whl` and `tapesift-0.1.0.dev0.tar.gz`; two builds are byte-identical; METADATA 2.4 with `Requires-Python: >=3.12`. Pins: `actions/checkout` v7.0.1 = `3d3c42e5aac5ba805825da76410c181273ba90b1`; `astral-sh/setup-uv` v10.3.0 = `1c37ad07a6a961277cf70c0d37d6f313000f5884` (both as in ci.yml). macos-14 retires 2026-11-02; macos-15 is the oldest arm64 image left.

## Scope
May change:
- `.github/workflows/install-test.yml` (new)
- `scripts/ci/install_check.sh` (new; bash 3.2 compatible, no arrays)
- `CHANGELOG.md`: one line under Unreleased, Added: `- CI: an install test builds the wheel, installs it with uv outside the checkout and runs version, doctor and (on demand) index plus search (#31).`

Must not touch:
- `pyproject.toml`, `uv.lock`, `src/**`, `.github/workflows/ci.yml`, `.github/workflows/models.yml`, `scripts/ci/test_guard.py`, `tests/**`.
- `.claude/settings.json` (card 3 is the owner's), `docs/spec.md`, `README.md`, `AGENTS.md`, `CLAUDE.md`, `THIRD_PARTY.md`.
- GitHub settings, environments, rulesets, PyPI/TestPyPI accounts, tags, releases.

## Interfaces touched
Before: no install test. After: the two files below. Nothing in `src/` changes; the version stays `0.1.0.dev0`.

### `scripts/ci/install_check.sh`
`install_check.sh WHEEL [FIXTURE]`. `WHEEL` is an absolute path to `tapesift-V-py3-none-any.whl`; `V` is parsed from the filename. With `FIXTURE`, the index-and-search step runs. `set -euo pipefail`; no arrays; every variable assigned before use. `PY` is `"$(uv tool dir)/tapesift/bin/python"`. Each step prints one line; any failure exits non-zero with a message naming the step.
1. `cd "$(mktemp -d)"` so the tool, not the source tree, runs.
2. `uv tool install "$WHEEL"`, timed with `date +%s`; print `install_s=<n>`; **fail if `n > 120`** (spec 184; issue #31 says stop and ask).
3. `test "$(tapesift --version)" = "tapesift $V"`.
4. `tapesift doctor --json > doctor.json` exits 0; `"$PY" - doctor.json "$V"` (heredoc) checks `d["tapesift"] == V` and `d["problems"] == []`.
5. **Metadata leak check.** `"$PY" - "$WHEEL"` (heredoc, `zipfile`) reads `tapesift-V.dist-info/METADATA` and fails if it contains, case-insensitive, `download.pytorch.org`, `pytorch-cpu` or `+cpu`, printing the line.
6. With `FIXTURE`: copy it to `./speech.mp4`; `tapesift index speech.mp4` exits 0; `tapesift search "quarterly pricing review" --json > hits.json` exits 0; `"$PY" - hits.json` checks `hits[0]`: `modality == "speech"`, `path` ends with `speech.mp4`, `start_s < 2.82`, `trust == "untrusted_media"`; on failure it prints the hit.

### `.github/workflows/install-test.yml`
```yaml
name: install-test

on:
  pull_request:
    paths:
      - pyproject.toml
      - uv.lock
      - .github/workflows/install-test.yml
      - scripts/ci/install_check.sh
  workflow_dispatch:
    inputs:
      models:
        description: "Also index and search speech.mp4 (downloads ASR and embedder weights on the runner)"
        type: boolean
        default: false

permissions:
  contents: read

concurrency:
  group: install-test-${{ github.ref }}
  cancel-in-progress: true

jobs:
  install:
    name: install wheel (${{ matrix.os }})
    strategy:
      fail-fast: false
      matrix:
        # macOS only on manual dispatch: its minutes bill 10x on a private repo.
        os: ${{ fromJSON(github.event_name == 'workflow_dispatch' && '["ubuntu-24.04", "macos-15"]' || '["ubuntu-24.04"]') }}
    runs-on: ${{ matrix.os }}
    timeout-minutes: 25
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false
      - uses: astral-sh/setup-uv@1c37ad07a6a961277cf70c0d37d6f313000f5884 # v10.3.0
        with:
          enable-cache: false # time the install as a stranger sees it
      - run: uv build --no-sources -o dist
      - env:
          MODELS: ${{ inputs.models }}
        shell: bash # explicit shell gives -eo pipefail; the default is bash -e, so tee would hide a failure
        run: |
          wheel="$PWD/$(ls dist/tapesift-*-py3-none-any.whl)"
          if [ "$MODELS" = "true" ]; then
            bash scripts/ci/install_check.sh "$wheel" "$PWD/tests/fixtures/speech.mp4" | tee -a "$GITHUB_STEP_SUMMARY"
          else
            bash scripts/ci/install_check.sh "$wheel" | tee -a "$GITHUB_STEP_SUMMARY"
          fi
```
No secrets, no `id-token`, no `pull_request_target`, no upload, ever. `inputs.*` reaches `run:` only through `env:`.

## Acceptance
| # | Check | Command | Expected |
| --- | --- | --- | --- |
| 1 | Script parses | `bash -n scripts/ci/install_check.sh` | exit 0 |
| 2 | The wheel builds locally (no models involved) | `rm -rf /tmp/e8 && uv build --no-sources -o /tmp/e8 && ls /tmp/e8` | `tapesift-0.1.0.dev0-py3-none-any.whl` and `tapesift-0.1.0.dev0.tar.gz` (plus uv's `.gitignore`) |
| 3 | Gate | `make check` | exit 0 (no new pytest tests; the count is unchanged) |
| 4 | Every action pinned by SHA | `grep -E '^\s*(-\s*)?uses:' .github/workflows/install-test.yml \| grep -cvE '@[0-9a-f]{40}( \|$)'` | `0` |
| 5 | No credentials or privileged triggers | `grep -cE 'secrets\.\|id-token\|pull_request_target' .github/workflows/install-test.yml` | `0` |
| 6 | The PR's own run (it triggers itself through `paths`) | `install-test` on the PR | green on ubuntu-24.04; the summary shows `install_s` (≤ 120) and every step line |
| 7 | Dispatch with models, after E6 and E7 are on main | `gh workflow run install-test.yml --ref <branch> -f models=true` (the lead may dispatch; it uploads nothing) | green on ubuntu-24.04 and macos-15, the index and search step included. The PR's Numbers section records `install_s` per OS and the run's billed minutes |

Never run `install_check.sh` on the laptop: it installs a uv tool into the user's environment and, with `FIXTURE`, downloads model weights (ADR 0008).

**Tests.** No new pytest tests: the script's check is the workflow run itself (rows 6-7). The one logic piece with a trust-boundary flavour, the metadata leak check, is exercised on every run.

## Out of scope
- Publishing anywhere (TestPyPI, PyPI, GHCR), `release.yml`, tags, GitHub releases.
- Docker images (S5), Windows/WSL2, Intel Macs.
- README install text (E9), including the Linux `--torch-backend cpu` note for `[vision]`.

## Later (cut for the MVP demo; r2 design in the appendix)
- `release.yml`: tag-triggered build, `plan` (private-repo refusal, tag/version match, on-main check, CHANGELOG notes), protected `pypi` environment, trusted publishing with PEP 740 attestations, post-publish `verify` on fresh runners, draft GitHub release (cards 1 and 2).
- `scripts/ci/release.py` (`target`, `check-dist`, `check-lock`, `notes`) and its 46 unit tests; `build-constraints.txt` (hash-pinned `uv_build`); reproducible-build `cmp`; zizmor online audit.
- Install test inside an `almalinux:8` container (glibc 2.28 floor); the `[vision]` extra install and its time gate; a `--python 3.12` install run.
- `docs/guides/release.md` owner runbook (flip, environment, tag ruleset, pending publishers).
- Card 3's `.claude/settings.json` deny rules (owner OK needed) and card 4's name-claim timing (owner OK needed if the flip comes first).
- Dependabot for action SHA pins (follow-up issue).

Revive these as a new spec revision once the MVP demo works and before the public flip (Q9).

## Risks
- **uv's default Python.** `uv tool install` may pick a CPython newer than any wheel of a dependency; then step 2 fails. Stop and raise a card (upper bound on `requires-python`, or document `--python 3.12`).
- **The platform floors are not tested** (ubuntu-24.04 has glibc 2.39; macos-15 is above the macOS 14 floor). The appendix's container test and `check-lock` close that later.
- **Time gate flakes** on a slow runner network: one re-run allowed; two failures in a row is issue #31's "stop and ask".
- **The models step downloads weights from Hugging Face on the runner** (ADR 0008 allows it); an HF outage fails it, and a re-run is the fix.
- **Name squatting** grows with the flip-to-upload gap (card 4).
- **Agents hold the owner's `gh` login** without card 3's deny rules. With no release workflow, a stray tag or GitHub release publishes nothing to PyPI, but card 3 should land before `release.yml` does.

## T1 calls (list them in the PR)
1. The version stays `0.1.0.dev0`.
2. ubuntu-24.04 on PRs; macos-15 added on dispatch only (minutes).
3. uv caches off; the install is timed cold; 120 s gate.
4. The metadata leak check reads the wheel with Python's `zipfile`, not `unzip`.
5. The lead may run `gh workflow run install-test.yml` (it uploads nothing); it is not a release action.

## Decision cards
Decided or deferred in the table at the top. The full r2 cards (options, pros and cons) are in the appendix under "Decision cards".

## Appendix: r2 release design (parked, not built in lean mode)
Kept verbatim for when the release workflow is revived. Builders of r3 ignore this section. Facts in it (action SHAs, PyPI and GitHub behaviour) were observed on 2026-10-20 and must be re-checked before use.

### r2 (parked): 31. Packaging and release workflow (E8)

Issue: #31   Lane: Core (CI and release; this spec grants the paths below)   Status: draft. Cards 1 and 4 are T3 and need the council. Cards 2 and 3 are T2; card 3 is a context edit.

Revisions:
- 2026-10-20 r2, for the spec-critic findings (lead-filtered):
  - supply chain: the tag ruleset now restricts tag creation; build hashes are verified before upload; uv_build is pinned exactly on the release path; zizmor runs online in CI;
  - card 3's deny list is wider; card 4 is new (name registration);
  - verify retries every check and survives a pre-existing `tapesift` on PyPI;
  - a `--python 3.12` install run and a lock floor check are added; runner labels are pinned;
  - `doctor --json` is parsed with Python; 11 more tests; concurrency settings and a minutes estimate.

  Push-back is under "Where r2 departs from the findings".

#### Goal
After this PR, a `v*` tag pushed by the owner does the following:
1. builds one sdist and one wheel with `uv build --no-sources`, using an exactly pinned, hash-checked `uv_build`;
2. checks them and records their sha256;
3. installs the wheel in a clean glibc 2.28 Linux container and on a macOS arm64 runner, then runs:
   - `--version` and `doctor`;
   - `index` and `search` on speech.mp4;
   - the `[vision]` extra;
   - a `--python 3.12` install;
4. after the owner approves the protected `pypi` environment, re-verifies the sha256s and publishes through trusted publishing with PEP 740 (sigstore) attestations: to TestPyPI for `vX.Y.ZrcN`, and to PyPI for `vX.Y.Z`;
5. checks the published files, their attestations and `uvx` installs on fresh ubuntu and macOS runners;
6. drafts the GitHub release from the CHANGELOG.

Before the public flip, only steps 1 to 3 run: on packaging PRs and on manual dispatch, from the wheel artifact. Nothing is uploaded while the repo is private.

#### Read first
- Issue #31, in full, including "Stop and ask if" and the owner decisions.
- docs/spec.md:
  - Install and distribution (160-208): 184 (under 2 minutes), 206 (platforms), 208 (release mechanics);
  - the v0.1 exit criterion (333: "`uvx tapesift` works from PyPI on a fresh Linux and Mac machine");
  - E8 (342);
  - Y5 (535-541: "Agents never hold publish credentials. PyPI and GHCR publish only from CI through trusted publishing.");
  - the CI table (Orchestration: "Install test from the built wheel in a clean container | Release tag").
- **docs/specs/25-m1-interfaces.md (approved 2026-10-20).** E8 uses these names from it, and no others:
  - the `vision` extra (`transformers==5.20.2`, `torch>=2.14.1`, `pillow>=13.0.0`);
  - the `[[tool.uv.index]] pytorch-cpu` index and the `[tool.uv.sources]` torch entry. These are for dev and CI only and must never reach wheel metadata (its A7 check);
  - `doctor --json`'s `"vision"` key: `"transformers <v>, torch <v>"`, or null;
  - `search --json` printing `{"query": ..., "hits": [...]}` with `Hit` keys `path`, `start_s`, `modality` and `trust` (card 3);
  - `out_dir` defaulting to `tapesift_index` in the current directory, which `index` and `search` share (card 4);
  - card 10's floors: glibc 2.28+, and macOS 14+ on arm64;
  - the README note that Linux needs `--torch-backend cpu` to avoid CUDA wheels.
- `tapesift index PATH` and `tapesift search "query"` come from the CLI table in docs/spec.md (212-218). E8 uses no flag or type from the unapproved E6 or E7 specs. Exit codes are from spec 212.
- ADRs:
  - 0004 and its amendment (private until launch; flip before the first public release);
  - 0008 (nothing heavy on the laptop; CI runners may download models);
  - 0011 (Python 3.12 floor);
  - draft 0013 on branch `docs/v01-decisions`: Q4 A (macOS runs real models only in E8's tag install test), Q7 A (the talk check is X1 on Modal, not E8), Q9 A.
- Code and config:
  - `pyproject.toml` (static `version`; `uv_build>=0.11.27,<0.12.0`);
  - `src/tapesift/__init__.py` (`__version__ = version("tapesift")`);
  - `src/tapesift/cli/__init__.py` (`--version` prints `tapesift <v>`);
  - `src/tapesift/cli/doctor.py` (exit 3 only on `problems`; `MIN_FREE_DISK_GIB = 2.0`);
  - `.github/workflows/ci.yml` (action pins by SHA, `python3 scripts/ci/test_guard.py`);
  - `scripts/ci/test_guard.py` and `tests/unit/test_test_guard.py` (how a CI script is loaded in tests);
  - `.claude/settings.json` (`uv publish` denied, `git push` asks);
  - `CHANGELOG.md` (Keep a Changelog).
- **Observed by the planner on 2026-10-20:**
  - **Build output.**
    - `uv build --no-sources -o DIR` on main (uv 0.11.27) gives `tapesift-0.1.0.dev0-py3-none-any.whl` (29 578 B) and `tapesift-0.1.0.dev0.tar.gz` (24 732 B). Two builds are byte-identical.
    - The wheel holds only `tapesift/**` and `tapesift-<v>.dist-info/{METADATA,WHEEL,RECORD,entry_points.txt,licenses/LICENSE}`.
    - The sdist holds `PKG-INFO`, `pyproject.toml`, `README.md`, `LICENSE` and `src/**`.
    - uv also writes a `.gitignore` into the output dir.
    - METADATA is version 2.4, with `License-Expression: Apache-2.0` and `Requires-Python: >=3.12`.
  - **uv_build.** The latest release in pyproject's range is 0.11.33; the latest overall is 0.13.4. So the backend a CI build uses depends on which uv the runner has. `uv build` has `-b/--build-constraints` and `--require-hashes`.
  - **uv CLI.** uv 0.11.27 has `--torch-backend` (env `UV_TORCH_BACKEND`) on `uv tool install` and `uvx`, `--index-strategy`, env `UV_INDEX_URL` and `UV_EXTRA_INDEX_URL`, and `uv version --short`.
  - **Lock floor prototype.** A floor check on the M1 branch's `uv.lock` passes. It walks the 55-package runtime closure (base plus `vision`) and checks each package for a macOS arm64 wheel at 14.0 or older and an x86_64 wheel at glibc 2.28 or older. torch appears twice (CPU index and PyPI), and both entries are checked.
  - **Name.** `https://pypi.org/pypi/tapesift/json` and `https://test.pypi.org/pypi/tapesift/json` both return 404.
  - **Repo.** It is private and owned by a user account.
  - **Action pins.** Each tag was peeled with `gh api repos/<r>/git/ref/tags/<t>` (then `git/tags/<sha>` for annotated tags) in the owning repo, which rules out fork impostor commits:

    | Action | Tag | Commit |
    | --- | --- | --- |
    | pypa/gh-action-pypi-publish | v1.14.2 | `dc37677b2e1c63e2034f94d8a5b11f265b73ba33` |
    | pypa/gh-action-pypi-publish | v1.14.3, released 2026-10-20 | `7245906fb61fa33a13554f9d5fb856fe61758086` |
    | actions/upload-artifact | v7.0.2 | `cf430e030ddbb5b0abf93d22962f4752f3646cd9` |
    | actions/download-artifact | v8.0.2 | `9000827ccba6bdab643e8b6fd33ac0654aef8333` |
    | actions/checkout | v7.0.1 | `3d3c42e5aac5ba805825da76410c181273ba90b1` |
    | astral-sh/setup-uv | v10.3.0 | `1c37ad07a6a961277cf70c0d37d6f313000f5884` |

    The publish action's `attestations` input defaults to `'true'` ("Only works with PyPI and TestPyPI via Trusted Publishing"), and its `verify-metadata` input runs twine check.
  - **uv docs (guides/package).** Use `--no-sources` before publishing. `uv publish` uploads attestations but doesn't generate them.
  - **GitHub docs.** On Free, Pro and Team, environment required reviewers work only in public repos; artifact attestations need a public repo or Enterprise Cloud.
  - **Runner images.** macos-14 retires 2026-11-02, with brownouts through 2026-10-31. The runner-images README lists `macos-15` (arm64), `macos-26` (arm64, `macos-latest`) and `ubuntu-24.04` (`ubuntu-latest`).
  - **zizmor docs.** Online audits run only with `GH_TOKEN`, `GITHUB_TOKEN` or `ZIZMOR_GITHUB_TOKEN`; otherwise zizmor runs offline. Latest is 1.31.1 (MIT).
  - **PyPI docs.** A pending publisher "does not create a project or reserve a project's name until it is actually used to publish", and if someone else registers the name first, the pending publisher is invalidated. Provenance: `GET /integrity/<project>/<version>/<filename>/provenance`, and the response has `attestation_bundles`.

**Builds on main after M1 (#25) merges.** If `pyproject.toml` has no `vision` extra or no `[tool.uv.sources]` torch entry, stop: E8 checks M1's packaging and does not create it.

#### Scope
May change:
- `.github/workflows/install-test.yml` (new)
- `.github/workflows/release.yml` (new)
- `scripts/ci/release.py` (new): stdlib only
- `scripts/ci/install_check.sh` (new): bash 3.2 compatible, because macOS ships bash 3.2. No arrays.
- `scripts/ci/build-constraints.txt` (new): `uv-build==0.11.33` with a `--hash=sha256:` for every file of that release, from `https://pypi.org/pypi/uv-build/0.11.33/json` (card 2)
- `tests/unit/test_release.py` (new): 46 tests
- `docs/guides/release.md` (new): the owner's one-time setup and the per-release runbook (content below)
- `CHANGELOG.md`: one line under Unreleased, Added: `- Release workflow: a version tag builds the sdist and wheel, checks them, install-tests the wheel on Linux (glibc 2.28) and macOS, then publishes to TestPyPI (rc) or PyPI with trusted publishing and attestations once the owner approves (#31).`
- `.claude/settings.json`: only if card 3 is decided A, and only the lines it lists.

Must not touch:
- `pyproject.toml`, `uv.lock`. The version stays `0.1.0.dev0` in this PR; the release PRs bump it (runbook; T1). The uv_build pin lives in `build-constraints.txt`, not in `[build-system]`. Anything wrong in M1's packaging means a card, not an edit.
- `src/**`, `.github/workflows/ci.yml`, `.github/dependabot.yml` (follow-up, see Out of scope), `scripts/ci/test_guard.py`, `tests/fixtures/**`, and every existing test.
- `docs/spec.md`, `README.md` (E9), `AGENTS.md`, `CLAUDE.md`, `THIRD_PARTY.md`.
- GitHub settings, environments, rulesets, PyPI or TestPyPI accounts, and tags. Those belong to the owner (see "Owner steps").

#### Interfaces touched
Before: no release path. The version is static in `pyproject.toml` and read at runtime through `importlib.metadata`, which stays the only source of truth.

After: the files below. Nothing in `src/` changes. The names `release.yml` (the workflow file) and `pypi` (the environment) are registered in the PyPI and TestPyPI trusted publishers. Renaming either breaks publishing until the owner edits both publishers.

**The real guards are outside the workflow:**
- the tag ruleset (only the owner can create `v*` tags);
- the `pypi` environment (the owner approves each deployment, and only `v*` tags may deploy);
- the publisher binding (only `release.yml` in this repo, with environment `pypi`).

The checks inside the workflow (`plan`, hash checks) catch mistakes. They are advisory against an attacker, because a tagged commit runs whatever `release.yml` it contains.

##### `scripts/ci/release.py`
```python
"""Release checks for CI (#31): which index a tag publishes to, whether a built sdist and wheel
are fit to publish, whether uv.lock still meets the platform floors, and the CHANGELOG section
that becomes the release notes. Stdlib only: CI runs it with the runner's python3 before
anything is installed.

    python3 scripts/ci/release.py target TAG        # prints "testpypi" or "pypi"
    python3 scripts/ci/release.py check-dist DIR    # prints sizes, then "ok"
    python3 scripts/ci/release.py check-lock        # prints "ok"
    python3 scripts/ci/release.py notes VERSION     # prints the CHANGELOG section body
"""

ROOT: Final = Path(__file__).resolve().parents[2]
TAG_RE: Final = re.compile(r"v(\d+\.\d+\.\d+)(rc\d+)?")   # fullmatch; nothing else is released
MAX_DATA_BYTES: Final = 1_000_000   # issue #31: nothing over 1 MB in the wheel that isn't code
FORBIDDEN: Final = ("download.pytorch.org", "pytorch-cpu", "+cpu")   # M1: never in metadata
SDIST_TOP: Final = frozenset({"PKG-INFO", "pyproject.toml", "README.md", "LICENSE", "src"})
MACOS_FLOOR: Final = (14, 0)   # M1 card 10
GLIBC_FLOOR: Final = (2, 28)   # M1 card 10


def publish_target(tag: str, version: str) -> Literal["testpypi", "pypi"]:
    """"testpypi" for vX.Y.ZrcN, "pypi" for vX.Y.Z. ValueError unless TAG_RE fullmatches tag and
    tag == "v" + version (version is pyproject's [project].version, as written)."""


def norm_req(req: str) -> str:
    """The form requirements are compared in: lowercase, whitespace removed, '"' made "'"."""


def dist_problems(dist: Path, pyproject: Path) -> list[str]:
    """Every reason the sdist and wheel in `dist` are not fit to publish, one line each, each
    starting with the file it is about. [] when fit. Rules: "check-dist rules" below."""


def lock_floor_problems(lock: Path) -> list[str]:
    """Runtime packages in uv.lock that break card 10's floors, one line each; [] when none.
    Rules: "check-lock rules" below. A canary: users resolve fresh, so it can't prove the floor."""


def changelog_section(text: str, version: str) -> str:
    """Body of the section headed "## [<version>]" (optionally followed by " - YYYY-MM-DD"), up to
    the next line starting "## ", stripped. ValueError if there is no such heading or the body is
    empty. "## [0.1.0rc1]" is not "## [0.1.0]"."""


def main(argv: Sequence[str] | None = None, root: Path = ROOT) -> int:
    """target TAG | check-dist DIR | check-lock | notes VERSION, reading root/pyproject.toml,
    root/uv.lock and root/CHANGELOG.md. Exit 0 with the result on stdout; exit 1 with each
    problem on its own stderr line; argparse usage errors exit 2."""
```

**check-dist rules.** `V` is pyproject's `[project].version`. The checks run on the headers of the wheel's `METADATA` and the sdist's `PKG-INFO`, parsed with `email.parser.HeaderParser`. The long description is never checked, because a README may mention PyTorch.
1. `dist` holds exactly `tapesift-V-py3-none-any.whl` and `tapesift-V.tar.gz`, plus at most a `.gitignore`. Otherwise there is one problem and no further checks run.
2. Headers, in both files:
   - `Name == "tapesift"`;
   - `Version == V`;
   - `Requires-Python` equals pyproject's `requires-python`;
   - `License-Expression` equals pyproject's `license`;
   - `set(norm_req(r) for r in Requires-Dist)` equals the expected set. That is `norm_req(d)` for each `[project].dependencies`, plus `norm_req(f"{d}; extra == '{x}'")` for each `[project.optional-dependencies]` entry. Each missing and each unexpected entry is its own problem;
   - no `Requires-Dist` contains ` @ ` (a direct URL reference, which PyPI rejects);
   - the `Provides-Extra` set equals the optional-dependencies keys;
   - no header value contains any `FORBIDDEN` string (case-insensitive). The problem names the header and the string.
3. Every wheel member is under `tapesift/` or `tapesift-V.dist-info/`. Otherwise: `... is outside the tapesift package`.
4. Any wheel member over `MAX_DATA_BYTES` that isn't a `.py` file is a problem.
5. The wheel has `tapesift/__init__.py`, `tapesift/py.typed`, `tapesift-V.dist-info/licenses/LICENSE`, `tapesift-V.dist-info/METADATA`, and an `entry_points.txt` line `tapesift = tapesift.cli:main`.
6. Every sdist member is the directory `tapesift-V` or sits under it. Its first path part below `tapesift-V/` is in `SDIST_TOP`, and `PKG-INFO` is present.

`main check-dist` prints `"<file>: <size / 1e6:.2f> MB"` for the wheel, then the sdist, then `ok`.

**check-lock rules.** `uv.lock` is parsed with `tomllib`.
- The runtime closure starts at the `[[package]]` named `tapesift`: its `dependencies`, plus every list in its `optional-dependencies`.
- From there, it follows each package's `dependencies`. For a dependency entry with `extra = [...]`, it also follows those `optional-dependencies` of the target. Markers are ignored, which is conservative. Dev-only packages are never reached.
- Every package entry in the closure is checked, including both torch entries. The tags are parsed from the wheel filenames in `wheels[].url`:
  - if it has any `macosx_*` wheel, at least one must be `arm64` or `universal2` with (major, minor) ≤ `MACOS_FLOOR`. Otherwise: `uv.lock: <name> <version>: no macOS arm64 wheel for macOS 14`;
  - if it has any `manylinux*_x86_64` wheel, at least one must have glibc ≤ `GLIBC_FLOOR`. The legacy aliases are `manylinux1` = 2.5, `manylinux2010` = 2.12 and `manylinux2014` = 2.17. Otherwise: `uv.lock: <name> <version>: no x86_64 wheel for glibc 2.28`.
- Packages with no platform wheels pass.

##### `scripts/ci/install_check.sh`
`install_check.sh WHEEL [FIXTURE]`. `WHEEL` is an absolute path to `tapesift-V-py3-none-any.whl`, and `V` is parsed from the filename. If `FIXTURE` is given, the real-model steps run. `set -euo pipefail`. The script uses no arrays, because bash 3.2 errors on an empty array under `set -u`; every variable is assigned before use. `PY` is `"$(uv tool dir)/tapesift/bin/python"`. Each step prints one line, and any failure exits non-zero.
1. `cd "$(mktemp -d)"`. Every later step runs outside the checkout, so the tool, not the source, is what runs.
2. `uv tool install "$WHEEL"` with uv's default Python, timed with `date +%s`. Print `install_s=<n>`. **Fail if `n > 120`** (spec 184; issue #31 says stop and ask if over 2 minutes).
3. `test "$(tapesift --version)" = "tapesift $V"`.
4. `tapesift doctor --json > doctor.json` exits 0. Then `"$PY" - doctor.json "$V"` (a heredoc) checks `d["tapesift"] == V` and `d["problems"] == []`. Parsed with Python, not grep.
5. With `FIXTURE`:
   - copy it to `./speech.mp4`;
   - `tapesift index speech.mp4` exits 0;
   - `tapesift search "quarterly pricing review" --json > hits.json` exits 0;
   - then `"$PY" - hits.json` checks `hits[0]`: `modality == "speech"`, a `path` ending in `speech.mp4`, `start_s < 2.82` (speech.mp4's first voiced span, M1), and `trust == "untrusted_media"`. On failure it prints the hit and exits 1.
6. The vision install:
   - on Linux (`uname -s` = Linux), `UV_TORCH_BACKEND=cpu uv tool install --reinstall "tapesift[vision] @ file://$WHEEL"`;
   - on macOS, the same without the variable;
   - it is timed and prints `vision_install_s=<n>`. **Fail if `n > 300`**. That bounds CI minutes; Q1 measured 33 s on Linux with CUDA wheels and 10 s on macOS.
7. `tapesift doctor --json` piped to `"$PY"`, which checks that `d["vision"]` starts with `"transformers "` and contains `", torch "`.
8. `uv tool install --reinstall --python 3.12 "$WHEEL"`, then `test "$(tapesift --version)" = "tapesift $V"`, then `"$PY" -c 'import sys; assert sys.version_info[:2] == (3, 12)'`. The floor works even when uv's default Python is newer.

##### `.github/workflows/install-test.yml`
- Triggers:
  - `pull_request` (never `pull_request_target`), with `paths: [pyproject.toml, uv.lock, .github/workflows/install-test.yml, .github/workflows/release.yml, scripts/ci/release.py, scripts/ci/install_check.sh, scripts/ci/build-constraints.txt]`;
  - `workflow_dispatch` and `workflow_call`, each with input `models: {type: boolean, default: false}`.
- `workflow_call` declares the output `sha256: ${{ jobs.build.outputs.sha256 }}`.
- `permissions: {contents: read}`. No `id-token`, no secrets, and no publish step, ever.
- `concurrency: {group: install-test-${{ github.event_name }}-${{ github.ref }}, cancel-in-progress: ${{ github.event_name == 'pull_request' }}}`. A new push to a PR cancels the old run. Release runs are never cancelled, and their group differs from `release.yml`'s, so they can't deadlock.
- Every action is pinned by commit SHA, with the version in a comment. Every `actions/checkout` has `persist-credentials: false`. Every `setup-uv` has `enable-cache: false`. `inputs.*` reaches `run:` only through `env:`.
- Job `build` (`ubuntu-24.04`, 10 min). Output `sha256`.
  1. `uv build --no-sources -b scripts/ci/build-constraints.txt --require-hashes -o dist`;
  2. the same into `"$RUNNER_TEMP/rebuild"`, then `cmp` each file (reproducibility);
  3. `python3 scripts/ci/release.py check-dist dist | tee -a "$GITHUB_STEP_SUMMARY"`, then `python3 scripts/ci/release.py check-lock`;
  4. `(cd dist && sha256sum tapesift-*)` becomes the `sha256` output (multi-line, with a heredoc delimiter) and goes to the summary;
  5. `actions/upload-artifact` as `dist`, with `if-no-files-found: error` and `retention-days: 7`.
- Job `install`, which needs `build` (25 min, `fail-fast: false`). Matrix `os: [ubuntu-24.04, macos-15]`. macos-15 is the oldest arm64 image left once macos-14 retires, so it is closest to card 10's floor. It checks out (for the script and the fixture), sets up uv and downloads `dist`. `FIXTURE` is `tests/fixtures/speech.mp4` when `inputs.models` is true, and unset otherwise.
  - **Linux:** a clean container at the glibc floor. The image is pinned by digest, and the builder records the `docker buildx imagetools inspect almalinux:8` output in the PR. The host's uv is mounted read-only:
    ```bash
    docker run --rm -v "$PWD:/w:ro" -v "$(dirname "$(command -v uv)"):/opt/uv:ro" \
      -e PATH=/opt/uv:/root/.local/bin:/usr/local/bin:/usr/bin:/bin \
      almalinux:8@sha256:<digest> bash /w/scripts/ci/install_check.sh /w/dist/<wheel> [/w/tests/fixtures/speech.mp4]
    ```
  - **macOS:** `bash scripts/ci/install_check.sh "$PWD/dist/<wheel>" [...]` directly on the runner.
  - Both append their `install_s=` and `vision_install_s=` lines to `$GITHUB_STEP_SUMMARY`.
- Job `zizmor` (`ubuntu-24.04`, 5 min). It runs `if: github.event_name != 'push'`, so on PRs and dispatch but not inside a release. It runs `uvx zizmor==1.31.1 .github/workflows/release.yml .github/workflows/install-test.yml` online, with `GH_TOKEN: ${{ github.token }}`, the job's ephemeral read-only token, and fails on any finding.

**Minutes estimate (private repo, before the flip; the PR replaces it with measured numbers).** On GitHub Free, macOS minutes count 10x against the 2 000-minute monthly quota.
- A packaging-PR run is about 2 (build) + 1 (zizmor) + 6 (Linux install) + 5 × 10 (macOS install), so about 60 billed minutes.
- A `models=true` dispatch adds about 2 Linux and 3 × 10 macOS minutes, so about 90 in total.
- After the flip, standard runners in a public repo are free.

##### `.github/workflows/release.yml`
```yaml
name: release
on:
  push:
    tags: ["v*"]
permissions: {}
concurrency:
  group: release-${{ github.ref }}
  cancel-in-progress: false
```
Jobs, in order. Every job has `timeout-minutes`, and runners are `ubuntu-24.04` and `macos-15`. Tag and version values reach shell steps only through `env:` (`GITHUB_REF_NAME`, `needs.*.outputs.*`), never through `${{ }}` inside `run:`.

1. **`plan`** (`contents: read`; checkout with `fetch-depth: 0`). Outputs `target` and `version`. This job is advisory (see above).
   - **Refuses on a private repo.** A step with `if: github.event.repository.private` prints `::error::repo is private; nothing is published before the public flip (Q9, ADR 0004)` and exits 1.
   - `target=$(python3 scripts/ci/release.py target "$GITHUB_REF_NAME")`.
   - `git merge-base --is-ancestor "$GITHUB_SHA" origin/main`.
   - `python3 scripts/ci/release.py notes "$version" > notes.md`, uploaded as artifact `notes`.
2. **`test`**: `uses: ./.github/workflows/install-test.yml` with `models: true` and `permissions: {contents: read}`. It builds the artifact `dist` that gets published (one build per run) and runs the real-model check on macOS (Q4) and on Linux. Output: `sha256`.
3. **`publish-testpypi`** and **`publish-pypi`**. They need `[plan, test]` and are mutually exclusive on `needs.plan.outputs.target`. Each has `environment: pypi` (card 1), `permissions: {id-token: write}` and nothing else, and no checkout:
   ```yaml
       environment:
         name: pypi
         url: https://pypi.org/project/tapesift/${{ needs.plan.outputs.version }}/   # test.pypi.org for testpypi
       permissions:
         id-token: write
       steps:
         - uses: actions/download-artifact@9000827ccba6bdab643e8b6fd33ac0654aef8333 # v8.0.2
           with: { name: dist, path: dist }
         - name: files are the ones the install test passed
           env: { SHA256: "${{ needs.test.outputs.sha256 }}" }
           run: cd dist && printf '%s\n' "$SHA256" | sha256sum --check --strict && test "$(ls | wc -l)" -eq 2
         - uses: pypa/gh-action-pypi-publish@dc37677b2e1c63e2034f94d8a5b11f265b73ba33 # v1.14.2
           # publish-testpypi only: with: { repository-url: https://test.pypi.org/legacy/ }
   ```
   The publish jobs live in `release.yml` itself, not in a reusable workflow, because that file is what the trusted publisher matches.
4. **`verify`**. Needs `[plan, test, publish-testpypi, publish-pypi]` and runs `if: always() && (needs.publish-testpypi.result == 'success' || needs.publish-pypi.result == 'success')`, on matrix `[ubuntu-24.04, macos-15]` (fresh VMs).
   - A shell function `retry() { i=0; until "$@"; do i=$((i+1)); [ "$i" -ge 10 ] && return 1; sleep 30; done; }` wraps **every** network check below, because index and CDN propagation is not instant. Every `uvx` call has `--no-cache`, so a cached 404 is never reused.
   - **For rc,** one step writes three variables to `$GITHUB_ENV`:
     - `UV_INDEX_URL=https://test.pypi.org/simple/`;
     - `UV_EXTRA_INDEX_URL=https://pypi.org/simple/`;
     - `UV_INDEX_STRATEGY=unsafe-first-match`.

     uv searches the extra index (PyPI) first, so dependencies come from PyPI. With `unsafe-first-match`, a `tapesift` project already on PyPI (ours later, or a squatter) without `==V` falls through to TestPyPI instead of failing. For final releases nothing is set, so no empty array or variable is ever expanded.
   - **The files on the index are ours.** `retry` fetches `$HOST/pypi/tapesift/$V/json`. The set of `urls[].digests.sha256` must equal the hashes in `needs.test.outputs.sha256`. `HOST` is `https://test.pypi.org` or `https://pypi.org`.
   - `retry uvx --no-cache --from "tapesift==$V" tapesift --version` must print `tapesift $V`.
   - `retry uvx --no-cache --from "tapesift==$V" tapesift doctor --json`. The output is parsed with `python3 -c`: `tapesift == V` and `problems == []`.
   - `retry uvx --no-cache --from "tapesift[vision]==$V" tapesift doctor --json`, with `UV_TORCH_BACKEND=cpu` on Linux. `vision` must start with `"transformers "`.
   - Ubuntu only: for the wheel and the sdist, `retry curl -fsS --max-time 30 "$HOST/integrity/tapesift/$V/<file>/provenance"` returns JSON with a non-empty `attestation_bundles`.
5. **`github-release`**: needs `[plan, verify]`, `permissions: {contents: write}`. It downloads `dist` and `notes`, then runs `gh release create "$GITHUB_REF_NAME" --draft --verify-tag --title "$GITHUB_REF_NAME" --notes-file notes.md dist/tapesift-*`, adding `--prerelease` for rc, with `GH_TOKEN: ${{ github.token }}`. The release stays a draft until the owner publishes it.

##### Owner steps (the builder writes these into `docs/guides/release.md`, exactly)
Every outward action belongs to the owner. Agents never:
- create or push tags;
- approve deployments, in the UI, through the REST API or through GraphQL;
- create releases;
- edit environments, rulesets or publishers;
- run `uv publish`.

**One time, in this order, before `v0.1.0rc1`:**
1. **Flip** (Q9: on or before Oct 31; card 4 sets how close to the release). Settings > General > Danger Zone > Change visibility > Public. Required reviewers and rulesets need a public repo on this plan.
2. **Environment.** Settings > Environments > New environment `pypi`:
   - Required reviewers: `jahnavi-yelamanchi`;
   - leave "Prevent self-review" **off**, because the owner both pushes the tag and approves;
   - leave "Allow administrators to bypass configured protection rules" **off**;
   - Deployment branches and tags: "Selected branches and tags", with a tag rule `v*`;
   - no environment secrets.
3. **Tag ruleset.** Settings > Rules > Rulesets > New tag ruleset `release tags`:
   - Enforcement: Active; target: tags matching `v*`;
   - rules: **Restrict creations**, **Restrict updates** and **Restrict deletions**;
   - bypass list: the Repository admin role (the owner), with "Always". So only the owner can create a `v*` tag, and no released tag can move or vanish.
4. **Name check.** `curl -s -o /dev/null -w '%{http_code}\n' https://pypi.org/pypi/tapesift/json` and the same for `test.pypi.org` should both print 404. If either is taken, stop (ADR 0004, "Revisit if").
5. **TestPyPI pending publisher.** On test.pypi.org (a separate account, with 2FA), go to Account settings > Publishing > Add a new pending publisher > GitHub, and enter:
   - PyPI Project Name `tapesift`;
   - Owner `jahnavi-yelamanchi`;
   - Repository name `tapesift`;
   - Workflow name `release.yml`;
   - Environment name `pypi`.
6. **PyPI pending publisher.** The same on pypi.org (Account settings > Publishing). This doesn't reserve the name (card 4).

**Each release:**
1. The lead opens a release PR, `chore(release): vX`:
   - `uv version X` (pyproject.toml and uv.lock);
   - in CHANGELOG.md, the Unreleased lines move under `## [X] - YYYY-MM-DD`, with an empty `## [Unreleased]` above;
   - for `v0.1.0`, the `## [0.1.0rc1]` heading is renamed to `## [0.1.0] - <date>`.

   The owner merges it.
2. rc1 only, after E3, E6 and E7 are on main: the owner runs `gh workflow run install-test.yml --ref main -f models=true`, and it goes green.
3. The owner runs `git fetch origin && git tag vX <merge sha> && git push origin vX`. `<merge sha>` is the release PR's merge commit, where `uv version --short` prints X.
4. When `plan` and `test` are green, the owner opens the run and clicks Review deployments > `pypi` > Approve.
5. When `verify` is green, the owner reads the draft GitHub release and publishes it.
6. A failed publish never reuses a version: PyPI and TestPyPI refuse a filename that was ever uploaded. Fix it, then release `rc2` (or `0.1.1`).

#### Acceptance
`...` stands for `uv run pytest tests/unit/test_release.py -q`.

**Before merge (the builder, on the PR):**

| # | Check | Command | Expected |
| --- | --- | --- | --- |
| 1 | The unit tests | `...` | `46 passed` (breakdown below) |
| 2 | The gate | `make check` | exit 0; pyright `0 errors`; the test count is main's plus 46 |
| 3 | The real build passes the checks | `rm -rf /tmp/e8 && uv build --no-sources -b scripts/ci/build-constraints.txt --require-hashes -o /tmp/e8 && uv run python scripts/ci/release.py check-dist /tmp/e8` | two `... MB` lines, then `ok`, exit 0 |
| 4 | The lock meets the floors | `uv run python scripts/ci/release.py check-lock` | `ok`, exit 0 |
| 5 | Reproducible | `uv build --no-sources -b scripts/ci/build-constraints.txt --require-hashes -o /tmp/e8b && cmp /tmp/e8/*.whl /tmp/e8b/*.whl && cmp /tmp/e8/*.tar.gz /tmp/e8b/*.tar.gz && echo same` | `same` |
| 6 | Fails closed before the release PR | `uv run python scripts/ci/release.py notes 0.1.0rc1; echo $?` and `uv run python scripts/ci/release.py target v0.1.0rc1; echo $?` | each prints an error on stderr, then `1` |
| 7 | Only the publish jobs can mint an OIDC token | `grep -c 'id-token: write' .github/workflows/release.yml .github/workflows/install-test.yml` | `release.yml:2`, `install-test.yml:0` |
| 8 | Every action pinned by SHA | command A8 below | `0` |
| 9 | No stored credentials, no `pull_request_target` | `grep -cE 'secrets\.\|pull_request_target' .github/workflows/release.yml .github/workflows/install-test.yml` | `release.yml:0`, `install-test.yml:0` |
| 10 | No `${{ }}` inside any `run:` block | command A10 below | no output |
| 11 | zizmor, online | the `zizmor` job on the PR | green, with no findings. A false positive may be suppressed inline with `# zizmor: ignore[<rule>]` and a reason, listed in the PR as T1 |
| 12 | The install test on this PR (it triggers itself through `paths`) | the `install-test` run on the PR | `build` and both `install` jobs green. The PR's Numbers section records: wheel MB and sdist MB; `install_s` and `vision_install_s` on Linux (container) and macOS; the default Python uv picked on each; the container digest; the billed minutes of the run (against the estimate). `install_s` ≤ 120, `vision_install_s` ≤ 300 |

Command A8 (row 8). It counts `uses:` lines that are neither a local reusable workflow nor pinned to a 40-hex SHA. The planner checked it against ci.yml: it prints 0.
```bash
grep -hE '^\s*(-\s*)?uses:' .github/workflows/release.yml .github/workflows/install-test.yml \
  | grep -cvE 'uses: (\./\.github/workflows/[a-z-]+\.yml|[^@ ]+@[0-9a-f]{40}( |$))'
```

Command A10 (row 10). It prints every line inside a `run:` block that contains `${{`. The planner checked it with BSD awk: on ci.yml it flags the `test_guard.py --base origin/${{ github.base_ref }}` line, and it flags a multi-line `run: |` case.
```bash
awk '/^[ ]*(- )?run:/ { match($0, /^[ ]*/); ind = RLENGTH; inrun = 1; if ($0 ~ /\$\{\{/) print FILENAME ":" FNR ": " $0; next }
     inrun { match($0, /^[ ]*/); if (RLENGTH <= ind && $0 !~ /^[ ]*$/) inrun = 0; else if ($0 ~ /\$\{\{/) print FILENAME ":" FNR ": " $0 }' \
  .github/workflows/release.yml .github/workflows/install-test.yml
```

**After merge: manual checks the owner runs, needing post-flip state unless marked. Issue #31 closes when 14 to 16 pass.**

| # | Manual check (owner) | Expected |
| --- | --- | --- |
| 13 | Optional, before the flip: a `v*` tag pushed by mistake | `plan` fails on the private-repo step; no other job runs; nothing is uploaded |
| 14 | Before the flip is fine: dispatch `install-test.yml` with `models=true` (runbook step 2) | green on both OSes; the `index` and `search` checks pass |
| 15 | After the flip and owner steps 2-6: `v0.1.0rc1` | `plan` and `test` are green; the owner approves; TestPyPI publish succeeds. `verify`, on ubuntu and macOS: digests match, `tapesift 0.1.0rc1`, `doctor` and vision pass, and the provenance endpoint lists `attestation_bundles` for both files. A draft prerelease exists |
| 16 | `v0.1.0` | the same from PyPI. `uvx tapesift --version` on a fresh runner prints `tapesift 0.1.0` (spec 333) |

**Tests in `tests/unit/test_release.py`.** The module is loaded with `importlib` the way `test_test_guard.py` loads its script.

The tests share one baseline. A minimal `pyproject.toml` is written in `tmp_path`: version `0.1.0rc1`, `requires-python = ">=3.12"`, `license = "Apache-2.0"`, `dependencies = ["av>=19.0.1", "numpy>=2.5.4"]`, `vision = ["torch>=2.14.1"]`, and M1's `[tool.uv.sources]` torch entry, so the leak checks have a pyproject that really carries the CPU index. The dist that matches it is built with `zipfile` and `tarfile`. Its METADATA and PKG-INFO headers are:
- `Name: tapesift`
- `Version: 0.1.0rc1`
- `Requires-Python: >=3.12`
- `License-Expression: Apache-2.0`
- `Requires-Dist: av>=19.0.1`
- `Requires-Dist: numpy>=2.5.4`
- `Requires-Dist: torch>=2.14.1 ; extra == 'vision'`
- `Provides-Extra: vision`

The members are the ones rules 5 and 6 require.

There is also a baseline `uv.lock` text with these packages:
- `tapesift`: depends on `a`; `optional-dependencies.vision = [b]`;
- `a`: wheels `macosx_11_0_arm64` and `manylinux_2_17_x86_64`;
- `b`: depends on `c`, py3-none-any only;
- `c`: wheels `macosx_14_0_arm64` and `manylinux_2_28_x86_64`;
- `d`: dev-only, a `macosx_15_0_arm64` wheel only.

Each test changes one thing.

| Test | Count | Asserts |
| --- | --- | --- |
| `test_publish_target[<case>]` | 3 | `("v0.1.0rc1", "0.1.0rc1")` and `("v0.1.0rc10", "0.1.0rc10")` give `"testpypi"`; `("v0.1.0", "0.1.0")` gives `"pypi"` |
| `test_publish_target_rejects[<case>]` | 6 | `ValueError` for `v0.1.0a1`, `v0.1.0.post1`, `v0.1.0.dev0` (each with version equal to the tag minus `v`); `0.1.0rc1` (no `v`); `v0.1.0rc1-x`; `("v0.1.0", "0.1.0rc1")` (mismatch) |
| `test_norm_req[<case>]` | 3 | `'torch >= 2.14.1 ; extra == "vision"'` gives `"torch>=2.14.1;extra=='vision'"`; `"Pillow>=13.0.0"` gives `"pillow>=13.0.0"`; `"av>=19.0.1"` is unchanged |
| `test_clean_dist_passes` | 1 | `dist_problems(...) == []` |
| `test_cpu_index_in_headers_is_caught[<case>]` | 3 | (a) wheel header `Project-URL: torch, https://download.pytorch.org/whl/cpu`; (b) wheel `Requires-Dist: torch==2.14.1+cpu ; extra == 'vision'`; (c) the sdist PKG-INFO header from (a). Each gives a problem naming the file and the forbidden string |
| `test_readme_body_may_mention_pytorch` | 1 | A METADATA body of `Uses PyTorch from download.pytorch.org.` gives `[]` |
| `test_unmarked_extra_dep_is_caught` | 1 | `Requires-Dist: torch>=2.14.1` without the marker gives exactly two problems: missing `torch>=2.14.1;extra=='vision'` and unexpected `torch>=2.14.1` |
| `test_unexpected_dep_is_caught` | 1 | An added `Requires-Dist: requests` gives one problem naming `requests` |
| `test_direct_reference_is_caught` | 1 | `Requires-Dist: torch @ https://example.org/torch.whl ; extra == 'vision'`, with pyproject changed to match so the sets agree, gives a problem naming ` @ ` |
| `test_missing_provides_extra_is_caught` | 1 | Without `Provides-Extra: vision`, a problem names `vision` |
| `test_name_mismatch_is_caught` | 1 | `Name: tapesift-x` gives a problem |
| `test_version_mismatch_is_caught` | 1 | `Version: 0.1.0` in files named `0.1.0rc1` gives a problem naming both |
| `test_requires_python_mismatch_is_caught` | 1 | `Requires-Python: >=3.11` gives a problem |
| `test_license_mismatch_is_caught` | 1 | `License-Expression: MIT` gives a problem |
| `test_member_outside_package_is_caught` | 1 | Wheel member `tests/fixtures/speech.mp4` gives `... is outside the tapesift package` |
| `test_data_file_size_limit` | 1 | `tapesift/a.bin` of 1 000 000 bytes and `tapesift/big.py` of 2 000 000 bytes give `[]`; `tapesift/a.bin` of 1 000 001 bytes gives one problem |
| `test_required_member_missing[<case>]` | 4 | Each gives one problem: no `tapesift/py.typed`; no `licenses/LICENSE`; no `tapesift/__init__.py`; `entry_points.txt` without the `tapesift = tapesift.cli:main` line |
| `test_sdist_extra_member_is_caught` | 1 | `tapesift-0.1.0rc1/tests/fixtures/speech.mp4` in the sdist gives a problem |
| `test_dist_must_hold_one_wheel_and_one_sdist[<case>]` | 2 | An empty dir, and the baseline plus `tapesift-0.1.0-py3-none-any.whl`: each gives exactly one problem |
| `test_lock_floor_ok` | 1 | The baseline lock gives `[]` (d is dev-only, so it isn't reached) |
| `test_lock_floor_caught[<case>]` | 2 | `a` with only `macosx_15_0_arm64` (plus a `macosx_10_13_x86_64`) names `a` and macOS 14; `a` with only `manylinux_2_31_x86_64` names `a` and glibc 2.28 |
| `test_lock_floor_follows_extras` | 1 | `c` (reached only through the `vision` extra and `b`) with only `macosx_15_0_arm64` gives a problem naming `c` |
| `test_changelog_section[<case>]` | 2 | `## [0.1.0rc1]` and `## [0.1.0rc1] - 2026-10-29`, each followed by `### Added\n- x\n` and then `## [0.0.1]`, give `"### Added\n- x"` |
| `test_changelog_version_prefix_not_matched` | 1 | Text with only `## [0.1.0rc1]`: asking for `0.1.0` raises `ValueError` |
| `test_changelog_missing_or_empty[<case>]` | 2 | No heading raises `ValueError`; a heading with only whitespace before the next `## ` raises `ValueError` |
| `test_main_check_dist_ok` | 1 | `main(["check-dist", str(dist)], root=tmp_path) == 0`; stdout ends with `ok`; two lines contain ` MB` |
| `test_main_check_dist_fails` | 1 | With two injected problems: exit 1, and each problem is on its own stderr line |
| `test_main_target_mismatch_exits_1` | 1 | `main(["target", "v9.9.9"], root=tmp_path) == 1`, with the message on stderr |

**Test count, stated once:** 3 + 6 + 3 + 1 + 3 + 1 + 1 + 1 + 1 + 1 + 1 + 1 + 1 + 1 + 1 + 1 + 4 + 1 + 2 + 1 + 2 + 1 + 2 + 1 + 2 + 1 + 1 + 1 = **46**.

#### Out of scope
- **`.github/dependabot.yml`: a follow-up issue, not this PR.** The lead files "CI: Dependabot (or the Y5 agent routine) for GitHub Actions SHA pins". It would open PRs against `ci.yml`, which E8 must not touch. And Y5 already plans weekly dependency updates as an agent routine (week 4), so the mechanism is a separate choice.
- Docker images and GHCR (S5, v0.3). Spec 208 lists them under release mechanics; v0.1 ships none.
- GitHub artifact attestations (`actions/attest`). They need a public repo, and PEP 740 attestations on PyPI cover the files users install. A follow-up after the flip if wanted.
- `[project.urls]` and README rendering on PyPI, including the M1 note that Linux `[vision]` pulls CUDA torch (about 4 GB, Q1) unless `--torch-backend cpu` is given. These belong to E9 (#32). E8 tests only the `cpu` backend on Linux.
- Pinning `uv_build` in `[build-system]`. It would be a `pyproject.toml` edit. The release path pins it through `build-constraints.txt` instead (card 2); sdist users build with whatever backend their tool picks, as with any sdist.
- Versions derived from tags; publishing rc tags to PyPI (unless card 4 picks B); pre-release channels, yanking, signed tags, SBOMs and changelog automation.
- The Linux `models` CI job (E3, Q4). The talk check on a Modal CPU box (X1 #33, Q7). E8 spends nothing beyond GitHub Actions minutes.
- Windows/WSL2, Intel Macs (card 10), a macOS 14 runner (Risks), and making `install-test` a required check (it is path-filtered).

#### Risks
- **Name squatting before the first PyPI upload.** See card 4. The name was free on both indexes on 2026-10-20.
- **uv's default Python.** In the clean container, `uv tool install` downloads the newest CPython it manages. If a dependency has no wheel for it, step 2 fails while step 8 (3.12) would pass. Then stop and raise a card. The options are an upper bound on `requires-python`, or documenting `--python 3.12` in E9.
- **The macOS 14 floor isn't tested in CI.** macos-14 is gone after Nov 2. E8 tests macos-15, the closest image, and `check-lock` checks the wheel tags. E9 states the floor as "built for macOS 14+".
- **`check-lock` is a canary.** End users resolve fresh, so a new dependency release that drops macOS 14 breaks them even while the lock passes. `install_check.sh` on macos-15 catches it only if the floor rises above 15.
- **The glibc container.** If the host uv binary or a managed Python needs a newer glibc, the container step fails before tapesift is involved. The fallback (T1) is the static musl uv from the same release, with a pinned sha256. If a tapesift dependency fails at glibc 2.28, card 10's floor is wrong: stop and raise a card.
- **Time gates can flake** on a slow runner network. One re-run is allowed; two failures in a row are issue #31's "stop and ask".
- **A partial upload.** If the wheel uploads and the sdist doesn't, a re-run fails on "File already exists" (`skip-existing` is off). The owner decides between re-running with `skip-existing: true` (a one-line PR, T1) and moving to the next version. `verify`'s digest check fails until both files are there.
- **TestPyPI provenance.** TestPyPI runs the same Warehouse code. If its integrity endpoint 404s after 10 retries, report the response. That is a card (make TestPyPI's check advisory), not a silent removal.
- **`unsafe-first-match` in rc verification.** It is unsafe only in a single throwaway `verify` job, where PyPI is searched first for every package. The digest check, not the resolver, proves the files are ours.
- **Agents hold the owner's `gh` login.** See card 3.
- **Actions minutes before the flip.** See the estimate above. If Actions reports the quota is spent, stop: more minutes cost money.
- **The models step downloads weights from Hugging Face** on runners (allowed by ADR 0008). An HF outage fails the tag run; a re-run is the fix.
- **The release section format.** `notes` matches only `## [X]` or `## [X] - YYYY-MM-DD`. A wrong heading fails `plan` before any approval, which is the intent.

#### Where r2 departs from the findings
- **zizmor online runs in CI, not on the laptop.** Online mode needs a GitHub token (zizmor docs). On the laptop, that would be the owner's `gh` token handed to a third-party binary, which is a credentials card. The CI job uses its own ephemeral, read-only `github.token`.
- **Dependabot is a follow-up issue,** for the reasons in Out of scope.
- **The `${{ }}`-in-`run:` check is awk (A10),** not a plain grep. A grep sees only one-line `run:` steps and misses `run: |` blocks.
- **`gh api *git/refs*` blocks ref creation, not the reads planners use.** Ref creation is `POST /repos/{o}/{r}/git/refs` (plural). The SHA peeling above uses `git/ref/tags/...` (singular), which stays allowed.

#### Decision cards

##### Decision needed (T3): card 1. How a tag becomes a public upload
Context: Q9 A decided to publish. Several things can't be undone:
- the upload itself: a PyPI filename can never be reused, and the source is public for good;
- project ownership on PyPI;
- the publisher identity (`release.yml` and `pypi`).

A tagged commit runs whatever `release.yml` it contains. So checks inside the workflow can't stop someone who can create tags; only the repo's settings can.

Options:
- **A. Settings are the guards, the workflow catches mistakes** (assumed above).
  - Real guards: a tag ruleset that restricts `v*` creation, update and deletion to the owner (admin bypass); the `pypi` environment, with the owner as required reviewer and only `v*` tags allowed; and the PyPI/TestPyPI publishers bound to `release.yml` and `pypi`.
  - Advisory guards: `plan` refuses a private repo, a tag that differs from pyproject or isn't `X.Y.Z`/`X.Y.ZrcN`, a commit not on main, and a missing CHANGELOG section. The upload waits for the full install test with real models, and publish re-checks the tested sha256s.
  - One environment guards both TestPyPI and PyPI.

  Pros: no single action by anyone uploads; every mistake is caught before the approval prompt. Cons: two owner actions per release; TestPyPI also waits for approval.
- **B. The tag push alone publishes** (the ruleset, but no required reviewer). Pros: one step. Cons: a mistyped tag is a permanent upload.
- **C. An owner-only `workflow_dispatch` with a version input**, and no tag trigger. Pros: an explicit button. Cons: spec 208 says tags; a dispatch can run from any branch unless guarded; the version and tag can drift.

Hardest to reverse: any PyPI upload, then the registered publisher names.
Recommendation: A.
Would change my mind: the owner wants TestPyPI uploads without approval. Then use two environments, with no reviewer on `testpypi`, and edit owner step 5.
Blocked until answered: the `publish-*` jobs and owner steps 2, 3, 5 and 6.

##### Decision needed (T2): card 2. Release-path supply chain: the publish action, the build backend, the hand-off
Context: The issue asks for trusted publishing and sigstore attestations. `uv publish` uploads attestations but doesn't generate them (uv docs). A new action in the `id-token: write` job is a dependency (AGENTS.md). Separately, pyproject allows `uv_build>=0.11.27,<0.12.0`, so the backend a release uses depends on the runner's uv: today 0.11.33 is the newest in range, and uv's own build fast path applies only when uv's version matches.

Options:
- **A** (assumed above), three parts:
  1. `pypa/gh-action-pypi-publish` v1.14.2 at `dc37677b2e1c63e2034f94d8a5b11f265b73ba33`, verified by peeling the tag in pypa's repo. It makes PEP 740 attestations by default and runs twine's check.
  2. `uv build -b scripts/ci/build-constraints.txt --require-hashes`, pinning `uv-build==0.11.33` with every file's sha256. CI-only; pyproject is untouched.
  3. The build job's sha256 output is checked in the publish job before upload, and again against the index after it.

  Pros: the PyPA path in PyPI's own guide; a known, hash-checked backend; the tested bytes are the uploaded bytes. Cons: a third-party Docker action in the most privileged job; one more file to bump when uv_build moves.
- **B. `uv publish --trusted-publishing always` plus a separate signer** (for example `pypi-attestations sign` via uvx), with the same pin and hand-off. Cons: two tools; the signer is also third-party.
- **C. `uv publish` with no attestations and no build pin.** Cons: drops what the issue asked for, and the build is not reproducible over time.

Hardest to reverse: none; releases already published keep whatever they shipped with.
Recommendation: A. v1.14.3 came out on 2026-10-20. Pin v1.14.2 unless v1.14.3's notes list a security fix; in that case pin `7245906fb61fa33a13554f9d5fb856fe61758086` and say so in the PR (T1).
Would change my mind: uv gains attestation generation before the flip (then B without the signer), or the owner prefers the pin in `[build-system]` (a pyproject edit).
Blocked until answered: the publish steps and `build-constraints.txt`.

##### Decision needed (T2, security; a context edit the owner approves at gate 4): card 3. Deny rules for outward release commands
Context: The `pypi` reviewer is the owner, and Claude Code agents run `gh` logged in as the owner. `git push *` already asks, but nothing stops an agent from doing any of these as the owner:
- approving a pending deployment (REST `pending_deployments` or the GraphQL `approveDeployments` mutation);
- creating a tag ref or a release through the API;
- editing rulesets;
- dispatching a workflow.

Options:
- **A. Add these to `.claude/settings.json`** in this PR:
  - `deny`:
    - `Bash(git tag *)`, `Bash(git push --tags*)`, `Bash(git push *refs/tags*)`, `Bash(git push --follow-tags*)`;
    - `Bash(gh release *)`;
    - `Bash(gh api *git/refs*)`, `Bash(gh api *releases*)`, `Bash(gh api *rulesets*)`, `Bash(gh api *deployment*)`, `Bash(gh api *environments*)`;
    - `Bash(gh api graphql*)`;
  - `ask`: `Bash(gh workflow run *)`.

  **Why `gh api graphql` is denied whole.** GraphQL exposes `approveDeployments`, `createRef` and ruleset mutations. A narrower pattern can't tell a read from a write, because the query can come from a file (`-F query=@q.graphql`). Agents read through `gh issue view`, `gh pr view` and REST `gh api` GETs, which stay allowed. `gh pr view` uses GraphQL internally, but the rule matches the typed command, not the HTTP call. `git push origin vX` by name is still only an ask, because a pattern for "a tag-shaped refspec" would also catch branch names. The ruleset (card 1) is the hard stop there.

  The owner checks with `/permissions` that each pattern matches as intended. Pros: the "owner only" rule is enforced, not just written down. Cons: a seatbelt, not a sandbox (curl with a token gets around it); REST reads of releases, deployments and environments are blocked too.
- **B. AGENTS.md text only.** Cons: depends on agents behaving, for the one irreversible action in the project.
- **C. Run agents with a separate token** that can't approve deployments or create refs. Pros: the real fix. Cons: owner setup across every session.

Hardest to reverse: none.
Recommendation: A now, then C after v0.1 if agents get more autonomy (the step 2.5 gate).
Would change my mind: the owner already runs agents with such a token.
Blocked until answered: only the `.claude/settings.json` lines.

##### Decision needed (T3): card 4. When the `tapesift` name is first claimed on PyPI
Context:
- A pending publisher doesn't reserve the name, and is invalidated if someone registers the name first (PyPI docs).
- TestPyPI and PyPI are separate namespaces, so `rc1` on TestPyPI protects nothing on PyPI.
- Trusted publishing needs the public flip (the environment's required reviewer needs a public repo on this plan). So without a token, the earliest PyPI claim is the first PyPI upload after the flip.
- The exposure really starts at the flip, when the repo and its name become visible.
- A PEP 541 reclaim of a squatted name takes weeks to months, and a rename touches ADR 0004, the CLI, the package and the docs.
- The name was free on 2026-10-20.

Options:
- **A. Accept the risk, and keep the flip-to-PyPI window short** (assumed above). The flip, owner steps 2-6, `v0.1.0rc1` on TestPyPI and `v0.1.0` on PyPI all happen within about 48 hours, and the owner reruns the 404 check (step 4) just before each tag. Pros: Q9 as decided; no extra upload. Cons: a squat in that window costs a rename.
- **B. rc tags also go to PyPI.** `publish-pypi` runs for rc as well, after `publish-testpypi` succeeds; it is a second approval. PyPI holds the name from the rc1 tag, hours after the flip. Pre-releases aren't installed by `uvx tapesift` unless pinned. Pros: no token; closes the window to the time it takes to tag. Cons: an rc is permanently on PyPI; it changes Q9's "TestPyPI first" to "TestPyPI and PyPI"; one more job condition and one more test case.
- **C. The owner claims the name now with a placeholder:** a minimal `tapesift 0.0.0` sdist with no source, uploaded from the owner's laptop with a project-scoped API token that is deleted right after. Trusted publishing is then added to the existing project. Pros: the only way to claim the name before the flip. Cons: an exception to spec 540 / Y5 ("publish only from CI through trusted publishing") for one upload; a token exists briefly; a permanent placeholder release.

Hardest to reverse: a lost name, then any upload (B, C).
Recommendation: A, given Q9's timing and a quiet repo. B if the owner wants certainty without a token. C only if the owner wants the name held before the flip.
Would change my mind: anything that publicizes the repo or name before the flip (a post, a talk), which makes B or C worth it.
Blocked until answered: nothing in the build. The answer sets the timing in owner step 1 and, for B, the `publish-pypi` condition.

##### T1 calls (no card; listed in the PR)
- The version stays `0.1.0.dev0` in this PR. `uv version X` in a release PR bumps it.
- A stdlib `release.py`, not a twine step in CI. The publish action runs twine's check anyway (card 2).
- Linux is tested in `almalinux:8` (glibc 2.28) by `docker run` on `ubuntu-24.04`. macOS is tested on `macos-15`, pinned rather than `-latest`, as the closest image to the floor.
- Reproducibility means two builds on one runner are byte-identical, with a pinned backend. Cross-OS identity is not claimed.
- Caches are off in both workflows. The default-Python install is timed as a stranger would see it; the `--python 3.12` run is not timed.
- Time gates: 120 s for the base install (spec 184), 300 s for the vision install (minutes).
- `verify` retries each network check 10 times at 30 s; rc verification uses `unsafe-first-match`.
- The GitHub release is created as a draft; publishing it is the owner's.
- Install-test concurrency cancels superseded PR runs only.
