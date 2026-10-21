<script setup lang="ts">
import {computed,onMounted,ref} from 'vue'
const props=defineProps<{kind:string;disabled?:boolean}>()
const emit=defineEmits<{select:[file:File]}>()
const items=ref<any[]>([]),busy=ref(''),error=ref('')
const choices=computed(()=>items.value.filter(item=>item.kind===props.kind))
onMounted(async()=>{try{const r=await fetch('/presets/catalog.json');if(!r.ok)throw Error();items.value=await r.json()}catch{error.value='示例素材暂时无法读取，仍可自行上传。'}})
async function select(item:any){busy.value=item.id;error.value='';try{const r=await fetch(item.url);if(!r.ok)throw Error();emit('select',new File([await r.blob()],item.filename))}catch{error.value='素材读取失败，请重试。'}finally{busy.value=''}}
</script>
<template>
 <section class="preset-picker">
  <h3>{{kind==='ppt'?'从示例课件开始':kind==='audio'?'选择参考声线':'选择教师形象'}}</h3>
  <p>可先查看或下载项目素材，再决定是否用于当前任务。每个任务独立绑定所选素材。</p>
  <div class="preset-grid" :class="kind">
   <article v-for="item in choices" :key="item.id">
    <a v-if="kind==='image'" class="visual-preview" :href="item.url" target="_blank" rel="noreferrer" :aria-label="`在线查看${item.name}`"><img :src="item.url" :alt="item.name"/></a>
    <a v-else-if="kind==='ppt'" class="ppt-preview" :href="item.previewUrl||item.url" target="_blank" rel="noreferrer" :aria-label="`在线预览${item.name}`"><span class="preset-ppt">PPT</span><small>打开 PDF 预览</small></a>
    <div v-if="kind==='image'" class="preview-hint">点击图片放大查看</div>
    <strong>{{item.name}}</strong>
    <audio v-if="kind==='audio'" :src="item.url" controls preload="metadata"/>
    <div class="preset-actions"><a class="asset-link" :href="item.downloadUrl||item.url" download>下载素材</a><button :disabled="disabled||!!busy" @click="select(item)">{{busy===item.id?'读取中…':'使用此素材'}}</button></div>
   </article>
  </div>
  <p v-if="error" role="alert">{{error}}</p>
 </section>
</template>
<style scoped>
.preset-picker{margin:20px 0;padding:20px;border:1px solid #dce8df;border-radius:14px;background:#f7faf8}.preset-picker h3{margin:0 0 8px;color:#254c3b}.preset-picker p{font-size:13px;color:#677c70;line-height:1.7}.preset-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}.preset-grid.image{grid-template-columns:repeat(4,minmax(0,1fr))}.preset-grid article{min-width:0;background:white;border:1px solid #dfe8e2;border-radius:10px;padding:12px;display:flex;flex-direction:column;gap:12px}.preset-grid img{width:100%;height:170px;object-fit:cover;border-radius:7px}.visual-preview,.ppt-preview{display:block;text-decoration:none}.visual-preview:focus,.ppt-preview:focus{outline:2px solid #2f7e5c;outline-offset:2px}.preview-hint{font-size:12px;color:#72867a}.preset-grid audio{width:100%;height:40px}.preset-grid strong{font-size:13px;line-height:1.4}.preset-actions{display:grid;grid-template-columns:1fr 1.2fr;gap:8px;align-items:center}.asset-link{font-size:12px;text-align:center;color:#276447;text-decoration:none;padding:8px;border:1px solid #c8d9ce;border-radius:7px}.preset-grid button{border:1px solid #a9c5b5;border-radius:7px;color:#276447;background:#f0f7f2;padding:9px;cursor:pointer}.preset-grid button:disabled{opacity:.5;cursor:default}.preset-ppt{height:92px;display:grid;place-items:center;background:#fff2e8;color:#bd6333;border-radius:7px;font-weight:700;font-size:25px}.ppt-preview small{display:block;margin-top:6px;text-align:center;color:#64776b;font-size:12px}@media(max-width:700px){.preset-grid,.preset-grid.image{grid-template-columns:repeat(2,minmax(0,1fr))}}
</style>
