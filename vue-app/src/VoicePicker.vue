<script setup lang="ts">
import {onMounted,ref,watch} from 'vue'
import {api} from './api'
const model=defineModel<string>({default:'default'})
const voices=ref<Array<{id:string;name:string;sampleUrl?:string}>>([]),error=ref('')
const selectedVoice=ref<{id:string;name:string;sampleUrl?:string}>()
const emit=defineEmits<{selectionName:[name:string]}>()
watch([model,voices],()=>{selectedVoice.value=voices.value.find(voice=>voice.id===model.value);emit('selectionName',selectedVoice.value?.name||'未选择可用音色')},{immediate:true})
onMounted(async()=>{try{voices.value=await api('/api/voices');if(!voices.value.length){error.value='服务器尚未配置可用音色。';return}if(!voices.value.some(voice=>voice.id===model.value))model.value=voices.value[0].id}catch(e){error.value=(e as Error).message}})
</script>
<template><div class="voice-choice"><div class="voice-title"><h3>讲解音色</h3><span>先试听，再开始生成</span></div><el-select v-model="model" placeholder="选择课程音色"><el-option v-for="voice in voices" :key="voice.id" :value="voice.id" :label="voice.name"/></el-select><audio v-if="selectedVoice?.sampleUrl" class="voice-preview" :src="selectedVoice.sampleUrl" controls preload="metadata"/><p>音色用于课程讲解和提问回答，教师形象单独设置。参考音频建议 6–12 秒，单人说话且无明显背景噪声。</p><el-alert v-if="error" :title="error" type="warning" :closable="false"/></div></template>
<style scoped>.voice-choice{margin:20px 0}.voice-title{display:flex;align-items:baseline;justify-content:space-between;margin-bottom:10px}.voice-title h3{margin:0}.voice-title span{font-size:11px;color:#7b9a87}.voice-preview{display:block;width:100%;margin:12px 0}.voice-choice p{font-size:13px;color:#64776b;line-height:1.7}</style>
