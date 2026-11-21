// The FZK-Haus 4D sample (public/samples/fzk-haus.xer and fzk-haus.4d.json) as strings in the bundle, so the sample works in the single file,
// which has no public folder. Loaded on demand with a dynamic import; in the single file the chunk is inlined.
import xer from '../../public/samples/fzk-haus.xer?raw';
import config from '../../public/samples/fzk-haus.4d.json?raw';

export const SAMPLE_XER: string = xer;
export const SAMPLE_CONFIG: string = config;
