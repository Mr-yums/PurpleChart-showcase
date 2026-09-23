import {svelte} from '@sveltejs/vite-plugin-svelte';
import {defineConfig} from 'vite';
import {fileURLToPath} from 'node:url';

const backend = process.env.REPLAY_BACKEND_URL || 'http://127.0.0.1:8948';
const localPath = (relative: string) => fileURLToPath(new URL(relative, import.meta.url));

export default defineConfig({
 plugins: [svelte()],
 resolve: {alias: {
  'lightweight-charts': localPath('./node_modules/lightweight-charts'),
  '$replay': localPath('../replay/frontend/lib'),
  '$replay-ui': localPath('../replay/frontend'),
 }},
 server: {proxy: {
  '/api': {target: backend, changeOrigin: false},
  '/ws': {target: backend.replace(/^http/, 'ws'), ws: true, changeOrigin: false},
 }},
});
