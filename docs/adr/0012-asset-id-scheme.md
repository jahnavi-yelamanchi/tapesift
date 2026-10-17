# 0012. Asset IDs use a versioned head/tail hash by default and a full sha256 on request

Date: 2026-10-17   Status: accepted 2026-10-17 (owner's call, after two-model council with rebuttal)   Tier: T3

## Context
Asset IDs key resume state, DUPLICATE detection, `--asset`, purge, and the eval manifests. Files can be 10+ GB and often sit on network storage, where hashing the whole file on every ingest is slow. The plan's decision D6 covers the trade-off.

## Options
A. `sha256:` prefix on the head/tail hash. Pros: looks like a standard digest. Cons: it fails a `shasum -a 256` check, so users read it as corruption; no versioning, so the scheme cannot change later without breaking old IDs.
B. `tsid1:` versioned prefix for the head/tail hash, and `sha256:` only for the true whole-file hash. Pros: the prefix says what was hashed; the version can change later. Cons: two ID forms to explain.
C. Full hash always. Pros: one simple scheme. Cons: slow on big archives over network storage.

## Decision
B. The default ID is `tsid1:` followed by sha256(8-byte big-endian size || first 8 MiB || last 8 MiB), where the last chunk starts at max(8 MiB, size - 8 MiB). `tsid1` versions the scheme, including the 8 MiB chunk size. Full mode gives `sha256:` plus the plain sha256 of the file, which `shasum -a 256` can verify. Indexes never mix modes. E7 confirms any DUPLICATE with a full hash before emitting it.

Council record: Sonnet first recommended A. It changed to B in the rebuttal round after Opus argued that a partial hash under `sha256:` looks like corruption to users and cannot be versioned later.

## Consequences
Ingest reads at most 16 MiB per file in the default mode, so it stays fast on network storage. The realistic collision case is equal-size headerless captures (PCM WAV, MPEG-TS) with identical heads and tails. E7's full-hash confirmation neutralizes it, so a collision cannot produce a false DUPLICATE. Changing the chunk size later means a new prefix, `tsid2`. Old IDs keep working, and mixed-mode indexes stay out of scope.

## Revisit if
A NAS benchmark shows the two 8 MiB reads are slow, or the plan changes the hash.
