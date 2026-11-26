import { runQuery } from '../src/query';
import type { SceneModel } from '../src/types';
import { resetModelTable } from '../src/query/table';

/** Element ids that match a query, after a fresh read of the model's properties. */
export function queryModel(model: SceneModel, text: string): number[] {
  resetModelTable(model);
  return runQuery(model, text).ids;
}
