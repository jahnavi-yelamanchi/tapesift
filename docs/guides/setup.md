# Setup: dev machine, agents and cloud compute

How to run tapesift's build loop day to day. The *what* lives in [docs/spec.md](../spec.md); the agent roles, gates and prompts in [docs/workflow.md](../workflow.md). This page is the *how to switch it on*.

Rule zero (ADR 0008): the laptop builds code. It never downloads model weights or datasets and never trains. Anything heavier runs in the cloud from a script in this repo.

## 1. One-time setup (about 30 minutes)

Already installed on this Mac: git, uv, gh (logged in), ffmpeg, espeak-ng, herdr, modal (logged in), hf, pre-commit.

```bash
cd ~/Documents/GitHub/tapesift
uv sync --all-extras          # dev tools into .venv
uv run pre-commit install     # ruff + hygiene checks on every commit
make check                    # must be green

# GitHub (P0.1, P0.4): repo, CI, protected main. Set protection after CI has run once,
# so the job names below exist.
gh repo create jahnavi-yelamanchi/tapesift --public --source . --push \
  --description "Self-hosted engine: video and audio in, timestamped searchable data out."
gh api -X PUT repos/jahnavi-yelamanchi/tapesift/branches/main/protection --input - <<'EOF'
{"required_status_checks": {"strict": true, "contexts": [
   "format, lint, type check",
   "tests (ubuntu-latest, py3.11)", "tests (ubuntu-latest, py3.12)", "tests (macos-latest, py3.12)",
   "no tests removed or skipped without a card"]},
 "enforce_admins": false,
 "required_pull_request_reviews": {"required_approving_review_count": 0},
 "restrictions": null, "allow_force_pushes": false, "allow_deletions": false}
EOF

# Hugging Face (datasets, eval suites, adapters live here)
hf auth login                  # token with write access to your namespace
# Same token for Modal jobs, never in the repo:
modal secret create huggingface HF_TOKEN=<token>

# Vast.ai (long training runs only, from v0.6)
uv tool install vastai && vastai set api-key <key>

# Agents
claude                         # accept workspace trust once, then run /auto-mode-setup
# Optional: herdr keeps the lead session alive across laptop sleeps
# herdr workspace create --cwd ~/Documents/GitHub/tapesift --label tapesift
```

Spending guardrail (decision D9, default $100 a month): set a workspace budget in the Modal dashboard (Settings, Usage and billing) and a credit cap on Vast. Agents must ask before `modal run` and `vastai` (ask rules in `.claude/settings.json`).

## 2. What runs where

| Work | Where | How |
| --- | --- | --- |
| Write code, unit tests, fixture smoke tests | Laptop | `make check` |
| Every PR's checks (Linux 3.11, 3.12, macOS) | GitHub Actions | automatic |
| GPU tests, `doctor` on a real GPU | Modal | `uvx --from modal==1.5.1 modal run scripts/cloud/modal_gpu.py --gpu L4` |
| Benchmarks (C2, C7, L2) | Modal, named GPU type | scripts in `bench/` (from v0.2) |
| Eval suites (V1-V5) | Modal | scripts in `evals/` (from v0.5) |
| SFT, GRPO, self-training rounds (T2-T5, R1-R2) | Vast.ai for long runs, Modal for short ones | scripts in `src/tapesift/train/` (from v0.6) |
| Poking at a model or dataset interactively | Colab | notebooks are scratch: no published number comes from one |
| Datasets, frozen eval suites, adapters | Hugging Face Hub | pinned by revision; you upload, agents never do (`hf upload` is denied) |

Modal GPU names to use: `T4`, `L4`, `A10G`, `L40S`, `A100-80GB`, `H100`. Pass any of them as `--gpu`.

## 3. The daily loop

Full detail: [docs/workflow.md](../workflow.md), sections "Feature squads" and "Running it day to day". Short form:

Everything runs from one lead Claude session in the repo (ADR 0009). It dispatches subagents in parallel at every step; you only act at the four gates. Prompts P1-P12 are in [docs/workflow.md](../workflow.md#prompt-library).

| Step | Subagents the lead dispatches | Your gate |
| --- | --- | --- |
| Spec | `planner` per issue, then `spec-critic` per draft, in parallel; lead commits approved specs on local main | 1: approve spec |
| Build | `feature-builder` per spec, each in its own worktree, in parallel; each calls `test-writer` (and `fixture-maker`) | 2: answer decision cards |
| Review | `reviewer` (opus) + `test-auditor` (sonnet) per PR, in parallel; lead verifies findings | 3: merge |
| Fix | same builder, resumed with its context | |
| T3 decision | two `council` subagents (opus, sonnet), then a rebuttal round | 2: decide |
| Bookkeeping | `scribe` (haiku) | 4: approve context edits |

**Morning (20 min)**
1. `cd ~/Documents/GitHub/tapesift && claude --continue` (or `claude agents` for background sessions).
2. Answer decision cards the lead surfaced. Write your own pick in `docs/decisions-scorecard.md` before reading the agent's.
3. Review draft PRs that have reviewer and test-auditor results. Squash-merge, or let P7 run.
4. Send P1 for 1-3 `agent-ready` issues; approve the specs.
5. Send P2: one builder per approved spec, in parallel. Each builder's `git push` and `gh pr create` ask you first (ask rules until step 2); approve them when they surface.

**Evening (90 min)**
1. Send P5 for each finished PR; read verified findings and diffs; merge or let P7 run.
2. Council (P8, P9) if a T3 card waits.
3. Your hand-written piece (scheduler core, Triton dedupe kernel, tIoU metric, reward functions). No agent writes these.
4. P11 (scribe), then P12 on the day's best PR, answered out loud.

## 4. Fixtures

`make fixtures` rebuilds `tests/fixtures/` (needs ffmpeg and espeak-ng). Output is byte-identical on the same FFmpeg version; `tests/unit/test_fixtures.py` pins every file's sha256, so an accidental change fails CI. To add one, follow `.claude/skills/add-fixture/SKILL.md`.

## 5. Troubleshooting

| Symptom | Fix |
| --- | --- |
| `make check` fails on format | `make fmt` |
| Modal image build 404s on apt | Base images must be current Debian; `debian_slim()` on an old builder version is bullseye. Use `from_registry("python:3.12-slim-trixie")` |
| Modal function "crash-looping" | It failed at import inside the container. Code at module level runs there too; guard local-only paths with `modal.is_local()` |
| A Modal app keeps running | `uvx --from modal==1.5.1 modal app list`, then `modal app stop -y <id>` |
| A subagent goes quiet | It is waiting on a permission or a decision card; the lead surfaces it |
| A builder's worktree is left behind | `git worktree list`; if clean, `git worktree unlock <path>` then `git worktree remove <path>` |
