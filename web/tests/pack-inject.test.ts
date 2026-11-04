import { describe, expect, it } from 'vitest';
import { INJECT_BEGIN, INJECT_END, PackError, buildBoot, fromBase64, injectTemplate, injectionScript, parseArgs, scriptSafe, toBase64 } from '../tools/pack/lib.mjs';
import { resolveSelect } from '../src/plugins/boot';

const TEMPLATE = `<!doctype html><html><head><title>BIM X-ray viewer</title></head><body>
<script>
${INJECT_BEGIN}
window.__xrayEmbeddedModels = {};
${INJECT_END}
</script><script>window.__xrayEmbeddedConfig = null;</script></body></html>`;

describe('boot document', () => {
  it('contains only what was requested', () => {
    expect(buildBoot('m', parseArgs(['a.glb', '-o', 'x.html']).options)).toEqual({ model: 'm' });
  });

  it('carries every option', () => {
    const { options } = parseArgs([
      'a.glb', '-o', 'x.html', '--title', 'T', '--preset', 'p', '--select', 'g1,class:IfcWindow', '--tools', 'xray,measure',
      '--open-tool', 'measure', '--kiosk', '--camera', '1,2,3:4,5,6',
    ]);
    const params = { schema: 'xray-params/1', sightlines: { alphaMin: 0.05 } };
    expect(buildBoot('m', options, params)).toEqual({
      model: 'm', title: 'T', params, preset: 'p', camera: { position: [1, 2, 3], target: [4, 5, 6] },
      select: ['g1', 'class:IfcWindow'], tools: ['xray', 'measure'], openTool: 'measure', kiosk: true,
    });
  });
});

describe('template injection', () => {
  const models = { demo: { glb: toBase64(new Uint8Array([1, 2, 3])), json: { schema: 'xray-model/1', elements: [] } } };

  it('fills the marked block and the title, nothing else', () => {
    const out = injectTemplate(TEMPLATE, { models, boot: { model: 'demo' }, title: 'My <model> & co' });
    expect(out).toContain('<title>My &lt;model&gt; &amp; co</title>');
    expect(out).toContain('window.__xrayEmbeddedModels = {"demo":{"glb":"AQID"');
    expect(out).toContain('window.__xrayBoot = {"model":"demo"};');
    expect(out).toContain('window.__xrayEmbeddedConfig = null;');
    expect(out).not.toContain('__xrayEmbeddedModels = {};');
    expect(out.split(INJECT_BEGIN)).toHaveLength(2);
    expect(out.split(INJECT_END)).toHaveLength(2);
  });

  it('can be filled twice with the same result shape (markers survive)', () => {
    const once = injectTemplate(TEMPLATE, { models, boot: { model: 'a' }, title: 'a' });
    const twice = injectTemplate(once, { models, boot: { model: 'b' }, title: 'b' });
    expect(twice).toContain('window.__xrayBoot = {"model":"b"};');
    expect(twice).not.toContain('"model":"a"');
  });

  it('the injected script parses back to the same data', () => {
    const boot = { model: 'demo', title: 'x</script><!-- y', params: { a: [1, 2] }, select: ['class:IfcWindow'] };
    const text = injectionScript(models, boot);
    expect(text).not.toMatch(/<\/script/i);
    expect(text).not.toContain('<!--');
    const w: Record<string, unknown> = {};
    new Function('window', text)(w);
    expect(w['__xrayBoot']).toEqual(boot);
    expect(w['__xrayEmbeddedModels']).toEqual(models);
  });

  it('refuses a page without markers or title', () => {
    expect(() => injectTemplate('<title>x</title>', { models, boot: {}, title: 't' })).toThrow(PackError);
    expect(() => injectTemplate(TEMPLATE.replace(/<title>.*<\/title>/, ''), { models, boot: {}, title: 't' })).toThrow(/title/);
  });

  it('scriptSafe escapes closers, comment openers and line separators', () => {
    expect(scriptSafe('</script></SCRIPT><!--')).toBe('<\\/script><\\/SCRIPT><\\!--');
    expect(scriptSafe('a\u2028b\u2029')).toBe('a\\u2028b\\u2029');
  });
});

describe('base64', () => {
  it('round trips bytes, including views into a bigger buffer', () => {
    const all = new Uint8Array(1000).map((_, i) => (i * 37) % 256);
    expect(Array.from(fromBase64(toBase64(all)))).toEqual(Array.from(all));
    const view = all.subarray(10, 500);
    expect(Array.from(fromBase64(toBase64(view)))).toEqual(Array.from(view));
    expect(fromBase64(toBase64(new Uint8Array(0)))).toHaveLength(0);
    expect(Array.from(fromBase64(toBase64(all.buffer)))).toEqual(Array.from(all));
  });
});

describe('boot selection', () => {
  const elements = [
    { id: 0, ifcClass: 'IfcWindow' }, { id: 1, ifcClass: 'IfcWall' }, { id: 2, ifcClass: 'IfcWindow' }, { id: 3, ifcClass: 'IfcDuctSegment' },
  ];
  const byGlobalId = new Map([['g-wall', 1], ['g-duct', 3]]);

  it('maps class entries (case-insensitive) and GlobalIds, deduplicated', () => {
    expect(resolveSelect({ elements, byGlobalId }, ['class:ifcwindow', 'g-duct', 'g-duct']).ids.sort()).toEqual([0, 2, 3]);
  });

  it('reports entries that match nothing', () => {
    const r = resolveSelect({ elements, byGlobalId }, ['class:IfcBeam', 'nope', 'g-wall']);
    expect(r.ids).toEqual([1]);
    expect(r.missing).toEqual(['class:IfcBeam', 'nope']);
  });
});
