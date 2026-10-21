import {createApp} from 'vue'
import {createRouter,createWebHashHistory} from 'vue-router'
import ElementPlus from 'element-plus'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import 'element-plus/dist/index.css'
import App from './App.vue'
import './style.css'
const router=createRouter({history:createWebHashHistory(),routes:[{path:'/:pathMatch(.*)*',component:{template:'<span />'}}]})
createApp(App).use(router).use(ElementPlus,{locale:zhCn}).mount('#app')
