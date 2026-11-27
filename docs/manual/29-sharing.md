# 29. Sharing without a server

## The problem

You have found the duct that clashes with the beam. You want a colleague to see exactly what you see: the same cut, the same
look, the same angle. You have no project server, and the colleague is on the other side of town. Sending a screenshot loses
the model. Sending a 40 MB file and an essay about which buttons to press loses the colleague.

## The idea

The viewer is a program that runs in the browser, so what you share can be small. Everything you see on screen is the model plus
a handful of settings. Send the settings and the receiver rebuilds the same picture, as long as they have the same model.

There are three sizes of sharing, from light to heavy:

- A **link** carries settings as text, a few hundred characters. The receiver needs the viewer and the model.
- A **file you export** (views, presets, parameters) carries more, and the receiver imports it. They still need the viewer and the model.
- A **single file** carries the viewer and the model together. The receiver needs only a browser.

A link is like a recipe card: it names the dish and the steps, but you still need a kitchen. A single file is the finished meal in
a box. Both are useful. The question is always what you want the receiver to be able to do with it.

Two words are defined here. A **share link** is a web address with a `#` part that holds settings, encoded as text. A **single
file** is one `.html` file that holds the viewer, and optionally a model. For **view** see chapter 13, for **preset** chapter 4.

## 29.1 Share link: what it carries and what it never carries

There are three kinds of link. Each comes from a different place and carries a different amount.

| Link | Where you get it | Carries | Does not carry |
| --- | --- | --- | --- |
| Settings link (`#p=`) | **Export / import** folder, **Copy share URL** | Model name, x-ray and classification settings, sightlines, display, camera position and target, and the settings of view modes, imaging and section | Selection, hides, sets, class styles, views, drawings, issues, key bindings |
| View link (`#view=`) | A view's **⋯** menu, **Copy link** | One view: camera, selection, hides, pins, and the settings that differ from the factory look | Thumbnail, other views, drawings |
| Preset link (`#preset=`) | **Presets** folder, **Share** on a preset | One preset (a look) and its actions | Camera, selection, model state |

Try it on the FZK-Haus. It takes about two minutes.

### Try it: send a view as a link

1. Open the viewer and choose **FZK-Haus** in **Sample Projects**.
2. Click the roof, then press `f` to frame it. Press `x` if the x-ray is off.
3. Press `Ctrl+Shift+S` to save a view. Give it the name "Roof".
4. Open the **Views** tab in the left sidebar. Click **⋯** on the row "Roof", then **Copy link**. The address is now on your clipboard.
5. Open a new browser tab and paste the address. The viewer loads FZK-Haus and applies the view once, with no animation. The status bar says `Shared view "Roof" applied. Press Save view to keep it.`
6. Look at the address bar. The `#` part is gone. The viewer removed it, so a reload does not undo what you did after.

A view link is typically 300 to 900 characters. It fits in an email or a chat message.

### What the settings link carries

The settings link is smaller in scope. It holds the model name, the main x-ray settings, the camera and the three cut and look
tools (view modes, imaging, section). Camera numbers are rounded to 1 mm to keep the link short. It is the right link for
"look at it like this", and not for "look at these three ducts", because it carries no selection.

### What no link ever carries

This list matters when you post a link in a public channel or a ticket.

- **API keys and tokens.** The classifier keys, the Hugging Face token and the map key are not settings. A link cannot contain them.
- **Reviewer names.** The name you type when you confirm a classification stays in your browser. It is in no link.
- **Pictures.** Thumbnails of views and pictures of elements made for the classifier are in no link.
- **Drawings, issues, sheets and notes.** They stay in your browser (see appendix G).
- **Your own scripts and fly-through captions.** They are your text, and a link does not copy them.
- **The map.** The map is off at every start, and it is in no link.
- **The model itself.** A link names the model. It does not contain it.

The last point is the one people forget. If you opened an IFC file from disk, the model is named `file:<name>`, and the receiver
has no such file. The link opens the viewer on whatever model is loaded there. If its name differs from the one in the link, the status bar says
`Shared view "Roof" belongs to model "file:<name>"; "<loaded model>" is loaded. Camera and elements may not match.` For a sample model (`fzk-haus`, `building`), the link works
for everyone. For your own project, either send the model file too, or send a single file (29.2).

