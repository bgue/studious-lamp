// The adapter for the decision model Jev (TypeSafe AI). EVERY field name, endpoint and header of the wire format is in this
// file, so one place changes when the vendor documentation (docs.typesafe.ai) differs from what is written here.
//
// These details come from public secondary sources and are NOT verified against docs.typesafe.ai (it was not reachable
// when this was written). See web/docs-features/classify.md, "Unverified details".
//
//   POST <endpoint>            default https://api.typesafe.ai/v1/systemone
//   Authorization: Bearer <key>   Content-Type: application/json
//   request  { model, state, questions: { <name>: { type: 'choice', instructions, criteria: { <option>: <text> } }
//                                                 | { type: 'score',  instructions, criteria: [ <level text>, ... ] }
//                                                 | { type: 'noul',   instructions: <statement> } } }
//   response { model, answers: { <name>: { type: 'choice', choice, confidence, probabilities }
//                                       | { type: 'score', score, confidence, legend, probabilities }
//                                       | { type: 'noul', noul } }, usage: { input_tokens, output_tokens } }

import { ProviderError } from './types';

export const JEV_DEFAULT_ENDPOINT = 'https://api.typesafe.ai/v1/systemone';
/** Pinned version: the default. Another host (DigitalOcean inference) uses 'typesafe-jev-1.13.0', so the id is a setting. */
export const JEV_DEFAULT_MODEL = 'jev-1.13.0';
/** A moving alias: the answers can change when the vendor ships a new version. */
export const JEV_LATEST_ALIAS = 'jev-latest';

export const isMovingAlias = (model: string): boolean => /(^|[-/])latest$/i.test(model.trim());

// ---------------------------------------------------------------- JSON and wire types

export type JsonValue = string | number | boolean | null | JsonValue[] | { [k: string]: JsonValue };
export type JsonObject = { [k: string]: JsonValue };

export interface ChoiceQuestion {
  type: 'choice';
  instructions: string;
  /** option -> what the option covers */
  criteria: Record<string, string>;
}
export interface ScoreQuestion {
  type: 'score';
  instructions: string;
  /** Text of level 0, level 1, ... */
  criteria: string[];
}
export interface NoulQuestion {
  type: 'noul';
  /** A statement to judge true or false. */
  instructions: string;
}
export type Question = ChoiceQuestion | ScoreQuestion | NoulQuestion;
export type Questions = Record<string, Question>;

export interface ChoiceAnswer {
  type: 'choice';
  choice: string;
  confidence: number;
  probabilities: Record<string, number>;
}
export interface ScoreAnswer {
  type: 'score';
  score: number;
  confidence: number;
  legend?: Record<string, unknown>;
  probabilities?: Record<string, number>;
}
export interface NoulAnswer {
  type: 'noul';
  /** P(the statement is true) */
  noul: number;
}
export type Answer = ChoiceAnswer | ScoreAnswer | NoulAnswer;

export interface Answers {
  /** The model id that answered. Logged with every result. */
  model: string;
  answers: Record<string, Answer>;
  usage?: { input_tokens?: number; output_tokens?: number };
}

// ---------------------------------------------------------------- request

export const choiceQuestion = (instructions: string, criteria: Record<string, string>): ChoiceQuestion => ({ type: 'choice', instructions, criteria });
export const scoreQuestion = (instructions: string, criteria: string[]): ScoreQuestion => ({ type: 'score', instructions, criteria });
export const noulQuestion = (statement: string): NoulQuestion => ({ type: 'noul', instructions: statement });

export interface JevRequest {
  model: string;
  state: JsonObject;
  questions: Questions;
}

export function buildRequest(model: string, state: JsonObject, questions: Questions): JevRequest {
  return { model, state, questions };
}

/** Request headers. Without a key (a same-origin proxy that adds it) no Authorization header is sent. */
export function requestHeaders(apiKey: string | null | undefined): Record<string, string> {
  const h: Record<string, string> = { 'Content-Type': 'application/json' };
  if (apiKey) h['Authorization'] = `Bearer ${apiKey}`;
  return h;
}

