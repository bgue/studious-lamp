# models/ provenance

## AC20-FZK-Haus.ifc (added as the "richer" model, IFC4, 2.5 MB)

- Source: https://github.com/IfcOpenShell/IfcOpenShell/blob/v0.9.0/docs/ifcopenshell-cpp/models/AC20-FZK-Haus.ifc
  (fetched with `git clone --depth 1 --filter=blob:none` plus a sparse checkout of `docs/ifcopenshell-cpp/models`).
- Content: the KIT "FZK-Haus" sample house exported from ARCHICAD 20 (Karlsruhe Institute of Technology,
  Institute for Automation and Applied Informatics). Walls, slabs, beams, stair, 5 doors and 11 windows with
  17 IfcRelVoidsElement / 16 IfcRelFillsElement relations. It has NO MEP (no ducts or pipes).
- Licence: the file carries no licence header. It is distributed inside the IfcOpenShell repository,
  whose licence is LGPL-3.0-or-later (COPYING.LESSER in the repo root). The FZK-Haus model itself is
  published by KIT as a freely usable sample; check upstream before redistributing outside this reference project.

## Building-*.ifc, Infra-*.ifc

buildingSMART Simple-Scene sample set (provided with the task; provenance not re-verified here).

## Not used

A real MEP + openings model (buildingsmart-community/Community-Sample-Test-Files, Duplex Apartment, CC BY 4.0)
exists, but its .ifc files are Git LFS objects (Duplex_MEP is 17.9 MB, Duplex_Plumbing 31.6 MB) and LFS downloads
are blocked by the session proxy, so it could not be fetched.
