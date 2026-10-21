<script setup lang="ts">
import {computed,onMounted,ref} from 'vue'
import {api} from './api'
type Task={id:string;name:string;status:string;outputs?:any}
type Page={page_id:number;title:string;script_text:string;key_points?:string[]}
const tasks=ref<Task[]>([]),taskId=ref(''),pages=ref<Page[]>([]),selected=ref(0),busy=ref(false),message=ref(''),error=ref('')
const task=computed(()=>tasks.value.find(item=>item.id===taskId.value))
async function loadPages(){if(!taskId.value)return;busy.value=true;error.value='';try{const taskData=await api<any>(`/v1/tasks/${encodeURIComponent(taskId.value)}`);const url=taskData.outputs?.s1?.courseStructure;if(!url)throw Error('课程没有可编辑的页面结构');const structure=await api<any>(url);pages.value=(structure.pages||[]).map((item:any)=>({page_id:Number(item.page_id),title:String(item.title||''),script_text:String(item.script_text||''),key_points:[...(item.key_points||[])]}));selected.value=0;message.value=`已读取 ${pages.value.length} 页课程内容`}catch(e){error.value=(e as Error).message}finally{busy.value=false}}
function move(direction:number){const target=selected.value+direction;if(target<0||target>=pages.value.length)return;[pages.value[selected.value],pages.value[target]]=[pages.value[target],pages.value[selected.value]];selected.value=target}
function removePage(){if(pages.value.length<=1)return;pages.value.splice(selected.value,1);selected.value=Math.min(selected.value,pages.value.length-1)}
function addPage(){const id=Math.max(0,...pages.value.map(item=>item.page_id))+1;pages.value.splice(selected.value+1,0,{page_id:id,title:'新增页面',script_text:'',key_points:[]});selected.value+=1}
function save(){localStorage.setItem(`smartcourse-deck-editor-${taskId.value}`,JSON.stringify(pages.value));message.value='编辑草稿已保存到当前课程工作区'}
function restore(){try{const value=JSON.parse(localStorage.getItem(`smartcourse-deck-editor-${taskId.value}`)||'null');if(Array.isArray(value)){pages.value=value;message.value='已恢复本地编辑草稿'}}catch{}}
function download(){const blob=new Blob([JSON.stringify({taskId:taskId.value,pages:pages.value},null,2)],{type:'application/json'});const url=URL.createObjectURL(blob);const link=document.createElement('a');link.href=url;link.download=`${task.value?.name||'course'}-editable-pages.json`;link.click();URL.revokeObjectURL(url)}
onMounted(async()=>{try{tasks.value=(await api<Task[]>('/v1/tasks')).filter(item=>item.status==='completed');taskId.value=tasks.value[0]?.id||'';await loadPages();restore()}catch(e){error.value=(e as Error).message}})
</script>
<template>
 <div class="deck-editor">
  <div class="heading"><div><p class="eyebrow">EDITABLE COURSE DECK</p><h1>课件逐页编辑</h1><p>修改页面标题和讲稿，调整页面顺序，保存编辑草稿。</p></div><el-tag effect="plain" round>编辑工作区</el-tag></div>
  <section class="panel editor-toolbar"><el-select v-model="taskId" filterable placeholder="选择已完成课程" @change="loadPages"><el-option v-for="item in tasks" :key="item.id" :value="item.id" :label="item.name"/></el-select><el-button :loading="busy" @click="loadPages">重新读取</el-button><el-button @click="restore">恢复草稿</el-button><el-button type="primary" @click="save">保存草稿</el-button><el-button @click="download">导出编辑结果</el-button></section>
  <el-alert v-if="error" :title="error" type="error" :closable="false"/><el-alert v-if="message" :title="message" type="success" :closable="false"/>
  <div v-if="pages.length" class="editor-layout">
   <section class="panel page-list"><div class="section-top"><h2>课程页面</h2><span>{{pages.length}} 页</span></div><button v-for="(page,index) in pages" :key="index" :class="{active:selected===index}" @click="selected=index"><span>{{index+1}}</span>{{page.title||'未命名页面'}}</button><div class="list-actions"><el-button size="small" @click="addPage">新增页</el-button><el-button size="small" @click="removePage" :disabled="pages.length<=1">删除页</el-button></div></section>
   <section class="panel page-form"><div class="section-top"><h2>第 {{selected+1}} 页</h2><div><el-button text @click="move(-1)" :disabled="selected===0">上移</el-button><el-button text @click="move(1)" :disabled="selected===pages.length-1">下移</el-button></div></div><el-form label-position="top"><el-form-item label="页面标题"><el-input v-model="pages[selected].title"/></el-form-item><el-form-item label="可朗读讲稿"><el-input v-model="pages[selected].script_text" type="textarea" :rows="16"/></el-form-item><el-form-item label="教学要点"><el-input v-for="(_,index) in pages[selected].key_points" :key="index" v-model="pages[selected].key_points![index]" class="point-input"/><el-button link type="primary" @click="pages[selected].key_points!.push('')">新增教学要点</el-button></el-form-item></el-form></section>
  </div>
 </div>
</template>
<style scoped>.deck-editor{max-width:1200px;margin:0 auto}.editor-toolbar{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-bottom:18px}.editor-toolbar .el-select{min-width:300px}.editor-layout{display:grid;grid-template-columns:300px 1fr;gap:18px}.page-list{padding:16px}.page-list button{display:flex;gap:10px;align-items:center;width:100%;padding:11px 8px;border:0;border-bottom:1px solid #edf2ee;background:white;text-align:left;color:#536c5e;cursor:pointer}.page-list button span{color:#276447;font-weight:700;min-width:20px}.page-list button.active{background:#edf5ef;color:#244c3a;font-weight:700}.list-actions{display:flex;gap:8px;margin-top:14px}.page-form{padding:22px}.point-input{margin-bottom:8px}@media(max-width:760px){.editor-layout{grid-template-columns:1fr}.editor-toolbar .el-select{min-width:100%}}
</style>
