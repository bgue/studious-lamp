// Pure checks of a ground-truth file (xray-truth/1) for tools/classify-truth.mjs. No I/O, so tests can import it.
//
// alt may hold discipline (informational), subDiscipline (same discipline, scored), division (scored), also ("DISC/sub" pairs, informational).
// Errors (the CLI exits non-zero): wrong format or no `elements` object; an entry that is not an object; a discipline, sub-discipline
// or division that the schema does not have (a sub-discipline must belong to the entry's discipline); an `alt` code that does not
// exist; and, once the model is known, an element of the model that has no truth entry.
// Warnings: a truth entry without an element in the model (the converter skips openings and spaces, so a few can be legitimate).

/** The sets of valid codes of a classification schema (default-schema.json). */
export function schemaCodes(schema) {
  const subs = new Map(schema.disciplines.map((d) => [d.code, new Set(d.subDisciplines.map((s) => s.code))]));
  const divisions = new Set(schema.masterformat.divisions.map((d) => d.division));
  return { subs, divisions };
}

/** Check the truth document against the schema. Returns { errors: string[], warnings: string[], entries: number }. */
export function validateTruth(doc, schema) {
  const errors = [];
  const warnings = [];
  const { subs, divisions } = schemaCodes(schema);
  if (!doc || typeof doc !== 'object') return { errors: ['the truth file is not a JSON object'], warnings, entries: 0 };
  if (doc.format !== 'xray-truth/1') errors.push(`format is ${JSON.stringify(doc.format)}, expected "xray-truth/1"`);
  const els = doc.elements;
  if (!els || typeof els !== 'object' || Array.isArray(els)) return { errors: [...errors, 'no "elements" object'], warnings, entries: 0 };
  const bad = (id, msg) => { if (errors.length < 200) errors.push(`${id}: ${msg}`); };
  let n = 0;
  for (const [id, t] of Object.entries(els)) {
    n++;
    if (!t || typeof t !== 'object') { bad(id, 'entry is not an object'); continue; }
    if (!subs.has(t.discipline)) bad(id, `unknown discipline ${JSON.stringify(t.discipline)}`);
    else if (!subs.get(t.discipline).has(t.subDiscipline)) bad(id, `unknown sub-discipline ${JSON.stringify(t.subDiscipline)} for ${t.discipline}`);
    if (!divisions.has(t.division)) bad(id, `unknown division ${JSON.stringify(t.division)}`);
    const alt = t.alt;
    if (alt !== undefined && alt !== null) {
      if (typeof alt !== 'object') { bad(id, 'alt is not an object'); continue; }
      for (const d of alt.discipline ?? []) if (!subs.has(d)) bad(id, `unknown alt discipline ${JSON.stringify(d)}`);
      // An alternate sub-discipline is judged under the entry's own discipline (the bench builds "DISC/sub" from it).
      for (const s of alt.subDiscipline ?? []) if (!subs.get(t.discipline)?.has(s)) bad(id, `unknown alt sub-discipline ${JSON.stringify(s)} for ${t.discipline}`);
      for (const pair of alt.also ?? []) { const [d, sub] = String(pair).split('/'); if (!subs.get(d)?.has(sub)) bad(id, `unknown alt pair ${JSON.stringify(pair)}`); }
      for (const v of alt.division ?? []) if (!divisions.has(v)) bad(id, `unknown alt division ${JSON.stringify(v)}`);
    }
  }
  if (n === 0) errors.push('the truth file has no entries');
  return { errors, warnings, entries: n };
}

/** Join of the truth file and the model's elements (global ids). */
export function joinTruth(doc, elementIds) {
  const truth = new Set(Object.keys(doc.elements ?? {}));
  const ids = new Set(elementIds);
  const withoutTruth = [...ids].filter((g) => !truth.has(g));
  const withoutElement = [...truth].filter((g) => !ids.has(g));
  return { withoutTruth, withoutElement };
}
