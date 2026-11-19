// The legacy build brings its own fallbacks for browsers that lack newer JavaScript features (Uint8Array.toHex, Map.getOrInsertComputed). The modern build fails to open or draw PDFs there.
// Keep this file and the import in components/pdf-preview.tsx on the same build.
import {copyFileSync,mkdirSync} from 'node:fs';
mkdirSync('public',{recursive:true});
copyFileSync('node_modules/pdfjs-dist/legacy/build/pdf.worker.min.mjs','public/pdf.worker.min.mjs');
