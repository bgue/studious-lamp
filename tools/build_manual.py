#!/usr/bin/env python3
"""Build the X-ray viewer manual (docs/manual/*.md) into one self-contained HTML page.

    pip install markdown==3.7
    python tools/build_manual.py [-o docs/manual/xray-manual.html] [--fragment]

Parts and chapter titles come from docs/manual/TOC.md; chapter text from the NN-*.md and A-*.md files. Cross-references
("see chapter 15", "see 15.3", "Appendix B") become links. `--fragment` writes the page without <html>/<head>/<body> (the
form the artifact publisher wraps itself).
"""
from __future__ import annotations

import argparse
import html
import re
import sys
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parent.parent
MAN = ROOT / "docs" / "manual"

LIST_RE = re.compile(r"^( +)([-*+]|\d+\.)( )")


def normalise(md: str) -> str:
    """Python-Markdown wants 4-space nesting and a blank line before a list; the manual uses 2-3 spaces and tight lists."""
    out: list[str] = []
    fence = False
    prev = ""
    for line in md.split("\n"):
        if line.lstrip().startswith("```"):
            fence = not fence
            out.append(line)
            prev = line
            continue
        if not fence:
            m = LIST_RE.match(line)
            if m:
                n = len(m.group(1))
                depth = 1 if n <= 3 else 2 if n <= 7 else 3
                line = " " * (4 * depth) + line[n:]
            # Continuation lines of a list item indented by 2-3 spaces: 4.
            elif re.match(r"^ {2,3}\S", line) and prev.strip() and not prev.startswith("|"):
                line = "    " + line.lstrip()
            is_item = bool(re.match(r"^\s*([-*+]|\d+\.) ", line))
            prev_item_or_cont = bool(re.match(r"^\s*([-*+]|\d+\.) ", prev)) or prev.startswith("    ")
            if is_item and not line.startswith(" ") and prev.strip() and not prev_item_or_cont and not prev.startswith(">"):
                out.append("")
        out.append(line)
        prev = line
    return "\n".join(out)


def slug_section(num: str) -> str:
    return "s-" + num.replace(".", "-")


def chapter_files() -> list[tuple[str, Path]]:
    files = []
    for p in sorted(MAN.glob("*.md")):
        m = re.match(r"^(\d\d)-", p.name)
        if m:
            files.append((str(int(m.group(1))), p))
    for p in sorted(MAN.glob("[A-H]-*.md")):
        files.append((p.name[0], p))
    return files


def read_parts() -> list[tuple[str, list[str]]]:
    """[(part title, [chapter keys])] from TOC.md."""
    parts: list[tuple[str, list[str]]] = []
    for line in (MAN / "TOC.md").read_text(encoding="utf-8").split("\n"):
        if line.startswith("## Part ") or line.startswith("## Appendices"):
            parts.append((line[3:].strip(), []))
        else:
            m = re.match(r"^### (\d+)\. ", line) or re.match(r"^### (?:Appendix )?([A-H])[.:] ", line)
            if m and parts:
                parts[-1][1].append(m.group(1))
    return parts


def render_chapter(key: str, path: Path) -> tuple[str, str, list[tuple[str, str]]]:
    """(title, html, [(section number, section title)])."""
    text = path.read_text(encoding="utf-8")
    first, _, body = text.partition("\n")
    title = re.sub(r"^#\s+", "", first).strip()
    title = re.sub(r"^(Appendix [A-H]\.|\d+\.)\s*", "", title)
    sections: list[tuple[str, str]] = []

    def head(m: re.Match) -> str:
        num, t = m.group(1), m.group(2).strip()
        sections.append((num, t))
        return f'## {t} {{: #{slug_section(num)} data-num="{num}" }}'

    body = re.sub(r"^## ((?:\d+|[A-H])\.\d+)\s+(.+)$", head, body, flags=re.M)
    body = normalise(body)
    md = markdown.Markdown(extensions=["tables", "fenced_code", "attr_list", "sane_lists"], output_format="html")
    out = md.convert(body)
    # Blockquote notes: "> Picture:" become figure placeholders.
    out = re.sub(
        r"<blockquote>\s*<p>Picture:\s*(.*?)</p>\s*</blockquote>",
        lambda m: f'<figure class="pic"><span class="pic-k">Picture</span><figcaption>{m.group(1)}</figcaption></figure>',
        out,
        flags=re.S,
    )
    # Section numbers in front of the h2 text.
    out = re.sub(r'(<h2 data-num="([^"]+)" id="[^"]+">)', r'\1<span class="num">\2</span> ', out)
    out = re.sub(r'(<h2 id="[^"]+" data-num="([^"]+)">)', r'\1<span class="num">\2</span> ', out)
    out = re.sub(r"<table>", '<div class="tbl"><table>', out)
    out = re.sub(r"</table>", "</table></div>", out)
    out = re.sub(r"<pre>", '<pre tabindex="0">', out)
    return title, out, sections


