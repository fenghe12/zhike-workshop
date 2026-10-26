<script setup lang="ts">
import {onMounted,onUnmounted,ref} from 'vue'
import {api,post} from './api'
import {t} from './ui-language'
const status=ref<any>(),busy=ref(false),message=ref(''),error=ref('')
let timer:ReturnType<typeof setInterval>|undefined
async function refresh(){try{status.value=await api('/v1/compute/status')}catch{}}
onMounted(()=>{void refresh();timer=setInterval(refresh,20000)})
onUnmounted(()=>{if(timer)clearInterval(timer)})
async function requestStart(){busy.value=true;error.value='';try{await post('/v1/compute/request',{});message.value='启动请求已提交，准备完成后可开始生成。';await refresh()}catch(e){error.value=(e as Error).message}finally{busy.value=false}}
</script>
<template><div class="compute-panel"><p>{{t('生成服务按需启动；空闲或到达预算期限后自动停止。')}}</p><button v-if="status?.status!=='RUNNING'" :disabled="busy||!status?.controllerAvailable" @click="requestStart">{{t('申请启动生成服务')}}</button><p v-if="status&&!status.controllerAvailable&&status.status!=='RUNNING'">{{t('生成服务暂未开放启动，请联系项目管理员。')}}</p><p v-if="message" role="status">{{t(message)}}</p><p v-if="error" role="alert">{{t(error)}}</p></div></template>
<style scoped>.compute-panel{border-top:1px solid #edf1ee;padding-top:10px;margin-top:12px}.compute-panel p{font-size:11px;line-height:1.8;color:#75867b;margin:8px 0}.compute-panel button{background:#24543d;border:0;border-radius:6px;padding:10px 12px;color:white;font-size:12px;cursor:pointer}.compute-panel button:disabled{opacity:.45;cursor:default}</style>
