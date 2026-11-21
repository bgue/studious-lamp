// The syntax tree of the animation script language. Every node carries the line and columns it came from, so the compiler can
// point at the exact place of a semantic error (an unknown name, a number out of range).

export interface Span {
  line: number;
  col: number;
  end: number;
}

export type Ease = 'linear' | 'in' | 'out' | 'inOut';

/** A number expression: numbers, names of variables, + - * / and parentheses. */
export type Num = Span &
  (
    | { k: 'num'; v: number }
    | { k: 'var'; name: string }
    | { k: 'neg'; a: Num }
    | { k: 'bin'; op: '+' | '-' | '*' | '/'; a: Num; b: Num }
  );

export type StrPart = { k: 'text'; v: string } | { k: 'name'; name: string; span: Span } | { k: 'num'; n: Num };

/** Text: quoted pieces, `it` and variables joined with `&`. */
export interface Str extends Span {
  parts: StrPart[];
}

/** Which elements a statement acts on. */
export type Elements = Span &
  (
    | { k: 'query'; query: string }
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
  // ---- 4D
  /** `schedule "plan" [view V] [from "date"] [to "date"] [over N]`: plays the plan; the statements after it start together with it. */
  | (Base & { kind: 'schedule'; plan: Text; view?: 'planned' | 'actual' | 'variance'; from?: Text; to?: Text; over?: Num })
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
