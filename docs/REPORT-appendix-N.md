# Appendix N: Saved views and field AR

Companion copy of Appendix N of the technical implementation report
(BIM X-Ray Vision: Technical Implementation Report). Algorithm numbers continue
from Appendix M (Algorithm 15).

Two features take the X-ray state out of a single session. Saved views let a
designer return to an exact look. Field AR lays that look over the real building
at full scale. Both reuse the classification of Algorithm 1 unchanged; they only
decide which inputs it runs on.

## N.1 Saved views

**What a view is.** A view is the camera plus the inputs to classification: the
selection (the focus set), the hides and pins (Appendix D overrides), the section
box or plane, the exploded flag, the active preset id and the look settings.
Elements are named by IFC GlobalId, so a view survives a reload or a reconversion
of the model. A view stores the user's choices, never per-element alphas: the
alphas are recomputed from the stored inputs, so a view saved before a model
change still gives a correct picture after it.

**Look settings as differences.** The look is the full parameter snapshot minus
the sections a view must not own (tools with their own documents, keymap,
selection sets). On restore it is merged over the factory state, which is the
parameters right after the first model loaded. Only the top-level sections that
differ from the current state are applied, so a restore costs one parameter apply
and one classification run. A share link stores only the leaves that differ from
the factory state, typically 300 to 900 characters.

```c
// Algorithm 16  Restore a saved view

 end any applied BCF viewpoint             // its hides, planes and pins go first
 target   = merge(factory, view.params)     // a missing section resets to factory
 changed  = sections where target != current
 apply(changed)                             // no reclassification yet
 set section box or plane; set clip planes if the view held BCF planes
 overrides = remap(view.hides, view.pins)   // GlobalId -> element; report the missing
 focus     = remap(view.selection)
 classify(focus, overrides)                 // Algorithm 1, once
 if view.exploded: explode(focus)
 turn camera to view.camera over 400 ms     // jump under reduced motion
 mark view.preset active                    // the params already hold its effect
```

**Isolates.** When more than half of the model is hidden, the view stores the
visible elements instead of the hidden ones. This keeps an isolate of three ducts
in a 100,000-element model small.

**Measured.** After a reload, every restore matched the saved camera within 0.001
and the section planes within 0.0001, on the FZK house and on the 5,000-element
synthetic model.

## N.2 Field AR

Field AR is a third XR mode next to the VR and tabletop AR of Appendix M. The
model is never scaled. It is placed by **site registration**: the user names two
or more features on the model, then aims at the same features in the room.

**Registration.** The device's reference space is gravity aligned on ARCore and
Quest, so the solve keeps the model vertical. It is the keep-vertical case of the
point cloud solver: a 2D Kabsch fit for the yaw on plan, plus the mean vertical
offset, at real scale. A full 3D rotation is not offered, because picking noise
would tilt the model, and a tilt of 0.5 degrees moves a duct 9 cm over 10 m.

```c
// Algorithm 17  Field registration and the cut around the user

 // Before the session: model points m[i], snapped on plan to the nearest
 // element vertex within 10 cm, so a click near a wall corner lands on its edge.
 // In the session: room points r[i], one hit test each (screen centre or ray).

 (yaw, shift) = kabsch2D(m.xz, r.xz); shift.y = mean(r.y - m.y)
 report residual[i] on plan and in height; name any pair > 10 cm off
 anchor = createAnchor(centroid(r))         // the rig follows the anchor each frame

 every 25 cm of head movement, or on a storey change:
     feet   = head.y - eyeHeight
     storey = highest storey floor <= feet + 0.5 m
     cut box: plan radius R around the head (default 6 m),
              bottom = storey floor - 1 m, top = next storey floor
```

**Why the cut.** On site the viewer stands inside the model. Without a cut, every
wall, slab and duct of the building lies between the eye and the room: the
stacked-transparency problem that X-ray mode exists to solve, at its worst. The
box removes the far field outright; Algorithm 1 then only has to rank what is in
the room and the storey above the ceiling.

**Field looks.** The looks are class styles laid over the user's own for the
session. *Ghosted* (the default) keeps the focus classes (services), draws
structure at alpha 0.06 and the rest at 0.2: the real walls are what the user
sees, and the model adds what is behind them. *X-ray* shows the focus classes
only. *Full* is the user's own look. On exit the original style object is put back.

**Accuracy.** In the emulator with three pairs, taps off by up to 1 cm gave
residuals of 0.61 to 0.80 cm (RMS 0.73 cm). Two check points not used in the
solve, 2 m and 9 m away, were off by 0.45 and 0.81 cm. On a real phone the hit
test itself adds several centimetres, and tracking drift adds more over a long
walk; the anchor and "Register again" are the remedies.

**Devices.** Field AR needs `immersive-ar` with hit test: Android Chrome with
ARCore, and the Quest headsets in passthrough. Only Quest keeps persistent
anchors, so a saved site comes back there without taps; Android asks for the
saved points again. Safari on iPhone and iPad has no WebXR, and Vision Pro Safari
offers VR only. On those devices the viewer exports the current look to USDZ for
AR Quick Look: the model stands at real size on a tapped surface, but without
registration it is for showing, not for checking on site.

**Limits.** A web page cannot read the camera image in WebXR, so field snapshots
hold the rendered overlay and the head pose, not a photograph. Real tracking
drift, plane detection and the phone panel in `dom-overlay` need a real device;
the reference viewer has been checked only in the iwer emulator.
