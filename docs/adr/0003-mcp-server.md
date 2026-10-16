# 0003. Add `tapesift mcp` in v0.3 so agents can search local footage

Date: 2026-10-13   Status: accepted   Tier: T3

## Context
Agents are a growing consumer of search. An MCP server with search, show and clip tools lets Claude or any agent search someone's local footage without a hosted service.

## Options
1. Ship `tapesift mcp` in v0.3. Pros: cheap on top of the store; a distinctive demo; pairs with the untrusted-media safety work. Cons: one more interface to keep stable.
2. HTTP API only. Cons: every agent user writes glue code.

## Decision
Option 1. Every result carries the untrusted-media tag.

## Consequences
Search results become a prompt-injection surface, which the Y1 benchmark measures.

## Revisit if
Nobody uses it by v1.0.
