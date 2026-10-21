import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
export default defineConfig({plugins:[vue()],build:{rollupOptions:{output:{manualChunks(id){if(id.includes('node_modules/element-plus')||id.includes('node_modules/@element-plus'))return 'ui';if(id.includes('node_modules/vue')||id.includes('node_modules/@vue'))return 'vue'}}}},server:{proxy:{'/v1':'http://127.0.0.1:18771','/api':'http://127.0.0.1:18772','/artifacts':'http://127.0.0.1:18771'}}})
