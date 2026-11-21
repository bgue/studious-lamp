#!/usr/bin/env node
// xray-4d: 4D construction animation from a Primavera P6 schedule. Design: docs/design/4d-xer-animation.md; usage and the
// XER fields read: docs-features/xray-4d.md. Only `inspect` exists so far; later pieces (link, plan, script, render, pack,
// all) are added to the COMMANDS table below.
//   node tools/xray-4d.mjs <command> [options]     xray-4d --help  |  xray-4d <command> --help
// The schedule parser is TypeScript (src/schedule). It is bundled for node on first use into tools/xray-4d/schedule.bundle.mjs
// (vite ssr, the same way tools/pack/convert.mjs bundles the IFC reader) and rebuilt when src/schedule is newer.
// Exit codes: 0 ok, 1 unexpected internal error, 2 usage, 3 input (missing, unreadable or not an XER file, or a project
// choice that cannot be made).
import { existsSync, readFileSync, readdirSync, realpathSync, renameSync, rmSync, statSync } from 'node:fs';
import { basename, dirname, join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { makeScriptCommand } from './xray-4d/script.mjs';

export const EXIT_OK = 0;
export const EXIT_ERROR = 1;
export const EXIT_USAGE = 2;
export const EXIT_INPUT = 3;

const here = dirname(fileURLToPath(import.meta.url));
const webRoot = resolve(here, '..');
const bundleDir = join(here, 'xray-4d');
const bundleFile = join(bundleDir, 'schedule.bundle.mjs');
const WEEK = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

export class CliError extends Error {
  constructor(message, code) {
    super(message);
    this.code = code;
  }
}
const usage = (message) => new CliError(message, EXIT_USAGE);
const input = (message) => new CliError(message, EXIT_INPUT);

/** Newest mtime (ms) of a file, or of every file below a directory; 0 when missing. */
export function newestMtime(path) {
  if (!existsSync(path)) return 0;
  const st = statSync(path);
  if (!st.isDirectory()) return st.mtimeMs;
  let m = 0;
  for (const name of readdirSync(path)) m = Math.max(m, newestMtime(join(path, name)));
  return m;
}

/** The bundled parser: rebuilt when missing or older than src/schedule or the entry. Returns its path. */
export async function ensureBundle() {
  const sources = [join(webRoot, 'src', 'schedule'), join(webRoot, 'src', 'anim'), join(bundleDir, 'entry.ts')];
  const built = existsSync(bundleFile) ? statSync(bundleFile).mtimeMs : 0;
  if (built > 0 && built >= Math.max(...sources.map(newestMtime))) return bundleFile;
  const { build } = await import('vite');
  // build into a private directory, then rename: two runs at once cannot leave a half-written bundle behind
  const tmp = join(bundleDir, `.build-${process.pid}`);
  try {
    await build({
      root: webRoot,
      configFile: false,
      logLevel: 'silent',
      publicDir: false,
      build: {
        ssr: join(bundleDir, 'entry.ts'),
        outDir: tmp,
        emptyOutDir: true,
        minify: false,
        target: 'node22',
        rollupOptions: {
          output: { format: 'es', entryFileNames: 'schedule.bundle.mjs', codeSplitting: false },
        },
      },
    });
    renameSync(join(tmp, 'schedule.bundle.mjs'), bundleFile);
  } finally {
    rmSync(tmp, { recursive: true, force: true });
  }
  return bundleFile;
}

async function loadParser() {
  return import(pathToFileURL(await ensureBundle()).href);
}

// ---------------------------------------------------------------- arguments

/** Parses `--flag`, `--flag value`, `--flag=value` against a spec ({ name: 'bool' | 'string' | 'int' }). */
export function parseArgs(argv, spec) {
  const out = { _: [] };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '-o') {
      if (!spec['--out']) throw usage('unknown option -o');
      const v = argv[++i];
      if (v === undefined) throw usage('-o needs a value');
      out.out = v;
      continue;
    }
    if (!a.startsWith('--')) {
      out._.push(a);
      continue;
    }
    const eq = a.indexOf('=');
    const name = eq >= 0 ? a.slice(0, eq) : a;
    const kind = spec[name];
    if (!kind) throw usage(`unknown option ${name}`);
    if (kind === 'bool') {
      if (eq >= 0) throw usage(`${name} takes no value`);
      out[name.slice(2)] = true;
      continue;
    }
    let value = eq >= 0 ? a.slice(eq + 1) : argv[++i];
    if (value === undefined) throw usage(`${name} needs a value`);
    if (kind === 'int') {
      if (!/^\d+$/.test(value)) throw usage(`${name} needs a whole number, got "${value}"`);
      value = Number(value);
    }
    out[name.slice(2)] = value;
  }
  return out;
}

