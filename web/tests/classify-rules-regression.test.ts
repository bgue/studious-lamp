// Regression guard for the rules: their output (discipline, sub-discipline, division, final flag) for every bundled model
// except the process plant must not change unless the schema says it should. The fixture was taken before the process-context
// rules were added. To accept a justified change: UPDATE_RULES_SNAPSHOT=1 npx vitest run tests/classify-rules-regression.test.ts,
// then list each difference (the test prints them) with its reason in the report.

import { existsSync, readFileSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import { buildInputs, classByRules, defaultSchema, isBuildingContext, resolveRule, RULE_FINAL } from '../src/classify';
import { sidecarModel } from './classify-helpers';

const MODELS = ['building', 'fzk-haus', 'plumbing', 'synth5k', 'debris-demo'];
const FIXTURE = fileURLToPath(new URL('./fixtures/rules-snapshot.json', import.meta.url));
const schema = defaultSchema();

/** "DISC/SUB/DIV/F" (F final, W weak) per element id, or "-" when no rule applies. */
function snapshot(name: string): { names: Record<string, string>; rules: Record<string, string> } {
  const model = sidecarModel(name);
  const names: Record<string, string> = {};
  const rules: Record<string, string> = {};
  for (const i of buildInputs(model, model.elements.map((e) => e.id))) {
    const h = classByRules(i);
    const d = h ? resolveRule(h, schema, isBuildingContext(i)) : null;
    names[i.id] = `${i.ifcClass} ${i.name}`;
    rules[i.id] = d ? `${d.discipline}/${d.subDiscipline ?? ''}/${d.division ?? ''}/${d.confidence >= RULE_FINAL ? 'F' : 'W'}` : '-';
  }
  return { names, rules };
}

describe('rules regression on the other bundled models', () => {
  if (process.env['UPDATE_RULES_SNAPSHOT']) {
    it('writes the fixture', () => {
      const out: Record<string, Record<string, string>> = {};
      for (const m of MODELS) out[m] = snapshot(m).rules;
      writeFileSync(FIXTURE, JSON.stringify(out));
    });
    return;
  }
  const fixture = existsSync(FIXTURE) ? (JSON.parse(readFileSync(FIXTURE, 'utf8')) as Record<string, Record<string, string>>) : {};
  for (const m of MODELS) {
    it(`${m}: rules output is unchanged`, () => {
      const { names, rules } = snapshot(m);
      const want = fixture[m] ?? {};
      const diffs: string[] = [];
      for (const id of new Set([...Object.keys(want), ...Object.keys(rules)])) {
        if (want[id] !== rules[id]) diffs.push(`${names[id] ?? id}: ${want[id] ?? 'missing'} -> ${rules[id] ?? 'missing'}`);
      }
      expect(diffs.slice(0, 20), `${diffs.length} differences`).toEqual([]);
    });
  }
});
