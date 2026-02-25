import { defineConfig } from 'vite';
import cesium from 'vite-plugin-cesium';
import path from 'path';

export default defineConfig({
  plugins: [cesium()],
  server: {
    port: 3000,
    host: '0.0.0.0',
    proxy: {
      '/geodata': {
        target: 'http://localhost:3000',
        rewrite: (p) => p
      }
    },
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