def link_refs(h: str, known_ch: set[str], known_sec: set[str]) -> str:
    """Cross-references outside code and tags become links."""
    parts = re.split(r"(<pre.*?</pre>|<code>.*?</code>|<span class=\"num\">.*?</span>|<a .*?</a>|<[^>]+>)", h, flags=re.S)

    def ch(m: re.Match) -> str:
        word, n = m.group(1), m.group(2)
        return f'<a href="#ch-{n}">{word} {n}</a>' if n in known_ch else m.group(0)

    def chs(m: re.Match) -> str:
        word, a, sep, b = m.group(1), m.group(2), m.group(3), m.group(4)
        la = f'<a href="#ch-{a}">{a}</a>' if a in known_ch else a
        lb = f'<a href="#ch-{b}">{b}</a>' if b in known_ch else b
        return f"{word} {la}{sep}{lb}"

    def sec(m: re.Match) -> str:
        n = m.group(1)
        return f'<a href="#{slug_section(n)}">{n}</a>' if n in known_sec else m.group(0)

    def app(m: re.Match) -> str:
        n = m.group(1)
        return f'<a href="#ch-{n}">Appendix {n}</a>' if n in known_ch else m.group(0)

    for i, s in enumerate(parts):
        if not s or s.startswith("<"):
            continue
        s = re.sub(r"\b(chapters) (\d+)(,? and |, | or |-|–)(\d+)\b", chs, s)
        s = re.sub(r"\b([Cc]hapter) (\d+)\b", ch, s)
        s = re.sub(r"(?<![\d.\w])(\d{1,2}\.\d{1,2})(?![\d.]\d)", sec, s)
        s = re.sub(r"\bAppendix ([A-H])\b", app, s)
        parts[i] = s
    return "".join(parts)


