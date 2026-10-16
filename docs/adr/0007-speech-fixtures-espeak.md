# 0007. Synthesize speech fixtures with espeak-ng

Date: 2026-10-16   Status: proposed (needs your approval at gate 2)   Tier: T2

## Context
Three fixtures need real speech: the plain speech clip (E3 WER check), the code-switched clip (`MIXED_LANG`), and speech under music. FFmpeg test sources only make tones and noise. The agent rules say fixtures come from FFmpeg test sources only, so this is an exception that needs a decision.

## Options
A. espeak-ng (GPL-3.0 tool; its audio output is not covered by the GPL). Voices for English, Hindi and Telugu. Runs on macOS (`brew install espeak-ng`) and Linux (`apt install espeak-ng`). Pros: license-free output, reproducible, covers Telugu. Cons: robotic voice, so WER on it says little about real speech.
B. macOS `say`. Pros: natural voices. Cons: mac only, no Telugu voice, Apple's terms on generated audio are unclear.
C. Record 20 seconds yourself with consent. Pros: real accent and code-switching. Cons: not regenerable by a script; personal voice in a public repo.

## Decision
A for fixtures. C stays the plan for the code-switched eval suite, which lives in the cloud and is not committed.

## Consequences
espeak-ng is needed only to regenerate fixtures, never at runtime. It is listed in THIRD_PARTY.md under build-only tools.

## Revisit if
An open TTS model with a permissive license gives natural Telugu-English speech that a script can regenerate.
