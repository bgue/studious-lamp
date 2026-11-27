// Tour of chapter 33, "The agent skill ifc-4d-schedule" (docs/manual/33-agent-skill.md): the steps of 33.4 run with the skill's own scripts in place of the agent
// (read, link, propose, write IFC, verify, write XER, animation, check), and the rules of 33.5 checked on the files. The agent itself (a language model) is not
// run; what it would call is. Needs Python 3 with ifcopenshell and Node. No picture notes in this chapter.
// Run: node bench/run-smokes.mjs --only tour-33-agent-skill
import { spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { existsSync, mkdirSync, mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { repoRoot, startTour, webRoot } from './lib.mjs';

const tour = await startTour('tour-33-agent-skill');
const w = mkdtempSync(join(tmpdir(), 'tour-33-'));
const skill = resolve(repoRoot, 'skills', 'ifc-4d-schedule'), S = resolve(skill, 'scripts');
const FZK = resolve(repoRoot, 'models', 'AC20-FZK-Haus.ifc');
const XER = resolve(webRoot, 'public/samples/fzk-haus.xer'), CFG = resolve(webRoot, 'public/samples/fzk-haus.4d.json');
const run = (cmd, args) => { const r = spawnSync(cmd, args, { encoding: 'utf8', timeout: 240000 }); return { code: r.status, out: r.stdout ?? '', err: r.stderr ?? '' }; };
const py = (script, ...args) => run('python3', [resolve(S, script), ...args]);
const at = (n) => join(w, n);
const sha = (f) => createHash('sha256').update(readFileSync(f)).digest('hex');
const json = (s) => { try { return JSON.parse(s); } catch { return null; } };

await tour.step('33.2 Install: the folder is a skill; the selftest runs every step', async () => {
  const md = readFileSync(resolve(skill, 'SKILL.md'), 'utf8');
  tour.check('"A skill is a folder ... SKILL.md": skills/ifc-4d-schedule/SKILL.md has the name ifc-4d-schedule', /^---\nname: ifc-4d-schedule\n/.test(md));
  tour.check('"Python 3 ... ifcopenshell ... Node 18 or newer" are present on this machine', run('python3', ['-c', 'import ifcopenshell']).code === 0 && run('node', ['--version']).code === 0);
  mkdirSync(w + '/self');
  const r = run('bash', [resolve(S, 'selftest.sh'), w + '/self']);
  tour.check('"scripts/selftest.sh ... runs every step on the FZK-Haus sample and prints ok with the folder it used"', r.code === 0 && /^ok: /m.test(r.out), (r.out + r.err).split('\n').slice(-2).join(' | ').slice(0, 160));
});

await tour.step('33.3 Try it steps 2-3: read both files, link by the configuration', async () => {
  const x = py('xer_read.py', XER, '-o', at('schedule.json'));
  const xs = json(x.out);
  tour.check('step 2: the schedule is read: project FZK-HAUS, 46 activities', x.code === 0 && /FZK-HAUS/.test(x.out) && /46/.test(x.out), x.out.slice(0, 160));
  const m = py('ifc_read.py', FZK, '-o', at('model.json'));
  const ms = json(m.out);
  tour.check('step 2: the model is read: storeys and element counts by class', m.code === 0 && /82/.test(m.out) && /IfcWallStandardCase/.test(m.out), m.out.slice(0, 200) || m.err.slice(-100));
  const l = py('link.py', '--xer', at('schedule.json'), '--ifc', at('model.json'), '--config', CFG, '--min-coverage', '1', '-o', at('links.json'));
  tour.check('step 3: it links by the configuration (coverage 1)', l.code === 0, l.err.slice(-120));
  const links = json(readFileSync(at('links.json'), 'utf8'));
  tour.check('"how many links are accepted, how many activities have no elements and how many ties"', Array.isArray(links?.links) && 'ties' in links && 'unlinked_activities' in links, Object.keys(links ?? {}).join());
  tour.check('"activities such as plaster, screed drying and services have no geometry and stay unlinked" (activities without links remain)', (links.unlinked_activities?.length ?? 0) > 0, `${links.unlinked_activities?.length} unlinked activities`);
  tour.check('Rule: "Only accepted links ... proposed, never accepted": every link of the linker is accepted or proposed, none is invented as accepted by the agent', links.links.every((k) => ['accepted', 'proposed'].includes(k.status)));
  // step 4/5: a proposal by the agent and the decision
  const code = links.unlinked_activities[0]?.task_code ?? links.unlinked_activities[0];
  const prop = [{ activity: code, role: 'build', elements: [links.links[0].elements[0]], confidence: 0.5, reasons: ['tour: the name says so'] }];
  writeFileSync(at('mine.json'), JSON.stringify(prop));
  const p = py('link.py', '--xer', at('schedule.json'), '--ifc', at('model.json'), '--config', CFG, '--proposals', at('mine.json'), '-o', at('links-p.json'));
  const lp = json(readFileSync(at('links-p.json'), 'utf8'));
  tour.check('step 4: a proposal of an agent is kept as "proposed", with its reasons', p.code === 0 && lp.links.some((k) => k.id === `ln-${code}-build-proposed` && k.source === 'agent' && k.status === 'proposed' && k.reasons?.length), p.err.slice(-120));
});

await tour.step('33.3 Try it step 6; 33.4 steps 5-9: write the IFC, verify, write the XER, animation, check', async () => {
  const a = py('apply_links.py', '--ifc', FZK, '--links', at('links-p.json'), '--xer', XER, '-o', at('model.4d.ifc'));
  tour.check('step 5 (33.4): apply_links.py writes model.4d.ifc to a new file', a.code === 0 && existsSync(at('model.4d.ifc')), a.err.slice(-120));
  const v = py('verify.py', '--ifc', at('model.4d.ifc'), '--links', at('links-p.json'));
  tour.check('"then run verify.py. It must pass."', v.code === 0, (v.out + v.err).slice(-160));
  const orig = readFileSync(FZK), outb = readFileSync(at('model.4d.ifc'));
  tour.check('"Every output is a new file": the original is not touched', sha(FZK) === createHash('sha256').update(orig).digest('hex') && outb.length > orig.length);
  const t = outb.toString('latin1');
  tour.check('"the work schedule, tasks with dates, task-to-element assignments, the logic between tasks, and Xray_4D"', /IFCWORKSCHEDULE/.test(t) && /IFCTASKTIME/.test(t) && /IFCRELASSIGNSTOPRODUCT/.test(t) && /IFCRELSEQUENCE/.test(t) && /Xray_4D/.test(t));
  tour.check('"Only accepted links are written": the proposed link\'s id never reaches the IFC', !/tour: the name says so|ln-A\d+-build-proposed/.test(t));
  tour.check('"Never write reviewed_by"', !/reviewed_by|ReviewedBy/.test(t));
  const a2 = py('apply_links.py', '--ifc', at('model.4d.ifc'), '--links', at('links-p.json'), '--xer', XER, '-o', at('model2.4d.ifc'));
  const count = (f, e) => (readFileSync(f).toString('latin1').match(new RegExp(`=${e}\\(`, 'g')) ?? []).length;
  tour.check('"Running again replaces the Xray 4D schedule ... not duplicated": a second run on the written file has the same number of work schedules, tasks and sequences', a2.code === 0 && count(at('model.4d.ifc'), 'IFCWORKSCHEDULE') === 1 && ['IFCWORKSCHEDULE', 'IFCTASK', 'IFCRELSEQUENCE'].every((e) => count(at('model.4d.ifc'), e) === count(at('model2.4d.ifc'), e)), `${count(at('model.4d.ifc'), 'IFCTASK')} tasks`);
  const x = py('xer_write.py', '--xer', XER, '--links', at('links-p.json'), '-o', at('schedule.4d.xer'));
  const xt = readFileSync(at('schedule.4d.xer'), 'latin1');
  tour.check('step 6: "Three activity user fields are added to a copy": 4D Elements, 4D Status, 4D Model', x.code === 0 && ['4D Elements', '4D Status', '4D Model'].every((f) => xt.includes(f)), x.err.slice(-100));
  tour.check('"4D Status: linked, proposed, tie, no elements or no geometry"', /\blinked\b/.test(xt) && /\bproposed\b/.test(xt) && /no elements/.test(xt) && /no geometry/.test(xt));
  const x2 = py('xer_write.py', '--xer', at('schedule.4d.xer'), '--links', at('links-p.json'), '-o', at('schedule2.4d.xer'));
  tour.check('"The 4D fields are replaced, not duplicated": writing the XER again gives the same bytes and one 4D Status field', x2.code === 0 && sha(at('schedule.4d.xer')) === sha(at('schedule2.4d.xer')) && (readFileSync(at('schedule2.4d.xer'), 'latin1').match(/4D Status/g) ?? []).length === 1);
  const an = py('anim_write.py', '--links', at('links.json'), '--ifc', at('model.json'), '--trade', 'MASON-EXT', '--length', '30', '-o', at('build.xrayanim'));
  tour.check('step 7: "Write an animation ... select by trade" writes a .xrayanim', an.code === 0 && existsSync(at('build.xrayanim')), (an.err + an.out).slice(-160));
  const an2 = py('anim_write.py', '--links', at('links.json'), '--ifc', at('model.json'), '--length', '30', '-o', at('all.xrayanim'));
  const at1 = readFileSync(at('all.xrayanim'), 'utf8');
  tour.check('"captions give the date and activity" in the script', /caption /.test(at1) && /fly to /.test(at1), at1.split('\n').slice(0, 3).join(' | ').slice(0, 120));
  const c = run('node', [resolve(S, 'xrayanim_check.mjs'), at('all.xrayanim')]);
  tour.check('step 8: "node xrayanim_check.mjs" compiles the script with the viewer\'s own compiler without errors', c.code === 0, (c.out + c.err).slice(-200));
  writeFileSync(at('broken.xrayanim'), 'flyto everything\n');
  tour.check('"Every error is fixed before the file is handed over": a broken script is reported by the check', run('node', [resolve(S, 'xrayanim_check.mjs'), at('broken.xrayanim')]).code !== 0);
  void an2;
});

await tour.step('33.3 step 7: the written IFC links again natively (xray-4d reads it back)', async () => {
  writeFileSync(at('empty.4d.json'), '{"schema":"xray-4d-config/1","schedule":{},"model":{}}\n');
  const r = run('node', [resolve(webRoot, 'tools/xray-4d.mjs'), 'link', at('model.4d.ifc'), XER, '--config', at('empty.4d.json'), '-o', at('back.json')]);
  const back = json(readFileSync(at('back.json'), 'utf8'));
  tour.check('"Open model.4d.ifc ... The 4D tab links come back as accepted": native accepted links with no configuration', r.code === 0 && back.links.filter((l) => l.source === 'native' && l.status === 'accepted').length > 10, r.err.split('\n').find((l) => /coverage/.test(l)));
});

await tour.finish();
