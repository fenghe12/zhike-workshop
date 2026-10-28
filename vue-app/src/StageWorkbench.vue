<script setup lang="ts">
import {computed,ref,watch} from 'vue'
import {api,type Task} from './api'
import StageOutput from './StageOutput.vue'
import AudioWaveform from './AudioWaveform.vue'
import CourseQuestion from './CourseQuestion.vue'
import CourseQuiz from './CourseQuiz.vue'
import CourseSearch from './CourseSearch.vue'
import CourseFeedback from './CourseFeedback.vue'
import {recordUsage} from './usage'
const props=defineProps<{task:Task;stage:number}>()
const output=computed<any>(()=>props.task.outputs?.['s'+props.stage]||{})
const languages=computed(()=>Object.keys(output.value.languages||{}))
const language=ref(''),tab=ref('overview'),busy=ref(false),error=ref(''),page=ref(0)
const data=computed<any>(()=>languages.value.length?output.value.languages[language.value]||{}:output.value)
const source=ref<any>({}),translated=ref<any>({}),report=ref<any>({}),timeline=ref<any>({}),layout=ref<any>({})
const speechAudio=ref<HTMLAudioElement>(),video=ref<HTMLVideoElement>()
const playbackSpeed=ref(Number(localStorage.getItem('smartcourse-playback-speed')||'1.25'))
const currentVideoPage=ref<number|null>(null)
const played=new Set<string>()
function recordPlay(){const key=props.task.id+':'+language.value;if(!played.has(key)){played.add(key);recordUsage('result_play',{taskId:props.task.id,language:language.value})}}
function recordDownload(event:MouseEvent){const link=(event.target as HTMLElement)?.closest('a');const href=link?.getAttribute('href');if(props.stage===5&&href?.startsWith('/artifacts/'))recordUsage('result_download',{taskId:props.task.id,language:language.value,fileType:href.split('.').pop()?.split('?')[0]||'unknown'})}
const languageNames:Record<string,string>={zh:'中文',en:'英语',ja:'日语',ko:'韩语',de:'德语',fr:'法语',ru:'俄语'}
const metricNames:Record<string,string>={semantic_similarity:'语义相似度',terminology_coverage:'术语覆盖率',formula_number_proper_name_accuracy:'公式、数字与专名匹配',contextual_consistency:'整体语义一致性'}
const selectedPage=computed(()=>translated.value.pages?.[page.value]||source.value.pages?.[page.value])
const sourcePage=computed(()=>source.value.pages?.find((p:any)=>p.page_id===selectedPage.value?.page_id))
const pageReport=computed(()=>report.value.pages?.find((p:any)=>p.page_id===selectedPage.value?.page_id))
const previewRoot=computed(()=>String(data.value.translatedPptx||data.value.translatedPdf||'').replace(/[^/]+$/, 'preview/'))
const previewPdf=computed(()=>data.value.previewPdf||previewRoot.value+'translated.pdf')
const previewImage=computed(()=>data.value.previewPages?.[page.value]||previewRoot.value+'slide_'+String(page.value+1).padStart(3,'0')+'.png')
const selectedBox=computed(()=>layout.value.bboxes?.[page.value])
const progress=computed(()=>props.task.stages.find(s=>s.index===props.stage))
const fileNames:Record<string,string>={pdf:'原始 PDF 课件',coursePdf:'PDF 课件',translatedPdf:'翻译后的 PDF',viewPptx:'兼容查看版课件',portablePreview:'网页预览',downloadBundle:'完整结果包',coursePptx:'带讲稿的课件',lectureScript:'视频讲稿',sourceLecture:'源语言讲稿',translatedLecture:'译文讲稿',video:'课程视频',finalVideo:'课程视频',poster:'视频封面',pptx:'课程课件',translatedPptx:'翻译课件',translatedStructure:'逐页译文',validationReport:'校验说明',narrationStructure:'口语讲稿',timeline:'时间轴',bbox:'布局坐标',manifest:'结果清单',fullAudio:'完整语音',referenceAudio:'参考声音',referenceImage:'参考照片',srt:'SRT 字幕',courseStructure:'课程结构',previewPdf:'PDF 预览'}
const links=computed(()=>Object.entries(data.value).filter(([,v])=>typeof v==='string'&&v.startsWith('/artifacts/')))
const totalDuration=computed(()=>Number(timeline.value.total_duration||data.value.durationSeconds||0))
watch(languages,list=>{if(!list.includes(language.value))language.value=list[0]||''},{immediate:true})
watch(video,(element,previous,onCleanup)=>{
 if(previous)previous.removeEventListener('timeupdate',onVideoTimeUpdate)
 if(element){element.playbackRate=playbackSpeed.value;element.addEventListener('timeupdate',onVideoTimeUpdate);onCleanup(()=>element.removeEventListener('timeupdate',onVideoTimeUpdate))}
})
watch(playbackSpeed,value=>{
 if(video.value)video.value.playbackRate=value
 if(speechAudio.value)speechAudio.value.playbackRate=value
 localStorage.setItem('smartcourse-playback-speed',String(value))
})
let requestNumber=0
watch([()=>props.task.id,()=>props.stage,()=>language.value,()=>JSON.stringify(data.value)],async()=>{
 tab.value='overview'
 const current=++requestNumber;busy.value=true;error.value='';page.value=0
 source.value={};translated.value={};report.value={};timeline.value={};layout.value={}
 const s1=props.task.outputs?.s1 as any
 const entries:Array<[string,any]>=[['source',s1?.courseStructure],['translated',data.value.translatedStructure],['report',data.value.validationReport],['timeline',data.value.timeline],['layout',data.value.bbox]]
 const fetched=await Promise.allSettled(entries.map(async([key,url])=>[key,typeof url==='string'&&url.startsWith('/artifacts/')?await api<any>(url):{}] as const))
 if(current!==requestNumber)return
 for(const item of fetched){if(item.status==='rejected'){error.value='部分阶段文件暂时无法读取，可在输出文件中重试。';continue}const [key,value]=item.value;if(key==='source')source.value=value;if(key==='translated')translated.value=value;if(key==='report')report.value=value;if(key==='timeline')timeline.value=value;if(key==='layout')layout.value=value}
 busy.value=false
},{immediate:true})
function jump(seconds:number){if(speechAudio.value)speechAudio.value.currentTime=seconds;if(video.value)video.value.currentTime=seconds}
function onVideoTimeUpdate(){
 const current=Number(video.value?.currentTime)
 if(!Number.isFinite(current)||!timeline.value.pages?.length)return
 const index=timeline.value.pages.findIndex((item:any)=>{
  const start=Number(item.start_time??item.start),end=Number(item.end_time??item.end)
  return current>=start&&current<=end
 })
 if(index>=0){page.value=index;currentVideoPage.value=timeline.value.pages[index].page_id}
}
async function jumpToPage(identifier:number){
 const item=timeline.value.pages?.find((value:any)=>value.page_id===identifier)
 if(!item||!video.value){error.value='页面时间轴尚未加载，请稍后重试。';return}
 jump(Number(item.start_time??item.start));currentVideoPage.value=identifier
 try{await video.value.play()}catch{error.value='请点击视频播放器中的播放按钮。'}
}
function time(value:number){return Number.isFinite(value)?`${Math.floor(value/60)}:${Math.floor(value%60).toString().padStart(2,'0')}`:'—'}
</script>
<template>
 <div class="stage-workbench" v-loading="busy" @click="recordDownload">
  <el-radio-group v-if="languages.length" v-model="language" class="language-switch"><el-radio-button v-for="code in languages" :key="code" :value="code">{{languageNames[code.split('-')[0]!]||code}}</el-radio-button></el-radio-group>
  <el-alert v-if="error" :title="error" type="warning" :closable="false"/>
  <el-alert v-if="[3,5].includes(stage)&&data.warning" :title="data.warning" type="warning" :closable="false"/>
  <el-alert v-if="stage===3&&language.startsWith('en')&&data.speechPacing" :title="data.speechPacing.passed===false?'英语逐句语速检测：有异常语句需要复核。':data.speechPacing.checkedPages>=data.pageCount?'英语逐句语速检测通过。':'英语逐句语速已检查 '+data.speechPacing.checkedPages+' 页；其余页面的有效语句不足，请试听确认。'" :type="data.speechPacing.passed===false?'warning':data.speechPacing.checkedPages>=data.pageCount?'success':'info'" :closable="false"/>
  <el-tabs v-model="tab">
   <el-tab-pane label="阶段概览" name="overview">
    <div class="stage-stat-grid"><div><small>处理页数</small><strong>{{data.pageCount??report.pageCount??output.pageCount??'待统计'}}</strong></div><div><small>已用时间</small><strong>{{progress?.elapsedSeconds!==undefined?time(progress.elapsedSeconds):'待统计'}}</strong></div><div><small>预计剩余</small><strong>{{progress?.etaSeconds!==undefined?time(progress.etaSeconds):'待估算'}}</strong></div></div>
    <div v-if="progress?.detail&&progress.status==='running'" class="stage-subsection"><h3>当前处理对象</h3><StageOutput :value="progress.detail"/></div>
    <div v-if="stage===1" class="stage-subsection"><h3>课程内容结构化</h3><p>查看逐页标题、教学要点和讲稿，核对课件内容后进入翻译。</p><el-alert v-if="data.reviewStatus==='needs_review'" title="自动内容审阅仍有待人工判断的项目，请检查课件和逐页讲稿。" type="warning" :closable="false"/><el-link v-if="data.pptx" :href="data.pptx" target="_blank" type="primary">下载原格式课件</el-link></div>
    <template v-if="stage===2"><div class="metric-grid"><div v-for="(name,key) in metricNames" :key="key"><span>{{name}}</span><strong>{{typeof data.metrics?.[key]==='number'?(data.metrics[key]*100).toFixed(1)+'%':'待校验'}}</strong></div></div><el-alert :title="data.passed===true?'自动校验通过，请继续检查逐页译文。':(data.warning||'译文需要检查，查看逐页内容和校验说明。')" :type="data.passed===true?'success':'warning'" :closable="false"/><el-link v-if="data.translatedPptx||data.translatedPdf" :href="data.translatedPptx||data.translatedPdf" target="_blank" type="primary">下载该语种课件</el-link></template>
    <template v-if="stage===3"><div class="stage-subsection" v-if="data.referenceAudio"><h3>本任务参考声音</h3><audio :src="data.referenceAudio" controls preload="metadata"/></div><div class="stage-subsection" v-if="data.fullAudio"><h3>生成语音试听</h3><audio ref="speechAudio" :src="data.fullAudio" controls preload="metadata"/><AudioWaveform :src="data.fullAudio" @seek="jump"/><p class="muted">请检查专业术语、数字、句尾完整性和音质。字幕采用实际语音时间戳。</p></div></template>
    <template v-if="stage===4"><div class="teacher-summary"><img v-if="data.referenceImage" :src="data.referenceImage" alt="当前任务参考照片"/><div><h3>本任务数字讲者</h3><p>已生成 {{data.successPages??0}} / {{data.pageCount??'待统计'}} 页</p><p class="muted">检查人物是否与参考照片一致，以及口型、头部运动和页面遮挡。</p></div></div><div class="avatar-previews"><div v-for="item in data.generationPages||[]" :key="item.page_id"><h4>第 {{item.page_id}} 页</h4><video v-if="item.previewUrl" :src="item.previewUrl" controls preload="metadata"/><span v-else class="muted">视频预览地址尚未提供</span></div></div></template>
    <template v-if="stage===5"><video v-if="data.video||data.finalVideo" ref="video" @play="recordPlay" class="course-video" :src="data.video||data.finalVideo" :poster="data.poster" controls preload="metadata"/><div v-if="data.video||data.finalVideo" class="playback-speed"><span>播放语速</span><el-select v-model="playbackSpeed" aria-label="播放语速" size="small"><el-option :value="1" label="正常 1.0×"/><el-option :value="1.15" label="稍快 1.15×"/><el-option :value="1.25" label="推荐 1.25×"/><el-option :value="1.5" label="快速 1.5×"/></el-select><span class="muted">仅影响播放，不改变下载的视频</span></div><div class="stage-subsection"><h3>成品检查</h3><p>逐页检查内容、语音、人物和字幕，确认完整后下载使用。</p><div class="file-links"><el-link v-if="data.downloadBundle" :href="data.downloadBundle" type="primary">下载完整结果包</el-link><el-link v-if="data.coursePptx" :href="data.coursePptx" target="_blank" type="primary">下载带讲稿的课件</el-link><el-link v-if="data.previewPdf" :href="data.previewPdf" target="_blank" type="primary">下载 PDF</el-link><el-link v-if="data.viewPptx" :href="data.viewPptx" target="_blank" type="primary">下载兼容查看版</el-link><el-link v-if="data.portablePreview" :href="data.portablePreview" target="_blank" type="primary">网页预览</el-link><el-link v-if="data.lectureScript" :href="data.lectureScript" target="_blank" type="primary">查看视频讲稿</el-link><el-link v-if="data.srt" :href="data.srt" target="_blank" type="primary">下载 SRT 字幕</el-link></div></div></template>
    <p v-if="stage===5&&currentVideoPage" class="video-page-indicator">当前课件页：第 {{currentVideoPage}} 页 · 搜索、时间轴和提问均以此页为准</p>
    <CourseFeedback v-if="stage===5&&(data.video||data.finalVideo)" :task="task" :language="language" :media="video" :page-id="currentVideoPage"/>
    <section v-if="stage===5&&data.pageVideos?.length" class="stage-subsection">
     <h3>课程目录与逐页下载</h3>
     <el-table :data="data.pageVideos">
      <el-table-column prop="page_id" label="页码" width="80"/>
      <el-table-column label="时长"><template #default="scope">{{time(scope.row.durationSeconds)}}</template></el-table-column>
      <el-table-column label="操作"><template #default="scope"><el-button link type="primary" @click="jumpToPage(scope.row.page_id)">播放本页</el-button><el-link :href="scope.row.path" target="_blank" type="primary">下载本页视频</el-link></template></el-table-column>
     </el-table>
    </section>
    <CourseQuiz v-if="stage===5&&(data.video||data.finalVideo)" :course-id="task.id" :language="language" :media="video" :timeline="timeline"/>
    <CourseQuestion v-if="stage===5&&(data.video||data.finalVideo)" :course-id="task.id" :language="language" :media="video" :timeline="timeline" :source="data.video||data.finalVideo"/>
    <CourseSearch v-if="stage===5&&(data.video||data.finalVideo)" :pages="[...(translated.pages||[]),...(source.pages||[])]" :timeline="timeline" :media="video"/>
   </el-tab-pane>
   <el-tab-pane v-if="stage===2&&(data.translatedPptx||data.translatedPdf)" label="课件预览" name="slides"><p class="muted">页面由生成服务渲染，可直接检查文字、公式和排版。</p><el-select v-model="page" class="page-selector"><el-option v-for="(item,index) in translated.pages||[]" :key="item.page_id" :value="index" :label="'第 '+item.page_id+' 页 · '+item.title"/></el-select><el-link :href="previewPdf" target="_blank" type="primary">打开 PDF 预览</el-link><img class="translated-slide-preview" :src="previewImage" :alt="'第 '+(page+1)+' 页译文课件'"/></el-tab-pane>
   <el-tab-pane v-if="stage===1||stage===2" :label="stage===2?'源文 · 译文 · 回译':'逐页内容与讲稿'" name="pages">
    <el-select v-model="page" placeholder="选择课件页面" class="page-selector"><el-option v-for="(item,index) in translated.pages||source.pages||[]" :key="item.page_id" :value="index" :label="'第 '+item.page_id+' 页 · '+item.title"/></el-select>
    <el-empty v-if="!selectedPage" description="尚未产生逐页内容"/><template v-else><h3>{{selectedPage.title}}</h3><div v-if="stage===2" class="translation-columns"><article><h4>源文</h4><p>{{sourcePage?.script_text||'未提供源文讲稿'}}</p></article><article><h4>译文</h4><p>{{selectedPage.script_text}}</p></article><article><h4>回译</h4><p>{{pageReport?.back_translation||'尚未提供回译结果'}}</p></article></div><template v-else><ul><li v-for="point in selectedPage.key_points||[]">{{point}}</li></ul><p class="script-text">{{selectedPage.script_text}}</p></template><el-alert v-if="pageReport?.note" :title="pageReport.note" :type="pageReport.passed?'success':'warning'" :closable="false"/></template>
   </el-tab-pane>
   <el-tab-pane v-if="stage===3||stage===5" label="页级时间轴" name="timeline"><el-empty v-if="!timeline.pages?.length" description="实际音频对齐后显示页面时间轴"/><template v-else><div class="page-timeline"><button v-for="item in timeline.pages" :key="item.page_id" :style="{flexGrow:Math.max(.01,item.duration)}" @click="jump(item.start_time)">{{item.page_id}}</button></div><p class="muted">总时长 {{time(totalDuration)}} · 点击页面定位到实际起始时间</p><el-table :data="timeline.pages"><el-table-column prop="page_id" label="页码" width="70"/><el-table-column label="开始"><template #default="scope">{{Number(scope.row.start_time).toFixed(3)}} 秒</template></el-table-column><el-table-column label="结束"><template #default="scope">{{Number(scope.row.end_time).toFixed(3)}} 秒</template></el-table-column><el-table-column prop="script_text" label="讲稿" min-width="220" show-overflow-tooltip/></el-table></template></el-tab-pane>
   <el-tab-pane v-if="stage===4" label="页面布局与遮挡" name="layout"><el-empty v-if="!layout.bboxes?.length" description="页面分析后显示实际布局坐标"/><template v-else><el-select v-model="page" class="page-selector"><el-option v-for="(item,index) in layout.bboxes" :key="item.slide_number" :value="index" :label="'第 '+item.slide_number+' 页'"/></el-select><div v-if="selectedBox?.imageUrl" class="layout-preview" :style="{aspectRatio:selectedBox.img_w+'/'+selectedBox.img_h}"><img :style="selectedBox.layout_mode==='side_panel'?{width:selectedBox.slide_content_width_px/selectedBox.img_w*100+'%',top:((selectedBox.slide_content_height_px||selectedBox.img_h)/selectedBox.img_h-selectedBox.slide_content_width_px/selectedBox.img_w)*50+'%'}:{}" :src="selectedBox.imageUrl" alt="课件页面布局"/><span :style="{left:selectedBox.x_px/selectedBox.img_w*100+'%',top:selectedBox.y_px/selectedBox.img_h*100+'%',width:selectedBox.size_px/selectedBox.img_w*100+'%',height:selectedBox.size_px/selectedBox.img_h*100+'%'}">数字人</span></div><p>{{selectedBox?.reason}}</p><el-table :data="layout.bboxes"><el-table-column prop="slide_number" label="页码"/><el-table-column prop="x_px" label="X 坐标"/><el-table-column prop="y_px" label="Y 坐标"/><el-table-column prop="size_px" label="区域尺寸"/><el-table-column label="布局"><template #default="scope">{{scope.row.layout_mode==='side_panel'?'独立侧栏':'页面内叠加'}}</template></el-table-column></el-table></template></el-tab-pane>
   <el-tab-pane label="输出文件与执行记录" name="files"><div class="file-links"><el-link v-for="([key,url]) in links" :key="key" :href="String(url)" target="_blank" type="primary">{{fileNames[key]||key}} ↗</el-link></div><StageOutput :value="output"/></el-tab-pane>
  </el-tabs>
 </div>
