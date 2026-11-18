// Real-browser proof of the web fill page under the web client's CSP (V3-F3, W2 probe clause).
// Run: node dev/tools/surveyjs_probe/page_probe.mjs ORIGIN SESSION_TOKEN PATH PLAN_JSON [shot.png]
//   ORIGIN        the running web client, e.g. http://127.0.0.1:8765
//   SESSION_TOKEN a signed-in session token (put in the tl_session cookie)
//   PATH          the fill page, e.g. /web/forms/t/<id>?project=P200
//   PLAN_JSON     a JSON list of {id, kind, value}: what to type (value: text, number, or a list
//                 of choices for a multi question), keyed by question id (SurveyJS `data-name`)
// Environment: PAGE_PROBE_CLICK="Open record" clicks that link first (the card's link to the form);
// PAGE_PROBE_DRAFT=1 saves a draft before completing (prints `draft <id>`).
// PAGE_PROBE_TEXT='["a","b"]' each string must show as text in the survey; PAGE_PROBE_NO='["img"]'
// each selector must match nothing inside the survey; PAGE_PROBE_VALUES='{"topic":"x"}' each
// question's first input must hold that value; PAGE_PROBE_NO_SUBMIT=1 stops before completing.
// Prints `ok <step>` lines and a final `result {...}` line (the page's end address and its text),
// exits 1 and prints `FAIL <step>` when a step does not hold. The CSP is the server's own: any
// violation, console error or foreign request fails the run. Needs playwright and a Chromium.
import { createRequire } from "node:module";

const [origin, token, path, planJson, shot] = process.argv.slice(2);
const plan = JSON.parse(planJson);
const { chromium } = createRequire(import.meta.url)("playwright");

const failures = [];
const ok = (what) => console.log(`ok ${what}`);
const fail = (what, why) => {
  failures.push(what);
  console.log(`FAIL ${what}: ${why}`);
};

const browser = await chromium.launch();
try {
  const context = await browser.newContext({ deviceScaleFactor: 1, viewport: { width: 900, height: 900 } });
  await context.addCookies([{ name: "tl_session", value: token, url: origin }]);
  const page = await context.newPage();
  const seen = [];
  const foreign = [];
  page.on("console", (m) => seen.push(m.text()));
  page.on("pageerror", (e) => seen.push(String(e)));
  page.on("request", (r) => {
    if (!r.url().startsWith(origin) && !r.url().startsWith("data:")) foreign.push(r.url());
  });
  await page.addInitScript(() => {
    window.__csp = [];
    document.addEventListener("securitypolicyviolation", (e) => window.__csp.push(e.violatedDirective));
  });
  await page.goto(origin + path);
  if (process.env.PAGE_PROBE_CLICK) {
    try {
      await page.getByRole("link", { name: process.env.PAGE_PROBE_CLICK }).click({ timeout: 5000 });
      await page.waitForURL((u) => u.pathname.startsWith("/web/forms/"), { timeout: 8000 });
      ok(`followed the link to ${new URL(page.url()).pathname}`);
    } catch (e) {
      fail("followed the card link", e.message.split("\n")[0]);
    }
  }
  try {
    await page.waitForSelector("#survey [data-name]", { timeout: 8000 });
    ok("survey rendered");
  } catch (e) {
    fail("survey rendered", e.message.split("\n")[0]);
  }
  const inSurvey = async (what, check) => {
    try {
      await check();
      ok(what);
    } catch (e) {
      fail(what, e.message.split("\n")[0]);
    }
  };
  for (const text of JSON.parse(process.env.PAGE_PROBE_TEXT ?? "[]")) {
    await inSurvey(`shows as text: ${text.slice(0, 30)}`, async () => {
      const shown = await page.locator("#survey").innerText();
      if (!shown.includes(text)) throw new Error("not in the survey text");
    });
  }
  for (const sel of JSON.parse(process.env.PAGE_PROBE_NO ?? "[]")) {
    await inSurvey(`no ${sel} in the survey`, async () => {
      const n = await page.locator(`#survey ${sel}`).count();
      if (n !== 0) throw new Error(`${n} found`);
    });
  }
  for (const [id, want] of Object.entries(JSON.parse(process.env.PAGE_PROBE_VALUES ?? "{}"))) {
    await inSurvey(`${id} holds its saved value`, async () => {
      const got = await page.locator(`#survey [data-name="${id}"] input`).first().inputValue();
      if (got !== want) throw new Error(`holds ${got}`);
    });
  }
  for (const step of plan) {
    const q = page.locator(`#survey [data-name="${step.id}"]`).first();
    try {
      if (step.kind === "text" || step.kind === "number" || step.kind === "date") {
        await q.locator("input").first().fill(String(step.value));
        await q.locator("input").first().blur();
      } else if (step.kind === "yes_no_na" || (step.kind === "choice" && step.radio !== false)) {
        const words = { yes: "Yes", no: "No", na: "Not applicable" };
        await q.getByText(words[step.value] ?? step.value, { exact: true }).first().click();
      } else if (step.kind === "multi") {
        for (const v of step.value) await q.getByText(v, { exact: true }).first().click();
      } else if (step.kind === "choice") {
        await q.locator(".sd-dropdown").first().click();
        await page.getByText(step.value, { exact: true }).last().click();
      }
      ok(`typed ${step.id}`);
    } catch (e) {
      fail(`typed ${step.id}`, e.message.split("\n")[0]);
    }
  }
  if (shot) await page.screenshot({ path: shot });
  let end = null;
  if (process.env.PAGE_PROBE_DRAFT) {
    await inSurvey("draft saved", async () => {
      await page.locator("#save-draft").click();
      await page.waitForFunction(() => document.getElementById("fill-status").textContent.includes("Draft saved"), null, { timeout: 8000 });
      const draft = await page.locator("#draft_id").inputValue();
      if (!draft) throw new Error("no draft id after the save");
      console.log(`draft ${draft}`);
    });
  }
  if (process.env.PAGE_PROBE_NO_SUBMIT) {
    await context.close();
    process.exit(failures.length ? 1 : 0);
  }
  try {
    await page
      .locator("#survey")
      .getByRole("button", { name: "Complete" })
      .or(page.locator("#survey input[value=Complete]"))
      .first()
      .click({ timeout: 5000 });
    await page.waitForURL((u) => !u.pathname.startsWith("/web/forms/t/") && !u.pathname.startsWith("/web/forms/for/") || u.pathname.includes("/done/"), { timeout: 15000 });
    end = new URL(page.url());
    const body = (await page.locator("main").innerText()).replace(/\s+/g, " ").trim();
    ok("submitted");
    console.log(`result ${JSON.stringify({ path: end.pathname + end.search, text: body })}`);
  } catch (e) {
    const status = await page.locator("#fill-status").textContent().catch(() => "");
    fail("submitted", `${e.message.split("\n")[0]} status line: ${status}`);
  }
  const violations = await page.evaluate(() => window.__csp ?? []).catch(() => ["page gone"]);
  const cspConsole = seen.filter((t) => /content security policy|refused to/i.test(t));
  if (violations.length || cspConsole.length) fail("no CSP violation", [...violations, ...cspConsole].join(" | "));
  else ok("no CSP violation");
  const errors = seen.filter((t) => /error/i.test(t) && !/content security/i.test(t));
  if (errors.length) fail("no console error", errors.join(" | "));
  else ok("no console error");
  if (foreign.length) fail("no foreign request", foreign.join(" "));
  else ok("no foreign request");
} finally {
  await browser.close();
}
process.exit(failures.length ? 1 : 0);
