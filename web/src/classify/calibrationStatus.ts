// What the drawer shows about calibration: the mode, what is in use, and the last fit with its before and after numbers.

import type { CalibrationChoice, QuestionReport, StoredFit, Temperatures } from './calibrate';
import type { CalibrationReport } from './calibrateRules';
import type { ClassifySettings } from './settings';

export interface CalibrationStatus {
  mode: ClassifySettings['calibration'];
  /** What is used now ("shipped", "fitted on ...", "manual", "off ..."). */
  label: string;
  note: string;
  temperatures: Temperatures;
  fitted: StoredFit | null;
  /** The numbers of the last fit: this page's report, else those stored with the fit. */
  questions: QuestionReport[];
  /** The BIM model that the last fit was measured on. */
  source: string;
}

export function calibrationStatus(s: ClassifySettings, choice: CalibrationChoice, fitted: StoredFit | null, last: CalibrationReport | null): CalibrationStatus {
  return {
    mode: s.calibration,
    label: choice.label,
    note: choice.note,
    temperatures: choice.temperatures,
    fitted,
    questions: last?.questions ?? fitted?.reports ?? [],
    source: last?.source ?? fitted?.source ?? '',
  };
}
