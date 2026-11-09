// The shipped schema, "Throughline-aligned default". Its single source is public/classification/default-schema.json. It is a
// stand-in for the project's actual Throughline `Discipline` code list (see throughline.ts). It is imported here so that it
// also reaches the single-file viewer, which has no server, and Node.
import json from '../../public/classification/default-schema.json';
import type { ClassificationSchema } from './types';

export const DEFAULT_SCHEMA = json as unknown as ClassificationSchema;
