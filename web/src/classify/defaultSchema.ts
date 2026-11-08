// The shipped draft schema. Its single source is public/classification/default-schema.json (a PLACEHOLDER to be replaced
// by the schema that the project specifies). It is imported here so that it also reaches the single-file viewer, which has
// no server, and Node.
import json from '../../public/classification/default-schema.json';
import type { ClassificationSchema } from './types';

export const DEFAULT_SCHEMA = json as unknown as ClassificationSchema;