// ---------------------------------------------------------------- inspect

const TYPE_LABEL = { task: 'task', resource: 'resource', milestone: 'milestone', finishMilestone: 'finish milestone', loe: 'level of effort', wbsSummary: 'WBS summary', other: 'other' };
const STATUS_LABEL = { notStarted: 'not started', active: 'active', complete: 'complete' };

/** The facts `inspect` shows, as plain data (also the --json output). */
export function summarize(schedule, { encoding, depth }) {
  const tasks = schedule.tasks;
  const count = (list, key) => list.reduce((acc, t) => ((acc[t[key]] = (acc[t[key]] ?? 0) + 1), acc), {});
  const byType = count(tasks, 'type');
  const byStatus = count(tasks, 'status');
  const relations = schedule.relations.reduce((acc, r) => ((acc[r.type] = (acc[r.type] ?? 0) + 1), acc), {});

  const codes = Object.entries(schedule.codeTypes).map(([type, values]) => {
    const counted = values.map((value) => ({ value, count: tasks.filter((t) => t.codes[type] === value).length }));
    return { type, values: counted, withoutValue: tasks.filter((t) => t.codes[type] === undefined).length };
  });
  const udfs = schedule.udfLabels.map((label) => ({ label, count: tasks.filter((t) => t.udfs[label] !== undefined).length }));

  const calendars = schedule.calendars.map((c) => {
    const week = {};
    c.week.forEach((hours, i) => {
      week[WEEK[i]] = hours.map(([a, b]) => `${hhmm(a)}-${hhmm(b)}`).join(', ');
    });
    const exc = Object.entries(c.exceptions).sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0));
    return {
      id: c.id,
      name: c.name,
      hoursPerDay: c.hoursPerDay ?? null,
      week,
      exceptions: exc.length,
      holidays: exc.filter(([, h]) => h.length === 0).map(([d]) => d),
      partDays: exc.filter(([, h]) => h.length > 0).map(([d, h]) => ({ date: d, hours: h.map(([a, b]) => `${hhmm(a)}-${hhmm(b)}`).join(', ') })),
    };
  });

  const children = new Map();
  for (const w of schedule.wbs) {
    const key = w.parentId ?? '';
    if (!children.has(key)) children.set(key, []);
    children.get(key).push(w);
  }
  const directTasks = new Map();
  for (const t of tasks) directTasks.set(t.wbsId, (directTasks.get(t.wbsId) ?? 0) + 1);
  const subtreeCount = (id) => (directTasks.get(id) ?? 0) + (children.get(id) ?? []).reduce((n, c) => n + subtreeCount(c.id), 0);
  const tree = (id, level) => (children.get(id) ?? []).map((w) => ({
    shortName: w.shortName,
    name: w.name,
    activities: subtreeCount(w.id),
    children: level < depth ? tree(w.id, level + 1) : [],
    truncated: level >= depth && (children.get(w.id)?.length ?? 0) > 0,
  }));
  const wbs = (children.get('') ?? []).map((w) => ({
    shortName: w.shortName,
    name: w.name,
    activities: subtreeCount(w.id),
    children: depth > 0 ? tree(w.id, 1) : [],
    truncated: depth === 0 && (children.get(w.id)?.length ?? 0) > 0,
  }));

  return {
    schema: 'xray-4d-inspect/1',
    sourceHash: schedule.sourceHash,
    encoding,
    project: { id: schedule.project.id, shortName: schedule.project.shortName, name: schedule.project.name ?? null, dataDate: schedule.project.dataDate ?? null, calendarId: schedule.project.calendarId ?? null },
    projects: schedule.projects.map((p) => ({ shortName: p.shortName, name: p.name ?? null, dataDate: p.dataDate ?? null })),
    activities: { total: tasks.length, byType, byStatus },
    relations: { total: schedule.relations.length, byType: relations },
    codes,
    udfs,
    calendars,
    wbs,
    warnings: schedule.warnings,
  };
}

