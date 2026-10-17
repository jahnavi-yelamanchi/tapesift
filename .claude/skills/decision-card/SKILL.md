---
name: decision-card
description: Decision tiers T0-T3 and the decision-card template for tapesift. Use whenever a choice might be costly to reverse, or a stop rule in AGENTS.md fires.
---
# Decision cards

## Tiers
| Tier | Examples | Who decides |
| --- | --- | --- |
| T0 trivial | Local names, helper layout, test file structure | You. Record nothing. |
| T1 cheap to reverse | Internal module split, which approved library to use | You. One line in the PR's Decisions list. |
| T2 costly to reverse | New dependency, config key, default value, perf vs quality tradeoff | The owner, from a card. Stop. |
| T3 one-way door | Output schema, CLI names, interfaces, license, training data, public benchmark claims | The owner, after a two-model council. Stop. |

If unsure between two tiers, pick the higher one.

## Template (write exactly this, then stop)
```markdown
### Decision needed (T2 or T3): <one line>
Context: <2-3 lines, with numbers if any>
Options:
A. <option>. Pros: ... Cons: ...
B. <option>. Pros: ... Cons: ...
C. <option, if a real third exists>
Hardest to reverse: <A, B or C, and why>
Recommendation: <letter>, because <one reason>
Would change my mind: <evidence>
Blocked until answered: <what work waits>
```

## Example 1 (T2, from this repo)
```markdown
### Decision needed (T2): How to synthesize the English speech fixture
Context: E3 needs a short English clip with a known transcript. FFmpeg test sources only make tones and noise; AGENTS rules allow only FFmpeg sources.
Options:
A. espeak-ng. Pros: license-free output, scriptable on mac and Linux. Cons: robotic voice.
B. macOS `say`. Pros: natural voice. Cons: mac only, unclear terms.
C. Owner records 20 s. Pros: real voice. Cons: not scriptable; personal voice in a public repo.
Hardest to reverse: C, a voice in git history stays forever.
Recommendation: A, because fixtures must regenerate from a script.
Would change my mind: a permissive natural TTS that scripts the same way.
Blocked until answered: the speech fixture.
```
Outcome: A, recorded as ADR 0007.

## Example 2 (T3)
```markdown
### Decision needed (T3): Asset ID scheme
Context: a full sha256 reads every byte, and archives hold thousands of multi-GB files; asset IDs are stored in every index and output.
Options:
A. sha256(size + first 8 MB + last 8 MB). Pros: constant time. Cons: two files differing only in the middle collide.
B. Full sha256. Pros: no collisions. Cons: slow on big archives.
C. A, with full hash opt-in via config. Pros: fast default, escape hatch. Cons: two ID kinds to document.
Hardest to reverse: any of them, IDs persist in user indexes.
Recommendation: C, because the default must stay fast and the risk is written down.
Would change my mind: a real-world collision report.
Blocked until answered: E1.
```
