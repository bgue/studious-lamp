// The shipped schema, "Throughline-aligned default". Its single source is public/classification/default-schema.json. It is a
// stand-in for the project's actual Throughline `Discipline` code list (see throughline.ts). It is imported here so that it
// also reaches the single-file viewer, which has no server, and Node.
import json from '../../public/classification/default-schema.json';
import { parseFacets } from './facets/defs';
import type { ClassificationSchema } from './types';

const raw = json as unknown as ClassificationSchema & { facets?: unknown };

/** The file is used as it is, except the `facets` section: it is checked and filled in (the file form has the facet ids as keys). */
export const DEFAULT_SCHEMA: ClassificationSchema = { ...raw, ...(raw.facets === undefined ? {} : { facets: parseFacets(raw.facets, [], raw.minConfidence) }) };
