<script setup lang="ts">
import {t} from './ui-language'
import {computed,onMounted,ref,watch} from 'vue'
import {api,post} from './api'
import PolicyLinks from './PolicyLinks.vue'
import PasswordReset from './PasswordReset.vue'
const props=defineProps<{mode:'register'|'login';sessionUser?:any}>()
const emit=defineEmits<{authenticated:[value:any];mode:[value:string];logout:[]}>()
const values=ref({name:'',institution:'',account:'',password:'',confirmPassword:'',captchaCode:'',email:'',emailCode:''})
const resetMode=ref(false),emailEnabled=ref(false),emailMessage=ref('')
const policies=ref<any>(),captcha=ref<any>(),agreed=ref(false),busy=ref(false),error=ref(''),captchaBusy=ref(false),showPassword=ref(false)
const needsConsent=computed(()=>props.sessionUser&&(props.sessionUser.policyConsent?.version!==policies.value?.version||props.sessionUser.policyConsent?.termsAccepted!==true||props.sessionUser.policyConsent?.privacyAccepted!==true))
let captchaRequest=0
async function refreshCaptcha(){const id=++captchaRequest;captchaBusy.value=true;values.value.captchaCode='';try{const value=await api<any>('/v1/auth/captcha');if(id===captchaRequest)captcha.value=value}catch(e){if(id===captchaRequest)error.value=(e as Error).message}finally{if(id===captchaRequest)captchaBusy.value=false}}
watch(()=>props.mode,()=>{agreed.value=false;error.value='';values.value.password='';values.value.confirmPassword='';if(policies.value&&!props.sessionUser)void refreshCaptcha()})
watch(()=>props.sessionUser?.id,()=>{agreed.value=false;error.value='';values.value.password='';values.value.confirmPassword='';if(policies.value&&!props.sessionUser)void refreshCaptcha()})
async function submit(){
 if(busy.value||!policies.value)return
 error.value=''
 if(!agreed.value){error.value='请先阅读并同意用户协议和隐私说明。';return}
 if(!props.sessionUser&&(!captcha.value||!values.value.captchaCode.trim())){error.value='请填写图形验证码。';return}
 if(!props.sessionUser&&props.mode==='register'&&values.value.password!==values.value.confirmPassword){error.value='两次输入的密码不一致。';return}
 busy.value=true
 try{
  const agreement={termsAccepted:true,privacyAccepted:true,policyVersion:policies.value.version}
  const result=props.sessionUser?await post<any>('/v1/auth/consent',agreement):await post<any>('/v1/auth/'+props.mode,{...values.value,account:values.value.account.trim(),captchaId:captcha.value.id,...agreement})
  localStorage.setItem('smartcourse-known-browser','1');values.value.password='';values.value.confirmPassword='';emit('authenticated',result)
 }catch(e){error.value=(e as Error).message;if(!props.sessionUser)await refreshCaptcha()}finally{busy.value=false}
}
async function sendEmail(){if(!captcha.value||!values.value.captchaCode){error.value='请填写图形验证码。';return}busy.value=true;error.value='';try{await post('/v1/auth/email/request',{email:values.value.email,purpose:'register',captchaId:captcha.value.id,captchaCode:values.value.captchaCode});emailMessage.value='验证码已发送，10 分钟内有效。'}catch(e){error.value=(e as Error).message}finally{await refreshCaptcha();busy.value=false}}
onMounted(async()=>{try{const [policy,capabilities]=await Promise.all([api<any>('/v1/auth/policies'),api<any>('/v1/auth/capabilities')]);policies.value=policy;emailEnabled.value=capabilities.emailEnabled;if(!props.sessionUser)await refreshCaptcha()}catch(e){error.value=(e as Error).message}})
</script>
<template>
 <PasswordReset v-if="resetMode" @close="resetMode=false" @authenticated="emit('authenticated',$event)" />
 <section v-else class="account-card">
  <div v-if="!sessionUser" class="account-tabs" :aria-label="t('账号管理')"><button v-for="tab in ['register','login'] as const" :key="tab" type="button" :class="{selected:mode===tab}" :aria-current="mode===tab?'page':undefined" @click="emit('mode',tab)">{{t(tab==='register'?'注册':'登录')}}</button></div>
  <h2>{{sessionUser?(needsConsent?t("确认服务协议"):t("当前已登录")):mode==='register'?t("注册新用户"):t("登录工作台")}}</h2>
  <p class="account-intro">{{sessionUser?t("账号 ")+sessionUser.phone:t(mode==='register'?"创建账号，开始制作你的多语种课程。":"继续制作，管理你的课程与素材。")}}</p>
  <p v-if="!policies&&!error" class="account-loading">{{t("正在读取注册与隐私说明…")}}</p>
  <form v-else-if="!sessionUser||needsConsent" @submit.prevent="submit">
   <template v-if="!sessionUser">
    <div v-if="mode==='register'" class="account-identity"><label>{{t("姓名")}}<input v-model="values.name" autocomplete="name" maxlength="80" :placeholder='t("请输入姓名")' required></label><label>{{t("所属单位")}}<input v-model="values.institution" autocomplete="organization" maxlength="160" :placeholder='t("学校或所属单位")' required></label></div>
    <label>{{t("账号")}}<input v-model="values.account" autocomplete="username" autocapitalize="none" spellcheck="false" :placeholder='t("邮箱或自定义账号，至少 6 个字符")' minlength="6" maxlength="128" required></label>
    <label>{{t("密码")}}<span class="account-password"><input v-model="values.password" :type="showPassword?'text':'password'" :autocomplete="mode==='register'?'new-password':'current-password'" :placeholder='t("请输入密码，至少 6 位")' minlength="6" maxlength="128" required><button type="button" @click="showPassword=!showPassword">{{showPassword?t("隐藏"):t("显示")}}</button></span></label>
    <label v-if="mode==='register'">{{t("确认密码")}}<input v-model="values.confirmPassword" type="password" autocomplete="new-password" :placeholder='t("再次输入密码")' minlength="6" maxlength="128" required></label>
    <label>{{t("图形验证码")}}<span class="captcha-row"><input v-model="values.captchaCode" :aria-label='t("图形验证码")' autocomplete="off" autocapitalize="characters" maxlength="5" :placeholder='t("输入图中字母数字")' required><button type="button" class="captcha-image" :disabled="captchaBusy" :aria-label='t("刷新图形验证码")' @click="refreshCaptcha"><img v-if="captcha&&!captchaBusy" :src="captcha.image" :alt='t("图形验证码")'><span v-else>{{captchaBusy?t("正在刷新…"):t("点击获取")}}</span></button></span></label><p class="captcha-help">{{t("不区分大小写，5 分钟内有效。看不清可点击图片刷新。")}}</p>
    <template v-if="mode==='register'&&emailEnabled"><label>{{t('邮箱')}}<input v-model="values.email" type="email" autocomplete="email" required maxlength="254"></label><label>{{t('邮箱验证码')}}<span class="captcha-row"><input v-model="values.emailCode" inputmode="numeric" autocomplete="one-time-code" pattern="[0-9]{6}" maxlength="6" required><button type="button" :disabled="busy||!values.email||!values.captchaCode" @click="sendEmail">{{t('获取邮箱验证码')}}</button></span></label><p class="captcha-help">{{t(emailMessage||'先填写图形验证码，再获取邮箱验证码。')}}</p></template>
   </template>
   <p v-else class="account-intro">{{t("请阅读本次更新的说明，确认后继续使用。人物照片与声音的处理会在上传前单独确认。")}}</p>
   <div class="account-agreement"><label><input v-model="agreed" type="checkbox" required><span>{{t("我已阅读并同意用户协议和隐私说明")}}</span></label><PolicyLinks /></div>
   <p v-if="error" class="account-error" role="alert">{{t(error)}}</p><button class="account-submit" :disabled="busy||!policies||captchaBusy">{{busy?t("正在处理…"):sessionUser?t("同意并继续"):mode==='register'?t("注册并进入工作台"):t("登录并进入工作台")}}<svg v-if="!busy" viewBox="0 0 24 24" aria-hidden="true"><path d="M4 12h15m-6-6 6 6-6 6"/></svg></button>
  </form>
  <template v-else><p v-if="error" class="account-error" role="alert">{{t(error)}}</p><button class="account-submit" @click="emit('authenticated',{user:sessionUser})">{{t("进入我的工作台")}}</button></template>
  <p v-if="error&&!policies" class="account-error" role="alert">{{t(error)}}</p>
  <button v-if="sessionUser" type="button" class="account-switch" @click="emit('logout')">{{t("退出当前账号")}}</button>
  <button v-if="!sessionUser&&mode==='login'" type="button" class="account-switch" @click="resetMode=true">{{t('忘记密码？')}}</button>
 </section>
