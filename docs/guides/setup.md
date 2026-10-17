# Setup: dev machine, agents and cloud compute

How to run tapesift's build loop day to day. The *what* lives in [docs/spec.md](../spec.md); the agent roles, gates and prompts in [docs/workflow.md](../workflow.md). This page is the *how to switch it on*.

Rule zero (ADR 0008): the laptop builds code. It never downloads model weights or datasets and never trains. Anything heavier runs in the cloud from a script in this repo.

## 1. One-time setup (about 30 minutes)

Already installed on this Mac: git, uv, gh (logged in), ffmpeg, espeak-ng, codex, herdr, modal (logged in), hf, pre-commit.

```bash
cd ~/Documents/GitHub/tapesift
uv sync --all-extras          # dev tools into .venv
uv run pre-commit install     # ruff + hygiene checks on every commit
make check                    # must be green

# GitHub (P0.1, P0.4): public repo, CI, protected main
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
codex login
claude                         # accept workspace trust once, then run /auto-mode-setup
herdr workspace create --cwd ~/Documents/GitHub/tapesift --label tapesift
npx skills add ogulcancelik/herdr --skill herdr -g   # lets Claude drive herdr panes
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

**Morning (20 min)**
1. `herdr` to reattach.
2. Clear **blocked** panes first: each holds a decision card. Write your own pick in `docs/decisions-scorecard.md` before reading the agent's.
3. Review **done** PRs that already have the other model's review. Merge (squash) or send prompt P7.
4. In the `lead` pane: `@agent-planner Write the spec for issue #<N>.` Approve the spec (gate 1), label the issue `agent-ready`.
5. Launch squads:
   ```bash
   # Claude squad (Core, Train, Docs lanes)
   herdr pane run w1:p2 "claude --agent feature-builder --worktree e1-probe 'Build issue #12 from docs/specs/12-probe.md.'"
   # Codex squad (Media, Eval lanes)
   git worktree add ../tapesift-wt/e2-decode -b feat/e2-decode
   herdr agent start e2 --kind codex --pane w1:p3 -- -C ../tapesift-wt/e2-decode --sandbox workspace-write -a on-request
   herdr agent prompt e2 "<prompt P3 from docs/workflow.md, issue #13>"
   ```

**Evening (90 min)**
1. Cross-review: `codex review --base main` in Claude worktrees; `@agent-reviewer Review branch <b> against docs/specs/<spec>.md` for Codex branches.
2. Merge or send fixes.
3. Your hand-written piece (scheduler core, Triton dedupe kernel, tIoU metric, reward functions). No agent writes these.
4. `@agent-scribe` for changelog, devlog drafts and metrics; then prompt P12 on the day's best PR, answered out loud.

## 4. Fixtures

`make fixtures` rebuilds `tests/fixtures/` (needs ffmpeg and espeak-ng). Output is byte-identical on the same FFmpeg version; `tests/unit/test_fixtures.py` pins every file's sha256, so an accidental change fails CI. To add one, follow `.claude/skills/add-fixture/SKILL.md`.

## 5. Troubleshooting

| Symptom | Fix |
| --- | --- |
| `make check` fails on format | `make fmt` |
| Modal image build 404s on apt | Base images must be current Debian; `debian_slim()` on an old builder version is bullseye. Use `from_registry("python:3.12-slim-trixie")` |
| Modal function "crash-looping" | It failed at import inside the container. Code at module level runs there too; guard local-only paths with `modal.is_local()` |
| A Modal app keeps running | `uvx --from modal==1.5.1 modal app list`, then `modal app stop -y <id>` |
| An agent pane sits idle | It is blocked on a permission or a card; it shows as blocked in herdr |
