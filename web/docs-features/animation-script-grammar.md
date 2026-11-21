# Animation script: formal grammar

This page is the formal grammar of the animation script language (`web/src/anim/script/`) and of the criteria query it
embeds (`web/src/query/`). It describes what the parser **accepts**. Where the compiler adds checks on top of the syntax
(unknown names, out-of-range numbers), they are listed in the limits and timing tables. The plain-language reference is
[animation-script.md](animation-script.md); a step-by-step guide with recipes is [animation-script-guide.md](animation-script-guide.md).

Notation: **W3C EBNF** (the notation of XML 1.0, section 6). `::=` defines a rule, `|` separates alternatives, `?` means
optional, `*` zero or more, `+` one or more, `( )` groups, `[a-z]` is a character class, `[^...]` is a negated class,
`#xC0` is a code point, `/* */` is a comment. A quoted lower-case term such as `"fly"` is a **keyword**: it matches a word
ignoring case. `EOL` is a line break (`\r\n`, `\r` or `\n`). `WS` is a space or a tab. Rules are written in the order of the
source: lexical rules, lines, statements, elements, values and expressions, blocks, criteria.

## 1. Lexical rules

```ebnf
(* The lexer reads one line at a time. A line is split at EOL. Tokens never span lines. *)
Script        ::= ( Statement? EOL )* Statement?                    /* blank and comment-only lines may stand anywhere */
Token         ::= String | Number | Word | Punct                    /* a statement is a sequence of tokens; WS and Comment may stand between them */

(* Strings. A double quote, or a curly quote, opens; a double quote, or a closing curly quote, closes.
   Two double quotes inside a string stand for one double quote. *)
String        ::= OpenQuote StringChar* CloseQuote
StringChar    ::= '""' | [^"“”]
OpenQuote     ::= '"' | '“' | '”' | '„'
CloseQuote    ::= '"' | '“' | '”'

(* Numbers. A number may be followed directly by the unit s or sec (any case). No other letter may follow it. *)
Number        ::= ( Digits ( "." Digits? )? | "." Digits ) GluedUnit?
Digits        ::= [0-9]+
GluedUnit     ::= "s" | "sec" | "secs" | "second" | "seconds"      /* glued to the number: "2s", "2sec", "2seconds" (any case) */

(* Words. Letters, digits and underscores; segments joined by single dots (xray names, Pset_X.Prop). *)
Word          ::= WordStart WordChar* ( "." WordChar+ )*
WordStart     ::= [A-Za-z_] | [#xC0-#xFFFF]
WordChar      ::= [A-Za-z0-9_] | [#xC0-#xFFFF]

(* Punctuation. Two-character operators are read before one-character ones. *)
Punct         ::= "==" | "!=" | "<>" | "<=" | ">=" | "=" | "<" | ">"
                | "(" | ")" | "," | "+" | "-" | "*" | "/" | "&"

(* A comment runs from its first mark to the end of the line. Outside strings only. *)
Comment       ::= ( "--" | "#" ) [^#xA#xD]*
```

Lexical notes:

- A character that is not in any rule is an error (for example `!` alone, `'`, `?`, `{`). A single quote is reported as "use double quotes".
- A line with a lexical error is dropped as a whole. The other lines still parse.
- The lexer has a limit on the whole source and on the number of lines (section 10).
- Keywords are ordinary words to the lexer. The parser decides what they mean at their place in a statement.
- Space, tab and the no-break spaces U+00A0, U+2007 and U+202F separate tokens.

## 2. Statements and lines

```ebnf
Statement     ::= Simple | Together | Repeat | ForEach

(* Block statements. The header is one line; the body is the statements up to the closing line. *)
Together      ::= "together" EOL Script "end" "together"
Repeat        ::= "repeat" Expr ( "times" | "time" ) EOL Script "end" "repeat"
ForEach       ::= "repeat" "for" "each" ( "element" | "elements" ) "in" Elements EOL Script "end" "repeat"
                | "repeat" "for" "each" "set" "in" "sets" EOL Script "end" "repeat"

(* One-line statements. *)
Simple        ::= Fly | FlyView | Orbit | SetStmt | ModeStmt | ApplyStmt
                | Visibility | SelectStmt | Caption | Label | Hover | Wait | Put

(* A closing line holds nothing after its block word. Any other "end" line is an error. *)
```

Each statement occupies one line. The header of a block statement is the whole line: nothing may follow `together`, and
nothing may follow the `in` elements of a `repeat for each` line. A line that starts with `end` must be `end together`
or `end repeat` and must close the block that is open. Nesting is at most 8 blocks deep (section 10).

## 3. Simple statements

