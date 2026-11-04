# WebXR (experimental)

Look at the model in virtual reality (a headset) or place it in augmented reality (a headset with passthrough, or a phone). Tool `xr` (label `WebXR`) in the action panel, folder `WebXR` in the panel, actions `xr.vr` and `xr.ar` (no default keys). Everything is feature detected: the viewer asks `navigator.xr.isSessionSupported('immersive-vr')` and `('immersive-ar')`; when neither is supported the tool, the folder and the buttons stay hidden, and the viewer behaves exactly as before. **Experimental**: it was developed and checked against the Immersive Web Emulation Runtime (iwer), not on a headset (see "What was verified" below).

| Control (folder `WebXR`) | Meaning |
| --- | --- |
| `Enter VR` | Start an `immersive-vr` session at real scale. Hidden when VR is not supported. Call it from a click or a key press (a browser rule). |
| `Enter AR` | Start an `immersive-ar` session (hit-test feature requested as optional). Hidden when AR is not supported. |
| `AR scale` | `1:1` (real size) or `tabletop 1:50` (the model looks 50 times smaller). Changing it during a session re-applies the placement at once. |
| `XR status` | Read-only text: what the session is doing and which passes it leaves out. |
| `pointer rays` | Draw the ray of each controller or hand (blue; yellow when it meets an element). |

The drawer of the tool has the same buttons plus `Leave XR session` and a longer status line. Params section `xr` is `{ scale, pointerRays }` (not in the share URL). `window.__xrayXr = { enter(mode), exit(), state(), setArScale(s), config, manager }`.

## VR

- Real scale: one model metre is one metre in the room. The session uses the `local` reference space, so the head starts at the origin of that space and the viewer puts it exactly on the **current orbit camera position**, looking along the horizontal part of the orbit view direction. (Head height above the floor is whatever the headset reports; the viewer does not add an eye height.)
- Controllers or hands draw a pointer ray (`pointer rays`). **Trigger or pinch** (`select`) selects the element under the ray (`app.selectIds`, the same BVH raycast and the same rules as the mouse: hidden and click-through ghosts are skipped, cut parts do not count); selecting nothing clears the selection. **Squeeze** toggles X-ray. The first pointer also drives the hover highlight (`app.hoverId`).
- **Right thumbstick**: snap turn by 30 degrees (push past 0.7, back below 0.3 to re-arm). The turn pivots about the head, so the head does not move in the world. **Left thumbstick**: walk in the horizontal plane along the head direction (2 m/s). There is no teleport.

## AR

- Before the first tap the model stands 1.2 m ahead of you (1:1, floor 1.4 m below the eyes) or 0.9 m ahead on a table height (tabletop). With the `hit-test` feature a white ring follows the surface under the view centre; **select** (tap, trigger, pinch) places the model so that the centre of its footprint (at its lowest point) lands on the ring. Without hit-test the select places it where it stands. Afterwards a select picks an element like in VR. **Squeeze** picks the model up again (the next select places it); in AR the thumbsticks do not move you.
- The canvas clears to alpha 0 and the scene background is removed, so the camera image shows through; both are restored on exit.
- `tabletop 1:50`: the viewer is made 50 times larger than the model (the rig scale, see below), so a 25 m building is 0.5 m long on the table. The pointer ray, the controllers and the head keep their physical size; the model is not rescaled.

## The rig

The model never moves. The XR camera sits in a rig (an `Object3D` in the scene that also holds the pointer rays and the reticle): `world = rigPosition + Ry(yaw) * (scale * local)`, `local` being a position in the XR reference space. Walking and turning change position and yaw; the AR presets change `scale` (world metres per physical metre). Placing the model in AR is solving that equation for the rig position so that a world anchor lands on the hit point. The maths is `src/xr/maths.ts` (pure, tested); the session logic is `src/xr/session.ts`; `plugins/xr.ts` owns the GUI. The camera clip distances are physical metres (near 0.05, far at least 50).

## What a session draws

Inside a session `renderer.render` draws with three.js' stereo camera straight into the XR framebuffer. A render into a private target (OIT accumulation, the peel flood, imaging, post effects) would be drawn once per eye with the eye viewports, which is wrong for a single-view target, so these passes are left out, and the status line says which:

| Feature | In a session |
| --- | --- |
| Normal passes, edges, sorted ghost pass, focus pass | Drawn per eye (the shaders read `viewMatrix`, `projectionMatrix` and `cameraPosition` per view). |
| X-ray (algorithms 1 and 2) | Runs from the **XR camera's world position** (the head), throttled as before: `SIGHTLINE_INTERVAL_MS`, and only after the head moved by 1 cm (in rig scale). |
| Behind-only | Works; the plane is perpendicular to the **head's view direction** through the nearest focus point. |
| Sections (box, plane) and their caps | Work (a per-fragment test in world coordinates). |
| Order-independent ghosts | **Off**, the sorted ghost path draws. Tested with the emulator: with a forced OIT the right eye is wrong even where both eyes share one framebuffer, and on real devices the eyes may sit in separate textures or array layers. `renderer.xrForceOit` exists only for that test. |
| Peelback window | **Off** (mask and jump flood are single-view screen-space targets; picking ignores it too). |
| Imaging (radiograph, MRI) | **Off**, the standard renderer draws; status says `imaging radiograph drawn as standard`. Imaging renders into screen-sized float targets, which neither fit the XR framebuffer layouts nor the per-eye views. |
| Post pipeline (AO, bloom, depth of field, vignette) | **Off**. |

Exit restores everything: the renderer is the normal one (`renderer.xr.enabled` is false again, not just not presenting), the camera is detached from the rig and gets its orbit position, orientation, scale, clip distances and field of view back, the orbit controls are enabled, the background and the clear alpha come back, the canvas is resized to the page, and Algorithm 2 runs from the orbit camera again. The frame loop is the same one before, inside and after the session.

## Frame loop

`app.start()` hands the frame function to `renderer.renderer.setAnimationLoop`: three.js uses `window.requestAnimationFrame` outside a session and the session's own `requestAnimationFrame` inside one. Frame timing statistics and every plugin hook (`onFrame`, `afterFrame`) run in both. A new hook `beforeFrame(app, now, dt)` runs first in every frame; the XR plugin uses it to read the head pose and the controllers, move the rig and bring the camera up to date for the hooks that follow (view-mode planes, sections). `runSightlinesNow` uses `renderer.cameraWorldPosition()`.

## What was verified, and how

- Pure maths (`tests/xr-maths.test.ts`): rig transform (also against a three.js `Object3D`), pose to camera, orbit camera to head, controller ray to world ray, snap turn and its re-arming, walking, the AR placement and both scale presets. Feature detection with fake `navigator.xr` objects (`tests/xr-support.test.ts`).
- **Headless with iwer** (`bench/smoke-xr.mjs`; `iwer` 2.7.0 is a dev dependency, MIT licence, with its own dev-only dependencies `gl-matrix` (MIT) and `webxr-layers-polyfill` (Apache-2.0), injected into the page by the script with `page.addInitScript`, never part of the app or of the bundles: the `npm run build` and `npm run bundle` outputs contain no iwer code, `src/ui/params.ts` imports only `version` from `package.json` so even the name does not appear, and `tests/xr-iwer.test.ts` checks that no file under `src/` mentions it). The emulated Meta Quest 3 gets installed as `navigator.xr`; the script enters VR from the GUI button, checks the camera starts on the orbit position, aims the emulated right controller at the element under the screen centre, pulls the trigger and asserts the selection, squeezes (X-ray toggles), pushes the thumbstick (a 30 degree snap turn, head fixed), walks with the left stick (sightlines run again), turns imaging, peel, behind-only and a section on (the fall back list), exits and asserts that the normal renderer is restored (xr off, no rig, camera scale 1, orbit controls on, frame loop running, the picture pixel identical to the one before entering), then enters AR, places the model with a select and switches to `tabletop 1:50`.
- **Not verifiable here**: anything that needs a real device. The layout of the XR framebuffer (side by side, per-view textures, texture arrays or multiview) and with it the verdict on OIT and imaging on real hardware; real hit-test and the reticle (the emulator has no environment, so the script covers the placement without a surface); hand tracking (the same `select` event, not exercised); performance and foveation; passthrough compositing on a phone; haptics (none are sent). The emulator draws both eyes into the one canvas, which is also what `bench/xr-*.png` show.

## Limits

- Experimental. Tested with an emulated device only.
- Imaging, the peel window, the post effects and order-independent ghosts are not drawn in a session (see above).
- No teleport, no hand-specific gestures beyond the `select` pinch, no depth sensing or occlusion of the model by the real room.
- The model is not rescaled in AR (the viewer is), so very small physical sizes need a camera far plane that follows the rig scale (it does: `clipDistances`), and picking distances shown by the pointer are in model metres divided by the rig scale.
