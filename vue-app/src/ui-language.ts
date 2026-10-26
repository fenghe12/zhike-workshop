import {ref,watch} from 'vue'
import {catalog} from './locales/catalog'
import {authDesign} from './locales/auth-design'
import {examples} from './locales/examples'
import {errors} from './locales/errors'
import {legalCopy,legalTitles} from './locales/legal'
export type UiLanguage='zh'|'en'|'ja'|'ru'|'fr'|'es'|'de'
export const uiLanguages=[{code:'zh',name:'中文',tag:'zh-CN'},{code:'en',name:'English',tag:'en-US'},{code:'ja',name:'日本語',tag:'ja-JP'},{code:'ru',name:'Русский',tag:'ru-RU'},{code:'fr',name:'Français',tag:'fr-FR'},{code:'es',name:'Español',tag:'es-ES'},{code:'de',name:'Deutsch',tag:'de-DE'}]
let initial:UiLanguage='zh'
try{const saved=localStorage.getItem('smartcourse-ui-language');if(uiLanguages.some(x=>x.code===saved))initial=saved as UiLanguage}catch{}
export const uiLanguage=ref<UiLanguage>(initial)
const columns=['en','ja','ru','fr','es','de']
const messages:Record<string,string[]>={...catalog,...authDesign,...examples,...errors,...legalTitles,
 '已登录':['Signed in','ログイン済み','Вход выполнен','Connecté','Sesión iniciada','Angemeldet']}
export function t(value:unknown):string{
 const key=String(value??'')
 if(uiLanguage.value==='zh')return key
 const index=columns.indexOf(uiLanguage.value)
 return messages[key]?.[index]??key
}
export function localeTag(){return uiLanguages.find(x=>x.code===uiLanguage.value)?.tag||'zh-CN'}
export function policyText(kind:string,index:number,original:string){
 if(uiLanguage.value==='zh')return original
 return legalCopy[kind+'.'+index]?.[columns.indexOf(uiLanguage.value)]??original
}
watch(uiLanguage,value=>{
 try{localStorage.setItem('smartcourse-ui-language',value)}catch{}
 if(typeof document!=='undefined'){document.documentElement.lang=localeTag();document.title=t('智课工坊')}
},{immediate:true})