const hhmm = (h) => `${String(Math.floor(h)).padStart(2, '0')}:${String(Math.round((h % 1) * 60)).padStart(2, '0')}`;

function formatCounts(counts, labels) {
  return Object.entries(counts).map(([k, n]) => `${labels[k] ?? k} ${n}`).join(', ') || 'none';
}

/** The human-readable report. */
export function formatInspect(s) {
  const lines = [];
  const p = s.project;
  if (s.file) lines.push(`File         ${s.file}`);
  lines.push(`Project      ${p.shortName}${p.name ? `  ${p.name}` : ''}`);
  lines.push(`Data date    ${p.dataDate ?? 'not set'}`);
  lines.push(`Source       sha256 ${s.sourceHash.slice(0, 16)}..., ${s.encoding}`);
  if (s.projects.length > 1) lines.push(`Projects     ${s.projects.map((x) => x.shortName).join(', ')} (choose with --project)`);
  lines.push('');
  lines.push(`Activities   ${s.activities.total}  (${formatCounts(s.activities.byType, TYPE_LABEL)})`);
  lines.push(`Status       ${formatCounts(s.activities.byStatus, STATUS_LABEL)}`);
  lines.push(`Relations    ${s.relations.total}  (${formatCounts(s.relations.byType, {})})`);
  lines.push('');
  lines.push('Activity codes');
  if (s.codes.length === 0) lines.push('  none');
  for (const c of s.codes) {
    lines.push(`  ${c.type} (${c.values.length} values, ${c.withoutValue} activities without)`);
    const shown = c.values.slice(0, 40).map((v) => `${v.value} ${v.count}`);
    if (shown.length) lines.push(`    ${shown.join(', ')}${c.values.length > 40 ? `, ... ${c.values.length - 40} more` : ''}`);
  }
  lines.push('User fields (activity)');
  if (s.udfs.length === 0) lines.push('  none');
  for (const u of s.udfs) lines.push(`  ${u.label}  (${u.count} activities with a value)`);
  lines.push('');
  lines.push('Calendars');
  if (s.calendars.length === 0) lines.push('  none (fallback Mon-Fri assumed)');
  for (const c of s.calendars) {
    const days = WEEK.filter((d) => c.week[d]).map((d) => `${d} ${c.week[d]}`);
    const worked = Object.entries(c.week).filter(([, h]) => h).map(([d]) => d);
    lines.push(`  ${c.id}  ${c.name}  working ${worked.join(' ') || 'none'}${c.hoursPerDay ? `, ${c.hoursPerDay} h/day` : ''}`);
    if (days.length) lines.push(`      ${days.join('; ')}`);
    lines.push(`      exceptions ${c.exceptions}: holidays ${c.holidays.join(', ') || 'none'}`);
    for (const d of c.partDays) lines.push(`      ${d.date} ${d.hours}`);
  }
  lines.push('');
  lines.push('WBS (activities in each node, including below)');
  const walk = (nodes, indent) => {
    for (const n of nodes) {
      lines.push(`${indent}${n.shortName}  ${n.name}  (${n.activities})${n.truncated ? '  ...' : ''}`);
      walk(n.children, `${indent}  `);
    }
  };
  if (s.wbs.length === 0) lines.push('  none');
  walk(s.wbs, '  ');
  lines.push('');
  lines.push(s.warnings.length ? `Warnings (${s.warnings.length})` : 'Warnings     none');
  for (const w of s.warnings) lines.push(`  - ${w}`);
  return lines.join('\n');
}

