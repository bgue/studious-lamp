# ext_demo: a fixture module

`ext_demo` is a test fixture, not a product module. It is never installed and has no entry point:
only tests and the P2-X4 demo load it, through `load.py` (`ext_demo_spec()`), and hand the result
to `tl_core.modules.use_modules`.

It exists to prove that the platform serves a module no platform source file names. It adds one
record type (`ext_demo.Note`, class set at add time), one command (`ExtDemoAddNote`), one read
route, one agent tool and one CLI group, all through the `ModuleSpec` hooks and all inside the
package `tl_mod_ext_demo`. A note's confidentiality class is read through the viewer's class
filter, so a hidden note answers as a missing one on every surface.

Its table, `ext_demo_note`, is created by the module's projector (plain `CREATE TABLE`, no
generated DDL, no `schema/**` file).
