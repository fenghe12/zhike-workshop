import {createApp} from 'vue'
import {createRouter,createWebHashHistory} from 'vue-router'
import MobileApp from './MobileApp.vue'
import AssistedInput from './AssistedInput.vue'
import AssistedTextarea from './AssistedTextarea.vue'
import ElementPlus from 'element-plus'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import 'element-plus/dist/index.css'
const router=createRouter({history:createWebHashHistory(),routes:[{path:'/:pathMatch(.*)*',component:{template:'<span />'}}]})
createApp(MobileApp).component('AssistedInput',AssistedInput).component('AssistedTextarea',AssistedTextarea).use(router).use(ElementPlus,{locale:zhCn}).mount('#app')
