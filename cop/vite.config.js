import { defineConfig, loadEnv } from 'vite';
import cesium from 'vite-plugin-cesium';
import path from 'path';
import { readFileSync, existsSync } from 'fs';

// Load CESIUM_ION_TOKEN from parent .env and expose as VITE_CESIUM_ION_TOKEN
function loadParentEnv() {
  const parentEnv = path.resolve(__dirname, '../.env');
  if (!existsSync(parentEnv)) return {};
  const lines = readFileSync(parentEnv, 'utf8').split('\n');
  const vars = {};
  for (const line of lines) {
    const match = line.match(/^CESIUM_ION_TOKEN=(.+)$/);
    if (match) vars.VITE_CESIUM_ION_TOKEN = match[1].trim();
  }
  return vars;
}

export default defineConfig({
  plugins: [cesium()],
  define: {
    // Only set if not already provided via env/CLI
    ...(!process.env.VITE_CESIUM_ION_TOKEN ? Object.fromEntries(
      Object.entries(loadParentEnv()).map(([k, v]) => [`import.meta.env.${k}`, JSON.stringify(v)])
    ) : {}),
  },
  server: {
    port: 3000,
    host: '0.0.0.0',
    fs: {
      allow: ['.', '../geodata']
    }
  },
  resolve: {
    alias: {
      '/geodata': path.resolve(__dirname, '../geodata')
    }
  },
  build: {
    outDir: 'dist',
    sourcemap: true
  }
});
