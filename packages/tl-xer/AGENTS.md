# AGENTS.md — tl-xer

Read the root `AGENTS.md` first. These rules add to it. This package parses files from outside; every rule here is a security rule.

- **Bound everything, refuse never cut.** A new dimension (a count, a length, a nesting depth, a total) gets a constant in `limits.py` and a test that fails when the check is removed. Crafted inputs in tests stay small: lower the limit with `monkeypatch`, do not build a 50 MiB file (the large cases live in `test_largest.py`, marked `slow`).
- **Pure and deterministic.** No clock, no randomness, no environment, no file access, no `pickle`, `eval` or `marshal`. The same bytes give the same result byte for byte, including the gzip of the bundle (no time stamp).
- **Fixed messages.** An exception or a problem never carries a cell, a path or the text of another exception. Values allowed in a message: table and column names that passed the name pattern, activity ids that passed the id check, counts.
- **ASCII digits only.** Dates and numbers are matched with `[0-9]`, never `\d` or `str.isdigit()` alone (other scripts' digits are digits to Python).
- **Forbidden characters refuse the file** (`reader.FORBIDDEN`: control characters, line and paragraph separators, text-direction marks), and the parent checks every text cell against the same pattern again in `wire.py`; keep the two on one pattern.
- **The parent does not believe the child.** Everything the child returns is re-checked in `wire.py` (lengths, hashes, kinds of every cell, bounds); a new field of the answer needs its check there and a test that forges it.
- **Resource use is part of the interface.** A change that touches the reader, the typed step or the bundle reruns `tests/test_largest.py` and records the seconds and megabytes in ADR-0015 §2 (targets: at most 20 s and 600 MB for the worst legal file).
- Synthetic fixtures only (`synth.py`, `tests/xersupport.py`): never a real project's schedule.
- Never name a module `types.py` (L-P0-I5-B1).
