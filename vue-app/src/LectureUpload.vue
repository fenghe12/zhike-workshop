<script setup lang="ts">
import {ref,watch} from 'vue'
const props=defineProps<{selectedFile?:File}>()
const emit=defineEmits<{select:[file:File|undefined];mode:[value:'auto'|'docx']}>()
const selected=ref<File>(),error=ref(''),inputElement=ref<HTMLInputElement>(),mode=ref<'auto'|'docx'>('auto')
watch(()=>props.selectedFile,file=>{selected.value=file;if(file){mode.value='docx';emit('mode','docx')}},{immediate:true})
function choose(event:Event){
 const input=event.target as HTMLInputElement,file=input.files?.[0]
 error.value=''
 if(!file)return
 if(!file.name.toLowerCase().endsWith('.docx')||file.size>20*1024*1024){
  error.value='请选择不超过 20 MB 的 DOCX 讲稿。';input.value='';return
 }
 selected.value=file;emit('select',file)
}
function clear(){selected.value=undefined;error.value='';if(inputElement.value)inputElement.value.value='';emit('select',undefined)}
function modeChanged(value:'auto'|'docx'){if(value==='auto')clear();emit('mode',value)}
</script>
<template>
 <el-form-item label="讲稿来源">
  <el-radio-group v-model="mode" @change="modeChanged"><el-radio value="auto">根据 PPT 直接生成讲稿</el-radio><el-radio value="docx">上传 DOCX 讲稿</el-radio></el-radio-group>
  <input v-if="mode==='docx'" ref="inputElement" type="file" accept=".docx" aria-label="选择逐页讲稿" @change="choose"/>
  <p v-if="mode==='docx'" class="hint">用“第 1 页”等标题对应课件页面，也支持每页一个独立段落。</p>
  <p v-if="selected">已选择：{{selected.name}}</p>
  <el-button v-if="selected" link type="danger" @click="clear">移除讲稿</el-button>
  <el-alert v-if="error" :title="error" type="error" :closable="false"/>
 </el-form-item>
</template>
