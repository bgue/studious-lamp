// The syntax tree of the animation script language. Every node carries the line and columns it came from, so the compiler can
// point at the exact place of a semantic error (an unknown name, a number out of range).

export interface Span {
  line: number;
  col: number;
  end: number;
}

export type Ease = 'linear' | 'in' | 'out' | 'inOut';

/** An expression. Statements that want a number (`over`, `for`, `wait`, ...) read the arithmetic part: numbers, names of
 *  variables, + - * / and parentheses, function calls and `the count of`. `put`, `if`, `repeat while|until`, `return` and the
 *  arguments of calls read all of it: text, `&`, comparisons, `and` `or` `not`, `there are`. It is evaluated when the script compiles. */
export type Num = Span &
  (
    | { k: 'num'; v: number }
    | { k: 'var'; name: string }
    | { k: 'neg'; a: Num }
    | { k: 'bin'; op: '+' | '-' | '*' | '/'; a: Num; b: Num }
    | { k: 'str'; v: string }
    | { k: 'bool'; v: boolean }
    /** `a & b`: the two as text, joined. */
    | { k: 'cat'; a: Num; b: Num }
    | { k: 'cmp'; op: '=' | '<>' | '<' | '>' | '<=' | '>='; a: Num; b: Num }
    | { k: 'and' | 'or'; a: Num; b: Num }
    | { k: 'not'; a: Num }
    /** `name(arg, arg)`: a call of a `function`. */
    | { k: 'call'; name: string; args: Num[] }
    /** `the count of <elements>`: how many elements match, in the model as it is when the script compiles. */
    | { k: 'count'; target: Elements }
    /** `there are <elements>` / `there are no <elements>`. */
    | { k: 'there'; target: Elements; none: boolean }
  );
export type Expr = Num;

export type StrPart = { k: 'text'; v: string } | { k: 'name'; name: string; span: Span } | { k: 'num'; n: Num };

/** Text: quoted pieces, `it` and variables joined with `&`. */
export interface Str extends Span {
  parts: StrPart[];
}

/** A bare word in a query that may be a variable: where it sits in `query` (the quoted word) and its name. */
export interface QuerySub {
  at: number;
  len: number;
  name: string;
}

/** Which elements a statement acts on. */
export type Elements = Span &
  (
    /** `subs`: bare words of the query in value position (`storey = name`): a variable of that name gives its value when the script compiles. */
    | { k: 'query'; query: string; subs?: QuerySub[] }
    | { k: 'set'; name: string }
    | { k: 'selection' }
    | { k: 'everything' }
    | { k: 'it' }
    | { k: 'gids'; ids: string[] }
    /** 4D: the elements in this state of the running schedule (`active`, `completed`, `critical`). */
    | { k: 'schedule'; set: 'active' | 'completed' | 'critical' }
  );

/** A text of the 4D statements with where it stands (a plan name, a date, a milestone, a storey, a colour). */
export type Text = Span & { v: string };

export type Value =
  | (Span & { k: 'bool'; v: boolean })
  | (Span & { k: 'str'; v: string })
  /** A bare word: a variable when one has this name, else text (`set imaging.style to radiograph`). */
  | (Span & { k: 'word'; text: string })
  | (Span & { k: 'list'; items: Num[] });

/** Every statement spans its first token to its last. */
type Base = Span;

export type Stmt =
  | (Base & { kind: 'flyTo'; target: Elements; over?: Num; ease?: Ease; margin?: Num })
  | (Base & { kind: 'flyView'; name: string; over?: Num; ease?: Ease })
  | (Base & { kind: 'orbit'; degrees: Num; about?: Elements; over?: Num; ease?: Ease })
  | (Base & { kind: 'set'; path: string; pathSpan: Span; value: Value; over?: Num; ease?: Ease })
  | (Base & { kind: 'mode'; mode: string; modeSpan: Span })
  | (Base & { kind: 'preset'; name: string; nameSpan: Span })
  | (Base & { kind: 'visibility'; op: 'show' | 'hide' | 'isolate'; target: Elements; fading?: Num })
  | (Base & { kind: 'select'; target: Elements | null })
  | (Base & { kind: 'caption'; title: Str; text?: Str; for?: Num })
  | (Base & { kind: 'label'; target: Elements; fields: string[]; for?: Num })
  | (Base & { kind: 'hover'; target: Elements; for?: Num })
  | (Base & { kind: 'wait'; seconds: Num })
  | (Base & { kind: 'together'; body: Stmt[] })
  | (Base & { kind: 'repeat'; times: Num; body: Stmt[] })
  | (Base & { kind: 'forEach'; each: 'element' | 'set'; target?: Elements; body: Stmt[] })
  | (Base & { kind: 'put'; value: Num; name: string; nameSpan: Span })
  // ---- decisions, loops and your own commands
  /** `if c then` ... `else if c then` ... `else` ... `end if`, or the one-line `if c then <statement>`. */
  | (Base & { kind: 'if'; branches: Array<{ cond: Num; body: Stmt[] } & Span>; otherwise?: Stmt[] })
  /** `repeat while c` / `repeat until c` (until: true). */
  | (Base & { kind: 'while'; until: boolean; cond: Num; body: Stmt[] })
  /** `repeat with i from a to|down to b [by s]`. */
  | (Base & { kind: 'repeatWith'; name: string; nameSpan: Span; from: Num; to: Num; down: boolean; by?: Num; body: Stmt[] })
  /** `on name params` ... `end name` (a handler) or `function name params` ... `end name`. */
  | (Base & { kind: 'def'; form: 'on' | 'function'; name: string; nameSpan: Span; params: Array<{ name: string; span: Span }>; body: Stmt[] })
  /** A call of a handler as a statement: `name arg, arg`. */
  | (Base & { kind: 'call'; name: string; nameSpan: Span; args: Num[] })
  | (Base & { kind: 'return'; value?: Num })
  // ---- playback
  /** `show|hide issues`, `show|hide drawings`. */
  | (Base & { kind: 'overlays'; issues?: boolean; drawings?: boolean })
  /** `fade new elements over N seconds` / `instantly` (no seconds). */
  | (Base & { kind: 'fadeDefault'; seconds?: Num })
  // ---- 4D
  /** `schedule "plan" [view V] [from "date"] [to "date"] [over N]`: plays the plan; the statements after it start together with it. */
  | (Base & { kind: 'schedule'; plan: Text; view?: 'planned' | 'actual' | 'variance'; from?: Text; to?: Text; over?: Num; fade?: Num })
  /** `at date "YYYY-MM-DD"` / `at milestone "name"`: the statements after it start at that moment of the running schedule. */
  | (Base & { kind: 'at'; what: 'date' | 'milestone'; value: Text })
  /** `tint <elements> <colour> [fading over N]`; colour null = `off`. */
  | (Base & { kind: 'tint'; target: Elements; colour: Text | null; fading?: Num })
  | (Base & { kind: 'explode'; mode: 'storeys' | 'radial'; by?: Num; over?: Num })
  | (Base & { kind: 'collapse'; over?: Num })
  | (Base & { kind: 'focus'; target: Elements | null })
  /** `section box around <elements>|storey "name" [over N]`, or `section box off [over N]` (around null). */
  | (Base & { kind: 'section'; around: Elements | { storey: Text } | null; over?: Num });

export type StmtKind = Stmt['kind'];

export interface Program {
  body: Stmt[];
}
