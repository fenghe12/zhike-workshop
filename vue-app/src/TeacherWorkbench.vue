<script setup lang="ts">
import {computed,onMounted,onUnmounted,ref,watch} from 'vue'
import {useRoute,useRouter} from 'vue-router'
import {api,post,type Task} from './api'

type Objective={objective_id:string;text:string;required:boolean}
type Unit={unit_id:string;title:string;objective_ids:string[];page_ids:number[];prerequisite_unit_ids?:string[]}
type Blueprint={blueprint_id:string;course_id:string;source_revision:number;target_locale:string;revision:number;status:string;objectives:Objective[];units:Unit[]}
type UnitDraft={unitId:string;title:string;objectiveId:string;objectiveText:string;pageIds:number[];prerequisiteIds:string[]}
type Question={question_id:string;prompt:string;status:string;locale:string;correct_option_id:string;options:Array<{id:string;text:string;feedback:string}>}
const route=useRoute()
const router=useRouter()
const tasks=ref<Task[]>([])
const courseId=ref('')
const sourcePages=ref<Array<{page_id:number;title:string;script_text:string}>>([])
const blueprints=ref<Blueprint[]>([])
const selectedBlueprint=ref<Blueprint|null>(null)
const locale=ref('zh-CN')
const units=ref<UnitDraft[]>([])
const build=ref<any>(null)
const questions=ref<Question[]>([])
const patchPlans=ref<any[]>([])
const patchAvailable=ref(true)
const sourcePdf=ref(false)
const patchPage=ref(1)
const patchKind=ref<'script'|'slide_text'|'subtitle'>('script')
const patchLocale=ref('zh-CN')
const patchOldText=ref('')
const patchText=ref('')
const stats=ref<any>(null)
const error=ref('')
const message=ref('')
const busy=ref(false)
const question=ref({locale:'zh-CN',prompt:'',anchorPage:1,objectiveId:'',correct:'a',a:'',b:'',c:'',d:'',feedbackA:'',feedbackB:'',feedbackC:'',feedbackD:''})
const locales=[{code:'zh-CN',name:'中文'},{code:'en-US',name:'英语'},{code:'ja-JP',name:'日语'},{code:'ko-KR',name:'韩语'},{code:'de-DE',name:'德语'},{code:'fr-FR',name:'法语'}]
const completedTasks=computed(()=>tasks.value.filter(task=>task.status==='completed'))
const availablePatchLocales=computed(()=>{
  const task=completedTasks.value.find(item=>item.id===courseId.value)
  return locales.filter(item=>task?.targetLanguages?.some(value=>value===item.code||value===item.name))
})
const availableUnitIds=computed(()=>units.value.map(unit=>({value:unit.unitId,label:unit.title||unit.unitId})))
let buildTimer:ReturnType<typeof setTimeout>|undefined

