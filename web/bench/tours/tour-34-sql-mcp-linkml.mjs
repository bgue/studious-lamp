// Tour of chapter 34, "SQL, MCP and LinkML" (docs/manual/34-sql-mcp-linkml.md): the schema files (34.1), the keys and statuses (34.2), the tables (34.3),
// the three SQL queries of 34.4 run in SQLite on a dataset written by `xray-4d link`, and the JSON Schema check of 34.5. Python 3 (sqlite3, jsonschema) does
// the database part. The MCP server of 34.1 is a program for agents and is not run. No picture notes in this chapter.
// Run: node bench/run-smokes.mjs --only tour-34-sql-mcp-linkml
import { spawnSync } from 'node:child_process';
import { existsSync, mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { repoRoot, startTour, webRoot } from './lib.mjs';

const tour = await startTour('tour-34-sql-mcp-linkml');
const out = mkdtempSync(join(tmpdir(), 'tour-34-'));
const schemaDir = resolve(repoRoot, 'schema', 'linkml');
const FZK = resolve(repoRoot, 'models', 'AC20-FZK-Haus.ifc');
const py = (script, args = []) => {
  const f = join(out, 'step.py');
  writeFileSync(f, script);
  const r = spawnSync('python3', ['-I', f, ...args], { encoding: 'utf8', timeout: 120000 });
  return { code: r.status, out: r.stdout ?? '', err: r.stderr ?? '' };
};

await tour.step('34.1 Why a schema: the generated files exist', async () => {
  for (const f of ['xray_4d.yaml', 'xray_4d.sql', 'xray_4d.schema.json', 'generate.sh']) tour.check(`the table lists ${f}`, existsSync(resolve(schemaDir, f)));
  tour.check('the table lists examples/', existsSync(resolve(schemaDir, 'examples')) && /^model:/m.test(readFileSync(resolve(schemaDir, 'examples/LinkDataset-fzk.yaml'), 'utf8')) && /^links:/m.test(readFileSync(resolve(schemaDir, 'examples/LinkDataset-fzk.yaml'), 'utf8')));
  const sql = readFileSync(resolve(schemaDir, 'xray_4d.sql'), 'utf8');
  tour.check('"SQL tables, one per class, join tables for lists, foreign keys to Activity(task_code) and Element(global_id)"',
    /CREATE TABLE "Activity"/.test(sql) && /CREATE TABLE "Element"/.test(sql) && /CREATE TABLE "ActivityLink_elements"/.test(sql) && /REFERENCES "Activity" \(task_code\)/.test(sql) && /REFERENCES "Element" \(global_id\)/.test(sql));
});

let dataset = '';
await tour.step('34.4 Try it: a dataset like the one Export links wrote, loaded into SQLite', async () => {
  dataset = join(out, 'links.json');
  const r = spawnSync('node', [resolve(webRoot, 'tools/xray-4d.mjs'), 'link', FZK, resolve(webRoot, 'public/samples/fzk-haus.xer'), '--config', resolve(webRoot, 'public/samples/fzk-haus.4d.json'), '-o', dataset], { cwd: webRoot, encoding: 'utf8', timeout: 240000 });
  tour.check('xray-4d link writes the link dataset', r.status === 0 && existsSync(dataset), r.stderr.slice(-100));
  const run = py(`
import json, sqlite3, sys
d = json.load(open(sys.argv[1])); sql = open(sys.argv[2]).read()
c = sqlite3.connect(':memory:'); c.executescript(sql); c.execute('PRAGMA foreign_keys=ON')
m, s = d['model'], d['schedule']
c.execute('INSERT INTO ModelRef(identity_key,name,file_name) VALUES (?,?,?)', (m['identity_key'], m.get('name'), m.get('file_name')))
c.execute('INSERT INTO ScheduleRef(source_hash,project,data_date,file_name) VALUES (?,?,?,?)', (s['source_hash'], s.get('project'), s.get('data_date'), s.get('file_name')))
c.execute('INSERT INTO LinkDataset(id,tool,model_identity_key,schedule_source_hash) VALUES (?,?,?,?)', (d['id'], d.get('tool'), m['identity_key'], s['source_hash']))
for a in d['activities']:
    c.execute('INSERT INTO Activity(task_code,name,wbs_path,activity_type,activity_status,start,finish,location,trade,zone,critical,LinkDataset_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
              (a['task_code'], a.get('name'), a.get('wbs_path'), a.get('activity_type'), a.get('activity_status'), a.get('start'), a.get('finish'), a.get('location'), a.get('trade'), a.get('zone'), a.get('critical'), d['id']))
for e in d['model_elements']:
    c.execute('INSERT INTO Element(global_id,ifc_class,name,storey,location,trade,zone,LinkDataset_id) VALUES (?,?,?,?,?,?,?,?)', (e['global_id'], e.get('ifc_class'), e.get('name'), e.get('storey'), e.get('location'), e.get('trade'), e.get('zone'), d['id']))
for l in d['links']:
    c.execute('INSERT INTO ActivityLink(id,activity,role,source,confidence,split,rule,status,LinkDataset_id) VALUES (?,?,?,?,?,?,?,?,?)', (l['id'], l['activity'], l['role'], l.get('source'), l.get('confidence'), l.get('split'), l.get('rule'), l.get('status'), d['id']))
    for g in l['elements']: c.execute('INSERT INTO ActivityLink_elements VALUES (?,?)', (l['id'], g))
# a proposal from an "agent", as the chapter describes
c.execute("INSERT INTO ActivityLink(id,activity,role,source,confidence,status,LinkDataset_id) VALUES ('ln-agent-1','A1000','build','agent',0.55,'proposed',?)", (d['id'],))
g0 = d['links'][0]['elements'][0]
c.execute("INSERT INTO ActivityLink_elements VALUES ('ln-agent-1',?)", (g0,))
c.execute("INSERT INTO Assignment(id,element,attribute,value,source,confidence,status,LinkDataset_id) VALUES ('as-1',?, 'trade','CONC','agent',0.6,'proposed',?)", (g0, d['id']))
q1 = c.execute('''SELECT l.id, l.activity AS task_code, l.role, e.elements_global_id AS global_id FROM "ActivityLink" l
 JOIN "ActivityLink_elements" e ON e."ActivityLink_id" = l.id WHERE l.status = 'accepted' ORDER BY l.activity, e.elements_global_id''').fetchall()
q2 = c.execute('''SELECT 'link' AS kind, id, activity AS subject, source, confidence FROM "ActivityLink" WHERE status = 'proposed'
 UNION ALL SELECT 'assignment', id, element, source, confidence FROM "Assignment" WHERE status = 'proposed' ''').fetchall()
c.execute("INSERT INTO Assignment(id,element,attribute,value,source,confidence,status,created_at,LinkDataset_id) VALUES ('as-2',?, 'trade','OLD','manual',1,'accepted','2027-01-01T00:00:00',?)", (g0, d['id']))
c.execute("INSERT INTO Assignment(id,element,attribute,value,source,confidence,status,created_at,LinkDataset_id) VALUES ('as-3',?, 'trade','NEW','manual',1,'accepted','2027-02-01T00:00:00',?)", (g0, d['id']))
q3 = c.execute('''SELECT element, attribute, value FROM "Assignment" s WHERE s.status = 'accepted' AND s.created_at = (SELECT MAX(created_at) FROM "Assignment" t WHERE t.element = s.element AND t.attribute = s.attribute AND t.status = 'accepted')''').fetchall()
fk = c.execute('PRAGMA foreign_key_check').fetchall()
try:
    c.execute("INSERT INTO ActivityLink(id,activity,role,status) VALUES ('bad','NO-SUCH-ACTIVITY','build','accepted')"); bad_fk = False
except sqlite3.IntegrityError: bad_fk = True
print(json.dumps({'accepted_rows': len(q1), 'json_accepted_elements': sum(len(l['elements']) for l in d['links'] if l['status']=='accepted'), 'first': q1[0] if q1 else None,
  'review': q2, 'newest': q3, 'fk_problems': len(fk), 'bad_fk_refused': bad_fk}))
`, [dataset, resolve(schemaDir, 'xray_4d.sql')]);
  tour.check('the generated xray_4d.sql loads into SQLite and the dataset imports', run.code === 0, run.err.split('\n').slice(-3).join(' | '));
  if (run.code !== 0) return;
  const r2 = JSON.parse(run.out);
  tour.check('"Accepted links with one row per element": one row for each element of each accepted link', r2.accepted_rows > 50 && r2.accepted_rows === r2.json_accepted_elements, `${r2.accepted_rows} rows, ${r2.json_accepted_elements} in the file`);
  tour.check('the row has id, task_code, role and global_id', r2.first && /^ln-/.test(r2.first[0]) && /^A\d+/.test(r2.first[1]) && r2.first[2] === 'build' && r2.first[3].length === 22, JSON.stringify(r2.first));
  tour.check('"What is waiting for review": the proposed link and assignment of an agent show up with source agent', r2.review.length === 2 && r2.review.every((r) => r[3] === 'agent'), JSON.stringify(r2.review));
  tour.check('"the current accepted ... when there is more than one accepted row, is the newest"', r2.newest.some((r) => r[2] === 'NEW') && !r2.newest.some((r) => r[2] === 'OLD'), JSON.stringify(r2.newest.filter((r) => r[1] === 'trade').slice(0, 2)));
  tour.check('keys: "An activity is its P6 Activity ID ... An element is its IFC GlobalId": foreign keys hold and an unknown activity is refused', r2.fk_problems === 0 && r2.bad_fk_refused);
});

await tour.step('34.5 The JSON Schema checks a links.json', async () => {
  const run = py(`
import json, sys, copy
from jsonschema import Draft202012Validator, Draft7Validator
schema = json.load(open(sys.argv[2])); d = json.load(open(sys.argv[1]))
V = Draft202012Validator if '2020-12' in schema.get('$schema', '') else Draft7Validator
v = V(schema)
res = {'good': len(list(v.iter_errors(d)))}
b = copy.deepcopy(d); b['links'][0]['status'] = 'maybe'; res['bad_status'] = len(list(v.iter_errors(b)))
b = copy.deepcopy(d); b['links'][0]['confidence'] = 1.5; res['bad_conf'] = len(list(v.iter_errors(b)))
b = copy.deepcopy(d); b['links'][0]['elements'] = []; res['no_elements'] = len(list(v.iter_errors(b)))
print(json.dumps(res))
`, [dataset, resolve(schemaDir, 'xray_4d.schema.json')]);
  tour.check('the validator runs', run.code === 0, run.err.split('\n').slice(-2).join(' | '));
  if (run.code !== 0) return;
  const r = JSON.parse(run.out);
  tour.check('a dataset written by xray-4d passes the JSON Schema', r.good === 0, `${r.good} errors`);
  tour.check('"refuse a dataset that has a bad status"', r.bad_status > 0);
  tour.check('"... a confidence outside 0 to 1"', r.bad_conf > 0);
  tour.check('"... a link with no elements (a link needs at least one)"', r.no_elements > 0);
});

await tour.step('34.6/34.7 Review with an agent: the privacy rules', async () => {
  const text = readFileSync(dataset, 'utf8');
  tour.check('"reviewed_by ... the viewer never writes it": the dataset has no reviewed_by value', !/"reviewed_by":\s*"/.test(text));
});

await tour.finish();
