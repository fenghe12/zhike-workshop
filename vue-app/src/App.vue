<script setup lang="ts">
import {computed,onMounted,onUnmounted,ref,watch} from 'vue'
import {useRoute,useRouter} from 'vue-router'
import {Plus,Grid,VideoCamera,Setting,Document,MagicStick,UploadFilled,ArrowRight,QuestionFilled,Check,Headset,User,Connection,Refresh,FolderOpened,Clock,ArrowLeft,Menu} from '@element-plus/icons-vue'
import {ElMessage,ElMessageBox} from 'element-plus'
import {api,post,ApiError,type Task} from './api'
import StageWorkbench from './StageWorkbench.vue'
import PresetPicker from './PresetPicker.vue'
import LectureUpload from './LectureUpload.vue'
import VoicePicker from './VoicePicker.vue'
import TeacherPhotoInput from './TeacherPhotoInput.vue'
import CodeLessonCreate from './CodeLessonCreate.vue'
import ReferenceAudioInput from './ReferenceAudioInput.vue'
import TeacherWorkbench from './TeacherWorkbench.vue'
import PublicLibrary from './PublicLibrary.vue'
import CoursePlanner from './CoursePlanner.vue'
import DeckEditor from './DeckEditor.vue'
import QuestionBank from './QuestionBank.vue'
import ProductLanding from './ProductLanding.vue'
import QueueNotice from './QueueNotice.vue'
import KnowledgeLibrary from './KnowledgeLibrary.vue'
const lectureFile=ref<File>()
const knowledgeReady=ref(false)
const selectedVoiceName=ref('正在读取音色')
const route=useRoute(),router=useRouter()
const privacy=ref(false)
const screen=computed(()=>route.path.split('/')[1]||'landing')
const labels:Record<string,string>={landing:'产品介绍',home:'任务工作台',create:'创建课程',code:'代码讲解与动画',teacher:'教学设计与练习',task:'任务详情',stage:'阶段详情',results:'结果中心',settings:'系统设置',login:'登录',register:'注册'}
const languages=[{name:'中文',native:'简体中文',code:'ZH'},{name:'英语',native:'English',code:'EN'},{name:'日语',native:'日本語',code:'JA'},{name:'韩语',native:'한국어',code:'KO'},{name:'德语',native:'Deutsch',code:'DE'},{name:'法语',native:'Français',code:'FR'}]
const flow=[{code:'S1',title:'课程内容结构化',description:'读取课件，整理页面与讲稿',icon:Document},{code:'S2',title:'翻译与回译校验',description:'检查语义、术语、公式与数字',icon:Connection},{code:'S3',title:'声音与时间轴',description:'使用所选音色生成多语种讲解',icon:Headset},{code:'S4',title:'数字讲者与布局',description:'使用所选照片生成讲者画面',icon:User},{code:'S5',title:'视频与字幕输出',description:'合成课程，输出视频与 SRT',icon:VideoCamera}]
const statusNames:Record<string,string>={processing:'生成中',running:'执行中',queued:'排队中',completed:'已完成',failed:'需处理',cancelled:'已取消',waiting:'等待执行',waiting_input:'等待上传素材',needs_review:'待审核',needs_regeneration:'待重新生成'}
const tasks=ref<Task[]>([]),loading=ref(false),loadError=ref(''),filter=ref('all'),search=ref(''),connected=ref(false),mediaReady=ref(false),help=ref(false),menuOpen=ref(false)
const emptyDraft=()=>({name:'',mode:'upload',voiceId:'default',referenceAudioUrl:'',teacherImageUrl:'',subtitlesEnabled:true,topic:'',totalPages:10,durationMinutes:10,targetLearners:'高校本科生',requirements:'',sourceLanguage:'英语',targetLanguages:[] as string[]})
function privateDraftKey(){try{return 'smartcourse-vue-draft:'+String(JSON.parse(sessionStorage.getItem('smartcourse-user')||'null')?.id||'guest')}catch{return 'smartcourse-vue-draft:guest'}}
const draftOwnerKey=ref(privateDraftKey()),draft=ref(emptyDraft())
try{Object.assign(draft.value,JSON.parse(localStorage.getItem(draftOwnerKey.value)||'{}'))}catch{}
function switchPrivateDraft(copyGuest=false){
 const key=privateDraftKey();if(key===draftOwnerKey.value)return
 const pending=copyGuest&&draftOwnerKey.value.endsWith(':guest')?{...draft.value}:emptyDraft()
 draftOwnerKey.value=key
 let saved={};try{saved=JSON.parse(localStorage.getItem(key)||'null')||pending}catch{saved=pending}
 Object.assign(draft.value,emptyDraft(),saved);localStorage.setItem(key,JSON.stringify(draft.value))
}
if(route.query.topic){draft.value.mode='topic';draft.value.topic=String(route.query.topic);if(route.query.audience)draft.value.targetLearners=String(route.query.audience)}
watch(draft,v=>localStorage.setItem(draftOwnerKey.value,JSON.stringify(v)),{deep:true})
watch(()=>route.query.topic,value=>{if(value){draft.value.mode='topic';draft.value.topic=String(value);if(route.query.audience)draft.value.targetLearners=String(route.query.audience)}},{immediate:true})
const file=ref<File>(),preview=ref<any>(),fileReading=ref(false),formError=ref(''),submitting=ref(false),fileInput=ref<HTMLInputElement>(),step=ref(0),selected=ref<Task>(),stageNumber=computed(()=>Number(route.query.stage)||1)
const assetInput=ref<HTMLInputElement>()
const generationActive=computed(()=>['processing','running','queued'].includes(selected.value?.status||''))
const activeAsset=computed(()=>selected.value?.assets?.[stageNumber.value===3?'referenceAudio':'referenceImage'])
const selectedStage=computed(()=>selected.value?.stages?.find(s=>s.index===stageNumber.value))
const filtered=computed(()=>tasks.value.filter(t=>(filter.value==='all'||(filter.value==='failed'?['failed','waiting_input','needs_regeneration'].includes(t.status):filter.value==='processing'?['processing','running','queued'].includes(t.status):t.status===filter.value))&&t.name.toLowerCase().includes(search.value.toLowerCase())))
const completed=computed(()=>tasks.value.filter(t=>t.status==='completed'))
const emptyAuth=()=>({name:'',institution:'',account:'',password:'',confirmPassword:'',agreed:false})
const currentUser=ref<any>(null),auth=ref(emptyAuth()),authError=ref(''),sessionReady=ref(false)
try{currentUser.value=JSON.parse(sessionStorage.getItem('smartcourse-user')||'null')}catch{}
const translationPolicy=ref({semantic_similarity:.85,terminology_coverage:.9,formula_number_proper_name_accuracy:1,contextual_consistency:.85,maxRetries:1})
const policyLabels={semantic_similarity:'语义相似度',terminology_coverage:'术语覆盖率',formula_number_proper_name_accuracy:'公式、数字与专名匹配',contextual_consistency:'整体语义一致性'}
const settings=ref({base_url:''}),settingMessage=ref(''),assetBusy=ref(false)
function go(path:string){menuOpen.value=false;router.push(path);window.scrollTo(0,0)}
async function health(){try{const d=await api<any>('/v1/health');connected.value=d.status==='ok';mediaReady.value=d.mediaService==='RUNNING';if(!settings.value.base_url)settings.value.base_url=d.base_url||''}catch{connected.value=false;mediaReady.value=false}}
async function fetchTasks(){const owner=currentUser.value?.id;if(!owner){tasks.value=[];loadError.value='';return}loading.value=true;loadError.value='';try{const d=await api<Task[]>('/v1/tasks');if(currentUser.value?.id===owner)tasks.value=d}catch(e){if(currentUser.value?.id===owner)loadError.value=(e as Error).message}finally{if(currentUser.value?.id===owner)loading.value=false}}
async function fetchTask(){const id=String(route.query.id||''),owner=currentUser.value?.id;if(!id||!owner)return;if(selected.value?.id!==id)selected.value=undefined;try{const task=await api<Task>('/v1/tasks/'+encodeURIComponent(id));if(currentUser.value?.id===owner&&String(route.query.id)===id)selected.value=task}catch(e){if(currentUser.value?.id===owner)ElMessage.error((e as Error).message)}}
function resetAccountView(){tasks.value=[];selected.value=undefined;file.value=undefined;preview.value=null;lectureFile.value=undefined;knowledgeReady.value=false;step.value=0;fileReading.value=false;filter.value='all';search.value='';loading.value=false;loadError.value='';formError.value='';settingMessage.value='';translationPolicy.value={semantic_similarity:.85,terminology_coverage:.9,formula_number_proper_name_accuracy:1,contextual_consistency:.85,maxRetries:1}}
function clearSession(){sessionStorage.removeItem('smartcourse-token');sessionStorage.removeItem('smartcourse-user');currentUser.value=null;resetAccountView();switchPrivateDraft();auth.value=emptyAuth()}
watch(screen,()=>{authError.value='';auth.value.password='';auth.value.confirmPassword='';auth.value.agreed=false})
watch(()=>route.fullPath,()=>{formError.value='';health();if(screen.value==='settings')loadPolicy();if(['home','results'].includes(screen.value))fetchTasks();if(['task','stage'].includes(screen.value))fetchTask()},{immediate:true})
let poll:ReturnType<typeof setInterval>
onMounted(()=>{health();post<any>('/v1/auth/session',{}).then(data=>{currentUser.value=data.user;sessionStorage.setItem('smartcourse-user',JSON.stringify(data.user));switchPrivateDraft();if(['home','results'].includes(screen.value))fetchTasks();if(['task','stage'].includes(screen.value))fetchTask();if(screen.value==='settings')loadPolicy()}).catch(e=>{if(e instanceof ApiError&&e.status===401)clearSession()}).finally(()=>{sessionReady.value=true});poll=setInterval(()=>{if(['task','stage'].includes(screen.value)&&selected.value&&!['completed','cancelled','failed','needs_regeneration'].includes(selected.value.status))fetchTask()},5000)})
onUnmounted(()=>clearInterval(poll))
async function chooseFile(f?:File){
 if(!f)return
 const owner=currentUser.value?.id
 if(!owner){formError.value='请先登录后上传课程素材。';return}
 if(!/\.(pptx|pdf)$/i.test(f.name)){formError.value='请选择 PPTX 或 PDF 课件。';return}
 if(f.size>280*1024*1024){formError.value='文件超过 280 MB，请压缩课件后重新选择。';return}
 file.value=f;preview.value=null;fileReading.value=true;formError.value=''
 try{
  const data=await api<any>('/api/preview?name='+encodeURIComponent(f.name),{method:'POST',headers:{'Content-Type':'application/octet-stream'},body:f})
  if(currentUser.value?.id!==owner)return
  preview.value=data;if(!draft.value.name)draft.value.name=f.name.replace(/\.(pptx|pdf)$/i,'');if(data.language)draft.value.sourceLanguage=data.language
 }catch(e){if(currentUser.value?.id===owner)formError.value=(e as Error).message}finally{if(currentUser.value?.id===owner)fileReading.value=false}
}
async function bindDraftAsset(f:File,kind:'audio'|'image'){
 const owner=currentUser.value?.id
 if(!owner){formError.value='请先登录后上传课程素材。';return}
 try{
  const data=await new Promise<string>((res,rej)=>{const reader=new FileReader();reader.onload=()=>res(String(reader.result).split(',')[1]);reader.onerror=rej;reader.readAsDataURL(f)})
  if(currentUser.value?.id!==owner)return
  const asset=await post<{path:string}>('/v1/uploads',{filename:f.name,kind,contentBase64:data})
  if(currentUser.value?.id!==owner)return
  if(kind==='audio')draft.value.referenceAudioUrl=asset.path;else draft.value.teacherImageUrl=asset.path
  ElMessage.success(kind==='audio'?'已关联示例声音':'已关联示例教师形象')
 }catch(e){if(currentUser.value?.id===owner)formError.value=(e as Error).message}
}
function bindDraftAudio(f:File){void bindDraftAsset(f,'audio')}
function bindDraftImage(f:File){void bindDraftAsset(f,'image')}
function next(){formError.value='';if(!draft.value.name.trim()){formError.value='先填写任务名称，便于后续查找。';return}if(draft.value.mode==='upload'&&!preview.value){formError.value='请先上传并读取课件。';return}if(draft.value.mode==='topic'&&!draft.value.topic.trim()){formError.value='请描述课程主题和教学范围。';return}if(step.value===1&&!draft.value.targetLanguages.length){formError.value='请至少选择一种输出语言。';return}if(step.value===0&&draft.value.mode==='topic'&&!knowledgeReady.value){formError.value='请先导入课程参考课件。';return}step.value=Math.min(2,step.value+1)}
async function submit(){submitting.value=true;formError.value='';try{if(!currentUser.value)throw Error('请先登录。课程草稿已保存在当前浏览器。');let ppt:{path:string}|null=null,script:{path:string}|null=null;if(draft.value.mode==='upload'){ppt=await post<{path:string}>('/api/transfer-upload',{preview_id:preview.value.id});if(lectureFile.value){const contentBase64=await new Promise<string>((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result).split(',')[1]!);reader.onerror=reject;reader.readAsDataURL(lectureFile.value!)});script=await post<{path:string}>('/v1/uploads',{filename:lectureFile.value.name,kind:'script',contentBase64});}}const t=await post<{jobId:string}>('/api/courses',{...draft.value,pptUrl:ppt?.path,scriptUrl:script?.path,pageCount:draft.value.totalPages,audience:draft.value.targetLearners});go('/task?id='+t.jobId)}catch(e){formError.value=(e as Error).message}finally{submitting.value=false}}
async function authenticate(){
 if(submitting.value||!sessionReady.value)return
 authError.value=''
 const a={...auth.value,account:auth.value.account.trim()},registering=screen.value==='register'
 if(registering&&(!a.name.trim()||!a.institution.trim())){authError.value='请填写姓名和所属单位。';return}
 if(a.account.length<6||a.password.length<6){authError.value='账号和密码均须至少 6 个字符。';return}
 if(registering&&(a.account.length>128||/\s/.test(a.account))){authError.value='账号不能包含空格，且不能超过 128 个字符。';return}
 if(registering&&(a.password.length>128||!a.password.trim())){authError.value='密码须为 6 至 128 个字符，且不能全部为空格。';return}
 if(registering&&a.password!==a.confirmPassword){authError.value='两次输入的密码不一致。';return}
 if(registering&&!a.agreed){authError.value='请先阅读素材处理说明。';return}
 submitting.value=true
 try{
  const d=await post<any>('/v1/auth/'+(registering?'register':'login'),a)
  if(!d.accessToken||!d.user)throw Error('服务未返回有效登录信息。')
  resetAccountView();sessionStorage.setItem('smartcourse-token',d.accessToken);sessionStorage.setItem('smartcourse-user',JSON.stringify(d.user));currentUser.value=d.user;switchPrivateDraft(true);auth.value=emptyAuth();go('/home');ElMessage.success(registering?'注册成功，已进入你的工作台。':'登录成功。')
 }catch(e){authError.value=(e as Error).message}finally{submitting.value=false}
}
async function taskAction(action:string){if(!selected.value)return;try{const id=selected.value.id;if(action==='rename'){const {value}=await ElMessageBox.prompt('输入新的课程名称','修改名称',{inputValue:selected.value.name,inputValidator:v=>!!v.trim()||'名称不能为空'});await api('/v1/tasks/'+id,{method:'PUT',body:JSON.stringify({name:value})})}else{await ElMessageBox.confirm(action==='cancel'?'停止此任务的后续生成？':'删除此任务记录？','确认操作',{type:'warning'});await api('/v1/tasks/'+id+(action==='cancel'?'/cancel':''),{method:action==='cancel'?'POST':'DELETE'});if(action==='delete'){go('/home');return}}await fetchTask()}catch(e){if(e!=='cancel'&&e!=='close')ElMessage.error((e as Error).message)}}
async function retry(){if(!selected.value)return;try{await post(`/v1/tasks/${selected.value.id}/stages/${selected.value.currentStage}/retry`,{});await fetchTask()}catch(e){ElMessage.error((e as Error).message)}}
async function uploadAsset(event:Event){
 const input=event.target as HTMLInputElement,f=input.files?.[0]
 if(f)await bindSelectedAsset(f)
 input.value=''
}
async function bindSelectedAsset(f:File){
 if(!f||!selected.value)return
 const taskId=selected.value.id,isAudio=stageNumber.value===3
 assetBusy.value=true
 try{
  const data=await new Promise<string>((res,rej)=>{const reader=new FileReader();reader.onload=()=>res(String(reader.result).split(',')[1]);reader.onerror=rej;reader.readAsDataURL(f)})
  const asset=await post('/v1/uploads',{filename:f.name,kind:isAudio?'audio':'image',contentBase64:data})
  await api(`/v1/tasks/${taskId}/assets`,{method:'PUT',body:JSON.stringify({[isAudio?'referenceAudio':'referenceImage']:asset})})
  if(String(route.query.id)===taskId)await fetchTask()
  ElMessage.success('素材已上传并关联到所选任务')
 }catch(e){ElMessage.error((e as Error).message)}finally{assetBusy.value=false}
}
async function logout(){if(submitting.value)return;submitting.value=true;try{await post('/v1/auth/logout',{});clearSession();go('/login');ElMessage.success('已退出当前账号。')}catch(e){ElMessage.error((e as Error).message)}finally{submitting.value=false}}
async function loadPolicy(){const owner=currentUser.value?.id;if(!owner)return;try{const policy=await api<typeof translationPolicy.value>('/v1/settings/translation');if(currentUser.value?.id===owner)translationPolicy.value=policy}catch(e){if(currentUser.value?.id===owner)settingMessage.value=(e as Error).message}}
async function saveSettings(){try{await api('/v1/settings/translation',{method:'PUT',body:JSON.stringify(translationPolicy.value)});await health();settingMessage.value=connected.value?'账户参数已保存，服务连接正常。':'账户参数已保存，生成服务尚未响应。'}catch(e){settingMessage.value=(e as Error).message}}

