<script setup lang="ts">
import {provideInputContext} from './inputAssistance'
import {onMounted,ref} from 'vue'
import {api,post} from './api'
type Term={source:string;target:string;language:string}
type Memory={enabled:boolean;audience:string;style:string;glossary:Term[];revision:number}
const memory=ref<Memory>({enabled:true,audience:'',style:'',glossary:[],revision:0})
const languages:Record<string,string>={'zh-CN':'中文','en-US':'英语','ja-JP':'日语','ko-KR':'韩语','de-DE':'德语','fr-FR':'法语','ru-RU':'俄语','es-ES':'西班牙语'}
const busy=ref(false),ready=ref(false),error=ref(''),message=ref('')
async function load(){error.value='';try{memory.value=await api<Memory>('/v1/settings/teaching-memory');ready.value=true}catch(e){error.value=(e as Error).message}}
onMounted(load)
async function save(clear=false){busy.value=true;error.value='';message.value='';try{const value=clear?{enabled:false,audience:'',style:'',glossary:[],revision:memory.value.revision}:memory.value;memory.value=await post<Memory>('/v1/settings/teaching-memory',value);message.value=clear?'教学偏好与术语已清空。':'已保存，对之后新建的课程生效。'}catch(e){error.value=(e as Error).message}finally{busy.value=false}}
provideInputContext(()=>({language:'zh-CN',context:{audience:memory.value.audience,style:memory.value.style,glossary:memory.value.glossary}}))
</script>
<template>
 <section class="teaching-memory">
  <h3>教学偏好与术语</h3>
  <p>保存常用教学对象、讲解风格与术语译法。新课程会使用当前版本；已有课程继续使用创建时的版本。内容仅用于当前账号，评分反馈不会自动写入。</p>
  <p v-if="error" class="error" role="alert">{{error}} <button type="button" @click="load">重新读取</button></p>
  <form v-if="ready" @submit.prevent="save()">
   <fieldset :disabled="busy">
    <label class="toggle"><input v-model="memory.enabled" type="checkbox">新课程使用我的教学偏好</label>
    <label>常用教学对象<AssistedInput v-model="memory.audience" maxlength="300" placeholder="例如：没有编程基础的本科生" assist-label="常用教学对象" assist-purpose="audience"/></label>
    <label>讲解偏好<AssistedTextarea v-model="memory.style" rows="3" maxlength="1500" placeholder="例如：先解释术语再举例，使用简短句子，直接向学生讲授知识。" assist-label="讲解偏好" assist-purpose="memory"/></label>
    <div class="terms-head"><b>术语译法</b><button type="button" :disabled="memory.glossary.length>=40" @click="memory.glossary.push({source:'',target:'',language:'en-US'})">添加术语</button></div>
    <div v-for="(term,index) in memory.glossary" :key="index" class="term">
     <AssistedInput v-model="term.source" required maxlength="160" aria-label="术语原文" placeholder="术语原文" assist-label="术语原文" assist-purpose="memory" :assist-language="term.language" :assist-context="{term:term.source}"/>
     <select v-model="term.language" aria-label="目标语种"><option v-for="(name,code) in languages" :key="code" :value="code">{{name}}</option></select>
     <AssistedInput v-model="term.target" required maxlength="160" aria-label="指定译法" placeholder="指定译法" assist-label="术语指定译法" assist-purpose="memory" :assist-language="term.language" :assist-context="{term:term.source}"/>
     <button type="button" @click="memory.glossary.splice(index,1)">移除</button>
    </div>
    <p>课程本次填写的要求、原始内容和目标语种优先；术语仅用于对应目标语种。</p>
    <div class="actions"><button type="submit">保存教学偏好</button><button type="button" @click="save(true)">清空并停用</button><small>版本 {{memory.revision}}</small></div>
   </fieldset>
  </form>
  <p v-if="message" role="status">{{message}}</p>
 </section>
</template>
<style scoped>
.teaching-memory{margin:24px 0;color:#315641}.teaching-memory h3{font-size:16px}.teaching-memory p{font-size:13px;line-height:1.8;color:#687d70}.teaching-memory fieldset{border:0;padding:0;margin:0;min-width:0}.teaching-memory label{display:block;font-size:13px;margin:16px 0}.teaching-memory input:not([type=checkbox]),.teaching-memory textarea,.teaching-memory select{display:block;box-sizing:border-box;width:100%;border:1px solid #dce5de;border-radius:6px;padding:10px;margin-top:7px;font:inherit;font-size:16px;background:white;color:#315641}.teaching-memory .toggle{display:flex;align-items:center;gap:8px}.terms-head,.actions{display:flex;align-items:center;gap:12px;flex-wrap:wrap}.terms-head{justify-content:space-between;font-size:13px}.term{display:grid;grid-template-columns:1fr 110px 1fr auto;gap:8px;align-items:center;margin:8px 0}.teaching-memory button{border:1px solid #cbdcd0;border-radius:6px;background:#f3f8f4;color:#24543d;padding:9px 12px;font:inherit;font-size:12px;cursor:pointer}.actions button:first-child{background:#24543d;color:white}.actions small{font-size:12px}.teaching-memory .error{color:#9b453b}@media(max-width:650px){.term{grid-template-columns:1fr 100px}.term button{justify-self:end}.teaching-memory p{font-size:12px}}
</style>
