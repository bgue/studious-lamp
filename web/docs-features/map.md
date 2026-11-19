# Map under the model

An optional map on the ground under the model. Off by default. Controls: the `Map` folder of the settings panel. Code: `src/map/`, wired by `src/plugins/map.ts`.

## Privacy

Turning the map on sends the project's location (the tiles you see) to a third-party tile server. So:

- The map is off at every start. The switch is never stored.
- The first time you turn it on for a provider, a notice says: "Map tiles are fetched from <provider>; this reveals the project's location to them." Nothing is requested until you accept. Changing the provider asks again.
- With the map off, the viewer (also the single-file build) makes no network request. `bench/single-file.mjs` checks this.
- The map is in no params document, share link, saved view, preset or packed page.
- An API key, and a custom URL (it may hold a key), are kept like the classifier keys: in `sessionStorage`, gone when the tab closes. They are sent only to the tile server.
- The place you set by hand is stored per model in IndexedDB. Not in localStorage, a URL or a share link.

## Where the model is

In this order:

1. A place you set by hand for this model.
2. IfcMapConversion with IfcProjectedCRS. Supported: UTM, EPSG 326xx and 327xx (WGS 84), 258xx (ETRS89), 269xx (NAD83). Other CRSs are not supported. The panel says so and the next step is used.
3. IfcSite RefLatitude and RefLongitude, with TrueNorth of the model context. The site's point is taken as the project origin.
4. Unknown. Nothing is drawn. Use `Align manually`.

The status line shows which one: `From IfcMapConversion (EPSG:25832)`, `From IfcSite`, `Manual` or `Unknown`.

## Controls

| Control | Meaning |
| --- | --- |
| show map under model | On or off. Off at start. |
| provider | Esri World Imagery, OpenStreetMap, or a custom XYZ template. |
| URL template, API key, attribution | Custom provider only. `{z}`, `{x}`, `{y}` and an optional `{key}`. |
| opacity | 0 to 1. |
| radius (m) | Radius of the disc around the model. Default 150. |
| location | Where the place came from. |
| Align manually... | Opens the aligner. |
| Use the model's own place | Forgets the manual place. |

## Providers

- Esri World Imagery. Attribution on screen: "Esri, Maxar, Earthstar Geographics, and the GIS User Community".
- OpenStreetMap standard. A street map, not satellite. Attribution: "© OpenStreetMap contributors". It is subject to the [tile usage policy](https://operations.osmfoundation.org/policies/tiles/): light use only. Do not use it for heavy or bulk viewing.
- Custom XYZ. You give the attribution.

The attribution shows in a small label at the bottom right while the map is drawn.

## Aligner

Enter `latitude, longitude` (paste from any map) and the rotation: the bearing of the model's +Y axis from true north, degrees clockwise (the IFC TrueNorth angle). Or drag on the ground: the map moves under the model. Shift and drag turns it about the middle of the model. Right drag and the wheel still move the camera. `Top view` looks straight down. `Done` keeps the place, `Cancel` drops the changes.

## How it is drawn

- A flat disc of tiles at the lowest storey elevation (else the bottom of the model), 2 cm below it, so a floor slab at the same height wins.
- Zoom follows the camera distance, so a tile pixel is about a screen pixel, with a limit of 72 tiles. Tiles load nearest first, a few at a time, are kept in a memory cache (256 tiles, least recently used go first) and fade in. The finer level replaces a coarser one only when it has all loaded.
- Drawn first, behind the model. It has no raycast: picks, measurements, the classification and its pictures never see it. It is not in the bounds used for fit, section box or explode.
- Not clipped by section planes. It is the ground the model stands on; a cut through the building does not cut the earth away.
- Seen from above only. From below it is not drawn, so the x-ray view from underneath is clear.
- The radiograph and MRI looks draw the model only.
- The placed PDF sheet quad is drawn over the map.

## Scripts

`window.__xrayMap`: `state()`, `setEnabled(on)`, `patch({ opacity, radius, provider })`, `setManual({ lat, lon, rotation })`, `openAlign()`, `pickable()`.

Tests: `tests/map-*.test.ts`, `bench/smoke-satmap.mjs`.
