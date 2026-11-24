# 17. Exchanging issues: BCF

## 17.0 The problem

Your issues live in your browser. The architect uses another program, the structural engineer a third. You cannot ask them to
open your viewer to read "Duct-12 hits Wall-3". And you cannot ask yourself to retype their list of 60 issues. You need a
shared file that every program reads.

## 17.1 The idea: BCF is the file, an issue is what is in it

**BCF** (BIM Collaboration Format) is the common file for issues in building projects. It is a zip file (`.bcfzip`, or `.bcf`)
that holds issues, comments, pictures, and for each issue one or more camera positions with what is selected, hidden and cut.
Read this chapter with one rule in mind: BCF is only the *exchange format*. In the viewer you work with views and issues
(chapters 13 and 15). Exporting turns your issues into a BCF file. Opening a BCF file turns its content into issues and views.

In a BCF file, a camera position with selection, hidden elements, colours and cut planes is called a **viewpoint**. That is the
file's word for what the viewer calls a view. When you open a BCF file, each viewpoint becomes a view of its issue.

The viewer reads BCF 2.0, 2.1 and 3.0. It writes 2.1 (the default) and 3.0.

## 17.2 Try it: a round trip

Use the **FZK-Haus** sample. First make an issue with a drawing, as in 15.1.

1. Open the **Issues** tab and click your issue. Its detail opens.
2. Scroll to the bottom and click **Export BCF 2.1**. The browser downloads a `.bcfzip` of every issue in the list.
3. Click **Delete issue** (it may ask for a second click). The issue goes. Its view stays in the Views tab as a loose view. The status bar says
   `0 open issues`.
4. In the Issues tab, click **Open BCF** and choose the file you just saved. (You can also drop a `.bcf` or `.bcfzip` anywhere
   on the page.)
5. The issue is back, with its status, priority, comments and snapshot. Click it: the camera, selection, hides and cut come
   back, and the status line says what was applied and what was skipped. The Views tab has a view linked to the issue, with your
   drawings.
6. Click **Clear** on the view row. Whatever the file hid or coloured is undone, and only that: elements you hid yourself stay
   hidden.

> Picture: the Issues tab after opening a BCF file, with the status line saying what was applied.

**Opening replaces, unless you have your own.** Opening a file replaces the issues that are loaded. If you have unsaved issues of
your own, the file is merged in instead, and for an issue with the same id the file wins. Issues that belong to other models are
never touched.

**Exporting writes everything.** **Export BCF 2.1** and **Export BCF 3.0** write every issue of the session, including the ones
hidden under **Other models**. Each carries its model's identity, so opening the file on the right model sorts them again.

## 17.3 What a viewpoint does when you apply it

**Apply** (on a view row of an issue) restores what the BCF viewpoint holds:

| In the file | In the viewer |
| --- | --- |
| Perspective camera | Camera position, target and field of view. If your window is narrower than the file's aspect ratio, the field of view widens, as the BCF guide says |
| Orthogonal camera | Approximated by a perspective camera placed so the visible height at the model matches. The status line says so |
| Selection | Those elements, by GlobalId. A viewpoint with no selection clears the selection |
| Visibility | The file's default and exceptions, then the hints for spaces and openings. If this would blank the view (none of the listed elements exist), it is skipped and the status line says so |
| Colouring | A temporary colour on the listed elements. The alpha byte is ignored |
| Clipping planes | The cut planes of the viewer, with the direction reversed as BCF defines it |
| Lines and bitmaps | Not shown, but counted in the status line |

Elements are matched by GlobalId only. Ones the model does not have are counted in the status line and never dropped silently.
Applying a viewpoint first clears the earlier one. **Clear** undoes what the file changed (camera and selection stay where they are).

## 17.4 What survives a round trip

BCF 2.1 and 3.0 have no field for a pin or a drawing. So the viewer writes a small extra file, `xray-markup.json`, in each issue's
folder and leaves the BCF XML as the standards define it. Other programs read only the files the BCF names, so they ignore it. The
BCF is still valid against the official schemas, and the viewer's own export was also read by an open source BCF client.

| Survives in this viewer | Seen by other programs |
| --- | --- |
| Title, description, type, status, priority, labels, assignee, due date, comments | Yes |
| Camera, selection, hides, colours, cut planes | Yes |
| The snapshot picture, with drawings and pin burned in | Yes: it is a picture |
| Elements that drawings point at | Yes: they join the viewpoint's selection, so other tools highlight them |
| Surface and region drawings | As 3D lines in the viewpoint (a box has 12 edges) |
| The pin, with its number | No: only in the side file |
| Drawings as editable shapes (clouds, callouts, attachments) | No: only in the side file |
| Model identity (name, element count, a hash of the GlobalIds) | No: only in the side file |
| A check result that an issue came from (chapter 15.3) | No: only in the side file |

**What it means.** A file that goes out of the viewer and comes back keeps everything. A file that goes through another program
and is saved there usually loses the side file: that program rewrites the zip and drops what it does not know. You still have
the picture, the selection and the text. The drawings come back from the picture and the lines, but not as editable shapes.

**Plan and Section viewpoints.** For each view that is tied to the model (13.3), every export also writes the Plan and the
Section as two more viewpoints right after the view's own: orthogonal cameras with cut planes and the same selection, hides and
colours. They have no snapshot. Other tools read them as ordinary orthographic viewpoints. When you open the file here, they are
not made into views of their own. The issue detail lists them as **Plan (derived)** and **Section (derived)**, each with
**Apply** and **Clear**. Exporting again replaces them and never doubles them.

**Sheet viewpoints.** A view on a PDF sheet (chapter 16) has no camera. It is written as a snapshot of the sheet region and a
reference to the PDF. In 3.0 the PDF is a document of the file. In 2.1 it sits in a `Documents` folder in the zip. Opening such a
file opens the PDF from the zip, if it is not already open, and makes a view of the drawings on the right page, found by a
checksum of the PDF.

## 17.5 Choices and settings

- **Export BCF 2.1 or 3.0.** Choose 3.0 when the other side asks for it. 2.1 limits the field of view to 45 to 60 degrees and has
  no aspect ratio. 3.0 writes the aspect ratio, lower-case ids and an extensions file.
- **Author.** The author of comments and new issues is the name in the **Author** box, which the viewer remembers in this
  browser. It is written into the file.
- **Elements without a valid id.** The built-in demo models have synthetic GlobalIds that the BCF schema would reject. They are
  left out of the selection and visibility lists. Real IFC files are not affected.
- **Params.** The parameters file has a section with the default author and the default export version.

## 17.6 Limits and gotchas

- Orthogonal cameras are approximated. Camera roll is ignored. Lines, bitmaps and the alpha of colours are ignored.
- Only GlobalIds match elements. There is no match by project or file.
- An issue made on another model is hidden under **Other models**. Opened on purpose, it applies its camera but selects nothing,
  and it says how many ids were unknown. An issue from another program has no model identity, so it shows on any model.
- Selection and visibility lists over 1,000 elements work, but the BCF guide asks you to keep them short.
- Other programs that rewrite the zip drop the side file (see 17.4).
- Notes in free space and point-to-point measurements do not follow exploded storeys. The burned snapshot draws anchors at the
  unexploded place even if the snapshot was taken exploded.
- The issue detail has no box for the title or description of an existing issue.
- BCF is not a place to keep secrets. The file holds author names, comments, pictures of your model, and the model's element
  count. Hand it on only to people who may see these.

## 17.7 See also

Chapter 15 (issues, reports), chapter 13 (what a view is), chapter 16 (sheet views in a BCF file), Appendix C (file formats).
