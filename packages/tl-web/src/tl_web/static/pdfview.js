// The full PDF viewer of /web/p/{project}/files/{file_id}/view (P2-WEB1-T05).
// It reads the data attributes of #pdf-view and draws pages with the vendored pdf.js as they scroll
// into view. No business logic, no framework; the markup never gets script text or style attributes.
import * as pdfjs from "/web/static/vendor/pdfjs/pdf.min.mjs";

const ZOOM_MIN = 0.5;
const ZOOM_MAX = 3;
const ZOOM_STEP = 0.25;
const FAILED = "This PDF could not be shown. Use the download link.";

const view = document.getElementById("pdf-view");
const pages = document.getElementById("pdf-pages");
const indicator = document.getElementById("pdf-page");
const zoomOut = document.getElementById("pdf-zoom-out");
const zoomIn = document.getElementById("pdf-zoom-in");

let doc = null;
let zoom = 1;
let generation = 0;
let observer = null;
let ratios = new Map();
let current = 1;

function showFailure() {
  pages.textContent = FAILED;
}

function updateIndicator() {
  if (doc === null) {
    return;
  }
  indicator.textContent = `page ${current} of ${doc.numPages}`;
  zoomOut.disabled = zoom <= ZOOM_MIN;
  zoomIn.disabled = zoom >= ZOOM_MAX;
}

async function drawPage(canvas, number, gen) {
  if (canvas.dataset.drawn === "1") {
    return;
  }
  canvas.dataset.drawn = "1";
  try {
    const page = await doc.getPage(number);
    if (gen !== generation) {
      return;
    }
    const viewport = page.getViewport({ scale: zoom });
    canvas.width = Math.floor(viewport.width);
    canvas.height = Math.floor(viewport.height);
    await page.render({ canvasContext: canvas.getContext("2d"), viewport }).promise;
  } catch (error) {
    canvas.dataset.drawn = "";
  }
}

function onVisible(entries, gen) {
  for (const entry of entries) {
    const number = Number(entry.target.dataset.page);
    ratios.set(number, entry.intersectionRatio);
    if (entry.isIntersecting) {
      drawPage(entry.target, number, gen);
    }
  }
  // the page most in view names the page in the toolbar
  let best = current;
  let bestRatio = -1;
  for (const [number, ratio] of ratios) {
    if (ratio > bestRatio) {
      best = number;
      bestRatio = ratio;
    }
  }
  current = best;
  updateIndicator();
}

async function layout() {
  generation += 1;
  const gen = generation;
  if (observer !== null) {
    observer.disconnect();
  }
  ratios = new Map();
  pages.replaceChildren();
  const first = await doc.getPage(1);
  const size = first.getViewport({ scale: zoom });
  const canvases = [];
  for (let number = 1; number <= doc.numPages; number += 1) {
    const canvas = document.createElement("canvas");
    canvas.dataset.page = String(number);
    canvas.width = Math.floor(size.width);
    canvas.height = Math.floor(size.height);
    canvas.setAttribute("aria-label", `page ${number} of ${doc.numPages}`);
    pages.appendChild(canvas);
    canvases.push(canvas);
  }
  observer = new IntersectionObserver((entries) => onVisible(entries, gen), {
    root: null,
    rootMargin: "200px 0px",
    threshold: [0, 0.25, 0.5, 0.75, 1],
  });
  for (const canvas of canvases) {
    observer.observe(canvas);
  }
  updateIndicator();
}

function setZoom(next) {
  const clamped = Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, next));
  if (doc === null || clamped === zoom) {
    return;
  }
  zoom = clamped;
  layout().catch(showFailure);
}

async function start() {
  pdfjs.GlobalWorkerOptions.workerSrc = view.dataset.worker;
  try {
    doc = await pdfjs.getDocument({
      url: view.dataset.src,
      isEvalSupported: false,
      enableXfa: false,
      disableRange: true,
      disableStream: true,
    }).promise;
    await layout();
  } catch (error) {
    showFailure();
  }
}

zoomOut.addEventListener("click", () => setZoom(zoom - ZOOM_STEP));
zoomIn.addEventListener("click", () => setZoom(zoom + ZOOM_STEP));
start();
