<script setup lang="ts">
import {computed,ref} from 'vue'

type Page={page_id:number;title?:string;script_text?:string;key_points?:string[];layout?:{regions?:{text?:string}[]}}
type Timeline={page_id:number;start_time?:number;end_time?:number;start?:number;end?:number}
const props=defineProps<{pages?:Page[];timeline?:{pages?:Timeline[]};media?:HTMLVideoElement}>()
const query=ref('')
const keywordAliases:Record<string,string[]>={
 '权重':['weight','weights','가중치','重み','poids'],
 '阈值':['threshold','임계값','しきい値','seuil'],
 '反向传播':['backpropagation','back propagation','역전파','誤差逆伝播'],
 '激活函数':['activation function','활성화 함수','活性化関数'],
}
const searchablePages=computed(()=>{
 const pages=new Map<number,Page>()
 for(const page of props.pages||[]) {
  const previous=pages.get(page.page_id)
  if(!previous){pages.set(page.page_id,{...page});continue}
  pages.set(page.page_id,{...previous,
   title:previous.title||page.title,
   script_text:[previous.script_text,page.script_text].filter(Boolean).join(' '),
   key_points:[...(previous.key_points||[]),...(page.key_points||[])],
   layout:previous.layout||page.layout})
 }
 return [...pages.values()]
})
const results=computed(()=>{
 const value=query.value.trim().toLocaleLowerCase()
 if(!value)return []
 const needles=[value,...(keywordAliases[value]||[])].map(item=>item.toLocaleLowerCase())
 return searchablePages.value.flatMap(page=>{
 const regions=(page.layout?.regions||[]).map(region=>region.text||'')
 const haystack=[page.title||'',page.script_text||'',...(page.key_points||[]),...regions].join(' ')
 const lowerHaystack=haystack.toLocaleLowerCase()
 const matched=needles.find(item=>lowerHaystack.includes(item))
 if(!matched)return []
 const matchIndex=lowerHaystack.indexOf(matched)
  const snippet=haystack.slice(Math.max(0,matchIndex-36),Math.min(haystack.length,matchIndex+96))
  const time=props.timeline?.pages?.find(item=>item.page_id===page.page_id)
  return [{page,snippet,time}]
 })
})
function jump(item:{time?:Timeline;page:Page}){
 const start=Number(item.time?.start_time??item.time?.start)
 if(!Number.isFinite(start)||!props.media)return
 props.media.currentTime=start
 props.media.play().catch(()=>{})
}
function format(value?:number){return Number.isFinite(value)?`${Math.floor(Number(value)/60)}:${Math.floor(Number(value)%60).toString().padStart(2,'0')}`:'—'}
</script>
<template>
 <section class="course-search">
  <div class="search-heading"><div><h3>课程内搜索定位</h3><p>搜索讲稿、页面标题和教学要点，点击结果跳到对应视频位置。</p></div><el-input v-model="query" clearable placeholder="例如：权重、反向传播、阈值" class="search-input"/></div>
  <el-empty v-if="query.trim()&&!results.length" description="没有匹配内容"/>
  <div v-else-if="results.length" class="search-results">
   <button v-for="item in results" :key="item.page.page_id" class="search-result" @click="jump(item)">
    <span class="result-page">第 {{item.page.page_id}} 页 · {{format(item.time?.start_time??item.time?.start)}}</span>
    <strong>{{item.page.title||'未命名页面'}}</strong>
    <span>{{item.snippet}}</span>
   </button>
  </div>
 </section>
</template>
<style scoped>
.course-search{margin:24px 0;padding:20px;border:1px solid #dce7df;border-radius:12px;background:#fbfdfb}.search-heading{display:flex;justify-content:space-between;align-items:end;gap:20px}.search-heading h3{margin:0 0 6px}.search-heading p{margin:0;color:#75877e;font-size:13px}.search-input{max-width:360px}.search-results{display:grid;gap:8px;margin-top:16px}.search-result{display:grid;gap:5px;text-align:left;padding:12px 14px;border:1px solid #dfe9e2;border-radius:9px;background:white;color:#23463a;cursor:pointer}.search-result:hover{border-color:#42a77b;background:#f2faf5}.search-result .result-page{color:#168763;font-size:12px}.search-result strong{font-size:14px}.search-result>span:last-child{color:#64776b;font-size:13px;line-height:1.55}@media(max-width:760px){.search-heading{display:block}.search-input{max-width:none;margin-top:12px}}
</style>
