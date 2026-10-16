# Security policy

## Reporting a vulnerability

Email jy4857@nyu.edu with "tapesift security" in the subject, or open a [private security advisory](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing-information-about-vulnerabilities/privately-reporting-a-security-vulnerability) on the repository. Please do not open a public issue.

You will get a reply within 7 days.

## Scope

- Code execution or file access triggered by a crafted media file.
- Prompt injection carried by on-screen text or speech that escapes the `untrusted_media` tagging.
- Network calls other than model downloads.
- Supply chain: unpinned weights, `trust_remote_code`, non-safetensors loading.

## What we do by default

- Model weights pinned by revision, safetensors only, `trust_remote_code` off.
- `uv.lock` committed.
- Releases published from CI through PyPI trusted publishing; no maintainer holds publish tokens.
