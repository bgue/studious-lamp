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
Token         ::= String | Number | Word | Colour | Punct           /* a statement is a sequence of tokens; WS and Comment may stand between them */

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

(* Colours (for tint). A hash and exactly six hex digits, not followed by a letter, digit or underscore. Any other hash starts a comment. *)
Colour        ::= "#" Hex Hex Hex Hex Hex Hex
Hex           ::= [0-9a-fA-F]

(* Punctuation. Two-character operators are read before one-character ones. *)
Punct         ::= "==" | "!=" | "<>" | "<=" | ">=" | "=" | "<" | ">"                /* "≠", "≤" and "≥" are read as words and accepted as the comparisons */
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
Statement     ::= Simple | Together | Repeat | ForEach | While | RepeatWith | If | Def      /* Def only at the top level, section 2.1 */

(* Block statements. The header is one line; the body is the statements up to the closing line. *)
Together      ::= "together" EOL Script "end" "together"
Repeat        ::= "repeat" Expr ( "times" | "time" ) EOL Script "end" "repeat"
ForEach       ::= "repeat" "for" "each" ( "element" | "elements" ) "in" Elements EOL Script "end" "repeat"
                | "repeat" "for" "each" "set" "in" "sets" EOL Script "end" "repeat"

(* One-line statements. *)
Simple        ::= Fly | FlyView | Orbit | SetStmt | ModeStmt | ApplyStmt
                | Visibility | Overlays | SelectStmt | Caption | Label | Hover | Wait | Put | FadeNew | Call | Return
                | Schedule | At | Tint | Explode | Collapse | Focus | Section          /* the 4D statements, section 3.1 */

(* A closing line holds nothing after its block word. Any other "end" line is an error. *)
```

Each statement occupies one line. The header of a block statement is the whole line: nothing may follow `together`, and
nothing may follow the `in` elements of a `repeat for each` line. A line that starts with `end` must be `end together`,
`end repeat`, `end if` or `end <name>` (for a handler or function) and must close the block that is open. Nesting is at most
8 blocks deep (section 10).

### 2.1 Decisions, loops and your own commands

A script is compiled to a fixed timeline before it plays, so all flow control is decided **when it compiles**, over what is
known then: numbers, text, names, the model (element counts, through the criteria query engine) and the 4D plan. There is no
branching at run time.

```ebnf
If            ::= "if" Cond "then" Simple                          /* one-line form: one plain statement, no block word */
                | "if" Cond "then" EOL Script
                  ( "else" "if" Cond "then" EOL Script )*
                  ( "else" EOL Script )?
                  "end" "if"
While         ::= "repeat" ( "while" | "until" ) Cond EOL Script "end" "repeat"
RepeatWith    ::= "repeat" "with" Word "from" Expr ( "to" | "down" "to" ) Expr ( "by" Expr )? EOL Script "end" "repeat"

(* Your own commands. A handler (on) is called as a statement and puts its statements on the timeline where it is called.
   A function is called in an expression and gives back a value; it computes only, so it holds put, if, repeat and return. *)
Def           ::= Handler | Function
Handler       ::= "on" Word ( Word ( "," Word )* )? EOL Script "end" Word          /* the closing word is the handler's name */
Function      ::= "function" Word ( Word ( "," Word )* )? EOL Script "end" Word
Call          ::= Word ( Full ( "," Full )* )?                     /* a handler's name, as the first word of a line */
Return        ::= "return" Full?                                   /* with a value in a function; without one in a handler (stops it early) */
```

- `else if` and `else` stand alone on their line (`else if <Cond> then` ends the line); the statements of the branch follow
  below. `else` comes last and only once. A one-line `if` holds one plain statement: not `together`, `repeat`, `if`, `on`,
  `function`, `else` or `end`. `return` is plain, so `if n <= 1 then return 1` works.
- `repeat while` runs while the condition is true, `repeat until` runs until it is true. A loop runs at most 500 passes
  (`LIMITS.maxIterations`); then the compiler stops it with an error that names the line (section 10). The statements of all
  passes count against the step limit.
- `repeat with i from a to b` counts up by 1, or by the `by` step (more than 0); `from a down to b` counts down by 1 or by the
  step. The bounds and the step are worked out once. A loop that cannot run (`from 5 to 1`) gives a warning. The name is the
  loop's own: it has its previous value (or none) again after the loop, like `index`.
- A handler or function **may stand anywhere at the top level**, before or after the lines that call it (they are read first).
  A definition inside another block is an error. The names of handlers and functions are case-insensitive, are not words of the
  language (section 6) and are unique; a clash is an error. A handler nobody calls gives a warning (its lines are checked
  only where they run).
- **Names.** A call has its own names: its parameters and the names it `put`s. It reads, in order, its own and then the script's
  (global) names. `put` inside a handler or function always makes or changes its own name; it never changes a global. `it` (the
  element or set of the loop the call was made in) is passed through. `index` and a `repeat with` name belong to the frame that
  runs the loop.
- A call gives one value for each parameter (a wrong count is an error that shows the right form). The values are worked out
  where the call is written. Handlers and functions may call each other and themselves (recursion) up to 16 calls deep; the 17th
  is an error. A handler's statements start where it is called and take time like inline statements; the line of a cue is the
  line inside the handler, and an error inside it says where it was called from.
- A `function` cannot hold statements for the timeline (`fly`, `wait`, `show`, `caption`, a handler call, ...); that is an error.
  `return` outside a function or a handler is an error.
- In `where` clauses and the `class` shorthand a bare word in a value position that is the name of a variable stands for its
  value (`where storey = name`); put text in double quotes to keep it as text.

Example: a handler called in a counting loop, a function in a condition, a guard that looks at the model.

```xrayanim
function isTop n
  return n = 3
