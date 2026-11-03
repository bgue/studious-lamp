// The web half of the wave-1 preview (dev/tour/wave1.py runs this with Node and Playwright).
//
//     node dev/tour/wave1_web.mjs <config.json>
//
// The config (written by wave1.py) names the server, the plain user, the project, the record
// numbers to open and the output folder. Playwright is a Node package; it is found next to the
// tools in /opt/node-tools, in the global modules, or through PLAYWRIGHT_NODE_PATH. The script
// prints one line per file ("wrote web-02-rfi-log.png") and one per skip ("skipped <name>: why"),
// and exits 1 only when it cannot sign in. It sends the Origin header the way a browser does.

import { createRequire } from "module";
import fs from "fs";

function load() {
  const roots = [process.env.PLAYWRIGHT_NODE_PATH, "/opt/node-tools/", "/opt/node22/lib/node_modules/"];
  for (const root of roots.filter(Boolean)) {
    try {
      return createRequire(root.endsWith("/") ? root : root + "/")("playwright");
    } catch (_) {
      /* try the next */
    }
  }
  return createRequire(import.meta.url)("playwright");
}

const { chromium } = load();
const cfg = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
const base = cfg.base;
const p = cfg.project;
const out = cfg.out;
const DESKTOP = { width: 1440, height: 900 };
const PHONE = { width: 390, height: 844 };
fs.mkdirSync(out, { recursive: true });

const wrote = [];
async function shot(page, name, full = false) {
  await page.waitForTimeout(250);
  await page.screenshot({ path: `${out}/${name}.png`, fullPage: full });
  wrote.push(name);
  console.log(`wrote ${name}.png`);
}
const skip = (name, why) => console.log(`skipped ${name}: ${why}`);

async function open(page, path) {
  const response = await page.goto(base + path, { waitUntil: "load" });
  return response ? response.status() : 0;
}

async function rowOf(page, number) {
  const row = page.locator(`[data-number="${number}"]`).first();
  await row.waitFor({ timeout: 8000 });
  return row;
}

