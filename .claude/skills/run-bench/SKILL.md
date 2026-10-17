---
name: run-bench
description: How to measure performance in tapesift so a speed or cost claim can merge. Use for any PR that claims faster, cheaper or less memory.
---
# Run a benchmark

No number, no merge for perf PRs.

## Where
- Never on the laptop for GPU numbers. GPU numbers come from Modal (`bench/` scripts, `modal run bench/<script>.py`) on a named GPU type, e.g. L4.
- CPU-only microbenchmarks may run on the laptop, labelled with the machine (`sysctl -n machdep.cpu.brand_string`).
- Before and after run on the same GPU type, same driver, same fixture set, same commit of the bench script.

## How
1. Profile first (`--trace out.json`, open in Perfetto once C1 lands). Write the hypothesis in the PR.
2. Change one thing.
3. Run 3 times each side. Report the median and the spread (min to max).
4. Commit the `bench.json` diff with the PR (CI marks perf PRs without it as "needs numbers").

## Report format
| Metric | Before (median, min-max) | After | Change |
| --- | --- | --- | --- |
| video-hours / GPU-hour | | | |
| $ / video-hour (at $X/h) | | | |
| peak VRAM | | | |

Modal runs cost money: an agent asks before `modal run` (it is an `ask` rule in .claude/settings.json).
