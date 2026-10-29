<script setup lang="ts">
import {computed,useAttrs} from 'vue'
import AiInputAssist from './AiInputAssist.vue'
defineOptions({inheritAttrs:false})
const props=defineProps<{modelValue?:string;multiline?:boolean;assistLabel?:string;assistPurpose?:string;assistCourseId?:string;assistPage?:number;assistLanguage?:string;assistContext?:Record<string,unknown>}>()
const emit=defineEmits<{'update:modelValue':[value:string]}>()
const attrs=useAttrs()
const locked=computed(()=>[attrs.readonly,attrs.disabled].some(x=>x!==undefined&&x!==false))
const maximum=computed(()=>Number(attrs.maxlength)||Number(attrs.maxLength)||4000)
</script>
<template>
 <span class="assisted-field">
  <textarea v-if="multiline" v-bind="attrs" :value="modelValue||''" @input="emit('update:modelValue',($event.target as HTMLTextAreaElement).value)"/>
  <input v-else v-bind="attrs" :value="modelValue||''" @input="emit('update:modelValue',($event.target as HTMLInputElement).value)">
  <AiInputAssist v-if="!locked" :model-value="modelValue" :label="assistLabel" :purpose="assistPurpose" :course-id="assistCourseId" :page="assistPage" :language="assistLanguage" :context="assistContext" :max-length="maximum" @update:model-value="emit('update:modelValue',$event)"/>
 </span>
</template>
<style scoped>.assisted-field{display:inline-block;width:100%;min-width:0;vertical-align:top}.assisted-field>textarea,.assisted-field>input{display:block;box-sizing:border-box;width:100%;font:inherit;font-size:15px;line-height:1.65;color:#254d38;border:1px solid #cbdccf;border-radius:7px;background:#fff;padding:9px 11px;outline:none}.assisted-field>textarea{resize:vertical;min-height:70px}.assisted-field>textarea:focus,.assisted-field>input:focus{border-color:#478664;box-shadow:0 0 0 2px #e4f1e8}.assisted-field>textarea:disabled,.assisted-field>input:disabled{background:#f2f5f3;color:#778b7d}</style>
