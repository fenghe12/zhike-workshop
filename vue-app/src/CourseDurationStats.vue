<script setup lang="ts">
const props=defineProps<{value:any}>()
function time(value:any){if(value===null||value===undefined)return '未记录';const total=Math.round(value);return Math.floor(total/60)+' 分 '+String(total%60).padStart(2,'0')+' 秒'}
</script>
<template>
 <section v-if="props.value" class="duration-stats">
  <h3>MOOC 课程时长分布</h3><p class="duration-note">统计已生成课程视频的播放时长，每个语种单独计为一个版本。区间包含下限、不包含上限。</p>
  <div class="duration-cards"><article v-for="[label,key] in [['已生成版本','generatedVersions'],['时长已记录','samples'],['时长未记录','unrecordedVersions']]" :key="key"><b>{{props.value[key]}}</b><span>{{label}}</span></article><article v-for="[label,key] in [['总播放时长','totalSeconds'],['平均时长','averageSeconds'],['中位数','medianSeconds'],['P90','p90Seconds'],['最短','minimumSeconds'],['最长','maximumSeconds']]" :key="key"><b>{{time(props.value[key])}}</b><span>{{label}}</span></article></div>
  <div v-for="row in props.value.distribution" :key="row.key" class="duration-bar"><span>{{row.label}}</span><div><i :style="{width:row.percent+'%'}"></i></div><b>{{row.count}}</b><small>{{row.percent}}%</small></div>
 </section>
</template>
<style scoped>.duration-stats h3{margin:0 0 12px}.duration-note{font-size:13px;color:#6b8076;line-height:1.7}.duration-cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(135px,1fr));gap:10px;margin:14px 0 20px}.duration-cards article{padding:13px;border:1px solid #dce8e0;background:#f8fbf9;border-radius:9px}.duration-cards b,.duration-cards span{display:block}.duration-cards b{font-size:17px;color:#23664c;margin-bottom:7px}.duration-cards span{font-size:12px;color:#6b8076}.duration-bar{display:grid;grid-template-columns:125px 1fr 40px 50px;gap:9px;align-items:center;margin:11px 0;font-size:13px}.duration-bar>div{height:10px;background:#edf3ef;border-radius:8px;overflow:hidden}.duration-bar i{display:block;height:100%;background:#3a8d69;border-radius:8px}.duration-bar small{color:#7c8c83}@media(max-width:500px){.duration-bar{grid-template-columns:110px 1fr 25px 42px;font-size:12px;gap:5px}}</style>
