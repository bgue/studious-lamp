// Friendly text for IFC reader failures (fix w7-9): web-ifc internals become one line, our own messages pass through.

import { describe, expect, it } from 'vitest';
import { IFC_UNREADABLE, IfcUnreadable, friendlyIfcError } from '../src/model/ifcErrors';
import { IfcReadError } from '../src/model/ifcRaw';

describe('friendlyIfcError', () => {
  it('rewrites a web-ifc internal error from the worker and keeps the raw text as detail', () => {
    const e = Object.assign(new Error("IFC reader failed: Cannot read properties of undefined (reading 'arguments')"), { code: 'reader' });
    const f = friendlyIfcError(e, 'bad.ifc');
    expect(f).toBeInstanceOf(IfcUnreadable);
    expect(f.message).toBe(`${IFC_UNREADABLE} (bad.ifc)`);
    expect(f.message).not.toMatch(/arguments|undefined/);
    expect((f as IfcUnreadable).detail).toBe("Cannot read properties of undefined (reading 'arguments')");
  });

  it('rewrites a raw TypeError of the main-thread reader and a crashed worker', () => {
    expect(friendlyIfcError(new TypeError('x is not a function')).message).toBe(IFC_UNREADABLE);
    expect((friendlyIfcError('boom') as IfcUnreadable).detail).toBe('boom');
    // An old worker sent code 'invalid' with the prefixed raw text: still rewritten.
    expect(friendlyIfcError(Object.assign(new Error('IFC reader failed: bad'), { code: 'invalid' }))).toBeInstanceOf(IfcUnreadable);
  });

  it('passes our own user-facing reader errors through unchanged', () => {
    const own = new IfcReadError('x.ifc is not a valid IFC file (no ISO-10303-21 header)', 'invalid');
    expect(friendlyIfcError(own, 'x.ifc')).toBe(own);
    const mem = Object.assign(new Error('The IFC file is too large for the browser to read (out of memory)'), { code: 'memory' });
    expect(friendlyIfcError(mem)).toBe(mem);
    const empty = Object.assign(new Error('e.ifc is empty'), { code: 'empty' });
    expect(friendlyIfcError(empty)).toBe(empty);
  });
});