end isTop

on showFloor name
  if there are (where class = IfcWall and storey = name) then
    fly to where storey = name over 2 seconds
    caption name for 2 seconds
  end if
end showFloor

repeat with i from 1 to 3
  showFloor "Level " & i
  if isTop(i) then caption "Top floor" for 1 seconds
end repeat
show issues
```

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

(* Playback. Issues and drawings are hidden while a script plays (the player does that); a script shows them only when it says so.
   They come back as they were when playback ends. Instant. *)
Overlays      ::= ( "show" | "hide" ) Overlay ( ( "," | "and" ) Overlay )*
Overlay       ::= "issues" | "drawings"
(* The default fade for elements that appear or disappear from here on; "instantly" is 0. *)
FadeNew       ::= "fade" "new" "elements" ( "over" Quantity | "instantly" | "instant" )

SelectStmt    ::= "select" ( "nothing" | "none" | Elements )

Caption       ::= "caption" Str Str? ForOpt?                       /* a bare word after the title is read as text, see Str */

Label         ::= "label" Elements "with" Field ( "," Field )* ForOpt?
Field         ::= Word | String                                    /* name, class, storey, material, globalid, type, or "Pset_X.Prop" */

Hover         ::= "hover" Elements ForOpt?

Wait          ::= "wait" Quantity

Put           ::= "put" Full "into" Word                           /* a number, text or yes/no (section 4); the name must not be a reserved word (section 6) */
```

Notes on the simple statements:

