# P1-I1-T01 — The acme standards fixture

Status: ready
Tier: haiku
Labels: schema (data only; the approver below), tests
Depends on: P1-I1-S3 (the standards document model, `tl_mod_engineering.document`, on `p1/i1`); no other ticket
Branch: `p1/i1-t01-standards-fixture`
Approver (schema tickets only): the orchestrator, under the delegation of ADR-0008 decision 6 (class: additive, a new fixture)

## Goal
The company standards of the sample company Acme, first edition, as one YAML file the registry loader will read in the next
round: the code lists (disciplines, areas, document types, NDE methods, weld types, crafts, units of measure, and two lists that
mirror the pset package), the mnemonics (tag prefixes), the tag-number pattern, and the tag classes. You write
`schema/fixtures/standards/co.acme.standards@1.0.0.yaml`. A provided test (`9` test functions, 17 cases) parses it with the
real model and checks that it holds what the demos and the next tickets need. You write data, no code.

## Brief references (pasted)
> **Brief 6.4 Standards registry (company "holding zone").** Engineered standards used everywhere, versioned and governed:
> - Mnemonics and abbreviations (e.g. tag prefixes `FV`, `PT`, `HS`) with meanings
> - Tag/document/line numbering conventions as parseable patterns (regex + segment definitions), used for validation and auto-parsing
> - Code lists: disciplines, areas, document types, status codes, NDE methods, weld types, gasket types, piping classes, test media, punch categories, crafts
> - Units of measure and conversions
> - Each entry has an owner, effective dates, supersession links, and project adoption status
> - Code lists follow the same `value_list_policy` and crosswalk rules as pset value lists (6.3), so a project's local values always map to company values for reporting
>
> **Brief 6.3 `value_list_policy`.** `closed` (company values only), `extensible` (projects may add values, which must crosswalk to a company value or `other`), or `project_defined` (projects own the list entirely; an optional crosswalk keeps cross-project reports working).
>
> **Brief 9 M2 Engineering Data.** `TagClass`: class definition, required psets, applicable ITR templates. Tag class determines mandatory psets (e.g. control valve: size, rating, body material, actuator type, fail action).
>
> **Brief 27.6 Definition.** Description mandatory; units declare a UCUM code.

## Specification
The file is one YAML mapping in the form below (the models are under *Interfaces*; unknown keys are errors).
Values are listed in the order they should appear; the loader numbers them in file order. Write meaningful labels and
one-sentence definitions in plain English: an engineer reads them. `meaning` IRIs are optional; leave them out.

| Top-level key | Content |
|---|---|
| `standards` | `co.acme.standards` |
| `version` | `1.0.0` |
| `title` | `Acme company standards` |
| `description` | one sentence |
| `owner` | `role:standards-steward` |
| `effective_from` | `2026-01-01` |
| `code_lists` | the nine lists below |
| `mnemonics` | at least the 22 below |
| `numbering_patterns` | one: `tag` |
| `tag_classes` | the ten below |

**Code lists** (policy; minimum values; codes that must be there; add more if you like):
| List | `value_list_policy` | Values |
|---|---|---|
| `Discipline` | closed | at least 8: PIP Piping, MEC Mechanical, ELE Electrical, INS Instrumentation, CIV Civil, STR Structural, PRO Process, HSE Health safety and environment |
| `Area` | extensible | at least 6: 10, 20, 30, 40, 47, 50 (label each like "Unit 47, Hydrotreater") |
| `DocumentType` | extensible | at least 12: ISO isometric, PID piping and instrument diagram, GA general arrangement, DS datasheet, LD loop diagram, SPC specification, PRC procedure, CAL calculation, MTO material take-off, and three more of your choice |
| `NdeMethod` | closed | at least 6: RT, UT, MT, PT, VT, PAUT |
| `WeldType` | closed | at least 4: BW butt weld, SW socket weld, FW fillet weld, and one more |
| `Craft` | project_defined | at least 6: PF pipefitter, WLD welder, ELC electrician, INT instrument technician, SCF scaffolder, RIG rigger |
| `UnitOfMeasure` | closed | at least 10, each with `attributes: {ucum: ..., dimension: ...}`: mm, in, m, bar, psi, degC, degF, kg, lb, m3. UCUM codes: mm `mm`, in `[in_i]`, m `m`, bar `bar`, psi `[psi]`, degC `Cel`, degF `[degF]`, kg `kg`, lb `[lb_av]`, m3 `m3`. Dimensions: length, pressure, temperature, mass, volume |
| `MaterialCode` | extensible | exactly, in this order: CS Carbon steel, SS304 304 stainless steel, SS316L 316L stainless steel, DUPLEX Duplex stainless steel, other Other (see description). Mirrors `schema/fixtures/co.acme.engineering@3.2.0.yaml` |
| `FailAction` | closed | exactly, in this order: FC Fail closed, FO Fail open, FL Fail last position. Mirrors the same package |

