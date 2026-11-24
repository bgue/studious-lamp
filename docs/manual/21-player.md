# 21. One player behind every "Play"

You build a fly-through on Monday, write a script on Tuesday and play a 4D film on Wednesday. If each had its own buttons, its own
keys and its own way of putting the model back, you would relearn the same thing three times. And a video made from each would look
different. In this viewer the three, plus the autoplay of a packed page, share one machine.

## 21.1 Fly-throughs, scripts, 4D films and kiosk autoplay

### The idea

A **player** plays a **timeline**. A timeline is a list of things that happen at a time: the camera moves from here to there
between second 2 and second 5, a caption shows from second 5 to second 8, the slabs fade out from second 8. Think of a conductor's
sheet. Each instrument has its own line, and the conductor's baton moves along all of them together.

Four things produce a timeline, and one player plays any of them:

| Source | You make it in | Chapter |
| --- | --- | --- |
| Fly-through | **Views** tab, **Fly-through** section | 22 |
| Script | **Script** tab of the right sidebar | 23 |
| 4D film | **4D** tab, **Play** | 27 |
| Kiosk autoplay | a packed page that starts playing by itself | 30 |

So whatever you learn about pausing, scrubbing or stopping here holds for all four. The video export (22.3) is the same player
too, run frame by frame.

### Try it

Use the **FZK-Haus 4D** sample for the 4D film, or any model with a few saved views for a fly-through.

1. Start something. In the **Script** tab type `fly to everything over 3 seconds` and press **Run**. Or in the **Views** tab, open
   **Fly-through**, add two keyframes and press **Play**. Or open the FZK-Haus 4D sample, which leaves the **4D** tab on **Play**.
2. While it plays, press `Space`. It pauses, and the picture holds. Press `Space` again to resume.
3. In a fly-through, click or drag on the timeline bar at the bottom of the section. The model jumps to that moment and
   continues from there. Press `Right` and `Left` to jump to the next and previous keyframe.
4. Play it again and, halfway, click or turn the wheel on the 3D view. Playing stops and the camera stays where you took it.
   Everything else goes back.
5. Play it once more and let it end. The camera, selection, hidden elements, settings, explode and the active preset
   are all as they were before **Play**.
6. Press `Esc` while it plays. It stops, and everything goes back, camera included.

### How it works

**What the player does.** It keeps a clock. On every frame it advances the clock (not past 0.25 s at once, so a stalled tab does
not skip ahead), starts each item whose time has come, and updates the ones that are running. Each kind of item has a small
helper that knows how to do it: move the camera along a path, blend a number, show or hide elements with a fade, pick a preset,
select, put up a caption. An item the helper does not know is skipped.

**Scrubbing is not a jump.** When you scrub or seek, the player restores the starting state and replays every item up to the new time.
So the picture at second 14 is the same whether you got there by playing, by scrubbing or by pressing a key. A 4D film evaluates the
schedule from scratch at that moment for the same reason.

**Restore at the end.** Before it starts, the player remembers the camera, selection, hides, settings, explode state and active
preset. When the timeline ends or you stop it, it puts them back. The exception is a press or a wheel turn on the 3D view. That
means you want the camera, so the camera stays and the rest returns. A **loop** restores and starts again.

**Element references.** A timeline names elements by a query, a set name, GlobalIds or "the selection". The player looks these up
once when it starts. If you edit the model while it plays, the picture does not change. The selection is read at the moment
its item runs.

**Keys.** They work while something plays and you are not typing in a box.

| Key | Action |
| --- | --- |
| `Space` | Pause or resume |
| `Right`, `Left` | Next or previous keyframe of the active fly-through |
| `Esc` | Stop, and put everything back |
| a press or wheel on the 3D view | Stop, keep the camera, put the rest back |
| `Shift+w` | Nothing. Walk mode (3.2) cannot start while something plays, and starting a fly-through, script or 4D film leaves it. |

**The on-screen display.** Everything that shows over the 3D view while it plays comes from one layer, drawn on a transparent canvas
above the view. It takes no mouse input. The same layer is drawn into every frame of an exported video, so what you see is what the
video holds.

- **Captions** are a lower third with a title and a line of text, fading in and out over 0.3 s. They can sit at the bottom or top.
  When two overlap, the later one shows.
- **Labels** pin a tag to each element with fields you ask for: name, class, storey, material, GlobalId, type or any property.
  Tags never overlap each other or the caption. At most 12 show, with a "+N more" counter.
- The **hover card** shows the card of the first element, with a leader line.
- The **progress bar** at the bottom has a mark for each chapter (the arrival at each keyframe, or the start of each caption in a
  script) and the elapsed and total time. On by default. In a 4D film the time is replaced by the schedule date.
- The **compass** (off by default) draws a north arrow at the top right. North comes from the map when it is on, else the site's
  true north, else the model's +Y.
- The **scale bar** (off by default) draws a round length at the bottom left.
- A 4D film adds the schedule date, week and percent complete, the current activities, an S-curve, milestone captions and a
  legend. Chapter 27 explains these.

Where you set these: in the **On-screen display** block of the Fly-through section of the Views tab: **Progress bar**,
**Compass**, **Scale bar**, **Label size** (9 to 28) and the caption position. They are stored with the fly-throughs of the
model and apply to scripts as well.

### Choices and settings

- **Loop** repeats a fly-through or a script. A packed kiosk page takes `--loop`.
- The on-screen display options above.
- Cinematic effects that apply during play are depth of field and motion blur, set in the **Cinematic** folder (see 6.3).
- Video export (22.3) takes size, frame rate, quality and format.

### Limits and gotchas

- Walk mode is left when something starts to play, so the camera keys of Walk mode (`w a s d q e`) do nothing during playback. After it ends, press `Shift+w` to walk again.
- Space, Left, Right and Esc work only while the player plays and the cursor is not in a text box. Typing a caption does not trigger them.
- `Left` and `Right` know only fly-through keyframes. During a script or a 4D film they jump to the keyframe times of the active fly-through, and do nothing when it has none. Use `Space` and `Esc`, or the date slider of a 4D film, instead.
- When the timeline bar has the focus, `Left` and `Right` move it by 1 s (`Shift` for 5 s).
- The sightline algorithm (x-ray ghosting) runs on timers after the camera moves, so a frame can show the ghosting of a nearby
  pose. Expect a slight lag on a slow machine.
- Opening another model while it plays abandons the run without restoring, because the old state no longer exists.
- The older Cinematic tour and the saved-view slide show have simple players of their own. They are not this one.

### See also

Chapter 22 (fly-throughs), chapter 23 (scripts), chapter 27 (the 4D film), chapter 30 (kiosk pages).