async function inspect(args, io) {
  const file = args._[0];
  if (!file) throw usage('inspect needs a schedule file: xray-4d inspect schedule.xer [--project X] [--json]');
  if (args._.length > 1) throw usage(`inspect takes one file, got ${args._.length}`);
  const path = resolve(file);
  if (!existsSync(path) || !statSync(path).isFile()) throw input(`cannot read ${file}`);
  const bytes = new Uint8Array(readFileSync(path));
  const parser = await loadParser();
  const { encoding } = parser.decodeXer(bytes);
  let schedule;
  try {
    schedule = parser.parseXer(bytes, { project: args.project });
  } catch (e) {
    throw input(`${basename(file)}: ${e.message}`);
  }
  const summary = summarize(schedule, { encoding, depth: args.depth ?? 2 });
  summary.file = basename(file);
  io.out(args.json ? JSON.stringify(summary, null, 2) : formatInspect(summary));
  return EXIT_OK;
}

const INSPECT_OPTIONS = { '--project': 'string', '--json': 'bool', '--depth': 'int' };

/** Subcommand table: name -> { summary, usage, options, run }. Later commands are added here. */
export const COMMANDS = {
  inspect: {
    summary: 'projects, data date, activity counts, codes, user fields, calendars, WBS tree and warnings of a P6 .xer file',
    usage: 'xray-4d inspect <schedule.xer> [--project NAME] [--depth N] [--json]',
    options: INSPECT_OPTIONS,
    optionHelp: [
      '  --project NAME   the project to read, by short name (needed when the file holds several)',
      '  --depth N        WBS levels to show below the project (default 2; 0 shows only the top)',
      '  --json           print a JSON summary (schema xray-4d-inspect/1) instead of the report',
    ],
    run: inspect,
  },
  script: makeScriptCommand({ loadParser, CliError, EXIT_OK, EXIT_USAGE, EXIT_INPUT, webRoot }),
};

const TOP_HELP = `xray-4d: 4D construction animation from a Primavera P6 schedule

Usage: xray-4d <command> [options]

Commands:
${Object.entries(COMMANDS).map(([name, c]) => `  ${name.padEnd(9)} ${c.summary}`).join('\n')}

Run "xray-4d <command> --help" for a command's options.
Exit codes: 0 ok, 1 internal error, 2 usage, 3 input.`;

function commandHelp(name) {
  const c = COMMANDS[name];
  return `Usage: ${c.usage}\n\n${c.summary}\n\nOptions:\n${c.optionHelp.join('\n')}`;
}

/** Runs the CLI with argv (without node and the script). Returns the exit code. */
export async function run(argv, io = { out: (s) => process.stdout.write(s + '\n'), err: (s) => process.stderr.write(s + '\n') }) {
  try {
    if (argv.length === 0) {
      io.out(TOP_HELP);
      return EXIT_USAGE;
    }
    if (argv[0] === '--help' || argv[0] === '-h' || argv[0] === 'help') {
      io.out(TOP_HELP);
      return EXIT_OK;
    }
    const [name, ...rest] = argv;
    const command = COMMANDS[name];
    if (!command) throw usage(`unknown command "${name}" (commands: ${Object.keys(COMMANDS).join(', ')})`);
    if (rest.includes('--help') || rest.includes('-h')) {
      io.out(commandHelp(name));
      return EXIT_OK;
    }
    const args = parseArgs(rest, command.options);
    return await command.run(args, io);
  } catch (e) {
    if (e instanceof CliError) {
      io.err(`xray-4d: ${e.message}`);
      return e.code;
    }
    io.err(`xray-4d: ${e?.stack ?? e}`);
    return EXIT_ERROR;
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(realpathSync(process.argv[1])).href) {
  process.exitCode = await run(process.argv.slice(2));
}
