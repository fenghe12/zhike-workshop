<script setup lang="ts">
defineProps<{value:any;label?:string}>()
const labels:Record<string,string>={viewPptx:'兼容查看版课件',portablePreview:'网页预览',downloadBundle:'完整结果包',coursePptx:'带讲稿的课件',lectureScript:'视频讲稿',sourceLecture:'源语言讲稿',translatedLecture:'译文讲稿',page:'当前页',previewPdf:'PDF 预览',previewPages:'页面预览',narrationStructure:'口语讲稿',segmentCount:'视频片段数',fileSizeMb:'文件大小（MB）',languages:'各语种结果',pageCount:'课件页数',languageCount:'输出语种',pages:'逐页内容',title:'页面标题',script_text:'页面讲稿',key_points:'教学要点',metrics:'质量指标',semantic_similarity:'语义相似度',terminology_coverage:'术语覆盖率',formula_number_proper_name_accuracy:'公式、数字与专名匹配',contextual_consistency:'整体语义一致性',passed:'检查结果',video:'课程视频',finalVideo:'课程视频',fullAudio:'完整音频',srt:'字幕文件',timeline:'时间轴',durationSeconds:'时长（秒）',referenceAudio:'参考声音',referenceImage:'讲者照片',translatedPptx:'翻译课件',translatedStructure:'翻译内容',validationReport:'校验报告',courseStructure:'课程结构',pptx:'课程课件',bbox:'布局标注',manifest:'结果清单',start:'开始时间',end:'结束时间',text:'文本内容',note:'说明',status:'状态',source:'来源',page_id:'页码',language:'语种',processed:'已处理',total:'总数量',step:'处理步骤',elapsedSeconds:'已用时（秒）'}
const isLink=(v:any)=>typeof v==='string'&&v.startsWith('/artifacts/')
</script>
<template>
 <div class="output-section">
  <h3 v-if="label">{{labels[label]||label}}</h3>
  <template v-if="Array.isArray(value)"><el-collapse v-if="value.some(v=>v&&typeof v==='object')"><el-collapse-item v-for="(item,index) in value" :title="String(item.title||item.name||'记录 '+(index+1))" :name="index"><StageOutput :value="item"/></el-collapse-item></el-collapse><ul v-else><li v-for="item in value">{{item}}</li></ul></template>
  <template v-else-if="value&&typeof value==='object'"><div v-for="(item,key) in value" :key="String(key)" class="output-property"><StageOutput v-if="item&&typeof item==='object'" :value="item" :label="String(key)"/><template v-else><span class="output-label">{{labels[String(key)]||key}}</span><template v-if="isLink(item)"><video v-if="/\.mp4(?:\?|$)/i.test(item)" :src="item" controls preload="metadata"/><audio v-else-if="/\.(wav|mp3)(?:\?|$)/i.test(item)" :src="item" controls preload="metadata"/><img v-else-if="/\.(png|jpg|webp)(?:\?|$)/i.test(item)" :src="item" alt="阶段生成结果"/><el-link :href="item" target="_blank" type="primary">查看或下载文件</el-link></template><el-tag v-else-if="typeof item==='boolean'" :type="item?'success':'warning'">{{item?'通过':'待处理'}}</el-tag><p v-else>{{item===null?'尚未产生':item}}</p></template></div></template>
  <p v-else>{{value}}</p>
 </div>
</template>
