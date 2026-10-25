<script setup lang="ts">
import {computed} from 'vue'
import type {Task} from './api'
const props=defineProps<{task:Task}>()
const message=computed(()=>{
 if(props.task.status==='queued'&&props.task.queue?.position)
  return `任务已排队，前方还有 ${props.task.queue.position-1} 个待执行任务。页面会自动更新。`
 if(props.task.queue?.state==='waiting_resource')
  return `${props.task.queue.message||'正在等待计算资源'}，其他课程仍可继续处理。`
 return ''
})
</script>

<template>
 <el-alert v-if="message" :title="message" type="info" show-icon :closable="false" style="margin-bottom:16px"/>
</template>
