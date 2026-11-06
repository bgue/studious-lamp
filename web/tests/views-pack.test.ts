// xray-pack --views / --open-view: argument rules, views document checks, boot document and template injection.
import { describe, expect, it } from 'vitest';
import { INJECT_BEGIN, INJECT_END, PackError, buildBoot, checkViews, injectTemplate, parseArgs } from '../tools/pack/lib.mjs';
import { parseViewsDocument } from '../src/views/model';

const cam = { position: [10, 8, 10], target: [0, 1, 0], up: [0, 1, 0], fov: 50, ortho: false };
const doc = {
  schema: 'xray-views/1',
  model: 'fzk',
  views: [
    { id: 'a', name: 'Entrance', camera: cam, selection: ['G1'], params: { xray: true } },
    { id: 'b', name: 'Roof cut', camera: cam, selection: [], params: { section: { plane: { enabled: true } } } },
  ],
};

const usage = (argv: string[]): string => {
  try {
    parseArgs(argv);
  } catch (e) {
    expect(e).toBeInstanceOf(PackError);
    return (e as PackError).message;
  }
  throw new Error('expected a usage error');
};

describe('xray-pack saved views', () => {
  it('parses --views and --open-view; --open-view needs --views', () => {
    const { options } = parseArgs(['m.glb', '-o', 'o.html', '--views', 'v.json', '--open-view', 'Roof cut']);
    expect(options).toMatchObject({ views: 'v.json', openView: 'Roof cut' });
    expect(usage(['m.glb', '-o', 'o.html', '--open-view', 'x'])).toMatch(/needs --views/);
    expect(usage(['m.glb', '-o', 'o.html', '--views', 'v.json', '--open-view', ' '])).toMatch(/must not be empty/);
  });

  it('checks the views document and the --open-view entry like the viewer finds views', () => {
    expect(checkViews(doc, 'Roof cut', 'fzk').views).toHaveLength(2);
    expect(checkViews(doc, 'roof CUT').warnings).toEqual([]);
    expect(checkViews(doc, 'b').views).toHaveLength(2);
    expect(checkViews(doc, '1').views).toHaveLength(2);
    expect(checkViews(doc.views).views).toHaveLength(2);
    expect(checkViews({ schema: 'xray-view/1', model: 'fzk', view: doc.views[0] }).views).toHaveLength(1);
    expect(checkViews(doc, undefined, 'other').warnings[0]).toMatch(/saved on model "fzk"/);
    const partly = checkViews({ ...doc, views: [...doc.views, { name: 'No camera' }, { camera: cam }] });
    expect(partly.views).toHaveLength(2);
    expect(partly.warnings).toHaveLength(2);
    expect(() => checkViews(doc, 'Nope')).toThrow(/not in the views file/);
    expect(() => checkViews({ schema: 'xray-params/1' })).toThrow(/not a saved views document/);
    expect(() => checkViews({ schema: 'xray-views/1', views: [{ name: 'x' }] })).toThrow(/no usable view/);
    try {
      checkViews({ schema: 'xray-params/1' });
    } catch (e) {
      expect((e as PackError).code).toBe(2);
    }
  });

  it('puts views and openView into the boot document, and the page reads them back', () => {
    const { options } = parseArgs(['m.glb', '-o', 'o.html', '--views', 'v.json', '--open-view', 'Roof cut']);
    const { views } = checkViews(doc, options.openView, 'fzk');
    const boot = buildBoot('fzk', options, undefined, views);
    expect(boot).toEqual({ model: 'fzk', views: { schema: 'xray-views/1', model: 'fzk', views }, openView: 'Roof cut' });
    expect(parseViewsDocument(boot['views']).views.map((v) => v.name)).toEqual(['Entrance', 'Roof cut']);
    expect(buildBoot('fzk', parseArgs(['m.glb', '-o', 'o.html']).options)).toEqual({ model: 'fzk' });
  });

  it('injects the views into the template script safely', () => {
    const tpl = `<html><head><title>t</title></head><body><script>${INJECT_BEGIN}${INJECT_END}</script></body></html>`;
    const evil = { ...doc, views: [{ ...doc.views[0], name: 'Bad </script><script>alert(1)</script>' }] };
    const { views } = checkViews(evil);
    const html = injectTemplate(tpl, { models: {}, boot: buildBoot('fzk', { openView: '1' }, undefined, views), title: 'T' });
    expect(html.match(/<\/script>/g)).toHaveLength(1);
    const script = html.slice(html.indexOf(INJECT_BEGIN) + INJECT_BEGIN.length, html.indexOf(INJECT_END));
    const win: Record<string, unknown> = {};
    new Function('window', script)(win);
    const boot = win['__xrayBoot'] as { views: unknown; openView: string };
    expect(boot.openView).toBe('1');
    expect(parseViewsDocument(boot.views).views[0]!.name).toBe('Bad </script><script>alert(1)</script>');
  });
});
