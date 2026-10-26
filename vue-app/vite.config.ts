import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import process from 'node:process'
import {fileURLToPath} from 'node:url'
const backend=process.env.SMARTCOURSE_BACKEND_URL||'http://127.0.0.1:18771'
const adapter=process.env.SMARTCOURSE_ADAPTER_URL||'http://127.0.0.1:18772'
export default defineConfig({plugins:[vue()],build:{rollupOptions:{input:{main:fileURLToPath(new URL('./index.html',import.meta.url)),mobile:fileURLToPath(new URL('./mobile.html',import.meta.url))},output:{entryFileNames:'assets/[name].js',chunkFileNames:'assets/[name].js',assetFileNames:'assets/[name][extname]',manualChunks(id){if(id.includes('node_modules/element-plus')||id.includes('node_modules/@element-plus'))return 'ui';if(id.includes('node_modules/vue')||id.includes('node_modules/@vue'))return 'vue'}}}},server:{proxy:{'/v1':backend,'/api':adapter,'/artifacts':backend}}})
