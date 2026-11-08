// Toolbar icons: 20x20, stroke only, currentColor, 1.6 px round strokes. One style for all tools.

const svg = (body: string): string =>
  `<svg viewBox="0 0 20 20" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${body}</svg>`;

export const ICONS = {
  /** folder with an arrow */
  open: svg('<path d="M2.5 5.5h5l1.5 1.8h8.5v8.2h-15z"/><path d="M10 14.2v-4.4M8.2 11.5 10 9.7l1.8 1.8"/>'),
  /** cube drawn with a dashed hidden edge: x-ray */
  xray: svg('<path d="M3.5 6.5 10 3l6.5 3.5v7L10 17l-6.5-3.5z"/><path d="M3.5 6.5 10 10l6.5-3.5" stroke-dasharray="2 2"/><path d="M10 10v7" stroke-dasharray="2 2"/>'),
  /** two stacked layers with a cut plane */
  viewModes: svg('<path d="M10 3 3 7l7 4 7-4z"/><path d="M3 11l7 4 7-4"/><path d="M3 14.5l7 4 7-4" stroke-dasharray="2 2"/>'),
  /** broom */
  cleanup: svg('<path d="M12.5 2.8 8.7 9.2"/><path d="M7.2 8.8l5.2 3.1-3 5.1H4.4z" transform="translate(0 0)"/><path d="M6.5 13.2l-1.3 2.2M9 14.2l-1 1.9"/>'),
  /** ruler on a diagonal */
  measure: svg('<path d="M3 13.5 13.5 3l3.5 3.5L6.5 17z"/><path d="M6.3 10.2l1.7 1.7M8.8 7.7l1 1M10.8 5.7l1.7 1.7"/>'),
  /** two solids with a gap arrow */
  clearance: svg('<rect x="2.5" y="5" width="4.5" height="10" rx="1"/><rect x="13" y="5" width="4.5" height="10" rx="1"/><path d="M8.5 10h3M9.6 8.6 8.5 10l1.1 1.4M10.4 8.6 11.5 10l-1.1 1.4"/>'),
  /** wall with a round hole and a pipe through it */
  penetrations: svg('<rect x="6" y="2.5" width="6" height="15" rx="0.8"/><circle cx="9" cy="10" r="2.2"/><path d="M2.5 10h4.3M11.2 10h6.3"/>'),
  /** tag with a dot: a label for each element */
  classify: svg('<path d="M3 3.5h6.6l7 7-6.1 6.1-7-7z"/><circle cx="6.6" cy="7.1" r="1.1"/>'),
  /** fallback */
  tool: svg('<circle cx="10" cy="10" r="6"/><path d="M10 7v3.5l2 1.5"/>'),
} as const;
