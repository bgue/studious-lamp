import { describe, expect, it } from 'vitest';
import {
  CLASS_FOLDER_KEY,
  classNameOf,
  classOf,
  controllerAltKey,
  controllerKey,
  fillEntry,
  folderKey,
  folderTitle,
  isClassFolder,
  lookupHelp,
  normalizeKey,
  renderPopover,
  type ControllerLike,
  type GuiLike,
} from '../src/ui/help';
import { HELP } from '../src/ui/helpText';

// A fake lil-gui: a folder has a title (as $title text, like lil-gui) and a parent; a controller has _name, property and a parent.
function folder(title: string, parent: GuiLike | null = null, how: '$title' | '_title' = '$title'): GuiLike {
  return how === '$title' ? { $title: { textContent: title }, parent } : { _title: title, parent };
}
function ctl(parent: GuiLike, name: string | undefined, property: string): ControllerLike {
  return { _name: name, property, parent };
}

const root = folder('X-ray');
const classification = folder('Classification (Alg 1)', root);
const styles = folder('Class styles', root);
const classes = folder('Classes', styles);
const slab = folder('IfcSlab (12)', classes);
const alias = folder('Concrete (4) [alias]', classes);
const cin = folder('Cinematic', root);
const bloom = folder('Focus bloom', cin);
const edge = folder('Host edge glow', cin);

describe('key derivation', () => {
  it('keys a folder by its title', () => {
    expect(folderKey(root)).toBe('X-ray');
    expect(folderKey(classification)).toBe('Classification (Alg 1)');
    expect(folderKey(folder('Rendering', root, '_title'))).toBe('Rendering');
    expect(folderTitle({ $title: { textContent: '  Display \n' } })).toBe('Display');
  });

  it('keys a control by the immediate parent title and the display name', () => {
    expect(controllerKey(ctl(root, 'Model', 'model'))).toBe('X-ray/Model');
    expect(controllerKey(ctl(classification, undefined, 'bufferBase'))).toBe('Classification (Alg 1)/bufferBase');
    expect(controllerKey(ctl(bloom, 'Strength', 'bloomStrength'))).toBe('Focus bloom/Strength');
    expect(controllerKey(ctl(edge, 'Strength', 'glowStrength'))).toBe('Host edge glow/Strength');
  });

  it('gives the same display name in two folders two different keys', () => {
    expect(controllerKey(ctl(bloom, 'Strength', 'a'))).not.toBe(controllerKey(ctl(edge, 'Strength', 'b')));
  });

  it('falls back to the property name when the name is empty', () => {
    expect(controllerKey(ctl(root, '', 'tiersMode'))).toBe('X-ray/tiersMode');
    expect(controllerAltKey(ctl(root, 'Tiers mode', 'tiersMode'))).toBe('X-ray/tiersMode');
    expect(controllerAltKey(ctl(root, 'tiersMode', 'tiersMode'))).toBeNull();
  });

  it('maps every per-class folder to the pattern key and fills the class name', () => {
    expect(isClassFolder(slab)).toBe(true);
    expect(isClassFolder(classes)).toBe(false);
    expect(isClassFolder(styles)).toBe(false);
    expect(folderKey(slab)).toBe(CLASS_FOLDER_KEY);
    expect(folderKey(alias)).toBe(CLASS_FOLDER_KEY);
    expect(classOf(slab)).toBe('IfcSlab');
    expect(classOf(alias)).toBe('Concrete');
    expect(classOf(classification)).toBeNull();
    expect(controllerKey(ctl(slab, 'alpha max', 'alphaMax'))).toBe('Class styles/*/alpha max');
    expect(controllerKey(ctl(slab, undefined, 'floor'))).toBe('Class styles/*/floor');
    expect(controllerKey(ctl(styles, 'Export JSON', 'export'))).toBe('Class styles/Export JSON');
  });

  it('extracts class names from folder titles', () => {
    expect(classNameOf('IfcWallStandardCase (130)')).toBe('IfcWallStandardCase');
    expect(classNameOf('Steel (3) [alias]')).toBe('Steel');
    expect(classNameOf('Plain')).toBe('Plain');
  });
});

