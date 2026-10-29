<script setup lang="ts">
import {ref,watch} from 'vue'
import {api,post} from './api'
const props=defineProps<{enabled:boolean}>()
const emit=defineEmits<{ready:[value:boolean]}>()
const ready=ref(false),busy=ref(false),message=ref(''),units=ref(0)
const language=ref('zh-CN')
async function refresh(){
 if(!props.enabled){ready.value=false;emit('ready',false);return}
 try{const status=await api<any>('/v1/rag/status');ready.value=status.ready;units.value=status.metadata?.unitCount||0;emit('ready',ready.value)}catch(e){message.value=(e as Error).message}
}
watch(()=>props.enabled,refresh,{immediate:true})
async function upload(event:Event){
 const input=event.target as HTMLInputElement,file=input.files?.[0];if(!file)return
 busy.value=true;message.value=''
 try{
  const contentBase64=await new Promise<string>((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result).split(',')[1]!);reader.onerror=reject;reader.readAsDataURL(file)})
  const asset=await post<any>('/v1/uploads',{filename:file.name,kind:'ppt',contentBase64})
  await post('/v1/rag/ingest',{pptx:asset,pptxSourceId:'user-course-reference',pptxLanguage:language.value})
  await refresh();message.value='参考课件已导入，后续主题课程可以使用这些内容。'
 }catch(e){message.value=(e as Error).message}finally{busy.value=false;input.value=''}
}
</script>
<template>
 <div class="guidance" style="display:block">
  <strong>课程参考课件</strong>
  <p>参考课件选填，每个账户独立保存。导入后，主题生成会检索相关内容；也可直接根据主题生成课程。</p>
  <p v-if="ready">已建立知识库，包含 {{units}} 个内容单元。</p>
  <p v-else-if="!enabled">请先登录，再导入参考课件。</p>
  <label>参考课件语言 <select v-model="language" :disabled="busy"><option value="zh-CN">中文</option><option value="en-US">英语</option><option value="ja-JP">日语</option><option value="ko-KR">韩语</option><option value="de-DE">德语</option><option value="fr-FR">法语</option></select></label><br/>
  <input type="file" accept=".pptx" :disabled="!enabled||busy" aria-label="导入课程参考课件" @change="upload"/>
  <p v-if="busy">正在导入参考材料…</p><p v-if="message">{{message}}</p>
 </div>
</template>
