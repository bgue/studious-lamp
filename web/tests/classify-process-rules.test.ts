// The process-context rules: the same words mean piping in a process facility and HVAC or plumbing in a building. The schema decides
// (default-schema.json): PIP/UTL "air, steam, water and nitrogen", PIP/PMP "process pumps and compressors", MEC/HYD "heating and cooling
// water piping", PLB "building plumbing", division 40 "instrumentation and control of process systems".

import { describe, expect, it } from 'vitest';
import { ClassifyService, buildInputs, classByRules, defaultSchema, isBuildingContext, isProcessContext, isProcessModel, processEvidenceOf, resolveRule, validateSettings } from '../src/classify';
import type { ClassifyInput } from '../src/classify';
import { sidecarModel } from './classify-helpers';

const schema = defaultSchema();
const storey = { ifcClass: 'IfcBuildingStorey', name: 'Level 1', globalId: 'storey:1' };
const mk = (over: Partial<ClassifyInput>): ClassifyInput => ({ id: 'G', ifcClass: 'IfcPipeSegment', name: 'Pipe', psets: {}, hierarchy: { path: [storey] }, ...over });
const process = (over: Partial<ClassifyInput>): ClassifyInput => mk({ processContext: true, ...over });
const attr = (o: Record<string, string>): ClassifyInput['psets'] => ({ Attr: o });
const got = (i: ClassifyInput) => {
  const h = classByRules(i)!;
  const d = resolveRule(h, schema, isBuildingContext(i))!;
  return { key: `${d.discipline}/${d.subDiscipline}/${d.division}`, final: h.confidence >= 0.85 };
};

