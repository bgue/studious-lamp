# Appendix G. Privacy and data

The short version: the viewer uploads nothing by itself. Your model, your issues and your decisions stay in your browser.
A few optional features talk to other servers, and only when you switch them on. This appendix lists all of them.

## What the viewer never does

- It never uploads your model, your views, your issues, your drawings or your settings to a server of the viewer.
- With the map off and no classifier provider that talks to a server chosen, it makes no request to any other server. The single-file build is checked for this, and opens from `file://` without any request.

Everything below is either stored on your own computer, or sent somewhere because you chose a feature that needs it.

## Where your data is kept

There are three places in the browser, and they differ in how long data lives and who can read it.

| Place | Lives until | Used for |
| --- | --- | --- |
| **Session storage** | You close the tab | Secrets: API keys and tokens, unless you tick "remember" |
| **Local storage** | You or the browser clear site data | Small settings and lists |
| **IndexedDB** | You or the browser clear site data | Bigger work: drawings, issues, sheets, 4D, revisions, review logs, a hand-set map place |

Each browser profile has its own storage. A `file://` page may share storage across all files in some browsers, and may lose it in
others. A private window may keep nothing. The viewer copes with that and works for the session. Clearing "site data" deletes all of it.
Export what you want to keep.

### Local storage (small settings and lists)

Keys are per model where they say so. A model is recognised by its name, its element count and a hash of its GlobalIds, so a
renamed copy of the same model finds its fly-throughs and views again, and a different model with the same name does not.

| What | Key |
| --- | --- |
| Sets and class style changes | `xray.sets.<model>`, `xray.classStyles.<model>` |
| Views | `xray.views.<model>`, `xray.views.ui` (list or grid) |
| Packed views already offered | `xray.viewsPacked.<model>` |
| Presets you saved | `xray.presets` |
| Fly-throughs | `xray.flythroughs.<model identity>`, `xray.flythrough.ui` |
| Animation scripts and the text you were editing | `xray.anim.<model>` |
| Shortcuts you changed, keyboard speeds, navigation style, eye height, Walk collision | `xray.keymap`, `xray.keynav` |
| The last viewer version whose "What's new" card you saw (a number, kept in this browser only) | `xray.whatsnew` |
| Recent searches and palette commands | `xray.search.recent`, `xray.palette.recent` |
| Layout: sidebars, dock, tool strip, top bar, view cube, pointer mode, hover list | `xray.sidebar`, `xray.dock`, `xray.toolbar`, `xray.topbar`, `xray.gizmo`, `xray.pointerMode`, `xray.propsListOpen` |
| Tooltips on or off | `xray.help` |
| Cleanup rules, the length unit | `xray.cleanup.<model>`, `xray.cleanup.lengthUnit` |
| Video export options | `xray.record.options` |
| Author name for issues | `xray.bcf.author`, `xray.bcf.version` |
| Field AR sites (point pairs, anchor) | `xray.xr.sites.<model>` (newest 20) |
| Classification: answers cache, fitted temperatures, manual overrides, schema, review log fallback | `xray.classify.*` |
| Classification: reviewer name | `xray.classify.reviewer.v1` |
| Map: which providers you accepted the notice for | `xray.map.noticeAck` |

The key `xray.probe` is only a test that local storage works. It holds nothing. `xray.toggle` is an action name, not a storage key.

The reviewer name and the issue author are names of people. They are kept only in this browser. They are in no link, view, preset,
parameters file or packed page (see below).

### IndexedDB (bigger work)

| Database | Holds |
| --- | --- |
| `xray-work` | Drawings, issues and the links between them, one record per model |
| `xray-sheets` | PDF files you opened (the bytes), and sheet data and sheet drawings (no bytes in the data record) |
| `xray-4d-map` | 4D assignments (location, trade, zone), value lists, class table |
| `xray-4d-schedule` | 4D configuration, links with review state, and the `.xer` as it was read (not stored above 24 MB) |
| `xray-revisions` | Snapshots of earlier model versions (3 per file name, 300 MB in all), review sessions, ghost shapes (up to 64 MB) |
| `xray-classification-review` | The classification review log, per model fingerprint |
| `xray-map` | A place you set by hand for the map, per model |

Without IndexedDB (a private window) none of this is kept, and the session works as before. A test scans the code to make sure
issues, drawings and sheet data are never put in local storage.

### Session storage (secrets)

These live only until the tab closes. Nothing writes them to a file.

- **Classification API key** (for the Jev decision service), **d3 key**, and **Hugging Face token**. Tick **Remember on this device** to keep one in local storage instead. It is off by default. A key held in a page can be read by anyone who uses that browser profile, by a script on the page, and by a browser extension. For a shared installation use a proxy on your own server and leave the key box empty.
- **Map API key** and **custom tile URL** (a URL may hold a key).

Key boxes are password fields and empty after saving. The panel shows only that a key is set and its length. The viewer does not
write keys to the log, and strips them from error messages.

## What goes to other servers, and when

Only four features can send anything out. Each is off, or needs your action, until you use it.

### The map (off at every start)

Turning the map on sends the project's location, as the tile requests you see, to a tile server.

- **Esri World Imagery** (satellite): `server.arcgisonline.com`.
- **OpenStreetMap** (street map): `tile.openstreetmap.org`. Light use only, per their policy.
- **Custom**: the address you typed. It may hold a key. The key goes to that server only.

