# 31. AR and VR (experimental)

> Experimental. The AR and VR features were built and checked against a software emulator of a headset (the Immersive Web
> Emulation Runtime), not on a real headset or phone. Treat everything in this chapter as untested on real devices.
> Try it before you rely on it on site.

## The problem

On a drawing, the duct runs behind a ceiling you cannot see. On a screen, you can see it, but you are not in the room. You
would like to stand where the duct is and look at it, or hold the building on a table, or walk the real corridor and see what
is behind the plaster.

## The idea

Three ways to put the model around you, from simplest to most demanding:

- **VR (virtual reality).** You wear a headset that shows only the model. One metre in the model is one metre in the room. You walk through the building.
- **Tabletop AR (augmented reality).** The camera of a phone or a headset shows the real room, and the model stands in it, small, 50 times smaller than real. You place it on a table.
- **Field AR.** The model is shown at real size, laid over the real building. You tell the viewer where two or three known points are (a wall corner, a column) and it lines the model up. Then the ducts behind the real wall show on your screen.

The x-ray idea carries over: in field AR the viewer ghosts the walls and slabs and keeps the services, so the real walls are what
you see and the model adds what is behind them.

New words:

- **session**: the time between "Enter" and "Leave". The browser runs the headset or phone camera for you.
- **registration**: telling the viewer where the model sits in the real room, by pairing points on the model with the same points in the room.
- **anchor**: a point the device remembers in the room, so the model stays put while you walk.
- **AR Quick Look**: the viewer that Apple phones and tablets offer for 3D files. It is a fallback, not the same feature.

## What you need

This is the honest table. Nothing below was tried on a real device.

| Device and browser | VR | Tabletop AR | Field AR |
| --- | --- | --- | --- |
| Android phone or tablet, Chrome with ARCore | no | yes | yes |
| Meta Quest 3, 3S, Pro, Quest 2, Quest Browser | yes | yes | yes |
| Apple Vision Pro, Safari | expected | no | no |
| iPhone and iPad, any browser | no | no | no (use AR Quick Look) |
| A desktop browser with no headset | no | no | no |

Quest 2 has grey passthrough, Quest 3 has colour passthrough. Samsung Internet on an ARCore device is expected to work like Chrome.
Apple Vision Pro VR was not tried.

When the browser has no WebXR, the **WebXR** drawer says so. **Enter VR**, **Enter AR** and **Enter field AR** are disabled with
the reason. **Download USDZ** and **Share link as QR** still work.

## 31.1 VR walk, tabletop AR, field AR at real size on site

The tool is **WebXR** (headset icon, tooltip "AR / VR") in the action panel. The drawer has the buttons below. A browser rule
says the session must start from a click or a key press, so you cannot start one by script.

| Control | Meaning |
| --- | --- |
| **Enter VR** | Start a VR session at real scale. |
| **Enter AR** | Start a tabletop AR session. |
| **Enter field AR** | Start a field AR session at real scale. |
| **AR scale** | `1:1` (real size) or `tabletop 1:50`. |
| **field look** | `x-ray` (services only), `ghosted` (default) or `full`. |
| **pointer rays** | Draw the ray of each controller or hand. |
| **Leave XR session** | End the session. |

None of these has a default key.

### VR walk

1. Open FZK-Haus. Orbit to the room where you want to start.
2. Click **Enter VR** and put the headset on.
3. You start at the position of the orbit camera, looking along the horizontal part of the view direction.
4. Point a controller at an element. A blue ray turns yellow when it hits one.
5. Pull the **trigger** (or pinch) to select the element. Selecting nothing clears the selection.
6. **Squeeze** to switch the x-ray on or off.
7. Push the **right thumbstick** sideways to turn by 30 degrees. Push the **left thumbstick** to walk at 2 m/s.
8. Click **Leave XR session** or take the headset off.

There is no teleport. The viewer does not add an eye height: your head height is what the headset reports.

### Tabletop AR

1. Click **Enter AR**. The model stands 1.2 m ahead of you at real size, or 0.9 m ahead at table height in `tabletop 1:50`.
2. If the device can find surfaces, a white ring follows the surface under the centre of your view.
3. Tap (or trigger, or pinch) to put the model down. The centre of its footprint lands on the ring.
4. Tap again on an element to pick it. **Squeeze** picks the model up again.

In `tabletop 1:50`, a 25 m building is 0.5 m long on the table.

### Field AR at real size on site

Use this on the real building. Plan about 10 minutes the first time.

