# How the manual is written

The X-ray viewer manual is written in a Feynman-like way: start from the problem a person has, explain the idea in plain
words with a concrete example, show how to do it, then say what is really going on underneath, and be honest about the
limits. A reader should finish a chapter able to do the thing and able to explain why it works.

## Every chapter has this shape

1. **The problem** (2–5 sentences). What goes wrong without this feature, in the reader's world (a site meeting, a clash,
   a client presentation, a weekly schedule update). No feature names yet.
2. **The idea** (one or two paragraphs). The simplest true explanation, with an everyday comparison when it helps
   (x-ray: "a radiologist sees the bone because the flesh is made faint, not removed"). Define every new word here, once.
3. **Try it** (a numbered walk-through on a sample model that ships with the viewer: FZK-Haus, Process plant, Building,
   Synthetic 5k, Debris demo, or the FZK-Haus 4D sample). Real button labels in **bold**, keys in `code`, what you should see
   after each step.
4. **How it works** (the mechanism in plain words: what is computed, what is stored, what is not). No code, no internal
   names, unless the reader is a developer ([D] sections may name files and `window.__xray…` hooks).
5. **Choices and settings** (only the ones that change outcomes; link the settings appendix for the rest).
6. **Limits and gotchas** (what it cannot do, what surprises people, what is experimental).
7. **See also** (two or three cross-references by chapter number).

Not every chapter needs all seven; short reference chapters (appendices) are tables and lists.

## Voice

- Talk to the reader ("you"). Active voice, present tense. Short sentences (aim under 20 words). One idea per paragraph.
- Concrete before abstract: show the duct behind the wall, then name "focus" and "occluder".
- Explain why, not only how. If a step looks arbitrary, say what it prevents.
- Honest: say "experimental", "untested on Safari", "slow on a software renderer" where true. Never promise.
- No marketing words (seamless, powerful, effortless, cutting-edge). No exclamation marks.
- Numbers as digits ("3 storeys"). Units with a space ("2 m", "90 s").

## Words (use these, and only these, for users)

| Say | Means | Do not say (glossary only, as "formerly") |
| --- | --- | --- |
| view | a captured moment: camera, what is shown, hidden, cut and selected; may carry drawings | sketch, markup set, viewpoint (except when talking about BCF files) |
| drawing | a cloud, arrow, text, callout, shape or pen line on a view | markup, annotation (except PDF annotations) |
| issue | a problem someone must act on: status, priority, assignee, due date, comments; points at one or more views | topic, BCF topic |
| sheet | a page of a PDF drawing set, shown as a view you can draw on | sheet sketch |
| mode | one of the five top-bar looks (Solid, Ghost, Radiograph, Glow, Cutaway) | |
| preset | a saved look (settings only, never the camera) | |
| set | a named group of elements, fixed or defined by a query | selection set (fine on first use) |
| query | a condition in the query language (`class = 'IfcWall' and storey = 'Level 2'`) | criteria, WHERE (fine once) |
| fly-through | a sequence of views with timing | tour (that old feature is mentioned only in limits) |
| script | an animation script (`.xrayanim`) | DSL, score |
| player | what plays fly-throughs, scripts and 4D films | score player |
| 4D plan | what each element is doing at each date | |
| link (4D) | an activity and the elements it builds or removes | |
| focus / context / occluder | the x-ray roles (defined in chapter 1) | |

BCF is named only as a file format ("export the issues as BCF"). Internal names (score, cue, markup, topic, HUD layer)
appear only in [D] sections.

## Format

- Markdown, one file per chapter: `docs/manual/NN-short-name.md` (two-digit chapter number), appendices `A-keys.md` etc.
- Headings use the chapter number without a leading zero: `# 1. Title`, `## 1.1 Title`, matching the TOC numbers. File names keep two digits (`01-what-it-is.md`).
- Reader tags from the TOC ([C], [P], [D]) on sections that are only for one kind of reader.
- Tables for comparisons (what each thing stores, which tool for which job). At most one table per section.
- No screenshots in this pass; where a picture would help, write `> Picture: <what it should show>` on its own line.
- Length: 1,200–3,000 words per chapter; appendices as long as needed.
- Cross-references: "see chapter 15" or "see 15.3". Links to source docs are not part of the manual text.

## Accuracy

- Every fact comes from the source docs named in the TOC (`web/docs-features/*.md`, `README.md`, `SPEC.md`, `docs/`), and
  when they disagree or are unclear, from the code (`web/src/…`). Do not invent buttons, keys or numbers.
- If something cannot be confirmed, leave it out or mark it `> Check: …` for the editor.
- Part V describes the Views + Issues model (decided 2026-11-23); its UI is being changed at the same time. Its chapters are
  written after that change lands, from `docs/design/views-and-issues.md`.
