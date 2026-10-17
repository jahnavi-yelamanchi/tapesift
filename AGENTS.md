# tapesift agent guide
Self-hosted engine: video and audio in, timestamped searchable data out.
Spec: docs/spec.md. Feature specs: docs/specs/. Decisions: docs/adr/.

## Commands
- Setup: uv sync --all-extras
- Everything: make check   (must pass before you say done)
- Fast loop: uv run pytest tests/unit -x -q
- Smoke: uv run pytest tests/smoke -q

## Lanes (edit only your spec's paths)
- Core: src/tapesift/{cli,pipeline,runner,store,audio,vision,serve}/
- Media: src/tapesift/media/, src/tapesift/kernels/, scripts/make_fixtures.py
- Eval: src/tapesift/{eval,safety}/, bench/, evals/
- Train: src/tapesift/train/
- Docs: docs/, README.md, devlog/

## Code rules
- Timestamps come from PTS, in seconds. Never frame_index / fps.
- One bad file never fails a batch: catch per file, record a warning code.
- Typed code; pyright strict passes on src/. No print; use the logger.
- Every network or subprocess call has a timeout.
- New behavior starts with tests from the spec; a bug fix starts with a failing test.

## Compute (ADR 0008)
- The laptop runs code, unit tests and fixture smoke tests only. Never download model weights or datasets locally, never train locally.
- Real models use fake backends in local tests. GPU work runs on Modal (scripts in bench/ or tests/gpu/); long training on Vast.ai; datasets and adapters live on the Hugging Face Hub, pinned by revision.

## Decision tiers
- T0 trivial, T1 cheap to reverse: decide; list T1 calls in the PR.
- T2 costly to reverse, T3 one-way door: write a decision card, then stop.

## Stop and raise a decision card before you
- add, remove or upgrade a dependency
- change a public interface, the output schema, a CLI command or flag, or a config key or default
- delete, skip, loosen or rewrite an existing test
- edit outside the paths in your spec
- touch licensing, privacy, security, credentials or training data
- start anything that costs money
- fail the same error twice in a row (write what you tried and your best guess)
- find the spec ambiguous

## Decision card format
### Decision needed (T2 or T3): <one line>
Context / Options A-C with pros and cons / Hardest to reverse /
Recommendation / Would change my mind / Blocked until answered

## Done means
make check green, the spec's acceptance commands pass, docs and CHANGELOG updated.
PR description sections: Summary, How tested (with output), Numbers (perf only),
Decisions (T0/T1), Cards raised, Open questions.
Never push to main, publish, or post. Draft PRs only.
