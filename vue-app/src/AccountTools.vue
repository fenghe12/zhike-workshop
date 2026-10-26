<script setup lang="ts">
import {onMounted,ref} from 'vue'
import {api,post} from './api'
import {t} from './ui-language'
const props=defineProps<{user:any}>(),emit=defineEmits<{updated:[value:any]}>()
const enabled=ref(false),busy=ref(false),message=ref(''),error=ref(''),email=ref(props.user?.email||''),code=ref('')
const currentPassword=ref(''),password=ref(''),confirmPassword=ref('')
onMounted(async()=>{try{enabled.value=(await api<any>('/v1/auth/capabilities')).emailEnabled}catch{}})
async function perform(action:()=>Promise<void>){if(busy.value)return;busy.value=true;error.value='';message.value='';try{await action()}catch(e){error.value=(e as Error).message}finally{busy.value=false}}
function send(){void perform(async()=>{await post('/v1/auth/email/request',{email:email.value,purpose:'bind'});message.value='验证码已发送，10 分钟内有效。'})}
function bind(){void perform(async()=>{const result=await post<any>('/v1/auth/email/confirm',{email:email.value,code:code.value});emit('updated',result);code.value='';message.value='邮箱验证完成。'})}
function change(){void perform(async()=>{const result=await post<any>('/v1/auth/password/change',{currentPassword:currentPassword.value,password:password.value,confirmPassword:confirmPassword.value});emit('updated',result);currentPassword.value='';password.value='';confirmPassword.value='';message.value='密码已修改，其他登录会话已退出。'})}
</script>
<template>
 <section class="account-tools">
  <p v-if="message" role="status">{{t(message)}}</p><p v-if="error" class="tool-error" role="alert">{{t(error)}}</p>
  <details><summary>{{t('修改密码')}}</summary><form @submit.prevent="change"><label>{{t('当前密码')}}<input v-model="currentPassword" type="password" autocomplete="current-password" required maxlength="128"></label><label>{{t('新密码')}}<input v-model="password" type="password" autocomplete="new-password" minlength="6" maxlength="128" required></label><label>{{t('确认密码')}}<input v-model="confirmPassword" type="password" autocomplete="new-password" minlength="6" maxlength="128" required></label><button :disabled="busy">{{t('保存新密码')}}</button></form></details>
  <details><summary>{{t('验证邮箱')}}</summary><p v-if="user.emailVerifiedAt">{{user.email}} · {{t('已验证')}}</p><p v-if="!enabled">{{t('邮箱服务暂未启用，请联系项目管理员。')}}</p><form v-else @submit.prevent="bind"><label>{{t('邮箱')}}<input v-model="email" type="email" autocomplete="email" maxlength="254" required></label><button type="button" :disabled="busy" @click="send">{{t('获取邮箱验证码')}}</button><label>{{t('邮箱验证码')}}<input v-model="code" inputmode="numeric" autocomplete="one-time-code" pattern="[0-9]{6}" maxlength="6" required></label><button :disabled="busy">{{t('验证并绑定')}}</button></form></details>
 </section>
</template>
<style scoped>
.account-tools details{border-bottom:1px solid #e5ece7;padding:12px 0}.account-tools summary{font-size:13px;cursor:pointer;color:#315641}.account-tools p{font-size:12px;line-height:1.7;color:#54745e;margin:10px 0}.account-tools .tool-error{color:#a14c3f}.account-tools label{display:block;font-size:12px;color:#617467;margin:12px 0}.account-tools input{display:block;box-sizing:border-box;width:100%;margin-top:6px;padding:10px;border:1px solid #dce5de;border-radius:7px;font-size:16px}.account-tools button{padding:10px 13px;color:#fff;background:#24543d;border:0;border-radius:7px;font:inherit;font-size:12px;cursor:pointer}.account-tools button:disabled{opacity:.5}
</style>