1. **Before the session**, on screen: open the drawer and click **Pick model points**. Click at least 2 clear features on the model: wall corners, column centres, floor marks. Keep them far apart on plan. Magenta dots show your picks.
2. Click **Enter field AR**. The model appears at real size.
3. For each model point, in the same order, aim at the same real feature and mark it. On a phone, the crosshair at the middle of the screen is the aim: tap **Mark room point**. On a headset, the controller ray is the aim: pull the trigger.
4. When every model point has a room point, the viewer solves the match. It shows each pair's error and the average (RMS). A pair more than 10 cm off is named.
5. Click **Floor here** (phone) or press `Y` on the left controller at the floor of the storey you stand on. This sets the floor height.
6. If the model is a little off, use **Nudge**: it moves 1 cm (10 cm with the **step** button) or turns 0.5 degrees (2). On a headset, the sticks do the same.
7. Walk. The model follows an anchor, so it stays put when the device corrects its own map. Without anchors, the status says "no anchors: may drift while you walk"; register again.
8. Click **Save site** to keep the match for next time.

What you see:

- **ghosted** (default): services show as they are. Walls, slabs and other structure drop to 6 % opacity, and everything else to 20 %.
- **x-ray**: only the services.
- **full**: your own look.
- The model is cut away more than 6 m from you (**Cut -** and **Cut +** change it). Under the floor you stand on, services stay.
- A line shows the storey, your eye height above its floor, its ceiling, and the height of the white dot.

Tap an element to get a card: name, class, storey, material, up to 4 properties, and the **clearance**: the distance from the
device to the element, and from the white dot to it.

**Snapshot** saves what the model overlay draws, with the head position and the element. A web page cannot read the camera
picture in WebXR, so the snapshot has no photo of the room. At the end of the session each snapshot becomes an issue called
"Field note N" (when the issue tool is present and **snapshots to BCF** is on). **Download notes** saves them all as a file.

### Saving a site

**Save site** keeps the pairs, the result and the anchor in this browser. With **restore saved site** on (default), the next
session restores the newest site. On Quest the anchor is persistent, so the model comes back without a tap. On Android Chrome
there are no persistent anchors, so you tap the saved points again (2 or more taps). **Export site** and **Import site** move a
site between devices as a file. A site of another model is refused.

### iPhone and iPad

Safari and every browser on an iPhone or iPad has no WebXR. The viewer offers **Open in AR Quick Look** (or **Download USDZ**
where that is not supported). It exports what you see to a 3D file and opens it in Apple's viewer. The model stands on a
surface you tap, at real size.

AR Quick Look does not register the model to the building and does not show the x-ray. It is for showing, not for checking on
site. **Share link as QR** is the other way to get a view onto a phone (chapter 29).

## How it works

The model never moves. The viewer puts the camera in a "rig", a point in the scene that you walk, turn and scale. In VR the rig
follows your head. In tabletop AR the rig is scaled 50 times, so the model looks small. In field AR the rig is solved from your
point pairs: the viewer finds the turn and shift that best puts the model's points on the room's points, with real scale and no
tilt, because the device already knows which way is down.

Inside a session the viewer draws the scene once for each eye. A few drawing steps cannot be done twice per frame in the same
way, so they are left out and the status line says which: radiograph and MRI looks, the peel window, ambient shading,
bloom and depth of field, and the order-independent ghosting (the sorted ghost path is used instead). Section cuts and cap faces
still work, and the x-ray works from the position of your head.

When you leave, the viewer puts everything back: renderer, camera, controls, background, and your section and class settings.

## Choices and settings

The params section `xr` has `scale`, `pointerRays`, `fieldView`, `cutRadius` and `storeyCut`. It is not in a share link. Appendix B
says where the **WebXR** settings are.

## Limits and gotchas

- Experimental. Tested with an emulated device only. Expect problems the emulator cannot show: tracking drift, real surface detection, real hand tracking, speed.
- On a phone expect several centimetres of error from the hit test alone, even with a good registration. The emulator results (under 1 cm with 1 cm of tap noise) do not carry over.
- No teleport. No gestures except pinch as select. No depth sensing: real objects do not hide the model.
- Field AR has no tilt in the registration, no floating mini-model for picking model points inside the session, no camera pixels in snapshots, and a cut that is a box and not a sphere.
- The text panel of a headset shows text only. The controller buttons do the actions.
- Views are not saved or restored during a session.
- Where a browser has no WebXR, the tool still opens, with a note.

## See also

- Chapter 29: share link as QR, to open a view on a phone.
- Chapter 13: views, which you cannot save or restore during a session.
- Appendix F: all known limits.
