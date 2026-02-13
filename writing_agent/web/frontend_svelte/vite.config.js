import { defineConfig } from 'vite'
import { svelte } from '@sveltejs/vite-plugin-svelte'

export default defineConfig({
  plugins: [svelte({
    compilerOptions: {
      runes: false,
      compatibility: {
        componentApi: 4
      }
    }
  })],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://127.0.0.1:8000'
    }
  },
  build: {
    outDir: '../static/v2_svelte',
    emptyOutDir: true,
    assetsDir: '',
    cssCodeSplit: false,
    minify: 'esbuild',
    rollupOptions: {
      output: {
        entryFileNames: 'main.js',
        chunkFileNames: 'chunk-[name].js',
        assetFileNames: (asset) => {
          if (asset.name && asset.name.endsWith('.css')) return 'style.css'
          return '[name][extname]'
        }
      }
    }
  }
})
