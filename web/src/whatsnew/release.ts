// The release number this build carries: a build-time constant from tools/release-number.mjs (a vite plugin defines it).
// null when it is not defined (a tool that bundles src/ without the plugin) or the counter file was missing.
declare const __XRAY_RELEASE__: number | null | undefined;

export const RELEASE: number | null = typeof __XRAY_RELEASE__ === 'number' ? __XRAY_RELEASE__ : null;
