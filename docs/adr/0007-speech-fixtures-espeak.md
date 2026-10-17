# 0007. Synthesize the English speech fixture with espeak-ng

Date: 2026-10-16   Status: accepted   Tier: T2

## Context
The E3 transcription check needs one short English clip with a known transcript. FFmpeg test sources only make tones and noise, and the agent rules say fixtures come from FFmpeg test sources only, so this is an exception that needs a decision. (The first draft also covered a Telugu-English clip; ADR 0010 made v1.0 English only, so that clip was dropped.)

## Options
A. espeak-ng (GPL-3.0 tool; its audio output is not covered by the GPL). Runs on macOS and Linux. Pros: license-free output, regenerable by a script. Cons: robotic voice, so WER on it says little about real speech.
B. macOS `say`. Pros: natural voice. Cons: mac only; Apple's terms on generated audio are unclear.
C. Record 20 seconds yourself. Pros: real voice. Cons: not regenerable; a personal voice in git history.

## Decision
A. The fixture only proves the pipeline runs end to end; real accuracy comes from the English eval suites in the cloud (docs/spec.md, Evals).

## Consequences
espeak-ng is needed only to regenerate fixtures, never at runtime. Listed in THIRD_PARTY.md under build-only tools.

## Revisit if
A permissively licensed, natural-sounding English TTS can be scripted the same way.