async function recordId(page, logPath, number) {
  await open(page, logPath);
  const row = await rowOf(page, number);
  const href = (await row.getAttribute("data-open")) || "";
  const m = /records\/([^"?]+)/.exec(href);
  return m ? decodeURIComponent(m[1]) : null;
}

const browser = await chromium.launch();
try {
  const context = await browser.newContext({ viewport: DESKTOP });
  const page = await context.newPage();

  // 01 the sign-in page, then the sign-in itself (the browser sends the Origin header)
  await open(page, "/web/sign-in");
  await shot(page, "web-01-sign-in");
  await page.fill("#username", cfg.user);
  await page.fill("#password", cfg.password);
  await Promise.all([page.waitForNavigation({ waitUntil: "load" }), page.click("button[type=submit]")]);
  const cookies = await context.cookies();
  if (!cookies.some((c) => c.name === "tl_session")) {
    console.log("error: the sign-in set no session cookie");
    process.exit(1);
  }

  // 02 the RFI log with a row selected: list and panel
  await open(page, `/web/p/${p}/rfis`);
  const row = await rowOf(page, cfg.rfi);
  await row.click();
  try {
    await page.waitForFunction(
      (n) => (document.querySelector("#log-panel")?.textContent || "").includes(n),
      cfg.rfi,
      { timeout: 8000 },
    );
  } catch (_) {
    skip("web-02-rfi-log", "the panel did not show the RFI");
  }
  await shot(page, "web-02-rfi-log");

  // 03-09 one RFI record, each tab
  const rid = await recordId(page, `/web/p/${p}/rfis`, cfg.rfi);
  const tabs = [
    ["details", "03-rfi-details"],
    ["properties", "04-rfi-properties"],
    ["history", "05-rfi-history"],
    ["links", "06-rfi-links"],
    ["trace", "07-rfi-trace"],
    ["thread", "08-rfi-thread"],
    ["files", "09-rfi-files"],
  ];
  for (const [tab, slug] of tabs) {
    if (!rid) {
      skip(`web-${slug}`, "no record id");
      continue;
    }
    const status = await open(page, `/web/p/${p}/records/${encodeURIComponent(rid)}?tab=${tab}`);
    if (status !== 200) {
      skip(`web-${slug}`, `HTTP ${status}`);
      continue;
    }
    await shot(page, `web-${slug}`, true);
  }

  // 10 the correspondence log
  await open(page, `/web/p/${p}/correspondence`);
  try {
    const letter = await rowOf(page, cfg.letter);
    await letter.click();
    await page.waitForFunction(
      (n) => (document.querySelector("#log-panel")?.textContent || "").includes(n),
      cfg.letter,
      { timeout: 8000 },
    );
  } catch (_) {
    /* the list alone is still worth a picture */
  }
  await shot(page, "web-10-correspondence-log");

  // 11 the document log with the page-1 image, 12 the viewer
  await open(page, `/web/p/${p}/documents`);
  let fileId = null;
  try {
    const doc = await rowOf(page, cfg.document);
    await doc.click();
    await page.waitForSelector('img[alt="Page 1"]', { timeout: 8000 });
    await page.waitForFunction(() => {
      const img = document.querySelector('img[alt="Page 1"]');
      return img && img.complete && img.naturalWidth > 0;
    }, null, { timeout: 8000 });
    const src = await page.locator('img[alt="Page 1"]').first().getAttribute("src");
    const m = /files\/([^/]+)\/page1\.png/.exec(src || "");
    fileId = m ? m[1] : null;
  } catch (_) {
    skip("web-11-document-log", "no page-1 image appeared");
  }
  await shot(page, "web-11-document-log");
  if (fileId) {
    const status = await open(page, `/web/p/${p}/files/${fileId}/view`);
    if (status === 200) {
      try {
        await page.waitForSelector("#pdf-view canvas", { timeout: 10000 });
      } catch (_) {
        /* the shell alone is still shown */
      }
      await page.waitForTimeout(800);
      await shot(page, "web-12-pdf-viewer");
    } else {
      skip("web-12-pdf-viewer", `HTTP ${status}`);
    }
  } else {
    skip("web-12-pdf-viewer", "no file id");
  }

  // 13 a refusal: the answer form of an RFI that is still a draft is not offered
  const draftId = await recordId(page, `/web/p/${p}/rfis`, cfg.draft);
  if (draftId) {
    const row2 = await rowOf(page, cfg.draft);
    await row2.click();
    await page.waitForTimeout(600);
    const url = `/web/p/${p}/records/${encodeURIComponent(draftId)}/do/AnswerTechnical/form`;
    const verdict = await page.evaluate(async (u) => {
      const r = await fetch(u, { headers: { "HX-Request": "true" } });
      const html = await r.text();
      const status = document.querySelector("#log-status");
      const holder = document.createElement("div");
      holder.innerHTML = html;
      const text = (holder.textContent || "").trim();
      if (status) {
        status.textContent = text;
        status.classList.add("tl-error");
      }
      return { code: r.status, text };
    }, url);
    console.log(`refusal answered ${verdict.code}: ${verdict.text}`);
    await shot(page, "web-13-refusal");
  } else {
    skip("web-13-refusal", "no draft RFI");
  }

  // 14 a hidden record answers as one that never existed
  const hidden = await open(page, `/web/p/${p}/rfis/panel/${cfg.restricted}`);
  console.log(`hidden record answered ${hidden}`);
  await shot(page, "web-14-hidden-404");

  // 15 the RFI log at phone width, with the same session
  const phone = await browser.newContext({ viewport: PHONE, storageState: await context.storageState() });
  const small = await phone.newPage();
  await open(small, `/web/p/${p}/rfis`);
  try {
    const r = await rowOf(small, cfg.rfi);
    await r.click();
    await small.waitForTimeout(700);
  } catch (_) {
    /* the list alone */
  }
  await shot(small, "web-15-rfi-log-phone", true);
  await phone.close();
  await context.close();
} finally {
  await browser.close();
}
console.log(`web shots: ${wrote.length}`);
