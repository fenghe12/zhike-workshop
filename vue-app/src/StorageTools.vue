<script setup lang="ts">
import {onMounted,ref} from 'vue'
import {api} from './api'
import {t} from './ui-language'
const settings=ref({retentionDays:0,maxTaskBudgetCny:10}),assets=ref<any[]>([]),busy=ref(false),message=ref(''),error=ref('')
async function load(){const [preferences,files]=await Promise.all([api<typeof settings.value>('/v1/settings/storage'),api<any[]>('/v1/uploads')]);settings.value=preferences;assets.value=files}
onMounted(async()=>{try{await load()}catch(e){error.value=(e as Error).message}})
async function save(){if(settings.value.retentionDays&&!window.confirm(t('到期课程和未引用素材将自动删除，是否保存保留期限？')))return;busy.value=true;error.value='';try{settings.value=await api<typeof settings.value>('/v1/settings/storage',{method:'PUT',body:JSON.stringify(settings.value)});message.value='保留期限和预算已保存。'}catch(e){error.value=(e as Error).message}finally{busy.value=false}}
async function remove(asset:any){if(!window.confirm(t('确认删除此素材文件？')))return;busy.value=true;error.value='';try{await api('/v1/uploads/'+asset.id,{method:'DELETE'});await load();message.value='素材文件已删除。'}catch(e){error.value=(e as Error).message}finally{busy.value=false}}
</script>
<template>
 <section class="storage-tools"><label>{{t('课程和素材保留期限')}}<select v-model.number="settings.retentionDays"><option :value="0">{{t('永久保留')}}</option><option v-for="days in [7,30,90]" :key="days" :value="days">{{days}} {{t('天')}}</option></select></label><p>{{t('默认永久保留。选择期限后，已结束课程与未引用素材到期自动删除；恢复备份单独保留。')}}</p><label>{{t('单任务计算预算（元）')}}<input v-model.number="settings.maxTaskBudgetCny" type="number" min="0.1" max="50" step="0.1"></label><button :disabled="busy" @click="save">{{t('保存存储与预算设置')}}</button><p v-if="message" role="status">{{t(message)}}</p><p v-if="error" class="storage-error" role="alert">{{t(error)}}</p><details><summary>{{t('我的上传素材')}} · {{assets.length}}</summary><ul><li v-for="asset in assets" :key="asset.id"><span>{{asset.name}}<small>{{(asset.size/1024/1024).toFixed(2)}} MB</small></span><button :disabled="busy" @click="remove(asset)">{{t('删除')}}</button></li></ul></details></section>
</template>
<style scoped>
.storage-tools h3{font-size:14px}.storage-tools label{display:flex;align-items:center;justify-content:space-between;gap:10px;font-size:12px;margin:14px 0}.storage-tools select,.storage-tools input{width:125px;max-width:45%;border:1px solid #dce5df;border-radius:6px;padding:8px;background:white;color:#315641;font-size:14px}.storage-tools p{font-size:11px;line-height:1.8;color:#75867b;margin:12px 0}.storage-tools button{padding:9px 12px;background:#24543d;color:white;border:0;border-radius:6px;font-size:12px;cursor:pointer}.storage-tools button:disabled{opacity:.5}.storage-tools details{margin-top:20px;font-size:12px}.storage-tools summary{cursor:pointer}.storage-tools ul{padding:0;list-style:none}.storage-tools li{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:12px 0;border-bottom:1px solid #edf1ee}.storage-tools li span{overflow-wrap:anywhere;min-width:0}.storage-tools small{display:block;margin-top:4px;color:#8c9a90}.storage-tools .storage-error{color:#9b453b}
</style>
