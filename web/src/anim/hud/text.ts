// Text helpers of the HUD: word wrap and ellipsis against a measure function (ctx.measureText in the layer, a fake in tests). Pure.

export type Measure = (text: string) => number;

/** Break `text` into lines no wider than `maxW`. Words that are wider than a line are cut by characters. Newlines break lines. */
export function wrapText(measure: Measure, text: string, maxW: number): string[] {
  const lines: string[] = [];
  for (const para of text.split(/\r?\n/)) {
    const words = para.split(/\s+/).filter(Boolean);
    if (words.length === 0) {
      if (para === '' && text.includes('\n')) lines.push('');
      continue;
    }
    let cur = '';
    for (const word of words) {
      const next = cur ? `${cur} ${word}` : word;
      if (measure(next) <= maxW) {
        cur = next;
        continue;
      }
      if (cur) lines.push(cur);
      let w = word;
      while (measure(w) > maxW && w.length > 1) {
        let n = w.length - 1;
        while (n > 1 && measure(w.slice(0, n)) > maxW) n--;
        lines.push(w.slice(0, n));
        w = w.slice(n);
      }
      cur = w;
    }
    if (cur) lines.push(cur);
  }
  return lines;
}

/** `text` cut with an ellipsis to fit `maxW`. */
export function fitText(measure: Measure, text: string, maxW: number): string {
  if (measure(text) <= maxW) return text;
  let n = text.length;
  while (n > 1 && measure(text.slice(0, n) + '…') > maxW) n--;
  return text.slice(0, n).trimEnd() + '…';
}
