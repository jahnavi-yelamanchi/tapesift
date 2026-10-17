---
name: write-adr
description: How to write an Architecture Decision Record for tapesift. Use after a T2/T3 decision card is answered.
---
# Write an ADR

1. Next number: `ls docs/adr | sort | tail -1`, add one, four digits.
2. Copy `docs/adr/0000-template.md` to `docs/adr/drafts/NNNN-<slug>.md` (agents) — the owner moves it to `docs/adr/` when accepting.
3. Title is the decision as a sentence: "0009. Use LanceDB as the embedded vector store".
4. Context has numbers. Options include the losing ones and the strongest argument for each. T3 ADRs record the council's dissent.
5. "Revisit if" names an observation, not a feeling.
6. Add one row to the Decision log in `docs/spec.md` (newest first).
