// The Xray_4D property set: what goes into the IFC for an element, and how it comes back on load. The set holds the IfcLabel properties
// Location, Trade and Zone, written from the accepted assignments only. On load the properties come back as accepted assignments
// with source `property`. Pure. Tested in tests/map4d-ifcio.test.ts and tests/ifcsave-4d.test.ts.

import type { ActivityLink, Assignment, AttributeKind } from '../schedule/types';
import { ATTRIBUTES, acceptedValues, newId } from './assignments';
import type { ElementValues } from './assignments';

export const PSET_4D = 'Xray_4D';
export const PROP_NAME: Record<AttributeKind, string> = { location: 'Location', trade: 'Trade', zone: 'Zone' };

/** What the save plan writes: accepted values by GlobalId, only elements that have at least one. */
export function saveMap(list: readonly Assignment[]): Map<string, ElementValues> {
  const out = new Map<string, ElementValues>();
  for (const [g, v] of acceptedValues(list)) if (ATTRIBUTES.some((a) => v[a])) out.set(g, v);
  return out;
}

/** Accepted assignments from the `Xray_4D.*` hover properties of the model's elements (the IFC was saved by this tool before). */
export function assignmentsFromProps(elements: ReadonlyArray<{ globalId: string; props?: Record<string, string | number | boolean> }>, now: string = new Date().toISOString(), idGen: () => string = newId): Assignment[] {
  const out: Assignment[] = [];
  for (const e of elements) {
    if (!e.props) continue;
    for (const attr of ATTRIBUTES) {
      const v = e.props[`${PSET_4D}.${PROP_NAME[attr]}`];
      if (typeof v !== 'string' || !v.trim()) continue;
      out.push({ id: idGen(), element: e.globalId, attribute: attr, value: v.trim(), source: 'property', confidence: 1, reasons: [`Read from property ${PSET_4D}.${PROP_NAME[attr]} of the IFC`], status: 'accepted', created_at: now, reviewed_at: now });
    }
  }
  return out;
}

/** Records from the properties that add something: skip an attribute when an accepted record of that element and attribute already exists. */
export function newFromProps(existing: readonly Assignment[], fromProps: readonly Assignment[]): Assignment[] {
  const have = acceptedValues(existing);
  return fromProps.filter((a) => have.get(a.element)?.[a.attribute] === undefined);
}

// ---------------------------------------------------------------- ActivityIds (schedule links in the same property set)

export const ACTIVITY_IDS = 'ActivityIds';
/** The property the linker reads the task codes from when a saved model is opened again (`LinkOptions.idProperty`): links with source `property`. */
export const ACTIVITY_IDS_PROPERTY = `${PSET_4D}.${ACTIVITY_IDS}`;

/** GlobalId -> comma-separated task codes of the accepted build links that name the element: the `Xray_4D.ActivityIds` text. */
export function activityIdsMap(links: readonly ActivityLink[] | undefined): Map<string, string> {
  const by = new Map<string, string[]>();
  for (const l of links ?? []) {
    if (l.status !== 'accepted' || l.role !== 'build' || /[,;]/.test(l.activity)) continue;
    for (const g of l.elements) {
      const list = by.get(g) ?? [];
      if (!list.includes(l.activity)) list.push(l.activity);
      by.set(g, list);
    }
  }
  return new Map([...by].map(([g, codes]) => [g, codes.sort().join(',')] as const));
}

/** The values the save plan writes: the accepted assignments plus the activity ids. Elements that have neither are left out. */
export function saveMapWithLinks(list: readonly Assignment[], links: readonly ActivityLink[] | undefined): Map<string, ElementValues & { activityIds?: string }> {
  const out: Map<string, ElementValues & { activityIds?: string }> = saveMap(list);
  for (const [g, ids] of activityIdsMap(links)) out.set(g, { ...(out.get(g) ?? {}), activityIds: ids });
  return out;
}