### Safe to open?

A link is data, not a program. But a preset link also carries **actions** (such as "fit the section box to the selection"), and
those run when the link opens. Open preset links from people you trust. The view link and the settings link only set settings.

### The QR code

The **WebXR** drawer has **Share link as QR**. It shows a QR code of the share link, so a phone or a headset can scan it and
open the same view. When the link is too long for a QR code, the code holds the model name only. The model must be reachable
from the other device; a model opened from a local file is not.

## 29.2 Send a single file

A link needs the viewer to be reachable. A single file does not. There are two kinds.

**The viewer alone.** `xray-viewer.html` is one file that holds the application, the sample models and the IFC reader. It makes no
network requests. Double-click it in Chromium, Edge or Chrome, then open your own IFC file with **Open IFC or glb file**.
Firefox and Safari were not tested.

**The viewer with your model inside.** `xray-pack` writes one `.html` file that holds the viewer and the converted model, with
the look, the selection and the camera you chose. The receiver opens it from an email attachment or a shared drive, with no
server and no install. Chapter 30 explains how to make one. It is a developer tool: someone who can run a command makes the page,
and everyone else only opens it.

### Which one to send

| You want the receiver to... | Send |
| --- | --- |
| see your exact angle on a sample model | a view link |
| try your look on their own model | a preset link, or an exported presets file |
| keep your views and import them | an exported views file (`xray-views/1`) |
| keep your settings or import them in a pack | an exported parameters file (`xray-params/1`) |
| see your model, with no setup and no viewer | a packed page (chapter 30) |
| open any IFC they have | the single-file viewer |

### What you can export from the viewer

| What | Where | Format |
| --- | --- | --- |
| All settings | **Export / import** folder, **Export JSON** | `xray-params/1` |
| Views | **Views** tab, **Export** | `xray-views/1` |
| Fly-throughs | **Views** tab, fly-through section, **⋯** menu, **Export file** | `xray-flythroughs/1` |
| Animation scripts | **Script** tab, **Export** | `.xrayanim` text |
| Presets | **Presets** folder, **Export presets** | `xray-presets/1` |
| Sets | **Sets** tab, **Export** | `xray-sets/1` |
| Shortcuts | **Edit shortcuts**, **Export JSON** | `xray-keymap/1` |

Appendix C lists these formats. The receiver imports each file in the same place where you exported it.

## How it works

A share link is the settings, written as JSON, turned into text with base64url, and put after the `#`. The part after `#` never
leaves your browser when you open a page, so a link opened from a file or an intranet does not send the settings to any server.

When a link opens, the viewer waits until the first model is loaded. It applies the settings once, then removes the `#` part
from the address. Later changes you make are your own. A reload does not repeat the link.

A view link is the same idea for one view. The camera is rounded to 0.1 mm and only the settings that differ from the factory
look are kept. Elements are named by their GlobalId (the permanent id inside the IFC file), not by an internal number. So the
view still works if the model is converted again. If the receiver's model lacks some of those ids, the status bar counts them and
the rest applies.

An exported file is the same content with more of it, for example the thumbnails of the views.

## Choices and settings

There are few. The **Export / import** folder holds **Copy share URL**, **Export JSON**, **Import JSON** and **Reset to
defaults**. The presets and views tabs hold the other share buttons. Appendix B explains where each panel's settings are.

## Limits and gotchas

- A link names the model. If the receiver has not got the model, the link shows nothing useful.
- A link carries the settings as differences from the receiver's factory look. A viewer with a different configuration file or
  different plugins can show a slightly different picture.
- An orthographic view is the viewer's approximation (a narrow field of view with the camera moved back). It restores as saved.
- Views are stored per browser and per model name. The same model opened under another file name has its own list.
- During an AR or VR session views are not saved or restored. Leave the session first.
- Very long links can be cut by chat tools. If a link fails, export the file instead.

## See also

- Chapter 13: views, and what a view stores.
- Chapter 30: packed pages, the single file with your model inside.
- Appendix G: what is stored where, and what never leaves your browser.
