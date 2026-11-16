# P2-FORMS-WEB W1 — Vendor `survey-core` and `survey-js-ui` (MIT) into the web client

kind: piece
review: full
branch: p2/forms-w1-vendor-surveyjs
worktree: /home/user/wt/forms/w1
Depends on: nothing (FORMS C2 reached: S3, CR1 merged). Independent of every other forms item; it adds files and one test, no route.
Gated: **licence line, the owner approves** (APPROVALS line before merge). Labels: web, licence. Heavy runs: one at a time (the browser probe is a node run, not a gate part).

## Why
ADR-0031 and `forms-eval.md` §2.1, §2.2: the web fill page (W2) renders a form with the plain-JS SurveyJS renderer; the model runs in the browser (store and forward later needs that). Both packages are MIT, prebuilt and have no
runtime dependency, so they are vendored unedited like htmx and pdf.js (`packages/tl-web/src/tl_web/static/vendor/VENDORED.toml`, checked by `just check` through `dev/tools/check_licences.py`). The Creator, PDF and analytics packages are
commercial and are **never** vendored. The templates are written as YAML or JSON by the CLI, the terminal and agent proposals, so no designer is needed.

## Facts confirmed by the supervisor on 2026-11-16 (the builder re-checks each and stops with `122` on a difference)
| Fact | Value |
|---|---|
| Registry data | `survey-core@3.2.5` licence field `MIT`, no dependencies; `survey-js-ui@3.2.5` licence field `MIT`, peer `survey-core 3.2.5` (+ `@types/react`, `@types/react-dom`, typings only; the prebuilt file needs neither) |
| Tarballs | `https://registry.npmjs.org/survey-core/-/survey-core-3.2.5.tgz` sha512 `MjuWYuBe3Q3GOZrlcV7YWzJAWUA+J5JWZM/ry+X4WlZsMWbyHI//Vctj23jtTzf9C0yGuSlRp6P7c2QgHjA0cw==`; `https://registry.npmjs.org/survey-js-ui/-/survey-js-ui-3.2.5.tgz` sha512 `StlxZUgoAvgrwznbY9J413xdz9AT3+TUCX0n39vA+LppnXM6RBIfECQHdEILUem+HyW7spCbG7NEa6Hb/n7B5A==` (tarball sha256 `9b7332f3...7412` and `c18734a8...00c9`) |
| **No LICENSE file in either tarball** | The licence is stated in `package.json` (`"license": "MIT"`), in the banner of every file (`License: MIT (http://www.opensource.org/licenses/mit-license.php)`, `Copyright (c) 2015-2026 Devsoft Baltic OÜ`) and in the README ("distributed under the MIT license", link to the upstream `LICENSE`). The text is therefore taken from upstream: `https://raw.githubusercontent.com/surveyjs/survey-library/v3.2.5/LICENSE` (1102 bytes, "MIT License", `Copyright (c) 2015-2026 Devsoft Baltic OÜ`), sha256 `ef2cef07ff83d3ab514f530d85b8b86eb5979f2897eabb875cb69c2bbd8ee611` (the same bytes at `surveyjs/surveyjs`, the repository named in `package.json`) |
| Files to vendor (sha256) | `package/survey.core.min.js` 1,863,812 bytes `46f07eca3a1f07fbafff2864bfc31cb9ab766e8a25dfc2375dcc02df2dbcd253`; `package/survey-core.min.css` 543,507 bytes `68fa8ad13a6e09935fbb93baee388c4054576a6524419e3e477a3ae671ad8f41` (no `url()`, no font, no data URI); `survey-js-ui` `package/survey-js-ui.min.js` 238,770 bytes `66587c72ecee48222d9fd2ffc02f603dfe0890631e85204c625a50a582df42f5`. Total about 2.65 MB |
| Globals (UMD) | core sets `window.Survey`; the renderer sets `window.SurveyUI` and expects `Survey` loaded first |
| Scan of the two JS files | no `eval(`, no `new Function`; `.innerHTML=` appears (4 and 3 times: they set markup the library built; a template string is never markup, see W2); no `document.write`; `XMLHttpRequest` or `fetch` text is present in core (choice lists by URL; a template has no URL: S1 rules accept only text choices) |
Not vendored, never: `survey.i18n*`, `themes`, `tester`, `collaboration`, `survey-creator-*`, `survey-pdf`, `survey-analytics`, any source map.