// ---------------------------------------------------------------- response

const isObj = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v);
const isProb = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v) && v >= 0 && v <= 1;

function readProbabilities(v: unknown, name: string, options: readonly string[] | null): Record<string, number> {
  if (!isObj(v)) throw new ProviderError(`Answer "${name}" has no probabilities object.`);
  const out: Record<string, number> = {};
  for (const [k, p] of Object.entries(v)) {
    if (!isProb(p)) throw new ProviderError(`Answer "${name}": the probability of "${k}" is not a number from 0 to 1.`);
    if (options && !options.includes(k)) throw new ProviderError(`Answer "${name}": probability for "${k}", which is not one of the options.`);
    out[k] = p;
  }
  return out;
}

/**
 * Check a response against the questions that were asked and return it in the typed shape. Throws a ProviderError with
 * a plain message for a wrong shape, a missing answer, a choice outside the options, or a number outside 0 to 1.
 */
export function parseResponse(json: unknown, questions: Questions): Answers {
  if (!isObj(json)) throw new ProviderError('The response is not a JSON object.');
  if (typeof json['model'] !== 'string' || !json['model']) throw new ProviderError('The response has no model id.');
  const raw = json['answers'];
  if (!isObj(raw)) throw new ProviderError('The response has no "answers" object.');
  const answers: Record<string, Answer> = {};
  for (const [name, q] of Object.entries(questions)) {
    const a = raw[name];
    if (!isObj(a)) throw new ProviderError(`The response has no answer for "${name}".`);
    if (a['type'] !== q.type) throw new ProviderError(`Answer "${name}" has type ${JSON.stringify(a['type'])}, expected "${q.type}".`);
    if (q.type === 'choice') {
      const options = Object.keys(q.criteria);
      const choice = a['choice'];
      if (typeof choice !== 'string' || !options.includes(choice)) throw new ProviderError(`Answer "${name}": ${JSON.stringify(choice)} is not one of the options.`);
      if (!isProb(a['confidence'])) throw new ProviderError(`Answer "${name}" has no confidence from 0 to 1.`);
      answers[name] = { type: 'choice', choice, confidence: a['confidence'], probabilities: readProbabilities(a['probabilities'], name, options) };
    } else if (q.type === 'noul') {
      if (!isProb(a['noul'])) throw new ProviderError(`Answer "${name}" has no probability from 0 to 1.`);
      answers[name] = { type: 'noul', noul: a['noul'] };
    } else {
      const score = a['score'];
      if (typeof score !== 'number' || !Number.isFinite(score) || score < 0 || score > q.criteria.length - 1) throw new ProviderError(`Answer "${name}": the score is outside the levels.`);
      if (!isProb(a['confidence'])) throw new ProviderError(`Answer "${name}" has no confidence from 0 to 1.`);
      answers[name] = {
        type: 'score', score, confidence: a['confidence'],
        ...(isObj(a['legend']) ? { legend: a['legend'] } : {}),
        ...(isObj(a['probabilities']) ? { probabilities: readProbabilities(a['probabilities'], name, null) } : {}),
      };
    }
  }
  const out: Answers = { model: json['model'], answers };
  const u = json['usage'];
  if (isObj(u)) {
    out.usage = {
      ...(typeof u['input_tokens'] === 'number' ? { input_tokens: u['input_tokens'] } : {}),
      ...(typeof u['output_tokens'] === 'number' ? { output_tokens: u['output_tokens'] } : {}),
    };
  }
  return out;
}

export function readChoice(a: Answers, name: string): ChoiceAnswer {
  const x = a.answers[name];
  if (!x || x.type !== 'choice') throw new ProviderError(`No choice answer "${name}".`);
  return x;
}
export function readNoul(a: Answers, name: string): number {
  const x = a.answers[name];
  if (!x || x.type !== 'noul') throw new ProviderError(`No yes/no answer "${name}".`);
  return x.noul;
}
