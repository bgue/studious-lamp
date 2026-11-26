# 4D storyboard

A **storyboard** is a PDF of still frames of the 4D film at chosen dates: a grid of pictures on landscape pages, each with its date, week number and the work going on, and the colour legend once per page. It is made for a report or a wall, where a video cannot go. Code: `src/schedule/storyboard.ts` (dates, captions, page maths and the PDF, pure), `src/anim/record/session.ts` (`Recorder.stills`, the frames in the viewer), `tools/xray-4d/commands.mjs` (the CLI).

## In the viewer

4D tab > Film step > the film bar > **Storyboard PDF**. The viewer plays the film's own score (the director's camera, explode, focus and temporary works when the plan has them) and, for each date, seeks there, draws one frame at 960 x 540 and keeps it as JPEG (quality 0.85, so the file stays small). The frames carry no HUD: the date and the legend are on the page. The PDF is built with pdf-lib, loaded on first use (the single-file build carries it). The default is a frame every week, A4, three columns; `window.__xray4dSchedule.storyboard({ every, page, cols, download })` takes the same choices (`lastStoryboard` says how many pages and frames the last one had).

## On the command line

```
xray-4d storyboard build.4d.json --model model.ifc [--every week|month|milestone|N] [--page A3|A4] [--cols 3]
                   [--script film.xrayanim] [--size 960x540] -o board.pdf
```

| Option | Meaning |
| --- | --- |
| `--every` | `week` (default): the first day of the window and every 7 days after it; `month`: the first day and each first of the month; `milestone`: one frame per milestone; `N`: N frames spread evenly over the window (`1` is the last day). The last day of the window is always the last frame, except for `milestone` and `N`. At most 200 frames. |
| `--page` | `A4` (default) or `A3`, landscape. |
| `--cols` | Frames across a page, 1 to 8 (default 3). The rows follow from the page height. |
| `--script` | An `.xrayanim` script whose camera cues give each frame its view (as for `render`). Without it the camera stays where the model opens. |
| `--size` | Frame size in pixels (default 960x540; 1280x720 on A3). |

It uses the same headless Chromium path as `render` (page assembly with `xray-pack`, software GL), then lays the frames out in node with the same code as the viewer. The last stdout line is a JSON summary (file, pages, frames, bytes). Exit 5 when the render fails.

## The page

- **Title block**: project, `Schedule data date`, `Generated` date, the `every` choice and frame count, `Page n of m`.
- **Frames**: a grid, 16:9 by default; a frame is as wide as the page allows for the columns. The rows per page fill the space between the title block and the legend.
- **Caption** under each frame: the date and `Week n`, then the top three running activities (most elements first), then `+N more`. A frame with no running activity says `Complete` at the end or `No work in the model`.
- **Legend** at the foot of every page: the trades of the film and the state key, as in the HUD ([4d-playback.md](4d-playback.md)).

Text is Helvetica; characters outside Latin-1 print as `?`.
