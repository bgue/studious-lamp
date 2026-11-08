# <package name> (`<import_name>`)

<One sentence: what this package is for and which brief sections it implements (§…).>

## Public interface
| Symbol | Kind | Purpose |
|---|---|---|

## Depends on / used by
- Depends on: …
- Used by: …

## Commands
```
just test -- packages/<pkg>
```

## Configuration
| Setting or env var | Default | Notes |
|---|---|---|

## Rules specific to this package
See `AGENTS.md` in this directory.

## Module standard
- Every event payload class names its world-date field with `tl:valid_time` (`at` for a moment, `from`/`to` for a span), or the class is listed with a reason in `tests/tools/valid_time_baseline.toml`; deadlines, forecasts and expiry dates are never tagged.

## Status
Introduced in <increment>. Last interface change: <increment> (<ADR if any>).
