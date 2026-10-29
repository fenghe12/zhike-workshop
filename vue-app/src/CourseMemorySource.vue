<script setup lang="ts">
import {onMounted,ref} from 'vue'
import {api} from './api'
defineProps<{courseId:string;templateId:string}>()
const emit=defineEmits<{'update:courseId':[value:string];'update:templateId':[value:string]}>()
const courses=ref<any[]>([]),templates=ref<any[]>([]),error=ref('')
onMounted(async()=>{try{courses.value=(await api<any[]>('/v1/studio/courses')).filter(x=>['owner','editor'].includes(x.role));templates.value=await api<any[]>('/v1/studio/templates')}catch(e){error.value=(e as Error).message}})
</script>
<template><section class="memory-source"><h3>沿用课程记忆与模板</h3><p>选择后使用已采纳的课程记忆和模板参数，保存创建时的版本。</p><label>课程记忆来源<select :value="courseId" @change="emit('update:courseId',($event.target as HTMLSelectElement).value)"><option value="">不选择已有课程记忆</option><option v-for="item in courses" :key="item.id" :value="item.id">{{item.name}}</option></select></label><label>我的课程模板<select :value="templateId" @change="emit('update:templateId',($event.target as HTMLSelectElement).value)"><option value="">不使用模板</option><option v-for="item in templates" :key="item.id" :value="item.id">{{item.name}}</option></select></label><p v-if="error" role="alert">{{error}}</p></section></template>
<style scoped>.memory-source{margin:18px 0;padding:16px;border:1px solid #dce7df;border-radius:8px}.memory-source h3{font-size:14px;margin:0}.memory-source p{font-size:12px;line-height:1.8;color:#6b8172}.memory-source label{display:block;font-size:13px;margin:10px 0}.memory-source select{display:block;box-sizing:border-box;width:100%;margin-top:6px;padding:9px;background:white;color:#234a35;border:1px solid #cbd9ce;border-radius:6px;font:inherit;font-size:16px}</style>
