<script setup lang="ts">
import {t,policyText} from './ui-language'
import {ref,onMounted} from 'vue'
import {api} from './api'
const props=defineProps<{mediaOnly?:boolean}>()
const documents=ref<any>(),selected=ref<any>(),selectedKey=ref(''),dialog=ref<HTMLDialogElement>(),error=ref('')
async function show(kind:string){try{if(!documents.value)documents.value=await api<any>('/v1/auth/policies');selectedKey.value=kind;selected.value=documents.value.documents[kind];dialog.value?.showModal()}catch(e){error.value=(e as Error).message}}
</script>
<template>
 <span class="policy-links"><template v-if="!props.mediaOnly"><button type="button" @click="show('terms')">{{t("用户协议")}}</button><span> · </span><button type="button" @click="show('privacy')">{{t("隐私说明")}}</button><span> · </span></template><button type="button" @click="show('media')">{{t("人物与声音处理说明")}}</button></span>
 <p v-if="error" class="policy-error" role="alert">{{t(error)}}</p>
 <dialog ref="dialog" class="policy-dialog" @click="$event.target===dialog&&dialog?.close()"><template v-if="selected"><header><strong>{{t(selected.title)}}</strong><button type="button" :aria-label='t("关闭说明")' @click="dialog?.close()">×</button></header><div class="policy-copy"><p class="policy-version">{{t("版本")}} {{documents.version}}</p><section v-for="(item,index) in selected.sections" :key="item.title"><h3>{{t(item.title)}}</h3><p>{{policyText(selectedKey,index,item.text)}}</p></section><button type="button" class="policy-close" @click="dialog?.close()">{{t("返回")}}</button></div></template></dialog>
</template>
<style scoped>
.policy-links{display:inline;font-size:12px;line-height:1.9}.policy-links button{border:0;background:none;color:#176b5b;padding:0;font:inherit;text-decoration:underline;text-underline-offset:3px;cursor:pointer}.policy-links span{color:#9aa99e}.policy-error{font-size:12px;color:#a04334}.policy-dialog{width:min(92vw,640px);max-height:85dvh;border:1px solid #dbe6df;border-radius:14px;padding:0;color:#273e32;overflow:auto;background:white}.policy-dialog::backdrop{background:#14251c88}.policy-dialog header{display:flex;position:sticky;top:0;background:white;align-items:center;justify-content:space-between;padding:14px 20px;border-bottom:1px solid #e7eee9}.policy-dialog header button{font-size:27px;border:0;background:none;color:#61756a;cursor:pointer}.policy-copy{padding:20px}.policy-version{font-size:12px;color:#859488}.policy-copy section{margin:20px 0}.policy-copy h3{font-size:15px;margin:0 0 8px;color:#223e2e}.policy-copy p{font-size:13px;line-height:1.9;margin:0}.policy-close{display:block;width:100%;border:0;background:#176b5b;color:white;border-radius:9px;padding:12px;font:inherit;cursor:pointer}
</style>