**Mnemonics** (`code`, `label`, and `class_hint` where the table gives a class): FV flow control valve, PV pressure control valve, LV level control valve, TV temperature control valve, XV on-off valve (these five: `class_hint: ControlValve`); HV hand valve (`ManualValve`); PSV pressure safety valve (`SafetyValve`); FT flow transmitter, PT pressure transmitter, LT level transmitter, TT temperature transmitter (`Transmitter`); FIC flow indicating controller, PIC pressure indicating controller, LIC level indicating controller, TIC temperature indicating controller (`Controller`); P pump (`Pump`); E heat exchanger (`HeatExchanger`); V vessel (`Vessel`); K compressor (`Compressor`); M motor (`Motor`); HS hand switch and TW thermowell (no class, no `class_hint`).

**The pattern** (exactly this; the test checks every field):
```yaml
numbering_patterns:
  - code: tag
    label: Tag number
    definition: Area, mnemonic and a four-digit sequence, separated by hyphens, for example 47-FV-1001.
    record_type: engineering.Tag
    template: "{area}-{mnemonic}-{seq:4}"
    segments:
      area: {role: area, list: Area}
      mnemonic: {role: mnemonic, registry: mnemonic}
      seq: {role: sequence}
```
(`allocate` stays at its default, false.)

**Tag classes** (`code`, `family`, `required_psets`, `mnemonics`; give each a `label` and a one-sentence `definition`):
| Code | Family | `required_psets` | `mnemonics` |
|---|---|---|---|
| ControlValve | valve | [valve_data] | FV, PV, LV, TV, XV |
| ManualValve | valve | [valve_data] | HV |
| SafetyValve | valve | [valve_data, safety_data] | PSV |
| Transmitter | instrument | [] | FT, PT, LT, TT |
| Controller | instrument | [] | FIC, PIC, LIC, TIC |
| Pump | pump | [] | P |
| Vessel | equipment | [] | V |
| HeatExchanger | equipment | [] | E |
| Compressor | equipment | [] | K |
| Motor | equipment | [] | M |

A tag class may add `itr_templates: [ITR-VALVE-01]` style references (any string); they are references only.

