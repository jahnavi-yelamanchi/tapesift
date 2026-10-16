# 0001. Build tapesift in three phases: engine, then evals and post-training, then self-training

Date: 2026-10-13   Status: accepted   Tier: T3

## Context
The project has to prove systems skill, research-engineering skill and closed-loop improvement, within about 16 weeks of part-time work, while staying useful to real users at every release.

## Options
1. Engine first (v0.1 to v0.4), then evals, post-training and safety (v0.5 to v0.7), then self-training and v1.0. Pros: every phase ships something usable; cost numbers exist before training starts. Cons: post-training starts late.
2. Post-training first on an existing pipeline. Pros: faster research story. Cons: no engine to show, no cost numbers, nothing for users.
3. All tracks in parallel. Cons: too many lanes for one reviewer.

## Decision
Option 1. Dates: engine Oct 14 to Dec 6, evals and post-training Dec 7 to Jan 3, self-training and v1.0 Jan 4 to Jan 31.

## Consequences
The launch (Dec 6) is the fixed date; v0.3 slips before the launch does. Post-training can rely on the eval harness and the demo corpus.

## Revisit if
Buyer conversations by Dec 15 show no demand and job outreach gets no replies.