function newUnit(){
  let index=units.value.length+1
  while(units.value.some(unit=>unit.unitId===`unit-${index}`||unit.objectiveId===`objective-${index}`))index++
  units.value.push({unitId:`unit-${index}`,title:'',objectiveId:`objective-${index}`,objectiveText:'',pageIds:[],prerequisiteIds:[]})
}
function resetBlueprint(){selectedBlueprint.value=null;locale.value='zh-CN';units.value=[];newUnit();build.value=null}
function editBlueprint(value:Blueprint){
  selectedBlueprint.value=value;locale.value=value.target_locale
  units.value=value.units.map(unit=>{
    const objectiveId=unit.objective_ids[0]||`objective-${unit.unit_id}`
    return {unitId:unit.unit_id,title:unit.title,objectiveId,
      objectiveText:value.objectives.find(item=>item.objective_id===objectiveId)?.text||'',
      pageIds:unit.page_ids.map(Number),prerequisiteIds:[...(unit.prerequisite_unit_ids||[])]}
  })
  build.value=null
  if(value.status==='APPROVED')void loadBuild(value.blueprint_id)
}
function blueprintPayload(){
  const entries=units.value
  if(!entries.length||entries.some(item=>!item.title.trim()||!item.objectiveText.trim()||!item.pageIds.length)){
    throw Error('每个单元都须填写标题、教学目标并关联页面。')
  }
  return {
    source_revision:selectedBlueprint.value?.source_revision||1,target_locale:locale.value,
    objectives:entries.map(item=>({objective_id:item.objectiveId,text:item.objectiveText.trim(),required:true,
      source_refs:item.pageIds.map(page_id=>({page_id}))})),
    units:entries.map(item=>({unit_id:item.unitId,title:item.title.trim(),objective_ids:[item.objectiveId],
      page_ids:item.pageIds,prerequisite_unit_ids:item.prerequisiteIds.filter(id=>id!==item.unitId),estimated_seconds:0})),
  }
}
async function refresh(){
  if(!courseId.value)return
  error.value=''
  try{
    const id=encodeURIComponent(courseId.value)
    const task=await api<Task>(`/v1/tasks/${id}`)
    sourcePdf.value=(task.outputs?.s1 as any)?.inputMode==='pdf_converted_pptx'
    if(!availablePatchLocales.value.some(item=>item.code===patchLocale.value)){
      patchLocale.value=availablePatchLocales.value[0]?.code||'zh-CN'
    }
    const structureUrl=(task.outputs?.s1 as any)?.courseStructure
    const structure=structureUrl?await api<any>(structureUrl):null
    sourcePages.value=(structure?.pages||[]).map((page:any)=>({page_id:Number(page.page_id),title:String(page.title||''),script_text:String(page.script_text||'')}))
    blueprints.value=await api<Blueprint[]>(`/v1/courses/${id}/blueprints`)
    try{patchPlans.value=await api<any[]>(`/v1/courses/${id}/patch-plans`);patchAvailable.value=true}
    catch{patchPlans.value=[];patchAvailable.value=false}
    questions.value=await api<Question[]>(`/v1/courses/${id}/teacher/questions`)
    stats.value=await api<any>(`/v1/courses/${id}/question-stats`)
    if(selectedBlueprint.value){
      selectedBlueprint.value=blueprints.value.find(item=>item.blueprint_id===selectedBlueprint.value?.blueprint_id)||null
    }else if(blueprints.value.length){
      editBlueprint(blueprints.value.find(item=>item.status==='APPROVED')||blueprints.value[0]!)
    }
    if(sourcePages.value.length&&!sourcePages.value.some(page=>page.page_id===question.value.anchorPage)){
      question.value.anchorPage=sourcePages.value[0]!.page_id
    }
    if(sourcePages.value.length&&!sourcePages.value.some(page=>page.page_id===patchPage.value)){
      patchPage.value=sourcePages.value[0]!.page_id
      patchText.value=sourcePages.value[0]!.script_text
    }
    if(sourcePages.value.length&&!patchText.value){
      patchText.value=sourcePages.value.find(page=>page.page_id===patchPage.value)?.script_text||''
    }
  }catch(e){error.value=(e as Error).message}
}
async function saveBlueprint(){
  error.value='';message.value='';busy.value=true
  try{
    const payload=blueprintPayload()
    const result=selectedBlueprint.value
      ?await api<Blueprint>(`/v1/blueprints/${encodeURIComponent(selectedBlueprint.value.blueprint_id)}`,{method:'PUT',body:JSON.stringify({expected_revision:selectedBlueprint.value.revision,blueprint:payload})})
      :await post<Blueprint>(`/v1/courses/${encodeURIComponent(courseId.value)}/blueprints`,payload)
    selectedBlueprint.value=result;message.value='教学蓝图草稿已保存。';await refresh()
  }catch(e){error.value=(e as Error).message}
  finally{busy.value=false}
}
async function approveBlueprint(){
  if(!selectedBlueprint.value)return
  error.value='';busy.value=true
  try{
    selectedBlueprint.value=await post<Blueprint>(`/v1/blueprints/${encodeURIComponent(selectedBlueprint.value.blueprint_id)}/approve`,{expected_revision:selectedBlueprint.value.revision})
    message.value='教学蓝图已批准。';await refresh()
  }catch(e){error.value=(e as Error).message}
  finally{busy.value=false}
}
async function loadBuild(id:string){
  try{
    build.value=await api<any>(`/v1/blueprints/${encodeURIComponent(id)}/unit-build`)
    if(['QUEUED','RUNNING'].includes(build.value.status)){
      buildTimer=setTimeout(()=>loadBuild(id),2500)
    }
  }catch(e){if((e as Error).message!=='微课单元生成任务不存在')error.value=(e as Error).message}
}
async function buildUnits(){
  if(!selectedBlueprint.value)return
  error.value='';busy.value=true
  try{
    build.value=await post<any>(`/v1/blueprints/${encodeURIComponent(selectedBlueprint.value.blueprint_id)}/unit-build`,{})
    message.value='微课单元已开始生成。';void loadBuild(selectedBlueprint.value.blueprint_id)
  }catch(e){error.value=(e as Error).message}
  finally{busy.value=false}
}
async function createQuestion(){
  error.value='';message.value='';busy.value=true
  try{
    const form=question.value
    const options=[['a',form.a,form.feedbackA],['b',form.b,form.feedbackB],['c',form.c,form.feedbackC],['d',form.d,form.feedbackD]]
      .filter(([,text])=>String(text).trim()).map(([id,text,feedback])=>({id,text:String(text).trim(),feedback:String(feedback)}))
    if(!form.prompt.trim()||options.length<2||!options.some(option=>option.id===form.correct))throw Error('请填写题干、至少两个选项及正确选项。')
    await post(`/v1/courses/${encodeURIComponent(courseId.value)}/questions`,{
      locale:form.locale,type:'single_choice',prompt:form.prompt.trim(),options,correct_option_id:form.correct,
      objective_id:form.objectiveId||null,anchor:{page_id:form.anchorPage},
    })
    message.value='题目草稿已创建，审核后才会向学生展示。'
    question.value={...form,prompt:'',a:'',b:'',c:'',d:'',feedbackA:'',feedbackB:'',feedbackC:'',feedbackD:''}
    await refresh()
  }catch(e){error.value=(e as Error).message}
  finally{busy.value=false}
}
async function reviewQuestion(item:Question,approved:boolean){
  error.value='';busy.value=true
  try{await post(`/v1/questions/${encodeURIComponent(item.question_id)}/review`,{approved});await refresh()}
  catch(e){error.value=(e as Error).message}
  finally{busy.value=false}
}
async function createPatchPlan(){
  error.value='';message.value='';busy.value=true
  try{
    if(!patchText.value.trim())throw Error('请填写修订内容。')
    if(patchKind.value!=='script'&&!patchOldText.value.trim())throw Error('请填写要修订的原文片段。')
    await post(`/v1/courses/${encodeURIComponent(courseId.value)}/patch-plans`,{
      changes:[{page_id:patchPage.value,kind:patchKind.value,
        oldText:patchKind.value!=='script'?patchOldText.value.trim():undefined,
        locale:patchKind.value==='subtitle'?patchLocale.value:undefined,text:patchText.value.trim()}],
    })
    message.value='局部修订方案已保存，批准后可生成新版本。';await refresh()
  }catch(e){error.value=(e as Error).message}
  finally{busy.value=false}
}
async function approvePatchPlan(plan:any){
  error.value='';busy.value=true
  try{await post(`/v1/patch-plans/${encodeURIComponent(plan.patch_plan_id)}/approve`,{});await refresh()}
  catch(e){error.value=(e as Error).message}
  finally{busy.value=false}
}
async function executePatchPlan(plan:any){
  error.value='';busy.value=true
  try{
    const result=await post<{releaseTaskId:string}>(`/v1/patch-plans/${encodeURIComponent(plan.patch_plan_id)}/execute`,{})
    await refresh()
    await router.push('/task?id='+encodeURIComponent(result.releaseTaskId))
  }catch(e){error.value=(e as Error).message}
  finally{busy.value=false}
}
watch(patchPage,number=>{patchText.value=patchKind.value==='script'?(sourcePages.value.find(page=>page.page_id===number)?.script_text||''):'';patchOldText.value=''})
watch(patchKind,kind=>{patchText.value=kind==='script'?(sourcePages.value.find(page=>page.page_id===patchPage.value)?.script_text||''):'';patchOldText.value=''})
watch(courseId,()=>{if(buildTimer)clearTimeout(buildTimer);resetBlueprint();question.value.objectiveId='';patchPage.value=1;patchText.value='';void refresh()})
onMounted(async()=>{
  try{
    tasks.value=await api<Task[]>('/v1/tasks')
    const requested=String(route.query.id||'')
    courseId.value=completedTasks.value.some(task=>task.id===requested)?requested:
      (completedTasks.value.find(task=>task.featuredForTeaching)?.id||completedTasks.value[0]?.id||'')
  }catch(e){error.value=(e as Error).message}
})
onUnmounted(()=>{if(buildTimer)clearTimeout(buildTimer)})
</script>

