<script setup lang="ts">
import {ref,watch} from 'vue'
import {api} from './api'
const props=defineProps<{taskId:string}>()
const value=ref<any>(),error=ref(''),busy=ref(false)
const names:Record<string,string>={running:'执行中',queued:'等待资源',completed:'已完成',failed:'失败',cancelled:'已取消',waiting_input:'等待素材',waiting_review:'等待讲稿审阅',interrupted:'执行中断'}
async function load(){busy.value=true;error.value='';const id=props.taskId;try{const result=await api<any>('/v1/tasks/'+encodeURIComponent(id)+'/execution-journal');if(id===props.taskId)value.value=result}catch(e){if(id===props.taskId)error.value=(e as Error).message}finally{busy.value=false}}
watch(()=>props.taskId,()=>{value.value=undefined}, {immediate:true})
</script>
<template>
 <details class="execution-journal" @toggle="(event)=>{if((event.target as HTMLDetailsElement).open)load()}">
  <summary>生成记录与使用的教学偏好</summary>
  <p v-if="error" role="alert">{{error}}</p>
  <div v-if="value">
   <p v-if="value.teachingMemory">创建时的教学偏好：版本 {{value.teachingMemory.revision}} · {{value.teachingMemory.enabled?'启用':'停用'}}</p><p v-else>此课程创建时尚未保存教学偏好版本。</p>
   <p v-if="value.journal?.courseMemory?.sourceCourseId">课程记忆：版本 {{value.journal.courseMemory.revision}} · {{value.journal.courseMemory.entries?.length||0}} 条已采纳内容</p><p v-if="value.teachingMemory?.audience">教学对象：{{value.teachingMemory.audience}}</p><p v-if="value.teachingMemory?.style">讲解偏好：{{value.teachingMemory.style}}</p>
   <ul v-if="value.teachingMemory?.glossary?.length"><li v-for="term in value.teachingMemory.glossary" :key="term.language+term.source">{{term.source}} → {{term.target}}（{{term.language}}）</li></ul>
   <p v-if="!value.journal">此课程尚无生成记录。执行新任务后将记录阶段状态；历史任务不补写为已验证。</p>
   <article v-for="run in [...(value.journal?.runs||[])].reverse()" :key="run.number">
    <b>第 {{run.number}} 次执行 · {{names[run.status]||run.status}}</b>
    <p>{{run.startedAt}} · 语言模型 {{run.model}} · 讲稿规则版本 {{run.narrationStyleVersion}}</p>
    <p v-if="run.reusedStages?.length">从 S{{run.startStage}} 继续，沿用前置阶段：{{run.reusedStages.join('、')}}</p>
    <ul><li v-for="(stage,code) in run.stages" :key="code">{{code}} · {{names[stage.status]||stage.status}}<span v-if="stage.engine"> · {{stage.engine}}</span><span v-if="stage.elapsedSeconds!=null"> · 执行 {{stage.elapsedSeconds}} 秒</span><span v-if="stage.queueWaitSeconds!=null"> · 等待 {{stage.queueWaitSeconds}} 秒</span><p v-if="stage.message">{{stage.message}}</p></li></ul>
    <p v-if="run.message">{{run.message}}</p>
   </article>
  </div>
  <button type="button" :disabled="busy" @click="load">{{busy?'正在读取…':'刷新记录'}}</button>
 </details>
</template>
<style scoped>
.execution-journal{margin:20px 0;padding:16px;border:1px solid #dde6df;border-radius:10px;background:#fff;color:#315641;font-size:13px;overflow-wrap:anywhere}.execution-journal summary{cursor:pointer;font-weight:600}.execution-journal p,.execution-journal li{font-size:12px;line-height:1.8;white-space:pre-wrap}.execution-journal article{border-top:1px solid #e6ece7;padding:14px 0}.execution-journal button{padding:8px 12px;border:1px solid #cbdcd0;border-radius:6px;color:#24543d;background:#f3f8f4;cursor:pointer}
</style>
