<script setup lang="ts">
import {provideInputContext} from './inputAssistance'
import {ref, watch, onUnmounted} from 'vue'
import {api} from './api'
import {PlaybackInterruption} from './playbackInterruption'
const props=defineProps<{courseId:string;language:string;media?:HTMLVideoElement;timeline:any;source:string}>()
const question=ref(''),record=ref<any>(null),error=ref(''),submitting=ref(false)
const childProgress=ref<any>(null)
const answerMedia=ref<HTMLVideoElement>()
async function playAnswer(){
 try{await answerMedia.value?.play();error.value=''}catch{error.value='回答视频暂时无法播放，请稍后重试。'}
}
const stageNames:Record<string,string>={preparing:'生成回答课件',translating:'翻译回答课件',synthesizing_speech:'生成回答语音',generating_avatar:'生成回答人物视频',composing:'合成回答课程',completed:'已完成'}
let playback:PlaybackInterruption|null=null
let timer:ReturnType<typeof setTimeout>|undefined
let generation=0
const sourceKey=()=>`${props.courseId}:${props.language}:${props.source}`
const storageKey=()=>`mooc-interruption:${sourceKey()}`
function saveSession(value:any){try{sessionStorage.setItem(storageKey(),JSON.stringify({statusUrl:value.statusUrl,position:playback?.position}))}catch{/* Storage may be disabled. */}}
function clear(){generation++;if(timer)clearTimeout(timer);playback?.discard();playback=null;record.value=null;childProgress.value=null;submitting.value=false}
watch(()=>[props.courseId,props.language,props.source],clear)
watch(()=>[props.media,props.courseId,props.language,props.source],()=>{
 if(!props.media||playback)return
 try{
  const saved=JSON.parse(sessionStorage.getItem(storageKey())||'null')
  const prefix=`/api/courses/${encodeURIComponent(props.courseId)}/interruptions/`
  if(!saved||typeof saved.statusUrl!=='string'||!saved.statusUrl.startsWith(prefix))return
  playback=new PlaybackInterruption(props.media,sourceKey)
  playback.restore(saved.position)
  record.value={status:'running',stage:'answering'}
  void poll(saved.statusUrl,++generation)
 }catch{playback=null;error.value='保存的提问记录暂时无法恢复。'}
},{immediate:true})
onUnmounted(clear)
async function poll(url:string,epoch:number){
 try{
  const value=await api<any>(url)
  if(epoch!==generation)return
  record.value=value
  if(typeof value.question==='string')question.value=value.question
  if(value.generationTaskId&&value.status==='running'){
   const child=await api<any>(`/api/courses/${encodeURIComponent(value.generationTaskId)}`)
   if(epoch!==generation)return
   childProgress.value=child
  }
  if(value.status==='queued'||value.status==='running')timer=setTimeout(()=>poll(url,epoch),2500)
 }catch(e){if(epoch===generation){error.value=(e as Error).message;timer=setTimeout(()=>poll(url,epoch),5000)}}
}
async function submit(){
 if(!props.media||!question.value.trim()||submitting.value||playback?.position)return
 error.value=''
 const position=props.media.currentTime
 const current=props.timeline?.pages?.find((p:any)=>position>=Number(p.start_time??p.start)&&position<=Number(p.end_time??p.end))
 if(!current){error.value='当前页面时间轴尚未加载，请稍后重试。';return}
 playback=new PlaybackInterruption(props.media,sourceKey)
 const saved=playback.begin(current.page_id)
 const epoch=++generation
 submitting.value=true
 try{
  const value=await api<any>(`/api/courses/${encodeURIComponent(props.courseId)}/interruptions`,{method:'POST',body:JSON.stringify({question:question.value,currentPage:saved.currentPage,currentTime:saved.currentTime,targetLanguage:props.language})})
  if(epoch!==generation)return
  record.value=value
  saveSession(value)
  void poll(value.statusUrl,epoch)
 }catch(e){if(epoch===generation)error.value=(e as Error).message}
 finally{if(epoch===generation)submitting.value=false}
}
async function resume(){
 try{await playback?.resume();try{sessionStorage.removeItem(storageKey())}catch{}clear();error.value=''}catch{error.value='浏览器未允许自动播放，请点击原课程的播放按钮。'}
}
async function retryAnswer(){
 if(!record.value?.id||submitting.value)return
 submitting.value=true;error.value=''
 const epoch=++generation
 if(timer)clearTimeout(timer)
 try{
  const value=await api<any>(`/api/courses/${encodeURIComponent(props.courseId)}/interruptions/${encodeURIComponent(record.value.id)}/retry`,{method:'POST',body:'{}'})
  if(epoch!==generation)return
  record.value=value;saveSession(value);void poll(value.statusUrl,epoch)
 }catch(e){if(epoch===generation)error.value=(e as Error).message}
 finally{if(epoch===generation)submitting.value=false}
}
provideInputContext(()=>({courseId:props.courseId,language:props.language,context:{question:question.value,playbackSeconds:props.media?.currentTime}}))
</script>
<template>
 <section class="course-question">
  <h3>课程提问</h3>
  <AssistedTextarea v-model="question" type="textarea" :rows="3" maxlength="4000" show-word-limit placeholder="输入当前课程的问题，提交后课程将暂停。" :disabled="!!record||submitting" assist-label="课程学习提问" assist-purpose="question"/>
  <div class="question-actions"><el-button type="primary" :loading="submitting" :disabled="!question.trim()||!!record" @click="submit">暂停并提问</el-button><el-button v-if="record||error" @click="resume">返回原课程</el-button></div>
  <el-alert v-if="error" :title="error" type="warning" :closable="false"/>
  <template v-if="record">
   <p v-if="record.resumePosition">原课程位置：第 {{record.resumePosition.currentPage}} 页，{{Math.floor(record.resumePosition.currentTime/60)}} 分 {{Math.floor(record.resumePosition.currentTime%60)}} 秒。</p>
   <p v-if="(record.status==='queued'||record.status==='running')&&record.stage!=='generating_answer_course'">{{record.stage==='answering'?'正在生成回答':record.stage==='synthesizing_speech'?'正在生成回答语音':'正在生成回答视频'}}，原课程位置已保存。</p>
   <p v-if="record.answer" class="answer-text">{{record.answer}}</p>
   <div v-if="record.stage==='generating_answer_course'"><p>{{stageNames[childProgress?.stage]||'正在生成临时回答课件和视频'}}。</p><el-progress v-if="childProgress" :percentage="childProgress.progress||0"/></div>
   <el-link v-if="record.pptUrl" :href="record.pptUrl" target="_blank" type="primary">下载回答课件</el-link>
   <el-alert v-if="record.status==='failed'" :title="record.message" type="error" :closable="false"/>
   <el-button v-if="record.status==='failed'" :loading="submitting" @click="retryAnswer">重试回答</el-button>
   <el-button v-if="record.status==='completed'&&record.videoUrl" @click="playAnswer">播放回答</el-button>
   <video v-if="record.status==='completed'&&record.videoUrl" ref="answerMedia" :src="record.videoUrl" controls autoplay playsinline @ended="resume"/>
  </template>
 </section>
</template>
<style scoped>
.course-question{margin:24px 0;padding:20px;border:1px solid #dce7df;border-radius:12px}.question-actions{display:flex;gap:12px;margin:14px 0}.answer-text{white-space:pre-wrap;line-height:1.8}.course-question video{width:100%;max-height:520px;background:#14241c;border-radius:10px}
</style>
