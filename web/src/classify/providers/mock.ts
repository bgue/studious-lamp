// The mock provider: deterministic answers for tests and for trying the interface without a model. A choice question is
// answered by word overlap between the element state and the option texts, turned into probabilities with a softmax.
// The same state always gives the same answer.

import { ProviderError } from '../types';
import type { DecisionModel } from '../types';
import type { Answer, Answers, JsonObject, Questions } from '../jevAdapter';

export const MOCK_MODEL_ID = 'mock-1';

const tokens = (s: string): string[] => s.toLowerCase().split(/[^a-z0-9]+/).filter((w) => w.length > 2);

/** Plural and class prefixes folded together: "ducts", "duct", "IfcDuctSegment" share "duct". */
const stem = (w: string): string => w.replace(/(ies|es|s)$/, '');

function hash(s: string): number {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) h = Math.imul(h ^ s.charCodeAt(i), 16777619);
  return (h >>> 0) / 4294967296;
}

function chooseAnswer(state: JsonObject, text: string, criteria: Record<string, string>): Answer {
  const words = new Set(tokens(text.replace(/([a-z])([A-Z])/g, '$1 $2')).map(stem));
  const opts = Object.keys(criteria);
  const scores = opts.map((o) => {
    let s = 0;
    for (const w of tokens(criteria[o]!)) if (words.has(stem(w))) s += 1;
    return s + hash(`${JSON.stringify(state)}|${o}`) * 0.01;
  });
  const exps = scores.map((s) => Math.exp(s * 1.5));
  const sum = exps.reduce((a, b) => a + b, 0);
  const probabilities: Record<string, number> = {};
  let best = 0;
  opts.forEach((o, i) => {
    probabilities[o] = Math.round((exps[i]! / sum) * 1e4) / 1e4;
    if (exps[i]! > exps[best]!) best = i;
  });
  return { type: 'choice', choice: opts[best]!, confidence: probabilities[opts[best]!]!, probabilities };
}

export interface MockOptions {
  /** Replace the default answers. Throw a ProviderError to simulate a failure. */
  answer?: (state: JsonObject, questions: Questions) => Answers;
  model?: string;
  /** Milliseconds to wait before answering (to test abort and progress). */
  delayMs?: number;
}

export interface MockProvider extends DecisionModel {
  /** Every request that arrived, in order. */
  readonly log: Array<{ state: JsonObject; questions: Questions }>;
}

export function createMockProvider(o: MockOptions = {}): MockProvider {
  const log: MockProvider['log'] = [];
  return {
    provider: 'mock',
    log,
    async decide(state, questions, signal): Promise<Answers> {
      if (signal.aborted) throw new DOMException('Aborted', 'AbortError');
      log.push({ state, questions });
      if (o.delayMs) {
        await new Promise<void>((resolve, reject) => {
          const t = setTimeout(resolve, o.delayMs);
          signal.addEventListener('abort', () => { clearTimeout(t); reject(new DOMException('Aborted', 'AbortError')); }, { once: true });
        });
      }
      if (o.answer) return o.answer(state, questions);
      const text = JSON.stringify(state);
      const answers: Record<string, Answer> = {};
      for (const [name, q] of Object.entries(questions)) {
        if (q.type === 'choice') answers[name] = chooseAnswer(state, text, q.criteria);
        else if (q.type === 'noul') answers[name] = { type: 'noul', noul: state['building_context'] === false ? 0.04 : 0.96 };
        else throw new ProviderError('The mock provider does not answer score questions.');
      }
      return { model: o.model ?? MOCK_MODEL_ID, answers, usage: { input_tokens: Math.ceil(text.length / 4), output_tokens: 1 } };
    },
  };
}