CSS = r"""
:root {
  /* Layout: a fixed contents rail on the left, one reading column of about 68 characters, chapters in one scroll. */
  --paper: #f6f8f9; --ink: #172026; --muted: #56656e; --rule: #d5dde1; --panel: #eaf0f2;
  --accent: #0b6f7a; --accent-soft: #d6ecee; --code-bg: #e9eef0; --mark: #fff1b8;
  --f-display: "IBM Plex Sans Condensed", "Arial Narrow", system-ui, sans-serif;
  --f-body: "Source Serif 4", Georgia, "Times New Roman", serif;
  --f-ui: "IBM Plex Sans", system-ui, -apple-system, "Segoe UI", sans-serif;
  --f-mono: "IBM Plex Mono", ui-monospace, "SFMono-Regular", Menlo, monospace;
}
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) {
  --paper: #0f1518; --ink: #dfe7ea; --muted: #93a4ac; --rule: #26343a; --panel: #151e22;
  --accent: #62c6cf; --accent-soft: #163338; --code-bg: #1a2428; --mark: #4a4216; color-scheme: dark; } }
:root[data-theme="dark"] {
  --paper: #0f1518; --ink: #dfe7ea; --muted: #93a4ac; --rule: #26343a; --panel: #151e22;
  --accent: #62c6cf; --accent-soft: #163338; --code-bg: #1a2428; --mark: #4a4216; color-scheme: dark; }
* { box-sizing: border-box; }
html { scroll-padding-top: 16px; }
body { background: var(--paper); color: var(--ink); font: 17px/1.62 var(--f-body); margin: 0; }
a { color: var(--accent); text-underline-offset: 2px; }
a:focus-visible, button:focus-visible, input:focus-visible, pre:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.shell { display: grid; grid-template-columns: 300px minmax(0, 1fr); min-height: 100vh; }
nav.toc { position: sticky; top: env(safe-area-inset-top, 0px); height: 100vh; overflow-y: auto; border-right: 1px solid var(--rule);
  background: var(--panel); padding: 20px 14px 40px max(16px, env(safe-area-inset-left, 0px)); font: 14px/1.4 var(--f-ui); }
.brand { font: 600 20px/1.15 var(--f-display); letter-spacing: .01em; margin: 0 0 4px; }
.brand-sub { color: var(--muted); font-size: 13px; margin: 0 0 14px; }
.filter { width: 100%; padding: 7px 10px; border: 1px solid var(--rule); border-radius: 6px; background: var(--paper); color: var(--ink);
  font: 14px var(--f-ui); margin-bottom: 14px; }
.toc h2 { font: 600 11px/1.3 var(--f-ui); letter-spacing: .08em; text-transform: uppercase; color: var(--muted); margin: 16px 0 6px; }
.toc ol { list-style: none; margin: 0; padding: 0; display: grid; gap: 1px; }
.toc a { display: grid; grid-template-columns: 2.1em 1fr; gap: 4px; padding: 4px 8px; border-radius: 5px; color: var(--ink); text-decoration: none; }
.toc a .n { color: var(--muted); font-variant-numeric: tabular-nums; }
.toc a:hover { background: var(--accent-soft); }
.toc a[aria-current="true"] { background: var(--accent-soft); color: var(--accent); font-weight: 600; }
.toc a[aria-current="true"] .n { color: var(--accent); }
main { min-width: 0; padding-block: 32px 120px; padding-left: max(16px, env(safe-area-inset-left, 0px)); padding-right: max(16px, env(safe-area-inset-right, 0px)); }
.col { max-width: 46rem; margin: 0 auto; }
.cover { padding-block: 24px 28px; border-bottom: 1px solid var(--rule); margin-bottom: 8px; }
.cover .eyebrow { font: 600 12px/1 var(--f-ui); letter-spacing: .1em; text-transform: uppercase; color: var(--accent); margin: 0 0 12px; }
.cover h1 { font: 600 clamp(32px, 5vw, 46px)/1.05 var(--f-display); margin: 0 0 14px; text-wrap: balance; }
.cover p { margin: 0 0 10px; color: var(--muted); max-width: 40rem; }
.readers { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 14px; font: 13px/1.3 var(--f-ui); }
.readers span { border: 1px solid var(--rule); border-radius: 999px; padding: 4px 10px; color: var(--muted); }
.readers b { color: var(--ink); }
.part-head { font: 600 12px/1 var(--f-ui); letter-spacing: .1em; text-transform: uppercase; color: var(--muted); margin: 64px 0 0; padding-top: 18px; border-top: 3px solid var(--ink); }
section.chapter { padding-top: 8px; }
section.chapter > h1 { font: 600 clamp(28px, 4vw, 36px)/1.1 var(--f-display); margin: 14px 0 18px; text-wrap: balance; }
section.chapter > h1 .cn { color: var(--accent); margin-right: .35em; font-variant-numeric: tabular-nums; }
h2 { font: 600 22px/1.25 var(--f-display); margin: 40px 0 10px; text-wrap: balance; }
h2 .num { color: var(--muted); font-weight: 500; margin-right: .3em; font-variant-numeric: tabular-nums; }
h3 { font: 600 17px/1.3 var(--f-ui); margin: 28px 0 6px; }
p, ul, ol { margin: 0 0 14px; }
li { margin: 3px 0; }
li > ul, li > ol { margin: 4px 0 6px; }
strong { font-weight: 650; }
code { font: .86em/1.4 var(--f-mono); background: var(--code-bg); padding: .08em .32em; border-radius: 4px; overflow-wrap: anywhere; }
pre { background: var(--code-bg); border: 1px solid var(--rule); border-radius: 8px; padding: 14px 16px; overflow-x: auto; margin: 0 0 18px; }
pre code { background: none; padding: 0; font-size: 14px; line-height: 1.55; overflow-wrap: normal; }
.tbl { overflow-x: auto; margin: 6px 0 20px; border: 1px solid var(--rule); border-radius: 8px; }
table { border-collapse: collapse; width: 100%; font: 14.5px/1.45 var(--f-ui); }
th, td { text-align: left; vertical-align: top; padding: 8px 12px; border-bottom: 1px solid var(--rule); }
th { background: var(--panel); font-weight: 600; white-space: nowrap; }
tr:last-child td { border-bottom: 0; }
td code { font-size: .9em; }
blockquote { margin: 0 0 16px; padding: 10px 16px; border-left: 3px solid var(--accent); background: var(--accent-soft); border-radius: 0 6px 6px 0; }
blockquote p:last-child { margin: 0; }
figure.pic { margin: 6px 0 20px; padding: 14px 16px; border: 1px dashed var(--rule); border-radius: 8px; display: grid; grid-template-columns: auto 1fr; gap: 12px; align-items: start;
  font: 14px/1.45 var(--f-ui); color: var(--muted); }
.pic-k { font: 600 11px/1.6 var(--f-ui); letter-spacing: .08em; text-transform: uppercase; color: var(--accent); border: 1px solid currentColor; border-radius: 4px; padding: 0 6px; }
figure.pic figcaption { margin: 0; }
mark { background: var(--mark); color: inherit; border-radius: 2px; }
.top { position: fixed; right: max(16px, env(safe-area-inset-right, 0px)); bottom: calc(16px + env(safe-area-inset-bottom, 0px)); font: 13px var(--f-ui);
  background: var(--ink); color: var(--paper); border: 0; border-radius: 999px; padding: 8px 14px; cursor: pointer; text-decoration: none; }
.mbar { display: none; }
@media (max-width: 880px) {
  .shell { display: block; }
  nav.toc { position: fixed; inset: 0 auto 0 0; width: min(320px, 86vw); z-index: 20; transform: translateX(-102%); transition: transform .2s ease; height: 100%;
    padding-top: calc(20px + env(safe-area-inset-top, 0px)); box-shadow: 0 0 40px rgba(0,0,0,.25); }
  nav.toc.open { transform: none; }
  .mbar { display: block; position: sticky; top: env(safe-area-inset-top, 0px); z-index: 10; background: var(--paper); border-bottom: 1px solid var(--rule);
    margin: -32px calc(-1 * max(16px, env(safe-area-inset-right, 0px))) 0 calc(-1 * max(16px, env(safe-area-inset-left, 0px)));
    padding: 8px max(16px, env(safe-area-inset-right, 0px)) 8px max(16px, env(safe-area-inset-left, 0px)); }
  body::before { content: ""; position: fixed; inset: 0 0 auto; height: env(safe-area-inset-top, 0px); z-index: 11; background: var(--paper); }
  .menu-btn { font: 600 13px var(--f-ui); background: var(--ink); color: var(--paper); border: 0; border-radius: 999px; padding: 7px 14px; cursor: pointer; }
  html { scroll-padding-top: 64px; }
  body { font-size: 16.5px; }
}
@media (prefers-reduced-motion: reduce) { nav.toc { transition: none; } html { scroll-behavior: auto; } }
"""