What the server learns: the tile positions you view, which reveal where the project is, plus your address and browser details, as
for any web page. The first time you switch the map on for a provider, a notice says so and nothing is requested until you
accept. Changing the provider asks again. The switch itself is never stored. The map is in no parameters file, link, view, preset
or packed page. A place you set by hand is stored in IndexedDB and in no URL.

### The classifier (only when you choose a provider that needs one)

With **provider = off** or with rules only, nothing leaves the browser. Other providers:

| Provider | What is sent, and to whom |
| --- | --- |
| `decision` (small model in the browser) | Nothing about your elements. On first use the weights are downloaded from Hugging Face (or the mirror you set), and the code is loaded from a code delivery network (`cdn.jsdelivr.net`). The browser keeps the weights in its cache. A Hugging Face token, if you set one, goes only to the Hugging Face address. |
| `d3` (browser) | Nothing about your elements. Files are downloaded from Hugging Face (or a mirror or folder you set); the runtime comes from `cdn.jsdelivr.net`. |
| `d3` (endpoint) | A request per decision to the System One address you set. It holds class, name, type, property sets, quantities, material, systems, the place in the building and the parents of the element. With **images** on, it also holds pictures of the element. |
| `webllm` | Nothing about your elements. The code is loaded from `cdn.jsdelivr.net`; model files come from Hugging Face. |
| `jev` | A request per decision to the Jev address (default `https://api.typesafe.ai/v1/systemone`, or your proxy). It holds the same element facts as above. The key goes in the `Authorization` header, to that address only. No cookies are sent. |
| `mock` | Nothing. It is for tests. |

Read the facts that are sent before you use a service with a real project. Names and property sets of your elements are
project information. Use a proxy in your own network, or a decision model in the browser, if that is not allowed.

Downloading weights is an ordinary web request. The code of the viewer sends no data from your model with it. Hugging Face sees what any web server sees: your network address, the browser name and which files you ask for (and the token, if you set one).

### Fly-through video

The video encoder is a library that is loaded the first time you export, with no network request (it is inside the viewer).

### Google or other fonts, analytics, updates

None. The viewer asks for no fonts, scripts or updates.

The served build asks only the server it came from, for the model files, `xray.config.json` and `xray.presets.json`. The page loads no fonts, scripts or analytics from elsewhere. The single file makes no request at all when opened from disk. Anything that talks to another server is something you switch on: the map (chapter 6), the classification providers above, a custom endpoint you type.

## What share links, views, presets and packed pages never contain

| Never in a link, a view, a preset, a parameters file or a packed page | Why |
| --- | --- |
| API keys and tokens (Jev key, d3 key, Hugging Face token, map key, custom tile URL) | A page that holds a key can be read by anyone it is sent to. A parameters file that has a key field is refused. |
| Reviewer names, issue author names | Personal data. |
| `reviewed_by` of 4D assignments and links | Personal data. It stays in the dataset. It goes into the IFC only by your choice. |
| Pictures of elements, and thumbnails | Pictures are held in memory and never in a file. View thumbnails are left out of links. |
| The map, and its place | It reveals the project location. |
| Fly-through captions, animation scripts, element labels | Your own text. A packed page takes a script or fly-through only when you name its file. |
| Your drawings, issues and sheets | They stay in IndexedDB. |
| The version marker of the "What's new" card (the last viewer version you saw) | It is kept in this browser's local storage and nowhere else. It is not sent anywhere. The card text comes from the `CHANGELOG.md` inside the page, so nothing is fetched. |
| The model itself (in a link) | A link only names it. A packed page does contain the model, because that is the point. |

What a link or a view does hold: the model's name, camera, settings, and (for a view) the GlobalIds of selected, hidden and pinned
elements. Treat a view link like the model's name plus a hint about what you looked at.

Unit tests check these rules on the parameters document, the share link, the views and the packed output.

## What goes into an IFC you save

**Save IFC** writes a block into a copy of your file. It holds classification results, review marks, 4D values, and (if you tick
it) reviewer names and comments. The box **Include reviewer names and comments** is off every time you open the dialog. It is
not remembered. Off: no name and no review comment is written. API keys, tokens and pictures are never written.

`reviewed_by` of 4D data goes in only through an explicit option.

**Save cleaned copy** writes your IFC without the elements that cleanup hid. It is a derived file and says so in its comment.

## What you can do

- To remove all stored data: clear site data for the viewer's address in your browser. That deletes local storage, session storage and IndexedDB for that address.
- To remove one thing: **Reset to defaults** in **Export / import** resets settings, pins, hides and class edits. Delete a view, a set or an issue in its own tab. In the Classification tab, use **Clear results**.
- Before you hand a computer to someone, clear the site data, or work in a private window.
- Before you send a parameters or views file, remember that it holds element ids (GlobalIds) and your settings, but no keys or names.
- If you use a classifier service, read what it sends (above).

## Check list for a project that must stay private

1. Use the single file `xray-viewer.html`, not a hosted copy.
2. Leave the map off.
3. Set the classifier provider to `off` or `decision`, or to a proxy you control.
4. Do not tick "Remember on this device".
5. Leave **Include reviewer names and comments** unticked when you save an IFC to send out.
6. Give a packed page to the people who may see the model. It contains the model.
