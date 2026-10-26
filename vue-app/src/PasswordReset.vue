<script setup lang="ts">
import {onMounted,ref} from 'vue'
import {api,post} from './api'
import {t} from './ui-language'
const emit=defineEmits<{close:[];authenticated:[value:any]}>()
const email=ref(''),code=ref(''),password=ref(''),confirmPassword=ref(''),captchaCode=ref(''),captcha=ref<any>(),enabled=ref(false),busy=ref(false),error=ref(''),message=ref('')
async function refresh(){captcha.value=await api<any>('/v1/auth/captcha');captchaCode.value=''}
onMounted(async()=>{try{enabled.value=(await api<any>('/v1/auth/capabilities')).emailEnabled;if(enabled.value)await refresh()}catch(e){error.value=(e as Error).message}})
async function send(){if(busy.value)return;busy.value=true;error.value='';try{await post('/v1/auth/email/request',{email:email.value,purpose:'reset',captchaId:captcha.value?.id,captchaCode:captchaCode.value});message.value='若该邮箱已验证，将收到验证码。';await refresh()}catch(e){error.value=(e as Error).message;await refresh()}finally{busy.value=false}}
async function submit(){if(busy.value)return;busy.value=true;error.value='';try{emit('authenticated',await post('/v1/auth/password/reset',{email:email.value,code:code.value,password:password.value,confirmPassword:confirmPassword.value}));password.value='';confirmPassword.value=''}catch(e){error.value=(e as Error).message}finally{busy.value=false}}
</script>
<template>
 <section class="reset-card"><h2>{{t('找回密码')}}</h2><p>{{t('使用已验证的邮箱重设密码。')}}</p><p v-if="!enabled">{{t('邮箱服务暂未启用，请联系项目管理员。')}}</p>
  <form v-else @submit.prevent="submit"><label>{{t('邮箱')}}<input v-model="email" type="email" autocomplete="email" required></label><label>{{t('图形验证码')}}<span class="reset-row"><input v-model="captchaCode" maxlength="5" autocomplete="off"><button type="button" @click="refresh"><img v-if="captcha" :src="captcha.image" :alt="t('刷新图形验证码')"></button></span></label><button type="button" :disabled="busy||!email||!captchaCode" @click="send">{{t('获取邮箱验证码')}}</button><label>{{t('邮箱验证码')}}<input v-model="code" inputmode="numeric" autocomplete="one-time-code" pattern="[0-9]{6}" maxlength="6" required></label><label>{{t('新密码')}}<input v-model="password" type="password" autocomplete="new-password" minlength="6" maxlength="128" required></label><label>{{t('确认密码')}}<input v-model="confirmPassword" type="password" autocomplete="new-password" minlength="6" maxlength="128" required></label><button :disabled="busy">{{t('重设密码并登录')}}</button></form>
  <p v-if="message" role="status">{{t(message)}}</p><p v-if="error" class="reset-error" role="alert">{{t(error)}}</p><button type="button" class="reset-back" @click="emit('close')">{{t('返回登录')}}</button>
 </section>
</template>
<style scoped>
.reset-card{max-width:430px;margin:auto;color:#264b36}.reset-card h2{font-size:27px}.reset-card p{font-size:12px;line-height:1.8;color:#718575;margin:12px 0}.reset-card label{display:block;font-size:12px;margin:14px 0}.reset-card input{display:block;box-sizing:border-box;width:100%;min-width:0;padding:11px;border:1px solid #dce5de;border-radius:8px;margin-top:6px;font-size:16px}.reset-card button{padding:11px 15px;background:#24543d;color:white;border:0;border-radius:7px;cursor:pointer}.reset-card button:disabled{opacity:.5}.reset-row{display:flex;align-items:center;gap:10px}.reset-row input{flex:1;width:0}.reset-row button{padding:0;background:none}.reset-row img{width:122px;height:44px;object-fit:contain}.reset-card .reset-back{display:block;margin:20px auto;background:none;color:#24543d}.reset-card .reset-error{color:#9b453b}
</style>
