# Appendix H. Troubleshooting

Find your symptom, read the likely cause, do the fix. Where the fix is not certain, the entry says so. Messages in the viewer
appear in the red segment of the status bar, with a dismiss button, and in **Load status**.

## The page does not open or the model does not appear

| Symptom | Likely cause | What to do |
| --- | --- | --- |
| The page opens but nothing works | An untested browser | Use Chromium, Edge or Chrome. Firefox and Safari were not tested. |
| A red message at the top, and a built-in procedural model appears | The `?model=` name is unknown or the model could not load. The viewer falls back to a built-in procedural model. | Use one of `building`, `fzk-haus`, `plumbing`, `process-plant`, `synth5k`, `debris-demo`, or open your own file. |
| A sample is listed but says "needs the served app or the zip" | You opened the single file, which carries only some samples | Use the served app or the zip build, or choose a sample that the file carries. |
| Nothing happens when you click **Enter VR** or **Enter AR** | A browser rule: a session must start from a click or a key press, and the device must support it | Click the button yourself. If the button is disabled it says why. |

## Opening a file

The viewer shows a one-line message in **Load status** and the red segment of the status bar. The model on screen stays.

| Message or symptom | Cause | What to do |
| --- | --- | --- |
| Mixed IFC and glb | IFC and glb cannot be opened together | Open them separately. |
| Several glb | Only one glb at a time | Open one. |
| A lone `.json` | A sidecar alone has no model | Open it together with its glb, with the same base name. |
| Unsupported type, empty or corrupt file | The file is not IFC, IFCZIP or glb, or is damaged | Check the file in another tool. Accepted: `.ifc`, `.ifczip`, `.glb`, `.json` (the sidecar). |
| A warning about size, over 100 MB | The loader warns and carries on | Wait. Memory is about 25 times the file size at 40 MB. For very large files, set `edges` to `none` and `properties` to `none` before you open (they apply to the next file only). |
| Loading is very slow at "Reading properties" | Properties are the slowest part | Set `properties` to `none`. Hover cards then show no property sets. |
| Some elements are missing | The reader cannot mesh some shapes (advanced B-rep, B-spline, some boolean and swept shapes, IFC4X3 alignment) | The console shows `[ifc-import]` with a count of products without geometry. Export the model again from the source tool as a simpler IFC, or accept the gap. |
| A wall has no window hole | An opening could not be subtracted | Same as above. The host stays solid. |
| Elements missing from a glb that worked before | The sidecar is not next to it | Put `model.json` next to the glb with the same base name. Without it, classes are guessed from node names. |
| Edges are missing on a large model | `edges` is `auto` and skips edges above 50,000 elements | Set `edges` to `all` for the next opening. It is slower to draw. |

## Seeing the model

| Symptom | Likely cause | What to do |
| --- | --- | --- |
| Nothing ghosts | The x-ray is off, or nothing is selected | Press `x`. Click an element to make it the focus. |
| Everything is solid after I pressed a key | A preset or mode such as **Solid** or **Plain** is active | Press `1` for **Coordination**, or click **Ghost** in the top bar. |
| The picture is empty after selecting a small element on a big model | The preset frames the selection and the view was far away | Press `f` to frame the selection. |
| The model is cut and I do not know why | A section box, a plane, a view mode or a view with a clip is on | Press `c` (box) and `Alt+c` (plane) to toggle, or use `section.clear` in the palette. Switch off **Behind only** (`b`) and **Peelback** (`p`). |
| Radiograph or MRI look does nothing | The graphics card has no float colour buffers | The status line says "imaging ... drawn as standard". Use another look. |
| A cut shows the inside of a wall in odd colours | Caps are back faces, and the mesh is open | See appendix F. Use a solid model, or accept it. |
| Ghosts flicker or blend wrongly | No float colour buffers, so blending follows draw order | Use another device. |
| Hover cards do not show | Hover info is off | Press `i`. |
| The camera will not zoom out in the orthographic view | Distances are tuned for perspective | Press `Home`. It frames everything again, and `Ctrl+z` brings the old view back. |
| I lost the model | The camera moved far away | Press `Home`. |
| Hidden elements are back | Hides are not applied while x-ray is off | Switch x-ray on again. |
| The map is not visible | Off at every start, or you look from below, or the location is unknown | Turn **show map under model** on and accept the notice. The map shows from above only. If the location says `Unknown`, use **Align manually...**. |
| The map is in the wrong place | The model's own location is wrong or in an unsupported coordinate system | Use **Align manually...** and enter latitude, longitude and rotation. |

## Keys

