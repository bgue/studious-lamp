# 22. Fly-throughs

You have to show the client why the duct runs under the beam. A live walk-through means you orbit, lose the spot, and say "wait, it was
here". A video made by screen recording shakes and cannot be re-timed. What you want is a camera trip you build once from places
you already saved, play at a meeting, tune, and turn into a video file.

## 22.1 Build a fly-through from views

### The idea

A **fly-through** is a sequence of **keyframes** with timing. A keyframe starts from a saved view (chapter 13) and takes its
camera, section, selection, hides, settings and preset. It adds how long to take to get there and how long to stay. The keyframe
keeps its own copy of the view: editing the view later does not change it, and **Update** retakes it from the current view. The
viewer draws a smooth camera path through all the keyframes. Between them it blends the settings and fades elements in and out.

Drawings on a view (chapter 14) are not drawn during playback. The keyframe takes the camera and the look only.

Think of a film storyboard. Each frame is a place you chose. The viewer is the camera crew that works out the move between the frames.

### Try it

Use **FZK-Haus**. If you have no saved views yet, make three first (chapter 13): the outside, a view of the roof with a
section, and a view of the heating pipes in the cellar.

1. Open the **Views** tab of the left sidebar. Find the **Fly-through** section.
2. Click **New**. A fly-through is a named list, and a model can hold several.
3. Click **From views**. It replaces the keyframes with one per saved view. The list next to **Add keyframe** adds one view. (**From sets** does the same with one per selection
   set, the camera framed on the set.) To add one at a time, orbit to a place and click **Add keyframe**.
4. Each keyframe is a card with a thumbnail, its name and the move (`to 2 s`, `hold 1 s`). Click a card to go there. Drag the grip,
   use the arrow buttons or press `Alt+Left` and `Alt+Right` to reorder. `Delete` removes the card.
5. Select a card. In its editor set **Hold** to 1 s, so the camera pauses on arrival. Set **Fade** on, so what appears fades in and
   what disappears fades out over the last 40 % of the move. Type a caption title and text.
6. Choose **Timing**: **Constant speed** (default; metres per second along the path) or **Seconds per move** (the same time each move).
7. Click **Play**.

While the section is open, the camera path is drawn in 3D as a dashed line, with a small camera marker per keyframe. It is hidden
while the fly-through plays or records.

### How it works

Playing a fly-through means compiling it into a timeline and handing it to the player (chapter 21). What it compiles to:

- **The camera path**: a smooth spline through every pose (it passes through each keyframe, has no corners, and does not overshoot
  when keyframes are unevenly spaced). Up vector and field of view follow it. At the start, the end and around every hold the
  camera eases in and out, for at most 1.4 s. A keyframe passed without a hold does not slow the camera.
- **Settings**: numbers blend over the move; on/off and text switch at the keyframe's **Switch at** (start, middle or end of the move,
  default arrival). A section box that moves between keyframes animates.
- **Fades**: elements newly shown fade in and newly hidden fade out over the last 40 % of the move. Without a fade the change switches
  at **Switch at**.
- **Selection**: the keyframe's selection is made shortly before arrival, so a selection effect runs as the camera arrives.
- **Captions**: shown at arrival as a lower third, as long as the hold (2.5 s with no hold).
- **Labels and hover card**: if you turn on **Label selection** or **Hover card** for a keyframe that has a selection, a tag with
  the fields you pick (empty means name, class, storey), or the hover card, shows at arrival.

### Choices and settings

| Control | Effect |
| --- | --- |
| **Travel** | Seconds into this keyframe. Empty uses the timing choice |
| **Hold** | Pause on arrival |
| **Ease** | Shape of the start and end of the move |
| **Fade** and its length | Fade the elements that appear or disappear |
| **Switch at** | When non-numeric settings flip |
| **Look at selection** | The camera stays pointed at the keyframe's selection |
| **Loop** | Repeat from the start |
| **Update** | Replace this keyframe's state with the current view |
| **Insert after** | Add a copy after this one |

The **⋯** menu of the fly-through list renames, duplicates, exports, imports and deletes. Export saves an `xray-flythroughs/1`
file that you can send. **Progress bar**, **Compass**, **Scale bar**, **Label size** and the caption position are in **On-screen
display** (21.1).