## Interfaces (verbatim from the repo at the branch point)
`packages/tl-modules/engineering/src/tl_mod_engineering/document.py` (the models the file must satisfy; `StandardsDoc.problems()` also
rejects duplicate codes, a mnemonic whose `class_hint` is not a class of the document, a class that lists an undefined mnemonic,
and a pattern segment that names a missing list):
```python
class ValueDef(_Strict):
    code: str
    label: str = Field(min_length=1)
    meaning: str | None = None  # IRI of the value's meaning (brief 27.6)
    effective_from: str | None = None
    effective_to: str | None = None
    attributes: dict[str, Any] = {}

    @field_validator("code")
    @classmethod
    def _code(cls, value: str) -> str:
        if VALUE_CODE.fullmatch(value) is None:
            raise ValueError(f"value code {value!r} may hold letters, digits and ._- only")
        return value

    @field_validator("effective_from", "effective_to")
    @classmethod
    def _dates(cls, value: str | None) -> str | None:
        return _date(value)


class CodeListDef(_Strict):
    label: str = Field(min_length=1)
    definition: str = Field(min_length=1)  # brief 27.6: a definition is mandatory
    value_list_policy: ValueListPolicy = "closed"
    adoption: Adoption = "default"
    owner: str | None = None  # default: the document's owner
    values: list[ValueDef] = Field(min_length=1)


class MnemonicDef(_Strict):
    code: str
    label: str = Field(min_length=1)  # what the prefix means
    definition: str | None = None
    class_hint: str | None = None  # the tag class a tag with this prefix normally has
    discipline: str | None = None  # a value of the Discipline list, when there is one

    @field_validator("code")
    @classmethod
    def _code(cls, value: str) -> str:
        if MNEMONIC_CODE.fullmatch(value) is None:
            raise ValueError(f"mnemonic {value!r} must be upper-case letters and digits")
        return value


class SegmentDef(_Strict):
    """What one segment of a numbering pattern is and where its values come from."""

    role: SegmentRole
    list: str | None = None  # the value must be a code of this code list
    registry: Literal["mnemonic"] | None = None  # the value must be a registered mnemonic


class PatternDef(_Strict):
    code: str
    label: str = Field(min_length=1)
    definition: str = Field(min_length=1)
    record_type: str
    template: str  # ``{area}-{mnemonic}-{seq:4}``; see tl_core.numbering.pattern
    segments: dict[str, SegmentDef]  # by name: each field of the template, and ``seq``
    allocate: bool = False  # True: the numbering service hands out the sequence
    gap_free: bool = True
    scope: str = "project:*"
    reserved: list[tuple[int, int]] = []

    @field_validator("code")
    @classmethod
    def _code(cls, value: str) -> str:
        if ENTRY_CODE.fullmatch(value) is None:
            raise ValueError(f"pattern code {value!r} may hold letters, digits and _ only")
        return value

    @field_validator("record_type")
    @classmethod
    def _record_type(cls, value: str) -> str:
        if RECORD_TYPE.fullmatch(value) is None:
            raise ValueError(f"record type {value!r} must look like 'engineering.Tag'")
        return value


class TagClassDef(_Strict):
    code: str
    label: str = Field(min_length=1)
    definition: str = Field(min_length=1)
    family: TagFamily
    required_psets: list[str] = []
    itr_templates: list[str] = []
    mnemonics: list[str] = []

    @field_validator("code")
    @classmethod
    def _code(cls, value: str) -> str:
        if ENTRY_CODE.fullmatch(value) is None:
            raise ValueError(f"class code {value!r} may hold letters, digits and _ only")
        return value

    @field_validator("required_psets")
    @classmethod
    def _psets(cls, value: list[str]) -> list[str]:
        for name in value:
            if PSET_NAME.fullmatch(name) is None:
                raise ValueError(f"pset name {name!r} must be lower snake case")
        return value


class StandardsDoc(_Strict):
    standards: str  # the name of the standards, ``co.acme.standards``
    version: str
    title: str | None = None
    description: str = Field(min_length=1)
    owner: str = Field(min_length=1)  # a role or actor that stewards the standards
    effective_from: str | None = None
    code_lists: dict[str, CodeListDef] = {}
    mnemonics: list[MnemonicDef] = []
    numbering_patterns: list[PatternDef] = []
    tag_classes: list[TagClassDef] = []

    @field_validator("standards")
    @classmethod
    def _name(cls, value: str) -> str:
        if NAME_PATTERN.fullmatch(value) is None:
            raise ValueError(
                f"name {value!r} must be lower-case dotted words, like co.acme.standards"
            )
        return value

    @field_validator("version")
    @classmethod
    def _version(cls, value: str) -> str:
        if VERSION_PATTERN.fullmatch(value) is None:
            raise ValueError(f"version must be MAJOR.MINOR.PATCH, got {value!r}")
        return value

    @field_validator("effective_from")
    @classmethod
    def _start(cls, value: str | None) -> str | None:
        return _date(value)

    @field_validator("code_lists")
    @classmethod
    def _list_names(cls, value: dict[str, CodeListDef]) -> dict[str, CodeListDef]:
        for name in value:
            if LIST_CODE.fullmatch(name) is None:
                raise ValueError(f"code list name {name!r} must be UpperCamelCase")
        return value
```

