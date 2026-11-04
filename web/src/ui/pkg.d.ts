// Lets `import pkg from '../../package.json'` type-check without turning on resolveJsonModule in tsconfig.json.
declare module '*/package.json' {
  const pkg: { name: string; version: string };
  export default pkg;
}
