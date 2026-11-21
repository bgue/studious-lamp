// Label fields that read the running 4D schedule: activity, percent, finish.
import { describe, expect, it } from 'vitest';
import { fieldText, labelLines } from '../src/anim/hud/fields';

const el = { name: 'Sparren-12', ifcClass: 'IfcMember', globalId: 'g', schedule: { code: 'A1310', name: 'Rafters', percent: 45, finish: Date.UTC(2027, 4, 21, 17) } };

describe('schedule label fields', () => {
  it('reads the activity, its progress and its finish date', () => {
    expect(fieldText(el, 'activity')).toBe('A1310 Rafters');
    expect(fieldText(el, 'percent')).toBe('45 % done');
    expect(fieldText(el, 'finish')).toBe('finishes 2027-05-21');
    expect(labelLines(el, ['activity', 'percent', 'finish'])).toEqual(['A1310 Rafters', '45 % done', 'finishes 2027-05-21']);
  });
  it('falls back to the element name when no schedule plays', () => {
    const { schedule: _s, ...plain } = el;
    expect(labelLines(plain, ['activity', 'percent', 'finish'])).toEqual(['Sparren-12']);
  });
});
