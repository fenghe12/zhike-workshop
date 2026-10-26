<script setup lang="ts">
defineProps<{compact?:boolean}>()
</script>
<template><span class="workshop-logo" :class="{compact}"><img src="/brand/smartcourse-logo-transparent.png" alt="智课工坊" width="160" height="160"></span></template>
<style scoped>
.workshop-logo{position:relative;display:block;width:160px;height:160px;margin:0 auto 15px;flex-shrink:0}.workshop-logo img{display:block;width:100%;height:100%;object-fit:contain}.workshop-logo.compact{width:42px;height:42px;margin:0;overflow:hidden}.compact img{position:absolute;width:145%;height:145%;max-width:none;left:-22%;top:-6%;clip-path:inset(0 0 34% 0)}
</style>
