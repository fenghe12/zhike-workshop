import {confirmMediaUse} from './media-consent'
export interface Stage {index:number;code:string;title:string;status:string;progress?:number;elapsedSeconds?:number;etaSeconds?:number;detail?:Record<string,unknown>}
export interface Task {id:string;name:string;status:string;targetLanguages:string[];currentStage:number;overallProgress:number;stages:Stage[];outputs?:Record<string,unknown>;assets?:Record<string,{name:string;path:string}|null>;requiredAsset?:string;error?:{message:string};updatedAt?:string;featuredForTeaching?:boolean;queue?:{state:string;position?:number;resource?:string;message?:string}}
export class ApiError extends Error {constructor(message:string,public status:number){super(message)}}
export async function api<T>(path:string,options:RequestInit={}):Promise<T>{
 if(path==='/v1/uploads'&&typeof options.body==='string'){
  const body=JSON.parse(options.body)
  if(['image','audio'].includes(body.kind)&&!body.mediaConsent){body.mediaConsent=await confirmMediaUse();options={...options,body:JSON.stringify(body)}}
 }
 const token=sessionStorage.getItem('smartcourse-token')
 let r:Response
 try{r=await fetch(path,{...options,headers:{'Content-Type':'application/json',...(token?{Authorization:`Bearer ${token}`}:{ }),...options.headers},signal:AbortSignal.timeout(30000)})}catch{throw Error('暂时无法连接生成服务。请稍后重试，已填写内容会保留。')}
 let d:any;try{d=await r.json()}catch{throw Error('生成服务暂未就绪，请稍后重试。')}
 if(!r.ok)throw new ApiError(d.message||d.detail||'操作未完成，请重试。',r.status)
 return d as T
}
export const post=<T>(path:string,body:unknown)=>api<T>(path,{method:'POST',body:JSON.stringify(body)})
