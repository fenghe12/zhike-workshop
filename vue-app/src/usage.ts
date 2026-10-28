import {post} from './api'
export function recordUsage(kind:string,detail:Record<string,unknown>={}){
 void post(kind==='page_view'?'/v1/visits':'/v1/usage',{kind,...detail,eventId:globalThis.crypto?.randomUUID?.()||Date.now()+'-'+Math.random()}).catch(()=>{})
}
