# Appendix E. Glossary

Terms as the manual uses them, in alphabetical order. Old names are listed as "formerly" so you can find them in old notes,
in `docs/SETTINGS.md` and in the console. Use the new names in your own writing.

## Words you will meet in the screens

| Term | Meaning |
| --- | --- |
| **4D plan** | What each element is doing at each date: not yet built, under construction, finished, being removed. |
| **action** | One thing the keyboard, the palette or a script can do, such as "toggle x-ray". It has an id such as `xray.toggle`. |
| **activity** | One line of a schedule (a P6 task). It has an Activity ID. |
| **anchor** | A point that an AR device remembers in the room, so the model stays in place while you walk. |
| **BCF** | A file format for exchanging issues between programs. The manual names it only as a file format: "export the issues as BCF". |
| **bucket** | The result of the first x-ray step for an element: focus, host, near or far. |
| **buffer** | The distance around the focus inside which a context element counts as near. |
| **cap** | A flat hatched face that closes the cut of a solid, so that the cut looks like a section. |
| **class** | The IFC type of an element, such as `IfcWall` or `IfcDuctSegment`. |
| **clearance** | The shortest distance between the surface of an element and the focus. |
| **clash** | Two elements that overlap. The clearance colouring paints it red. |
| **context** | Elements that may ghost: slabs, walls, beams, columns on nearby storeys. |
| **drawing** | A cloud, arrow, text, callout, shape or pen line on a view. Formerly: *markup*, *annotation* (PDF annotations keep that word). |
| **far** | Context that is neither host nor near. By default it is drawn solid. It ghosts, with `far weight`, when it blocks the view of the focus (chapter 4). With `far mode` set to `hidden` it is not drawn. |
| **federate** | Open several IFC files as one model. |
| **fly-through** | A sequence of views with timing, played as a film. Formerly: *tour* (an older feature that the manual mentions only in its limits). |
| **focus** | The elements you are looking at, such as the selected duct run. They are drawn solid and in front. |
| **ghost** | To draw an element see-through, so that the focus shows through it. |
| **GlobalId** | The permanent 22-character id of an IFC element. Views, sets and links name elements by it. |
| **host** | A context element that crosses or contains the focus, such as the slab a pipe passes through. |
| **imaging** | The two medical looks: radiograph and MRI slice. |
| **issue** | A problem someone must act on: status, priority, assignee, due date, comments. It points at one or more views. Formerly: *topic*, *BCF topic*. |
| **kiosk** | A packed page with the panels folded, often playing a film by itself. |
| **link (4D)** | An activity together with the elements it builds or removes. |
| **mode** | One of the five top-bar looks: Solid, Ghost, Radiograph, Glow, Cutaway. Not to be confused with the view modes (behind-only, peelback). |
| **near** | Context inside the buffer of the focus that is not host. |
| **occluder** | Context that blocks the line of sight to the focus: host, near and, with the default `occluder scope` `all`, far. Only occluders change opacity. |
| **orbit** | Turn the camera around a point. |
| **pin** | A rule that keeps an element's opacity above a floor. |
| **player** | What plays fly-throughs, scripts and 4D films. Formerly: *score player*. |
| **preset** | A saved look: settings only, never the camera. |
| **query** | A condition in the query language, for example `class = 'IfcWall' and storey = 'Level 2'`. Formerly: *criteria*, *WHERE* (still shown in the search bar for a query). |
| **radiograph** | The look that draws material thickness as brightness, like an x-ray picture. |
| **registration** | In AR, telling the viewer where the model sits in the room. For point clouds, the alignment of a scan to the model. |
| **revision** | A newer version of the same model, compared with the earlier one (chapter 20). |
| **script** | An animation script (`.xrayanim`): short English-like lines that move the camera and change the view. Formerly: *score* (in the code), *DSL*. |
| **section** | A cut through the model with a box or a plane. |
| **selection set** | A named group of elements. See *set*. |
| **set** | A named group of elements, fixed or defined by a query. Formerly: *selection set* (still fine on first use). |
| **sheet** | A page of a PDF drawing set, shown as a view you can draw on. Formerly: *sheet sketch*. |
| **sightline** | A straight line from a point on the focus to the camera. The viewer counts what each one hits. |
| **storey** | A level of the building. An element belongs to at most one. |
| **tie** | A link between an activity and elements that the viewer could not decide and left for a person. |
| **tier** | The rank of a class. A higher tier ghosts a lower tier. |
| **view** | A captured moment: camera, what is shown, hidden, cut and selected. It may carry drawings. Formerly: *sketch*, *markup set*, *saved view* (the Views tab keeps the word), *viewpoint* (kept only for BCF files). |
| **viewpoint** | The BCF word for a camera with selection, hides, colours and clip planes. Used only when talking about BCF files. |

## Old names, and what replaced them

| Formerly | Now | Where you may still see the old name |
| --- | --- | --- |
| sketch | view with drawings; the old **New sketch** is **Draw on this view** | action names such as `markup.new`, files `xray-markup-set/1` |
| markup set | view with drawings | the PDF report text, the file name |
| markup | drawing | `docs/SETTINGS.md`, console messages |
| annotation | drawing | PDF files still use the word for the drawings written into them |
| topic, BCF topic | issue | BCF files, the BCF dialog |
| viewpoint | view | BCF files only |
| BCF drawer | the **Issues** tab | `docs/SETTINGS.md`; action `tool.bcf` opens the Issues tab |
| Markup drawer | the **Views** tab on the filter **With drawings** | action `tool.markup`; key `k` opens the same place |
| Classify drawer | the **Classification** tab of the right sidebar | `docs/SETTINGS.md`; action `tool.classify` |
| score | script, fly-through or 4D film, whichever it plays | internal names, `window.__xray…` |
| score player | player | internal names |
| sheet sketch | a view on a sheet (filter **On sheets**) | files, `docs/SETTINGS.md` |
| tour | fly-through | the settings folder named **Tour** (a different, older feature) |
| selection set | set | first use only |

## Words of the x-ray in one picture

You select a duct. The duct and what connects to it are the **focus**. Slabs, walls, beams and columns around it are the
**context**. The context that crosses the focus is **host**. The context within a small distance is **near**. The context far away
is **far**. Host and near parts that block your view are **occluders**, and so are far parts that block it. Only occluders become
see-through, by how much they block and how close they are. A radiologist does the same: the bone shows because the flesh is made faint, not removed.