</template>
<style scoped>
.translated-slide-preview{display:block;width:100%;height:auto;margin-top:16px;border:1px solid #dce7df;border-radius:8px}.language-switch{margin:8px 0 18px}.stage-stat-grid,.metric-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin:12px 0 24px}.stage-stat-grid>div,.metric-grid>div{background:#f4f8f5;border:1px solid #e5ede8;border-radius:12px;padding:18px}.stage-stat-grid small,.metric-grid span{display:block;color:#75877e;font-size:12px}.stage-stat-grid strong,.metric-grid strong{display:block;font-size:24px;margin-top:8px;color:#244c3e}.metric-grid{grid-template-columns:repeat(2,1fr)}.stage-subsection{margin:24px 0}.stage-subsection audio{width:100%;margin-bottom:12px}.page-selector{width:100%;max-width:540px;margin:16px 0}.translation-columns{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}.translation-columns article{border:1px solid #e2e9e4;border-radius:12px;padding:18px;min-width:0}.translation-columns h4{color:#168763;margin:0 0 12px}.translation-columns p,.script-text{white-space:pre-wrap;line-height:1.85;overflow-wrap:anywhere}.teacher-summary{display:flex;align-items:center;gap:24px;margin:20px 0}.teacher-summary img{width:130px;height:160px;object-fit:cover;border-radius:12px}.avatar-previews{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}.avatar-previews video,.course-video{width:100%;border-radius:12px;background:#17241e;max-height:520px}.page-timeline{display:flex;gap:3px;height:48px;margin:20px 0;overflow:hidden}.page-timeline button{border:0;background:#d9eee2;color:#236247;min-width:16px;cursor:pointer}.page-timeline button:hover{background:#a5d4b9}.layout-preview{position:relative;max-width:800px}.layout-preview{background:white}.layout-preview img{display:block;width:100%;position:absolute;left:0;top:0}.layout-preview span{position:absolute;border:2px dashed #159264;background:#15926422;color:#116648;font-size:12px;display:grid;place-items:center}.file-links{display:flex;flex-wrap:wrap;gap:18px;margin-bottom:20px}@media(max-width:760px){.stage-stat-grid{grid-template-columns:repeat(3,1fr);gap:6px}.stage-stat-grid>div{padding:12px}.stage-stat-grid strong{font-size:18px}.translation-columns,.avatar-previews{grid-template-columns:1fr}.teacher-summary{align-items:flex-start;gap:14px}.teacher-summary img{width:90px;height:110px}}
.video-page-indicator{margin:8px 0 18px;color:#168763;font-size:13px}
.playback-speed{display:flex;align-items:center;gap:12px;margin:12px 0}.playback-speed .el-select{width:150px}.playback-speed .muted{font-size:12px}
</style>
