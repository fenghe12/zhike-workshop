<script setup lang="ts">
import {onBeforeUnmount,ref,watch,nextTick} from 'vue'
const props=defineProps<{src:string}>()
const emit=defineEmits<{seek:[seconds:number]}>()
const canvas=ref<HTMLCanvasElement>(),duration=ref(0),error=ref(''),busy=ref(false)
let generation=0
watch(()=>props.src,async src=>{
 const current=++generation;error.value='';duration.value=0
 if(!src)return
 busy.value=true
 let context:AudioContext|undefined
 try{
  const response=await fetch(src);if(!response.ok)throw Error('无法读取音频')
  context=new AudioContext();const audio=await context.decodeAudioData(await response.arrayBuffer())
  if(current!==generation)return
  duration.value=audio.duration;await nextTick()
  const element=canvas.value;if(!element)return
  const drawing=element.getContext('2d');if(!drawing)return
  const samples=audio.getChannelData(0);drawing.clearRect(0,0,element.width,element.height)
  drawing.fillStyle='#138b69'
  const columns=160,chunk=Math.max(1,Math.floor(samples.length/columns))
  for(let column=0;column<columns;column++){
   let peak=0;for(let i=column*chunk;i<Math.min(samples.length,(column+1)*chunk);i++)peak=Math.max(peak,Math.abs(samples[i]!))
   const height=Math.max(1,peak*(element.height-8));drawing.fillRect(column*5,(element.height-height)/2,3,height)
  }
 }catch(e){if(current===generation)error.value=(e as Error).message}
 finally{await context?.close();if(current===generation)busy.value=false}
},{immediate:true})
function seek(event:MouseEvent){if(!duration.value||!canvas.value)return;const bounds=canvas.value.getBoundingClientRect();emit('seek',Math.max(0,Math.min(1,(event.clientX-bounds.left)/bounds.width))*duration.value)}
onBeforeUnmount(()=>generation++)
</script>
<template><div class="audio-wave"><p v-if="busy" class="muted">正在读取音频波形…</p><p v-if="error" class="muted">{{error}}</p><canvas ref="canvas" width="800" height="86" aria-label="实际音频波形，点击跳转播放位置" @click="seek"/><small class="muted">{{duration?duration.toFixed(2)+' 秒 · 点击波形定位播放':'音频加载后显示实际波形'}}</small></div></template>
<style scoped>.audio-wave{padding:12px;background:#f3f8f5;border-radius:12px}.audio-wave canvas{display:block;width:100%;height:86px;cursor:pointer}</style>
