// Throughline web client script: keys and focus only. Every record, panel and action is the
// server's; htmx (configured from the page's <meta name="htmx-config">) does the requests.
// No inline handler, no dynamic code, no direct network call, no markup built from text.
const table = () => document.querySelector("#log-table");
const rows = () => Array.from(document.querySelectorAll("#log-table tbody tr[data-number]"));
const selected = () => rows().find((row) => row.getAttribute("aria-selected") === "true") || null;
const typing = (el) => el instanceof HTMLElement && el.matches("input, textarea, select");

// Select a row: mark it, keep it in the address (a reload comes back to it), fetch its panel.
function select(row, ask) {
  for (const other of rows()) other.setAttribute("aria-selected", other === row ? "true" : "false");
  const url = new URL(window.location.href);
  url.searchParams.set("sel", row.dataset.number);
  window.history.replaceState(null, "", url);
  row.scrollIntoView({ block: "nearest" });
  if (ask) row.click(); // the row's hx-get asks for its panel
}

function move(step) {
  const all = rows();
  if (all.length === 0) return;
  const at = all.indexOf(selected());
  const next = all[Math.min(Math.max(at + step, 0), all.length - 1)];
  if (next !== all[at]) select(next, true);
}

function clearFilter() {
  const box = document.querySelector("#log-filter input[name=q]");
  if (box && box.value !== "") {
    box.value = "";
    box.form.submit();
    return true;
  }
  return false;
}

document.addEventListener("keydown", (event) => {
  if (event.ctrlKey || event.metaKey || event.altKey) return;
  const box = document.querySelector("#log-filter input[name=q]");
  if (event.key === "Escape") {
    if (!clearFilter() && !typing(event.target) && window.history.length > 1) window.history.back();
    else if (document.activeElement instanceof HTMLElement) document.activeElement.blur();
    return;
  }
  if (typing(event.target)) return;
  if (event.key === "ArrowDown" || event.key === "ArrowUp") {
    event.preventDefault();
    move(event.key === "ArrowDown" ? 1 : -1);
  } else if (event.key === "Enter") {
    const row = selected();
    if (row && row.dataset.open && event.target === document.body) window.location.assign(row.dataset.open);
  } else if (event.key === "/" && box) {
    event.preventDefault();
    box.focus();
  } else if (event.key === "F5") {
    event.preventDefault();
    window.location.reload();
  } else if (event.key.length === 1) {
    const button = document.querySelector(`#log-actions button[data-key="${CSS.escape(event.key)}"]`);
    if (button) {
      event.preventDefault();
      button.click();
    }
  }
});

document.addEventListener("click", (event) => {
  const row = event.target instanceof Element ? event.target.closest("#log-table tbody tr[data-number]") : null;
  if (row && table()) select(row, false); // the click itself fires the row's panel request
});

document.addEventListener("dblclick", (event) => {
  const row = event.target instanceof Element ? event.target.closest("#log-table tbody tr[data-number]") : null;
  if (row && row.dataset.open) window.location.assign(row.dataset.open);
});

// An answer for a row that is no longer selected is dropped. A refusal (4xx/5xx) the server sent
// for the status line (HX-Retarget) is swapped; any other error page is not, and says so in words.
document.body.addEventListener("htmx:beforeSwap", (event) => {
  const detail = event.detail;
  const from = detail.requestConfig && detail.requestConfig.elt;
  if (from instanceof Element && from.matches("tr[data-number]") && from.getAttribute("aria-selected") !== "true") {
    detail.shouldSwap = false;
    return;
  }
  if (detail.xhr.status < 400) return;
  if (detail.xhr.getResponseHeader("HX-Retarget")) {
    detail.shouldSwap = true;
    detail.isError = false;
  } else {
    const status = document.querySelector("#log-status");
    if (status) status.textContent = detail.xhr.status === 404 ? "! Not found" : "! The request failed";
  }
});

// Every htmx request carries the CSRF token of the session (the server checks it on unsafe methods).
document.body.addEventListener("htmx:configRequest", (event) => {
  const meta = document.querySelector('meta[name="csrf-token"]');
  if (meta instanceof HTMLMetaElement) event.detail.headers["X-CSRF-Token"] = meta.content;
});
