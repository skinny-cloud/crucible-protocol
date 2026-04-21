// render_figures.mjs — export each CRUCIBLE figure as standalone PDF + PNG
//
// Reads: CRUCIBLE Figures.html (Claude Design output, Round 1 HTML/CSS/JSX)
// Writes: render/figure{1..N}.pdf   (vector, paper-ready, arXiv-submittable)
//         render/figure{1..N}.png   (3x DPI raster, preview/Slack/README)
//         render/manifest.json      (dimensions, file sizes, timestamps)
//
// This script IS the reproducibility artifact — committed alongside the
// source HTML, it regenerates every figure deterministically. Gate B
// compliance under arxiv-paper-coach rubric v2.
//
// Usage: node render_figures.mjs

import { chromium } from 'playwright';
import { readFile, writeFile, mkdir, stat } from 'node:fs/promises';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = __dirname;
const SRC = join(ROOT, 'CRUCIBLE Figures.html');
const OUT = join(ROOT, 'render');

async function main() {
  await mkdir(OUT, { recursive: true });
  const html = await readFile(SRC, 'utf8');

  const browser = await chromium.launch();
  const ctx = await browser.newContext({
    viewport: { width: 1400, height: 2400 },
    deviceScaleFactor: 3,
  });
  const page = await ctx.newPage();
  await page.setContent(html, { waitUntil: 'networkidle' });
  await page.evaluate(() => document.fonts.ready);

  // Hide Claude Design's self-annotation sticky notes (Comic Sans font-family
  // signature). Keeps source HTML pristine for reproducibility while producing
  // clean paper-ready figures.
  await page.evaluate(() => {
    document.querySelectorAll('div').forEach(el => {
      const ff = (el.style.fontFamily || '').toLowerCase();
      if (ff.includes('comic sans') || ff.includes('marker felt')) {
        el.style.display = 'none';
      }
    });
  });

  // INTEGRITY FIX (2026-04-20): Figure 4's .cov-composition block contained
  // fabricated file attributions — rvc_pipeline.py (412 LOC), whisper_engine.py
  // (387 LOC), hunyuan_video.py (346 LOC) — verified against Podcast-Pipeline
  // repo on NXTG-AI as NOT real. Actual files: whisper_engine.py = 282 LOC,
  // hunyuan_avatar.py (not _video) = 255 LOC, rvc_pipeline.py does not exist.
  // Numbers inverse-engineered to sum to 1,145 (the real total from paper).
  // Fix: hide the fabricated panel and rewrite the caption to not reference it.
  // Keeps source HTML pristine; correction captured in render step.
  await page.evaluate(() => {
    const comp = document.querySelector('.cov-composition');
    if (comp) comp.style.display = 'none';

    // Update caption to remove the "three excluded files" reference.
    const cov = document.querySelector('.cov');
    if (cov) {
      const caption = cov.closest('.fig')?.querySelector('.fig-caption');
      if (caption) {
        caption.innerHTML =
          '<b>Figure 4.</b> Reported vs. honest coverage for Case Study #2. ' +
          'The 77% figure was the value displayed by the repository\u2019s README ' +
          'badge; the 15% figure is the output of ' +
          '<span class="mono">coverage run</span> after the ' +
          '<span class="mono">[tool.coverage.run] omit</span> list was removed. ' +
          'The 62-percentage-point gap corresponds to 1,145&nbsp;LOC of business ' +
          'logic excluded from measurement, 66 hollow assertions removed on audit, ' +
          'and 5 test files dead-gated by an unset <span class="mono">PYTEST_GPU' +
          '</span> environment variable. Full file-level breakdown appears in ' +
          '\u00A75.2 of the paper.';
      }
    }
  });

  // Extract shared <style> + font links once, reuse for isolated PDFs
  const fontLinks = await page.evaluate(() =>
    Array.from(document.querySelectorAll('link[rel="stylesheet"], link[rel="preconnect"]'))
      .map(l => l.outerHTML)
      .join('\n')
  );
  const styleBlocks = await page.evaluate(() =>
    Array.from(document.querySelectorAll('style'))
      .map(s => s.outerHTML)
      .join('\n')
  );

  const figs = await page.$$('.fig');
  const results = [];

  for (let i = 0; i < figs.length; i++) {
    const fig = figs[i];
    const idx = i + 1;
    const pngPath = join(OUT, `figure${idx}.png`);
    const pdfPath = join(OUT, `figure${idx}.pdf`);

    // PNG at 3x DPI (set via deviceScaleFactor)
    await fig.screenshot({ path: pngPath, omitBackground: false });

    // Per-figure PDF — render in isolated page at exact figure dimensions
    const figHtml = await fig.evaluate(el => el.outerHTML);
    const standalone = `<!doctype html>
<html><head><meta charset="utf-8">${fontLinks}${styleBlocks}
<style>html,body{margin:0;padding:0;background:#fdfdfb;}</style>
</head><body>${figHtml}</body></html>`;

    const pdfPage = await ctx.newPage();
    await pdfPage.setContent(standalone, { waitUntil: 'networkidle' });
    await pdfPage.evaluate(() => document.fonts.ready);
    const dims = await pdfPage.$eval('.fig', el => {
      const r = el.getBoundingClientRect();
      return { width: Math.ceil(r.width), height: Math.ceil(r.height) };
    });

    await pdfPage.pdf({
      path: pdfPath,
      width: `${dims.width}px`,
      height: `${dims.height}px`,
      printBackground: true,
      pageRanges: '1',
      margin: { top: 0, right: 0, bottom: 0, left: 0 },
    });
    await pdfPage.close();

    const pdfStat = await stat(pdfPath);
    const pngStat = await stat(pngPath);
    results.push({
      figure: idx,
      png: `figure${idx}.png`,
      pdf: `figure${idx}.pdf`,
      width_px: dims.width,
      height_px: dims.height,
      png_bytes: pngStat.size,
      pdf_bytes: pdfStat.size,
    });
    console.log(`fig ${idx}: ${dims.width}×${dims.height}px · PDF ${pdfStat.size}B · PNG ${pngStat.size}B`);
  }

  await browser.close();

  const manifest = {
    generated_at: new Date().toISOString(),
    source: 'CRUCIBLE Figures.html',
    renderer: 'playwright/chromium@1.57',
    dpi: 216,
    results,
  };
  await writeFile(join(OUT, 'manifest.json'), JSON.stringify(manifest, null, 2));
  console.log(`\nmanifest → ${join(OUT, 'manifest.json')}`);
}

main().catch(err => { console.error(err); process.exit(1); });
