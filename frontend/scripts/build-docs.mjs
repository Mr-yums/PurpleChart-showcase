import {readFile, writeFile} from 'node:fs/promises';
const source = await readFile(new URL('../../docs/ARCHITECTURE.md', import.meta.url), 'utf8');
const escaped = source.replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;');
await writeFile(new URL('../public/architecture.html', import.meta.url), `<!doctype html><html lang="fr"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Architecture — Purple Replay</title><style>body{max-width:1000px;margin:40px auto;padding:0 22px;background:#0c0b12;color:#ece8f3;font:15px/1.65 system-ui}a{color:#cba4ff}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:inherit}</style><a href="/guide.html">← Guide</a><pre>${escaped}</pre></html>\n`);
