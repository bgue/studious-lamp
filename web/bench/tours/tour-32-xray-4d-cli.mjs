// Tour of chapter 32, "xray-4d command line" (docs/manual/32-xray-4d-cli.md): runs the documented commands with node and checks their output:
// inspect (32.2), link with report and IFC write-back (32.2, 32.4), plan, script, pack, exit codes (32.3). `render` and `storyboard` need a
// Chromium render of the whole film (minutes on the software renderer) and are not run here. No picture notes in this chapter.
// Run: node bench/run-smokes.mjs --only tour-32-xray-4d-cli
import { spawnSync } from 'node:child_process';
import { existsSync, mkdtempSync, readFileSync, statSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { repoRoot, startTour, webRoot } from './lib.mjs';

const tour = await startTour('tour-32-xray-4d-cli');
const out = mkdtempSync(join(tmpdir(), 'tour-32-'));
const FZK = resolve(repoRoot, 'models', 'AC20-FZK-Haus.ifc');
const XER = resolve(webRoot, 'public/samples/fzk-haus.xer'), CFG = resolve(webRoot, 'public/samples/fzk-haus.4d.json');
const x4d = (args, opts = {}) => {
  const r = spawnSync('node', [resolve(webRoot, 'tools/xray-4d.mjs'), ...args], { cwd: webRoot, encoding: 'utf8', timeout: 240000, ...opts });
  return { code: r.status, out: r.stdout ?? '', err: r.stderr ?? '' };
};
const at = (n) => join(out, n);

await tour.step('32.2 Try it steps 1-3: inspect the sample', async () => {
  const r = x4d(['inspect', 'public/samples/fzk-haus.xer']);
  tour.check('step 1: inspect exits 0', r.code === 0, r.err.slice(0, 120));
  tour.check('step 2: "project FZK-HAUS, data date 2027-05-19"', /FZK-HAUS/.test(r.out) && /2027-05-19/.test(r.out));
  tour.check('"46 activities (40 tasks, 2 milestones, 4 finish milestones)"', /46\s+\(milestone 2, task 40, finish milestone 4\)/.test(r.out), r.out.split('\n').find((l) => /^Activities/.test(l)));
  tour.check('"64 relations"', /Relations\s+64/.test(r.out));
  tour.check('"the code types Level, Trade and Phase with their values"', /Level \(/.test(r.out) && /Trade \(/.test(r.out) && /Phase \(/.test(r.out));
  tour.check('"the calendar with its holidays" and "the WBS tree with the activity count of each node"', /holidays 2027-03-26/.test(r.out) && /WBS/.test(r.out) && /Preconstruction\s+\(2\)/.test(r.out));
  const d3 = x4d(['inspect', 'public/samples/fzk-haus.xer', '--depth', '3']);
  tour.check('step 3: "--depth 3" shows more WBS levels', d3.out.length >= r.out.length && d3.code === 0, `${r.out.length} -> ${d3.out.length}`);
  const j = x4d(['inspect', 'public/samples/fzk-haus.xer', '--json']);
  let doc = null; try { doc = JSON.parse(j.out); } catch { /* checked below */ }
  tour.check('"--json for a machine-readable summary (xray-4d-inspect/1)"', doc?.schema === 'xray-4d-inspect/1' && doc.activities?.total === 46, doc?.schema);
  const bad = x4d(['inspect', resolve(repoRoot, 'README.md')]);
  tour.check('"only a file that is not an XER ... stops the tool" (exit 3)', bad.code === 3, `exit ${bad.code}`);
});

let links = null;
await tour.step('32.2 link: coverage, report, IFC copy; 32.4 IFC write-back', async () => {
  const r = x4d(['link', FZK, XER, '--config', CFG, '--report', at('r.html'), '--write-ifc', at('m.4d.ifc'), '-o', at('links.json')]);
  tour.check('link exits 0', r.code === 0, r.err.slice(-160));
  tour.check('"The coverage (share of elements linked) is printed to stderr"', /coverage: elements 100\.0 %/.test(r.err), r.err.split('\n').find((l) => /coverage/.test(l)));
  tour.check('"Progress and warnings go to stderr, results to -o"', existsSync(at('links.json')) && r.out.trim() === '', `stdout: ${r.out.slice(0, 80)}`);
  links = JSON.parse(readFileSync(at('links.json'), 'utf8'));
  tour.check('links.json has links and activities (a LinkML dataset)', Array.isArray(links.links) && links.links.length > 10 && Array.isArray(links.activities), Object.keys(links).join());
  tour.check('"The same inputs give the same files": a second run gives the same links.json', (() => { const r2 = x4d(['link', FZK, XER, '--config', CFG, '-o', at('links2.json')]); return r2.code === 0 && readFileSync(at('links2.json')).equals(readFileSync(at('links.json'))); })());
  tour.check('the link report is one page with no scripts', (() => { const h = readFileSync(at('r.html'), 'utf8'); return /<html/i.test(h) && !/<script/i.test(h); })());
  // 32.4: write-back
  const orig = readFileSync(FZK), outIfc = readFileSync(at('m.4d.ifc'));
  const cut = orig.lastIndexOf('ENDSEC;');
  tour.check('"The original bytes are untouched. One block is inserted before the final ENDSEC;"', outIfc.subarray(0, cut).equals(orig.subarray(0, cut)) && outIfc.subarray(outIfc.length - (orig.length - cut)).equals(orig.subarray(cut)));
  const t = outIfc.toString('latin1');
  for (const e of ['IFCWORKSCHEDULE', 'IFCTASK(', 'IFCTASKTIME', 'IFCRELASSIGNSTOCONTROL', 'IFCRELASSIGNSTOPRODUCT', 'IFCRELSEQUENCE', 'IFCLAGTIME']) tour.check(`32.4 table: the copy holds ${e}`, t.includes(e));
  tour.check('"one, named Xray 4D"', /IFCWORKSCHEDULE\([^;]*'Xray 4D'/.test(t));
  // a second write replaces only the 4D part: write the copy again from the copy
  const r2 = x4d(['link', at('m.4d.ifc'), XER, '--config', CFG, '--write-ifc', at('m2.4d.ifc'), '-o', at('links3.json')]);
  tour.check('"A second write replaces only the 4D part, and rewriting gives the same bytes"', r2.code === 0 && readFileSync(at('m2.4d.ifc')).equals(outIfc), `exit ${r2.code} ${r2.err.slice(-100)}`);
  // reading back is automatic: link with no configuration
  writeFileSync(at('empty.4d.json'), '{"schema":"xray-4d-config/1","schedule":{},"model":{}}\n');
  tour.check('"link needs --config": without it the command stops (exit 2)', x4d(['link', at('m.4d.ifc'), XER, '-o', at('links5.json')]).code === 2);
  const r3 = x4d(['link', at('m.4d.ifc'), XER, '--config', at('empty.4d.json'), '-o', at('links4.json')]);
  const l4 = existsSync(at('links4.json')) ? JSON.parse(readFileSync(at('links4.json'), 'utf8')) : { links: [] };
  tour.check('"A file written by --write-ifc links natively again, with no configuration of its own" (an empty configuration)', r3.code === 0 && l4.links.some((l) => l.source === 'native') && /coverage: elements 100/.test(r3.err), r3.err.split('\n').find((l) => /coverage/.test(l)));
});

await tour.step('32.2 exit codes: 2 usage, 3 input (yaml config), 4 coverage below --min-coverage', async () => {
  tour.check('exit 2: an unknown command', x4d(['frobnicate']).code === 2);
  writeFileSync(at('c.yaml'), 'schedule: {}\n');
  tour.check('"a .yaml file is refused with exit 3"', x4d(['link', FZK, XER, '--config', at('c.yaml'), '-o', at('y.json')]).code === 3);
  const r = x4d(['link', FZK, XER, '--config', at('empty.4d.json'), '--min-coverage', '0.99', '-o', at('nocfg.json')]);
  tour.check('"Below --min-coverage, the files are still written and the exit code is 4"', r.code === 4 && existsSync(at('nocfg.json')), `exit ${r.code}; ${r.err.split('\n').find((l) => /coverage/.test(l))}`);
});

await tour.step('32.2 plan, script, pack', async () => {
  const p = x4d(['plan', FZK, XER, at('links.json'), '--config', CFG, '-o', at('build.4d.json')]);
  tour.check('plan exits 0 and writes build.4d.json', p.code === 0 && existsSync(at('build.4d.json')), p.err.slice(-120));
  const plan = JSON.parse(readFileSync(at('build.4d.json'), 'utf8'));
  tour.check('the plan has a format xray-4d-plan/1', /xray-4d-plan\/1/.test(JSON.stringify(plan).slice(0, 400)), Object.keys(plan).join());
  tour.check('plan reports 82 elements, 46 activities and a 90 s film', /82 elements, 46 activities/.test(p.err) && /90\.0 s/.test(p.err), p.err.split('\n').find((l) => /^plan/.test(l)));
  const s = x4d(['script', at('build.4d.json'), '--model', FZK, '-o', at('film.xrayanim'), '--notes', at('notes.txt')]);
  const txt = readFileSync(at('film.xrayanim'), 'utf8');
  tour.check('script writes a film.xrayanim with a header, the schedule statement and "at date" blocks', s.code === 0 && /^-- generated by xray-4d script/.test(txt) && /^schedule "/m.test(txt) && /^at date "/m.test(txt), s.err.slice(-100));
  tour.check('"The notes file has one line per decision: time, date, and what and why"', /^\d\d:\d\d\.\d  \d{4}-\d\d-\d\d  /m.test(readFileSync(at('notes.txt'), 'utf8')));
  const noModel = x4d(['script', at('build.4d.json'), '-o', at('x.xrayanim')]);
  tour.check('"The plan carries no geometry, so it needs --model"', noModel.code !== 0, `exit ${noModel.code}`);
  const k = x4d(['pack', FZK, at('build.4d.json'), '--script', at('film.xrayanim'), '--loop', '-o', at('build.html')], { timeout: 300000 });
  tour.check('pack writes a kiosk page that autoplays the plan in a loop', k.code === 0 && existsSync(at('build.html')) && /autoplay plan:build \(loop\)/.test(k.err), k.err.split('\n').slice(-2).join(' ').slice(0, 160));
  tour.check('the packed page is one .html file with no reviewer name or key', (() => { const h = readFileSync(at('build.html'), 'utf8'); return !/hf_[A-Za-z0-9]{8}|"reviewed_by":\s*"/.test(h); })(), `${(statSync(at('build.html')).size / 1e6).toFixed(1)} MB`);
});

await tour.finish();
