// Generates docs/SETTINGS.md from src/ui/helpText.ts. Usage: npm run docs
// Needs Node 22.18 or newer (it loads the TypeScript file by type stripping).
import { writeFileSync, mkdirSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const src = resolve(here, '../src/ui/helpText.ts');
const out = resolve(here, '../../docs/SETTINGS.md');
const { FOLDER_HELP, CONTROL_HELP, GLOSSARY } = await import(pathToFileURL(src).href);

const cell = (s) => String(s).replace(/\|/g, '\\|').replace(/\{class\}/g, '*class*');
const row = (name, e) => `| ${cell(name)} | ${cell(e.intent)} | ${cell(e.impact)} | ${cell(e.use)} | ${cell(e.ref)} |`;

// Group the control keys by folder key. The folder is the longest folder entry that the key starts with, because a
// control name can hold a slash itself ("Clear pins/hides", "Speed (deg/s)"). A key without a folder entry falls back
// to everything before the last slash.
const folderKeys = Object.keys(FOLDER_HELP).sort((a, b) => b.length - a.length);
const groups = new Map();
for (const key of Object.keys(CONTROL_HELP)) {
  const f = folderKeys.find((k) => key.startsWith(`${k}/`));
  const g = f ?? key.slice(0, key.lastIndexOf('/'));
  if (!groups.has(g)) groups.set(g, []);
  groups.get(g).push({ name: key.slice(g.length + 1), entry: CONTROL_HELP[key] });
}
// Folders in panel order, then groups that have controls but no folder entry.
const order = [...Object.keys(FOLDER_HELP)];
for (const g of groups.keys()) if (!order.includes(g)) order.push(g);

const lines = [];
lines.push('# Settings reference', '');
lines.push(
  'This file is generated from `web/src/ui/helpText.ts` by `npm run docs`. Do not edit it by hand.',
  'The same texts appear as hover tooltips in the viewer: hover over a setting for 350 ms, or focus a slider with the keyboard.',
  '',
  'Each setting has four texts. **Impact** is the plain-language effect: what you see or feel change in the viewer when you move or use the control, in everyday words and without the jargon of the report. ' +
    'The other columns are the technical wording. **Intent** says what the setting does, **Use** says how and when to change it, and **Ref** names the section of the report. ' +
    'The tooltip shows the lines in this order: Intent, Impact, Use, Ref.',
  '',
);
lines.push('Switch the tooltips off with `window.__xrayHelp.disable()` or `localStorage["xray.help"] = "off"`.', '');
lines.push('## Contents', '');
lines.push('- [Glossary](#glossary)');
for (const g of order) lines.push(`- [${g}](#${g.toLowerCase().replace(/[^a-z0-9 -]/g, '').trim().replace(/ +/g, '-')})`);
lines.push('', '## Glossary', '');
lines.push('The texts use these terms with one meaning each.', '', '| Term | Meaning |', '| --- | --- |');
for (const { term, definition } of GLOSSARY) lines.push(`| ${cell(term)} | ${cell(definition)} |`);
lines.push('');
lines.push('## Writing rules', '');
lines.push(
  'Intent and Use follow ASD-STE100 Simplified Technical English, extended with the glossary above.',
  '',
  '- One instruction per sentence. At most 20 words per sentence.',
  '- Active voice and present tense. The Use line is in the imperative mood.',
  '- No sentence starts with a gerund. No parentheses, no "e.g." and no "etc.".',
  '- Numbers as digits. A unit follows the number after a space.',
  '- The Ref line starts with `Report:` and names the section and, where it exists, the algorithm line.',
  '',
  'Impact follows the same sentence rules and adds these:',
  '',
  '- Everyday words at a grade 6 to 8 reading level. It says what you see or feel change on screen.',
  '- A slider: what happens at each end. A switch: what happens on and off. A list: what each choice looks like.',
  '- It uses none of the glossary terms, none of the words of the setting name or folder title, and none of the technical words that the test lists.',
  '',
);
for (const g of order) {
  lines.push(`## ${g}`, '');
  lines.push('| Setting | Intent | Impact | Use | Ref |', '| --- | --- | --- | --- | --- |');
  if (FOLDER_HELP[g]) lines.push(row(`*Folder: ${g}*`, FOLDER_HELP[g]));
  for (const { name, entry } of groups.get(g) ?? []) lines.push(row(name, entry));
  lines.push('');
}
mkdirSync(dirname(out), { recursive: true });
writeFileSync(out, lines.join('\n'));
console.log(`wrote ${out}: ${Object.keys(FOLDER_HELP).length} folders, ${Object.keys(CONTROL_HELP).length} controls, ${GLOSSARY.length} glossary terms`);