## Goal
1. Files under `packages/tl-web/src/tl_web/static/vendor/surveyjs/`: `survey.core.min.js`, `survey-core.min.css`, `survey-js-ui.min.js` (byte-identical to the tarball files) and `LICENSE` (the upstream text, byte-identical to the fetched file).
2. Four `[[file]]` rows in `VENDORED.toml` (paths relative to the manifest: `surveyjs/...`): names `survey-core`, `survey-core-css`, `survey-js-ui`, `surveyjs-licence`; version `3.2.5`; licence `MIT`; url the tarball URL (for the licence row the upstream raw URL); sha256 of each file as vendored.
   The header comment of the manifest gains one line saying the surveyjs rows come from two tarballs and that the licence file is upstream's because the tarballs carry none.
3. A browser proof that W2 reuses: `dev/tools/surveyjs_probe/` (`probe.mjs`, `index.html`, `probe.js`): a node script starting a local server that serves the three vendored files, the page and `probe.js` with exactly the web client's policy
   (`default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; worker-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'`, copied from `tl_web/app.py` `CSP`), launching the system Chrome through
   `playwright` (read how `dev/tour` and the node tooling find them; do not add a dependency), loading the page (no inline script or style), building `new SurveyUI.Survey(json)` from a small format-2-shaped JSON (one text, one choice, one number with
   a `visibleIf`), rendering into a container, answering through the DOM, completing, and printing `PASS survey-render`, `PASS no-csp-violation` (a `securitypolicyviolation` listener and the console saw none), `PASS answer-roundtrip`, `PASS no-network`
   (no request left the local origin). Any failure prints `FAIL <clause>: <text>` and exits 1. Report the output. If the renderer needs `unsafe-inline` or `unsafe-eval` for any clause: **stop with `122`** (the policy is not relaxed in this piece).
4. Tests in `packages/tl-web/tests/test_web_vendored_surveyjs.py`: the four manifest rows exist with the fixed names, version, licence and sha256 and each file hashes to its row; the licence file hashes to the upstream sha256 above and begins `MIT License`;
   the vendor directory holds no file besides those four (nothing commercial or extra rides along); neither JS file contains `eval(` or `new Function`; the CSS has no `url(`, `@import` or `@font-face`; `survey-js-ui.min.js` banner and `survey.core.min.js` banner both say `License: MIT`; `just check`'s licence step
   accepts the manifest; a manifest row with licence `SEE LICENSE IN LICENSE` or `Proprietary` is refused by `vendored_problems` (add to `tests/tools/test_check_licences_vendored.py`: one parametrised test on the existing `tree` fixture; no edit to `check_licences.py`; if it
   would pass such a row, stop with `122`); the files are served under `/web/static/vendor/surveyjs/` with a JavaScript or CSS media type, `nosniff`, and the standard web headers (use the `light_world` style of `test_web_headers.py`), and are reachable with no session as the other static files are.
5. A short README row in `packages/tl-web/README.md` (the `static/vendor/` line names SurveyJS and says unedited and MIT).

## Allowed paths
- `packages/tl-web/src/tl_web/static/vendor/surveyjs/**` (create), `packages/tl-web/src/tl_web/static/vendor/VENDORED.toml` (edit: append rows and one comment line)
- `dev/tools/surveyjs_probe/**` (create)
- `packages/tl-web/tests/test_web_vendored_surveyjs.py` (create), `tests/tools/test_check_licences_vendored.py` (add one test)
- `packages/tl-web/README.md` (one row), `docs/reports/P2-FORMS/W1.md` (create)
Not allowed: any other file, `check_licences.py`, `app.py`, any template, `pyproject.toml`, `uv.lock`, a dependency, `docs/adr/**`. The files are downloaded into a fresh empty directory outside the repository and copied; scripts run from another directory (downloaded content is untrusted).

## Gate
`just check` (it runs the licence check over the new rows); `just gate packages/tl-web/tests/test_web_vendored_surveyjs.py tests/tools/test_check_licences_vendored.py packages/tl-web/tests/test_web_headers.py`; then `node dev/tools/surveyjs_probe/probe.mjs` once.

## Mutation cap
One sentinel (flip one byte of the vendored renderer: the hash test fails) plus at most 3 targeted: a row's licence changed to a commercial statement (refused); an extra file in the vendor directory (the directory test fails); `unsafe-inline` added to the probe's policy
(the probe must not need it: re-run with the strict policy is the proof, so this mutant is "probe passes with a policy missing `style-src 'self'`" and must FAIL). 3 lines in the report.

## Report
Builder return ≤ 15 lines; report ≤ 60 lines; first line deviations or none. Include: the confirmed-facts table with any difference, the probe output, the four sha256 values, total vendored bytes, and **the licence line for the owner**
("survey-core 3.2.5 and survey-js-ui 3.2.5, MIT, Copyright (c) 2015-2026 Devsoft Baltic OÜ; licence text from upstream because the tarballs ship none; commercial Creator, PDF and analytics never vendored"). Commit `P2-FORMS-W1: ...` with the session trailers; no model names in committed text.
