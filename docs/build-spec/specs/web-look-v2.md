# Web look v2: a modern feel on the same layout

Status: accepted 2026-11-05 (owner: "The web interface is too much styled like the TUI; you can modernize it in feel
while preserving a similar layout"). Applies to `packages/tl-web` only. The terminal is unchanged.

## What stays
The log standard and its order on the page: crumb, filter, list, panel (right of the list from 1280 CSS px, below it
otherwise), actions, keys, status. Record screen tabs. The same routes, HTMX swaps, keyboard keys, CSP (no inline
style or script, no external host: fonts are the system stack, nothing is fetched). Hidden looks exactly like missing.

## What changes
1. **The panel and the record Details tab are HTML, not terminal text.** The `tl_tui.layout.Page` that each log builds
   today (and flattens with `present.plain_lines`) is rendered by one Jinja macro, `templates/page.html`:
   - `page.identity` → `<h2 class="tl-page-id">`; `page.state` → `<span class="tl-badge tl-<tone>">` where tone comes
     from `layout.state_style(state)`: `green` → `tl-done`, `yellow` → `tl-waiting`, `red` → `tl-bad`, else `tl-neutral`.
   - `page.summary` → `<p class="tl-summary">`.
   - each `Section` → `<section class="tl-sec"><h3>heading</h3>…</section>`; an empty section shows
     `<p class="tl-note">note</p>`.
   - consecutive `Prop` items → one `<dl class="tl-props">` (`<dt>` label, `<dd>` value; an empty value shows `—`).
   - consecutive `TableRow` items with the same `columns` → one `<table class="tl-mini">` with a `<thead>`; a `Cell`
     with a style gets the same tone class as the badge.
   - a `str` item → `<p class="tl-line">`.
   A log whose panel is not a `Page` (the PDF image, a free-text panel) keeps `<pre class="tl-panel-text">`.
2. **The State column of every list is a badge**: the `<td>` keeps its text and gets `tl-badge tl-<tone>` on an inner
   `<span>`.
3. **Actions are buttons without brackets**: `<button class="tl-btn">Accept <kbd>A</kbd></button>`; Open record is
   `<a class="tl-btn tl-primary">Open <kbd>Enter</kbd></a>`. The key still works as before.
4. **A new stylesheet** (`static/tl.css`, rewritten) with the tokens and components below.

## Tokens (CSS custom properties on `:root`; dark values under `@media (prefers-color-scheme: dark)`)
| Token | Light | Dark |
|---|---|---|
| `--bg` | `#f6f7f9` | `#0f1115` |
| `--surface` | `#ffffff` | `#171a21` |
| `--surface-2` | `#f0f2f5` | `#1f232c` |
| `--border` | `#e2e5ea` | `#2b303b` |
| `--text` | `#1a1f29` | `#e7e9ee` |
| `--muted` | `#5f6878` | `#9aa3b3` |
| `--accent` | `#2563eb` | `#6b9dff` |
| `--accent-weak` | `#2563eb14` | `#6b9dff1f` |
| `--done` / `--done-weak` | `#15803d` / `#15803d1a` | `#4ade80` / `#4ade801f` |
| `--waiting` / `--waiting-weak` | `#b45309` / `#b453091a` | `#fbbf24` / `#fbbf241f` |
| `--bad` / `--bad-weak` | `#b91c1c` / `#b91c1c1a` | `#f87171` / `#f871711f` |
| `--radius` / `--radius-sm` | `10px` / `6px` | same |
| `--shadow` | `0 1px 2px #1018280f, 0 1px 3px #1018281a` | `none` |

Font: `font-family: Inter, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; font-size: 14px; line-height: 1.5`;
numbers in tables `font-variant-numeric: tabular-nums`. No monospace except `<kbd>` and `.tl-panel-text`.

## Components
- **Top bar** `header.tl-bar`: 56px high, `--surface`, bottom border, 0 24px padding; `.tl-brand` 15px 600 with a 10px
  accent square before it (`::before`, radius 3px); Sign out is a ghost `.tl-btn`.
- **Page** `main`: 24px padding, `--bg` behind; logs use the full width.
- **Crumb** `.tl-crumb`: 13px `--muted`; the record part (after the last `›`) is not split: the whole crumb is one line,
  the last 600 weight is not required (it is one text node). Margin below 4px.
- **Filter** `.tl-filter input[type=search]`: 36px high, 320px max, `--surface`, border, `--radius-sm`, 12px left padding;
  focus: border `--accent` and a 3px `--accent-weak` ring.
- **List** `.tl-table`: a card (`--surface`, border, `--radius`, `--shadow`, `overflow: hidden`). `th`: 12px, 500,
  uppercase, letter-spacing .04em, `--muted`, `--surface-2` background, 10px 12px padding, sticky top. `td`: 10px 12px,
  border-bottom `--border` (none on the last row). No zebra. Hover: `--surface-2`. Selected (`aria-selected=true`):
  `--accent-weak` background and `box-shadow: inset 3px 0 0 var(--accent)`; text stays `--text`. Focus-visible: 2px
  `--accent` outline, offset -2px.
- **Badge** `.tl-badge`: inline-block, 12px, 500, 2px 8px, radius 999px; `.tl-done` `--done` on `--done-weak`,
  `.tl-waiting`, `.tl-bad` likewise, `.tl-neutral` `--muted` on `--surface-2`.
- **Panel** `.tl-panel`: a card like the list, 16px 20px padding, no coloured side border; same max-heights as today.
  `.tl-page-id` 16px 600 margin 0; the badge sits on the next line with `.tl-summary` (13px `--muted`) after it.
  `.tl-sec` margin-top 20px; `.tl-sec h3`: 11px, 600, uppercase, letter-spacing .06em, `--muted`, margin 0 0 8px.
  `dl.tl-props`: grid `minmax(120px, 34%) 1fr`, gap 6px 16px; `dt` `--muted`; `dd` margin 0, `overflow-wrap: anywhere`.
  `table.tl-mini`: full width, collapse; `th` 12px `--muted` 500 left, bottom border; `td` 6px 8px 6px 0, bottom border
  `--border`; wide tables scroll inside a wrapper `.tl-mini-wrap { overflow-x: auto }`. `.tl-note` `--muted` italic.
  `.tl-line` margin 4px 0.
- **Buttons** `.tl-btn`: 32px high, 0 12px, `--surface`, border, `--radius-sm`, 500, `--text`, inline-flex, gap 8px;
  hover `--surface-2`; `.tl-primary`: `--accent` background, white text, no border. `kbd`: 11px monospace, `--muted`,
  border, radius 4px, 0 5px, `--surface-2`.
- **Keys** `.tl-keys`: 12px `--muted`; hidden below 900px.
- **Status** `.tl-status`: 13px; when not empty: `--surface-2`, `--radius-sm`, 6px 10px.
- **Forms** (sign-in, action forms): labels 13px 500; inputs/selects/textarea 36px min height, border, `--radius-sm`,
  `--surface`; same focus ring as the filter; submit buttons `.tl-btn.tl-primary` look (style `button[type=submit]` so
  no template has to change). `.tl-error`: `--bad`, 500.
- **Sign-in**: `main:has(form[action="/web/sign-in"])` centres a 360px card (`--surface`, border, `--radius`,
  `--shadow`, 28px padding) 12vh from the top; the button is full width.
- **Record screen**: `.tl-rec-header h1` 20px 600; `#rec-tabs`: no box borders, 1px bottom border; a tab is 8px 12px,
  `--muted`; hover `--text`; current: `--accent` text, 600, `box-shadow: inset 0 -2px 0 var(--accent)`. `.tl-history`
  like `table.tl-mini`.
- **Phone** (< 900px): main padding 12px; the list and panel stack as today; drop columns as today.