JS = r"""
(function () {
  const nav = document.querySelector('nav.toc');
  const links = [...nav.querySelectorAll('a[href^="#ch-"]')];
  const byId = new Map(links.map((a) => [a.getAttribute('href').slice(1), a]));
  const chapters = [...document.querySelectorAll('section.chapter')];
  const mark = (id) => { links.forEach((a) => a.removeAttribute('aria-current')); const a = byId.get(id); if (a) { a.setAttribute('aria-current', 'true'); } };
  if ('IntersectionObserver' in window) {
    const io = new IntersectionObserver((es) => {
      const vis = es.filter((e) => e.isIntersecting).sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
      if (vis[0]) mark(vis[0].target.id);
    }, { rootMargin: '0px 0px -70% 0px' });
    chapters.forEach((c) => io.observe(c));
  }
  const btn = document.querySelector('.menu-btn');
  btn.addEventListener('click', () => { nav.classList.toggle('open'); btn.setAttribute('aria-expanded', String(nav.classList.contains('open'))); });
  nav.addEventListener('click', (e) => { if (e.target.closest('a')) { nav.classList.remove('open'); btn.setAttribute('aria-expanded', 'false'); } });
  // Filter the contents by chapter title or section title.
  const f = document.getElementById('toc-filter');
  f.addEventListener('input', () => {
    const q = f.value.trim().toLowerCase();
    links.forEach((a) => { a.parentElement.hidden = q && !(a.dataset.search || '').includes(q); });
    nav.querySelectorAll('.toc-part').forEach((p) => { p.hidden = q && !p.querySelector('li:not([hidden])'); });
  });
  if (location.hash) { const t = document.getElementById(location.hash.slice(1)); if (t) t.scrollIntoView(); }
})();
"""


