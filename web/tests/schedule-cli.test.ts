// The xray-4d CLI (tools/xray-4d.mjs) run as a process on the XER fixtures: the inspect JSON, the report, and exit codes.
import { spawnSync } from 'node:child_process';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

const web = resolve(__dirname, '..');
const execPath = (globalThis as unknown as { process: { execPath: string } }).process.execPath;
const cli = resolve(web, 'tools/xray-4d.mjs');
const fx = (name: string): string => resolve(web, 'tests/fixtures/xer', name);
const run = (...args: string[]) => spawnSync(execPath, [cli, ...args], { cwd: web, encoding: 'utf8', timeout: 120000 });

describe('xray-4d inspect', () => {
  it('prints the JSON summary of the building fixture', () => {
    const r = run('inspect', fx('building.xer'), '--json');
    expect(r.status).toBe(0);
    const j = JSON.parse(r.stdout);
    expect(j.schema).toBe('xray-4d-inspect/1');
    expect(j.file).toBe('building.xer');
    expect(j.encoding).toBe('utf-8');
    expect(j.sourceHash).toMatch(/^[0-9a-f]{64}$/);
    expect(j.project).toMatchObject({ shortName: 'BLD-A', name: 'Tower A', dataDate: '2027-03-12T08:00', calendarId: '1' });
    expect(j.activities.total).toBe(41);
    expect(j.activities.byType).toEqual({ task: 32, milestone: 2, finishMilestone: 4, loe: 2, wbsSummary: 1 });
    expect(j.activities.byStatus).toEqual({ complete: 15, active: 4, notStarted: 22 });
    expect(j.relations).toEqual({ total: 38, byType: { FS: 28, SS: 9, FF: 1 } });
    const level = j.codes.find((c: { type: string }) => c.type === 'Level');
    expect(level.values).toContainEqual({ value: 'L01', count: 11 });
    expect(level.withoutValue).toBe(0);
    expect(j.udfs).toEqual([{ label: 'Crew Size', count: 31 }]);
    const std = j.calendars.find((c: { id: string }) => c.id === '1');
    expect(std.holidays).toEqual(['2026-12-25', '2027-01-01']);
    expect(std.partDays).toEqual([{ date: '2026-12-24', hours: '08:00-12:00' }]);
    expect(std.week.Mon).toBe('08:00-12:00, 13:00-17:00');
    expect(j.wbs).toHaveLength(1);
    expect(j.wbs[0]).toMatchObject({ shortName: 'BLD-A', activities: 41 });
    expect(j.wbs[0].children.map((c: { shortName: string }) => c.shortName)).toEqual(['PRE', 'L00', 'L01', 'L02', 'ROOF', 'EXT']);
    expect(j.wbs[0].children[1].children.map((c: { shortName: string }) => c.shortName)).toEqual(['STR', 'MEP']);
    expect(j.warnings).toEqual([]);
  });

  it('limits the WBS tree with --depth', () => {
    const j = JSON.parse(run('inspect', fx('building.xer'), '--json', '--depth', '0').stdout);
    expect(j.wbs[0].children).toEqual([]);
    expect(j.wbs[0].truncated).toBe(true);
    const k = JSON.parse(run('inspect', fx('building.xer'), '--json', '--depth=1').stdout);
    expect(k.wbs[0].children[1].children).toEqual([]);
    expect(k.wbs[0].children[1].truncated).toBe(true);
  });

  it('chooses a project of a two-project file with --project, and asks for one without it', () => {
    const j = JSON.parse(run('inspect', fx('two-projects.xer'), '--project', 'BLD-B', '--json').stdout);
    expect(j.project.shortName).toBe('BLD-B');
    expect(j.projects.map((p: { shortName: string }) => p.shortName)).toEqual(['BLD-A', 'BLD-B']);
    expect(j.activities.total).toBe(4);
    const r = run('inspect', fx('two-projects.xer'));
    expect(r.status).toBe(3);
    expect(r.stderr).toMatch(/2 projects.*BLD-A, BLD-B/);
  });

  it('prints the readable report with the file, project, counts, codes, calendars and WBS', () => {
    const r = run('inspect', fx('windows-1252-names.xer'));
    expect(r.status).toBe(0);
    expect(r.stdout).toMatch(/File {9}windows-1252-names\.xer/);
    expect(r.stdout).toMatch(/Project {6}LEP-OST/);
    expect(r.stdout).toMatch(/Activities {3}4 /);
    expect(r.stdout).toMatch(/Gewerk \(2 values/);
    expect(r.stdout).toMatch(/Fassade Nord – Südseite/);
    expect(r.stdout).toMatch(/Warnings \(1\)/);
    expect(r.stdout).toMatch(/calendar Baustelle \(defekt\): clndr_data could not be read/);
  });

  it('exits 2 for usage problems and 3 for input problems', () => {
    expect(run().status).toBe(2);
    expect(run('frobnicate').status).toBe(2);
    expect(run('inspect').status).toBe(2);
    expect(run('inspect', fx('building.xer'), '--bogus').status).toBe(2);
    expect(run('inspect', fx('building.xer'), '--project').status).toBe(2);
    expect(run('inspect', fx('building.xer'), '--depth', 'x').status).toBe(2);
    expect(run('inspect', fx('missing.xer')).status).toBe(3);
    const notXer = run('inspect', resolve(web, 'package.json'));
    expect(notXer.status).toBe(3);
    expect(notXer.stderr).toMatch(/not an XER file/);
  });

  it('prints help for the tool and for inspect, exit 0', () => {
    const top = run('--help');
    expect(top.status).toBe(0);
    expect(top.stdout).toMatch(/inspect/);
    const h = run('inspect', '--help');
    expect(h.status).toBe(0);
    expect(h.stdout).toMatch(/Usage: xray-4d inspect <schedule\.xer>/);
    expect(h.stdout).toMatch(/--depth N/);
  });
});
