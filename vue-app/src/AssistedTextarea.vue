<script setup lang="ts">
import AssistedField from './AssistedField.vue'
defineOptions({inheritAttrs:false})
const value=defineModel<string>()
</script>
<template><AssistedField v-bind="$attrs" v-model="value" multiline/></template>
