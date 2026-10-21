<script setup lang="ts">
import {onMounted,ref} from 'vue'
import {post} from './api'

const model=defineModel<string>({default:''})
const busy=ref(false),error=ref(''),filename=ref(''),presets=ref<any[]>([])
onMounted(async()=>{try{const r=await fetch('/presets/catalog.json');if(r.ok)presets.value=(await r.json()).filter((x:any)=>x.kind==='audio')}catch{}})
async function choose(event:Event){const input=event.target as HTMLInputElement,file=input.files?.[0];if(!file)return;error.value='';if(!/\.(wav|mp3|m4a|flac|ogg)$/i.test(file.name)||file.size>20*1024*1024){error.value='请选择不超过 20 MB 的 WAV、MP3、M4A、FLAC 或 OGG 音频。';input.value='';return}await bind(file);input.value=''}
async function bind(file:File){busy.value=true;error.value='';try{const contentBase64=await new Promise<string>((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result).split(',')[1]!);reader.onerror=reject;reader.readAsDataURL(file)});const uploaded=await post<{path:string}>('/v1/uploads',{filename:file.name,kind:'audio',contentBase64});model.value=uploaded.path;filename.value=file.name}catch(e){error.value=(e as Error).message}finally{busy.value=false}}
async function choosePreset(item:any){try{const response=await fetch(item.url);if(!response.ok)throw Error('素材读取失败');await bind(new File([await response.blob()],item.filename))}catch(e){error.value=(e as Error).message}}
</script>
<template>
 <section class="reference-audio">
  <h3>自定义参考声音（可选）</h3><p>上传后优先使用这段声音，仅关联当前任务。</p>
  <div v-if="presets.length" class="preset-audio-grid"><article v-for="item in presets" :key="item.id"><strong>{{item.name}}</strong><audio :src="item.url" controls preload="metadata"/><div><a :href="item.url" download>下载素材</a><el-button link type="primary" :disabled="busy" @click="choosePreset(item)">使用此素材</el-button></div></article></div>
  <input type="file" accept="audio/*" :disabled="busy" @change="choose"/><p v-if="busy">正在上传参考声音…</p>
  <div v-if="model" class="selected-audio"><span>已关联：{{filename||'先前上传的声音'}}</span><el-button link type="danger" @click="model='';filename=''">移除</el-button></div>
  <el-alert v-if="error" :title="error" type="warning" :closable="false"/>
 </section>
</template>
<style scoped>
.reference-audio{margin:20px 0}.reference-audio p{color:#64776b;font-size:13px}.preset-audio-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;margin:12px 0}.preset-audio-grid article{padding:12px;border:1px solid #dfe8e2;border-radius:9px;background:#f7faf8}.preset-audio-grid audio{display:block;width:100%;height:36px;margin:8px 0}.preset-audio-grid a{font-size:12px;color:#276447;margin-right:10px}.selected-audio{display:flex;align-items:center;gap:10px;margin-top:8px}@media(max-width:700px){.preset-audio-grid{grid-template-columns:1fr}}
</style>
