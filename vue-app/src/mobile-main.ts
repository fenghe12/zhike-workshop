import {createApp} from 'vue'
import {createRouter,createWebHashHistory} from 'vue-router'
import MobileApp from './MobileApp.vue'
const router=createRouter({history:createWebHashHistory(),routes:[{path:'/:pathMatch(.*)*',component:{template:'<span />'}}]})
createApp(MobileApp).use(router).mount('#app')