</template>
<style scoped>
.account-card{padding:0 12px;max-width:430px;margin:0 auto;color:#223e31}.account-tabs{display:flex;align-items:center;gap:24px;border-bottom:1px solid #e1e7df;margin-bottom:30px}.account-tabs button{background:none;border:0;border-bottom:2px solid transparent;color:#8b968c;font-size:13px;font-weight:550;padding:0 2px 13px;min-width:44px;cursor:pointer;margin-bottom:-1px}.account-tabs button.selected{color:#24503d;border-bottom-color:#24503d}.account-card h2{font-size:28px;letter-spacing:-.7px;line-height:1.35;font-weight:650;margin:0 0 9px;text-wrap:balance}.account-intro{color:#839085;font-size:12px;line-height:1.7;margin:0 0 25px}.account-card label{display:block;font-size:12px;line-height:1.5;font-weight:550;margin:0 0 17px;color:#405648}.account-identity{display:grid;grid-template-columns:1fr 1fr;gap:14px}.account-card input:not([type=checkbox]){display:block;box-sizing:border-box;width:100%;min-width:0;min-height:44px;margin-top:7px;background:#fff;border:1px solid #dce3d8;border-radius:8px;padding:11px 12px;font-size:13px;line-height:20px;color:#253f2f;outline:none;transition:border-color .15s,box-shadow .15s}.account-card input::placeholder{color:#adb5ac;font-size:12px;font-weight:400}.account-card input:focus{border-color:#3f795c;box-shadow:0 0 0 3px #d4e4d566}.account-password{display:flex;border:1px solid #dce3d8;border-radius:8px;background:#fff;margin-top:7px;transition:border-color .15s,box-shadow .15s}.account-password:focus-within{border-color:#3f795c;box-shadow:0 0 0 3px #d4e4d566}.account-password input:not([type=checkbox]){margin:0;border:0;background:none;flex:1;box-shadow:none}.account-password button{background:none;border:0;padding:0 12px;color:#6e8473;font-size:11px;cursor:pointer;flex-shrink:0;max-width:110px;overflow-wrap:anywhere}.captcha-row{display:flex;gap:10px;align-items:center}.captcha-row input:not([type=checkbox]){flex:1;width:0}.captcha-image{padding:0;width:122px;height:44px;flex-shrink:0;border:1px solid #dce3d8;background:#edf3e9;border-radius:7px;margin-top:7px;overflow:hidden;color:#637c67;cursor:pointer}.captcha-image img{display:block;width:100%;height:100%;object-fit:contain}.captcha-help{color:#9aa496;font-size:10px;line-height:1.6;margin:-8px 0 19px}.account-agreement{padding:0;margin:21px 0}.account-agreement label{display:flex;align-items:flex-start;gap:8px;line-height:1.65;font-size:11px;margin:0 0 6px;color:#74836f;font-weight:400}.account-agreement input[type=checkbox]{display:block;width:15px;height:15px;min-height:15px;flex-shrink:0;margin:2px 0 0;accent-color:#24543d;padding:0;border-radius:3px}.account-agreement :deep(.policy-links){font-size:10px;margin-left:23px;display:block;line-height:1.7}.account-agreement :deep(.policy-links button){color:#6b826c;text-decoration:none}.account-agreement :deep(.policy-links button:hover){text-decoration:underline}.account-submit{display:flex;align-items:center;justify-content:center;gap:14px;width:100%;min-height:45px;padding:12px 16px;background:#214f3c;color:#fff;border:1px solid #214f3c;border-radius:8px;font:inherit;font-size:12px;font-weight:550;cursor:pointer;transition:background .15s,transform .15s;box-shadow:0 3px 7px #1b382710}.account-submit:hover{background:#173f2f}.account-submit:active{transform:translateY(1px)}.account-submit>svg{height:15px;width:15px;fill:none;stroke:currentColor;stroke-width:1.5}.account-submit:disabled{opacity:.55;cursor:wait}.account-switch{display:block;margin:18px auto 0;border:0;background:none;color:#356646;font-size:12px;font-weight:550;padding:5px;cursor:pointer}.account-error{padding:10px 12px;background:#fff0ec;color:#9d4436;border-radius:8px;font-size:12px;line-height:1.7;margin:12px 0}.account-loading{font-size:13px;color:#728578}
@media(max-width:959px){.account-card{padding:0;max-width:none}.account-tabs{margin-bottom:27px}.account-card h2{font-size:27px}.account-intro{margin-bottom:25px}.account-card input:not([type=checkbox]){font-size:16px}.account-card input::placeholder{font-size:12px}.account-footer{margin-bottom:20px}}
@media(prefers-reduced-motion:reduce){.account-card input,.account-password,.account-submit{transition:none}}
</style>
