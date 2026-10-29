<script setup lang="ts">
import {onMounted,ref,computed} from 'vue'
import {api} from './api'
import AiInputAssist from './AiInputAssist.vue'
export type CourseProfile={domain:string;audience:string;topics:string[]}
const props=defineProps<{modelValue?:CourseProfile}>()
const emit=defineEmits<{'update:modelValue':[value:CourseProfile]}>()
const options=ref<any>({domains:{},audiences:{}})
const value=computed(()=>props.modelValue||{domain:'',audience:'',topics:[]})
function update(key:keyof CourseProfile,item:any){emit('update:modelValue',{...value.value,[key]:item})}
onMounted(async()=>{try{options.value=await api('/v1/course-profile/options')}catch{}})
</script>
<template>
 <details class="course-profile"><summary>课程分类与面向人群（选填）</summary><p>用于整理课程及了解平台内的使用需求。</p><div class="profile-grid"><label>课程领域<select :value="value.domain" @change="update('domain',($event.target as HTMLSelectElement).value)"><option value="">未填写</option><option v-for="(label,key) in options.domains" :key="key" :value="key">{{label}}</option></select></label><label>面向人群<select :value="value.audience" @change="update('audience',($event.target as HTMLSelectElement).value)"><option value="">未填写</option><option v-for="(label,key) in options.audiences" :key="key" :value="key">{{label}}</option></select></label></div><label>主题标签<input :value="value.topics.join('，')" type="text" placeholder="例如：神经网络，机器学习；最多 10 个，用逗号分隔" @change="update('topics',($event.target as HTMLInputElement).value.split(/[,，]/).map(v=>v.trim()).filter(Boolean))"><AiInputAssist :model-value="value.topics.join('，')" label="课程主题标签" purpose="topic" :max-length="500" :context="{domain:value.domain,audience:value.audience}" @update:model-value="update('topics',$event.split(/[,，\n]/).map(v=>v.trim()).filter(Boolean).slice(0,10))"/></label></details>
</template>
<style scoped>.course-profile{padding:16px;border:1px solid #dce6df;border-radius:10px;margin:16px 0}.course-profile summary{font-weight:600;cursor:pointer}.course-profile p{font-size:12px;line-height:1.6;color:#718278}.profile-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}.course-profile label{font-size:13px;display:block}.course-profile select,.course-profile input[type=text]{width:100%;box-sizing:border-box;border:1px solid #cad9cf;border-radius:6px;background:white;padding:9px;margin:6px 0 12px;font:inherit;color:inherit}.course-profile fieldset{border:0;padding:0;margin:6px 0 12px}.course-profile legend{font-size:13px;margin-bottom:8px}.course-profile fieldset label{display:inline-flex;align-items:center;gap:5px;margin:5px 14px 5px 0}.course-profile input[type=checkbox]{accent-color:#286d4e}@media(max-width:550px){.profile-grid{grid-template-columns:1fr}}</style>
