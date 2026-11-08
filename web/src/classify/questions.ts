// The questions asked of the decision model, built from the target schema. The code lists and their descriptions in the
// schema become the `criteria` of the choice questions, so the answer space is the schema, nothing else.

import { choiceQuestion, noulQuestion } from './jevAdapter';
import type { Questions } from './jevAdapter';
import type { ClassificationSchema, SchemaDiscipline } from './types';

export const Q_DISCIPLINE = 'discipline';
export const Q_BUILDING = 'building_element';
export const Q_MASTERFORMAT = 'masterformat';
export const Q_SUB = 'sub_discipline';

/** Separator of discipline and sub-discipline in the option keys of a combined sub-discipline question. */
export const COMBINED_SEP = '/';

/** Questions of the first request: discipline, building_element and masterformat. */
export function mainQuestions(schema: ClassificationSchema): Questions {
  const discipline: Record<string, string> = {};
  for (const d of schema.disciplines) discipline[d.code] = `${d.label}. ${d.description}`;
  const division: Record<string, string> = {};
  for (const d of schema.masterformat.divisions) division[d.division] = `${d.title}. ${d.description}`;
  return {
    [Q_DISCIPLINE]: choiceQuestion(
      'Choose the engineering discipline that owns this BIM element. Decide from its IFC class, name, type, property sets, quantities, position in the building and its parents.',
      discipline,
    ),
    [Q_BUILDING]: noulQuestion('This element is part of a building (not of a road, a bridge, a site utility or a process plant).'),
    [Q_MASTERFORMAT]: choiceQuestion(
      'Choose the CSI MasterFormat 2018 division that covers the work of this BIM element. Choose by the work that the element belongs to.',
      division,
    ),
  };
}

/** The sub-discipline options of one discipline, or of several (then each key is "<discipline>/<sub>"). */
export function subOptions(schema: ClassificationSchema, disciplines: readonly string[]): { options: Record<string, string>; combined: boolean } {
  const combined = disciplines.length > 1;
  const options: Record<string, string> = {};
  for (const code of disciplines) {
    const d = schema.disciplines.find((x) => x.code === code);
    if (!d) continue;
    for (const s of d.subDisciplines) options[combined ? `${d.code}${COMBINED_SEP}${s.code}` : s.code] = combined ? `${d.label}: ${s.label}. ${s.description}` : `${s.label}. ${s.description}`;
  }
  return { options, combined };
}

/** The question of the second request. Null when there is at most one option (nothing to decide). */
export function subQuestions(schema: ClassificationSchema, disciplines: readonly string[]): Questions | null {
  const { options } = subOptions(schema, disciplines);
  if (Object.keys(options).length < 2) return null;
  const labels = disciplines.map((c) => schema.disciplines.find((d) => d.code === c)?.label ?? c);
  return {
    [Q_SUB]: choiceQuestion(
      `Choose the sub-discipline of this BIM element within ${labels.join(' or ')}.`,
      options,
    ),
  };
}

export function disciplineOf(schema: ClassificationSchema, code: string): SchemaDiscipline | undefined {
  return schema.disciplines.find((d) => d.code === code);
}
