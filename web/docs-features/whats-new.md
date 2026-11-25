# What's new

The first time you open a new version of the viewer, a small card in the corner of the 3D view lists what is new in it. This page
says where the text and the version number come from, and when the card stays away.

## What you see

- **The card.** It names the version and lists the newest release's lines of `CHANGELOG.md`. It takes the keyboard focus when it
  appears. **Escape** or **Dismiss** closes it. It shows once per version and per browser.
- **Show all changes.** A link on the card. It opens a dialog with the lines of every release, newest first, each with its date.
- **What's new in the command palette.** The action `help.whatsNew` (no default key) opens the same dialog at any time.
  Assign a key to it in the shortcut editor if you want one.
- It fits a 390 px wide phone screen: the card spans the width above the status bar.

## When the card shows

The browser remembers the last release it saw in `localStorage['xray.whatsnew']`. Nothing else stores or carries it: not the
settings, not a share link, not a packed page.

| Situation | Card | Stored number |
| --- | --- | --- |
| No key (first start ever) | no | set to this release |
| Key older than this release | yes, once | set to this release |
| Key the same or newer (an older build opened later) | no | unchanged |
| Packed page (`xray-pack`), kiosk page, `?embed` or `?kiosk`, page in a frame | never | unchanged |
| `localStorage` blocked (private window) | no | none |

The decision is the pure function `decideWhatsNew` in `src/whatsnew/changelog.ts` (`tests/whatsnew.test.ts`).

## Where the text comes from

`CHANGELOG.md` at the repository root. `src/plugins/whatsNew.ts` imports it with Vite's `?raw`, so the single-file build carries
it and no request is made. `parseChangelog` reads `## Unreleased` and `## vN - YYYY-MM-DD` headings with `- ` lines under them (a
line may continue on indented lines). "Unreleased" is never shown. The card shows the first section that has a release number.

Writing a release: rename "Unreleased" to `vN - YYYY-MM-DD` and fill it, then build.

## Where the release number comes from

`web/tools/release-number.mjs` reads `tools/viewer-release.txt` (the last released number) when vite starts and defines the
constant `__XRAY_RELEASE__` (`src/whatsnew/release.ts`); it also writes `<meta name="xray-release" content="N">` into the page.
`tools/release_viewer.sh` bumps the counter after the build, so a release is built with `RELEASE=1`, which gives counter + 1:

```sh
cd web && RELEASE=1 npm run bundle      # then: bash ../tools/release_viewer.sh
```

`release_viewer.sh` checks the meta tag of the built file against the number it is about to assign and stops when they differ.
A development server and the smoke tests show the last released number.
