# P1-UX-T00 — Shared display helper (plain language, technical toggle, leak finder)

Status: ready
Tier: haiku
Kind: ticket
Review: full
Labels: tui, tests
Depends on: —
Branch: `p1/ux-t00-display-helper`

(Was piece S1 until plan check F10: the module is pure functions with a pinned spec, so a Haiku ticket with a full reviewer.)

## Goal
One module, `packages/tl-tui/src/tl_tui/display.py`, that every screen uses to turn stored values into plain
words, plus the state of the technical-details toggle and a function that finds technical text in rendered
output. After this piece no screen has its own label table. Nothing is wired into a screen yet.

## Brief references (pasted)
> SCOPE clause 2: type labels, not class names (`Control valve`, not `ControlValve` or `engineering.Tag`); code-list
> names, not codes (`Piping`, not `PIP`); domain labels (`Letter`, not `general/letter`); property labels (`Body
> material`); set labels (`Valve data`). Hidden by default: record and event ids (ULIDs), hashes and digests,
> schema package names and versions, effective-schema hashes, internal keys, rule markers like
> `required@Design/Inst` (say "required at Design"), clock ids, calendar ids and versions, `svc:...` actor ids (show
> the service's label), stream ids. Duplicated columns go.
> SCOPE clause 3: one key toggles technical details; off by default; per viewer; not remembered; admins only; a
> plain user gets a one-line refusal.

## Interfaces
```python
# tl_tui/display.py (new). Pure; no client, no Textual import except for mode_of.
@dataclass(frozen=True)
class Labels:
    type_titles: Mapping[str, str] = {}            # "engineering.Tag" -> "Tag"
    code_labels: Mapping[str, Mapping[str, str]] = {}   # list name -> code -> label
    domains: Mapping[str, str] = {}                # domain code -> name
    subtypes: Mapping[tuple[str, str], str] = {}   # (domain, subtype) -> label
    services: Mapping[str, str] = {}               # "svc:intake" -> "Email intake"

def humanize(name: str) -> str                     # "ControlValve" -> "Control valve"; "engineering.Tag" -> "Tag"
def type_label(labels: Labels, record_type: str) -> str          # title, else humanize
def code_label(labels: Labels, list_name: str, code: str | None) -> str   # label, else the code, "—" for None
def domain_label(labels: Labels, domain: str | None, subtype: str | None = None) -> str   # "Letter"
def actor_label(labels: Labels, actor: str) -> str               # service label; "user:amy" -> "amy"; unknown svc: -> "a service"
def rule_phrase(field: FieldMeta) -> str                         # "required at Design or Installed", "advisory", "locked"
def pset_label(group: PsetGroupMeta) -> str                      # the label, never name@version
def quantity(value: Any, unit: str | None) -> str                # "2.5 in"; uses text.format_value, unit_label

class DisplayMode:                                              # per app, in memory
    technical: bool = False
    def toggle(self, *, is_admin: bool) -> str                  # "" when switched; else the one-line refusal
        # refusal text, exactly: "Technical details are for admins"
def mode_of(widget_or_app: object) -> DisplayMode               # app.display if present, else a plain-mode default

def find_technical(text: str, labels: Labels | None = None) -> list[str]   # every token a plain user must not see
```
`find_technical` matches: a 26-character Crockford ULID (`[0-9A-HJKMNP-TV-Z]{26}`); a 64-hex digest; the short
hash form `#abcd…ef`; a package reference `name@x.y.z`; `svc:` followed by a word; `required@`; `sha256:`; a
calendar id or version token as the clock text writes it (`cal:`, `calendar C-...`, `@v3`); and a `domain/subtype`
key only when `labels` is given and `domain` is a key of `labels.domains` (with no labels no `a/b` text matches).
Each pattern is a named constant with one test; the list is the contract the walking test (T11) greps with.

Existing helpers stay where they are: `tl_tui/text.py` (`unit_label`, `format_value`, `short_hash`, `timestamp`)
and `FieldMeta`, `PsetGroupMeta` from `tl_schema.forms`. `display.py` imports them; it does not copy them.
Extend `UNIT_LABELS` in `text.py` only if a test needs a unit (currency codes `USD`, `EUR`, `d` for days).

## Context (read these, nothing else)
- `packages/tl-tui/src/tl_tui/text.py`
- `packages/tl-tui/src/tl_tui/widgets/psets_tab.py` (`rule_text`, `value_text`: what `rule_phrase` replaces)
- `packages/tl-tui/src/tl_tui/correspondence_text.py` (`clock_line`, `suggestion_text`: examples of leaks)
- `packages/tl-tui/src/tl_tui/tag_text.py`
- `packages/tl-schema/src/tl_schema/forms.py` (`FieldMeta`, `PsetGroupMeta`)
- `packages/tl-tui/tests/test_psets_tab.py` (style of the existing tests)

## Allowed paths
- `packages/tl-tui/src/tl_tui/display.py` (create)
- `packages/tl-tui/src/tl_tui/text.py` (units only)
- `packages/tl-tui/tests/test_display.py` (create)
- `docs/reports/P1-UX/T00.md` (create)

## Tests to add (`packages/tl-tui/tests/test_display.py`)
- `test_humanize_splits_camel_case_and_drops_the_module_prefix`
- `test_type_label_prefers_the_title_and_falls_back_to_humanize`
- `test_code_label_returns_the_label_then_the_code_then_a_dash`
- `test_domain_label_names_the_subtype_without_the_internal_key`
- `test_actor_label_shows_a_service_by_label_and_never_its_id`
- `test_rule_phrase_says_required_at_states_in_words` (`required` + `[Design, Installed]` -> no `@`, no `/`)
- `test_pset_label_has_no_package_or_version`
- `test_quantity_joins_value_and_unit`
- `test_toggle_switches_for_an_admin_and_refuses_a_plain_user_with_the_exact_line`
- `test_toggle_twice_returns_to_plain`
- `test_mode_of_defaults_to_plain_without_an_app`
- `test_find_technical_matches_each_pattern` (one parametrised case per pattern; a ULID built with
  `tl_core` ids, a real `short_hash`, `co.acme.engineering@3.2.0`, `svc:intake`, `required@Design/Inst`)
- `test_find_technical_matches_a_domain_key_only_when_the_labels_know_the_domain` (`general/letter` with
  `Labels(domains={"general": "General"})` matches; without labels, or with `m/s`, does not)
- `test_find_technical_ignores_plain_sentences` (titles with `@` in an email address, a part number of 26
  letters that is not Crockford, `Letter`, `Control valve`, and the units/dates `m/s`, `kg/m3`, `N/A`, `2026/10/21`)

## Acceptance
```
just check
uv run pytest packages/tl-tui/tests/test_display.py -q
just gate packages/tl-tui/tests/test_display.py packages/tl-tui/tests/test_psets_tab.py packages/tl-tui/tests/test_text.py
```
Expected: pass; `just check` clean.

## Mutants (run by the implementer in its worktree, one line each in the report: killed or survived)
Sentinel: flip `DisplayMode.technical` default to `True`. Targeted: (1) the admin test in `toggle` inverted;
(2) the ULID pattern loosened to any 26 characters; (3) `actor_label` returning the raw `svc:` id;
(4) `rule_phrase` keeping `@`. Each must fail a test; revert each before committing.

## Report requirements
Standard report (`docs/templates/haiku-report.md`). List each `find_technical` pattern with its test name. Say which existing `text.py` helper each
function reuses.

## Escalation triggers
- Stop and report *Blocked* if a stored value needs a label that no existing client method can supply (that is S2's
  `load_labels`; do not add a client method here).
- Stop if a pattern would hide plain text in the existing snapshots (the leak finder only reports; it never edits).

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
