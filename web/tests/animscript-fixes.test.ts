import { describe, expect, it } from 'vitest';
import { compileScript } from '../src/anim/script/compiler';

const errs = (src: string, opts = {}): string[] => compileScript(src, opts).errors.filter((e) => (e as { severity?: string }).severity !== 'warning').map((e) => e.message);

describe('script language fixes', () => {
  it('treats a pasted no-break space as a space', () => {
    expect(errs('wait 2')).toEqual([]);
    expect(errs('wait 2 seconds')).toEqual([]);
  });
  it('accepts a seconds unit glued to the number in every spelling', () => {
    for (const u of ['s', 'sec', 'secs', 'second', 'seconds']) expect(errs(`wait 2${u}`), u).toEqual([]);
    expect(errs('wait 2min').length).toBe(1);
  });
  it('says that a caption takes `for`, not `over` or `ease`', () => {
    const e = compileScript('caption "A" over 2');
    expect(e.errors[0]?.message).toMatch(/caption does not take `over`/);
    expect(compileScript('caption "A" ease in').errors[0]?.message).toMatch(/caption does not take `ease`/);
    expect(errs('caption "A" "B" for 2')).toEqual([]);
  });
  it('caps a loop over selection sets like a loop over elements', () => {
    const many = Array.from({ length: 3 }, (_, i) => `Set ${i}`);
    expect(errs('repeat for each set in sets\n  wait 1\nend repeat', { setNames: () => many, limits: { maxIterations: 2 } })[0]).toMatch(/at most 2 times/);
    expect(errs('repeat for each set in sets\n  wait 1\nend repeat', { setNames: () => many })).toEqual([]);
  });
});