```ebnf
(* Options. Each keyword may appear at most once in one statement, in any order. *)
OverOpt       ::= "over" Quantity
EaseOpt       ::= "ease" Ease
MarginOpt     ::= "margin" Expr
ForOpt        ::= "for" Quantity
FadingOpt     ::= "fading" "over"? Quantity

Quantity      ::= Expr Unit?                                       /* a number of seconds, or of degrees where the statement says so */
Unit          ::= "s" | "sec" | "secs" | "second" | "seconds"      /* a separate word; glued units are read by the lexer */

Ease          ::= "linear" | "inout" | "inoutsine" | "in" "out"? | "out"

Fly           ::= "fly" "to" Elements ( OverOpt | EaseOpt | MarginOpt )*
FlyView       ::= "fly" "to" "view" String ( OverOpt | EaseOpt )*
Orbit         ::= "orbit" Expr ( "degree" | "degrees" | "deg" )? ( "about" Elements )? ( OverOpt | EaseOpt )*

SetStmt       ::= "set" Word "to" Value ( OverOpt | EaseOpt )*
Value         ::= String
                | ( BoolWord | Word )                              /* only when it is alone: the line ends or an option keyword follows */
                | Expr ( "," Expr )*                               /* a number, a name, or a list of numbers */
BoolWord      ::= "true" | "on" | "yes" | "false" | "off" | "no"

ModeStmt      ::= "mode" ModeWord
ModeWord      ::= "ghost" | "solid" | "radiograph" | "glow" | "cutaway"

ApplyStmt     ::= "apply" "preset" String

Visibility    ::= ( "show" | "hide" | "isolate" ) Elements FadingOpt?

SelectStmt    ::= "select" ( "nothing" | "none" | Elements )

Caption       ::= "caption" Str Str? ForOpt?                       /* a bare word after the title is read as text, see Str */

Label         ::= "label" Elements "with" Field ( "," Field )* ForOpt?
Field         ::= Word | String                                    /* name, class, storey, material, globalid, type, or "Pset_X.Prop" */

Hover         ::= "hover" Elements ForOpt?

Wait          ::= "wait" Quantity

Put           ::= "put" Expr "into" Word                           /* the name must not be a reserved word (section 9) */
```

Notes on the simple statements:

- `set` takes a Word as the path. The path is checked against the settings of the model by the compiler (section 10 and
  [animation-script.md](animation-script.md#settings-paths)); the grammar accepts any word.
- A `Caption` text after the title is taken when the next token is a string or a word other than `for`.
- `Field` in `label` may be a word or a string. The compiler knows the names `name`, `class`, `storey`, `material`,
  `globalid` and `type` (any case), and any `"Set.Prop"` with a dot.

## 4. Expressions and text

```ebnf
(* Numbers. Precedence from the lowest: + and - (left to right), * and / (left to right), unary - and +, then the primary. *)
Expr          ::= Term ( ( "+" | "-" ) Term )*
Term          ::= Unary ( ( "*" | "/" ) Unary )*
Unary         ::= "-" Unary | "+" Unary | Primary
Primary       ::= Number | Word | "(" Expr ")"                      /* a Word is a name set by put, or index inside a loop */

(* Text. Pieces are joined with &. A bare word is a name (a variable, index, or it) and must be one at compile time. *)
Str           ::= StrPart ( "&" StrPart )*
StrPart       ::= String | Word | Expr
```

A `Word` in an expression is looked up as a name when the script is compiled. Names are case-insensitive. An unknown name is
an error, and so is `it` outside `repeat for each`.

## 5. Elements

```ebnf
(* Where a statement says elements. *)
Elements      ::= "where" Criteria
                | ( "class" | "classes" ) ClassName ( "," ClassName )*
                | "set" String
                | "the" "selection"
                | "selection"
                | "everything"
                | "it"
                | "elements" String ( "," String )*
ClassName     ::= Word | String

(* A criteria is the words and signs after where, up to the first stop word at parenthesis depth 0.
   Stop words: over ease margin fading for with about. The signs + * / & are not allowed. The text must parse
   as a query (section 8). *)
Criteria      ::= CriteriaToken+
```

`class A, B` is the same as `where class IN ('A', 'B')`. `set "Name"` names a stored selection set. `elements "id"` lists
GlobalIds. The keyword `set` in an element position always takes a string.

## 6. Loop names and reserved names

```ebnf
(* Loop names: inside repeat for each, it is the element (GlobalId) or the set name; index counts passes from 1. *)
LoopVar       ::= "it" | "index"

(* Words that may not be used as names with put (the compiler's RESERVED list). *)
ReservedName  ::= "fly" | "orbit" | "set" | "mode" | "apply" | "show" | "hide" | "isolate" | "select"
                | "caption" | "label" | "hover" | "wait" | "together" | "repeat" | "put" | "end"
                | "it" | "index" | "over" | "ease" | "margin" | "fading" | "for" | "with" | "about"
                | "to" | "into" | "times" | "where" | "class" | "everything" | "selection"
                | "true" | "false" | "on" | "off" | "yes" | "no"
```

## 7. Blocks in the script

The block rules of section 2 nest. The body of each block is the statements of the lines between its header and its
closing line. A `together` starts all its statements at one moment. A `repeat` runs its body again and again. A `repeat for
each` runs its body once for each element or set. The timing is in section 11.

## 8. Criteria: the query language

The text after `where` is rewritten into query text, then parsed by the query grammar of `web/src/query/parser.ts`.

```ebnf
(* The rewrite (buildQuery). A word or a string in a value position becomes a text value. Value positions are: after a
   comparison operator, after LIKE, after BETWEEN and its AND, and inside the parentheses of IN.
   A word that is one of the query keywords becomes that keyword in capitals.
   A string outside a value position is a quoted column name. A word outside a value position is a column name. *)

(* The query grammar (after the rewrite). Precedence from the lowest: OR, AND, NOT, comparison. *)
Query         ::= QOr
QOr           ::= QAnd ( "OR" QAnd )*
QAnd          ::= QNot ( "AND" QNot )*
QNot          ::= "NOT" QNot | QPrimary
QPrimary      ::= "(" QOr ")"
                | QOperand
                  ( QCmpOp QOperand
                  | "IS" "NOT"? "NULL"
                  | "NOT"? "LIKE" QOperand
                  | "NOT"? "IN" "(" QOperand ( "," QOperand )* ")"
                  | "NOT"? "BETWEEN" QOperand "AND" QOperand )?      /* no tail: the operand is tested for TRUE */
QCmpOp        ::= "=" | "==" | "!=" | "<>" | "<" | "<=" | ">" | ">="
QOperand      ::= QColumn | QText | QNumber | "-" QNumber | "TRUE" | "FALSE" | "NULL"
QColumn       ::= Word | QuotedName                                /* a dotted word, or "double quoted" */
QText         ::= "'" ( "''" | [^'] )* "'"                          /* made by the rewrite from a bare word or a "string" */
QuotedName    ::= '"' ( '""' | [^"] )+ '"'
QNumber       ::= Digits ( "." Digits? )? | "." Digits
```

Examples of criteria accepted by the script:

```xrayanim
-- criteria forms
select where class = IfcPump and storey = "Level 2"
select where name like "P-1%" or not class IN (IfcSlab, IfcWall)
select where "Pset_WallCommon.IsExternal"
select where area between 2 and 10
select where material is not null
hide where class = IfcSlab fading over 2 seconds
```

Criteria rules:

- The words `over`, `ease`, `margin`, `fading`, `for`, `with` and `about` end the criteria at depth 0. A text value with one of
  these words must be in double quotes, and then it is accepted: `where name = "over"`. A bare `over` as a value is an error.
- A value with a space must be in double quotes. `where storey = Level 2` is an error (`Level` is a value, then `2` is not
  allowed).
- Single quotes are not accepted in a script. Text is in double quotes.
- Numbers with an exponent (`1e3`) are not accepted by the script lexer, although the query grammar has them.
- Column names are not checked when the script is parsed. They are checked when the elements are resolved against the model.

## 9. Keywords

The keywords the language knows. Each one appears in the grammar above as a quoted term.

| Group | Words |
| --- | --- |
| Statements | `fly`, `orbit`, `set`, `mode`, `apply`, `show`, `hide`, `isolate`, `select`, `caption`, `label`, `hover`, `wait`, `together`, `repeat`, `put`, `end` |
| Modes | `ghost`, `solid`, `radiograph`, `glow`, `cutaway` |
| Options and connectors | `to`, `view`, `preset`, `over`, `ease`, `margin`, `fading`, `for`, `with`, `about`, `into`, `times`, `time`, `in`, `each` |
| Ease | `linear`, `in`, `out`, `inout`, `inoutsine` |
| Units | `s`, `sec`, `secs`, `second`, `seconds`, `degree`, `degrees`, `deg` |
| Elements | `where`, `class`, `classes`, `set`, `sets`, `the`, `selection`, `everything`, `it`, `elements`, `element`, `nothing`, `none` |
| Loop names | `index`, `it` |
| Booleans | `true`, `false`, `on`, `off`, `yes`, `no` |
| Criteria | `and`, `or`, `not`, `like`, `in`, `between`, `is`, `null` |

## 10. Limits

Values from the code. A limit that is exceeded gives an error (or, for a loop count, a message) and the script does not play.

| Limit | Value | Source | Result when exceeded |
| --- | --- | --- | --- |
| Source size | 200 000 characters | `lexer.ts` `MAX_SOURCE_CHARS` | Error: the script is too long. Nothing is parsed. |
| Source lines | 5 000 lines | `lexer.ts` `MAX_SOURCE_LINES` | Error: too many lines. Nothing is parsed. |
| Block nesting | 8 blocks deep | `parser.ts` `MAX_NESTING` | Error on the 9th opening block. |
| Repeat count | a whole number from 0 to 500 | `compiler.ts` `LIMITS.maxIterations` | Error for a fraction, a negative count or more than 500. |
| Loop items | up to 500 elements | `compiler.ts` `maxIterations` | Error: narrow the elements with `where`. Set loops have no separate count; `maxSteps` and `maxCues` still apply. |
| Statements in all | 20 000 | `LIMITS.maxSteps` | Error. Loops count every pass. |
| Cues | 5 000 | `LIMITS.maxCues` | Error: use fewer or smaller loops. |
| Script duration | 3 600 seconds (1 hour) | `LIMITS.maxDuration` | Error when a cue would end after this time. |
| One duration | 0 to 3 600 seconds | `compiler.ts` `secs()` | Error for a negative value or one over the limit. |
| Fly margin | 1 to 6 | `compiler.ts` `flyTo` | Error outside this range. |
| Orbit angle | up to 36 000 degrees in either direction | `compiler.ts` `orbit` | Error (100 turns). |
| Division | the divisor must not be 0; results must be finite | `compiler.ts` `num()` | Error. |
| Loop index | `index` counts from 1 | `compiler.ts` `repeat` | Not a limit. Restored after the loop. |

## 11. Timing

Statements run in order. **Each statement starts when the one before it has ended.** A `together` block starts all its
statements at its own start time and lasts as long as its longest statement. A `repeat` runs its body again, one pass after
another. The start of the script is time 0.

| Statement | Lasts | Default | Notes |
| --- | --- | --- | --- |
| `fly to <elements>` | `over N` seconds | 2 seconds, ease `inout` | `margin` changes the framing, not the time. |
| `fly to view "name"` | `over N` seconds | 2 seconds, ease `inout` | |
| `orbit N degrees` | `over N` seconds | 3 seconds, ease `inout` | `about` defaults to the whole model. |
| `set path to value` | `over N` seconds | 0 (instant) | Numbers blend with the ease. Other values switch at the end. The default ease is `inout` for numbers over time, else none. |
| `mode`, `apply preset`, `select` | nothing | 0 | Instant. |
| `show`, `hide`, `isolate` | `fading over N` seconds | 0 (instant) | With a time, the elements fade. |
| `caption` | `for N` seconds | 3 seconds | The next statement waits for it. |
| `label` | `for N` seconds | 3 seconds | The next statement waits for it. |
| `hover` | `for N` seconds | 2 seconds | The next statement waits for it. |
| `wait N` | N seconds | 0 | |
| `put` | nothing | 0 | |
| `together` | the longest statement in it | | |
| `repeat` | the body, once per pass | | |
| `repeat for each` | the body, once per element or set | | An empty list lasts 0 seconds and gives a warning. |

Example of timing. `together` runs the fly and the caption from the same moment, and the wait after it starts at 3 seconds:

```xrayanim
fly to class IfcPump over 3 seconds
together
  orbit 90 degrees about class IfcPump over 3 seconds
  caption "The pumps" "Seen from the side" for 3 seconds
end together
wait 1
mode solid
```

## 12. Notes and differences

These are facts about the language as it stands, found while writing this page. They are not changes to the code.

- A seconds unit may be glued to the number in any spelling (`2s`, `2sec`, `2secs`, `2second`, `2seconds`) or written after a space.
- `repeat N time` (the singular) is accepted, and so is `repeat for each elements in ...`.
- A boolean word (`on`, `off`, `yes`, `no`, `true`, `false`) is a boolean only when it is alone. In a list such as `set a to on, 2` it is a name.
- The compiler accepts `label` fields `material`, `globalid` and `type`, which the parser's comment does not list.
- `set` paths and preset names are only checked when the model is loaded. Without a model the compiler gives a warning and accepts them.
- A no-break space (U+00A0, U+2007, U+202F), as pasted from a document, counts as a space.
- `caption` lasts `for N`; `over`, `ease` or `fading` after a caption is an error that says so.
- A loop over selection sets has the same cap as a loop over elements (500).