## Context (read these, nothing else)
- `packages/tl-modules/engineering/src/tl_mod_engineering/document.py` (the whole model, if the excerpt above is not enough)
- `schema/fixtures/co.acme.engineering@3.2.0.yaml` (only its `code_lists`, to copy the two mirrored lists)
- `docs/tickets/P1-I1/provided/t01-test_standards_fixture.py.txt` (the test)
may explore: (none)

Learnings that apply (pasted from `docs/memory/LEARNINGS.md` and the build's conventions):
- Environment: run everything from the repository root. A new worktree needs `uv sync --all-packages` once before `uv run` can import the workspace packages (L-P0-I6A-1). `uv` prints "UV_NATIVE_TLS is deprecated"; ignore it. Do not pipe `just check` into `tail`.
- pyright is `standard` for `packages/tl-modules`; ruff limits lines to 100 columns, docstrings and comments included (L-P0-I1-6). Run `uv run ruff format` before committing.
- Provided files live under `docs/tickets/P1-I1/provided/` as `.py.txt`; copy them into the tree byte for byte (the target names are in *Steps*). Do not edit the copies: they are already `ruff format` and pyright clean.
- Commit your report at `docs/reports/P1-I1/<ticket-id>.md` (it is inside your Allowed paths). Say "commit your report" in your final message (L-P0-I2-B7).
- A failing test that is not in your Allowed paths is not yours to fix: report it under *Blocked*.
- No new dependencies. Remove the `STUB` paragraph from the module docstring, every `STEPS` comment and the `# ruff: noqa: F401` line when you implement a stub.
- The test counts below were counted from the provided files (`grep -c "^def test_"`); parametrized tests expand to more cases when run, and the pytest summary is the number of cases (L-P0-I8A-8).
- Never name a module `types.py`, `enum.py` or `json.py` inside a package (L-P0-I5-B1).
- Never write a hand-made `cur_*` table or change `schema/**` or anything under `generated/` unless this ticket says so.
- YAML: quote any string that contains `: ` or starts with `{`, `[` or `*` (the template above is quoted for that reason). Flow style (`- {code: PIP, label: Piping}`) keeps the file short. `uv run python -c "from tl_mod_engineering.document import load_standards_file; ..."` checks the file as you go.
- The directory `schema/fixtures/standards/` is new. The package registry reads `schema/fixtures/*.yaml` at the top level only, so this file is not a package and does not change any effective schema or hash.

## Allowed paths
- `schema/fixtures/standards/co.acme.standards@1.0.0.yaml` (create)
- `packages/tl-modules/engineering/tests/test_standards_fixture.py` (create; byte-identical copy of the provided test)
- `docs/reports/P1-I1/P1-I1-T01.md` (create)

## Steps
1. `uv sync --all-packages`.
2. Copy `docs/tickets/P1-I1/provided/t01-test_standards_fixture.py.txt` to `packages/tl-modules/engineering/tests/test_standards_fixture.py`.
3. Write the fixture file.
4. Run the acceptance commands.

## Acceptance
```
just check
uv run pytest packages/tl-modules/engineering/tests/test_standards_fixture.py -q
uv run pytest packages/tl-modules -q
```
Expected: `just check` clean (it runs ruff, pyright and the codegen drift check; a YAML file changes none of them); the fixture test passes (17 passed); the whole module package passes.

## Tests to add
None beyond the provided file.

## Report requirements
Standard report (`docs/templates/haiku-report.md`) plus: the number of values in each list and the number of mnemonics, as a small table.

## Escalation triggers
- Stop and report *Blocked* if the provided test and the table in this ticket disagree, or if the model rejects something this ticket asks for.
- Stop if you think a code, list or class is wrong for a real company: the table is the specification; say so under *Open questions*.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
