# Query language reference

Use this page to write a filter for the TUI filter bar, an API request, or an MCP search. Every
example below parses as written. Each error example shows where the parser stops, so a filter bar
can point at the character that caused it.

## Shape of a query

A term has the form `field<operator>value`, for example `status:open`. Terms separated by spaces
are ANDed. Blank text means no filter.

```query
status:open
status:open voided:false
id:abc123
```

Field names are not case-sensitive. An unknown field is an error. To search for text that looks
like a field, quote it.

## Fields

| Field | Type | Meaning |
|---|---|---|
| `id` | text | Record id. |
| `key` | text | Human-readable number, unique within a scope. |
| `type` | text | Record type, such as `piping.Weld`. |
| `scope` | text | `company` or `project:<id>`. |
| `title` | text | Record title. |
| `description` | text | Record description. |
| `status` | text | Workflow state. Empty when the type has no workflow. |
| `voided` | true or false | Voided records are left out unless the caller asks for them. |
| `version` | whole number | Stream version. |
| `last_seq` | whole number | Ledger sequence of the last event applied. |
| `effective_schema_hash` | text | Effective schema hash. |
| `conformance` | text | One of `ok`, `warning`, `nonconformant`, `waived`. |
| `created_at` | date | When the record was created. |
| `updated_at` | date | When the record was last updated. |

```query
type:piping.Weld
scope:project:P123
title:"pipe spool"
status:null
version>=3
last_seq<10
conformance:warning
```

Pset values use three forms: `psets.<pset>.<property>`, `psets.<pset>.x.<property>` for a custom
section, and `psets.prj.<pset>.<property>` for a project pset.

```query
psets.nde.method=RT
psets.nde.x.method=RT
psets.prj.nde.method=RT
```

## Operators

| Operator | Meaning |
|---|---|
| `:` | Equals, the same as `=`. |
| `=` | Equals. Text is compared exactly, including case. |
| `!=` | Not equal. Also matches records with no value. |
| `~` | Contains, ignoring case. Text only. |
| `<` | Less than. |
| `<=` | Less than or equal. |
| `>` | Greater than. |
| `>=` | Greater than or equal. |

On pset values, `~` matches only values stored as text. A number or a boolean never matches `~`: use
`=`, `<` or `>` for those.

```query
key:007
status=open
status!=open
description~weld
voided=false
version<=5
```

## Values

A bare word has no spaces, parentheses or quotes. A quoted string uses `"` or `'`. Inside a quoted
string, `\"` and `\\` are escapes.

Text fields always read the value as text. `key:007` finds the key `007`.

Whole-number and true or false fields check the value. `version:3` and `voided:true` are valid.

An unquoted `null` means no value. A quoted `"null"` is the text `null`.

```query
key:007
title:"pipe spool"
title:"it's"
status:null
status!=null
```

Pset values are typed from their text. `3` is a number, `1.5` is a decimal, `true` is a boolean and
`+7d` is a relative date. Anything else is text, so `007` stays text. Quote a value to force text.

```query
psets.nde.thickness>1.5
psets.nde.passed:true
psets.nde.lot:007
psets.a.b:"12"
psets.nde.method:null
```

## Boolean logic

A space or `AND` means both terms must match. `OR` means either term may match. `-term` and
`NOT term` negate a term. `NOT` binds tightest, then `AND`, then `OR`. Parentheses group terms.

`or`, `and` and `not` work in any case. Quote a word to search for it.

```query
status:open voided:false
status:open AND voided:false
status:open OR status:closed
-status:open
NOT status:open
(status:open OR status:closed) scope:project:P123
weld OR joint status:open
"and" "not"
```

## Text search

A word with no field searches `key`, `title` and `description`, ignoring case. Several words must
all match. A quoted phrase matches as written. `%` and `_` are ordinary characters.

```query
weld
weld joint
"pipe spool"
50%
pipe_spool
```

## Links

A link is live while its status is `active`, `stale` or `broken`. Suggested and retracted links do
not count. Both directions count.

| Term | Matches |
|---|---|
| `linked` | Any record with a live link. |
| `linked:NCR` | A live link to a record of type `NCR`. `quality.NCR` also works, and the type ignores case. |
| `linked(raised_against)` | A live link with that relation. `*` means any relation. |
| `linked(raised_against):NCR` | A live link with that relation to a record of that type. |
| `linked:NCR.status:open` | A live link to an `NCR` whose linked record also matches the condition after the dot. |
| `linked(raised_against).(status:open type:NCR)` | A live link with that relation to a record matching every condition in the group. |
| `count(linked:NCR)>0` | The number of matching live links, compared with `=`, `!=`, `<`, `<=`, `>` or `>=`. |
| `missing(link:permit)` | No live link to a `permit`. |
| `missing(link)` | No links at all. |

```query
linked
linked:NCR
linked:quality.NCR
linked(raised_against)
linked(*)
linked(raised_against):NCR
linked:NCR.status:open
linked(raised_against).(status:open type:NCR)
count(linked:NCR)>0
count(linked:NCR)>=2
count(linked(raised_against):NCR)=0
missing(link:permit)
missing(link)
-linked:permit
```

`path(a>b>c)` is not supported yet. The parser rejects it.

## Dates

The forms below apply to `created_at` and `updated_at`. Pset properties that hold ISO dates take the
same forms.

| Value | Meaning |
|---|---|
| `2026-10-09` | That day in the project time zone. |
| `2026-10-09T12:30:00Z` | That instant. Offsets such as `+02:00` work. No offset means UTC. |
| `today` | The current day. |
| `+7d`, `-3d` | Whole days ahead or back. |

A day is a window. Each operator compares against the whole day as follows.

| Operator | Matches, for the day 2026-10-09 |
|---|---|
| `=` | Any time inside the day. |
| `<` | Any time before the day starts. |
| `<=` | Any time up to the end of the day. |
| `>` | Any time after the day ends. |
| `>=` | Any time from the start of the day. |

The project time zone defaults to UTC.

```query
created_at>=2026-10-09
created_at<2026-10-10
created_at>2026-10-09T12:30:00Z
updated_at>2026-10-09T12:30:00+02:00
created_at=today
updated_at>=-3d
created_at<+7d
psets.nde.due<+7d
```

## Errors

A text that does not parse raises `QuerySyntaxError`. Its `position` is the 0-based offset of the
first offending character. Each line below is a query, two spaces, `# position`, and the offset
the parser reports.

```query-error
status:  # position 7
(status:open  # position 12
status:open)  # position 11
foo:bar  # position 0
version:abc  # position 8
created_at>soon  # position 11
created_at:2026-13-45  # position 11
a OR  # position 4
path(a>b)  # position 0
count(linked:NCR)  # position 17
title:"unterminated  # position 6
key:  # position 4
```

## Limits

A query may have at most 2000 characters, at most 200 terms and nesting at most 32 levels deep.
A query over a limit raises `QuerySyntaxError`.
