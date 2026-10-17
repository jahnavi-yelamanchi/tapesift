---
name: ship-feature
description: The 7-step self-check every builder runs before opening a PR in tapesift. Use before `gh pr create`.
---
# Ship a feature

Do all seven. Paste the output of 1, 2 and 3 into the PR.

1. `make check` is green. Paste the last lines.
2. Every acceptance command in the spec runs and shows the expected output. Paste it.
3. `git diff --stat origin/main...HEAD`: every file is inside the spec's "paths you may change". Anything else needs a decision card.
4. No test was deleted, skipped, xfailed or loosened (`python3 scripts/ci/test_guard.py --base origin/main` exits 0).
5. Docs updated (CLI help, README section or docs page) and exactly one `CHANGELOG.md` line under Unreleased.
6. Performance claims only: median of 3 runs before and after, same machine, with spread (see run-bench).
7. Open a **draft** PR with `.github/pull_request_template.md` filled in: Summary, Spec, How tested, Numbers, Decisions (T0/T1), Decision cards raised, Open questions.