| Symptom | Likely cause | What to do |
| --- | --- | --- |
| A key does nothing | You are typing in a text box, or an overlay is open, or the master switch is off | Press `Escape`. Check **keyboard navigation** in the **Keyboard** folder. |
| A key does the wrong thing | You changed a binding, or two actions share it | Open the shortcut editor. Red cells show clashes. **Reset all** restores the defaults. |
| The preset keys `1` to `9` change the model look unexpectedly | They apply the first nine presets | See appendix D. |
| The standard angles jump | **smooth moves** is off, or your system asks for reduced motion | Turn **smooth moves** on, or accept the jump. |
| A key combination with Shift does not work on my keyboard layout | Shift+digit types another symbol on some layouts | The top bar keys use the physical key, so they work. Others may need a new binding. |

## Things that were saved, and are gone

| Symptom | Likely cause | What to do |
| --- | --- | --- |
| Sets, views, presets or style changes are gone after a reload | Browser storage is not kept. This happens on `file://` pages in some browsers, in private windows, and after clearing site data | Open the viewer from a web address, not `file://`. Export what you need and import it next time. |
| Views from one computer are not on another | Views are per browser and per model name | Export and import. |
| My views vanish when I rename the file | The list is per model name | Keep the name, or export and import. Fly-throughs follow the model identity, so a rename keeps them. |
| A packed view I deleted came back | A page packed again with a newer version offers it again | Delete it again, or pack without it. |
| An issue or drawing is gone | They are kept in this browser's IndexedDB. Site data was cleared, or you used a private window. | Export issues and drawings regularly. |
| The classification asks for my name again | The reviewer name is per browser | Enter it again. It is never in files. |

The viewer says when storage fails: for example the Views tab says that views last only for the session.

## Share links and packed pages

| Symptom | Likely cause | What to do |
| --- | --- | --- |
| A share link opens to the wrong model, or nothing | The link names a model that the receiver does not have | Send the model, or send a packed page (chapter 30). |
| A view link says "not in this model" for some elements | The receiver's model lacks some GlobalIds, or it is another version | The rest still applies. Check that both have the same model. |
| The link did not apply my selection | A settings link carries no selection | Use a view link. |
| A link gets cut in chat | Too long | Export the file instead. |
| The look of a link differs a little | A different configuration or plugins | Accept it, or send a packed page. |
| `xray-pack` stops with `xray-pack:` and an exit code | Code `1` is a usage error: a bad option, a missing `-o`, or an existing output. Code `2` is an input error. | Read the one line on stderr. Add `--force` to replace the output. |
| `--select` warns that an element is missing | GlobalIds are those of the converted model. A renamed duplicate ends with `~n`. | Fix the id. |
| `--preset` or `--open-tool` is ignored | A part of the viewer is not in the build | Read the console warning. |
| A packed page opens slowly | The model is base64 inside the page, and over a few tens of MB | Pack a smaller model, or send it another way. |
| A packed page opens with panels folded and does not show them again | `--kiosk` folded them and the browser remembers it | Press `[` and `]` to open the sidebars, and `t` for the tool strip. |

## Classification

| Symptom | Likely cause | What to do |
| --- | --- | --- |
| **Test connection** fails | A wrong address, a wrong key, or the server does not allow requests from the page (CORS) | Check the address. Codes 401 and 403 are not retried: check the key. Use a proxy on your own server with the same origin. |
| A request goes to the wrong key or server | A Jev key is never sent to a d3 server, and the other way round. They are kept apart. | Set each key in its own box. |
| The Hugging Face download fails | Not found, private or gated, or the host is unreachable | Save a token (stored only as long as the tab, unless you remember it), or check the network and the address. |
| WebGPU error | The device has no WebGPU, and the viewer does not switch silently | Choose another backend or data type. |

## AR and VR

| Symptom | Likely cause | What to do |
| --- | --- | --- |
| The **WebXR** drawer says there is no WebXR | The browser does not support it. iPhone and iPad never do. | Use Android Chrome with ARCore, or a Quest. On iPhone use AR Quick Look or **Share link as QR**. |
| The model drifts while I walk | The device has no anchors, or the registration is rough | Use points that are far apart. Register again. Save the site. |
| The model is a few centimetres off | The hit test of a phone has several centimetres of error | Add a third pair, or **Nudge**. |
| Snapshots show no photo of the room | A page cannot read the camera picture in WebXR | This is a limit of the platform. Use the notes and the pose. |

These features are experimental. See chapter 31.

## Starting over

- **Reset to defaults** (**Export / import** folder) resets the settings.
- **Reset shortcuts** (**Keyboard** folder) resets your keys.
- To clear everything stored by the viewer, clear site data for its address in your browser (appendix G).
- Reload the page. A `#` link is removed from the address after it is applied, so a reload gives a clean state.

## If it still does not work

Open the browser console. The viewer logs the cause of most problems there, for example `[ifc-import]`, `[keymap] conflict`, and
the list of keys of an imported file that it could not use. Note the browser, its version, the model file name and size, and the
message. Then ask the person who runs your installation.
