<script setup lang="ts">
import {computed,onUnmounted,ref,watch} from 'vue'
import {api,post} from './api'

type Question={question_id:string;locale:string;prompt:string;options:Array<{id:string;text:string}>;anchor?:{page_id?:number|string}}
const props=defineProps<{courseId:string;language:string;media?:HTMLVideoElement;timeline:any}>()
const questions=ref<Question[]>([])
const active=ref<Question|null>(null)
const selected=ref('')
const result=ref<{correct:boolean;feedback:string;attemptNumber:number;remediation?:any;remediationError?:string}|null>(null)
const remediation=ref<any>(null)
const error=ref('')
const busy=ref(false)
const completed=ref<string[]>([])
const eventId=ref('')
let remediationTimer:ReturnType<typeof setTimeout>|undefined
const available=computed(()=>questions.value.filter(question=>question.locale===props.language))
const key=computed(()=>`smartcourse-quiz:${props.courseId}:${props.language}`)

function pageFor(question:Question){
  const number=Number(question.anchor?.page_id)
  return Number.isInteger(number)&&number>0?number:null
}
function currentPage(){
  const time=props.media?.currentTime
  if(time===undefined)return null
  const page=props.timeline?.pages?.find((item:any)=>time>=Number(item.start_time)&&time<=Number(item.end_time))
  return page?Number(page.page_id):null
}
function updatePosition(){
  if(active.value||!props.media)return
  const page=currentPage()
  if(page===null)return
  const question=available.value.find(item=>pageFor(item)===page&&!completed.value.includes(item.question_id))
  if(question){
    props.media.pause()
    active.value=question
    selected.value=''
    result.value=null
    eventId.value=''
  }
}
watch(()=>props.media,(media,previous,onCleanup)=>{
  previous?.removeEventListener('timeupdate',updatePosition)
  media?.addEventListener('timeupdate',updatePosition)
  onCleanup(()=>media?.removeEventListener('timeupdate',updatePosition))
},{immediate:true})
watch([()=>props.courseId,()=>props.language],async()=>{
  if(remediationTimer)clearTimeout(remediationTimer)
  active.value=null;selected.value='';result.value=null;remediation.value=null;eventId.value='';error.value='';questions.value=[]
  try{completed.value=JSON.parse(sessionStorage.getItem(key.value)||'[]')}catch{completed.value=[]}
  try{questions.value=await api<Question[]>(`/v1/courses/${encodeURIComponent(props.courseId)}/questions`)}
  catch(e){error.value=(e as Error).message}
},{immediate:true})
onUnmounted(()=>{props.media?.removeEventListener('timeupdate',updatePosition);if(remediationTimer)clearTimeout(remediationTimer)})

async function pollRemediation(statusUrl:string){
  try{
    const value=await api<any>(statusUrl)
    remediation.value=value
    if(value.status==='queued'||value.status==='running')remediationTimer=setTimeout(()=>pollRemediation(statusUrl),2500)
  }catch(e){error.value=(e as Error).message}
}

async function submit(){
  if(!active.value||!selected.value||busy.value)return
  busy.value=true;error.value=''
  try{
    if(!eventId.value)eventId.value=`quiz-${Date.now()}-${Math.random().toString(36).slice(2)}`
    result.value=await post(`/v1/questions/${encodeURIComponent(active.value.question_id)}/attempt`,{
      option_id:selected.value,clientEventId:eventId.value,
    })
    remediation.value=result.value?.remediation||null
    if(remediation.value?.statusUrl)void pollRemediation(remediation.value.statusUrl)
    if(!completed.value.includes(active.value.question_id)){
      completed.value=[...completed.value,active.value.question_id]
      try{sessionStorage.setItem(key.value,JSON.stringify(completed.value))}catch{}
    }
  }catch(e){error.value=(e as Error).message}
  finally{busy.value=false}
}
function resume(){if(remediationTimer)clearTimeout(remediationTimer);active.value=null;selected.value='';result.value=null;remediation.value=null;eventId.value='';void props.media?.play().catch(()=>{})}
function review(){
  const page=active.value&&pageFor(active.value)
  const target=props.timeline?.pages?.find((item:any)=>Number(item.page_id)===page)
  if(target&&props.media){props.media.currentTime=Number(target.start_time)}
  if(remediationTimer)clearTimeout(remediationTimer)
  active.value=null;selected.value='';result.value=null;remediation.value=null;eventId.value=''
  void props.media?.play().catch(()=>{})
}
function retry(){if(remediationTimer)clearTimeout(remediationTimer);selected.value='';result.value=null;remediation.value=null;eventId.value=''}
function setRemediationSpeed(event:Event){(event.currentTarget as HTMLVideoElement).playbackRate=props.media?.playbackRate||1.25}
</script>

<template>
  <section class="course-quiz">
    <h3>随堂练习</h3>
    <p v-if="!available.length" class="muted">当前语种尚无已审核的练习题。</p>
    <p v-else class="muted">{{available.length}} 道题；播放到对应页面时自动暂停。</p>
    <el-alert v-if="error" :title="error" type="warning" :closable="false"/>
    <template v-if="active">
      <p class="quiz-prompt">{{active.prompt}}</p>
      <el-radio-group v-model="selected" :disabled="!!result||busy" class="quiz-options">
        <el-radio v-for="option in active.options" :key="option.id" :value="option.id">{{option.text}}</el-radio>
      </el-radio-group>
      <el-button v-if="!result" type="primary" :loading="busy" :disabled="!selected" @click="submit">提交答案</el-button>
      <template v-else>
        <el-alert :title="result.correct?'回答正确':'回答有误'" :description="result.feedback" :type="result.correct?'success':'warning'" :closable="false"/>
        <div v-if="!result.correct" class="remediation">
          <h4>专门讲解视频</h4>
          <p v-if="remediation&&remediation.status!=='completed'&&remediation.status!=='failed'">正在生成与这道错题对应的讲解视频，完成后可在这里播放。</p>
          <video v-if="remediation?.status==='completed'&&remediation.videoUrl" :src="remediation.videoUrl" :poster="remediation.posterUrl" controls preload="metadata" playsinline @loadedmetadata="setRemediationSpeed"/>
          <el-alert v-if="remediation?.status==='failed'||result.remediationError" :title="remediation?.message||result.remediationError||'讲解视频暂时未完成'" type="warning" :closable="false"/>
        </div>
        <el-button v-if="!result.correct" @click="review">复习对应页面</el-button>
        <el-button v-if="!result.correct" @click="retry">再次作答</el-button>
        <el-button type="primary" @click="resume">继续播放课程</el-button>
      </template>
    </template>
    <el-select v-else-if="available.length" placeholder="选择练习题" style="max-width:520px;width:100%" @change="active=available.find(item=>item.question_id===$event)||null">
      <el-option v-for="question in available" :key="question.question_id" :value="question.question_id" :label="question.prompt"/>
    </el-select>
  </section>
</template>

<style scoped>
.course-quiz{margin:24px 0;padding:20px;border:1px solid #dce7df;border-radius:12px}
.quiz-prompt{font-weight:600;line-height:1.7}.quiz-options{display:flex;flex-direction:column;align-items:flex-start;margin:14px 0}
.course-quiz .el-button{margin:8px 8px 0 0}
.remediation{margin:16px 0;padding:16px;border:1px solid #dce7df;border-radius:10px;background:#f7faf8}.remediation h4{margin:0 0 8px}.remediation video{display:block;width:100%;max-height:520px;margin-top:12px;background:#102f2b;border-radius:10px}
</style>
