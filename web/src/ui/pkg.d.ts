// Lets `import { version } from '../../package.json'` type-check without turning on resolveJsonModule in tsconfig.json.
// A named import (not the default export) keeps the rest of package.json, such as the list of dev dependencies, out of the bundle.
declare module '*/package.json' {
  const pkg: { name: string; version: string };
  export const name: string;
  export const version: string;
  export default pkg;
}
