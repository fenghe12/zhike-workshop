import {createApp} from 'vue'
import {createRouter,createWebHashHistory} from 'vue-router'
import MobileApp from './MobileApp.vue'
import ElementPlus from 'element-plus'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import 'element-plus/dist/index.css'
const router=createRouter({history:createWebHashHistory(),routes:[{path:'/:pathMatch(.*)*',component:{template:'<span />'}}]})
createApp(MobileApp).use(router).use(ElementPlus,{locale:zhCn}).mount('#app')
