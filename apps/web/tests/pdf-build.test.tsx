import {readFileSync} from 'node:fs';
import {expect,it} from 'vitest';

// The viewer and the worker file must come from the same pdf.js build, and it must be the legacy one: the modern build needs
// Uint8Array.toHex and Map.getOrInsertComputed, so on a browser without them it cannot open a PDF or draws Thai glyphs wrongly.
it('loads pdf.js from the legacy build in the viewer and copies the matching legacy worker',()=>{
 const viewer=readFileSync('components/pdf-preview.tsx','utf8');
 const imports=[...viewer.matchAll(/import\('(pdfjs-dist[^']*)'\)/g)].map(m=>m[1]);
 expect(imports.length).toBeGreaterThan(0);
 for(const path of imports)expect(path).toBe('pdfjs-dist/legacy/build/pdf.mjs');
 expect(readFileSync('scripts/pdf-worker.mjs','utf8')).toContain('node_modules/pdfjs-dist/legacy/build/pdf.worker.min.mjs');
});

it('serves a worker file that is the legacy one',()=>{
 const served=readFileSync('public/pdf.worker.min.mjs');
 const legacy=readFileSync('node_modules/pdfjs-dist/legacy/build/pdf.worker.min.mjs');
 expect(served.equals(legacy)).toBe(true);  // run `node scripts/pdf-worker.mjs` (the prebuild step) after upgrading pdfjs-dist
});
