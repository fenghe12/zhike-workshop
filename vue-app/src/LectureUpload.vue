<script setup lang="ts">
import {ref} from 'vue'
const emit=defineEmits<{select:[file:File|undefined]}>()
const selected=ref<File>(),error=ref(''),inputElement=ref<HTMLInputElement>()
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
</script>
<template>
 <el-form-item label="逐页讲稿（DOCX，可选）">
  <input ref="inputElement" type="file" accept=".docx" aria-label="选择逐页讲稿" @change="choose"/>
  <p class="hint">未上传时根据课件内容生成讲稿；上传时用“第 1 页”等标题对应课件页面，也支持每页一个独立段落。</p>
  <p v-if="selected">已选择：{{selected.name}}</p>
  <el-button v-if="selected" link type="danger" @click="clear">移除讲稿</el-button>
  <el-alert v-if="error" :title="error" type="error" :closable="false"/>
 </el-form-item>
</template>
