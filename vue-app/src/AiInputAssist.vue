<script setup lang="ts">
import {computed,ref} from 'vue'
import {api} from './api'
import {useInputContext} from './inputAssistance'
const props=defineProps<{modelValue?:string;label?:string;purpose?:string;courseId?:string;page?:number;language?:string;context?:Record<string,unknown>;maxLength?:number;disabled?:boolean}>()
const emit=defineEmits<{'update:modelValue':[value:string]}>()
const inherited=useInputContext(),open=ref(false),busy=ref(false),instruction=ref(''),error=ref(''),notice=ref(''),result=ref<any>(),history=ref<any[]>([])
const languages:Record<string,string>={'zh-CN':'中文','en-US':'英语','ja-JP':'日语','ko-KR':'韩语','de-DE':'德语','fr-FR':'法语','ru-RU':'俄语','es-ES':'西班牙语'}
const outputLanguage=ref('zh-CN')
const label=computed(()=>props.label||'输入内容')
const course=computed(()=>props.courseId||inherited.value.courseId)
const limit=computed(()=>Math.min(30000,props.maxLength||4000))
const unchanged=computed(()=>!result.value||String(props.modelValue||'')===result.value.original)
async function show(){const value=props.language||inherited.value.language||'zh-CN';outputLanguage.value=languages[value]?value:Object.keys(languages).find(k=>languages[k]===value)||'zh-CN';open.value=true;error.value='';notice.value='';try{const query=new URLSearchParams({label:label.value});if(course.value)query.set('courseId',course.value);history.value=await api<any[]>('/v1/studio/assist-input?'+query)}catch(e){error.value=(e as Error).message}}
async function generate(requirement?:string){
 if(busy.value)return
 if(requirement)instruction.value=requirement
 busy.value=true;error.value='';notice.value='';result.value=undefined
 try{result.value=await api<any>('/v1/studio/assist-input',{method:'POST',body:JSON.stringify({purpose:props.purpose||'writing',label:label.value,text:props.modelValue||'',instruction:instruction.value,maxLength:limit.value,courseId:course.value,page:props.page??inherited.value.page,language:outputLanguage.value,context:{...inherited.value.context,...props.context}}),signal:AbortSignal.timeout(600000)});history.value=[result.value,...history.value].slice(0,20)}catch(e){error.value=(e as Error).message}finally{busy.value=false}
}
async function accept(index:number,mode='replace'){
 if(!unchanged.value){error.value='当前输入已修改，请根据最新内容重新生成建议。';return}
 const proposed=result.value.suggestions[index].text
 const value=mode==='append'?[props.modelValue,proposed].filter(Boolean).join('\n'):proposed
 if(value.length>limit.value){error.value='合并后的内容超过此输入项的长度限制，请选择替换或缩短建议。';return}
 busy.value=true;error.value=''
 try{await api('/v1/studio/assist-input/'+encodeURIComponent(result.value.id)+'/accept',{method:'POST',body:JSON.stringify({index,mode})});emit('update:modelValue',value);notice.value='已填入当前草稿，请继续检查并保存。';open.value=false}catch(e){error.value=(e as Error).message}finally{busy.value=false}
}
</script>
<template>
 <span class="ai-input-tools"><button type="button" class="ai-input-trigger" :disabled="disabled" @click.stop.prevent="show">AI 填写建议</button><small v-if="notice" role="status">{{notice}}</small></span>
 <el-dialog v-model="open" :title="label+' · AI 填写建议'" width="min(760px,94vw)" append-to-body :close-on-click-modal="!busy">
  <div class="ai-input-dialog" :aria-busy="busy">
   <p>根据已填内容和当前课程提出建议。采纳后填入草稿，由你保存；不会直接提交表单或修改已发布课程。</p>
   <label>当前内容<textarea :value="modelValue||''" readonly rows="3"/></label>
   <label>建议内容语种<select v-model="outputLanguage"><option v-for="(name,code) in languages" :key="code" :value="code">{{name}}</option></select></label>
   <label>希望如何填写或修改<textarea v-model="instruction" rows="3" maxlength="1200" placeholder="可以简单写：面向零基础学生、补充例子、保持专业术语、缩短表达……"/></label>
   <div class="ai-quick-actions"><button type="button" :disabled="busy" @click="generate('根据当前材料整理成清楚、完整的表达，保留事实和要求。')">整理表达</button><button type="button" :disabled="busy" @click="generate('在现有材料范围内写得更具体；缺少信息时说明需要补充什么。')">完善内容</button><button type="button" :disabled="busy" @click="generate('保留核心信息，使用更简洁的表达。')">更简洁</button><button type="button" :disabled="busy" @click="generate()">{{busy?'正在生成建议…':'按要求生成建议'}}</button></div>
   <p v-if="error" class="ai-error" role="alert">{{error}}</p>
   <template v-if="result"><p>{{result.summary}}</p><p v-if="!unchanged" class="ai-error">输入内容已经变化，重新生成后可采纳。</p><ul v-if="result.questions?.length"><li v-for="item in result.questions" :key="item">{{item}}</li></ul><article v-for="(item,index) in result.suggestions" :key="index"><h4>建议 {{Number(index)+1}}</h4><p>{{item.reason}}</p><pre>{{item.text}}</pre><div class="ai-quick-actions"><button type="button" :disabled="busy||!unchanged" @click="accept(Number(index))">替换当前内容</button><button type="button" :disabled="busy||!unchanged" @click="accept(Number(index),'append')">追加到当前内容</button></div></article></template>
   <details v-if="history.length"><summary>我的近期建议（{{history.length}}）</summary><button v-for="row in history" :key="row.id" type="button" class="ai-history" @click="result=row">{{new Date(row.createdAt).toLocaleString()}} · {{row.summary}}</button></details>
  </div>
 </el-dialog>
</template>
<style scoped>
.ai-input-tools{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-top:5px}.ai-input-trigger{font:inherit;font-size:12px;color:#286449;border:1px solid #bed7c7;border-radius:6px;background:#f0f7f2;padding:5px 9px;cursor:pointer}.ai-input-trigger:disabled{opacity:.5;cursor:default}.ai-input-tools small{font-size:12px;color:#47715b}.ai-input-dialog{color:#264c38;line-height:1.7}.ai-input-dialog label{display:block;margin:12px 0;font-size:13px}.ai-input-dialog textarea{display:block;box-sizing:border-box;width:100%;font:inherit;font-size:15px;padding:10px;border:1px solid #c5d7cb;border-radius:7px;resize:vertical;margin-top:6px}.ai-input-dialog p{font-size:13px;white-space:pre-wrap}.ai-quick-actions{display:flex;gap:8px;flex-wrap:wrap}.ai-input-dialog button{font:inherit;font-size:13px;padding:8px 12px;border:1px solid #bfd5c7;border-radius:6px;background:#f0f6f2;color:#285c42;cursor:pointer}.ai-input-dialog button:disabled{opacity:.5}.ai-input-dialog article{border:1px solid #d9e6dd;background:#fafcfb;padding:14px;margin:14px 0;border-radius:9px}.ai-input-dialog pre{white-space:pre-wrap;overflow-wrap:anywhere;max-height:300px;overflow:auto;font:inherit;font-size:14px;background:white;padding:12px;border-radius:6px}.ai-input-dialog .ai-error{color:#a43e32}.ai-input-dialog details{margin-top:18px}.ai-input-dialog .ai-history{display:block;width:100%;text-align:left;margin:6px 0;overflow-wrap:anywhere}
</style>