function duration(s?:number){return s===undefined?'待计算':`${Math.floor(s/60)} 分 ${Math.floor(s%60)} 秒`}
</script>

<template>
 <div class="workspace-shell" :class="{'marketing-shell':screen==='landing'}">
  <aside class="sidebar" :class="{open:menuOpen}"><a class="brand" @click="go('/landing')"><span class="brand-symbol"><el-icon><Document/></el-icon></span><span>智课工坊<small>SMARTCOURSE STUDIO</small></span></a><div class="workspace-label"><span class="workspace-avatar">课</span><div>课程工作空间<small>多语言教学视频</small></div></div><p class="nav-caption">工作空间</p><nav><button v-for="item in [{path:'home',name:'任务工作台',icon:Grid},{path:'create',name:'创建课程',icon:Plus},{path:'code',name:'代码讲解与动画',icon:MagicStick},{path:'teacher',name:'教学设计与练习',icon:Document},{path:'results',name:'结果中心',icon:VideoCamera}]" :key="item.path" :class="{active:screen===item.path}" @click="go('/'+item.path)"><el-icon><component :is="item.icon"/></el-icon>{{item.name}}<span v-if="screen===item.path" class="active-dot"/></button></nav><p class="nav-caption tools-caption">内容工具</p><nav class="secondary-nav"><a href="#/public" :class="{active:screen==='public'}" @click="menuOpen=false"><el-icon><Grid/></el-icon>公共课程</a><a href="#/planner" :class="{active:screen==='planner'}" @click="menuOpen=false"><el-icon><Document/></el-icon>课程方案</a><a href="#/editor" :class="{active:screen==='editor'}" @click="menuOpen=false"><el-icon><Document/></el-icon>课件编辑</a><a href="#/question-bank" :class="{active:screen==='question-bank'}" @click="menuOpen=false"><el-icon><Check/></el-icon>题库与练习</a></nav><div class="sidebar-foot"><button @click="help=true"><el-icon><QuestionFilled/></el-icon>使用指南</button><button @click="go('/settings')"><el-icon><Setting/></el-icon>系统设置</button><div class="account"><span class="avatar"><el-icon><User/></el-icon></span><div><strong>{{currentUser?.displayName||'访客'}}</strong><small>{{currentUser?.institution||'登录后管理课程'}}</small></div><el-button link @click="go(currentUser?'/settings':'/login')">{{currentUser?'账户':'登录'}}</el-button></div></div></aside>
  <div v-if="menuOpen" class="nav-backdrop" @click="menuOpen=false"/>
  <section class="main-shell"><header class="topbar"><el-button class="mobile-menu" aria-label="打开导航" text :icon="Menu" @click="menuOpen=!menuOpen"/><el-breadcrumb separator="/"><el-breadcrumb-item @click="go('/home')">工作空间</el-breadcrumb-item><el-breadcrumb-item>{{labels[screen]||'课程'}}</el-breadcrumb-item></el-breadcrumb><div class="top-actions"><span class="service-state" :class="{online:connected&&mediaReady}"><i/>{{!connected?'生成服务未连接':mediaReady?'生成服务已连接':'媒体计算已停止'}}</span><el-button aria-label="使用指南" text :icon="QuestionFilled" @click="help=true"/></div></header>
  <main :key="currentUser?.id||'guest'">
   <template v-if="screen==='landing'"><ProductLanding @open-workspace="go('/home')"/></template>
   <template v-else-if="screen==='home'"><div class="heading"><div><p class="eyebrow">YOUR TEACHING WORKSPACE</p><h1>把课程带给更多学习者</h1><p>创建、跟进与管理你的多语言教学视频。</p></div><el-button type="primary" :icon="Plus" size="large" @click="go('/create')">创建课程</el-button></div><section class="welcome"><div><span class="welcome-kicker">从一份课件开始</span><h2>内容、声音、形象，<br>在同一工作空间完成。</h2><p>选择目标语言，按五个阶段制作课程视频与字幕。</p><el-button @click="go('/create')">开始制作<el-icon><ArrowRight/></el-icon></el-button></div><div class="welcome-visual" aria-hidden="true"><div class="visual-sheet"><span class="sheet-kicker">YOUR NEXT COURSE</span><strong>让知识<br>跨越语言</strong><div class="sheet-lines"><i/><i/><i/></div><div class="mini-languages"><span>中文</span><span>EN</span><span>日本語</span></div></div><div class="floating-play"><el-icon><VideoCamera/></el-icon></div><span class="floating-label">6 种语言 · 5 个阶段</span></div></section><div class="stats"><div v-for="s in [{label:'全部任务',value:tasks.length},{label:'生成中',value:tasks.filter(t=>['processing','running','queued'].includes(t.status)).length},{label:'已完成',value:completed.length},{label:'需处理',value:tasks.filter(t=>['failed','waiting_input','needs_review'].includes(t.status)).length}]"><span>{{s.label}}</span><strong>{{loadError?'—':s.value}}</strong></div></div><div class="section-top"><h2>课程项目</h2><el-button text :icon="Refresh" @click="fetchTasks">刷新</el-button></div><div class="toolbar"><el-radio-group v-model="filter"><el-radio-button value="all">全部</el-radio-button><el-radio-button value="processing">生成中</el-radio-button><el-radio-button value="completed">已完成</el-radio-button><el-radio-button value="failed">需处理</el-radio-button></el-radio-group><el-input v-model="search" aria-label="搜索课程" placeholder="搜索课程名称" clearable/></div><el-alert v-if="loadError" title="暂时无法读取课程" :description="loadError" type="info" show-icon :closable="false"/><div v-else-if="!filtered.length" class="empty"><el-icon><FolderOpened/></el-icon><h3>开始你的第一份课程</h3><p>上传 PPT 或输入主题，创建后在这里查看进度。</p><el-button type="primary" plain @click="go('/create')">创建课程</el-button></div><div class="task-grid" v-loading="loading"><article v-for="t in filtered" class="task-card" @click="go('/task?id='+t.id)"><div class="course-cover"><el-icon><Document/></el-icon><span>{{t.targetLanguages?.length}} 种语言</span></div><div class="task-body"><el-tag size="small">{{statusNames[t.status]||t.status}}</el-tag><h3>{{t.name}}</h3><p>{{t.targetLanguages?.join(' / ')}}</p><el-progress :percentage="t.overallProgress||0" :stroke-width="5"/><small>S{{t.currentStage}} · {{t.updatedAt?new Date(t.updatedAt).toLocaleString():''}}</small></div></article></div></template>

   <template v-else-if="screen==='create'"><div class="heading"><div><p class="eyebrow">CREATE A COURSE</p><h1>创建多语言课程</h1><p>准备课程内容，选择目标语种和音色，可上传教师照片。</p></div><el-tag effect="plain" round>草稿自动保存</el-tag></div><div class="create-layout"><section class="panel form-panel"><el-steps :active="step" finish-status="success" align-center><el-step title="课程内容"/><el-step title="输出语种"/><el-step title="确认创建"/></el-steps><div class="form-content" v-show="step===0"><h2>01 <span>准备课程内容</span></h2><el-form label-position="top"><el-form-item label="任务名称" required><el-input v-model="draft.name" size="large" placeholder="例如：神经网络基础多语种课程" maxlength="120"/><span class="hint">使用便于辨认的名称，之后可以修改。</span></el-form-item><div class="mode-options"><button :class="{selected:draft.mode==='upload'}" @click="draft.mode='upload'"><el-icon><Document/></el-icon><strong>上传已有课件</strong><span>保留课件内容与页面顺序</span><el-icon v-if="draft.mode==='upload'" class="mode-check"><Check/></el-icon></button><button :class="{selected:draft.mode==='topic'}" @click="draft.mode='topic'"><el-icon><MagicStick/></el-icon><strong>输入课程主题</strong><span>生成大纲、讲稿和配套课件</span><el-icon v-if="draft.mode==='topic'" class="mode-check"><Check/></el-icon></button></div><div v-if="draft.mode==='upload'"><PresetPicker kind="ppt" :disabled="fileReading" @select="chooseFile"/><div v-if="!file" class="dropzone" @dragover.prevent @drop.prevent="chooseFile($event.dataTransfer?.files[0])" @click="fileInput?.click()" role="button" tabindex="0" @keydown.enter="fileInput?.click()"><span class="upload-symbol"><el-icon><UploadFilled/></el-icon></span><h3>拖拽课件到这里，或 <b>选择文件</b></h3><p>PPTX 或 PDF 格式 · 最大 280 MB</p></div><div v-else class="selected-file" v-loading="fileReading"><span class="ppt-icon">P</span><div><strong>{{file.name}}</strong><p>{{(file.size/1024/1024).toFixed(2)}} MB<span v-if="preview"> · {{preview.pages}} 页 · {{preview.elements}} 个元素</span></p></div><el-button text type="danger" @click="file=undefined;preview=null">移除</el-button></div><input ref="fileInput" hidden type="file" accept=".pptx,.pdf" @change="chooseFile(($event.target as HTMLInputElement).files?.[0])"/></div><el-form-item v-else label="课程主题与教学要求" required><el-input v-model="draft.topic" type="textarea" :rows="6" placeholder="说明课程主题、面向的学生、教学范围与预期学习目标。"/></el-form-item><template v-if="draft.mode==='topic'"><KnowledgeLibrary :key="currentUser?.id" :enabled="!!currentUser" @ready="knowledgeReady=$event"/><el-form-item label="教学对象"><el-input v-model="draft.targetLearners"/></el-form-item><el-form-item label="课件页数"><el-input-number v-model="draft.totalPages" :min="1" :max="30"/></el-form-item><el-form-item label="预计课程时长（分钟）"><el-input-number v-model="draft.durationMinutes" :min="1" :max="180"/></el-form-item><el-form-item label="补充要求"><el-input v-model="draft.requirements" type="textarea" :rows="3"/></el-form-item></template><LectureUpload v-if="draft.mode==='upload'" @select="lectureFile=$event"/><el-form-item v-if="draft.mode==='upload'" label="源语言" class="source-select"><el-select v-model="draft.sourceLanguage"><el-option v-for="l in languages" :label="l.name" :value="l.name"/></el-select></el-form-item></el-form></div><div v-show="step===1" class="form-content"><h2>02 <span>选择输出语种</span></h2><p class="muted">每种语言分别生成课件、音频、视频和字幕，可同时选择多种。</p><el-checkbox-group v-model="draft.targetLanguages" class="language-options"><el-checkbox v-for="l in languages" :value="l.name" border><span class="lang-code">{{l.code}}</span><span><strong>{{l.name}}</strong><small>{{l.native}}</small></span></el-checkbox></el-checkbox-group><div class="guidance"><el-icon><Headset/></el-icon><div><strong>音色与教师形象独立设置</strong><p>使用所选音色生成讲解，可在任务中单独更换教师照片。</p></div></div></div><el-checkbox v-show="step===1" v-model="draft.subtitlesEnabled">在视频中显示字幕</el-checkbox><VoicePicker v-show="step===1" v-model="draft.voiceId" @selection-name="selectedVoiceName=$event"/><ReferenceAudioInput v-show="step===1" v-model="draft.referenceAudioUrl"/><TeacherPhotoInput v-show="step===1" v-model="draft.teacherImageUrl"/><div v-show="step===2" class="form-content"><h2>03 <span>确认课程任务</span></h2><el-descriptions :column="1" border><el-descriptions-item label="任务名称">{{draft.name}}</el-descriptions-item><el-descriptions-item label="创建方式">{{draft.mode==='upload'?'上传已有课件':'输入课程主题'}}</el-descriptions-item><el-descriptions-item label="课程输入">{{file?.name||draft.topic}}</el-descriptions-item><el-descriptions-item label="输出语种">{{draft.targetLanguages.join('、')}}</el-descriptions-item><el-descriptions-item label="讲解音色">{{selectedVoiceName}}</el-descriptions-item><el-descriptions-item label="教师照片">{{draft.teacherImageUrl?'已上传教师照片':'默认教师形象'}}</el-descriptions-item><el-descriptions-item label="字幕">{{draft.subtitlesEnabled?'显示字幕':'不显示字幕'}}</el-descriptions-item><el-descriptions-item v-if="draft.mode==='topic'" label="课件页数">{{draft.totalPages}} 页</el-descriptions-item><el-descriptions-item v-if="draft.mode==='topic'" label="目标时长">{{draft.durationMinutes}} 分钟</el-descriptions-item><el-descriptions-item v-if="draft.mode==='topic'" label="教学对象">{{draft.targetLearners}}</el-descriptions-item><el-descriptions-item v-if="draft.mode==='upload'" label="逐页讲稿">{{lectureFile?.name||'由系统根据课件生成'}}</el-descriptions-item></el-descriptions><div class="guidance"><el-icon><Clock/></el-icon><div><strong>创建后进入任务详情</strong><p>查看处理进度，完成后播放或下载课程结果。</p></div></div></div><el-alert v-if="formError" :title="formError" type="warning" :closable="false" show-icon/><el-button v-if="step===2&&!currentUser" link type="primary" @click="go('/login')">前往登录，草稿会保留</el-button><footer class="form-actions"><el-button v-if="step>0" @click="step--" :icon="ArrowLeft">上一步</el-button><span v-else class="hint">课程素材将独立保存到当前任务</span><el-button v-if="step<2" type="primary" size="large" @click="next">下一步<el-icon><ArrowRight/></el-icon></el-button><el-button v-else type="primary" size="large" :loading="submitting" @click="submit">创建并启动任务</el-button></footer></section><aside class="create-aside"><section class="panel"><h3>课程概览</h3><div class="preview"><template v-if="preview"><span>第 1 页 · 文本概览</span><h3>{{preview.title}}</h3><p>{{preview.first_page_text?.join(' · ')}}</p></template><template v-else><el-icon><Document/></el-icon><p>上传后显示实际课程内容</p></template></div><div class="preview-count" v-if="preview"><span>{{preview.pages}} 页课件</span><span>{{preview.notes}} 页含讲稿</span></div></section><section class="panel flow-panel"><h3>接下来会发生什么</h3><div v-for="f in flow" class="flow-item"><span>{{f.code}}</span><div><strong>{{f.title}}</strong><p>{{f.description}}</p></div></div></section></aside></div></template>

   <template v-else-if="['task','stage'].includes(screen)&&selected"><div class="heading"><div><p class="eyebrow">COURSE PRODUCTION</p><h1>{{selected.name}}</h1><p>{{selected.targetLanguages.join('、')}} · {{selected.id}}</p></div><el-tag>{{statusNames[selected.status]||selected.status}}</el-tag></div><QueueNotice :task="selected"/><div v-if="selected.status==='waiting_input'" class="next-action"><el-icon><UploadFilled/></el-icon><div><h3>{{selected.requiredAsset==='referenceAudio'?'请上传讲者参考声音':'请上传讲者照片'}}</h3><p>提供素材后继续当前阶段，已完成的结果会保留。</p></div><el-button type="primary" @click="go('/stage?id='+selected.id+'&stage='+selected.currentStage)">前往上传</el-button></div><el-alert v-if="selected.status==='needs_regeneration'" title="素材已更换，请在任务管理中重新生成后续阶段。" type="warning" :closable="false"/><el-alert v-if="selected.error" :title="selected.error.message" type="error" :closable="false"/><section v-if="screen==='task'&&selected.status==='completed'" class="panel"><StageWorkbench :task="selected" :stage="5"/></section><section v-if="screen==='task'" class="panel"><div class="section-top"><h2>任务执行监控</h2><span class="muted">每 5 秒更新</span></div><el-progress :percentage="selected.overallProgress||0"/><div class="stage-row" v-for="s in selected.stages"><span class="stage-number">{{s.code}}</span><div class="stage-label"><strong>{{s.title}}</strong><p>{{statusNames[s.status]||s.status}} · 已用 {{duration(s.elapsedSeconds)}}</p></div><el-progress :percentage="s.progress||0" :stroke-width="5"/><el-button @click="go('/stage?id='+selected.id+'&stage='+s.index)">查看阶段结果</el-button></div><div class="management"><el-button @click="taskAction('rename')">修改名称</el-button><el-button :disabled="!['processing','running','queued'].includes(selected.status)" @click="taskAction('cancel')">取消生成</el-button><el-button :disabled="!['failed','needs_regeneration'].includes(selected.status)" @click="retry">{{selected.status==='needs_regeneration'?'重新生成后续阶段':'重试异常阶段'}}</el-button><el-button type="danger" plain @click="taskAction('delete')">删除任务</el-button></div></section><template v-else><el-tabs :model-value="String(stageNumber)" @tab-change="go('/stage?id='+selected!.id+'&stage='+$event)"><el-tab-pane v-for="f in flow" :label="f.code+' '+f.title" :name="String(flow.indexOf(f)+1)"/></el-tabs><section class="panel"><div class="section-top"><h2>{{selectedStage?.title}}</h2><el-button link @click="go('/task?id='+selected!.id)">任务管理</el-button><el-tag>{{statusNames[selectedStage?.status||'waiting']}}</el-tag></div><p class="muted">{{flow[stageNumber-1]?.description}}</p><PresetPicker v-if="stageNumber===3||stageNumber===4" :kind="stageNumber===3?'audio':'image'" :disabled="assetBusy||generationActive" @select="bindSelectedAsset"/><div v-if="stageNumber===3||stageNumber===4" class="guidance"><el-icon><UploadFilled/></el-icon><div><strong>{{stageNumber===3?'讲者参考音频':'讲者参考图片'}}</strong><p>{{stageNumber===3?'选择清晰的单人语音，试听确认内容与音质。':'选择清晰的单人正面照片，检查人脸完整可见。'}}</p><el-button type="primary" plain :loading="assetBusy" :disabled="generationActive" @click="assetInput?.click()">{{activeAsset?'更换素材':stageNumber===3?'选择参考声音':'选择讲者照片'}}</el-button><input ref="assetInput" hidden type="file" :accept="stageNumber===3?'audio/*':'image/*'" :disabled="assetBusy||generationActive" @change="uploadAsset"/><div v-if="activeAsset" class="bound-reference"><p>已关联：{{activeAsset.name}}</p><audio v-if="stageNumber===3" :src="activeAsset.path" controls preload="metadata"/><img v-else :src="activeAsset.path" alt="本任务已上传讲者照片"/></div><p v-if="generationActive" class="hint">当前任务正在生成，完成或取消后可以更换素材。</p></div></div><div v-if="selectedStage?.status==='running'" class="stage-live-progress"><el-progress :percentage="selectedStage.progress||0"/><p>{{selectedStage.detail?.step||'正在处理'}}<template v-if="selectedStage.detail?.page"> · 第 {{selectedStage.detail.page}} 页</template><template v-if="selectedStage.detail?.total"> · 已处理 {{selectedStage.detail.processed||0}} / {{selectedStage.detail.total}}</template></p></div><el-empty v-if="!selected.outputs?.['s'+stageNumber]" description="此阶段尚未产生结果，完成后会在此显示实际数据。"/><div v-else class="stage-output"><StageWorkbench :task="selected" :stage="stageNumber"/></div></section></template></template>

   <template v-else-if="screen==='public'"><PublicLibrary/></template>
   <template v-else-if="screen==='planner'"><CoursePlanner/></template>
   <template v-else-if="screen==='editor'"><DeckEditor/></template>
   <template v-else-if="screen==='question-bank'"><QuestionBank/></template>
   <template v-else-if="screen==='code'"><CodeLessonCreate/></template>
   <template v-else-if="screen==='teacher'"><TeacherWorkbench/></template>

   <template v-else-if="screen==='results'"><div class="heading"><div><p class="eyebrow">COURSE LIBRARY</p><h1>结果中心</h1><p>按课程查看多语种视频、字幕与生成报告。</p></div></div><el-alert v-if="loadError" :title="loadError" type="info" :closable="false"/><div v-else-if="!completed.length" class="empty"><el-icon><VideoCamera/></el-icon><h3>这里将保存你的课程成品</h3><p>任务完成后，按语言预览和下载视频与字幕。</p><el-button @click="go('/home')">查看任务工作台</el-button></div><article v-for="t in completed" class="panel result-row"><el-icon><VideoCamera/></el-icon><div><h3>{{t.name}}</h3><p>{{t.targetLanguages.join(' / ')}}</p></div><el-button @click="go('/stage?id='+t.id+'&stage=5')">查看结果</el-button></article></template>

   <template v-else-if="screen==='settings'"><div class="heading"><div><p class="eyebrow">PREFERENCES</p><h1>系统设置</h1><p>管理当前账户的课程处理参数。</p></div></div><section class="panel settings-panel"><h2>账号与服务状态</h2><p>{{currentUser?.displayName||'尚未登录'}} · {{currentUser?.institution||'登录后显示所属单位'}}</p><p v-if="currentUser">登录账号：{{currentUser.phone}}</p><el-button v-if="currentUser" :loading="submitting" @click="logout">退出登录</el-button><el-button v-else @click="go('/login')">登录或注册</el-button><el-divider/><el-form label-position="top"><el-form-item label="生成服务状态"><span>{{connected?(mediaReady?'生成服务已连接':'媒体计算已停止'):'生成服务未连接'}}</span></el-form-item><el-divider/><h3>回译一致性校验参数</h3><p class="muted">修改后对新建任务生效。四项得分达到阈值后才进入下一阶段。</p><el-form-item v-for="(label,key) in policyLabels" :key="key" :label="label"><el-input-number v-model="translationPolicy[key]" :min="0" :max="1" :step="0.01" :precision="2"/></el-form-item><el-form-item label="自动修正次数上限"><el-input-number v-model="translationPolicy.maxRetries" :min="0" :max="3" :step="1"/></el-form-item><el-alert v-if="settingMessage" :title="settingMessage" :closable="false"/><el-button type="primary" @click="saveSettings">保存参数并检查连接</el-button></el-form></section></template>

   <template v-else-if="screen==='login'||screen==='register'">
    <section v-if="!sessionReady" class="auth-panel"><p class="muted">正在检查登录状态…</p></section>
    <section v-else-if="currentUser" class="auth-panel">
     <div class="auth-intro"><p class="eyebrow">YOUR ACCOUNT</p><h1>当前已登录</h1><p>{{currentUser.displayName}} · {{currentUser.institution}}</p></div>
     <p class="muted">登录账号：{{currentUser.phone}}</p><p class="muted">切换账号或注册新账号前，请先退出当前账号。</p>
     <el-button type="primary" class="auth-submit" @click="go('/home')">进入我的工作台</el-button><el-button :loading="submitting" @click="logout">退出当前账号</el-button>
    </section>
    <section v-else class="auth-panel">
     <div class="auth-intro"><p class="eyebrow">{{screen==='login'?'WORKSPACE ACCESS':'CREATE ACCOUNT'}}</p><h1>{{screen==='login'?'欢迎回到智课工坊':'注册智课工坊'}}</h1><p>使用账号和密码登录，课件、知识库与任务按账号分别保存。</p></div>
     <el-form label-position="top" :disabled="submitting" @submit.prevent="authenticate">
      <template v-if="screen==='register'">
       <el-form-item label="姓名" required><el-input v-model="auth.name" size="large" autocomplete="name" placeholder="请输入姓名"/></el-form-item>
       <el-form-item label="所属单位" required><el-input v-model="auth.institution" size="large" autocomplete="organization" placeholder="请输入学校或单位名称"/></el-form-item>
      </template>
      <el-form-item label="登录账号" required><el-input v-model="auth.account" size="large" placeholder="邮箱或账号，至少 6 个字符" autocomplete="username" :spellcheck="false"/></el-form-item>
      <el-form-item label="密码" required><el-input v-model="auth.password" type="password" show-password size="large" :autocomplete="screen==='register'?'new-password':'current-password'" placeholder="至少 6 个字符"/></el-form-item>
      <template v-if="screen==='register'">
       <el-form-item label="确认密码" required><el-input v-model="auth.confirmPassword" type="password" show-password size="large" autocomplete="new-password" placeholder="请再次输入密码"/></el-form-item>
       <el-checkbox v-model="auth.agreed">已阅读素材处理说明</el-checkbox><el-button link type="primary" @click="privacy=true">查看说明</el-button>
      </template>
      <el-alert v-if="authError" :title="authError" type="warning" :closable="false" show-icon/>
      <el-button type="primary" size="large" native-type="submit" :loading="submitting" class="auth-submit">{{screen==='login'?'进入工作台':'注册并进入'}}</el-button>
      <el-button link @click="go(screen==='login'?'/register':'/login')">{{screen==='login'?'没有账号？注册新用户':'已有账号，前往登录'}}</el-button>
     </el-form>
    </section>
   </template>
   <el-empty v-else description="请选择一个课程任务。"><el-button @click="go('/home')">返回工作台</el-button></el-empty>
  </main><footer class="app-footer">智课工坊 · 多语言教学视频工作空间</footer></section>
  <el-dialog v-model="privacy" title="素材处理说明" width="min(520px,92vw)"><p>课件、参考音频和照片将保存到当前任务的目录，用于课程制作和结果检查。</p><p>生成过程中，课程文本会发送到已配置的模型服务；声音和照片会发送到已配置的媒体计算服务。</p><p>请使用有权用于本任务的素材。生成结果需要检查后使用。</p><p>当前删除任务操作删除任务记录，生成文件按项目保存安排另行管理。</p><template #footer><el-button type="primary" @click="privacy=false">已了解</el-button></template></el-dialog>
  <el-drawer v-model="help" title="课程制作指南" size="min(440px,100%)"><p class="muted">从课程内容开始，按提示完成每一步。</p><div v-for="f in flow" class="guide-step"><span>{{f.code}}</span><h3>{{f.title}}</h3><p>{{f.description}}</p></div><el-alert title="进度与质量指标来自实际任务" description="需要上传素材或修订内容时，任务详情会显示下一步操作。" type="info" :closable="false"/></el-drawer>
 </div>
</template>
