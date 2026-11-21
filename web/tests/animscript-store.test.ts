import { describe, expect, it } from 'vitest';
import { ANIM_STORAGE_PREFIX, MAX_FILE_CHARS, cleanName, emptyDoc, exportFileName, exportText, findScript, importText, loadDoc, removeScript, saveDoc, storageKeyFor, uniqueScriptName, upsertScript } from '../src/anim/scriptStore';
import { MemoryStorage } from '../src/selectionSets';
import { highlightLine, markPieces } from '../src/anim/script/highlight';
import { flattenPaths } from '../src/plugins/animScript';

describe('script store', () => {
  it('keys scripts by the model identity', () => {
    expect(storageKeyFor('haus|12|abc')).toBe(`${ANIM_STORAGE_PREFIX}haus|12|abc`);
  });
  it('saves, loads, replaces by name without regard to case, sorts and removes', () => {
    const st = new MemoryStorage();
    let d = emptyDoc();
    d = upsertScript(d, 'Walk', 'wait 1', 5);
    d = upsertScript(d, 'Alpha', 'wait 2', 6);
    d = upsertScript(d, 'walk', 'wait 3', 7);
    expect(d.scripts.map((s) => [s.name, s.text])).toEqual([['Alpha', 'wait 2'], ['walk', 'wait 3']]);
    expect(saveDoc(st, 'm', d)).toBe(true);
    expect(loadDoc(st, 'm').scripts).toEqual(d.scripts);
    expect(loadDoc(st, 'other').scripts).toEqual([]);
    expect(findScript(d, ' ALPHA ')?.text).toBe('wait 2');
    expect(removeScript(d, 'alpha').scripts.map((s) => s.name)).toEqual(['walk']);
  });
  it('keeps the draft and ignores a corrupt or foreign value', () => {
    const st = new MemoryStorage();
    saveDoc(st, 'm', { ...emptyDoc(), draft: { name: 'x', text: 'wait 1' } });
    expect(loadDoc(st, 'm').draft).toEqual({ name: 'x', text: 'wait 1' });
    for (const bad of ['', '{', 'null', '[]', '{"version":2,"scripts":[]}', '{"version":1,"scripts":[{"name":1}]}']) {
      st.setItem(storageKeyFor('b'), bad);
      expect(loadDoc(st, 'b').scripts).toEqual([]);
    }
  });
  it('survives a storage that throws and a missing storage', () => {
    const bad = { getItem: () => { throw new Error('no'); }, setItem: () => { throw new Error('no'); } };
    expect(loadDoc(bad, 'm')).toEqual(emptyDoc());
    expect(saveDoc(bad, 'm', emptyDoc())).toBe(false);
    expect(saveDoc(null, 'm', emptyDoc())).toBe(false);
    expect(loadDoc(null, 'm')).toEqual(emptyDoc());
  });
  it('cleans and numbers names', () => {
    expect(cleanName('  a\n b\t c  ')).toBe('a b c');
    expect(cleanName('x'.repeat(200)).length).toBe(60);
    let d = upsertScript(emptyDoc(), 'Walk', '');
    expect(uniqueScriptName(d, 'Walk')).toBe('Walk 2');
    d = upsertScript(d, 'Walk 2', '');
    expect(uniqueScriptName(d, 'walk')).toBe('walk 3');
    expect(uniqueScriptName(d, '')).toBe('Script');
    expect(upsertScript(d, '   ', 'x')).toBe(d);
  });
});

describe('.xrayanim files', () => {
  it('exports the script text itself with one final newline and a safe name', () => {
    expect(exportText('wait 1\r\nwait 2')).toBe('wait 1\nwait 2\n');
    expect(exportText('wait 1\n')).toBe('wait 1\n');
    expect(exportFileName('A/B: "C"')).toBe('A-B- -C-.xrayanim'.replace(' -', ' -'));
    expect(exportFileName('')).toBe('script.xrayanim');
  });
  it('imports a file: name from the file name, no BOM, \\n line ends', () => {
    expect(importText('C:\\x\\Pump walk.xrayanim', '\uFEFFwait 1\r\nwait 2')).toEqual({ name: 'Pump walk', text: 'wait 1\nwait 2' });
    expect(importText('notes.txt', 'wait 1')).toMatchObject({ name: 'notes' });
    expect(importText('', 'x')).toMatchObject({ name: 'Imported script' });
  });
  it('refuses a huge or binary file', () => {
    expect(importText('a.xrayanim', 'x'.repeat(MAX_FILE_CHARS + 1))).toHaveProperty('error');
    expect(importText('a.xrayanim', 'a\u0000b')).toHaveProperty('error');
  });
  it('an export reads back as the same script', () => {
    const text = 'mode ghost\nfly to class IfcPump over 3 seconds\n';
    const r = importText(exportFileName('T'), exportText(text));
    expect('text' in r && r.text).toBe(text);
  });
});

describe('highlighting', () => {
  it('colours the statement word, options, text, numbers and comments', () => {
    const p = highlightLine('fly to class IfcPump over 3 seconds -- go');
    const cls = (t: string) => p.find((x) => x.text === t)?.cls;
    expect(cls('fly')).toBe('kw');
    expect(cls('to')).toBe('opt');
    expect(cls('class')).toBe('el');
    expect(cls('3')).toBe('num');
    expect(cls('-- go')).toBe('com');
    expect(highlightLine('caption "a b"')[2]).toMatchObject({ cls: 'str', text: '"a b"' });
    expect(p.map((x) => x.text).join('')).toBe('fly to class IfcPump over 3 seconds -- go');
  });
  it('keeps every character, also for odd lines', () => {
    for (const s of ['', '   ', '"open', '###', 'a.b.c 1.5.2', '€ ~ ^', 'where a<=3 and b!="x"']) expect(highlightLine(s).map((x) => x.text).join('')).toBe(s);
  });
  it('marks the columns of a diagnostic and splits pieces at its edges', () => {
    const pieces = markPieces(highlightLine('show everything fade over 2'), [{ severity: 'error', line: 1, col: 17, end: 21, message: 'x' }]);
    expect(pieces.map((x) => x.text).join('')).toBe('show everything fade over 2');
    expect(pieces.filter((x) => x.mark).map((x) => x.text).join('')).toBe('fade');
  });
});

describe('settings paths of the app', () => {
  it('flattens a params document to its settings, leaving out the user data tables', () => {
    const doc = { schema: 'x', model: 'm', xray: true, display: { edgeAlpha: 0.8, inFront: true }, cinematic: { glowStrength: 1, tint: [1, 0, 0], nested: { a: 2 } }, classStyles: { IfcWall: { alphaMax: 1 } }, camera: { position: [1, 2, 3] } };
    expect(flattenPaths(doc).sort()).toEqual(['cinematic.glowStrength', 'cinematic.nested.a', 'cinematic.tint', 'display.edgeAlpha', 'display.inFront', 'xray']);
  });
});