<template>
  <div class="heading"><div><p class="eyebrow">TEACHER WORKSPACE</p><h1>教学设计与练习</h1><p>按课程组织微课单元，审核练习题并查看作答统计。</p></div></div>
  <section class="panel teacher-panel">
    <el-form-item label="课程项目"><el-select v-model="courseId" filterable placeholder="选择已完成的课程" style="width:100%"><el-option v-for="task in completedTasks" :key="task.id" :label="task.name" :value="task.id"/></el-select></el-form-item>
    <el-alert v-if="!completedTasks.length&&!error" title="目前没有已完成的课程，完成生成后即可设计微课单元。" type="info" :closable="false"/>
    <el-alert v-if="error" :title="error" type="warning" :closable="false"/>
    <el-alert v-if="message" :title="message" type="success" :closable="false"/>
  </section>
  <template v-if="courseId">
    <section class="panel teacher-panel">
      <div class="teacher-section-title"><h2>教学蓝图</h2><el-button @click="resetBlueprint">新建草稿</el-button></div>
      <div class="blueprint-list"><el-button v-for="item in blueprints" :key="item.blueprint_id" :type="selectedBlueprint?.blueprint_id===item.blueprint_id?'primary':'default'" plain @click="editBlueprint(item)">{{locales.find(locale=>locale.code===item.target_locale)?.name}} · 版本 {{item.revision}} · {{item.status==='APPROVED'?'已批准':'草稿'}}</el-button></div>
      <el-form label-position="top">
        <el-form-item label="目标语言"><el-select v-model="locale" :disabled="selectedBlueprint?.status==='APPROVED'"><el-option v-for="item in locales" :key="item.code" :value="item.code" :label="item.name"/></el-select></el-form-item>
        <article v-for="(unit,index) in units" :key="unit.unitId" class="unit-editor">
          <div class="teacher-section-title"><h3>单元 {{index+1}}</h3><el-button v-if="units.length>1&&selectedBlueprint?.status!=='APPROVED'" link type="danger" @click="units.splice(index,1)">移除</el-button></div>
          <el-form-item label="单元名称"><el-input v-model="unit.title" :disabled="selectedBlueprint?.status==='APPROVED'"/></el-form-item>
          <el-form-item label="教学目标"><el-input v-model="unit.objectiveText" :disabled="selectedBlueprint?.status==='APPROVED'"/></el-form-item>
          <el-form-item label="关联页面"><el-select v-model="unit.pageIds" multiple filterable :disabled="selectedBlueprint?.status==='APPROVED'" style="width:100%"><el-option v-for="page in sourcePages" :key="page.page_id" :value="page.page_id" :label="`第 ${page.page_id} 页 · ${page.title}`"/></el-select></el-form-item>
          <el-form-item label="先修单元"><el-select v-model="unit.prerequisiteIds" multiple :disabled="selectedBlueprint?.status==='APPROVED'" style="width:100%"><el-option v-for="option in availableUnitIds.filter(item=>item.value!==unit.unitId)" :key="option.value" :value="option.value" :label="option.label"/></el-select></el-form-item>
        </article>
        <div class="teacher-actions"><el-button v-if="selectedBlueprint?.status!=='APPROVED'" @click="newUnit">添加单元</el-button><el-button v-if="selectedBlueprint?.status!=='APPROVED'" type="primary" :loading="busy" @click="saveBlueprint">{{selectedBlueprint?'保存修订':'保存草稿'}}</el-button><el-button v-if="selectedBlueprint?.status==='DRAFT'" :loading="busy" @click="approveBlueprint">批准蓝图</el-button><el-button v-if="selectedBlueprint?.status==='APPROVED'" type="primary" :loading="busy" @click="buildUnits">生成微课单元</el-button></div>
      </el-form>
      <div v-if="build" class="build-result"><p>单元生成状态：{{build.status}}</p><el-alert v-if="build.error" :title="build.error" type="error" :closable="false"/><div v-for="unit in build.result?.units||[]" :key="unit.unitId" class="unit-download"><strong>{{unit.title}}</strong><el-link :href="unit.video" target="_blank">视频</el-link><el-link :href="unit.pdf" target="_blank">PDF</el-link><el-link :href="unit.subtitles" target="_blank">字幕</el-link></div></div>
    </section>
    <section v-if="patchAvailable" class="panel teacher-panel">
      <h2>局部修订</h2>
      <p class="muted">可修改逐页讲稿、课件上一处文字或当前语种的字幕。批准后生成独立课程版本，原课程保持不变。</p>
      <el-form label-position="top">
        <el-form-item label="修订内容"><el-select v-model="patchKind"><el-option value="script" label="逐页讲稿"/><el-option value="slide_text" label="课件文字" :disabled="sourcePdf"/><el-option value="subtitle" label="字幕文字"/></el-select></el-form-item>
        <el-form-item label="修订页面"><el-select v-model="patchPage"><el-option v-for="page in sourcePages" :key="page.page_id" :value="page.page_id" :label="`第 ${page.page_id} 页 · ${page.title}`"/></el-select></el-form-item>
        <el-form-item v-if="patchKind==='subtitle'" label="字幕语种"><el-select v-model="patchLocale"><el-option v-for="item in availablePatchLocales" :key="item.code" :value="item.code" :label="item.name"/></el-select></el-form-item>
        <el-form-item v-if="patchKind!=='script'" :label="patchKind==='subtitle'?'字幕中的原文片段':'课件上的原文（须位于同一文本片段）'"><el-input v-model="patchOldText"/></el-form-item>
        <el-form-item :label="patchKind==='script'?'修订后的可朗读讲稿':patchKind==='subtitle'?'替换后的字幕文字':'替换后的课件文字'"><el-input v-model="patchText" :type="patchKind==='script'?'textarea':'text'" :rows="7"/></el-form-item>
        <p v-if="patchKind==='subtitle'" class="muted">字幕修订会保留原语音和人物视频，重新合成对应语种的视频。请从课程结果下载 SRT，填写同一页面中的原文片段。</p>
        <el-button type="primary" :loading="busy" @click="createPatchPlan">保存修订方案</el-button>
      </el-form>
      <div v-for="plan in patchPlans" :key="plan.patch_plan_id" class="question-review">
        <strong>第 {{plan.changes?.[0]?.page_id}} 页 · {{plan.changes?.[0]?.kind==='slide_text'?'课件文字':plan.changes?.[0]?.kind==='subtitle'?'字幕':'讲稿'}} · {{plan.status==='APPROVED'?'已批准':'草稿'}}</strong>
        <el-button v-if="plan.status==='DRAFT'" link type="primary" :loading="busy" @click="approvePatchPlan(plan)">批准</el-button>
        <el-button v-if="plan.status==='APPROVED'&&!plan.releaseTaskId" link type="primary" :loading="busy" @click="executePatchPlan(plan)">生成修订版</el-button>
        <el-button v-if="plan.releaseTaskId" link @click="router.push('/task?id='+encodeURIComponent(plan.releaseTaskId))">查看修订版任务</el-button>
      </div>
    </section>
    <el-alert v-else title="讲稿修订服务正在更新，请稍后刷新页面。" type="info" :closable="false"/>
    <section class="panel teacher-panel">
      <h2>随堂练习</h2>
      <el-form label-position="top">
        <el-form-item label="语言"><el-select v-model="question.locale"><el-option v-for="item in locales" :key="item.code" :value="item.code" :label="item.name"/></el-select></el-form-item>
        <el-form-item label="关联页面"><el-select v-model="question.anchorPage"><el-option v-for="page in sourcePages" :key="page.page_id" :value="page.page_id" :label="`第 ${page.page_id} 页 · ${page.title}`"/></el-select></el-form-item>
        <el-form-item v-if="selectedBlueprint?.objectives?.length" label="关联教学目标"><el-select v-model="question.objectiveId" clearable placeholder="选择教学目标"><el-option v-for="item in selectedBlueprint.objectives" :key="item.objective_id" :value="item.objective_id" :label="item.text"/></el-select></el-form-item>
        <el-form-item label="题干"><el-input v-model="question.prompt" type="textarea" :rows="2"/></el-form-item>
        <div v-for="id in ['a','b','c','d']" :key="id" class="option-editor"><el-form-item :label="`选项 ${id.toUpperCase()}`"><el-input v-model="question[id as 'a'|'b'|'c'|'d']"/></el-form-item><el-form-item label="作答反馈"><el-input v-model="question[('feedback'+id.toUpperCase()) as 'feedbackA'|'feedbackB'|'feedbackC'|'feedbackD']"/></el-form-item></div>
        <el-form-item label="正确选项"><el-radio-group v-model="question.correct"><el-radio v-for="id in ['a','b','c','d']" :key="id" :value="id">{{id.toUpperCase()}}</el-radio></el-radio-group></el-form-item>
        <el-button type="primary" :loading="busy" @click="createQuestion">创建题目草稿</el-button>
      </el-form>
      <div v-for="item in questions" :key="item.question_id" class="question-review"><strong>{{item.prompt}}</strong><span>{{item.locale}} · {{item.status==='APPROVED'?'已审核':item.status==='REJECTED'?'已退回':'草稿'}}</span><el-button v-if="item.status!=='APPROVED'" link type="primary" @click="reviewQuestion(item,true)">审核通过</el-button><el-button v-if="item.status==='DRAFT'" link type="danger" @click="reviewQuestion(item,false)">退回</el-button></div>
      <div v-if="stats" class="question-stats">已审核 {{stats.approvedQuestions||0}} 题 · 首次/再次作答详见下方<el-table :data="stats.details||[]"><el-table-column prop="question_id" label="题目"/><el-table-column prop="firstAnswers" label="首次作答"/><el-table-column prop="firstCorrect" label="首次正确"/><el-table-column prop="repeatAnswers" label="再次作答"/></el-table></div>
    </section>
  </template>
</template>

<style scoped>
.teacher-panel{margin-bottom:20px}.teacher-section-title{display:flex;justify-content:space-between;align-items:center;gap:16px}.blueprint-list,.teacher-actions{display:flex;flex-wrap:wrap;gap:8px;margin:16px 0}.unit-editor{border:1px solid #dce7df;border-radius:12px;padding:18px;margin:16px 0}.unit-editor h3{margin:0 0 12px}.unit-download,.question-review{display:flex;flex-wrap:wrap;align-items:center;gap:12px;border-top:1px solid #e5ede8;padding:12px 0}.build-result,.question-stats{margin-top:20px}.option-editor{display:grid;grid-template-columns:1fr 1fr;gap:12px}@media(max-width:720px){.option-editor{grid-template-columns:1fr}}
</style>
