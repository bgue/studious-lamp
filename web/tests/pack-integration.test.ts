import { mkdtempSync, readFileSync, rmSync, writeFileSync, existsSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { INJECT_BEGIN, INJECT_END, fromBase64 } from '../tools/pack/lib.mjs';
import { run } from '../tools/xray-pack.mjs';

const web = resolve(dirname(fileURLToPath(import.meta.url)), '..');
let dir = '';
const io = { out: () => undefined, err: (s: string) => errors.push(s) };
const errors: string[] = [];

beforeAll(() => {
  dir = mkdtempSync(join(tmpdir(), 'xray-pack-test-'));
  // a stand-in template (the real one is a 1 MB bundle built by build-single-file.mjs --template)
  writeFileSync(join(dir, 'template.html'), `<html><head><title>BIM X-ray viewer</title></head><body><script>\n${INJECT_BEGIN}\nwindow.__xrayEmbeddedModels = {};\n${INJECT_END}\n</script></body></html>`);
  process.env['XRAY_PACK_TEMPLATE'] = join(dir, 'template.html');
});
afterAll(() => {
  delete process.env['XRAY_PACK_TEMPLATE'];
  rmSync(dir, { recursive: true, force: true });
});

function evalInjected(html: string): { models: Record<string, { glb: string; json?: { elements: unknown[] } }>; boot: Record<string, unknown> } {
  const m = /\/\* XRAY-PACK:INJECT-BEGIN \*\/([\s\S]*?)\/\* XRAY-PACK:INJECT-END \*\//.exec(html);
  expect(m).not.toBeNull();
  const w: Record<string, unknown> = {};
  new Function('window', m![1]!)(w);
  return { models: w['__xrayEmbeddedModels'] as never, boot: w['__xrayBoot'] as never };
}

describe('xray-pack end to end (glb)', () => {
  it('packs building.glb + building.json with options', async () => {
    const out = join(dir, 'building.html');
    const params = join(dir, 'p.json');
    writeFileSync(params, JSON.stringify({ schema: 'xray-params/1', sightlines: { alphaMin: 0.05 } }));
    const code = await run([
      join(web, 'public/models/building.glb'), '-o', out, '--params', params, '--select', 'class:IfcDuctSegment', '--title', 'Test',
      '--tools', 'xray,measure', '--open-tool', 'measure', '--kiosk', '--quiet',
    ], io);
    expect(code).toBe(0);
    const html = readFileSync(out, 'utf8');
    expect(html).toContain('<title>Test</title>');
    const { models, boot } = evalInjected(html);
    expect(Object.keys(models)).toEqual(['building']);
    const glb = fromBase64(models['building']!.glb);
    expect(new DataView(glb.buffer, glb.byteOffset).getUint32(0, true)).toBe(0x46546c67);
    const orig = readFileSync(join(web, 'public/models/building.glb'));
    expect(glb.length === orig.length && glb.every((b, i) => b === orig[i])).toBe(true);
    expect(models['building']!.json!.elements).toHaveLength(26);
    expect(boot).toEqual({
      model: 'building', title: 'Test', params: { schema: 'xray-params/1', sightlines: { alphaMin: 0.05 } },
      select: ['class:IfcDuctSegment'], tools: ['xray', 'measure'], openTool: 'measure', kiosk: true,
    });
  });

  it('refuses to overwrite without --force and reports input errors with exit code 2', async () => {
    const out = join(dir, 'building.html');
    expect(existsSync(out)).toBe(true);
    await expect(run([join(web, 'public/models/building.glb'), '-o', out, '--quiet'], io)).rejects.toMatchObject({ code: 1 });
    await expect(run([join(dir, 'missing.glb'), '-o', join(dir, 'x.html')], io)).rejects.toMatchObject({ code: 2 });
    writeFileSync(join(dir, 'bad.json'), '{nope');
    await expect(run([join(web, 'public/models/building.glb'), '-o', join(dir, 'y.html'), '--params', join(dir, 'bad.json')], io)).rejects.toMatchObject({ code: 2 });
    writeFileSync(join(dir, 'bad.glb'), 'not a glb at all');
    await expect(run([join(dir, 'bad.glb'), '-o', join(dir, 'z.html')], io)).rejects.toMatchObject({ code: 2 });
  });

  it('--samples adds the sample models after the packed one', async () => {
    const out = join(dir, 'samples.html');
    await run([join(web, 'public/models/building.glb'), '-o', out, '--samples', '--name', 'mine', '--quiet'], io);
    expect(Object.keys(evalInjected(readFileSync(out, 'utf8')).models)).toEqual(['mine', 'building', 'fzk-haus', 'plumbing']);
  });

  it('--help prints the usage and exits 0', async () => {
    const lines: string[] = [];
    expect(await run(['--help'], { out: (s: string) => lines.push(s), err: () => undefined })).toBe(0);
    expect(lines.join('\n')).toMatch(/Usage:[\s\S]*--ifc-reader/);
  });
});

describe('xray-pack end to end (ifc)', () => {
  it('converts an IFC with the browser reader code', async () => {
    const out = join(dir, 'fzk.html');
    const code = await run([resolve(web, '../models/AC20-FZK-Haus.ifc'), '-o', out, '--quiet'], io);
    expect(code).toBe(0);
    const { models, boot } = evalInjected(readFileSync(out, 'utf8'));
    expect(boot).toEqual({ model: 'AC20-FZK-Haus' });
    expect(models['AC20-FZK-Haus']!.json!.elements).toHaveLength(82);
  }, 120000);
});