describe('process context: piping', () => {
  it('cooling water, steam and condensate piping is PIP/UTL in a process facility and MEC/HYD in a building', () => {
    for (const sys of ['Cooling water supply', 'Steam', 'Condensate']) {
      expect(got(process({ systems: [sys] })).key).toBe('PIP/UTL/40');
    }
    expect(got(mk({ systems: ['Cooling water supply'] })).key).toBe('MEC/HYD/23');
    expect(got(mk({ systems: ['Steam'] })).key).toBe('MEC/HYD/23');
    expect(got(mk({ systems: ['Chilled water'] })).key).toBe('MEC/HYD/23');
  });

  it('process and flare services are PIP/PRC; domestic water stays PLB even in a process facility', () => {
    expect(got(process({ systems: ['Process - Crude feed'] })).key).toBe('PIP/PRC/40');
    expect(got(process({ systems: ['Flare'] })).key).toBe('PIP/PRC/40');
    expect(got(process({ systems: ['Domestic cold water'] })).key).toBe('PLB/SUP/22');
    expect(got(mk({ systems: ['Domestic cold water'] })).key).toBe('PLB/SUP/22');
  });

  it('a Service property counts as a system name, and a line number alone makes a process pipe', () => {
    expect(got(process({ psets: { Pset_PipeSegmentTypeCommon: { Service: 'Condensate' } } })).key).toBe('PIP/UTL/40');
    expect(got(process({ psets: { Pset_PipeSegmentTypeCommon: { LineNumber: '100-PR-1001-A1A' } } })).key).toBe('PIP/PRC/40');
  });

  it('a lone line number or a lone utility word does not make a process context', () => {
    expect(isProcessContext(mk({ psets: { X: { LineNumber: '100-PR-1001-A1A' } } }))).toBe(false);
    expect(isProcessContext(mk({ systems: ['Steam'] }))).toBe(false);
    expect(isProcessContext(mk({ systems: ['Steam'], psets: { X: { LineNumber: '100-ST-1001-A1A' } } }))).toBe(true);
  });

  it('fire water stays fire protection in a process facility', () => {
    expect(got(process({ systems: ['Fire water ring main'] })).key).toMatch(/^FPR\/SPR/);
  });

  it('a valve in a utility line is PIP/VLV; a regulating valve is a control valve (INS/CTL) in a process facility only', () => {
    expect(got(process({ ifcClass: 'IfcValve', systems: ['Steam'], psets: attr({ PredefinedType: 'ISOLATING' }) })).key).toBe('PIP/VLV/40');
    expect(got(process({ ifcClass: 'IfcValve', systems: ['Steam'], psets: attr({ PredefinedType: 'REGULATING' }) })).key).toBe('INS/CTL/40');
    expect(got(mk({ ifcClass: 'IfcValve', systems: ['Chilled water'], psets: attr({ PredefinedType: 'REGULATING' }) })).key).toMatch(/^MEC\//);
  });
});

describe('process context: equipment and instruments', () => {
  it('a pump, vessel and heat exchanger are process equipment in a process facility, building equipment otherwise', () => {
    expect(got(process({ ifcClass: 'IfcPump', name: 'P-101A', psets: attr({ PredefinedType: 'ENDSUCTION' }) })).key).toBe('PIP/PMP/43');
    expect(got(process({ ifcClass: 'IfcTank', name: 'V-301', psets: attr({ PredefinedType: 'VESSEL' }) })).key).toBe('PIP/VES/43');
    expect(got(process({ ifcClass: 'IfcHeatExchanger', name: 'E-201' })).key).toBe('PIP/HTX/42');
    expect(got(mk({ ifcClass: 'IfcPump', name: 'CHW pump 1', systems: ['Chilled water'] })).key).toBe('MEC/EQP/23');
    expect(got(mk({ ifcClass: 'IfcTank', name: 'Expansion tank', systems: ['Domestic cold water'] })).key).toMatch(/^PLB\/EQP/);
    expect(got(mk({ ifcClass: 'IfcHeatExchanger', name: 'Plate HX' })).key).toMatch(/^MEC\/EQP/);
  });

  it('a fire pump stays fire protection in a process facility', () => {
    expect(got(process({ ifcClass: 'IfcPump', name: 'Fire pump FP-1', systems: ['Fire water'] })).key).toMatch(/^FPR\//);
  });

  it('a motor that names the machine it drives is part of that pump, only in a process facility', () => {
    const motor = { ifcClass: 'IfcElectricMotor', name: 'Motor M-1', psets: { Pset_ElectricMotorCommon: { Driver: 'P-101A' } } };
    expect(got(process(motor)).key).toBe('PIP/PMP/43');
    expect(got(mk(motor)).key).toMatch(/^ELE\/PWR/);
  });

  it('equipment parts (baseplate, saddle, skirt, channel) follow their equipment only in a process facility', () => {
    const proxy = (name: string, type: string) => ({ ifcClass: 'IfcBuildingElementProxy', name, psets: attr({ ObjectType: type }) });
    expect(got(process(proxy('Pump baseplate', 'Pump baseplate 2 m'))).key).toBe('PIP/PMP/43');
    expect(got(process(proxy('Exchanger saddle', 'Saddle support'))).key).toBe('PIP/HTX/42');
    expect(got(process(proxy('Exchanger channel', 'Channel (front head)'))).key).toBe('PIP/HTX/42');
    expect(got(process(proxy('Vessel skirt', 'Vessel skirt'))).key).toBe('PIP/VES/43');
    expect(classByRules(mk(proxy('Pump baseplate', 'Pump baseplate 2 m')))).toBeNull();
  });

  it('a sensor is INS/SNS with division 40 in a process facility and 25 in a building', () => {
    expect(got(process({ ifcClass: 'IfcSensor', name: 'PT-1' })).key).toBe('INS/SNS/40');
    expect(got(mk({ ifcClass: 'IfcSensor', name: 'Room sensor' })).key).toBe('INS/SNS/25');
  });
});

describe('supports', () => {
  const member = (name: string, type: string, extra: Partial<ClassifyInput> = {}) => mk({ ifcClass: 'IfcMember', name, psets: attr({ ObjectType: type }), ...extra });

  it('a member that says pipe support, guide or sleeper is PIP/SUP, with division 40 in a process facility', () => {
    expect(got(process(member('Post', 'Pipe support post'))).key).toBe('PIP/SUP/40');
    expect(got(process(member('Arm', 'Riser guide arm'))).key).toBe('PIP/SUP/40');
    expect(got(process({ ifcClass: 'IfcBuildingElementProxy', name: 'PSL-01', psets: attr({ ObjectType: 'Concrete pipe sleeper' }) })).key).toBe('PIP/SUP/40');
    expect(got(member('Pipe hanger H1', 'Pipe hanger', { systems: ['Domestic cold water'] })).key).toBe('PIP/SUP/22');
  });

  it('a member that supports a cable tray goes with the tray, ELE/CND', () => {
    expect(got(process(member('Tray T-support post', 'Tray support post'))).key).toBe('ELE/CND/26');
    expect(got(process(member('Arm', 'Tray riser arm'))).key).toBe('ELE/CND/26');
  });

  it('an ordinary brace or member is still STR/BRC', () => {
    expect(got(process(member('Rack brace', 'Brace L75'))).key).toBe('STR/BRC/05');
    expect(got(mk({ ifcClass: 'IfcMember', name: 'Guide rail for lift', psets: attr({ ObjectType: 'Lift guide rail' }) })).key).toBe('STR/BRC/05');
  });
});

describe('bracing and connection parts', () => {
  it('a member named as bracing and a plate named as a base or gusset plate are STR/BRC and final; an unnamed member stays weak', () => {
    const m = classByRules(mk({ ifcClass: 'IfcMember', name: 'Rack bracing BR-A01' }))!;
    expect(m).toMatchObject({ discipline: 'STR', subDiscipline: 'BRC' });
    expect(m.confidence).toBeGreaterThanOrEqual(0.85);
    expect(classByRules(mk({ ifcClass: 'IfcPlate', name: 'Column base plate BP-01A' }))!.confidence).toBeGreaterThanOrEqual(0.85);
    expect(classByRules(mk({ ifcClass: 'IfcPlate', name: 'Plate P1' }))!.confidence).toBeLessThan(0.85);
    expect(classByRules(mk({ ifcClass: 'IfcMember', name: 'Member M1' }))!.confidence).toBeLessThan(0.85);
  });
});

describe('masonry and grating', () => {
  it('a load-bearing masonry wall is structural with division 04; a concrete one keeps 03', () => {
    expect(got(mk({ ifcClass: 'IfcWall', name: 'Wall S', psets: { Pset_WallCommon: { LoadBearing: true }, Attr: { ObjectType: 'Masonry 300 mm' } } })).key).toBe('STR/WLS/04');
    expect(got(mk({ ifcClass: 'IfcWall', name: 'Wall S', psets: { Pset_WallCommon: { LoadBearing: true }, Attr: { ObjectType: 'Concrete 200 mm' } } })).key).toBe('STR/WLS/03');
  });

  it('a steel grating floor panel is a metal deck, division 05', () => {
    expect(got(mk({ ifcClass: 'IfcSlab', name: 'Grating panel', psets: { Attr: { ObjectType: 'Steel grating 2.0 x 2.0', PredefinedType: 'FLOOR' } } })).key).toBe('STR/SLB/05');
  });
});

describe('the model-level context', () => {
  it('needs two kinds of evidence on three elements', () => {
    const line = processEvidenceOf(mk({ psets: { X: { LineNumber: '100-PR-1001-A1A' } } }));
    const service = processEvidenceOf(mk({ systems: ['Flare'] }));
    expect(line).toEqual(['line']);
    expect(service).toEqual(['service']);
    expect(isProcessModel([line, line, line])).toBe(false);
    expect(isProcessModel([line, service, []])).toBe(false);
    expect(isProcessModel([line, line, service])).toBe(true);
  });

  it('is set on the process plant and on no other bundled model', () => {
    for (const [name, want] of [['process-plant', true], ['building', false], ['fzk-haus', false], ['plumbing', false], ['synth5k', false], ['debris-demo', false]] as const) {
      const inputs = buildInputs(sidecarModel(name));
      expect(inputs.every((i) => (i.processContext === true) === want), name).toBe(true);
    }
  });
});

describe('rulesMode: rules where certain, else the model', () => {
  it('validates, defaults to final, and warns when off with no provider', () => {
    expect(validateSettings({}).settings.rulesMode).toBe('final');
    expect(validateSettings({ rulesMode: 'off', provider: 'mock' })).toMatchObject({ errors: [], settings: { rulesMode: 'off' } });
    expect(validateSettings({ rulesMode: 'rules' }).errors[0]).toBe('rulesMode must be one of final, off. Using "final".');
    expect(validateSettings({ rulesMode: 'off' }).warnings.join(' ')).toMatch(/nothing will be classified/);
  });

  it('final: a final rule decides discipline, sub and division together and the model sees only the rest; off: the model sees everything', async () => {
    const model = sidecarModel('fzk-haus');
    const run = async (rulesMode: 'final' | 'off') => {
      const svc = new ClassifyService({ storage: null, keyStorages: { session: null, local: null } });
      svc.setModel(model, 'fzk-haus');
      svc.patch({ provider: 'mock', rulesMode });
      const results = await svc.classify('all');
      return { svc, results, bySource: svc.stats().bySource };
    };
    const final = await run('final');
    const off = await run('off');
    expect(final.bySource.rules).toBeGreaterThan(0);
    expect(off.bySource.rules).toBe(0);
    expect(final.svc.stats().signatures).toBeLessThan(off.svc.stats().signatures);
    // the estimate follows the mode
    expect(final.svc.estimate('all').byRules).toBeGreaterThan(0);
    expect(off.svc.estimate('all').byRules).toBe(0);
    for (const r of final.results.filter((x) => x.source === 'rules')) {
      expect(r.rationale).toBeTruthy();
      expect(r.discipline.confidence).toBeGreaterThanOrEqual(0.85);
    }
    // changing the mode does not rebuild the provider (it is not a provider setting)
    const p = final.svc.provider();
    final.svc.patch({ rulesMode: 'off' });
    expect(final.svc.provider()).toBe(p);
  });
});
