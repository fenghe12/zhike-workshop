<script setup lang="ts">
import {computed,onMounted,ref} from 'vue'
import {useRouter} from 'vue-router'
import {api,post} from './api'
import VoicePicker from './VoicePicker.vue'
import TeacherPhotoInput from './TeacherPhotoInput.vue'

type Lesson={lessonId:string;subject:string;topic:string;grade:string}
const router=useRouter()
const lessons=ref<Lesson[]>([])
const languages=[
  {name:'中文',code:'zh-CN'},{name:'英语',code:'en-US'},
  {name:'日语',code:'ja-JP'},{name:'韩语',code:'ko-KR'},
  {name:'德语',code:'de-DE'},{name:'法语',code:'fr-FR'},
]
const selected=ref('')
const sourceType=ref<'custom'|'catalog'>('custom')
const codeText=ref('')
const codeLanguage=ref('Python')
const sourceLanguage=ref('中文')
const pageCount=ref(3)
const audience=ref('初学者')
const targetLanguages=ref<string[]>(['中文'])
const name=ref('')
const voiceId=ref('default')
const teacherImageUrl=ref('')
const referenceAudioUrl=ref('')
const audioBusy=ref(false)
const submitting=ref(false)
const error=ref('')
const chosen=computed(()=>lessons.value.find(item=>item.lessonId===selected.value))
onMounted(async()=>{
  try{lessons.value=await api<Lesson[]>('/v1/code-lessons')}
  catch(e){error.value=(e as Error).message}
})
async function uploadAudio(event:Event){
  const input=event.target as HTMLInputElement
  const file=input.files?.[0]
  if(!file)return
  error.value=''
  if(!/\.(wav|mp3|m4a|flac|ogg)$/i.test(file.name)||file.size>20*1024*1024){
    error.value='请选择不超过 20 MB 的 WAV、MP3、M4A、FLAC 或 OGG 音频。'
    input.value=''
    return
  }
  audioBusy.value=true
  try{
    const contentBase64=await new Promise<string>((resolve,reject)=>{
      const reader=new FileReader()
      reader.onload=()=>resolve(String(reader.result).split(',')[1]!)
      reader.onerror=reject
      reader.readAsDataURL(file)
    })
    const uploaded=await post<{path:string}>('/v1/uploads',{filename:file.name,kind:'audio',contentBase64})
    referenceAudioUrl.value=uploaded.path
  }catch(e){error.value=(e as Error).message}
  finally{audioBusy.value=false;input.value=''}
}
async function submit(){
  error.value=''
  if(sourceType.value==='catalog'&&!selected.value){error.value='请选择示例动画课程。';return}
  if(sourceType.value==='custom'&&!codeText.value.trim()){error.value='请粘贴待讲解代码。';return}
  if(sourceType.value==='custom'&&codeText.value.length>30000){error.value='待讲解代码不能超过 30000 字符。';return}
  if(!targetLanguages.value.length){error.value='请至少选择一种输出语言。';return}
  if(!sessionStorage.getItem('smartcourse-token')){error.value='请先登录，再创建课程。';return}
  submitting.value=true
  try{
    const result=await post<{jobId:string}>('/api/courses',{
      name:name.value.trim()||(sourceType.value==='catalog'?chosen.value?.topic:'代码讲解课程'),
      mode:'code',sourceLanguage:sourceType.value==='custom'?sourceLanguage.value:'中文',
      ...(sourceType.value==='catalog'?{lessonId:selected.value}:{codeText:codeText.value,
        codeLanguage:codeLanguage.value,totalPages:pageCount.value,targetLearners:audience.value}),
      targetLanguages:targetLanguages.value,voiceId:voiceId.value,
      teacherImageUrl:teacherImageUrl.value,referenceAudioUrl:referenceAudioUrl.value,
    })
    await router.push('/task?id='+encodeURIComponent(result.jobId))
  }catch(e){error.value=(e as Error).message}
  finally{submitting.value=false}
}
</script>

<template>
  <div class="heading"><div><p class="eyebrow">CODE COURSE</p><h1>代码讲解与动画</h1><p>粘贴自己的代码生成逐页讲解，或选用示例动画课程。</p></div></div>
  <section class="panel code-lesson-create">
    <el-alert v-if="error" :title="error" type="warning" :closable="false"/>
    <el-form label-position="top">
      <el-radio-group v-model="sourceType" class="source-mode"><el-radio-button value="custom">讲解我的代码</el-radio-button><el-radio-button value="catalog">示例动画课程</el-radio-button></el-radio-group>
      <template v-if="sourceType==='custom'">
        <el-form-item label="待讲解代码" required><el-input v-model="codeText" type="textarea" :rows="12" maxlength="30000" show-word-limit placeholder="粘贴需要讲解的代码。系统只读取代码文本，不执行代码。"/></el-form-item>
        <el-form-item label="编程语言"><el-input v-model="codeLanguage" maxlength="80" placeholder="例如 Python、JavaScript"/></el-form-item>
        <el-form-item label="讲解源语言"><el-select v-model="sourceLanguage"><el-option v-for="language in languages" :key="language.code" :value="language.name" :label="language.name"/></el-select></el-form-item>
        <el-form-item label="教学对象"><el-input v-model="audience" maxlength="120"/></el-form-item>
        <el-form-item label="讲解页数"><el-input-number v-model="pageCount" :min="1" :max="10"/></el-form-item>
      </template>
      <template v-else>
        <el-form-item label="示例课程" required><el-select v-model="selected" filterable placeholder="选择课程主题" style="width:100%"><el-option v-for="lesson in lessons" :key="lesson.lessonId" :label="`${lesson.subject} · ${lesson.topic}`" :value="lesson.lessonId"/></el-select></el-form-item>
        <p v-if="chosen" class="lesson-description">{{chosen.grade}} · {{chosen.subject}} · {{chosen.topic}}</p>
      </template>
      <el-form-item label="任务名称"><el-input v-model="name" :placeholder="sourceType==='catalog'?chosen?.topic:'输入便于辨认的名称'" maxlength="120"/></el-form-item>
      <el-form-item label="输出语种" required>
        <el-checkbox-group v-model="targetLanguages">
          <el-checkbox v-for="language in languages" :key="language.code" :value="language.name">{{language.name}}</el-checkbox>
        </el-checkbox-group>
      </el-form-item>
      <VoicePicker v-model="voiceId"/>
      <div class="custom-audio"><strong>自定义参考声音（可选）</strong><p>上传后优先使用这段声音，且仅关联当前任务。</p><input type="file" accept="audio/*" :disabled="audioBusy" @change="uploadAudio"/><span v-if="referenceAudioUrl">已上传参考声音</span></div>
      <TeacherPhotoInput v-model="teacherImageUrl"/>
      <el-button type="primary" size="large" :loading="submitting" :disabled="audioBusy" @click="submit">创建并启动任务</el-button>
    </el-form>
  </section>
</template>

<style scoped>
.code-lesson-create{max-width:840px}.source-mode{margin-bottom:20px}.lesson-description{margin:-8px 0 20px;color:#64776b}
.custom-audio{margin:20px 0}.custom-audio strong{display:block;margin-bottom:6px}.custom-audio p{color:#64776b;font-size:13px}
.custom-audio span{display:block;margin-top:8px;color:#1b7952}
</style>
