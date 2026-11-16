// Real-browser proof that the vendored SurveyJS renderer runs under the web client's CSP.
// Run: node dev/tools/surveyjs_probe/probe.mjs   (needs playwright and a Chromium, as dev tooling has)
import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const vendor = path.resolve(here, "../../../packages/tl-web/src/tl_web/static/vendor/surveyjs");
const CSP =
  "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; " +
  "worker-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; " +
  "form-action 'self'";
const policy = process.env.PROBE_CSP ?? CSP; // only the mutation check overrides this
const files = {
  "/": [path.join(here, "index.html"), "text/html; charset=utf-8"],
  "/probe.js": [path.join(here, "probe.js"), "text/javascript"],
  "/web/static/vendor/surveyjs/survey.core.min.js": [path.join(vendor, "survey.core.min.js"), "text/javascript"],
  "/web/static/vendor/surveyjs/survey-js-ui.min.js": [path.join(vendor, "survey-js-ui.min.js"), "text/javascript"],
  "/web/static/vendor/surveyjs/survey-core.min.css": [path.join(vendor, "survey-core.min.css"), "text/css"],
};
const server = http.createServer((req, res) => {
  const hit = files[(req.url ?? "").split("?")[0]];
  if (!hit) {
    res.writeHead(404).end();
    return;
  }
  res.writeHead(200, {
    "content-type": hit[1],
    "content-security-policy": policy,
    "x-content-type-options": "nosniff",
  });
  res.end(fs.readFileSync(hit[0]));
});

const failures = [];
const pass = (clause) => console.log(`PASS ${clause}`);
const fail = (clause, text) => {
  failures.push(clause);
  console.log(`FAIL ${clause}: ${text}`);
};

const { chromium } = createRequire(import.meta.url)("playwright");
await new Promise((ok) => server.listen(0, "127.0.0.1", ok));
const origin = `http://127.0.0.1:${server.address().port}`;
const browser = await chromium.launch();
try {
  const page = await browser.newPage();
  const consoleSeen = [];
  const foreign = [];
  page.on("console", (m) => consoleSeen.push(m.text()));
  page.on("pageerror", (e) => consoleSeen.push(String(e)));
  page.on("request", (r) => {
    if (!r.url().startsWith(origin) && !r.url().startsWith("data:")) foreign.push(r.url());
  });
  await page.goto(origin + "/");
  try {
    await page.waitForSelector("#host input[type=text], #host input[type=number]", { timeout: 5000 });
    const titles = await page.locator("#host").innerText();
    if (!titles.includes("Site") || !titles.includes("All clear?")) throw new Error(`titles missing: ${titles}`);
    if ((await page.locator("#host input[type=number]").count()) !== 0) throw new Error("visibleIf field shown early");
    pass("survey-render");
  } catch (e) {
    fail("survey-render", e.message.split("\n")[0]);
  }
  try {
    await page.locator("#host input[type=text]").first().fill("North yard");
    await page.locator("#host").getByText("no", { exact: true }).click();
    await page.waitForSelector("#host input[type=number]", { timeout: 3000 });
    await page.locator("#host input[type=number]").fill("7");
    await page.locator("#host input[type=text]").first().blur();
    await page.locator("#host").getByRole("button", { name: "Complete" }).or(page.locator("#host input[value=Complete]")).first().click({ timeout: 3000 });
    await page.waitForFunction(() => window.probe.completed !== null, null, { timeout: 3000 });
    const data = await page.evaluate(() => window.probe.completed);
    if (data.site !== "North yard" || data.ok !== "no" || Number(data.count) !== 7)
      throw new Error(`unexpected data ${JSON.stringify(data)}`);
    pass("answer-roundtrip");
  } catch (e) {
    fail("answer-roundtrip", e.message.split("\n")[0]);
  }
  const violations = await page.evaluate(() => (window.probe ? window.probe.violations : ["probe.js did not run"]));
  const cspConsole = consoleSeen.filter((t) => /content security policy|refused to/i.test(t));
  if (violations.length || cspConsole.length) fail("no-csp-violation", [...violations, ...cspConsole].join(" | "));
  else pass("no-csp-violation");
  if (foreign.length) fail("no-network", foreign.join(" "));
  else pass("no-network");
} finally {
  await browser.close();
  server.close();
}
process.exit(failures.length ? 1 : 0);
