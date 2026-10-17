---
name: Bug
about: Something broke on a file, a machine or a command.
labels: ["bug"]
---
## What happened
Command, exit code, and the shortest decisive error line.

## Expected

## Environment
Paste `tapesift doctor --json`.

## The file
Codec, container, duration, and whether you can share it. If not, `ffprobe -hide_banner -show_streams -show_format <file>` output.
