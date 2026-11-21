// The known values of the three attributes (the lists the mapping tool offers), their colours, and the class-to-trade table the
// suggestions use. Pure. Tested in tests/map4d-values.test.ts and tests/map4d-suggest.test.ts.

import type { Assignment, AttributeKind } from '../schedule/types';
import { ATTRIBUTES } from './assignments';

export interface ValueDef { name: string; colour?: string }
export type ValueLists = Record<AttributeKind, ValueDef[]>;

export const DEFAULT_TRADES: readonly string[] = ['CONC', 'STEEL', 'MASONRY', 'FACADE', 'ROOF', 'MEP-MECH', 'MEP-ELEC', 'MEP-PLUMB', 'FINISHES', 'SITE'];

/** A distinct colour for the n-th value (golden-angle hue steps), as #rrggbb. */
export function paletteColour(n: number): string {
  const h = ((n * 137.508) % 360) / 360;
  const s = 0.55;
  const l = 0.58;
  const a = s * Math.min(l, 1 - l);
  const f = (k0: number): number => {
    const k = (k0 + h * 12) % 12;
    return l - a * Math.max(-1, Math.min(k - 3, 9 - k, 1));
  };
  return '#' + [f(0), f(8), f(4)].map((v) => Math.round(v * 255).toString(16).padStart(2, '0')).join('');
}

export const emptyLists = (): ValueLists => ({ location: [], trade: [], zone: [] });

export function defaultLists(): ValueLists {
  const l = emptyLists();
  l.trade = DEFAULT_TRADES.map((name, i) => ({ name, colour: paletteColour(i) }));
  return l;
}

export const copyLists = (l: ValueLists): ValueLists => ({ location: l.location.map((v) => ({ ...v })), trade: l.trade.map((v) => ({ ...v })), zone: l.zone.map((v) => ({ ...v })) });

/** The text of a value as stored: trimmed, inner whitespace collapsed, at most 255 characters (IfcLabel). Empty when nothing is left. */
export const cleanValue = (s: string): string => s.replace(/\s+/g, ' ').trim().slice(0, 255);

export function addValue(l: ValueLists, attr: AttributeKind, name: string): { lists: ValueLists; added: boolean; name: string } {
  const n = cleanValue(name);
  if (!n || l[attr].some((v) => v.name === n)) return { lists: l, added: false, name: n };
  const lists = copyLists(l);
  lists[attr].push({ name: n, colour: paletteColour(lists[attr].length) });
  return { lists, added: true, name: n };
}

/** Rename a value. False when the new name is empty or already used by another value. */
export function renameInList(l: ValueLists, attr: AttributeKind, from: string, to: string): { lists: ValueLists; ok: boolean } {
  const n = cleanValue(to);
  if (!n || (n !== from && l[attr].some((v) => v.name === n))) return { lists: l, ok: false };
  const lists = copyLists(l);
  const v = lists[attr].find((x) => x.name === from);
  if (!v) return { lists: l, ok: false };
  v.name = n;
  return { lists, ok: true };
}

export function removeFromList(l: ValueLists, attr: AttributeKind, name: string): ValueLists {
  const lists = copyLists(l);
  lists[attr] = lists[attr].filter((v) => v.name !== name);
  return lists;
}