- `set` takes a Word as the path. The path is checked against the settings of the model by the compiler (section 10 and
  [animation-script.md](animation-script.md#settings-paths)); the grammar accepts any word.
- A `Caption` text after the title is taken when the next token is a string or a word other than `for`.
- `Field` in `label` may be a word or a string. The compiler knows the names `name`, `class`, `storey`, `material`,
  `globalid` and `type` (any case), and any `"Set.Prop"` with a dot.

## 3.1 The 4D statements

The 4D statements play a 4D plan (`FourDPlan`, `web/src/schedule/types.ts`) and direct the film on top of it. A plan is found by
name when the script is compiled (the `plans` option of `compileScript`; the viewer gives the plans it has loaded).

```ebnf
(* schedule starts the plan; the cue is a schedule4d cue over the given time. View, from and to are recorded in the cue
   for the host to rebuild the plan with. Without over: the plan's own film length. *)
Schedule      ::= "schedule" String ( ViewOpt | FromOpt | ToOpt | OverOpt | FadeOpt )*
FadeOpt       ::= "fade" Quantity                                  /* how long a new element fades in: schedule4d.fadeIn, seconds */
ViewOpt       ::= "view" ( "planned" | "actual" | "variance" )
FromOpt       ::= "from" String                                    /* "YYYY-MM-DD" */
ToOpt         ::= "to" String

(* at puts the statements after it at that moment of the running schedule. The date is "YYYY-MM-DD", or with a time
   "YYYY-MM-DDTHH:MM" or "YYYY-MM-DDTHH:MM:SS"; the milestone is a name of the plan (any case). *)
At            ::= "at" ( "date" | "milestone" ) String

Tint          ::= "tint" Elements ( Colour | ColourName | String | "off" | "none" | "clear" ) FadingOpt?
ColourName    ::= "red" | "orange" | "yellow" | "green" | "teal" | "cyan" | "blue" | "indigo" | "purple" | "magenta"
                | "pink" | "brown" | "grey" | "gray" | "white" | "black"

Explode       ::= "explode" ( "storeys" | "radial" ) ( ByOpt | OverOpt )*
ByOpt         ::= "by" Expr                                        /* the factor, 0 to 10 */
Collapse      ::= "collapse" OverOpt?
Focus         ::= "focus" ( "nothing" | "none" | Elements )
Section       ::= "section" "box" ( "off" OverOpt?
                                  | "around" ( "storey" String | Elements ) OverOpt? )
```

Notes on the 4D statements:

- `schedule` does not wait: the statements after it start together with it, and the script lasts at least as long as the schedule.
  The last `schedule` before an `at` is the running one. `at` before any `schedule` is an error.
- `at date` and `at milestone` do not wait for the statements before them either: they put the next statements at that
  moment of the schedule, so the blocks of a directed film may overlap. The moment is computed through the plan's time map
  (plan time to video seconds), scaled to the `over` time of the schedule. A date outside the plan counts as its nearest end and
  gives a warning. An unknown plan, an unknown milestone and a text that is not a date are errors with line and column.
- A time inside a hold of the time map (the pause at a milestone) cannot be named by a date; `at milestone "name"` is the first
  second of the hold, and a `wait` after it reaches the rest of it.
- In `tint where class = IfcWall red` the last word is the colour. Put a value that looks like a colour in double quotes.
- Example (the plan "Tower A" of the tests has the milestone "Frame complete"):

```xrayanim
schedule "Tower A" view planned over 120 seconds
at date "2027-03-01"
  explode storeys by 1.5 over 2 seconds
at milestone "Frame complete"
  caption "Frame complete" for 2 seconds
at date "2027-09-01"
  collapse over 2 seconds
```

- `focus active` sets the x-ray focus to the active elements (the schedule runner already does this while a schedule runs, so the
  statement is for moments where the focus was changed); `focus nothing` gives it back to the selection.

## 4. Expressions and text

```ebnf
(* Numbers. Precedence from the lowest: + and - (left to right), * and / (left to right), unary - and +, then the primary. *)
Expr          ::= Term ( ( "+" | "-" ) Term )*
Term          ::= Unary ( ( "*" | "/" ) Unary )*
Unary         ::= "-" Unary | "+" Unary | Primary
Primary       ::= Number | Word | Call | Count | "(" Expr ")"       /* a Word is a name set by put, or index inside a loop */
Call          ::= Word "(" ( Full ( "," Full )* )? ")"               /* a function; the "(" touches the name */
Count         ::= "the" "count" "of" ElementsArg                    /* how many elements match, in the model at compile time */

(* Text. Pieces are joined with &. A bare word is a name (a variable, index, or it) and must be one at compile time. *)
Str           ::= StrPart ( "&" StrPart )*
StrPart       ::= String | Word | Expr
```

A `Word` in an expression is looked up as a name when the script is compiled. Names are case-insensitive. An unknown name is
an error, and so is `it` outside `repeat for each`. A name holds a number, text or a yes/no.

### 4.1 Full expressions and conditions

`put`, `return`, the arguments of calls and the conditions of `if`, `repeat while` and `repeat until` read a **full
expression**; the places that want a number (`over`, `for`, `by`, `wait`, ...) read `Expr` only (which may hold a function call
and `the count of`).

```ebnf
Full          ::= Cond
Cond          ::= CAnd ( "or" CAnd )*                              /* lowest precedence */
CAnd          ::= CNot ( "and" CNot )*
CNot          ::= "not" CNot | Cmp
Cmp           ::= Cat ( CmpOp Cat )?                               /* at most one comparison: join two with and */
CmpOp         ::= "=" | "==" | "<>" | "!=" | "<" | ">" | "<=" | ">=" | "≠" | "≤" | "≥"
Cat           ::= Expr ( "&" Expr )*                               /* text: each side as text, joined */
(* In a full expression the primary also reads: *)
FPrimary      ::= String | BoolWord | There | "(" Cond ")"
There         ::= "there" ( "is" | "are" ) "no"? ElementsArg      /* true when the count is more than 0 (with "no": 0) */
ElementsArg   ::= Elements | "(" Elements ")"                      /* in parentheses when more follows a "where" */
```

- Comparison: two numbers compare as numbers. Two texts compare ignoring case (`<` and `>` use natural order, so "Level 2"
  comes before "Level 10"). A number and a text that reads as a number compare as numbers; anything else is an error. Yes/no
  values compare with `=` and `<>` only.
- `and` and `or` stop at the first answer, so `n > 0 and 10 / n > 1` is safe. `and` binds tighter than `or`; `not` tighter than
  `and`. A condition must be a yes/no; a number or text there is an error.
- `the count of` and `there are` ask the model (the compiler's `resolve` option, as `repeat for each element` does); with no
  model loaded they are errors. They cannot count `active`, `completed` or `critical` (known only while a schedule plays).
  A `where` runs to the end of the line, or to `then` or `into`: write `the count of (where class = IfcDoor) > 3` and
  `there are (where ...) and ...` with parentheses when more follows.

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
                | "active" | "completed" | "critical"                /* 4D: states of the running schedule */
ClassName     ::= Word | String

(* A criteria is the words and signs after where, up to the first stop word at parenthesis depth 0.
   Stop words: over ease margin fading for with about by. The signs + * / & are not allowed. The text must parse
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
                | "schedule" | "at" | "tint" | "explode" | "collapse" | "focus" | "section"
                | "if" | "else" | "function" | "return" | "then" | "and" | "or" | "not" | "there"
                | "it" | "index" | "over" | "ease" | "margin" | "fading" | "for" | "with" | "about"
                | "to" | "into" | "times" | "where" | "class" | "everything" | "selection"
                | "true" | "false" | "on" | "off" | "yes" | "no"
                | "active" | "completed" | "critical" | "date" | "milestone" | "box" | "storey" | "storeys"
                | "radial" | "by" | "from" | "around"
```

`fade` starts a statement (`fade new elements ...`) but is not reserved as a name, so `put 1.5 into fade` still works. A
handler or function cannot take the name of a statement word, so it cannot be called `fade`, `show` or `if`. The words
`while`, `until`, `down`, `new`, `issues`, `drawings`, `count`, `of`, `is` and `are` mean something only at their place in a
statement or expression, and may still be names.

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
| Statements | `fly`, `orbit`, `set`, `mode`, `apply`, `show`, `hide`, `isolate`, `select`, `caption`, `label`, `hover`, `wait`, `together`, `repeat`, `put`, `schedule`, `at`, `tint`, `explode`, `collapse`, `focus`, `section`, `if`, `else`, `on`, `function`, `return`, `fade`, `end` |
| 4D words | `date`, `milestone`, `around`, `box`, `storey`, `storeys`, `radial`, `by`, `from`, `planned`, `actual`, `variance`, `active`, `completed`, `critical` |
| Modes | `ghost`, `solid`, `radiograph`, `glow`, `cutaway` |
| Options and connectors | `to`, `view`, `preset`, `over`, `ease`, `margin`, `fading`, `for`, `with`, `about`, `into`, `times`, `time`, `in`, `each` |
| Flow | `then`, `while`, `until`, `down`, `and`, `or`, `not`, `the`, `count`, `of`, `there`, `is`, `are`, `no` |
| Playback | `new`, `elements`, `instantly`, `instant`, `issues`, `drawings` |
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
| Passes of `repeat while`, `until`, `with` | 500 each | `LIMITS.maxIterations` | Error that names the loop's line: a `while` that is still going after 500 passes is stopped; a `with` range of more than 500 is refused before it runs. |
| Call depth | 16 calls inside one another | `LIMITS.maxCallDepth` | Error at the 17th (a recursion without end). |
| Loop index | `index` counts from 1 | `compiler.ts` `repeat` | Not a limit. Restored after the loop. |

## 11. Timing

Statements run in order. **Each statement starts when the one before it has ended.** (`schedule` and the `at` statements are the
exceptions: section 3.1.) A `together` block starts all its
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
| `repeat while`, `until`, `with` | the body, once per pass | | A pass that does not run lasts 0 seconds. |
| `if` | the statements of the branch taken | | 0 seconds when no branch is taken. |
| a handler call | the statements of the handler | | They start where the call stands and follow one another. |
| `show` / `hide` `issues` or `drawings`, `fade new elements` | nothing | 0 | Instant (the `overlays` and `fadeDefault` cues). |
| `schedule "plan"` | nothing (it does not wait) | the plan's film length | The schedule4d cue lasts `over N`; the next statement starts with it. |
| `at date`, `at milestone` | nothing | | Sets the start of the statements after it to that moment of the schedule, even when that is before the end of earlier ones. |
| `tint` | `fading over N` seconds | 0 (instant) | |
| `explode`, `collapse` | `over N` seconds | 2 seconds | Eased `inout`. |
| `section box` | `over N` seconds | 1.5 seconds | Eased `inout`. |
| `focus` | nothing | 0 | Instant. |

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
- Issues and drawings are hidden while a script plays. `show issues` and `show drawings` (the `overlays` cue) bring them in; `hide` takes them away; the viewer puts them back as they were when playback ends.
- `fade new elements over N seconds` (the `fadeDefault` cue) sets the default fade of elements that appear or disappear after it; `schedule ... fade N seconds` sets the fade-in of that schedule (`fadeIn` of the cue). Without either, the plan's own style decides.
- Where a number is wanted, text is an error ("This is text, not a number"); join text with `&`, which also formats numbers (`"Level " & 2`).
- The label fields `activity`, `percent` and `finish` are for 4D: the HUD fills them from the activity of the element in the running schedule.
- `explode`, `collapse` and `section box` need the viewer's 4D cue runners (`src/anim/fourd/viewerTargets.ts`); a player without them skips the cues.