### Limits and gotchas

- Label and hover options need a selection in the keyframe. Select the elements, then click **Update**.
- Fly-throughs are kept per model in this browser. A different model with the same name does not inherit them.
- Fly-throughs are not saved into the IFC. Export the file to keep or share them.

## 22.2 Play, pause, scrub, use the display

### The idea

You will play the same fly-through many times while you tune it. The transport bar is built for that.

### Try it

1. Click **Play**. It starts from the beginning. **From** starts from the selected keyframe, which is how you tune a single move
   without watching the rest.
2. Press `Space` or click **Pause**. Click or drag on the timeline bar to jump. A tick marks each keyframe, and the bar shows the holds.
3. Press `Left` and `Right` for the previous and next keyframe. If you are more than 0.6 s into a move, `Left` goes back to the
   keyframe that began it. With the timeline bar in focus, they move it by 1 s instead.
4. Click **Stop** or press `Esc`. Camera, selection, hides, settings and preset go back as they were.
   If you were in Walk mode (3.2), playing leaves it, and `Shift+w` does nothing until the fly-through ends.
5. Click on the 3D view during play: it stops, and keeps the camera where you took it.

### How it works

This is the shared player: chapter 21 explains pause, seek, restore and the on-screen display. In a fly-through, the chapters of
the progress bar are the keyframes.

### Limits and gotchas

- Ghosting lags a little behind the camera, and depth of field and motion blur apply during playback (see 21.1).

## 22.3 Export a video

### The idea

A screen recording captures whatever your computer managed to draw, dropped frames included. The export here does not record the
screen. It plays the timeline **frame by frame**: for frame *i* the exporter advances the clock by exactly 1/fps, draws the viewer's
frame, adds the on-screen display, and hands the picture to an encoder. A slow machine makes a slow export, never a stuttering video.

### Try it

1. Click **Rec** in the Fly-through section. (In the Script tab the button is **Record**.) The **Record a video** dialog opens.
2. Choose **Size**: the window, 1280 x 720, 1920 x 1080, 2560 x 1440 or 3840 x 2160.
3. Choose **Frame rate**: 24, 30 or 60. Choose **Quality**: small file, balanced or high quality.
4. Choose **Format**: automatic, MP4, WebM or PNG sequence.
5. Leave **Captions and labels** on if you want the display in the video. Edit the file name if you like.
6. At 2560 x 1440 or above, click **Time a few frames**. It renders 4 test frames and tells you how long the whole video will take.
7. Click **Record** in the dialog. An overlay blocks mouse and keys, and shows *Frame n of N* and the time left. Click **Cancel** or press `Esc` to stop.
   When it ends, is cancelled or fails, camera, selection, hides, settings and the render size are put back.

### How it works

The video holds exactly duration x fps frames at fixed timestamps. The encoder is the browser's own hardware-aware encoder
(WebCodecs) through a small muxing library loaded on the first export. *Automatic* uses MP4 with H.264 when the browser can
encode it, else WebM with VP9, else VP8. *MP4* never falls back to WebM. *WebM* never uses H.264. A browser that cannot do the one you
asked for says so.

A browser without WebCodecs records in **real time** from a copy of the canvas (WebM, or MP4 on Safari) at the window size. That
export can drop frames on a slow machine. A browser with neither writes a **PNG image sequence** in a zip. You can also choose
it on purpose: it needs memory, so keep it short (at most 65,535 frames and 4 GB).

The size is limited by what the graphics card can draw. A larger size is scaled down with the aspect kept, and the sides are made even.
The quality choice is bits per pixel and frame: 0.04, 0.08 or 0.16.

### Limits and gotchas

- 4K takes long on a slow machine or a software renderer. Use **Time a few frames** first. The overlay warns past 5 minutes.
- Effects that start from the wall clock (the staggered reveal, sweep, pulse) follow the export's own frame clock from the moment
  they start.
- MP4 depends on the browser. Firefox and Safari are untested.
- Video export is off inside a headset session.

### See also

Chapter 13 (views), chapter 21 (the player and the display), chapter 23 (scripts, which export the same way).
