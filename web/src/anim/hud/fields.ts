// Label fields: what a label cue shows for an element. Pure (no DOM, no three.js).
//
// Fields: name, class, storey, material, globalid, type, or a property key "Pset_WallCommon.FireRating" (the keys of the
// element `props`, see src/model/ifcProps.ts; the hover card reads the same). A field without a value is left out.

import { formatValue, propLabel } from '../../ui/hoverCard';
import type { PropValue } from '../../ui/hoverCard';

export interface HudElement {
  name?: string;
  ifcClass: string;
  /** Name of the storey. */
  storey?: string;
  material?: string;
  globalId: string;
  props?: Readonly<Record<string, PropValue>>;
}

export const DEFAULT_LABEL_FIELDS: readonly string[] = ['name', 'class', 'storey'];
export const MAX_LABEL_FIELDS = 8;

/** A list of field names from text: split at commas, quotes and spaces around the names dropped, duplicates removed. */
export function parseFieldList(text: string): string[] {
  const out: string[] = [];
  for (const raw of text.split(',')) {
    const f = raw.trim().replace(/^["']|["']$/g, '').trim();
    if (!f || f.length > 80) continue;
    const norm = ['name', 'class', 'storey', 'material', 'globalid', 'type'].includes(f.toLowerCase()) ? f.toLowerCase() : f;
    if (!out.includes(norm)) out.push(norm);
    if (out.length >= MAX_LABEL_FIELDS) break;
  }
  return out;
}

function prop(el: HudElement, key: string): PropValue | undefined {
  const p = el.props;
  if (!p) return undefined;
  if (key in p) return p[key];
  const want = key.toLowerCase();
  for (const k of Object.keys(p)) if (k.toLowerCase() === want) return p[k];
  return undefined;
}

/** The value of one field as text, or '' when the element has none. */
export function fieldText(el: HudElement, field: string): string {
  switch (field.toLowerCase()) {
    case 'name':
      return (el.name ?? '').trim();
    case 'class':
      return el.ifcClass;
    case 'storey':
      return (el.storey ?? '').trim();
    case 'material':
      return (el.material ?? '').trim();
    case 'globalid':
      return el.globalId;
    case 'type': {
      const v = prop(el, 'Attr.PredefinedType') ?? prop(el, 'Attr.ObjectType');
      return v === undefined ? '' : formatValue(v);
    }
    default: {
      const v = prop(el, field);
      return v === undefined ? '' : formatValue(v);
    }
  }
}

/** The lines of a tag: the value of each built-in field, `Prop: value` for a property. The first line is the title. Never empty. */
export function labelLines(el: HudElement, fields: readonly string[]): string[] {
  const lines: string[] = [];
  const list = fields.length > 0 ? fields : DEFAULT_LABEL_FIELDS;
  for (const f of list) {
    const v = fieldText(el, f);
    if (!v) continue;
    const builtin = ['name', 'class', 'storey', 'material', 'globalid'].includes(f.toLowerCase());
    lines.push(builtin ? v : f.toLowerCase() === 'type' ? `Type: ${v}` : `${propLabel(f)}: ${v}`);
  }
  if (lines.length === 0) lines.push(el.name?.trim() || el.ifcClass);
  return lines;
}