export function setColour(l: ValueLists, attr: AttributeKind, name: string, colour: string): ValueLists {
  const lists = copyLists(l);
  const v = lists[attr].find((x) => x.name === name);
  if (v && /^#[0-9a-f]{6}$/i.test(colour)) v.colour = colour.toLowerCase();
  return lists;
}

/** The list plus any value that assignments use but the list does not hold (an import brings new values), in list order first. */
export function knownValues(l: ValueLists, list: readonly Assignment[], attr: AttributeKind): ValueDef[] {
  const out = l[attr].map((v) => ({ ...v }));
  const have = new Set(out.map((v) => v.name));
  const extra = new Set<string>();
  for (const a of list) if (a.attribute === attr && a.status === 'accepted' && !have.has(a.value)) extra.add(a.value);
  for (const name of [...extra].sort()) out.push({ name, colour: paletteColour(out.length) });
  return out;
}

/** Put every value the assignments use into the list (after an import or a read-back from the IFC). */
export function absorb(l: ValueLists, list: readonly Assignment[]): ValueLists {
  let lists = l;
  for (const attr of ATTRIBUTES) for (const v of knownValues(lists, list, attr)) lists = addValue(lists, attr, v.name).lists;
  return lists;
}

/** The colour of a value: the listed one, else a palette colour by position. */
export function colourOf(l: ValueLists, attr: AttributeKind, name: string): string {
  const i = l[attr].findIndex((v) => v.name === name);
  return (i >= 0 ? l[attr][i]!.colour : undefined) ?? paletteColour(i >= 0 ? i : 3 + [...name].reduce((a, c) => (a * 31 + c.charCodeAt(0)) >>> 0, 7) % 97);
}

export const hexToRgb = (hex: string): [number, number, number] => [0, 2, 4].map((i) => parseInt(hex.slice(1 + i, 3 + i), 16) / 255) as [number, number, number];

// ---------------------------------------------------------------- suggestion tables

/**
 * IFC class to trade. A key `Class:text` also needs the material name to contain the text (case-insensitive) and wins over the bare class.
 * Defaults only: the 4D tab edits a copy per model.
 */
export const DEFAULT_CLASS_TRADE: Readonly<Record<string, string>> = {
  IfcFooting: 'CONC', IfcPile: 'CONC', IfcSlab: 'CONC', IfcColumn: 'CONC', IfcBeam: 'CONC', IfcStair: 'CONC', IfcStairFlight: 'CONC', IfcRamp: 'CONC', IfcRampFlight: 'CONC',
  'IfcBeam:steel': 'STEEL', 'IfcColumn:steel': 'STEEL', IfcMember: 'STEEL', IfcRailing: 'STEEL',
  IfcWall: 'MASONRY', IfcWallStandardCase: 'MASONRY', 'IfcWall:concrete': 'CONC', 'IfcWallStandardCase:concrete': 'CONC',
  IfcCurtainWall: 'FACADE', IfcWindow: 'FACADE', IfcPlate: 'FACADE', IfcRoof: 'ROOF',
  IfcDoor: 'FINISHES', IfcCovering: 'FINISHES', IfcFurnishingElement: 'FINISHES', IfcFurniture: 'FINISHES', IfcSystemFurnitureElement: 'FINISHES',
  IfcDuctSegment: 'MEP-MECH', IfcDuctFitting: 'MEP-MECH', IfcDuctSilencer: 'MEP-MECH', IfcAirTerminal: 'MEP-MECH', IfcAirTerminalBox: 'MEP-MECH', IfcFan: 'MEP-MECH',
  IfcBoiler: 'MEP-MECH', IfcChiller: 'MEP-MECH', IfcUnitaryEquipment: 'MEP-MECH', IfcSpaceHeater: 'MEP-MECH', IfcCoil: 'MEP-MECH', IfcDamper: 'MEP-MECH', IfcHeatExchanger: 'MEP-MECH', IfcTransportElement: 'MEP-MECH',
  IfcPipeSegment: 'MEP-PLUMB', IfcPipeFitting: 'MEP-PLUMB', IfcSanitaryTerminal: 'MEP-PLUMB', IfcValve: 'MEP-PLUMB', IfcPump: 'MEP-PLUMB', IfcTank: 'MEP-PLUMB', IfcWasteTerminal: 'MEP-PLUMB', IfcFireSuppressionTerminal: 'MEP-PLUMB',
  IfcCableCarrierSegment: 'MEP-ELEC', IfcCableCarrierFitting: 'MEP-ELEC', IfcCableSegment: 'MEP-ELEC', IfcCableFitting: 'MEP-ELEC', IfcLightFixture: 'MEP-ELEC', IfcElectricDistributionBoard: 'MEP-ELEC',
  IfcElectricAppliance: 'MEP-ELEC', IfcOutlet: 'MEP-ELEC', IfcSwitchingDevice: 'MEP-ELEC', IfcJunctionBox: 'MEP-ELEC', IfcLamp: 'MEP-ELEC', IfcTransformer: 'MEP-ELEC', IfcSensor: 'MEP-ELEC',
  IfcGeographicElement: 'SITE', IfcCivilElement: 'SITE',
};

/** The classifier's discipline codes (default schema) to trade. */
export const DISCIPLINE_TRADE: Readonly<Record<string, string>> = {
  ARC: 'FINISHES', STR: 'CONC', MEC: 'MEP-MECH', PLB: 'MEP-PLUMB', FPR: 'MEP-PLUMB', ELE: 'MEP-ELEC', TEL: 'MEP-ELEC', CIV: 'SITE', PIP: 'MEP-PLUMB', INS: 'MEP-MECH',
};

/** MasterFormat division (two digits) to trade. */
export const DIVISION_TRADE: Readonly<Record<string, string>> = {
  '02': 'SITE', '03': 'CONC', '04': 'MASONRY', '05': 'STEEL', '07': 'ROOF', '08': 'FACADE', '09': 'FINISHES', '10': 'FINISHES', '12': 'FINISHES',
  '21': 'MEP-PLUMB', '22': 'MEP-PLUMB', '23': 'MEP-MECH', '26': 'MEP-ELEC', '27': 'MEP-ELEC', '28': 'MEP-ELEC', '31': 'SITE', '32': 'SITE', '33': 'SITE',
};
