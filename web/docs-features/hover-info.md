# Hover info

A small card that follows the pointer once it rests on an element: the element name, `class · storey · material`, a few
properties picked by a priority list, and (optionally) the x-ray bucket and current alpha. The same properties feed a
collapsible "Properties" list in the sidebar footer.

## Using it

- Rest the pointer on an element for 350 ms (setting `delay (ms)`). No mouse button may be down.
- The card hides on pointer leave, pointer down, wheel, any key press, and when the hovered element changes (the delay
  starts again). After a key press, wheel or click it stays hidden until the pointer moves.
- **Alt freezes the card** where it is: it becomes interactive, its text can be selected, and a small **Copy** button copies
  every row as text (`key: value` lines). Release Alt, press Escape, or move away from the card (more than 40 px) to let go.
- Key **i** (action `hover.toggle`) switches `show on hover` and shows a short toast, "Hover info on" / "Hover info off".
- With `highlight` on, the hovered element is outlined while the card shows, through `renderer.setHoverHighlight(id)`.
  The call is made only when the renderer has that method.

The pick is `app.hoverId`, which the app updates on pointer move at most every 80 ms. The card reads it in `afterFrame`
and does no ray cast of its own. Because the last move inside the 80 ms window is dropped, the card can describe the element
under the pointer as it was up to 80 ms earlier; it matters only when the pointer stops exactly on an edge.

## Settings (panel folder `Hover info`)

| Control | Default | Meaning |
| --- | --- | --- |
| `show on hover` | on | Master switch (key `i`). |
| `delay (ms)` | 350 | Rest time before the card appears. |
| `max rows` | 6 | Property rows on the card (0 to 24). |
| `show x-ray state` | on | Dim footer `x-ray: <bucket> · alpha <a>` (only while x-ray is on). |
| `highlight` | on | Outline the hovered element while the card shows. |
| `property filter` | see below | Comma-separated glob patterns, in priority order. |
| `all properties in sidebar` | off | Sidebar list shows every property instead of the filtered ones. |

Default `property filter`:
`Attr.ObjectType, *.IsExternal, *.LoadBearing, *.FireRating, *.Reference, Qto*.Length, Qto*.Width, Qto*.Height, Qto*.NetVolume, *Quantities.Length, *Quantities.Width, *Quantities.Height, *Quantities.NetVolume`

Patterns match the whole key, case-insensitively; `*` is any run of characters, `?` one character. Rows are chosen pattern
by pattern, in the order written; the keys one pattern matches keep the element's own order; a key is shown once. The
`*Quantities.*` patterns catch the ArchiCAD and IFC2x3 spelling `BaseQuantities.Length` (the FZK house) as well as
`Qto_WallBaseQuantities.Length`. When the filter keeps nothing of an element (for example a set named `Dimensions`
and no `IsExternal`), the card shows the element's first `max rows` properties instead.

The settings are exported in the params document as section `hoverInfo` (not part of the share URL).

## Sidebar "Properties" list

Under the selection details, a collapsible list **Properties (n)** shows the first selected element's properties: the
filtered ones, or all of them with `all properties in sidebar`. The title reads `Properties (k of n)` while a filter is
hiding some. Click a row to copy its value. The open or closed state is remembered in `localStorage` (`xray.propsListOpen`).

## Data: `props` in the sidecar

`model.json` elements may carry an optional `props` object (`ElementRecord.props` in `src/types.ts`). Absent means no
properties; the loader tolerates that, and drops entries that are not a string, a finite number or a boolean.

```json
"props": {
  "Attr.Tag": "BC6F0F70-6195-495E-A2-FC-239713029DB1",
  "Pset_WallCommon.IsExternal": true,
  "Pset_WallCommon.FireRating": "EI60",
  "Pset_WallCommon.ThermalTransmittance": 1.5,
  "Qto_WallBaseQuantities.Length": 4.17,
  "Qto_WallBaseQuantities.NetVolume": 2.496
}
```

### Keys

- `Attr.ObjectType`, `Attr.Tag`, `Attr.Description`, `Attr.PredefinedType` (empty values and `NOTDEFINED` are left out).
- `<PsetName>.<PropName>` for an `IfcPropertySingleValue` or `IfcPropertyEnumeratedValue` (values joined by `, `).
- `<QtoName>.<QuantityName>` for the quantities of an `IfcElementQuantity`.

Only the element's own property sets are read (through `IfcRelDefinesByProperties`), not those of its type.

### Modes (`tools/ifc2glb.py --props none|common|all`, default `common`)

- `none`: no `props`.
- `common`: the four attributes, every single-value property of any set named `Pset_*Common`, and the base quantities
  `Length, Width, Height, Depth, Perimeter, NetArea, GrossArea, NetVolume, GrossVolume, NetSideArea, GrossSideArea,
  CrossSectionArea, OuterSurfaceArea, NetWeight` of a quantity set named `Qto_*BaseQuantities` or `BaseQuantities` (the
  IFC2x3 and ArchiCAD spelling).
- `all`: every single-value property and every quantity.

The browser reader (`src/model/ifcRaw.ts`) always uses `common`; `extractIfc(api, data, name, { props: 'all' })` selects
another mode. It reads `IfcRelDefinesByProperties` once, parses each property set and quantity set once however many
elements share it, and costs a few percent of the geometry time.

### Order, cap and values

Per element: attributes, then `Pset_*Common` properties, then the whitelisted quantities, then everything else (`all`
only), each group in file order (relationships by express id). First key wins on a clash. At most **24** entries.
Strings are cut to **80** characters. Reals are rounded to **4 significant digits**; `IfcInteger`, `IfcCountMeasure`
and `IfcTimeStamp` stay exact. Booleans stay booleans; `IfcLogical` UNKNOWN is left out.

### Units

Values are SI without a unit in the key: lengths in metres, areas in m2, volumes in m3, masses in kg. The reader converts
`IfcLengthMeasure`, `IfcPositiveLengthMeasure`, `IfcAreaMeasure`, `IfcVolumeMeasure`, `IfcMassMeasure` values and the
length, area, volume and weight quantities with the project units (`IfcUnitAssignment`: SI prefixes, `GRAM`, conversion
based units). Other measures (temperature, thermal transmittance, ratios, angle) are written as the file gives them.

### Same result in both readers

The rules live in `src/model/ifcProps.ts` (browser) and `tools/glb_common.py` (converter), with one implementation of the
cap, ordering, rounding and units each. `tests/ifc-import-parity.test.ts` compares the browser reader with
`public/models/*.json` and with the fixtures (`web/tests/fixtures/ifc/*.ref.json` for `common`, `*.all.ref.json` for `all`,
including a millimetre project) key by key, in order.

## Limits

- Type properties (`IfcRelDefinesByType`), `IfcPropertyBoundedValue`, list, table and reference properties are not read.
- A property set shared by many elements is parsed once; a per-element override of a type's value is not considered.
- The `synth5k` sidecar carries synthetic properties (Pset_*Common, Qto lengths) made by `tools/synth_model.py`.
- The card needs the render loop; it appears on the first frame after the delay.
