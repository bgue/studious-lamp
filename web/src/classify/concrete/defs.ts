// The concrete facet family (namespace `XR_Concrete*`): ids, code lists, property fields and the result type. No DOM.
// Design: docs/design/concrete-classification.md. The five sets sit beside the six facets of `../facets/defs.ts` and share their core
// fields (Code, Label, Confidence, Source, Model, NeedsReview, SchemeVersion); they are kept in their own store, so the facet code
// lists and the schema files stay as they are.

import type { FacetFieldValue, FacetSource } from '../facets/defs';

export const CONCRETE_FACET_IDS = ['ConcreteGeometry', 'ConcreteElement', 'ConcreteMethod', 'ConcreteSpec', 'ConcreteReinforcement'] as const;
export type ConcreteFacetId = (typeof CONCRETE_FACET_IDS)[number];
export const CONCRETE_SCHEME = 'xr-concrete/1';
export const concretePset = (f: ConcreteFacetId): string => `XR_${f}`;
export const isConcreteKey = (k: string): boolean => k.startsWith('XR_Concrete');

export interface ConcreteCode { code: string; label: string; group?: string }
const c = (code: string, label: string, group?: string): ConcreteCode => ({ code, label, ...(group ? { group } : {}) });

/** Design section 3.1. */
export const ROLE_CODES: readonly ConcreteCode[] = [
  c('PAD_FOOTING', 'Pad footing', 'Foundations'), c('STRIP_FOOTING', 'Strip footing', 'Foundations'), c('RAFT', 'Raft', 'Foundations'), c('PILE_CAP', 'Pile cap', 'Foundations'),
  c('PILE', 'Pile', 'Foundations'), c('GRADE_BEAM', 'Grade beam', 'Foundations'), c('PLINTH', 'Plinth', 'Foundations'),
  c('SLAB_ON_GRADE', 'Slab on grade', 'Slabs'), c('SUSPENDED_SLAB', 'Suspended slab', 'Slabs'), c('FLAT_SLAB', 'Flat slab', 'Slabs'), c('RIBBED_SLAB', 'Ribbed slab', 'Slabs'),
  c('WAFFLE_SLAB', 'Waffle slab', 'Slabs'), c('TRANSFER_SLAB', 'Transfer slab', 'Slabs'), c('TOPPING', 'Topping', 'Slabs'), c('LANDING', 'Landing', 'Slabs'),
  c('BEAM', 'Beam', 'Frame'), c('DOWNSTAND_BEAM', 'Downstand beam', 'Frame'), c('UPSTAND_BEAM', 'Upstand beam', 'Frame'), c('TRANSFER_BEAM', 'Transfer beam', 'Frame'),
  c('COLUMN', 'Column', 'Frame'), c('PIER', 'Pier', 'Frame'),
  c('WALL', 'Wall', 'Walls'), c('SHEAR_WALL', 'Shear wall', 'Walls'), c('CORE_WALL', 'Core wall', 'Walls'), c('RETAINING_WALL', 'Retaining wall', 'Walls'),
  c('BASEMENT_WALL', 'Basement wall', 'Walls'), c('PARAPET', 'Parapet', 'Walls'),
  c('STAIR', 'Stair', 'Other'), c('RAMP', 'Ramp', 'Other'), c('CORBEL', 'Corbel', 'Other'), c('CURB', 'Curb', 'Other'), c('EQUIPMENT_PAD', 'Equipment pad', 'Other'),
  c('PRECAST_PANEL', 'Precast panel', 'Other'), c('OTHER', 'Other concrete element', 'Other'),
];

/** Design section 3.2. */
export const METHOD_CODES: readonly ConcreteCode[] = [
  c('CAST_IN_PLACE', 'Cast in place'), c('PRECAST', 'Precast'), c('POST_TENSIONED', 'Post-tensioned'), c('TILT_UP', 'Tilt-up'), c('COMPOSITE_DECK', 'Composite deck (concrete on metal deck)'), c('UNKNOWN', 'Unknown'),
];

/** Design section 3.4. */
export const REINFORCEMENT_CODES: readonly ConcreteCode[] = [
  c('REINFORCED', 'Reinforced'), c('POST_TENSIONED', 'Post-tensioned'), c('FIBRE', 'Fibre reinforced'), c('PLAIN', 'Plain (unreinforced)'), c('UNKNOWN', 'Unknown'),
];
export const SLAB_SCHEMES: readonly ConcreteCode[] = [c('ONE_WAY', 'One-way'), c('TWO_WAY', 'Two-way')];

export const labelOf = (list: readonly ConcreteCode[], code: string): string => list.find((x) => x.code === code)?.label ?? code;

export type FieldType = 'label' | 'real' | 'boolean';
export const CORE_FIELDS: ReadonlyArray<readonly [string, FieldType]> = [
  ['Code', 'label'], ['Label', 'label'], ['Confidence', 'real'], ['Source', 'label'], ['Model', 'label'], ['NeedsReview', 'boolean'], ['SchemeVersion', 'label'],
];

/** The facet-specific fields of each set, in order. */
export const CONCRETE_FIELDS: Record<ConcreteFacetId, ReadonlyArray<readonly [string, FieldType]>> = {
  ConcreteGeometry: [
    ['Volume', 'real'], ['VolumeEstimated', 'boolean'], ['FormworkArea', 'real'], ['TopArea', 'real'], ['SoffitArea', 'real'],
    ['FrameOrigin', 'label'], ['FrameX', 'label'], ['FrameY', 'label'], ['FrameZ', 'label'],
    ['Length', 'real'], ['Width', 'real'], ['Thickness', 'real'], ['SectionShape', 'label'], ['Faces', 'label'], ['Supports', 'label'], ['Carries', 'label'],
  ],
  ConcreteElement: [['Mark', 'label'], ['MarkSource', 'label'], ['Storey', 'real'], ['HostGroup', 'label']],
  ConcreteMethod: [],
  ConcreteSpec: [
    ['StrengthClass', 'label'], ['StrengthUnit', 'label'], ['Standard', 'label'], ['ExposureClass', 'label'], ['ExposureSource', 'label'],
    ['CoverNominal', 'real'], ['CoverMainBars', 'real'], ['CoverLinks', 'real'], ['CoverSource', 'label'], ['FireResistance', 'label'], ['ReinforcementGrade', 'label'], ['Derived', 'label'],
  ],
  ConcreteReinforcement: [['Scheme', 'label'], ['SchemeSource', 'label'], ['RatioEstimate', 'real'], ['RatioSource', 'label'], ['MassEstimate', 'real']],
};

/** One concrete facet value of one element. */
export interface ConcreteFacetResult {
  facet: ConcreteFacetId;
  code: string;
  label: string;
  confidence: number;
  source: FacetSource;
  model?: string;
  needsReview: boolean;
  fields: Record<string, FacetFieldValue>;
  probabilities?: Record<string, number>;
  rationale?: string;
}
export type ConcreteSet = Partial<Record<ConcreteFacetId, ConcreteFacetResult>>;

/** The question names of the decision model (design section 7). Exposure is never asked. */
export const Q_CONCRETE = { role: 'concrete_role', method: 'concrete_method', reinforcement: 'concrete_reinforcement', scheme: 'concrete_slab_scheme' } as const;