describe('lookup', () => {
  it('finds exact keys', () => {
    expect(lookupHelp('X-ray/Model')).toBe(HELP['X-ray/Model']);
    expect(lookupHelp('Class styles/*')).toBe(HELP['Class styles/*']);
  });

  it('ignores case, spaces and punctuation as a fallback', () => {
    expect(normalizeKey('Sightlines (Alg 2)/occluder scope')).toBe(normalizeKey('Sightlines (Alg 2)/occluderScope'));
    expect(lookupHelp('Sightlines (Alg 2)/occluderScope')).toBe(HELP['Sightlines (Alg 2)/occluder scope']);
    expect(lookupHelp('Class styles/*/alphaMax')).toBe(HELP['Class styles/*/alpha max']);
    expect(lookupHelp('Sightlines (Alg 2)/layerWeighting')).toBeDefined();
  });

  it('keeps the exploded view button and its select apart', () => {
    const f = 'Exploded view (picking stays unexploded)';
    expect(lookupHelp(`${f}/Explode`)).toBe(HELP[`${f}/Explode`]);
    expect(lookupHelp(`${f}/explode`)).toBe(HELP[`${f}/explode`]);
    expect(lookupHelp(`${f}/Explode`)).not.toBe(lookupHelp(`${f}/explode`));
  });

  it('returns undefined for an unknown key', () => {
    expect(lookupHelp('Nowhere/Nothing')).toBeUndefined();
  });

  it('derives a key with a text for every control the panel builds today', () => {
    const cases: Array<[GuiLike, string | undefined, string]> = [
      [root, 'Model', 'model'], [root, 'X-ray (X)', 'xray'], [root, 'Tiers mode', 'tiersMode'],
      [classification, undefined, 'bufferBase'], [classification, undefined, 'storeyBand'],
      [slab, 'alpha min', 'alphaMin'], [slab, undefined, 'hidden'], [slab, undefined, 'color'], [slab, 'Reset this class', 'reset'],
      [bloom, 'Selective bloom', 'bloom'], [edge, 'Colour', 'glowColor'],
    ];
    for (const [parent, name, prop] of cases) {
      const key = controllerKey(ctl(parent, name, prop));
      expect(lookupHelp(key), key).toBeDefined();
    }
  });

  it('fills the class name into a pattern entry', () => {
    const e = lookupHelp('Class styles/*')!;
    const f = fillEntry(e, 'IfcSlab');
    expect(f.intent).toContain('IfcSlab');
    expect(f.intent).not.toContain('{class}');
    expect(fillEntry(e, null)).toBe(e);
  });
});

// ------------------------------------------------------------------ popover renderer, with a fake DOM

interface FakeNode {
  tag: string;
  className: string;
  textContent: string;
  children: FakeNode[];
  appendChild(n: FakeNode): FakeNode;
  append(...n: FakeNode[]): void;
}

function fakeNode(tag: string): FakeNode {
  const n: FakeNode = {
    tag,
    className: '',
    textContent: '',
    children: [],
    appendChild(c) {
      n.children.push(c);
      return c;
    },
    append(...c) {
      n.children.push(...c);
    },
  };
  // The renderer clears the element with textContent = ''.
  Object.defineProperty(n, 'textContent', {
    get: () => (n as unknown as { _t: string })._t ?? '',
    set: (v: string) => {
      (n as unknown as { _t: string })._t = v;
      if (v === '') n.children.length = 0;
    },
  });
  return n;
}

describe('popover renderer', () => {
  const doc = { createElement: (tag: string) => fakeNode(tag) } as unknown as Document;

  it('outputs the title and four labelled lines in the order Intent, Impact, Use, Ref', () => {
    const el = fakeNode('div');
    el.appendChild(fakeNode('span')); // old content must go
    const e = HELP['Sightlines (Alg 2)/layer falloff']!;
    renderPopover(doc, el as unknown as HTMLElement, 'layer falloff', e);
    expect(el.children.length).toBe(5);
    expect(el.children[0]!.className).toBe('hp-title');
    expect(el.children[0]!.textContent).toBe('layer falloff');
    const lines = el.children.slice(1);
    const label = (n: FakeNode): string => n.children[0]!.textContent;
    const text = (n: FakeNode): string => n.children[1]!.textContent;
    expect(lines.map(label)).toEqual(['Intent', 'Impact', 'Use', 'Ref']);
    expect(lines.map(text)).toEqual([e.intent, e.impact, e.use, e.ref]);
    expect(lines.map((n) => n.className)).toEqual(['hp-line hp-intent', 'hp-line hp-impact', 'hp-line hp-use', 'hp-line hp-ref']);
  });

  it('renders the same shape again without keeping the earlier lines', () => {
    const el = fakeNode('div');
    renderPopover(doc, el as unknown as HTMLElement, 'one', HELP['Display/edgeAlpha']!);
    renderPopover(doc, el as unknown as HTMLElement, 'two', fillEntry(HELP['Class styles/*']!, 'IfcWall'));
    expect(el.children.length).toBe(5);
    expect(el.children[0]!.textContent).toBe('two');
    expect(el.children[2]!.children[1]!.textContent).toContain('IfcWall');
  });
});