def build(fragment: bool) -> str:
    files = dict(chapter_files())
    parts = read_parts()
    known_ch = set(files)
    rendered: dict[str, tuple[str, str, list]] = {k: render_chapter(k, p) for k, p in files.items()}
    known_sec = {num for _, _, secs in rendered.values() for num, _ in secs}
    placed: set[str] = set()

    nav: list[str] = []
    body: list[str] = []
    for part, keys in parts:
        keys = [k for k in keys if k in rendered]
        if part.startswith("Appendices"):
            keys = [k for k, _ in chapter_files() if k.isalpha()]
        if not keys:
            continue
        label = re.sub(r"^Part ([IVX]+)\.\s*", r"\1 · ", part)
        nav.append(f'<div class="toc-part"><h2>{html.escape(label)}</h2><ol>')
        body.append(f'<div class="part-head">{html.escape(part)}</div>')
        for k in keys:
            title, h, secs = rendered[k]
            placed.add(k)
            search = (title + " " + " ".join(t for _, t in secs)).lower()
            nav.append(f'<li><a href="#ch-{k}" data-search="{html.escape(search, quote=True)}"><span class="n">{k}</span><span>{html.escape(title)}</span></a></li>')
            cn = f"Appendix {k}" if k.isalpha() else f"{k}."
            body.append(f'<section class="chapter" id="ch-{k}"><h1><span class="cn">{cn}</span>{html.escape(title)}</h1>{link_refs(h, known_ch, known_sec)}</section>')
        nav.append("</ol></div>")
    missing = sorted(set(rendered) - placed)
    if missing:
        print(f"warning: chapters not in TOC.md: {missing}", file=sys.stderr)

    words = sum(len(re.findall(r"\w+", p.read_text(encoding="utf-8"))) for p in files.values())
    head = (
        '<title>X-ray Viewer Manual</title>\n'
        '<meta name="claude:viewport-fit-sides" content="cover">\n'
        '<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
        '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans+Condensed:wght@500;600'
        '&family=IBM+Plex+Sans:wght@400;600&family=Source+Serif+4:opsz,wght@8..60,400;8..60,650&display=swap">\n'
        f"<style>{CSS}</style>\n"
    )
    page = (
        '<div class="shell">'
        '<nav class="toc" aria-label="Contents">'
        '<p class="brand">X-ray viewer</p><p class="brand-sub">User manual · 35 chapters, 8 appendices</p>'
        '<input id="toc-filter" class="filter" type="search" placeholder="Filter chapters and sections" aria-label="Filter chapters and sections">'
        + "".join(nav)
        + "</nav>"
        '<main><div class="mbar"><button class="menu-btn" aria-expanded="false" type="button">Contents</button></div><div class="col">'
        '<header class="cover"><p class="eyebrow">User manual</p><h1>Seeing through a building model</h1>'
        "<p>How the X-ray BIM viewer works and how to use it: looking through a model, finding and checking elements, "
        "views and issues, presenting, 4D planning, sharing, and automation. Every chapter starts from a problem, explains "
        "the idea, walks through it on a sample model, then says what happens underneath and where it stops.</p>"
        f"<p>About {round(words, -3):,} words. Two nouns for coordination: a <b>view</b> is a moment you captured, an <b>issue</b> "
        "is a problem someone must act on, and it points at views.</p>"
        '<div class="readers"><span><b>C</b> coordinator, site engineer</span><span><b>P</b> 4D planner</span>'
        "<span><b>D</b> integrator, developer</span><span>untagged: everyone</span></div></header>"
        + "".join(body)
        + '</div></main></div><a class="top" href="#ch-1">Back to start</a>'
        f"<script>{JS}</script>"
    )
    if fragment:
        return head + page
    return f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">{head}</head><body>{page}</body></html>'


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("-o", "--out", default=str(MAN / "xray-manual.html"))
    ap.add_argument("--fragment", action="store_true")
    a = ap.parse_args()
    Path(a.out).write_text(build(a.fragment), encoding="utf-8")
    print(a.out)


if __name__ == "__main__":
    main()
