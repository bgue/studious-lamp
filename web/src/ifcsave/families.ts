// Schema families and the entity templates of the additions block (design 1.5, 1.6). Text only.

import { LIST, NULLTXT, REF, cutChars, entityLine, stepReal, stepString } from './stepText';

export type SchemaFamily = '2x3' | '4' | '4x3';

/** IFC2X3* -> 2x3; IFC4X3* -> 4x3; other IFC4* -> 4; anything else (IFC2X2, unknown) -> null: not supported. */
export function familyOf(schema: string | null | undefined): SchemaFamily | null {
  const s = (schema ?? '').trim().toUpperCase();
  if (/^IFC2X3/.test(s)) return '2x3';
  if (/^IFC4X3/.test(s)) return '4x3';
  if (/^IFC4(?!X)/.test(s)) return '4';
  return null;
}

/** IFC types that Xray writes as property values. */
export type ValueType = 'IfcLabel' | 'IfcText' | 'IfcIdentifier' | 'IfcBoolean' | 'IfcNormalisedRatioMeasure' | 'IfcDateTime';

export interface PropSpec {
  name: string;
  type: ValueType;
  value: string | number | boolean;
}

/** A typed value as it appears in a property line: IFCLABEL('x'), IFCBOOLEAN(.T.), IFCNORMALISEDRATIOMEASURE(0.5). */
export function typedValue(p: PropSpec): string {
  switch (p.type) {
    case 'IfcLabel':
      return `IFCLABEL(${stepString(cutChars(String(p.value), 255))})`;
    case 'IfcIdentifier':
      return `IFCIDENTIFIER(${stepString(cutChars(String(p.value), 255))})`;
    case 'IfcText':
      return `IFCTEXT(${stepString(String(p.value))})`;
    case 'IfcDateTime':
      return `IFCDATETIME(${stepString(String(p.value))})`;
    case 'IfcBoolean':
      return `IFCBOOLEAN(${p.value ? '.T.' : '.F.'})`;
    case 'IfcNormalisedRatioMeasure':
      return `IFCNORMALISEDRATIOMEASURE(${stepReal(Math.min(1, Math.max(0, Number(p.value))))})`;
  }
}

/** The type to use for a timestamp: IfcDateTime where the schema has it, else an IfcLabel with the same text. */
export const dateType = (f: SchemaFamily): ValueType => (f === '2x3' ? 'IfcLabel' : 'IfcDateTime');

export interface ClassificationText {
  source: string;
  edition: string;
  /** YYYY-MM-DD, IFC4 and later only. */
  editionDate?: string;
  name: string;
  location?: string;
}

const label = (s: string): string => stepString(cutChars(s, 255));
const opt = (s: string | undefined): string => (s ? label(s) : NULLTXT);

/** 2X3: (Source, Edition, EditionDate, Name). IFC4+: (Source, Edition, EditionDate, Name, Description, Location, ReferenceTokens). */
export function classificationLine(f: SchemaFamily, id: number, c: ClassificationText): string {
  if (f === '2x3') return entityLine(id, 'IFCCLASSIFICATION', [label(c.source), label(c.edition), NULLTXT, label(c.name)]);
  return entityLine(id, 'IFCCLASSIFICATION', [label(c.source), label(c.edition), c.editionDate ? stepString(c.editionDate) : NULLTXT, label(c.name), NULLTXT, opt(c.location), NULLTXT]);
}

/**
 * 2X3: (Location, ItemReference, Name, ReferencedSource): no hierarchy, so `parent` is ignored (the code is made unique by the caller).
 * IFC4+: (Location, Identification, Name, ReferencedSource, Description, Sort), where ReferencedSource is the classification or the parent reference.
 */
export function classificationReferenceLine(f: SchemaFamily, id: number, code: string, name: string, classification: number, parent: number | null): string {
  if (f === '2x3') return entityLine(id, 'IFCCLASSIFICATIONREFERENCE', [NULLTXT, label(code), label(name), REF(classification)]);
  return entityLine(id, 'IFCCLASSIFICATIONREFERENCE', [NULLTXT, label(code), label(name), REF(parent ?? classification), NULLTXT, NULLTXT]);
}

/** (GlobalId, OwnerHistory, Name, Description, RelatedObjects, RelatingClassification). OwnerHistory is `$` from IFC4 on. */
export function relAssociatesClassificationLine(f: SchemaFamily, id: number, guid: string, ownerHistory: number | null, name: string, objects: readonly number[], classRef: number): string {
  return entityLine(id, 'IFCRELASSOCIATESCLASSIFICATION', [stepString(guid), ownerRef(f, ownerHistory), label(name), NULLTXT, LIST(objects.map(REF)), REF(classRef)]);
}

/** (Name, Description, NominalValue, Unit) in every family. */
export const propertySingleValueLine = (id: number, p: PropSpec): string => entityLine(id, 'IFCPROPERTYSINGLEVALUE', [label(p.name), NULLTXT, typedValue(p), NULLTXT]);

/** (GlobalId, OwnerHistory, Name, Description, HasProperties). */
export function propertySetLine(f: SchemaFamily, id: number, guid: string, ownerHistory: number | null, name: string, props: readonly number[]): string {
  return entityLine(id, 'IFCPROPERTYSET', [stepString(guid), ownerRef(f, ownerHistory), label(name), NULLTXT, LIST(props.map(REF))]);
}

/** (GlobalId, OwnerHistory, Name, Description, RelatedObjects, RelatingPropertyDefinition). */
export function relDefinesByPropertiesLine(f: SchemaFamily, id: number, guid: string, ownerHistory: number | null, name: string, objects: readonly number[], pset: number): string {
  return entityLine(id, 'IFCRELDEFINESBYPROPERTIES', [stepString(guid), ownerRef(f, ownerHistory), label(name), NULLTXT, LIST(objects.map(REF)), REF(pset)]);
}

const ownerRef = (f: SchemaFamily, ownerHistory: number | null): string => (f === '2x3' && ownerHistory !== null ? REF(ownerHistory) : NULLTXT);

/**
 * A minimal owner history for an IFC2X3 file that has none (Person, Organization, PersonAndOrganization, Application, OwnerHistory).
 * `first` is the first express id used; the owner history is `first + 4`.
 */
export function ownerHistoryChain(first: number, version: string): string[] {
  return [
    entityLine(first, 'IFCPERSON', [NULLTXT, label('Unknown'), NULLTXT, NULLTXT, NULLTXT, NULLTXT, NULLTXT, NULLTXT]),
    entityLine(first + 1, 'IFCORGANIZATION', [NULLTXT, label('Unknown'), NULLTXT, NULLTXT, NULLTXT]),
    entityLine(first + 2, 'IFCPERSONANDORGANIZATION', [REF(first), REF(first + 1), NULLTXT]),
    entityLine(first + 3, 'IFCAPPLICATION', [REF(first + 1), label(version), label('Xray viewer'), label('xray')]),
    entityLine(first + 4, 'IFCOWNERHISTORY', [REF(first + 2), REF(first + 3), NULLTXT, '.ADDED.', NULLTXT, NULLTXT, NULLTXT, '0']),
  ];
}
